"""Check that api_client retries the right failures and no others.

No network: urlopen is replaced with a fake that answers from a script of
prepared responses, and sleep is replaced with a counter, so the whole thing
runs instantly instead of waiting six seconds per case.
"""

import io
import json
import os
import sys
import urllib.error
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


class FakeResponse:
    """What urlopen returns on a good call."""

    def __init__(self, payload):
        self._data = json.dumps(payload).encode()

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class StallingResponse:
    """A response whose headers arrived and whose body did not.

    Measured on this machine: when a server stops sending halfway through a
    body, urlopen's read() raises TimeoutError -- not URLError -- and a server
    that closes early raises http.client.IncompleteRead.
    """

    def __init__(self, exc):
        self.exc = exc

    def read(self):
        raise self.exc

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


def http_error(code, payload=None, body=b"<html>a proxy error page</html>"):
    """What urlopen raises on a 4xx or 5xx."""
    if payload is not None:
        body = json.dumps(payload).encode()
    return urllib.error.HTTPError("http://x", code, "the reason", {}, io.BytesIO(body))


class Script:
    """Answers each call with the next item: an exception raises, anything
    else is returned as a response."""

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = 0

    def __call__(self, url, timeout=None):
        self.calls += 1
        answer = self.answers.pop(0) if self.answers else self.answers_exhausted()
        if isinstance(answer, Exception):
            raise answer
        if isinstance(answer, StallingResponse):
            return answer
        return FakeResponse(answer)

    def answers_exhausted(self):
        raise AssertionError("api_client made more calls than the script had answers")


def run(*answers):
    """Point api_client at a scripted urlopen, and count the waits.

    The rate limiter is given the same fake clock as the retry waits, so a
    retry's sleep moves time forward for the limiter too -- the way real time
    would. Any extra wait the limiter added would show up in `waits`.
    """
    script = Script(*answers)
    waits = []
    clock = [0.0]

    def fake_sleep(seconds):
        waits.append(seconds)
        clock[0] += seconds

    real_urlopen = api_client.urllib.request.urlopen
    real_sleep = api_client.time.sleep
    real_limiter = api_client.limiter
    api_client.urllib.request.urlopen = script
    api_client.time.sleep = fake_sleep
    api_client.limiter = api_client.RateLimiter(
        api_client.SECONDS_BETWEEN_REQUESTS, clock=lambda: clock[0], sleep=fake_sleep
    )
    try:
        result = error = None
        try:
            result = api_client.call("user.info", handles="tourist")
        except Exception as exc:
            error = exc
        return script.calls, waits, result, error
    finally:
        api_client.urllib.request.urlopen = real_urlopen
        api_client.time.sleep = real_sleep
        api_client.limiter = real_limiter


OK = {"status": "OK", "result": [{"handle": "tourist"}]}
NOT_FOUND = {"status": "FAILED", "comment": "handle: User with handle nosuch not found"}
LIMIT = {"status": "FAILED", "comment": "Call limit exceeded"}

print("api_client retries")


def first_try_succeeds():
    calls, waits, result, error = run(OK)
    assert error is None, error
    assert calls == 1 and waits == [], f"{calls} calls, waits {waits}"
    assert result == [{"handle": "tourist"}]


check("a call that works is made exactly once, with no waiting", first_try_succeeds)


def retries_a_503():
    calls, waits, result, error = run(http_error(503), http_error(503), OK)
    assert error is None, f"gave up on a 503 that would have worked: {error}"
    assert calls == 3, f"{calls} calls"
    assert waits == [2.0, 4.0], f"waits were {waits}"


check("two 503s then success: 3 calls, waiting 2s then 4s", retries_a_503)


def retries_a_network_failure():
    calls, waits, result, error = run(urllib.error.URLError("connection reset"), OK)
    assert error is None, error
    assert calls == 2 and waits == [2.0], f"{calls} calls, waits {waits}"


check("a dropped connection is retried", retries_a_network_failure)


def retries_a_call_limit():
    calls, waits, result, error = run(http_error(403, LIMIT), OK)
    assert error is None, f'"Call limit exceeded" was treated as permanent: {error}'
    assert calls == 2, f"{calls} calls"


check('"Call limit exceeded" is retried even though it arrives as a 4xx', retries_a_call_limit)


def never_retries_a_bad_handle():
    calls, waits, result, error = run(http_error(400, NOT_FOUND))
    assert isinstance(error, RuntimeError), f"expected RuntimeError, got {error!r}"
    assert not isinstance(error, api_client.TemporaryFailure), "a bad handle was called temporary"
    assert calls == 1, f"a handle that does not exist was asked for {calls} times"
    assert waits == [], f"waited {waits} for an answer that will never change"
    assert "not found" in str(error), str(error)


check("a handle that does not exist fails once, immediately, with the reason", never_retries_a_bad_handle)


def gives_up_after_three():
    calls, waits, result, error = run(http_error(503), http_error(503), http_error(503))
    assert isinstance(error, api_client.TemporaryFailure), f"got {error!r}"
    assert isinstance(error, RuntimeError), "TemporaryFailure must still be a RuntimeError"
    assert calls == api_client.MAX_ATTEMPTS, f"{calls} calls"
    assert waits == [2.0, 4.0], f"waits were {waits}"


check("three 503s: gives up, and the error is still a RuntimeError for callers", gives_up_after_three)


def non_json_5xx_is_temporary():
    calls, waits, result, error = run(http_error(502), OK)
    assert error is None, f"a 502 with an HTML body was not retried: {error}"
    assert calls == 2, f"{calls} calls"


check("a 5xx whose body is not JSON is still retried", non_json_5xx_is_temporary)


def stalled_download_is_retried():
    import http.client

    calls, waits, result, error = run(
        StallingResponse(TimeoutError("timed out")),
        StallingResponse(http.client.IncompleteRead(b"{", 1000)),
        OK,
    )
    assert error is None, f"a download that stalled halfway was not retried: {error!r}"
    assert calls == 3 and waits == [2.0, 4.0], f"{calls} calls, waits {waits}"


check("a download that stalls or is cut off halfway is retried, like a dropped connection", stalled_download_is_retried)


def three_stalls_read_as_network_failure():
    stall = lambda: StallingResponse(TimeoutError("timed out"))  # noqa: E731
    calls, waits, result, error = run(stall(), stall(), stall())
    # URLError is what sync.py turns into "Could not reach Codeforces". A bare
    # TimeoutError would fall through to "Something went wrong on our side".
    assert isinstance(error, urllib.error.URLError), f"got {error!r}"
    assert calls == 3, f"{calls} calls"


check("...and three stalls in a row give up as a network failure (URLError)", three_stalls_read_as_network_failure)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
