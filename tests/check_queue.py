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


def waiting():
    """Which handles are queued or running, oldest first."""
    conn = db.connect()
    try:
        return [row["target"] for row in conn.execute(
            "SELECT target FROM jobs WHERE state IN ('pending', 'running') ORDER BY id"
        )]
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


def stale_results_are_shown_at_once_and_resynced_behind():
    """ADR 0018 as amended: the returning visitor never waits for a queue, and
    the page never quietly shows old numbers -- it carries a line saying a
    sync is running, where it is, and how long that is."""
    clear_jobs()
    stored("returning", "2026-01-01T00:00:00Z")
    response = client.get("/results/returning")
    html = response.get_data(as_text=True)

    assert response.status_code == 200, f"a returning visitor was sent to a queue ({response.status_code})"
    assert "Re-syncing" in html, "the page did not say a sync was running"
    assert "The numbers below are from the sync above" in html, "old numbers shown as if current"

    job = active_job_for("returning")
    assert job is not None, "nothing was queued to refresh it"
    assert f"/progress/{job['id']}/status" in html, "the line points at no job"
    assert "Update from Codeforces" not in html, "offered to start what is already running"


def the_line_carries_the_queue_without_javascript():
    """Everything the script would show is in the HTML at first render."""
    clear_jobs()
    stored("behind", "2026-01-01T00:00:00Z")
    queue("someone_else", "another")          # two syncs already waiting
    html = client.get("/results/behind").get_data(as_text=True)
    without_script = re.sub(r"(?s)<script.*?</script>", "", html)

    assert "2 syncs ahead of yours" in without_script, without_script[:600]
    seconds = int(3 * web.SECONDS_PER_SYNC)
    assert f">{seconds}</span>" in without_script, f"expected {seconds} seconds in the page"


def fresh_results_start_nothing_and_offer_the_button():
    clear_jobs()
    stored("current", db.utc_now())
    html = client.get("/results/current").get_data(as_text=True)

    assert "Re-syncing" not in html, "a fresh page started a sync"
    assert "from the sync above" not in html, "fresh numbers were called old"
    assert active_job_for("current") is None, "a fresh page queued a sync"
    # The case the automatic refresh cannot cover: somebody who was here eight
    # minutes ago and has solved something since.
    assert "Update from Codeforces" in html, "no way to refresh a page that counts as fresh"


def the_button_starts_a_sync_and_comes_back_to_the_page():
    clear_jobs()
    stored("presses", db.utc_now())
    response = client.post("/results/presses/sync")

    assert response.status_code == 302, response.status_code
    assert response.headers["Location"].endswith("/results/presses"), response.headers["Location"]

    job = active_job_for("presses")
    assert job is not None, "the button queued nothing"

    # And the page it lands back on now carries the live line instead.
    html = client.get("/results/presses").get_data(as_text=True)
    assert "Re-syncing" in html, "the page did not show the sync the visitor asked for"
    assert f"/progress/{job['id']}/status" in html, "the line points at no job"


def only_a_post_can_start_a_sync():
    """A GET that starts work is followed by prefetchers, crawlers and link
    checkers, and each would take a turn in the queue."""
    clear_jobs()
    stored("get_only", db.utc_now())
    response = client.get("/results/get_only/sync")

    assert response.status_code == 405, response.status_code
    assert active_job_for("get_only") is None, "a GET started a sync"


def a_junk_handle_cannot_be_queued_by_the_button():
    clear_jobs()
    response = client.post("/results/!!!/sync")
    assert response.status_code == 404, response.status_code


def a_running_sync_is_shown_even_when_the_numbers_are_fresh():
    """Another visitor may be syncing this handle, or this visitor may have
    just come back from the progress page. Either way the line is how they
    learn that the numbers in front of them are about to change."""
    clear_jobs()
    stored("fresh_but_busy", db.utc_now())
    (existing,) = queue("fresh_but_busy")
    html = client.get("/results/fresh_but_busy").get_data(as_text=True)

    assert "Re-syncing" in html, "a sync in flight was invisible on a fresh page"
    assert f"/progress/{existing}/status" in html, "the page watched some other job"


def a_sync_already_running_is_watched_not_duplicated():
    clear_jobs()
    stored("watching", "2026-01-01T00:00:00Z")
    (existing,) = queue("watching")
    html = client.get("/results/watching").get_data(as_text=True)

    assert f"/progress/{existing}/status" in html, "the page watched some other job"
    conn = db.connect()
    try:
        jobs = conn.execute("SELECT count(*) FROM jobs WHERE target = 'watching'").fetchone()[0]
    finally:
        conn.close()
    assert jobs == 1, f"{jobs} jobs queued for one handle"


# ------------------------------------------------------- the line, kept current
def the_status_endpoint_answers_with_the_same_line():
    """One wording, in one template. Two copies -- one in Jinja, one in
    JavaScript -- is how a page comes to say two different things."""
    clear_jobs()
    stored("live", "2026-01-01T00:00:00Z")
    page = client.get("/results/live").get_data(as_text=True)
    job = active_job_for("live")

    fragment = client.get(f"/progress/{job['id']}/status").get_data(as_text=True)
    assert 'data-state="pending"' in fragment, fragment
    assert 'data-poll="2"' in fragment, fragment

    # Every word the endpoint sends is already in the page it updates.
    words = " ".join(re.sub(r"(?s)<[^>]+>", " ", fragment).split())
    assert words, "the endpoint sent nothing"
    assert words in " ".join(re.sub(r"(?s)<[^>]+>", " ", page).split()), \
        f"the endpoint says something the page does not: {words}"


def a_finished_sync_stops_the_asking():
    clear_jobs()
    stored("finishes", "2026-01-01T00:00:00Z")
    client.get("/results/finishes")
    job = active_job_for("finishes")

    conn = db.connect()
    try:
        db.claim_job(conn, job["id"])
        db.finish_job(conn, job["id"])
    finally:
        conn.close()

    fragment = client.get(f"/progress/{job['id']}/status").get_data(as_text=True)
    assert "Fresh numbers are ready" in fragment, fragment
    assert 'data-poll="0"' in fragment, "the page would keep asking for ever"
    assert "/results/finishes" in fragment, "no way to see the fresh numbers"


def a_failed_sync_is_said_plainly():
    clear_jobs()
    stored("fails", "2026-01-01T00:00:00Z")
    client.get("/results/fails")
    job = active_job_for("fails")

    conn = db.connect()
    try:
        db.claim_job(conn, job["id"])
        db.finish_job(conn, job["id"], error="Codeforces did not answer.")
    finally:
        conn.close()

    fragment = client.get(f"/progress/{job['id']}/status").get_data(as_text=True)
    assert "did not finish" in fragment, fragment
    assert 'data-poll="0"' in fragment, "the page would keep asking for ever"


def a_job_that_no_longer_exists_is_404():
    """Then the script stops and leaves the words already on the page, rather
    than replacing them with a guess."""
    clear_jobs()
    response = client.get("/progress/999999/status")
    assert response.status_code == 404, response.status_code


def a_failed_job(handle, error="Codeforces rejected the request: no such user", finished_at=None):
    """A job that was tried and refused, as sync.py would leave it."""
    conn = db.connect()
    try:
        job_id = db.create_job(conn, "sync", handle)
        db.claim_job(conn, job_id)
        db.finish_job(conn, job_id, error=error)
        if finished_at is not None:
            with conn:
                conn.execute("UPDATE jobs SET finished_at = ? WHERE id = ?", (finished_at, job_id))
        return job_id
    finally:
        conn.close()


def a_handle_that_just_failed_is_answered_at_once():
    """One mistyped character used to cost two API requests and four seconds
    of everybody's queue, on every reload, for ever."""
    clear_jobs()
    a_failed_job("nosuchuser42qq")

    response = client.get("/results/nosuchuser42qq")
    html = response.get_data(as_text=True)

    assert response.status_code == 200, response.status_code
    assert "That did not work" in html, html[:300]
    assert "no such user" in html, "the reason was not shown"
    assert waiting() == [], f"asked Codeforces again anyway: {waiting()}"


def the_remembered_failure_offers_a_way_past_it():
    """Right about a handle that does not exist, wrong about a minute when
    Codeforces was down -- so the page carries a button that ignores it."""
    clear_jobs()
    a_failed_job("nosuchuser42qq")
    html = client.get("/results/nosuchuser42qq").get_data(as_text=True)
    assert "Try nosuchuser42qq again" in html, "no way past the remembered failure"

    response = client.post("/results/nosuchuser42qq/sync")
    assert response.status_code == 302, response.status_code
    assert waiting() == ["nosuchuser42qq"], waiting()


def an_older_failure_is_tried_again():
    clear_jobs()
    a_failed_job("gone_yesterday", finished_at=db.utc_ago(web.FAILURE_REMEMBERED_SECONDS + 60))

    response = client.get("/results/gone_yesterday")
    assert response.status_code == 302, "an old failure was still being believed"
    assert waiting() == ["gone_yesterday"], waiting()


def a_sync_in_flight_beats_a_remembered_failure():
    """After pressing the button: there is both a failure on the record and a
    job running. The page must follow the job, not the memory."""
    clear_jobs()
    a_failed_job("retried")
    sync.start_sync("retried")

    response = client.get("/results/retried")
    assert response.status_code == 302, "showed the old failure while a sync was running"
    assert "/progress/" in response.headers["Location"], response.headers["Location"]


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
check("stale results at once, re-synced behind", stale_results_are_shown_at_once_and_resynced_behind)
check("the line carries the queue without JavaScript", the_line_carries_the_queue_without_javascript)
check("fresh results start nothing, and offer the button", fresh_results_start_nothing_and_offer_the_button)
check("a running sync shows even on a fresh page", a_running_sync_is_shown_even_when_the_numbers_are_fresh)

print("\nthe button, for when the page counts as fresh")
check("the button starts a sync and comes back to the page", the_button_starts_a_sync_and_comes_back_to_the_page)
check("only a POST can start a sync", only_a_post_can_start_a_sync)
check("a junk handle cannot be queued", a_junk_handle_cannot_be_queued_by_the_button)
check("a sync already running is watched, not duplicated", a_sync_already_running_is_watched_not_duplicated)
check("nothing stored means waiting", a_visitor_with_nothing_stored_waits)

print("\na handle that failed")
check("answered at once, with no second request", a_handle_that_just_failed_is_answered_at_once)
check("and a way past it", the_remembered_failure_offers_a_way_past_it)
check("an older failure is tried again", an_older_failure_is_tried_again)
check("a sync in flight beats the memory", a_sync_in_flight_beats_a_remembered_failure)
check("two visitors, one handle, one job", two_visitors_asking_for_one_handle_share_a_job)

print("\nthe line, kept current")
check("the endpoint answers with the same line", the_status_endpoint_answers_with_the_same_line)
check("a finished sync stops the asking", a_finished_sync_stops_the_asking)
check("a failed sync is said plainly", a_failed_sync_is_said_plainly)
check("a job that no longer exists is 404", a_job_that_no_longer_exists_is_404)

print("\nthe worker")
check("oldest first, one at a time", the_worker_runs_them_oldest_first_and_one_at_a_time)
check("starting it twice starts one worker", starting_the_worker_twice_starts_one_worker)
check("a job that blows up does not kill it", a_job_that_blows_up_does_not_take_the_worker_with_it)
check("the entry points start it", the_entry_points_start_the_worker)

print(f"\n{passed} passed, {failed} failed")
shutil.rmtree(SCRATCH, ignore_errors=True)
sys.exit(1 if failed else 0)
