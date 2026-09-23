"""Check of collect.py and the dataset tables, with no network.

A fake Codeforces answers every request from data built here, and each check
gets a fresh temporary database, so the whole collection -- including the ways
it is meant to stop and resume -- runs in a few seconds.

Every claim is tested by making the failure happen: a handle that has vanished,
the network going down halfway, a run stopped and started again.
"""

import contextlib
import io
import os
import shutil
import sqlite3
import sys
import tempfile
import urllib.error
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="collect-"))
# Paths in this file are relative to the repository root, and the modules
# being checked live there, so go there first. The check then runs the same
# from any directory.
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import api_client  # noqa: E402
import collect  # noqa: E402
import db  # noqa: E402

passed = failed = 0
_counter = 0


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


def fresh_path():
    global _counter
    _counter += 1
    return SCRATCH / f"dataset{_counter}.db"


# ------------------------------------------------------------ a fake Codeforces

def rated_list(per_band=10):
    """What user.ratedList returns: users spread from 800 to 2299, plus the
    exact edges of every stratum, which is where an off-by-one would hide."""
    users = []
    for band in range(800, 2300, 100):
        for i in range(per_band // 2):
            users.append({"handle": f"u{band}_{i}", "rating": band + 37})
    for edge in (999, 1000, 1199, 1200, 1999, 2000):
        users.append({"handle": f"edge{edge}", "rating": edge})
    return users


PROBLEMSET = {
    "problems": [
        {"contestId": 1, "index": "A", "name": "Watermelon", "rating": 800, "tags": ["math"]},
        {"contestId": 2, "index": "B", "name": "Nobody in the sample tried this", "rating": 2400,
         "tags": ["dp", "graphs"]},
    ],
    "problemStatistics": [],
}


class FakeCodeforces:
    """Answers the three calls collect.py makes. `missing` handles do not exist;
    after `down_after` history requests the network goes down for good."""

    def __init__(self, missing=(), down_after=None, refuse_after=None):
        self.missing = {h.lower() for h in missing}
        self.down_after = down_after
        self.refuse_after = refuse_after
        self.history_requests = []

    def fetch_submissions(self, handle, count=None):
        if self.down_after is not None and len(self.history_requests) >= self.down_after:
            raise urllib.error.URLError("network is down")
        if self.refuse_after is not None and len(self.history_requests) >= self.refuse_after:
            # What api_client raises for a 4xx that is not JSON: a proxy page,
            # or Codeforces blocking us. Permanent-looking, and not about the handle.
            raise RuntimeError("HTTP 403 from Codeforces: Forbidden")
        self.history_requests.append(handle)
        if handle.lower() in self.missing:
            raise RuntimeError(f"handle: User with handle {handle} not found")
        return [
            {"id": abs(hash((handle, n))) % 10**9, "creationTimeSeconds": 1600000000 + n,
             "verdict": "OK", "author": {"participantType": "PRACTICE"},
             "problem": {"contestId": 1, "index": "A", "name": "Watermelon", "rating": 800, "tags": ["math"]}}
            for n in range(3)
        ]

    def fetch_rating_changes(self, handle):
        return [
            {"contestId": 1, "rank": 900, "ratingUpdateTimeSeconds": 1590000000, "oldRating": 0, "newRating": 400},
            {"contestId": 2, "rank": 500, "ratingUpdateTimeSeconds": 1595000000, "oldRating": 400, "newRating": 1100},
        ]

    def fetch_problemset(self):
        return PROBLEMSET


@contextlib.contextmanager
def codeforces(fake):
    real = (api_client.fetch_submissions, api_client.fetch_rating_changes, api_client.fetch_problemset)
    api_client.fetch_submissions = fake.fetch_submissions
    api_client.fetch_rating_changes = fake.fetch_rating_changes
    api_client.fetch_problemset = fake.fetch_problemset
    try:
        yield fake
    finally:
        api_client.fetch_submissions, api_client.fetch_rating_changes, api_client.fetch_problemset = real


def quietly(fn, *args, **kwargs):
    """Run fn without its progress lines cluttering this report."""
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return fn(*args, **kwargs)


def drawn(path, per_stratum=3, seed=7, users=None):
    quietly(collect.draw, path, users if users is not None else rated_list(), seed, per_stratum)


def rows(path, sql, params=()):
    conn = db.connect(path)
    try:
        return [tuple(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def collected_by_stratum(path):
    return dict(rows(path, """
        SELECT c.stratum, count(*)
          FROM sample_candidates c
          JOIN users u ON u.handle = c.handle AND u.last_synced IS NOT NULL
         GROUP BY c.stratum
    """))


print("collect.py")


# ----------------------------------------------------------------------- draw

def every_in_range_user_in_one_stratum():
    path = fresh_path()
    users = rated_list()
    drawn(path, users=users)
    got = dict(rows(path, "SELECT handle, stratum FROM sample_candidates"))
    expected = {u["handle"] for u in users if 1000 <= u["rating"] <= 1999}
    assert set(got) == expected, f"candidates differ from the users rated 1000-1999: {set(got) ^ expected}"
    for handle, want in (("edge1000", 1000), ("edge1199", 1000), ("edge1200", 1200), ("edge1999", 1800)):
        assert got[handle] == want, f"{handle} landed in stratum {got[handle]}, expected {want}"
    for stratum, n, lo, hi in rows(path, "SELECT stratum, count(*), min(position), max(position) "
                                         "FROM sample_candidates GROUP BY stratum"):
        assert (lo, hi) == (0, n - 1), f"stratum {stratum}: positions run {lo}..{hi} for {n} candidates"
    assert sorted(collect.STRATA) == [1000, 1200, 1400, 1600, 1800], collect.STRATA


check("the draw puts every user rated 1000-1999 in exactly one stratum; 999 and 2000 in none", every_in_range_user_in_one_stratum)


def draw_is_reproducible():
    users = rated_list()
    a, b, c = fresh_path(), fresh_path(), fresh_path()
    drawn(a, seed=7, users=users)
    drawn(b, seed=7, users=list(reversed(users)))  # the API may list users in another order
    drawn(c, seed=8, users=users)
    order = "SELECT stratum, position, handle FROM sample_candidates ORDER BY stratum, position"
    assert rows(a, order) == rows(b, order), "the same seed gave a different order"
    assert rows(a, order) != rows(c, order), "a different seed gave the same order"


check("the same seed draws the same order even if the API lists users differently; another seed does not", draw_is_reproducible)


def second_draw_is_refused():
    path = fresh_path()
    drawn(path, seed=7)
    before = rows(path, "SELECT handle FROM sample_candidates ORDER BY stratum, position")
    try:
        drawn(path, seed=8)
    except collect.SampleExists:
        pass
    else:
        raise AssertionError("a second draw was allowed, which would change who is in the dataset")
    assert rows(path, "SELECT handle FROM sample_candidates ORDER BY stratum, position") == before


check("a second draw into the same dataset is refused and changes nothing", second_draw_is_refused)


def draw_records_how_it_was_made():
    path = fresh_path()
    drawn(path, per_stratum=3, seed=7)
    (seed, rmin, rmax, width, per, source, when), = rows(
        path, "SELECT seed, rating_min, rating_max, stratum_width, per_stratum, source, source_fetched_at FROM samples")
    assert (seed, rmin, rmax, width, per) == (7, 1000, 1999, 200, 3), (seed, rmin, rmax, width, per)
    assert "ratedList" in source and when.endswith("Z"), (source, when)
    populations = dict(rows(path, "SELECT stratum, population FROM sample_strata"))
    expected = {s: sum(1 for u in rated_list() if s <= u["rating"] <= s + 199) for s in collect.STRATA}
    assert populations == expected, f"populations {populations}, expected {expected}"


check("the draw records seed, bounds, source and each stratum's population, for weighting", draw_records_how_it_was_made)


# ------------------------------------------------------------------------ run

def run_fills_each_stratum_in_order():
    path = fresh_path()
    drawn(path, per_stratum=3)
    with codeforces(FakeCodeforces()):
        code = quietly(collect.run, path)
    assert code == 0, f"run exited {code}"
    assert collected_by_stratum(path) == {s: 3 for s in collect.STRATA}, collected_by_stratum(path)
    firsts = rows(path, """
        SELECT count(*) FROM sample_candidates c
          JOIN users u ON u.handle = c.handle AND u.last_synced IS NOT NULL
         WHERE c.position >= 3""")
    assert firsts == [(0,)], "someone past position 2 was collected while earlier candidates were fine"
    assert rows(path, "SELECT count(*) FROM rating_changes") == [(15 * 2,)], rows(path, "SELECT count(*) FROM rating_changes")
    assert rows(path, "SELECT name FROM problems WHERE id = '2B'") == [("Nobody in the sample tried this",)]
    assert rows(path, "SELECT count(*) FROM problem_tags WHERE problem_id = '2B'") == [(2,)]


check("run collects exactly per_stratum users from every stratum, first positions first, with rating changes and the problemset", run_fills_each_stratum_in_order)


def unavailable_is_recorded_and_replaced():
    path = fresh_path()
    drawn(path, per_stratum=3)
    (gone,), = rows(path, "SELECT handle FROM sample_candidates WHERE stratum = 1400 AND position = 1")
    with codeforces(FakeCodeforces(missing=[gone])):
        code = quietly(collect.run, path)
    assert code == 0, f"run exited {code}"
    (note,), = rows(path, "SELECT unavailable FROM sample_candidates WHERE handle = ?", (gone,))
    assert note and "not found" in note, f"the vanished handle was recorded as {note!r}"
    got = [p for (p,) in rows(path, """
        SELECT c.position FROM sample_candidates c
          JOIN users u ON u.handle = c.handle AND u.last_synced IS NOT NULL
         WHERE c.stratum = 1400 ORDER BY c.position""")]
    assert got == [0, 2, 3], f"stratum 1400 collected positions {got}, expected the next in line to replace 1"


check("a handle Codeforces no longer knows is recorded with the reason and replaced by the next in line", unavailable_is_recorded_and_replaced)


def network_failure_stops_cleanly():
    path = fresh_path()
    drawn(path, per_stratum=3)
    with codeforces(FakeCodeforces(down_after=4)) as fake:
        code = quietly(collect.run, path)
    assert code != 0, "run reported success with the network down"
    assert rows(path, "SELECT count(*) FROM sample_candidates WHERE unavailable IS NOT NULL") == [(0,)], \
        "a network failure was recorded as the user being unavailable"
    assert sum(collected_by_stratum(path).values()) == 4, collected_by_stratum(path)
    assert rows(path, "SELECT count(*) FROM users") == [(4,)], "a user was written for a fetch that failed"


check("the network going down stops the run, marks nobody unavailable, and writes no partial user", network_failure_stops_cleanly)


def refusal_that_is_not_about_the_handle_stops():
    path = fresh_path()
    drawn(path, per_stratum=3)
    with codeforces(FakeCodeforces(refuse_after=2)):
        code = quietly(collect.run, path)
    assert code != 0, "run carried on through a 403"
    marked = rows(path, "SELECT count(*) FROM sample_candidates WHERE unavailable IS NOT NULL")
    assert marked == [(0,)], f"{marked[0][0]} candidates were marked unavailable because of a 403"


check("a refusal that is not 'handle not found' (a 403, a proxy page) stops the run instead of emptying the strata", refusal_that_is_not_about_the_handle_stops)


def rerun_resumes_without_refetching():
    path = fresh_path()
    drawn(path, per_stratum=3)
    with codeforces(FakeCodeforces(down_after=7)) as first:
        quietly(collect.run, path)
    with codeforces(FakeCodeforces()) as second:
        code = quietly(collect.run, path)
    assert code == 0, f"the second run exited {code}"
    assert collected_by_stratum(path) == {s: 3 for s in collect.STRATA}, collected_by_stratum(path)
    again = {h.lower() for h in first.history_requests} & {h.lower() for h in second.history_requests}
    assert not again, f"users collected in the first run were fetched again: {sorted(again)}"


check("running again after a stop finishes the job without fetching anyone already collected", rerun_resumes_without_refetching)


def strata_stay_balanced_when_stopped():
    path = fresh_path()
    drawn(path, per_stratum=3)
    with codeforces(FakeCodeforces(down_after=7)):
        quietly(collect.run, path)
    counts = [collected_by_stratum(path).get(s, 0) for s in collect.STRATA]
    assert max(counts) - min(counts) <= 1, f"after a stop the strata hold {counts}"


check("a run stopped halfway leaves the strata within one user of each other, not the low ones full", strata_stay_balanced_when_stopped)


def exhausted_stratum_is_reported_not_looped():
    path = fresh_path()
    users = rated_list()
    drawn(path, per_stratum=3, users=users)
    everyone_1800 = [h for (h,) in rows(path, "SELECT handle FROM sample_candidates WHERE stratum = 1800")]
    with codeforces(FakeCodeforces(missing=everyone_1800)):
        code = quietly(collect.run, path)
    assert code == 0, f"run exited {code}"
    assert collected_by_stratum(path).get(1800, 0) == 0
    assert all(collected_by_stratum(path)[s] == 3 for s in (1000, 1200, 1400, 1600))


check("a stratum that runs out of available users ends the run instead of looping", exhausted_stratum_is_reported_not_looped)


# --------------------------------------------------------------------- extend

def extend_continues_from_the_next_positions():
    path = fresh_path()
    drawn(path, per_stratum=3)
    with codeforces(FakeCodeforces()) as first:
        quietly(collect.run, path)
    quietly(collect.extend, path, 5)
    with codeforces(FakeCodeforces()) as second:
        code = quietly(collect.run, path)
    assert code == 0, f"run after extend exited {code}"
    assert collected_by_stratum(path) == {s: 5 for s in collect.STRATA}, collected_by_stratum(path)
    positions = sorted({p for (p,) in rows(path, """
        SELECT c.position FROM sample_candidates c
          JOIN users u ON u.handle = c.handle AND u.last_synced IS NOT NULL""")})
    assert positions == [0, 1, 2, 3, 4], f"collected positions {positions}: extend should take the next in line"
    again = {h.lower() for h in first.history_requests} & {h.lower() for h in second.history_requests}
    assert not again, f"extending fetched already-collected users again: {sorted(again)}"
    assert len(second.history_requests) == 10, f"{len(second.history_requests)} fetched, expected 2 more per stratum"
    assert rows(path, "SELECT per_stratum FROM samples") == [(5,)]
    changes = rows(path, "SELECT old_per_stratum, new_per_stratum FROM sample_size_changes")
    assert changes == [(3, 5)], f"the change was recorded as {changes}"
    assert rows(path, "SELECT count(*) FROM sample_candidates") == [(sum(1 for u in rated_list() if 1000 <= u["rating"] <= 1999),)], \
        "extend redrew the candidates"


check("extend raises per_stratum, run takes the next in line in each stratum, nobody is refetched, and the change is recorded", extend_continues_from_the_next_positions)


def extend_only_goes_up():
    path = fresh_path()
    drawn(path, per_stratum=3)
    for n in (3, 2):
        try:
            quietly(collect.extend, path, n)
        except collect.ResizeRefused:
            continue
        raise AssertionError(f"extend to {n} from 3 was allowed")
    assert rows(path, "SELECT per_stratum FROM samples") == [(3,)]
    assert rows(path, "SELECT count(*) FROM sample_size_changes") == [(0,)]
    conn = db.connect(path)
    try:
        # The table refuses it too, whatever code writes to it.
        with conn:
            conn.execute("INSERT INTO sample_size_changes VALUES (1, '2026-09-15T00:00:00Z', 3, 2)")
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("sample_size_changes accepted a decrease")
    finally:
        conn.close()


check("extend refuses the same or a smaller number, and so does the table itself", extend_only_goes_up)


def extend_stops_at_the_smallest_stratum():
    path = fresh_path()
    drawn(path, per_stratum=3)
    smallest = min(pop for (pop,) in rows(path, "SELECT population FROM sample_strata"))
    try:
        quietly(collect.extend, path, smallest + 1)
    except collect.ResizeRefused:
        pass
    else:
        raise AssertionError(f"extend past the smallest stratum ({smallest}) was allowed")
    quietly(collect.extend, path, smallest)
    assert rows(path, "SELECT per_stratum FROM samples") == [(smallest,)]


check("extend refuses more than the smallest stratum holds, so the strata stay equal", extend_stops_at_the_smallest_stratum)


# ---------------------------------------------------------------- the transaction

def rating_changes_are_inside_the_user_transaction():
    path = fresh_path()
    db.init_db(path)
    fake = FakeCodeforces()
    broken = fake.fetch_rating_changes("x")
    del broken[1]["newRating"]
    conn = db.connect(path)
    try:
        try:
            db.save_sync(conn, "someone", 1100, fake.fetch_submissions("someone"), rating_changes=broken)
        except (KeyError, sqlite3.IntegrityError):
            pass
        else:
            raise AssertionError("a malformed rating change was accepted")
        n_users = conn.execute("SELECT count(*) FROM users").fetchone()[0]
        n_subs = conn.execute("SELECT count(*) FROM submissions").fetchone()[0]
    finally:
        conn.close()
    assert (n_users, n_subs) == (0, 0), f"{n_users} users and {n_subs} submissions survived a failed save"


check("a malformed rating change leaves the whole user unwritten (ADR 0004)", rating_changes_are_inside_the_user_transaction)


def one_rating_change_per_user_per_contest():
    path = fresh_path()
    db.init_db(path)
    conn = db.connect(path)
    try:
        with conn:
            conn.execute("INSERT INTO users (handle, first_seen) VALUES ('someone', ?)", (db.utc_now(),))
            conn.execute("INSERT INTO rating_changes VALUES ('someone', 1, 900, 0, 400, '2020-05-20T00:00:00Z')")
        try:
            with conn:
                conn.execute("INSERT INTO rating_changes VALUES ('SOMEONE', 1, 800, 0, 450, '2020-05-20T00:00:00Z')")
        except sqlite3.IntegrityError:
            return
        raise AssertionError("a second rating change for the same user and contest was stored")
    finally:
        conn.close()


check("rating_changes refuses a second row for the same user and contest, in any casing", one_rating_change_per_user_per_contest)


# -------------------------------------------------------------------- refresh

class LaterCodeforces(FakeCodeforces):
    """The same users a month later: one more submission each, and the first
    one hacked since -- its verdict gone from OK to CHALLENGED."""

    def fetch_submissions(self, handle, count=None):
        subs = super().fetch_submissions(handle, count)
        subs[0] = dict(subs[0], verdict="CHALLENGED")
        subs.append(dict(subs[1], id=abs(hash((handle, 3))) % 10**9, creationTimeSeconds=1600000003))
        return subs


def collected(path):
    return {h for (h,) in rows(path, "SELECT handle FROM users WHERE last_synced IS NOT NULL")}


def collected_a_month_ago(path):
    """A full sample whose last fetch was long ago. Backdated by hand, because
    `--older-than-days 0` right after a run would skip whoever was stored in
    the same second as the cutoff."""
    drawn(path, per_stratum=3)
    with codeforces(FakeCodeforces()):
        quietly(collect.run, path)
    conn = db.connect(path)
    try:
        with conn:
            conn.execute("UPDATE users SET last_synced = '2026-01-01T00:00:00Z' WHERE last_synced IS NOT NULL")
    finally:
        conn.close()
    return collected(path)


def refresh_brings_everyone_up_to_date():
    path = fresh_path()
    before = collected_a_month_ago(path)
    with codeforces(LaterCodeforces()) as fake:
        code = quietly(collect.refresh, path)
    assert code == 0, f"refresh exited {code}"
    assert {h.lower() for h in fake.history_requests} == {h.lower() for h in before}, \
        "refresh fetched somebody other than exactly the collected users"
    assert collected(path) == before, "the set of collected users changed"
    stale = rows(path, "SELECT count(*) FROM users WHERE last_synced < '2026-02-01T00:00:00Z'")
    assert stale == [(0,)], f"{stale[0][0]} refreshed users kept the old last_synced"
    per_user = rows(path, "SELECT handle, count(*), sum(verdict = 'CHALLENGED') FROM submissions GROUP BY handle")
    wrong = [r for r in per_user if r[1:] != (4, 1)]
    assert not wrong, f"(handle, submissions, hacked) not (4, 1) after the refresh: {wrong[:3]}"


check("refresh fetches exactly the collected users again: new submissions added, a hack since the last fetch recorded", refresh_brings_everyone_up_to_date)


def refresh_resumes_where_it_stopped():
    path = fresh_path()
    before = collected_a_month_ago(path)
    with codeforces(LaterCodeforces(down_after=4)) as first:
        code = quietly(collect.refresh, path)
    assert code != 0, "refresh reported success with the network down"
    with codeforces(LaterCodeforces()) as second:
        code = quietly(collect.refresh, path)
    assert code == 0, f"the second refresh exited {code}"
    again = {h.lower() for h in first.history_requests} & {h.lower() for h in second.history_requests}
    assert not again, f"users refreshed before the stop were fetched again: {sorted(again)}"
    total = len(first.history_requests) + len(second.history_requests)
    assert total == len(before), f"{total} fetches for {len(before)} users"


check("a refresh stopped halfway carries on from where it stopped, fetching nobody twice", refresh_resumes_where_it_stopped)


def refresh_keeps_a_user_who_vanished():
    path = fresh_path()
    before = collected_a_month_ago(path)
    gone = sorted(before)[0]
    with codeforces(LaterCodeforces(missing=[gone])):
        code = quietly(collect.refresh, path)
    assert code == 0, f"refresh exited {code}"
    marked = rows(path, "SELECT count(*) FROM sample_candidates WHERE unavailable IS NOT NULL")
    assert marked == [(0,)], "a collected user who vanished was marked unavailable -- the next run would replace them"
    assert collected(path) == before, "the set of collected users changed"
    kept = rows(path, "SELECT count(*) FROM submissions WHERE handle = ?", (gone,))
    assert kept == [(3,)], f"the vanished user's history is now {kept[0][0]} submissions, not the 3 stored"


check("a collected user whose handle is gone keeps their rows and their place in the sample", refresh_keeps_a_user_who_vanished)


shutil.rmtree(SCRATCH, ignore_errors=True)
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
