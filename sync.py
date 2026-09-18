"""Fetch one user's whole Codeforces history, as a background job.

This cannot happen inside a web request. A sync is two API calls, and every
call waits for a two-second turn shared with everybody else syncing at the
same moment -- a few seconds alone, much longer in a queue -- and a browser
request cannot be held open for that. So web.py starts one of these and
immediately returns a progress page, which polls the `jobs` row this file
keeps up to date.

ADR 0004: an interrupted sync writes NOTHING. Everything is fetched into
memory first, then handed to db.save_sync, which writes it in one transaction.
If the process dies at any point before that, the database is untouched and
the next attempt starts from the beginning. `jobs.state` is what the progress
page follows; `jobs.progress` records how many submissions arrived.

Usage:
    .venv\\Scripts\\python.exe sync.py tourist
"""

import sqlite3
import sys
import threading
import time
import urllib.error

import api_client
import db

# One request per sync, for the whole history.
#
# This used to page 1000 at a time so the progress page could count upwards.
# Once api_client made every request wait for a two-second turn, each extra
# page cost two seconds: jiangly's 11,148 submissions were 13 requests and
# about 26 seconds, against 2 requests and about 5 in one go. Most people are a
# single page either way -- 18 of 25 random users rated 1000-1900 had under
# 1000 submissions -- so the saving lands on long histories, and on everybody
# queued behind them. The progress page lost its count in exchange, and a
# count that goes from nothing to everything in one step was not worth
# keeping. Paging, and the ordering trap that came with it, are gone with it.


def fetch_history(handle, job_id, conn):
    """Fetch a user's whole history in one request.

    Returns the raw list of submission dicts, newest first.

    Nothing is written to the database here except the progress number. That
    is the whole point: the history exists only in memory until save_sync.
    """
    submissions = api_client.fetch_submissions(handle)

    # Recorded for the jobs table, not for the progress page: with one request
    # there is no moment between "none" and "all", so the page shows no number.
    db.set_job_progress(conn, job_id, len(submissions))

    return submissions


def run_sync(handle, job_id):
    """Do one whole sync. This is what the background thread runs.

    It opens its own connection, because a sqlite3 connection belongs to the
    thread that created it.
    """
    conn = db.connect()
    try:
        db.start_job(conn, job_id)

        try:
            # user.info first, for two things user.status does not give: the
            # canonical spelling of the handle, and the Codeforces rating.
            # Everything after this uses the API's spelling, never the one
            # typed into the form.
            user = api_client.fetch_user(handle)
            canonical = user["handle"]

            submissions = fetch_history(canonical, job_id, conn)

            # The rating history too -- a third request, and the reason a sync
            # takes two seconds longer than it did. The model predicts each
            # past attempt from the rating its author had AT THE TIME (ADR
            # 0009, 0014); with only today's rating, somebody who climbed from
            # 1200 to 1600 would have their 1200-era failures read as a
            # 1600-rated user failing, be judged weaker than they are, and be
            # recommended problems that are too easy. collect.py has always
            # fetched this; the website now does the same thing for the same
            # reason.
            changes = api_client.fetch_rating_changes(canonical)

            # One call, one transaction, all or nothing. ADR 0004.
            db.save_sync(conn, canonical, user.get("rating"), submissions,
                         rating_changes=changes)

        except RuntimeError as exc:
            # Codeforces answered and refused -- nearly always a handle that
            # does not exist, and api_client has already dug the real
            # explanation out of the error body.
            db.finish_job(conn, job_id, error=f"Codeforces rejected the request: {exc}")

        except urllib.error.URLError as exc:
            # The network itself failed. Ordering note, same as web.py:
            # HTTPError is a subclass of URLError, so this clause would
            # swallow it -- api_client turns it into RuntimeError first.
            db.finish_job(conn, job_id, error=f"Could not reach Codeforces: {exc.reason}")

        except Exception as exc:
            # A bare `except Exception` is usually a mistake. Here it is the
            # opposite. This runs in a thread whose only way to tell anyone
            # anything is the jobs row, so an exception that escaped would
            # kill the thread in silence and leave the job marked running
            # forever, with the progress page spinning for a visitor who will
            # never be told. The real error goes to the log, not to them.
            db.finish_job(conn, job_id, error="Something went wrong on our side.")
            print(f"sync job {job_id} ({handle}) failed: {type(exc).__name__}: {exc}", file=sys.stderr)

        else:
            db.finish_job(conn, job_id)

    finally:
        conn.close()


def start_sync(handle):
    """Start a background sync and return the id of the job to watch.

    If this handle is already syncing, returns that job instead of starting a
    second one -- two visitors typing the same handle should watch the same
    work, not double the load on the API.
    """
    conn = db.connect()
    try:
        active = db.get_active_job(conn, "sync", handle)
        if active is not None:
            return active["id"]

        try:
            job_id = db.create_job(conn, "sync", handle)
        except sqlite3.IntegrityError:
            # Both visitors looked, both saw nothing, both tried to create.
            # The unique index on jobs is the real guard -- the check above is
            # only an optimisation -- so whoever lost reads back the job the
            # winner created.
            active = db.get_active_job(conn, "sync", handle)
            if active is None:
                raise
            return active["id"]
    finally:
        conn.close()

    # daemon=True: this thread does not keep the process alive at shutdown.
    # Killing a sync mid-flight costs nothing, because it has written nothing
    # (ADR 0004), and fail_orphaned_jobs() marks the abandoned job failed the
    # next time the web app starts.
    threading.Thread(target=run_sync, args=(handle, job_id), daemon=True).start()
    return job_id


def main():
    handle = sys.argv[1] if len(sys.argv) > 1 else "tourist"

    # init_db() only, never fail_orphaned_jobs(): this may be run by hand while
    # the web app is mid-sync on the same file. ADR 0007.
    db.init_db()
    job_id = start_sync(handle)
    print(f"job {job_id}: syncing {handle}")

    # Follow the job from outside, the same way the progress page will: by
    # reading the jobs row. Nothing here talks to the thread directly, which
    # is the point of keeping job state in the database.
    conn = db.connect()
    try:
        last_seen = None
        while True:
            job = db.get_job(conn, job_id)
            if job["progress"] != last_seen:
                last_seen = job["progress"]
                print(f"  {last_seen} submissions fetched")
            if job["state"] in ("done", "failed"):
                break
            time.sleep(0.5)

        print(f"{job['state']}{': ' + job['error'] if job['error'] else ''}")

        rows = db.get_submissions(conn, handle)
        if rows is None:
            print("nothing stored -- this handle has no completed sync")
        else:
            print(f"{len(rows)} submissions stored")
    finally:
        conn.close()

    return 0 if job["state"] == "done" else 1


if __name__ == "__main__":
    sys.exit(main())
