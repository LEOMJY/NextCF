"""Check that api_client spaces its requests out, across threads.

Mostly no real waiting: the limiter is given a fake clock whose sleep moves
time forward instantly. The one check about threads uses the real clock with
a short interval, because a fake clock cannot show threads colliding.
"""

import os
import sys
import threading
import time
from pathlib import Path

# Paths in this file are relative to the repository root, and the modules
# being checked live there, so go there first. The check then runs the same
# from any directory.
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
import api_client  # noqa: E402

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


class FakeClock:
    """A clock that only moves when something sleeps."""

    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(round(seconds, 6))
        self.now += seconds


print("api_client rate limit")


def interval_matches_codeforces():
    assert api_client.SECONDS_BETWEEN_REQUESTS == 2.0, api_client.SECONDS_BETWEEN_REQUESTS
    assert api_client.limiter.interval == api_client.SECONDS_BETWEEN_REQUESTS


check("the shared limiter allows one request every two seconds", interval_matches_codeforces)


def back_to_back_waits():
    clock = FakeClock()
    limiter = api_client.RateLimiter(2.0, clock=clock.monotonic, sleep=clock.sleep)
    limiter.wait()
    limiter.wait()
    limiter.wait()
    assert clock.sleeps == [2.0, 2.0], f"sleeps were {clock.sleeps}"


check("three requests back to back: the first goes at once, then 2s, then 2s", back_to_back_waits)


def slow_request_owes_nothing():
    clock = FakeClock()
    limiter = api_client.RateLimiter(2.0, clock=clock.monotonic, sleep=clock.sleep)
    limiter.wait()
    clock.now += 1.5  # the request itself took 1.5s
    limiter.wait()
    clock.now += 5.0  # and this one took 5s
    limiter.wait()
    assert clock.sleeps == [0.5], f"sleeps were {clock.sleeps}"


check("time spent inside a request counts toward the gap", slow_request_owes_nothing)


def start_times(n, wait):
    """n threads, released at the same instant; when each got to go."""
    barrier = threading.Barrier(n)
    starts = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        wait()
        with lock:
            starts.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    starts.sort()
    return [b - a for a, b in zip(starts, starts[1:])]


def threads_take_turns():
    # Two visitors syncing at once is two threads in one web app. Released
    # together, they must still go one interval apart.
    limiter = api_client.RateLimiter(0.2)
    gaps = start_times(4, limiter.wait)
    assert min(gaps) >= 0.18, f"gaps between threads were {[round(g, 3) for g in gaps]}"


check("four threads calling at the same instant go 0.2s apart, not together", threads_take_turns)


def threads_collide_without_it():
    # The counterfactual: the same four threads with no limiter. If this did
    # not show them bunched together, the check above would prove nothing.
    gaps = start_times(4, lambda: None)
    assert max(gaps) < 0.05, f"expected a pile-up, gaps were {[round(g, 3) for g in gaps]}"


check("...while the same four threads with no limiter go within 0.05s of each other", threads_collide_without_it)


def the_lock_is_doing_the_work():
    # The thread check above does NOT prove the lock is needed. Under the GIL
    # the gap between reading the free slot and moving the marker is a couple
    # of bytecodes, and with the lock deleted that check still passed in 20
    # runs out of 20. So the claim is tested the way the other checks test
    # theirs: a copy of wait() with the lock removed, and a forced thread
    # switch inside that gap. Two threads then take the same slot. On a
    # free-threaded Python -- which the Windows launcher picks by default,
    # spec section 7 -- no forcing is needed.
    class NoLockWideGap(api_client.RateLimiter):
        def wait(self):
            now = self._clock()
            slot = max(now, self._next_slot)
            time.sleep(0.001)
            self._next_slot = slot + self.interval
            if slot - now > 0:
                self._sleep(slot - now)

    class LockWideGap(api_client.RateLimiter):
        def wait(self):
            with self._lock:
                now = self._clock()
                slot = max(now, self._next_slot)
                time.sleep(0.001)
                self._next_slot = slot + self.interval
            if slot - now > 0:
                self._sleep(slot - now)

    unlocked = min(min(start_times(8, NoLockWideGap(0.05).wait)) for _ in range(3))
    locked = min(min(start_times(8, LockWideGap(0.05).wait)) for _ in range(3))
    assert unlocked < 0.01, f"without the lock the closest two threads were still {unlocked:.3f}s apart"
    assert locked >= 0.045, f"with the lock, the same wide gap let two threads {locked:.3f}s apart"


check("with the read-then-write gap forced open, no lock hands two threads one slot; the lock does not", the_lock_is_doing_the_work)


def every_attempt_waits_its_turn():
    # The limiter has to sit inside the retry loop, not around it. A retry
    # after "Call limit exceeded" is exactly the request that must not jump
    # the queue.
    consulted = []

    class CountingLimiter:
        interval = 2.0

        def wait(self):
            consulted.append(True)

    answers = [
        {"status": "FAILED", "comment": "Call limit exceeded"},
        {"status": "OK", "result": [{"handle": "tourist"}]},
    ]
    requests = []

    class Response:
        def __init__(self, payload):
            import json
            self.data = json.dumps(payload).encode()

        def read(self):
            return self.data

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(url, timeout=None):
        requests.append(url)
        return Response(answers.pop(0))

    real = (api_client.limiter, api_client.urllib.request.urlopen, api_client.time.sleep)
    api_client.limiter = CountingLimiter()
    api_client.urllib.request.urlopen = fake_urlopen
    api_client.time.sleep = lambda s: None
    try:
        api_client.call("user.info", handles="tourist")
    finally:
        api_client.limiter, api_client.urllib.request.urlopen, api_client.time.sleep = real

    assert len(requests) == 2, f"{len(requests)} requests"
    assert len(consulted) == 2, f"2 requests were sent but the limiter was consulted {len(consulted)} times"


check("a retry asks the limiter too: 2 requests, 2 turns", every_attempt_waits_its_turn)


def sync_asks_once_for_the_whole_history():
    # One request per history, however long. Paging 1000 at a time cost one
    # extra two-second slot per page once every request waits its turn: 13
    # requests for jiangly instead of 2. And pacing lives in one place, so
    # sync.py must not sleep on its own either.
    import sync

    calls, progress, sleeps = [], [], []
    real = (sync.api_client.fetch_submissions, sync.db.set_job_progress, sync.time.sleep)

    def fake_fetch(handle, **kwargs):
        calls.append(kwargs)
        return [{}] * 2500

    sync.api_client.fetch_submissions = fake_fetch
    sync.db.set_job_progress = lambda conn, job_id, n: progress.append(n)
    sync.time.sleep = sleeps.append
    try:
        got = sync.fetch_history("tourist", job_id=1, conn=None)
    finally:
        sync.api_client.fetch_submissions, sync.db.set_job_progress, sync.time.sleep = real

    assert len(calls) == 1, f"{len(calls)} requests for one history"
    assert calls[0].get("count") is None, f"asked for a page instead of everything: {calls[0]}"
    assert len(got) == 2500, f"{len(got)} submissions returned"
    assert progress == [2500], f"progress written as {progress}"
    assert sleeps == [], f"sync.py slept {sleeps} on top of the limiter"


check("sync.py asks once for the whole history: one request, no paging, no sleep", sync_asks_once_for_the_whole_history)


def whole_history_url_has_no_paging():
    urls = []

    class Response:
        def read(self):
            return b'{"status": "OK", "result": []}'

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_urlopen(url, timeout=None):
        urls.append(url)
        return Response()

    real = (api_client.limiter, api_client.urllib.request.urlopen)
    api_client.limiter = api_client.RateLimiter(0)
    api_client.urllib.request.urlopen = fake_urlopen
    try:
        api_client.fetch_submissions("tourist")
        api_client.fetch_submissions("tourist", count=100)
    finally:
        api_client.limiter, api_client.urllib.request.urlopen = real

    assert "count=" not in urls[0] and "from=" not in urls[0], f"whole history asked for with paging: {urls[0]}"
    assert "count=100" in urls[1], f"a count of 100 was not sent: {urls[1]}"


check("fetch_submissions() with no count asks for everything; with a count, sends it", whole_history_url_has_no_paging)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
