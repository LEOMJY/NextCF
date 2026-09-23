"""Check that schema.sql does what its comments claim.

Each test asserts a constraint actually FIRES, not merely that the file parses.
A constraint that is silently not enforced is worse than no constraint.
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

SCHEMA = open("schema.sql", encoding="utf-8").read()
passed, failed = 0, 0


def fresh():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


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


def rejects(conn, sql, args=()):
    """Assert the statement is refused by the database."""
    try:
        conn.execute(sql, args)
    except sqlite3.Error:
        return
    raise AssertionError("statement was ACCEPTED but should have been rejected")


def seed(conn):
    conn.execute("INSERT INTO users (handle, first_seen) VALUES ('tourist', '2026-09-09T00:00:00Z')")
    conn.execute(
        "INSERT INTO problems (id, contest_id, problem_index, name, rating)"
        " VALUES ('1234A', 1234, 'A', 'Watermelon', 800)"
    )


print("schema.sql")

check("executes cleanly", lambda: fresh())


def nocase_handle():
    conn = fresh()
    seed(conn)
    rejects(conn, "INSERT INTO users (handle, first_seen) VALUES ('Tourist', '2026-09-09T00:00:00Z')")


check("users.handle is case-insensitive (Tourist == tourist)", nocase_handle)


def strict_types():
    conn = fresh()
    rejects(
        conn,
        "INSERT INTO users (handle, cf_rating, first_seen) VALUES ('x', 'banana', '2026-09-09T00:00:00Z')",
    )


check("STRICT rejects text in an INTEGER column", strict_types)


def job_state_check():
    conn = fresh()
    rejects(
        conn,
        "INSERT INTO jobs (kind, target, state, started_at) VALUES ('sync', 'tourist', 'runnign', '2026-09-09T00:00:00Z')",
    )


check("CHECK rejects a misspelled job state", job_state_check)


def foreign_keys_enforced():
    conn = fresh()
    seed(conn)
    rejects(
        conn,
        "INSERT INTO submissions (id, handle, problem_id, submitted_at)"
        " VALUES (1, 'nobody', '1234A', '2026-09-09T00:00:00Z')",
    )


check("foreign key rejects a submission by an unknown handle", foreign_keys_enforced)


def tags_dedupe():
    conn = fresh()
    seed(conn)
    for _ in range(2):
        conn.execute("INSERT OR IGNORE INTO problem_tags VALUES ('1234A', 'math')")
    n = conn.execute("SELECT count(*) FROM problem_tags").fetchone()[0]
    assert n == 1, f"expected 1 tag row, got {n}"


check("re-inserting a tag leaves one row", tags_dedupe)


def submissions_idempotent():
    """The ADR 0004 proof: re-running a sync must not duplicate rows."""
    conn = fresh()
    seed(conn)
    rows = [
        (101, "tourist", "1234A", "OK", "PRACTICE", "2026-09-01T10:00:00Z"),
        (102, "tourist", "1234A", "WRONG_ANSWER", "PRACTICE", "2026-09-01T11:00:00Z"),
        (103, "tourist", "1234A", None, "CONTESTANT", "2026-09-02T09:00:00Z"),
    ]
    for _ in range(2):
        conn.executemany("INSERT OR IGNORE INTO submissions VALUES (?,?,?,?,?,?)", rows)
    n = conn.execute("SELECT count(*) FROM submissions").fetchone()[0]
    assert n == 3, f"expected 3 submissions after inserting twice, got {n}"


check("inserting the same 3 submissions twice leaves 3 rows", submissions_idempotent)


def one_active_job():
    conn = fresh()
    conn.execute("INSERT INTO jobs (kind, target, started_at) VALUES ('sync', 'tourist', '2026-09-09T00:00:00Z')")
    rejects(conn, "INSERT INTO jobs (kind, target, started_at) VALUES ('sync', 'tourist', '2026-09-09T00:00:01Z')")


check("a second pending job for the same handle is refused", one_active_job)


def retry_after_failure():
    conn = fresh()
    conn.execute("INSERT INTO jobs (kind, target, started_at) VALUES ('sync', 'tourist', '2026-09-09T00:00:00Z')")
    conn.execute("UPDATE jobs SET state = 'failed' WHERE target = 'tourist'")
    conn.execute("INSERT INTO jobs (kind, target, started_at) VALUES ('sync', 'tourist', '2026-09-09T00:00:02Z')")


check("...but a retry after that job failed is allowed", retry_after_failure)


def rollback_leaves_nothing():
    """ADR 0004: an interrupted sync writes nothing at all."""
    conn = fresh()
    seed(conn)
    conn.commit()
    try:
        with conn:
            conn.execute(
                "INSERT INTO submissions VALUES (201, 'tourist', '1234A', 'OK', 'PRACTICE', '2026-09-03T00:00:00Z')"
            )
            conn.execute("UPDATE users SET last_synced = '2026-09-09T00:00:00Z' WHERE handle = 'tourist'")
            raise RuntimeError("connection dropped mid-user")
    except RuntimeError:
        pass
    n = conn.execute("SELECT count(*) FROM submissions").fetchone()[0]
    flag = conn.execute("SELECT last_synced FROM users WHERE handle = 'tourist'").fetchone()[0]
    assert n == 0, f"expected 0 submissions after rollback, got {n}"
    assert flag is None, f"expected last_synced to stay NULL, got {flag!r}"


check("an interrupted transaction leaves 0 rows and last_synced NULL", rollback_leaves_nothing)


def id_disagrees_with_parts():
    conn = fresh()
    rejects(
        conn,
        "INSERT INTO problems (id, contest_id, problem_index, name)"
        " VALUES ('1234A', 1234, 'B', 'Mismatch')",
    )


check("problems CHECK rejects an id that disagrees with its parts", id_disagrees_with_parts)


def numeric_index_keeps_its_parts():
    """Contest 921 has indices '01'..'14', so '92114' cannot be split back."""
    conn = fresh()
    conn.execute(
        "INSERT INTO problems (id, contest_id, problem_index, name)"
        " VALUES ('92114', 921, '14', 'Labyrinth-14')"
    )
    row = conn.execute("SELECT contest_id, problem_index FROM problems WHERE id = '92114'").fetchone()
    assert row == (921, "14"), f"expected (921, '14'), got {row}"


check("contest 921 numeric index stored as (921, '14'), never re-parsed", numeric_index_keeps_its_parts)


def acmsguru_without_contest():
    conn = fresh()
    conn.execute(
        "INSERT INTO problems (id, contest_id, problem_index, name)"
        " VALUES ('acmsguru553', NULL, '553', 'placeholder')"
    )


check("an acmsguru problem with no contest_id is accepted", acmsguru_without_contest)


def join_reads_back():
    conn = fresh()
    seed(conn)
    conn.executemany("INSERT INTO problem_tags VALUES (?,?)", [("1234A", "math"), ("1234A", "implementation")])
    conn.execute(
        "INSERT INTO submissions VALUES (301, 'Tourist', '1234A', 'OK', 'PRACTICE', '2026-09-04T00:00:00Z')"
    )
    row = conn.execute(
        """
        SELECT p.name, p.rating, s.verdict, group_concat(t.tag) AS tags
          FROM submissions s
          JOIN problems     p ON p.id         = s.problem_id
          JOIN problem_tags t ON t.problem_id = p.id
         WHERE s.handle = 'tourist'
         GROUP BY s.id
        """
    ).fetchone()
    assert row is not None, "join returned nothing -- NOCASE lookup failed?"
    assert row[0] == "Watermelon", row


check("join across all three tables reads back (inserted as 'Tourist')", join_reads_back)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
