"""Fetch one user's whole Codeforces history, as a background job.

This cannot happen inside a web request. A sync is two API calls, and every
call waits for a two-second turn shared with everybody else syncing at the
same moment -- a few seconds alone, much longer in a queue -- and a browser
request cannot be held open for that. So web.py starts one of these and
immediately returns a progress page, which polls the `jobs` row this file
keeps up to date.

Since ADR 0018 they run ONE AT A TIME, in the order they were asked for: one
worker thread, and the `jobs` table as the queue. See "the queue" below for
what that is worth and what it cost.

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


def canonical_spelling(typed, submissions, changes):
    """The handle as Codeforces spells it, from what the sync fetched anyway.

    Stored under that spelling, never the typed one, or "TOURIST" and
    "tourist" would be displayed as two people. A rating change carries it.
    Failing that, a submission made alone does -- a team's lists several
    members, and the visitor need not be the first. Failing both, nothing
    fetched spells it and the typed form is kept: somebody with no contests
    and no solo submissions has nothing on the page to misspell.
    """
    for change in changes:
        if change.get("handle"):
            return change["handle"]
    for sub in submissions:
        members = sub.get("author", {}).get("members", [])
        if len(members) == 1 and members[0].get("handle", "").lower() == typed.lower():
            return members[0]["handle"]
    return typed


def run_sync(handle, job_id):
    """Do one whole sync. This is what the background thread runs.

    It opens its own connection, because a sqlite3 connection belongs to the
    thread that created it.
    """
    conn = db.connect()
    try:
        if not db.claim_job(conn, job_id):
            # Somebody else got there first: the web app's worker, or sync.py
            # run by hand against the same file. Fetching one user twice would
            # cost every other visitor four seconds of queue for nothing.
            return

        try:
            # Codeforces handles are case-insensitive, so both requests accept
            # the handle as typed; a handle that does not exist is refused by
            # the first of them.
            submissions = fetch_history(handle, job_id, conn)

            # The rating history: the model predicts each past attempt from
            # the rating its author had AT THE TIME (ADR 0009, 0014). With
            # only today's rating, somebody who climbed from 1200 to 1600
            # would have their 1200-era failures read as a 1600-rated user
            # failing, be judged weaker than they are, and be recommended
            # problems that are too easy.
            changes = api_client.fetch_rating_changes(handle)

            # Two requests, not three. user.info used to come first, for the
            # canonical spelling of the handle and the current rating -- and
            # both were already in what these two return: every rating change
            # carries the handle as Codeforces spells it, and the newest one's
            # newRating IS the current rating. Every request waits for a
            # two-second turn, so this took two seconds off every sync and off
            # everybody queued behind it: the tenth visitor in a queue now
            # waits about 40 seconds, not 60.
            canonical = canonical_spelling(handle, submissions, changes)
            rating = changes[-1]["newRating"] if changes else None

            # One call, one transaction, all or nothing. ADR 0004.
            db.save_sync(conn, canonical, rating, submissions, rating_changes=changes)

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


# ------------------------------------------------------------------ the queue
#
# ADR 0018: syncs run ONE AT A TIME, in the order they were asked for.
#
# Until 2026-09-22 each sync ran in a thread of its own, and api_client's
# limiter gave the next two-second slot to whichever thread asked for it, so
# requests from different visitors interleaved and ten visitors arriving
# together all finished near the fortieth second. Nobody chose that: it fell
# out of one thread per sync plus one shared limiter. It was also right, until
# a sync stopped paging a thousand submissions at a time and every job became
# the same two requests -- interleaving protects short jobs from long ones,
# and there are no long ones any more.
#
# One at a time cannot make the last visitor's wait any shorter: the rate
# limit decides that and nothing here can argue with it. What it does is stop
# everybody else waiting that long too. Ten visitors: the first is finished in
# four seconds instead of twenty-two, the average falls from thirty-one to
# twenty-two, the last is unchanged at forty. And it is what makes "you are
# 7th in the queue" a sentence that is true -- under interleaving everybody is
# tenth.

# The worker sleeps on this between jobs; start_sync sets it. The jobs table
# is the queue -- it already had to be, to survive a restart -- so this is
# only a doorbell, not a second copy of the work.
_wake = threading.Event()

# How long the worker waits before looking anyway. The doorbell covers jobs
# this process created; the timeout covers a job written to the same file by
# another process, which cannot ring it.
IDLE_SECONDS = 5.0

_worker_lock = threading.Lock()
_worker = None


def start_worker():
    """Start the one thread that runs syncs. Safe to call twice.

    Called by the entry points -- serve.py, and `python web.py` -- and never
    at import, for the same reason scheduler.start() is: every check imports
    web, and a thread looking for work inside a check would fetch from
    Codeforces in tests built to touch no network.
    """
    global _worker
    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, name="sync-worker", daemon=True)
            _worker.start()
    return _worker


def _work():
    """Take the oldest waiting job, run it, look again. Forever.

    daemon=True, so it does not keep the process alive at shutdown: a sync
    killed mid-flight has written nothing (ADR 0004), and fail_orphaned_jobs()
    fails whatever was left behind when the app next starts.
    """
    while True:
        job = None
        try:
            conn = db.connect()
            try:
                job = db.next_pending_job(conn)
            finally:
                conn.close()

            if job is None:
                _wake.wait(timeout=IDLE_SECONDS)
                _wake.clear()
                continue

            run_sync(job["target"], job["id"])

        except Exception as exc:
            # This thread is the only thing that runs syncs anywhere. If it
            # dies, every visitor watches a page that will never change and
            # nothing says why. run_sync reports its own failures into the
            # jobs row; this is for what surrounds it -- a database that would
            # not open, most likely -- and the pause keeps a permanent failure
            # from filling the log in a tight loop.
            print(f"sync worker: {type(exc).__name__}: {exc}", file=sys.stderr)
            _abandon(job)
            time.sleep(IDLE_SECONDS)


def _abandon(job):
    """Close a job whose run threw, so that nobody waits on it for ever.

    run_sync writes its own failures into the jobs row, so reaching here means
    something outside its reach threw -- and the row is still 'running'. One
    worker runs the queue, so a row left running is a visitor whose page
    counts down until they give up, and the next job cannot start either.
    """
    if job is None:
        return
    try:
        conn = db.connect()
        try:
            db.finish_job(conn, job["id"], error="Something went wrong on our side.")
        finally:
            conn.close()
    except Exception as exc:
        print(f"sync worker: could not close job {job['id']}: {exc}", file=sys.stderr)


def start_sync(handle):
    """Put a sync in the queue and return the id of the job to watch.

    Starts nothing itself: the worker above runs it when the jobs in front of
    it are done. If this handle is already syncing, returns that job instead
    of queueing a second -- two visitors typing the same handle should watch
    the same work, not double the load on the API.
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

    # Ring the doorbell. If the worker is asleep it looks again at once; if it
    # is busy it will find this job when it finishes the one in hand.
    _wake.set()
    return job_id


def main():
    handle = sys.argv[1] if len(sys.argv) > 1 else "tourist"

    # init_db() only, never fail_orphaned_jobs(): this may be run by hand while
    # the web app is mid-sync on the same file. ADR 0007.
    db.init_db()
    job_id = start_sync(handle)
    print(f"job {job_id}: syncing {handle}")

    # Run it here rather than starting a worker. A worker started in this
    # process would be a second runner on the file, and could pick up a job
    # the web app queued -- ADR 0007 keeps the queue the web app's. The claim
    # inside run_sync is what makes even this safe if the web app happens to
    # be running: whoever claims the job first does the work, and the loop
    # below follows the row either way.
    threading.Thread(target=run_sync, args=(handle, job_id), daemon=True).start()

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
