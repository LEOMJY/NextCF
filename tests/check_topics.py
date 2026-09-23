"""Check for the topic breakdown -- spec section 6, ADR 0010.

The one that matters most is tags_come_from_the_canonical_copy. Everything
else here would still pass if that rule were broken, and the bug it prevents
is invisible: a number that is wrong by a topic, on a page whose whole job is
to say which topics you are good at.
"""

import os
import sqlite3
import sys
from pathlib import Path

# Paths in this file are relative to the repository root, and the modules
# being checked live there, so go there first. The check then runs the same
# from any directory.
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
import db  # noqa: E402

SCHEMA = open("schema.sql", encoding="utf-8").read()
passed, failed = 0, 0


def check(label, fn):
    global passed, failed
    try:
        fn()
    except AssertionError as exc:
        print(f"  FAIL  {label}: {exc}")
        failed += 1
    else:
        print(f"  ok    {label}")
        passed += 1


def fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def problem(contest, index, name, rating, tags):
    return {"contestId": contest, "index": index, "name": name,
            "rating": rating, "tags": tags}


def submission(sid, prob, verdict="OK"):
    return {"id": sid, "verdict": verdict, "creationTimeSeconds": 1700000000 + sid,
            "author": {"participantType": "PRACTICE"}, "problem": prob}


def topics(conn, handle="t"):
    return {r["tag"]: r for r in db.topic_breakdown(conn, handle)}


print("topic breakdown")


# ----------------------------------------------------------------- the gate

def refuses_an_unknown_handle():
    conn = fresh()
    assert db.topic_breakdown(conn, "nobody") is None
    assert db.problem_totals(conn, "nobody") is None


def refuses_a_user_whose_sync_never_finished():
    """ADR 0004: rows can exist while last_synced is NULL, and they are a lie."""
    conn = fresh()
    conn.execute("INSERT INTO users (handle, first_seen) VALUES ('t', '2026-01-01T00:00:00Z')")
    conn.execute(
        "INSERT INTO problems (id, contest_id, problem_index, name, rating)"
        " VALUES ('1A', 1, 'A', 'P', 800)")
    conn.execute("INSERT INTO problem_tags VALUES ('1A', 'dp')")
    conn.execute(
        "INSERT INTO submissions VALUES (1, 't', '1A', 'OK', 'PRACTICE', '2026-01-01T00:00:00Z')")
    conn.commit()
    assert db.topic_breakdown(conn, "t") is None, "half-synced data was served"
    assert db.problem_totals(conn, "t") is None, "half-synced totals were served"


def a_synced_user_with_no_submissions_is_not_none():
    conn = fresh()
    db.save_sync(conn, "t", 1200, [])
    assert db.topic_breakdown(conn, "t") == [], "empty history should be [], not None"
    assert db.problem_totals(conn, "t")["attempted"] == 0


check("an unknown handle gets None", refuses_an_unknown_handle)
check("a half-synced user gets None (ADR 0004)", refuses_a_user_whose_sync_never_finished)
check("a synced user with nothing gets [] and zero", a_synced_user_with_no_submissions_is_not_none)


# ------------------------------------------------- the rule that matters most

def tags_come_from_the_canonical_copy():
    """The real 1292A / 1293C pair, with their real, different tags.

    The user solved the Div. 2 copy. What they did is a dsu problem; what
    Codeforces labels that id is constructive algorithms. The breakdown must
    report the former.
    """
    conn = fresh()
    db.save_problemset(conn, [
        problem(1292, "A", "NEKO's Maze Game", 1400,
                ["data structures", "dsu", "implementation"])])
    db.save_sync(conn, "t", 1500, [submission(1, problem(
        1293, "C", "NEKO's Maze Game", 1400,
        ["constructive algorithms", "implementation"]))])
    db.rebuild_aliases(conn)

    got = topics(conn)
    assert set(got) == {"data structures", "dsu", "implementation"}, sorted(got)
    assert "constructive algorithms" not in got, "the ALIAS's tags were counted"
    assert got["dsu"]["solved"] == 1


def the_alias_keeps_its_own_tag_rows():
    """Never counted, never deleted -- they are the evidence the map works."""
    conn = fresh()
    db.save_problemset(conn, [problem(1292, "A", "NEKO", 1400, ["dsu"])])
    db.save_sync(conn, "t", 1500, [submission(1, problem(
        1293, "C", "NEKO", 1400, ["constructive algorithms"]))])
    db.rebuild_aliases(conn)
    stored = [t for (t,) in conn.execute(
        "SELECT tag FROM problem_tags WHERE problem_id = '1293C'")]
    assert stored == ["constructive algorithms"], stored


def both_copies_of_one_problem_are_one_problem():
    conn = fresh()
    db.save_problemset(conn, [problem(1292, "A", "NEKO", 1400, ["dsu"])])
    db.save_sync(conn, "t", 1500, [
        submission(1, problem(1292, "A", "NEKO", 1400, ["dsu"])),
        submission(2, problem(1293, "C", "NEKO", 1400, ["constructive algorithms"])),
    ])
    db.rebuild_aliases(conn)
    assert db.problem_totals(conn, "t")["solved"] == 1, "one problem counted twice"
    assert topics(conn)["dsu"]["solved"] == 1


check("tags come from the canonical copy", tags_come_from_the_canonical_copy)
check("the alias keeps its own tag rows", the_alias_keeps_its_own_tag_rows)
check("solving both copies is one problem", both_copies_of_one_problem_are_one_problem)


# ------------------------------------------------------------- the counting

def counts_problems_not_submissions():
    """Three wrong answers then an accepted one is one solved problem."""
    conn = fresh()
    p = problem(1, "A", "P", 800, ["dp"])
    db.save_sync(conn, "t", 1200, [
        submission(1, p, "WRONG_ANSWER"), submission(2, p, "WRONG_ANSWER"),
        submission(3, p, "TIME_LIMIT_EXCEEDED"), submission(4, p, "OK"),
    ])
    row = topics(conn)["dp"]
    assert (row["solved"], row["attempted"]) == (1, 1), dict(row)


def an_unsolved_problem_is_attempted_not_solved():
    conn = fresh()
    db.save_sync(conn, "t", 1200, [
        submission(1, problem(1, "A", "Solved", 800, ["dp"])),
        submission(2, problem(2, "B", "Failed", 900, ["dp"]), "WRONG_ANSWER"),
    ])
    row = topics(conn)["dp"]
    assert (row["solved"], row["attempted"]) == (1, 2), dict(row)


def a_submission_still_being_judged_is_not_solved():
    """verdict is NULL while judging, and NULL = 'OK' is NULL, not false."""
    conn = fresh()
    db.save_sync(conn, "t", 1200, [
        submission(1, problem(1, "A", "P", 800, ["dp"]), None)])
    row = topics(conn)["dp"]
    assert (row["solved"], row["attempted"]) == (0, 1), dict(row)
    assert db.problem_totals(conn, "t")["solved"] == 0


def one_problem_counts_under_each_of_its_tags():
    conn = fresh()
    db.save_sync(conn, "t", 1200, [
        submission(1, problem(1, "A", "P", 800, ["dp", "greedy", "math"]))])
    got = topics(conn)
    assert [got[t]["solved"] for t in ("dp", "greedy", "math")] == [1, 1, 1]
    assert db.problem_totals(conn, "t")["solved"] == 1, "totals double-counted the tags"


check("counts problems, not submissions", counts_problems_not_submissions)
check("an unsolved problem is attempted, not solved", an_unsolved_problem_is_attempted_not_solved)
check("a submission still being judged is not solved", a_submission_still_being_judged_is_not_solved)
check("one problem counts under each of its tags", one_problem_counts_under_each_of_its_tags)


# ------------------------------------------------------------- the difficulty

def the_mean_covers_solved_rated_problems_only():
    conn = fresh()
    db.save_sync(conn, "t", 1200, [
        submission(1, problem(1, "A", "Easy",   1000, ["dp"])),
        submission(2, problem(2, "B", "Hard",   2000, ["dp"])),
        submission(3, problem(3, "C", "Failed", 3000, ["dp"]), "WRONG_ANSWER"),
        submission(4, problem(4, "D", "Unrated", None, ["dp"])),
    ])
    row = topics(conn)["dp"]
    assert row["attempted"] == 4, dict(row)
    assert row["solved"] == 3, dict(row)
    assert row["rated_solved"] == 2, "the unrated solve was counted in the mean's n"
    assert row["mean_solved_rating"] == 1500, row["mean_solved_rating"]


def a_topic_with_no_rated_solves_has_no_mean():
    conn = fresh()
    db.save_sync(conn, "t", 1200, [
        submission(1, problem(1, "A", "P", None, ["dp"]))])
    row = topics(conn)["dp"]
    assert row["rated_solved"] == 0, dict(row)
    assert row["mean_solved_rating"] is None, "a mean was invented from no data"


check("the mean covers solved, rated problems only", the_mean_covers_solved_rated_problems_only)
check("no rated solves means no mean, not zero", a_topic_with_no_rated_solves_has_no_mean)


# ----------------------------------------------------------------- the totals

def untagged_solves_are_reported_separately():
    """A solved problem with no tags is in no bar, so the bars cannot add up."""
    conn = fresh()
    db.save_sync(conn, "t", 1200, [
        submission(1, problem(1, "A", "Tagged", 800, ["dp"])),
        submission(2, problem(100500, "A", "Gym", None, [])),
    ])
    totals = db.problem_totals(conn, "t")
    assert totals["solved"] == 2, dict(totals)
    assert totals["solved_untagged"] == 1, dict(totals)
    assert sum(r["solved"] for r in db.topic_breakdown(conn, "t")) == 1


def rows_come_back_most_solved_first():
    conn = fresh()
    db.save_sync(conn, "t", 1200, [
        submission(1, problem(1, "A", "P1", 800, ["dp", "greedy"])),
        submission(2, problem(2, "B", "P2", 800, ["greedy"])),
        submission(3, problem(3, "C", "P3", 800, ["greedy"])),
    ])
    order = [r["tag"] for r in db.topic_breakdown(conn, "t")]
    assert order == ["greedy", "dp"], order


check("untagged solves are reported separately", untagged_solves_are_reported_separately)
check("rows come back most-solved first", rows_come_back_most_solved_first)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
