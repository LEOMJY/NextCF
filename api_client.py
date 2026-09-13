"""Codeforces API client.

Every request to Codeforces goes through call(), which does two things for
every caller so that no caller has to remember them:

    pacing     one request every two seconds, shared by all threads -- RateLimiter
    retrying   the failures that waiting can fix, and no others   -- call()

Usage:
    .venv\\Scripts\\python.exe api_client.py [handle]
"""

import json
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://codeforces.com/api"

# Codeforces asks for no more than one request every two seconds, and answers
# faster callers with "Call limit exceeded".
SECONDS_BETWEEN_REQUESTS = 2.0

# How many times one request is tried before giving up, and how long to wait
# after the first failure. The wait doubles: 2 seconds, then 4.
#
# Only failures that waiting can fix are retried -- see TemporaryFailure.
# Three attempts and six seconds of waiting rides out a blip, and is short
# enough that somebody watching a progress page has not given up.
MAX_ATTEMPTS = 3
RETRY_SECONDS = 2.0
RATING_WIDTH = 6


class RateLimiter:
    """Spaces out the moments requests start, across every thread in a program.

    Call wait() immediately before sending a request. It returns at once if
    the last request started long enough ago, and otherwise sleeps until it
    did.

    The idea is a queue of time slots. Each caller, under a lock, takes the
    next free slot -- "now", or one interval after the slot before it,
    whichever is later -- and moves the marker along. Then it lets go of the
    lock and sleeps until its slot. Two threads arriving at the same instant
    get slots two seconds apart, and neither holds the lock while sleeping, so
    a third thread can join the queue immediately instead of waiting to ask.

    What it does NOT cover: a second program. Each program that imports this
    file gets its own limiter, so collect.py and the local site running at
    the same moment each keep their own pace and together go twice as fast.
    Codeforces then answers "Call limit exceeded", which call() retries. Do not
    run the two together. See the 2026-09-13 devlog entry for why this is not
    shared between programs.
    """

    def __init__(self, interval, clock=time.monotonic, sleep=time.sleep):
        self.interval = interval

        # The clock and the sleep are parameters so the checks can hand in a
        # fake clock that moves only when something sleeps. The defaults are
        # the real thing.
        #
        # monotonic(), not time.time(): the wall clock can jump -- the computer
        # corrects its time from the internet, or daylight saving changes it --
        # and a clock that jumps backwards by an hour would make this wait an
        # hour. A monotonic clock only ever moves forward. Its value means
        # nothing on its own; only the difference between two readings does.
        self._clock = clock
        self._sleep = sleep

        # A thread lock: only one thread at a time may run the lines inside
        # `with self._lock`. Without it, two threads could both read the same
        # free slot before either moves the marker, and both send at once --
        # precisely the collision this class exists to prevent.
        self._lock = threading.Lock()

        # When the next free slot starts. Minus infinity means "no request
        # yet", so the very first caller never waits.
        self._next_slot = float("-inf")

    def wait(self):
        with self._lock:
            now = self._clock()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self.interval

        # Outside the lock, on purpose -- see the class docstring.
        delay = slot - now
        if delay > 0:
            self._sleep(delay)


# The one limiter for this program. Module-level on purpose: every thread that
# imports api_client shares it, which is what makes two simultaneous syncs in
# the web app take turns. The checks swap it out; nothing else should.
limiter = RateLimiter(SECONDS_BETWEEN_REQUESTS)


class TemporaryFailure(RuntimeError):
    """A failure that waiting might fix: Codeforces unwell, or asked too fast.

    Deliberately a subclass of RuntimeError, so callers that already catch
    RuntimeError -- web.py and sync.py both do -- keep working unchanged when
    one of these escapes after the last attempt.
    """


def call(method, **params):
    """Call one Codeforces API method and return its "result".

    Retries the failures that waiting can fix, and gives up at once on the
    ones it cannot. A handle that does not exist will still not exist in two
    seconds; a 503, or a complaint that we are asking too fast, very often
    will not be there any more.

    Raises RuntimeError if Codeforces answers and refuses the request.
    Raises urllib.error.URLError if the network itself keeps failing.

    Every method shares these failure modes, so they are handled once here
    rather than copied into each one.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _call_once(method, params)

        except (TemporaryFailure, urllib.error.URLError) as exc:
            # HTTPError is a subclass of URLError and would land here too --
            # but _call_once always converts it first, which is exactly why
            # this clause only ever sees a real network failure.
            if attempt == MAX_ATTEMPTS:
                raise

            # Wait longer each time. If Codeforces is busy, or is telling us
            # to slow down, asking again immediately is part of the problem.
            wait = RETRY_SECONDS * 2 ** (attempt - 1)
            print(
                f"{method}: {exc} -- retrying in {wait:.0f}s"
                f" (attempt {attempt + 1} of {MAX_ATTEMPTS})",
                file=sys.stderr,
            )
            time.sleep(wait)


def _call_once(method, params):
    """One attempt at one API call. The retrying lives in call()."""

    # Wait for a turn. Here, in the single attempt, rather than once in call():
    # a retry is a request too, and a retry after "Call limit exceeded" is the
    # last request that should be allowed to jump the queue. When the retry has
    # already slept 2 or 4 seconds, its turn has usually arrived and this
    # returns at once.
    limiter.wait()

    # urlencode escapes anything awkward in a value. A handle containing a
    # space or an "&" would otherwise corrupt the query string silently --
    # the request would succeed and return the wrong user's data.
    query = urllib.parse.urlencode(params)
    url = f"{API_BASE}/{method}?{query}"

    # The timeout is not optional. Without it a hung connection blocks forever,
    # and at v0.3 this same call runs ~2000 times unattended overnight.
    status_code = None
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            # .read() gives raw bytes; json.loads turns them into ordinary Python
            # dicts and lists. After this line there is no JSON left, just containers.
            payload = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        # Codeforces reports a bad handle as HTTP 400, and urlopen raises on
        # any 4xx/5xx. But the useful explanation is in the *body* of that
        # error response, e.g.
        #     {"status":"FAILED","comment":"handle: User ... not found"}
        # HTTPError is itself readable like a response, so the message is one
        # .read() away. Skip this and all you ever see is "Bad Request".
        status_code = exc.code
        try:
            payload = json.loads(exc.read())
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Not JSON at all -- Codeforces down, or a proxy or error page in
            # the way. Nothing useful to extract, so report the status code.
            message = f"HTTP {exc.code} from Codeforces: {exc.reason}"
            if exc.code >= 500:
                # 5xx means the far end is broken, not the request. Worth
                # asking again.
                raise TemporaryFailure(message) from exc
            raise RuntimeError(message) from exc

    # The real outcome lives in this field, and it is checked on every call.
    # When it says FAILED there is no "result" key at all, so reading
    # payload["result"] below would raise KeyError instead of telling you what
    # was actually wrong with the request.
    if payload["status"] != "OK":
        comment = payload.get("comment", "Codeforces returned FAILED")

        # Two kinds of no, needing opposite responses. Asking too fast is our
        # fault and waiting fixes it; a 5xx is theirs and waiting usually
        # fixes it too. A handle that does not exist is neither, and retrying
        # it only makes a visitor wait six seconds for the same answer.
        if (status_code is not None and status_code >= 500) or "limit exceeded" in comment.lower():
            raise TemporaryFailure(comment)

        raise RuntimeError(comment)

    return payload["result"]


def fetch_submissions(handle, count=None):
    """`handle`'s submissions, newest first: all of them, or the newest `count`.

    With no count, Codeforces sends the whole history in one response. That
    is what sync.py and collect.py want: every request waits for a two-second
    turn, so one request for 11,148 submissions (6.3 MB, 2.6 s, measured
    2026-09-13) beats twelve pages of 1000 by twenty-odd seconds.

    The timeout in _call_once does not cap how long a big download may take.
    It is how long to wait for the NEXT piece of data, so a response that keeps
    arriving never times out, however large.
    """
    if count is None:
        return call("user.status", handle=handle)
    return call("user.status", handle=handle, count=count)


def fetch_user(handle):
    """One user's profile: the canonical spelling of the handle, and a rating.

    Two things sync.py needs and user.status does not give. Codeforces handles
    are case-insensitive, so a visitor typing "TOURIST" must still be stored
    under the spelling the API returns -- otherwise the same person can end up
    displayed three different ways.

    "rating" is absent for anyone who has never competed, so read it with
    .get(), never with [].
    """
    # user.info takes "handles", plural, and answers with a list in the same
    # order. One handle in, one user out.
    return call("user.info", handles=handle)[0]


def format_submission(sub):
    """Render one submission as a single printable line."""
    problem = sub["problem"]

    # Both of these fields are genuinely absent sometimes, and indexing with
    # [] would raise KeyError and kill the run partway through:
    #   rating  -- unrated, brand new, or gym problems have none (spec section 6)
    #   verdict -- absent while a submission is still being judged
    # .get() returns None (or the fallback) instead of raising.
    rating = problem.get("rating")
    verdict = sub.get("verdict", "TESTING")

    rating_text = str(rating) if rating is not None else "?"

    # f-string alignment: >N right-aligns in N columns, <22 left-aligns in 22.
    return f"{rating_text:>{RATING_WIDTH}}  {verdict:<22}  {problem['name']}"


def main():
    # sys.argv is the command line, split on spaces. argv[0] is the script
    # name itself, so a supplied handle is argv[1].
    handle = sys.argv[1] if len(sys.argv) > 1 else "tourist"

    try:
        # The newest 100 only: this prints a table, and 8,000 rows is not one.
        submissions = fetch_submissions(handle, count=100)
    except urllib.error.URLError as exc:
        # Network-level failure: no DNS, no route, timed out, TLS refused.
        print(f"could not reach Codeforces: {exc.reason}")
        return 1
    except RuntimeError as exc:
        # Codeforces answered, and said no. Almost always a handle that does
        # not exist. This is the case spec section 7.1 calls the loudest
        # amateur tell if it reaches the user as a traceback.
        print(f"Codeforces rejected the request: {exc}")
        return 1

    print(f"{handle}: {len(submissions)} submissions\n")
    print(f"{'RATING':>{RATING_WIDTH}}  {'VERDICT':<22}  PROBLEM")
    for sub in submissions:
        print(format_submission(sub))

    return 0


# This block runs only when the file is executed directly. When sync.py later
# does `from api_client import fetch_submissions`, Python runs the whole file
# to define its functions -- without this guard, importing it would also print
# tourist's submissions as a side effect.
if __name__ == "__main__":
    sys.exit(main())
