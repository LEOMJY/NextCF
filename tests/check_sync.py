"""Check of sync.run_sync, the website's sync job, with no network.

A fake Codeforces answers api_client.call from data built here and records
every request, and the job writes into a temporary database (NEXTCF_DB), so
the whole job -- including the ways it is meant to fail -- runs in a second.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="sync-"))

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


class FakeCodeforces:
    """Answers api_client.call for one user, spelled `spelling` by Codeforces.
    `ratings` are their rating changes' newRating values, oldest first;
    `team_first` puts a team submission, somebody else listed first, at the
    top of their history."""

    def __init__(self, spelling="Tourist", ratings=(1350, 1620), exists=True, team_first=False,
                 submissions=True):
        self.spelling, self.ratings, self.exists, self.team_first = spelling, ratings, exists, team_first
        self.submissions = submissions
        self.requests = []

    def __call__(self, method, **params):
        self.requests.append(method)
        if not self.exists:
            raise RuntimeError(f"handle: User with handle {params.get('handle')} not found")
        if method == "user.status" and not self.submissions:
            return []
        if method == "user.status":
            problem = {"contestId": 1, "index": "A", "name": "Watermelon", "rating": 800, "tags": ["math"]}
            subs = [{"id": 10 + n, "creationTimeSeconds": 1600000000 + n, "verdict": "OK",
                     "author": {"participantType": "PRACTICE", "members": [{"handle": self.spelling}]},
                     "problem": problem} for n in range(3)]
            if self.team_first:
                subs.insert(0, {"id": 99, "creationTimeSeconds": 1600000100, "verdict": "OK",
                                "author": {"participantType": "CONTESTANT",
                                           "members": [{"handle": "teammate"}, {"handle": self.spelling}]},
                                "problem": problem})
            return subs
        if method == "user.rating":
            out, old = [], 0
            for n, new in enumerate(self.ratings):
                out.append({"contestId": 100 + n, "contestName": "Round", "handle": self.spelling,
                            "rank": 50, "ratingUpdateTimeSeconds": 1590000000 + n * 86400,
                            "oldRating": old, "newRating": new})
                old = new
            return out
        raise AssertionError(f"the sync asked Codeforces for {method}, which it should not need")


def synced(fake, typed):
    """Run one real sync job for `typed` against `fake`; return (job, user row)."""
    db.init_db()
    real = api_client.call
    api_client.call = fake
    conn = db.connect()
    try:
        job_id = db.create_job(conn, "sync", typed)
        sync.run_sync(typed, job_id)
        return db.get_job(conn, job_id), db.get_user(conn, typed)
    finally:
        conn.close()
        api_client.call = real


print("sync.py")


def two_requests():
    fake = FakeCodeforces()
    job, _ = synced(fake, "two_requests_user")
    assert job["error"] is None, job["error"]
    assert fake.requests == ["user.status", "user.rating"], f"the sync made {fake.requests}"


check("a sync makes two requests -- the history and the rating changes -- and no user.info", two_requests)


def spelling_and_rating_from_rating_changes():
    # No submissions at all: only the rating changes can spell the handle.
    fake = FakeCodeforces(spelling="MiXeD_Case", ratings=(1350, 1620, 1587), submissions=False)
    job, user = synced(fake, "mixed_case")
    assert job["error"] is None, job["error"]
    assert user is not None, "nothing stored"
    assert user["handle"] == "MiXeD_Case", f"stored as {user['handle']!r}, not as Codeforces spells it"
    assert user["cf_rating"] == 1587, f"current rating {user['cf_rating']}, not the newest change's 1587"


check("the handle is stored as Codeforces spells it and the rating is the newest change's", spelling_and_rating_from_rating_changes)


def unrated_spelling_from_a_solo_submission():
    fake = FakeCodeforces(spelling="NoContests", ratings=(), team_first=True)
    job, user = synced(fake, "NOCONTESTS")
    assert job["error"] is None, job["error"]
    assert user["handle"] == "NoContests", \
        f"stored as {user['handle']!r}: the spelling must come from a solo submission, not a team's first member"
    assert user["cf_rating"] is None, f"an unrated user stored with rating {user['cf_rating']}"


check("with no rating changes, the spelling comes from a solo submission, never a teammate; the rating stays empty", unrated_spelling_from_a_solo_submission)


def unknown_handle_fails_and_writes_nothing():
    fake = FakeCodeforces(exists=False)
    job, user = synced(fake, "nobody_by_this_name")
    assert job["state"] == "failed", f"job state {job['state']!r}"
    assert "not found" in (job["error"] or ""), f"the job's error does not carry Codeforces' reason: {job['error']!r}"
    assert user is None, "a user row was written for a handle that does not exist"
    assert fake.requests == ["user.status"], f"it carried on after the refusal: {fake.requests}"


check("a handle Codeforces does not know fails the job with the reason, after one request, writing nothing", unknown_handle_fails_and_writes_nothing)


shutil.rmtree(SCRATCH, ignore_errors=True)
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
