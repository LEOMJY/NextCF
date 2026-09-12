"""Fetch one user's whole Codeforces history, as a background job.

This cannot happen inside a web request. A user with a few thousand
submissions needs several API calls and tens of seconds, and a browser cannot
be held open for that. So web.py starts one of these and immediately returns a
progress page, which polls the `jobs` row this file keeps up to date.

ADR 0004: an interrupted sync writes NOTHING. Everything is fetched into
memory first, then handed to db.save_sync, which writes it in one transaction.
If the process dies at any point before that, the database is untouched and
the next attempt starts from the beginning. `jobs.progress` exists to move a
progress bar, not to resume from.

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

# How many submissions to ask for per request.
#
# The trade is requests against progress. Asking for everything at once is
# fastest and leaves the progress bar at zero until it is over; asking 100 at
# a time gives the finest progress and needs 55 requests for a history like
# tourist's, which is slow and rude to an API that asks for one request every
# two seconds. 1000 puts almost every user in a single request and still moves
# the bar for the heavy ones.
PAGE_SIZE = 1000

# Codeforces asks for no more than one request every two seconds. Real rate
# limiting -- with retries and backoff, shared by every caller -- belongs in
# api_client at v0.3 (spec section 4), where collect.py will hit this limit
# for ~2000 users in a row. This is the minimum that keeps one sync polite,
# and only a user long enough to need a second page ever waits for it.
SECONDS_BETWEEN_PAGES = 2.0


def fetch_history(handle, job_id, conn):
    """Page through a user's whole history, reporting progress as it goes.

    Returns the raw list of submission dicts, newest first.

    Nothing is written to the database here except the progress number. That
    is the whole point: the history exists only in memory until save_sync.
    """
    submissions = []
    from_index = 1

    while True:
        page = api_client.fetch_submissions(handle, count=PAGE_SIZE, from_index=from_index)
        submissions.extend(page)

        # Progress is written outside any transaction, one small commit at a
        # time, so the progress page can actually see it while the job runs.
        db.set_job_progress(conn, job_id, len(submissions))

        # A short page means there was nothing more to send.
        if len(page) < PAGE_SIZE:
            return submissions

        # Paging is by position in a list that is ordered newest first, so a
        # submission made DURING this loop shifts everything down by one and
        # the next page repeats a row already collected. That is harmless:
        # save_sync keys submissions by Codeforces' own id, so a repeat
        # collapses. It would not be harmless in the other direction -- if the
        # API answered oldest first, the same shift would skip a row instead,
        # and nothing would notice. This loop is correct because of how
        # somebody else's API happens to sort. If that changes, this breaks
        # silently.
        from_index += PAGE_SIZE
        time.sleep(SECONDS_BETWEEN_PAGES)


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

            # One call, one transaction, all or nothing. ADR 0004.
            db.save_sync(conn, canonical, user.get("rating"), submissions)

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
    # (ADR 0004), and init_db() marks the abandoned job failed the next time
    # the app starts.
    threading.Thread(target=run_sync, args=(handle, job_id), daemon=True).start()
    return job_id


def main():
    handle = sys.argv[1] if len(sys.argv) > 1 else "tourist"

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
