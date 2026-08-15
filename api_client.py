"""Codeforces API client.

v0.1 scope: fetch one user's recent submissions and print them.
Rate limiting, retries and backoff are v0.3 work — see docs/spec.md section 4.

Usage:
    .venv\\Scripts\\python.exe api_client.py [handle]
"""

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://codeforces.com/api"
RATING_WIDTH = 6


def fetch_submissions(handle, count=100):
    """Return a list of submission dicts for `handle`, newest first.

    Raises RuntimeError if Codeforces answers but refuses the request.
    Raises urllib.error.URLError if the network itself fails.
    """

    # urlencode escapes anything awkward in the handle. A handle containing a
    # space or an "&" would otherwise corrupt the query string silently --
    # the request would succeed and return the wrong user's data.
    query = urllib.parse.urlencode({"handle": handle, "from": 1, "count": count})
    url = f"{API_BASE}/user.status?{query}"

    # The timeout is not optional. Without it a hung connection blocks forever,
    # and at v0.3 this same call runs ~2000 times unattended overnight.
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
        try:
            payload = json.loads(exc.read())
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Not JSON at all -- Codeforces down, or a proxy/error page in the
            # way. Nothing useful to extract, so report the status code.
            raise RuntimeError(f"HTTP {exc.code} from Codeforces: {exc.reason}") from exc

    # The real outcome lives in this field, and it is checked on every call.
    # When it says FAILED there is no "result" key at all, so reading
    # payload["result"] below would raise KeyError instead of telling you what
    # was actually wrong with the request.
    if payload["status"] != "OK":
        raise RuntimeError(payload.get("comment", "Codeforces returned FAILED"))

    return payload["result"]


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

    # f-string alignment: >5 right-aligns in 5 columns, <22 left-aligns in 22.
    return f"{rating_text:>{RATING_WIDTH}}  {verdict:<22}  {problem['name']}"


def main():
    # sys.argv is the command line, split on spaces. argv[0] is the script
    # name itself, so a supplied handle is argv[1].
    handle = sys.argv[1] if len(sys.argv) > 1 else "tourist"

    try:
        submissions = fetch_submissions(handle)
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
