"""Check for the alias map -- ADR 0010.

Two halves.

The first builds tiny databases in memory and asserts that db._rebuild_aliases
does what the ADR says, including refusing to guess.

The second is the one ADR 0010 promised: method A, implemented here and
NOWHERE in the shipped code, run against dataset.db and compared with the
method B that ships. A is independent of B -- it clusters contests by when
their in-contest submissions happened, where B compares names and ratings -- so
agreement between them is evidence, and disagreement means the data moved or a
method is wrong. Skipped unless the dataset tier is asked for -- see
tests/run.py; the data lives on the author's machine only.
"""

import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
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
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def add(conn, pid, contest, index, name, rating, listed):
    conn.execute(
        "INSERT INTO problems (id, contest_id, problem_index, name, rating, in_problemset)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (pid, contest, index, name, rating, listed),
    )


def mapping(conn):
    return dict(conn.execute("SELECT alias_id, canonical_id FROM problem_aliases"))


print("alias map -- ADR 0010")


# ------------------------------------------------------------------ the schema

def rejects_self_alias():
    conn = fresh()
    add(conn, "1292A", 1292, "A", "NEKO", 1400, 1)
    try:
        conn.execute("INSERT INTO problem_aliases VALUES ('1292A', '1292A')")
    except sqlite3.Error:
        return
    raise AssertionError("a problem was allowed to be its own alias")


def rejects_two_canonicals_for_one_alias():
    conn = fresh()
    add(conn, "1292A", 1292, "A", "NEKO", 1400, 1)
    add(conn, "1294A", 1294, "A", "Other", 1400, 1)
    add(conn, "1293C", 1293, "C", "NEKO", 1400, 0)
    conn.execute("INSERT INTO problem_aliases VALUES ('1293C', '1292A')")
    try:
        conn.execute("INSERT INTO problem_aliases VALUES ('1293C', '1294A')")
    except sqlite3.Error:
        return
    raise AssertionError("one alias was allowed two canonical ids")


def alias_rows_follow_a_deleted_problem():
    conn = fresh()
    add(conn, "1292A", 1292, "A", "NEKO", 1400, 1)
    add(conn, "1293C", 1293, "C", "NEKO", 1400, 0)
    conn.execute("INSERT INTO problem_aliases VALUES ('1293C', '1292A')")
    conn.execute("DELETE FROM problems WHERE id = '1292A'")
    left = conn.execute("SELECT COUNT(*) FROM problem_aliases").fetchone()[0]
    assert left == 0, f"{left} alias rows survived their canonical problem"


check("a problem cannot be its own alias", rejects_self_alias)
check("an alias cannot have two canonical ids", rejects_two_canonicals_for_one_alias)
check("alias rows cascade with the problem", alias_rows_follow_a_deleted_problem)


# ------------------------------------------------------------------- the build

def maps_a_div1_div2_pair():
    conn = fresh()
    add(conn, "1292A", 1292, "A", "NEKO's Maze Game", 1400, 1)
    add(conn, "1293C", 1293, "C", "NEKO's Maze Game", 1400, 0)
    db.rebuild_aliases(conn)
    assert mapping(conn) == {"1293C": "1292A"}, mapping(conn)


def maps_every_copy_in_a_three_way_group():
    """VK Cup finals run the same problems under three contest ids."""
    conn = fresh()
    add(conn, "1784D", 1784, "D", "Wooden Spoon", 2400, 1)
    add(conn, "1785D", 1785, "D", "Wooden Spoon", 2400, 0)
    add(conn, "1786F", 1786, "F", "Wooden Spoon", 2400, 0)
    db.rebuild_aliases(conn)
    assert mapping(conn) == {"1785D": "1784D", "1786F": "1784D"}, mapping(conn)


def refuses_when_two_listed_problems_match():
    """The problemset holds three different problems called "Game" rated 800.

    An unlisted problem with that name and rating cannot be resolved, and the
    ADR's whole safety argument is that this produces no row rather than a
    coin flip.
    """
    conn = fresh()
    add(conn, "513A", 513, "A", "Game", 800, 1)
    add(conn, "984A", 984, "A", "Game", 800, 1)
    add(conn, "9999A", 9999, "A", "Game", 800, 0)
    db.rebuild_aliases(conn)
    assert mapping(conn) == {}, mapping(conn)


def ignores_an_unrated_alias():
    conn = fresh()
    add(conn, "1292A", 1292, "A", "NEKO", 1400, 1)
    add(conn, "1293C", 1293, "C", "NEKO", None, 0)
    db.rebuild_aliases(conn)
    assert mapping(conn) == {}, mapping(conn)


def ignores_a_different_rating():
    conn = fresh()
    add(conn, "1292A", 1292, "A", "NEKO", 1400, 1)
    add(conn, "1293C", 1293, "C", "NEKO", 1500, 0)
    db.rebuild_aliases(conn)
    assert mapping(conn) == {}, mapping(conn)


def ignores_gym_and_acmsguru():
    conn = fresh()
    add(conn, "1292A", 1292, "A", "NEKO", 1400, 1)
    add(conn, "100500A", 100500, "A", "NEKO", 1400, 0)
    add(conn, "acmsguru553", None, "553", "NEKO", 1400, 0)
    db.rebuild_aliases(conn)
    assert mapping(conn) == {}, mapping(conn)


def rebuilding_twice_changes_nothing():
    conn = fresh()
    add(conn, "1292A", 1292, "A", "NEKO", 1400, 1)
    add(conn, "1293C", 1293, "C", "NEKO", 1400, 0)
    db.rebuild_aliases(conn)
    first = mapping(conn)
    db.rebuild_aliases(conn)
    assert mapping(conn) == first, "the map is not idempotent"
    rows = conn.execute("SELECT COUNT(*) FROM problem_aliases").fetchone()[0]
    assert rows == 1, f"{rows} rows after two rebuilds -- DELETE did not run?"


check("maps a Div.1/Div.2 pair", maps_a_div1_div2_pair)
check("maps every copy in a three-way group", maps_every_copy_in_a_three_way_group)
check("refuses when two listed problems match", refuses_when_two_listed_problems_match)
check("ignores an alias with no rating", ignores_an_unrated_alias)
check("ignores a copy whose rating differs", ignores_a_different_rating)
check("ignores gym and acmsguru", ignores_gym_and_acmsguru)
check("rebuilding twice changes nothing", rebuilding_twice_changes_nothing)


# --------------------------------------------------------- membership is a snapshot

def a_problem_leaving_the_problemset_loses_its_aliases():
    """save_problemset() clears in_problemset before re-setting it.

    Without the clear, an id whose contest was removed from Codeforces would
    still be a valid recommendation, forever.
    """
    conn = fresh()
    api_shape = [
        {"contestId": 1292, "index": "A", "name": "NEKO", "rating": 1400, "tags": ["dsu"]},
    ]
    db.save_problemset(conn, api_shape)
    add(conn, "1293C", 1293, "C", "NEKO", 1400, 0)
    db.rebuild_aliases(conn)
    assert mapping(conn) == {"1293C": "1292A"}, mapping(conn)

    # The next fetch no longer lists it.
    db.save_problemset(conn, [
        {"contestId": 1500, "index": "A", "name": "Something else", "rating": 900, "tags": []},
    ])
    listed = conn.execute(
        "SELECT in_problemset FROM problems WHERE id = '1292A'").fetchone()[0]
    assert listed == 0, "in_problemset survived a fetch that did not list the problem"
    assert mapping(conn) == {}, mapping(conn)


def save_problemset_leaves_a_synced_problem_unlisted():
    """save_sync() must never mark something as being in the problemset."""
    conn = fresh()
    db.save_problemset(conn, [
        {"contestId": 1292, "index": "A", "name": "NEKO", "rating": 1400, "tags": []},
    ])
    db.save_sync(conn, "t", 1500, [{
        "id": 1, "verdict": "OK", "creationTimeSeconds": 1700000000,
        "author": {"participantType": "PRACTICE"},
        "problem": {"contestId": 1293, "index": "C", "name": "NEKO",
                    "rating": 1400, "tags": []},
    }])
    listed = dict(conn.execute("SELECT id, in_problemset FROM problems"))
    assert listed == {"1292A": 1, "1293C": 0}, listed


check("a problem leaving the problemset loses its aliases",
      a_problem_leaving_the_problemset_loses_its_aliases)
check("a synced problem is never marked as listed",
      save_problemset_leaves_a_synced_problem_unlisted)


# -------------------------------------------- method A, against the real dataset

def method_a(conn):
    """Cluster contests that ran at the same time, then match names inside.

    Deliberately shares no code with db.py. A CONTESTANT submission can only
    be made while its contest is running, so the earliest one per contest says
    when that contest started; contests starting within twenty minutes of each
    other were run together, which is what a Div.1/Div.2 pair is.
    """
    stamp = lambda s: datetime.strptime(s, db.TIMESTAMP_FORMAT).timestamp()
    rows = sorted(conn.execute(
        """
        SELECT p.contest_id, MIN(s.submitted_at)
          FROM submissions s JOIN problems p ON p.id = s.problem_id
         WHERE s.participant_type = 'CONTESTANT' AND p.contest_id < ?
         GROUP BY p.contest_id
        """, (db.GYM_CONTEST_ID_FLOOR,)), key=lambda r: r[1])

    clusters, current = [], [rows[0]]
    for row in rows[1:]:
        if stamp(row[1]) - stamp(current[-1][1]) <= 20 * 60:
            current.append(row)
        else:
            clusters.append(current)
            current = [row]
    clusters.append(current)

    by_contest = defaultdict(list)
    for pid, cid, name, listed in conn.execute(
            "SELECT id, contest_id, name, in_problemset FROM problems"
            " WHERE contest_id IS NOT NULL AND contest_id < ?",
            (db.GYM_CONTEST_ID_FLOOR,)):
        by_contest[cid].append((pid, name, listed))

    found = {}
    for cluster in (c for c in clusters if len(c) > 1):
        by_name = defaultdict(list)
        for cid, _ in cluster:
            for pid, name, listed in by_contest[cid]:
                by_name[name].append((pid, listed))
        for members in by_name.values():
            canonical = [pid for pid, listed in members if listed]
            if len(canonical) == 1:
                for pid, listed in members:
                    if not listed:
                        found[pid] = canonical[0]
    return found


def methods_agree_on_the_dataset():
    path = Path("dataset.db")
    if not os.environ.get("NEXTCF_TESTS_DATASET"):
        print("        (dataset tier not asked for -- skipped)")
        return
    if not path.exists():
        print("        (dataset.db absent -- skipped)")
        return
    conn = db.connect(path)
    try:
        stored = dict(conn.execute("SELECT alias_id, canonical_id FROM problem_aliases"))
        assert stored, "problem_aliases is empty -- has the problemset been fetched?"
        theirs = method_a(conn)
        both = set(stored) & set(theirs)
        assert both, "the two methods share no ids at all, which cannot be right"
        clashes = {k: (stored[k], theirs[k]) for k in both if stored[k] != theirs[k]}
        assert not clashes, f"{len(clashes)} disagreements, e.g. {list(clashes.items())[:3]}"
        print(f"        (B {len(stored)}, A {len(theirs)}, overlap {len(both)}, no disagreement)")
    finally:
        conn.close()


check("methods A and B never disagree on dataset.db", methods_agree_on_the_dataset)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
