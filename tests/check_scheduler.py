"""Check the upkeep thread -- scheduler.py, ADR 0020.

No network: web.load_problemset is replaced by a counter, and sync.start_sync
by one that writes a job row and starts no thread. What is checked is the
DECIDING -- what is due, and what is deliberately not done -- because the
fetching itself is checked where it lives.

The two that matter most:

  * VISITORS FIRST. Nothing is queued while any sync is waiting or running.
    A background refresh in front of somebody watching a progress page is
    four seconds they did not ask for, and this is the only thing standing
    between the queue and a nightly pile of work nobody is waiting for.
  * NOTHING IS REMEMBERED IN MEMORY that a restart would lose. The free
    instance restarts several times a day; what is due is asked of rows on
    disk, so a restart repeats nothing and forgets nothing.
"""

import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="scheduler-"))

# Must be set before db is imported: db.py reads it at import time.
os.environ["NEXTCF_DB"] = str(SCRATCH / "test.db")
# Paths in this file are relative to the repository root, and the modules
# being checked live there, so go there first. The check then runs the same
# from any directory.
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import scheduler  # noqa: E402
import sync  # noqa: E402
import web  # noqa: E402

passed = failed = 0


def check(label, fn):
    global passed, failed
    try:
        fn()
    except AssertionError as exc:
        print(f"  FAIL  {label}: {exc}")
        failed += 1
    except Exception as exc:
        print(f"  FAIL  {label}: crashed with {type(exc).__name__}: {exc}")
        failed += 1
    else:
        print(f"  ok    {label}")
        passed += 1


# ------------------------------------------------------------------ no network
fetches = []
fetch_succeeds = True


def fake_load_problemset():
    fetches.append(time.monotonic())
    return fetch_succeeds


def fake_start_sync(handle):
    conn = db.connect()
    try:
        active = db.get_active_job(conn, "sync", handle)
        if active is not None:
            return active["id"]
        return db.create_job(conn, "sync", handle)
    finally:
        conn.close()


web.load_problemset = fake_load_problemset
sync.start_sync = fake_start_sync

db.init_db()


def reset(problemset=1, fetched_just_now=True):
    """A database with no jobs, no visits and no users, and a clean clock."""
    global fetch_succeeds
    fetch_succeeds = True
    fetches.clear()
    conn = db.connect()
    try:
        with conn:
            conn.execute("DELETE FROM jobs")
            conn.execute("DELETE FROM visits")
            conn.execute("DELETE FROM submissions")
            conn.execute("DELETE FROM users")
            conn.execute("DELETE FROM problems")
            if problemset:
                conn.execute(
                    "INSERT INTO problems (id, contest_id, problem_index, name, rating, in_problemset)"
                    " VALUES ('1234A', 1234, 'A', 'Watermelon', 800, 1)"
                )
    finally:
        conn.close()
    scheduler._problemset_fetched_at = time.monotonic() if fetched_just_now else None


def seen(handle, last_synced, visited_at=None):
    """A user with a stored history, and a visit to their page."""
    conn = db.connect()
    try:
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO users (handle, cf_rating, first_seen, last_synced)"
                " VALUES (?, 1500, ?, ?)",
                (handle, "2026-01-01T00:00:00Z", last_synced),
            )
            if visited_at is not None:
                conn.execute(
                    "INSERT INTO visits (visitor_id, handle, path, visited_at)"
                    " VALUES ('aaaaaaaaaaaaaaaaaaaa', ?, '/results/x', ?)",
                    (handle, visited_at),
                )
    finally:
        conn.close()


def queued():
    conn = db.connect()
    try:
        return [row["target"] for row in conn.execute(
            "SELECT target FROM jobs WHERE state IN ('pending', 'running') ORDER BY id"
        )]
    finally:
        conn.close()


DAYS_AGO_2 = db.utc_ago(2 * 24 * 3600)
DAYS_AGO_40 = db.utc_ago(40 * 24 * 3600)
HOURS_AGO_30 = db.utc_ago(30 * 3600)


# ----------------------------------------------------------- the problemset
def an_empty_problemset_is_fetched_at_once():
    """The startup fetch failed, or this file was just created. Until this
    works the recommender has no candidates at all, so it does not wait."""
    reset(problemset=0)
    assert scheduler.problemset_is_due(db_conn := db.connect()), "an empty pool was not due"
    db_conn.close()
    assert "problemset" in scheduler.tick(), fetches


def a_fresh_problemset_is_left_alone():
    reset()
    assert scheduler.tick() == [], "fetched a problemset that was just fetched"
    assert fetches == [], fetches


def an_old_problemset_is_fetched_again():
    reset()
    scheduler._problemset_fetched_at = time.monotonic() - scheduler.PROBLEMSET_EVERY_SECONDS - 1
    assert "problemset" in scheduler.tick(), "an old problemset was not refreshed"
    assert len(fetches) == 1, fetches


def a_failed_fetch_is_tried_again_next_tick():
    """Not in six hours: the clock is only moved by a fetch that worked."""
    global fetch_succeeds
    reset()
    scheduler._problemset_fetched_at = time.monotonic() - scheduler.PROBLEMSET_EVERY_SECONDS - 1
    fetch_succeeds = False

    assert scheduler.tick() == [], "a failed fetch was reported as done"
    assert scheduler.tick() == [], "a failed fetch was reported as done"
    assert len(fetches) == 2, f"tried {len(fetches)} times, not twice"

    fetch_succeeds = True
    assert "problemset" in scheduler.tick(), "it gave up after failing"


# -------------------------------------------------------- who gets refreshed
def a_recent_visitor_with_an_old_history_is_refreshed():
    reset()
    seen("returning", last_synced=HOURS_AGO_30, visited_at=DAYS_AGO_2)
    assert scheduler.tick() == ["returning"], queued()
    assert queued() == ["returning"], queued()


def somebody_who_has_not_visited_is_left_alone():
    """Every user in the database was looked up by somebody once. The ones
    worth two requests a night are the ones who came back."""
    reset()
    seen("stranger", last_synced=HOURS_AGO_30, visited_at=None)
    seen("long_ago", last_synced=HOURS_AGO_30, visited_at=DAYS_AGO_40)
    assert scheduler.tick() == [], queued()


def a_history_that_is_already_fresh_is_left_alone():
    reset()
    seen("current", last_synced=db.utc_now(), visited_at=DAYS_AGO_2)
    assert scheduler.tick() == [], queued()


def the_oldest_history_goes_first():
    reset()
    seen("newer", last_synced=db.utc_ago(21 * 3600), visited_at=DAYS_AGO_2)
    seen("oldest", last_synced=db.utc_ago(80 * 3600), visited_at=DAYS_AGO_2)
    seen("middle", last_synced=db.utc_ago(40 * 3600), visited_at=DAYS_AGO_2)
    assert scheduler.tick() == ["oldest"], queued()


def only_one_user_a_tick():
    reset()
    for name in ("a", "b", "c"):
        seen(name, last_synced=HOURS_AGO_30, visited_at=DAYS_AGO_2)
    assert len(scheduler.tick()) == 1, "more than one refresh was queued at once"
    assert len(queued()) == 1, queued()


# --------------------------------------------------------------- visitors first
def nothing_is_queued_while_a_visitor_is_waiting():
    """The rule that keeps this from ever being in anybody's way."""
    reset()
    seen("returning", last_synced=HOURS_AGO_30, visited_at=DAYS_AGO_2)
    conn = db.connect()
    try:
        db.create_job(conn, "sync", "a_visitor")
    finally:
        conn.close()

    assert scheduler.tick() == [], "queued a background sync in front of a visitor"
    assert queued() == ["a_visitor"], queued()


def nothing_is_queued_while_its_own_last_job_is_running():
    reset()
    seen("returning", last_synced=HOURS_AGO_30, visited_at=DAYS_AGO_2)
    assert scheduler.tick() == ["returning"], "the first refresh was not queued"
    assert scheduler.tick() == [], "queued a second job while the first was waiting"


def the_problemset_is_refreshed_even_when_the_queue_is_busy():
    """It is one request and it blocks nobody's page; the rule above is about
    syncs, which are two requests each and stand in a visitor's way."""
    reset()
    scheduler._problemset_fetched_at = time.monotonic() - scheduler.PROBLEMSET_EVERY_SECONDS - 1
    conn = db.connect()
    try:
        db.create_job(conn, "sync", "a_visitor")
    finally:
        conn.close()
    assert scheduler.tick() == ["problemset"], "the problemset waited for the queue"


# ------------------------------------------------------------------- the thread
def the_loop_survives_a_tick_that_throws():
    real = scheduler.tick
    calls = []

    def angry():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("the first tick blew up")
        return []

    scheduler.tick = angry
    scheduler.TICK_SECONDS = 0.05
    try:
        thread = scheduler.start()
        deadline = time.monotonic() + 5
        while len(calls) < 3 and time.monotonic() < deadline:
            time.sleep(0.02)
        assert len(calls) >= 3, f"the loop stopped after {len(calls)} ticks"
        assert thread.is_alive(), "the scheduler thread died"
    finally:
        scheduler.tick = real
        scheduler.TICK_SECONDS = 30


def starting_it_twice_starts_one_thread():
    first = scheduler.start()
    second = scheduler.start()
    assert first is second, "a second scheduler thread was started"
    threads = [t for t in threading.enumerate() if t.name == "scheduler"]
    assert len(threads) == 1, f"{len(threads)} scheduler threads are running"


def the_entry_points_start_it():
    """A scheduler nobody starts is a problemset that ages for as long as the
    process stays up, and a failed startup fetch that is never retried."""
    for name in ("serve.py", "web.py"):
        source = Path(name).read_text(encoding="utf-8")
        assert "scheduler.start()" in source, f"{name} never starts the scheduler"


print("the problemset")
check("an empty problemset is fetched at once", an_empty_problemset_is_fetched_at_once)
check("a fresh one is left alone", a_fresh_problemset_is_left_alone)
check("an old one is fetched again", an_old_problemset_is_fetched_again)
check("a failed fetch is tried again next tick", a_failed_fetch_is_tried_again_next_tick)

print("\nwho gets refreshed")
check("a recent visitor with an old history", a_recent_visitor_with_an_old_history_is_refreshed)
check("somebody who has not visited is left alone", somebody_who_has_not_visited_is_left_alone)
check("a fresh history is left alone", a_history_that_is_already_fresh_is_left_alone)
check("the oldest history goes first", the_oldest_history_goes_first)
check("one user a tick, no more", only_one_user_a_tick)

print("\nvisitors first")
check("nothing queued while a visitor waits", nothing_is_queued_while_a_visitor_is_waiting)
check("nothing queued while its own job runs", nothing_is_queued_while_its_own_last_job_is_running)
check("the problemset does not wait for the queue", the_problemset_is_refreshed_even_when_the_queue_is_busy)

print("\nthe thread")
check("the loop survives a tick that throws", the_loop_survives_a_tick_that_throws)
check("starting it twice starts one thread", starting_it_twice_starts_one_thread)
check("the entry points start it", the_entry_points_start_it)

print(f"\n{passed} passed, {failed} failed")
shutil.rmtree(SCRATCH, ignore_errors=True)
sys.exit(1 if failed else 0)
