"""Upkeep that has to happen whether or not anybody is looking.

A thread inside the web app, not the host's scheduler: a cron service on
Render cannot read this service's disk, and a second program starting syncs
would break the rule that only the web app does (ADR 0007). Started by the
entry points -- serve.py, and `python web.py` -- never at import, so that
importing this module in a check reaches for nothing.

Two jobs, both described in ADR 0020:

    the problemset    Codeforces runs contests every week, and a problem that
                      is not in the pool can never be recommended. This
                      fetches it when the process starts -- the first tick
                      finds an empty pool and goes -- every six hours after
                      that, and again on the next tick whenever a fetch
                      fails.

    recent visitors   Somebody who came back once will come back again, and
                      their page is better if it is already fresh. One user
                      at a time, and only when nothing else is queued.

Neither job is a schedule. Both are the question "is anything due?", asked
from rows on disk, because this process restarts several times a day and a
plan kept in memory would either be repeated on every restart or lost with
it.

Usage:
    started by serve.py and web.py; nothing to run by hand
"""

import sys
import threading
import time

import db
import sync
import web

# How often the loop wakes to ask whether anything is due. Cheap: two small
# queries, and on most ticks the answer is no.
TICK_SECONDS = 30

# How old the problemset may get before it is fetched again. Codeforces runs
# a few contests a week, so a day would do; six hours costs four requests a
# day out of a budget of one every two seconds.
PROBLEMSET_EVERY_SECONDS = 6 * 3600

# Who counts as a recent visitor, and how stale their history has to be
# before it is worth two requests. Twenty hours rather than twenty-four so
# that somebody who visits at the same time each day is always due.
SEEN_WITHIN_SECONDS = 30 * 24 * 3600
STALE_AFTER_SECONDS = 20 * 3600

_thread = None
_thread_lock = threading.Lock()

# When the problemset was last fetched, on the monotonic clock. Deliberately
# in memory and not in the database: losing it means one extra fetch after a
# restart, which is one request, and the alternative is a row that has to be
# kept in step with something the database cannot see.
_problemset_fetched_at = None


def start():
    """Start the upkeep thread. Safe to call more than once.

    Called by the entry points only, for the same reason as
    sync.start_worker: every check imports web, and a loop that fetches the
    problemset inside a check would put a real request in a test built to
    make none.
    """
    global _thread
    with _thread_lock:
        # The clock is left unset on purpose: the first tick therefore counts
        # the problemset as due and fetches it, which IS the startup fetch.
        # The entry points used to start a separate thread for that, and the
        # two raced -- the fetch was still in flight when the first tick
        # found an empty pool and fetched it a second time. One owner.
        if _thread is None or not _thread.is_alive():
            _thread = threading.Thread(target=run, name="scheduler", daemon=True)
            _thread.start()
    return _thread


def run():
    """Ask what is due, do at most one thing about it, sleep. Forever."""
    while True:
        try:
            tick()
        except Exception as exc:
            # Same reasoning as the sync worker: a thread that dies takes its
            # own error message with it, and nothing else would ever notice
            # that the problemset had stopped being refreshed.
            print(f"scheduler: {type(exc).__name__}: {exc}", file=sys.stderr)
        time.sleep(TICK_SECONDS)


def tick():
    """One pass. Returns what it did, which is usually nothing.

    The return value is for the checks and for the log. Keeping the loop's
    body in a function with no sleeping in it is what makes the decisions
    testable without waiting for a clock.
    """
    done = []
    conn = db.connect()
    try:
        if problemset_is_due(conn):
            if refresh_problemset(conn):
                done.append("problemset")

        handle = user_to_refresh(conn)
        if handle is not None:
            sync.start_sync(handle)
            done.append(handle)
    finally:
        conn.close()
    return done


def problemset_is_due(conn):
    """Old enough to be worth a request, or missing altogether."""
    # Empty means the startup fetch failed, or this database was just
    # created. Either way the recommender has no candidates at all until this
    # is fixed, so it does not wait six hours.
    if db.problemset_size(conn) == 0:
        return True
    if _problemset_fetched_at is None:
        return True
    return time.monotonic() - _problemset_fetched_at >= PROBLEMSET_EVERY_SECONDS


def refresh_problemset(conn):
    """Fetch the problemset again and rebuild the alias map. True if it worked.

    web.load_problemset does the work; this decides when. The direction of
    that dependency is the right way round -- the scheduler is a thread
    inside the web app (ADR 0007), not something the app is built on.
    """
    global _problemset_fetched_at
    if web.load_problemset():
        _problemset_fetched_at = time.monotonic()
        return True
    # A failure leaves the clock alone, so the next tick tries again rather
    # than waiting six hours to find out whether the network came back.
    return False


def user_to_refresh(conn):
    """One handle worth re-syncing now, or None.

    **Visitors first.** Nothing is queued while any sync is waiting or
    running: a visitor watching a progress page is worth more than keeping
    somebody else's history warm, and one background job in front of them is
    four seconds they did not ask for. It also means this cannot build a
    queue -- there is never more than one of these jobs in flight.
    """
    if db.count_unfinished_jobs(conn) > 0:
        return None
    return db.next_user_to_refresh(
        conn,
        seen_since=db.utc_ago(SEEN_WITHIN_SECONDS),
        synced_before=db.utc_ago(STALE_AFTER_SECONDS),
    )
