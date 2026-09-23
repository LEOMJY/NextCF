"""Check the sync queue and the progress page -- ADR 0018.

No network: sync.run_sync is replaced with a recorder that claims and closes
the job the way the real one does, so the worker loop itself is exercised
without a single request leaving the machine.

The two that matter most:

  * ONE AT A TIME, OLDEST FIRST. Everything the progress page says about
    position and seconds is only true because of it. If two syncs ever
    overlap, the page is not slightly off -- it is quoting a queue that does
    not exist.
  * A CLAIMED JOB CANNOT BE CLAIMED TWICE. The web app runs one worker, but
    sync.py run by hand is a second process on the same file, and fetching one
    user twice costs everybody else four seconds of queue.

The checks that need jobs to sit still come first; the worker is only started
at the end, because once it runs it eats the queue.
"""

import os
import re
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="queue-"))

# Must be set before db is imported: db.py reads it at import time.
os.environ["NEXTCF_DB"] = str(SCRATCH / "test.db")
# Paths in this file are relative to the repository root, and the modules
# being checked live there, so go there first. The check then runs the same
# from any directory.
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import api_client  # noqa: E402
import db  # noqa: E402
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


db.init_db()
client = web.app.test_client()


def clear_jobs():
    conn = db.connect()
    try:
        with conn:
            conn.execute("DELETE FROM jobs")
    finally:
        conn.close()


def queue(*handles):
    """Put jobs in the queue by hand, in this order. Returns their ids."""
    conn = db.connect()
    try:
        return [db.create_job(conn, "sync", handle) for handle in handles]
    finally:
        conn.close()


def job_state(job_id):
    conn = db.connect()
    try:
        return db.get_job(conn, job_id)["state"]
    finally:
        conn.close()


def stored(handle, last_synced):
    """A user with a finished sync, aged to order."""
    conn = db.connect()
    try:
        db.save_sync(conn, handle, 1500, [{
            "id": abs(hash(handle)) % 10**8,
            "problem": {"contestId": 1234, "index": "A", "name": "Watermelon",
                        "tags": ["math"], "rating": 800},
            "creationTimeSeconds": 1600000000,
            "author": {"participantType": "PRACTICE"},
            "verdict": "OK",
        }])
        with conn:
            conn.execute("UPDATE users SET last_synced = ? WHERE handle = ?", (last_synced, handle))
    finally:
        conn.close()


# ------------------------------------------------------------------ claiming
def a_job_is_claimed_once():
    clear_jobs()
    (job_id,) = queue("tourist")
    conn = db.connect()
    try:
        assert db.claim_job(conn, job_id) is True, "the first claim failed"
        assert db.claim_job(conn, job_id) is False, "the same job was claimed twice"
        assert db.get_job(conn, job_id)["state"] == "running"
    finally:
        conn.close()


def a_finished_job_cannot_be_claimed():
    clear_jobs()
    (job_id,) = queue("tourist")
    conn = db.connect()
    try:
        db.claim_job(conn, job_id)
        db.finish_job(conn, job_id)
        assert db.claim_job(conn, job_id) is False, "a finished job was claimed"
        assert db.get_job(conn, job_id)["state"] == "done", "the state was overwritten"
    finally:
        conn.close()


def the_oldest_waiting_job_is_next():
    clear_jobs()
    first, second, third = queue("alpha", "beta", "gamma")
    conn = db.connect()
    try:
        assert db.next_pending_job(conn)["id"] == first, "not the oldest"
        db.claim_job(conn, first)
        assert db.next_pending_job(conn)["id"] == second, "did not move on"
        db.finish_job(conn, first)
        db.claim_job(conn, second)
        db.finish_job(conn, second)
        assert db.next_pending_job(conn)["id"] == third
        db.claim_job(conn, third)
        db.finish_job(conn, third)
        assert db.next_pending_job(conn) is None, "found work when the queue was empty"
    finally:
        conn.close()


def only_unfinished_older_jobs_are_ahead():
    clear_jobs()
    first, second, third, fourth = queue("a", "b", "c", "d")
    conn = db.connect()
    try:
        assert db.jobs_ahead(conn, fourth) == 3, db.jobs_ahead(conn, fourth)
        db.claim_job(conn, first)
        db.finish_job(conn, first)
        assert db.jobs_ahead(conn, fourth) == 2, "a finished job still counted"
        db.claim_job(conn, second)
        assert db.jobs_ahead(conn, fourth) == 2, "a running job stopped counting"
        assert db.jobs_ahead(conn, second) == 0, "the running job was behind something"
        assert db.jobs_ahead(conn, third) == 1
    finally:
        conn.close()


# ------------------------------------------------------------ the page's maths
def the_progress_page_gives_a_position_and_seconds():
    clear_jobs()
    ids = queue("a", "b", "c")
    html = client.get(f"/progress/{ids[2]}").get_data(as_text=True)

    assert "2 syncs ahead of yours" in html, html[:400]
    # Three jobs of two requests, two seconds a request, one at a time.
    seconds = int(3 * web.SECONDS_PER_SYNC)
    assert f">{seconds}</span>" in html, f"expected {seconds} seconds in the page"


def one_sync_ahead_is_not_plural():
    clear_jobs()
    ids = queue("a", "b")
    html = client.get(f"/progress/{ids[1]}").get_data(as_text=True)
    assert "1 sync ahead of yours" in html, html[:400]


def the_job_at_the_front_is_told_it_is_fetching():
    clear_jobs()
    (job_id,) = queue("a")
    html = client.get(f"/progress/{job_id}").get_data(as_text=True)
    assert "Fetching from Codeforces" in html, html[:400]
    assert "ahead of yours" not in html, "a lone job was told it was queued"


def the_estimate_is_readable_without_javascript():
    """The script only counts down; the number itself is in the HTML."""
    clear_jobs()
    ids = queue("a", "b", "c", "d")
    html = client.get(f"/progress/{ids[3]}").get_data(as_text=True)
    without_script = re.sub(r"(?s)<script.*?</script>", "", html)
    seconds = int(4 * web.SECONDS_PER_SYNC)
    assert f"about <span" in without_script, "the estimate lives only in the script"
    assert f">{seconds}</span>" in without_script, without_script[-600:]


def the_page_polls_less_often_further_back():
    clear_jobs()
    ids = queue(*[f"user{n}" for n in range(12)])

    front = client.get(f"/progress/{ids[0]}").get_data(as_text=True)
    back = client.get(f"/progress/{ids[11]}").get_data(as_text=True)

    assert f'content="{web.MIN_REFRESH_SECONDS}"' in front, "the front of the queue is not polling quickly"
    assert f'content="{web.MAX_REFRESH_SECONDS}"' in back, "the back of the queue is polling too often"


def the_estimate_follows_the_rate_limit():
    """The page's arithmetic is derived from the limit, not typed into it."""
    assert web.SECONDS_PER_SYNC == 2 * api_client.SECONDS_BETWEEN_REQUESTS, web.SECONDS_PER_SYNC


# ---------------------------------------------------- what a returning visitor sees
def active_job_for(handle):
    conn = db.connect()
    try:
        return db.get_active_job(conn, "sync", handle)
    finally:
        conn.close()


def stale_results_are_shown_at_once_and_nothing_is_queued():
    """ADR 0018 as amended: the visitor decides whether to spend two requests
    from a queue everybody shares. Looking at a page is not asking for that."""
    clear_jobs()
    stored("returning", "2026-01-01T00:00:00Z")
    response = client.get("/results/returning")
    html = response.get_data(as_text=True)

    assert response.status_code == 200, f"a returning visitor was sent to a queue ({response.status_code})"
    assert "These numbers are from the sync above" in html, "old numbers were shown as if current"
    assert "Update from Codeforces" in html, "there is no way to ask for a fresh copy"
    assert active_job_for("returning") is None, "reading a page queued a sync nobody asked for"


def fresh_results_offer_the_button_quietly():
    clear_jobs()
    stored("current", db.utc_now())
    html = client.get("/results/current").get_data(as_text=True)

    assert "These numbers are from the sync above" not in html, "fresh numbers were called old"
    # Still offered: somebody who solved a problem two minutes ago is inside
    # the freshness window and is exactly who wants this button.
    assert "Update from Codeforces" in html, "a fresh page offers no way to update"
    assert active_job_for("current") is None, "a fresh page queued a sync"


def the_button_queues_a_sync_and_shows_the_queue():
    clear_jobs()
    stored("asks", "2026-01-01T00:00:00Z")
    response = client.post("/results/asks/sync")

    assert response.status_code == 302, response.status_code
    assert "/progress/" in response.headers["Location"], response.headers["Location"]

    job = active_job_for("asks")
    assert job is not None, "the button queued nothing"
    assert str(job["id"]) in response.headers["Location"], "sent to somebody else's job"


def only_a_post_can_start_a_sync():
    """A GET that starts work is followed by prefetchers, crawlers and link
    checkers, and each would take a turn in the queue."""
    clear_jobs()
    stored("get_only", "2026-01-01T00:00:00Z")
    response = client.get("/results/get_only/sync")

    assert response.status_code == 405, response.status_code
    assert active_job_for("get_only") is None, "a GET started a sync"


def a_sync_already_running_is_a_link_not_a_second_button():
    clear_jobs()
    stored("watching", "2026-01-01T00:00:00Z")
    queue("watching")
    html = client.get("/results/watching").get_data(as_text=True)

    assert "running now" in html, "the page did not mention the sync in flight"
    assert "Update from Codeforces" not in html, "offered to queue a second sync for one handle"


def a_visitor_with_nothing_stored_waits():
    clear_jobs()
    response = client.get("/results/nobody_here_yet")
    assert response.status_code == 302, response.status_code
    assert "/progress/" in response.headers["Location"], response.headers["Location"]


def two_visitors_asking_for_one_handle_share_a_job():
    clear_jobs()
    first = client.get("/results/shared_handle").headers["Location"]
    second = client.get("/results/shared_handle").headers["Location"]
    assert first == second, f"{first} != {second}"


# ------------------------------------------------------------------ the worker
#
# From here on the worker is running, so nothing above can expect a job to sit
# still. run_sync is replaced first: the real one would fetch from Codeforces.

ran = []
overlaps = []
_running = 0
_count_lock = threading.Lock()


def fake_run_sync(handle, job_id):
    """Claims and closes a job like the real one, without the network.

    The counter is incremented and decremented in ONE pair of brackets, after
    the claim succeeds. An earlier version decremented in an outer `finally`,
    which also ran when the claim failed and nothing had been counted -- so a
    run in which many callers lost the claim drove the count below zero and
    the overlap assertion below could never fire. A mutant that ran every sync
    in its own thread passed because of it. A fake that lies is worse than no
    fake: it makes the check look like evidence.
    """
    global _running
    conn = db.connect()
    try:
        if not db.claim_job(conn, job_id):
            return

        with _count_lock:
            _running += 1
            overlaps.append(_running)
        try:
            time.sleep(0.05)
            if handle == "explodes":
                raise RuntimeError("this job blew up in the worker's hands")
            db.finish_job(conn, job_id)
            ran.append(handle)
        finally:
            with _count_lock:
                _running -= 1
    finally:
        conn.close()


def wait_until(condition, seconds=10.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def the_worker_runs_them_oldest_first_and_one_at_a_time():
    clear_jobs()
    ran.clear()
    overlaps.clear()

    sync.run_sync = fake_run_sync
    sync.IDLE_SECONDS = 0.05          # the check owns the clock, not the wall
    handles = [f"user{n}" for n in range(6)]
    for handle in handles:
        sync.start_sync(handle)

    sync.start_worker()
    assert wait_until(lambda: len(ran) == len(handles)), f"only {len(ran)} of {len(handles)} ran: {ran}"
    assert ran == handles, f"out of order: {ran}"
    assert max(overlaps) == 1, f"{max(overlaps)} syncs ran at once"


def starting_the_worker_twice_starts_one_worker():
    first = sync.start_worker()
    second = sync.start_worker()
    assert first is second, "a second worker thread was started"
    assert first.is_alive(), "the worker died"
    workers = [t for t in threading.enumerate() if t.name == "sync-worker"]
    assert len(workers) == 1, f"{len(workers)} worker threads are running"


def a_job_that_blows_up_does_not_take_the_worker_with_it():
    """The worker is the only thing that runs syncs anywhere. If it dies, every
    visitor watches a page that will never change."""
    clear_jobs()
    ran.clear()
    exploded = sync.start_sync("explodes")
    sync.start_sync("survivor")

    assert wait_until(lambda: "survivor" in ran), f"the queue stopped after a failure: {ran}"

    # And the job it died on is closed rather than left running, or its own
    # visitor would count down for ever on a page that never changes.
    assert wait_until(lambda: job_state(exploded) == "failed"), \
        f"the exploded job is still {job_state(exploded)}"


def the_entry_points_start_the_worker():
    """A queue nobody runs is worse than no queue: every visitor waits for
    ever, and the page keeps promising it is nearly done."""
    for name in ("serve.py", "web.py"):
        source = Path(name).read_text(encoding="utf-8")
        assert "start_worker()" in source, f"{name} never starts the sync worker"


print("claiming")
check("a job is claimed exactly once", a_job_is_claimed_once)
check("a finished job cannot be claimed", a_finished_job_cannot_be_claimed)
check("the oldest waiting job is next", the_oldest_waiting_job_is_next)
check("only unfinished, older jobs count as ahead", only_unfinished_older_jobs_are_ahead)

print("\nwhat the page can say, because of it")
check("position and seconds on the page", the_progress_page_gives_a_position_and_seconds)
check("one sync ahead is not plural", one_sync_ahead_is_not_plural)
check("the job at the front is fetching, not queued", the_job_at_the_front_is_told_it_is_fetching)
check("the estimate is readable without JavaScript", the_estimate_is_readable_without_javascript)
check("the page polls less often further back", the_page_polls_less_often_further_back)
check("the estimate follows the rate limit", the_estimate_follows_the_rate_limit)

print("\nwhat a returning visitor sees")
check("stale results at once, and nothing queued", stale_results_are_shown_at_once_and_nothing_is_queued)
check("fresh results offer the button quietly", fresh_results_offer_the_button_quietly)
check("the button queues a sync and shows the queue", the_button_queues_a_sync_and_shows_the_queue)
check("only a POST can start a sync", only_a_post_can_start_a_sync)
check("a sync already running is a link, not a button", a_sync_already_running_is_a_link_not_a_second_button)
check("nothing stored means waiting", a_visitor_with_nothing_stored_waits)
check("two visitors, one handle, one job", two_visitors_asking_for_one_handle_share_a_job)

print("\nthe worker")
check("oldest first, one at a time", the_worker_runs_them_oldest_first_and_one_at_a_time)
check("starting it twice starts one worker", starting_the_worker_twice_starts_one_worker)
check("a job that blows up does not kill it", a_job_that_blows_up_does_not_take_the_worker_with_it)
check("the entry points start it", the_entry_points_start_the_worker)

print(f"\n{passed} passed, {failed} failed")
shutil.rmtree(SCRATCH, ignore_errors=True)
sys.exit(1 if failed else 0)
