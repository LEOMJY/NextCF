"""Check that db.py does what its comments claim.

Same rule as check_schema.py: every claim is tested by making the failure it
prevents actually happen. Where a claim is "without X, Y breaks", the version
without X is run too, so the test proves X is doing the work.
"""

import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

# Paths in this file are relative to the repository root, and the modules
# being checked live there, so go there first. The check then runs the same
# from any directory.
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
import db  # noqa: E402

SCRATCH = Path(tempfile.mkdtemp(prefix="dbcheck-"))
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
    return SCRATCH / f"test{_counter}.db"


def seed(conn):
    with conn:
        conn.execute("INSERT INTO users (handle, first_seen) VALUES ('tourist', ?)", (db.utc_now(),))
        conn.execute(
            "INSERT INTO problems (id, contest_id, problem_index, name)"
            " VALUES ('1234A', 1234, 'A', 'Watermelon')"
        )


def seed_path(path):
    conn = sqlite3.connect(path)
    try:
        seed(conn)
    finally:
        conn.close()


print("db.py")


def creates_all_tables():
    path = fresh_path()
    db.init_db(path)
    conn = db.connect(path)
    try:
        names = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()
    expected = {"users", "problems", "problem_tags", "submissions", "jobs"}
    assert expected <= names, f"missing: {expected - names}"


check("init_db creates all five tables", creates_all_tables)


def second_init_keeps_data():
    path = fresh_path()
    db.init_db(path)
    conn = db.connect(path)
    try:
        seed(conn)
    finally:
        conn.close()
    db.init_db(path)
    conn = db.connect(path)
    try:
        n = conn.execute("SELECT count(*) FROM users").fetchone()[0]
    finally:
        conn.close()
    assert n == 1, f"expected the user to survive a second init_db, found {n}"


check("running init_db a second time keeps existing data", second_init_keeps_data)


def file_is_wal():
    path = fresh_path()
    db.init_db(path)
    conn = sqlite3.connect(path)  # plain connection: the mode belongs to the file
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()
    assert mode == "wal", f"got {mode!r}"


check("the file stays in WAL mode, even for a plain connection", file_is_wal)


def connect_enforces_foreign_keys():
    path = fresh_path()
    db.init_db(path)
    conn = db.connect(path)
    try:
        seed(conn)
        try:
            with conn:
                conn.execute(
                    "INSERT INTO submissions (id, handle, problem_id, submitted_at)"
                    " VALUES (1, 'nobody', '1234A', ?)",
                    (db.utc_now(),),
                )
        except sqlite3.IntegrityError:
            return
        raise AssertionError("a submission by an unknown handle was ACCEPTED")
    finally:
        conn.close()


check("connect() refuses a submission by an unknown handle", connect_enforces_foreign_keys)


def plain_connection_accepts_it():
    path = fresh_path()
    db.init_db(path)
    conn = sqlite3.connect(path)  # no pragma
    try:
        seed(conn)
        with conn:
            conn.execute(
                "INSERT INTO submissions (id, handle, problem_id, submitted_at)"
                " VALUES (1, 'nobody', '1234A', 'x')"
            )
        n = conn.execute("SELECT count(*) FROM submissions WHERE handle = 'nobody'").fetchone()[0]
    finally:
        conn.close()
    assert n == 1, "the unchecked row was not stored -- counterfactual did not reproduce"


check("...while a plain sqlite3.connect() silently stores the same row", plain_connection_accepts_it)


def rows_by_name():
    path = fresh_path()
    db.init_db(path)
    conn = db.connect(path)
    try:
        seed(conn)
        row = conn.execute("SELECT handle, target_prob FROM users").fetchone()
    finally:
        conn.close()
    assert row["handle"] == "tourist" and row["target_prob"] == 0.70, dict(row)


check("rows are readable by column name", rows_by_name)


def orphaned_jobs():
    path = fresh_path()
    db.init_db(path)
    conn = db.connect(path)
    try:
        with conn:
            for target, state in [("tourist", "pending"), ("alice", "running"), ("bob", "done")]:
                conn.execute(
                    "INSERT INTO jobs (kind, target, state, started_at) VALUES ('sync', ?, ?, ?)",
                    (target, state, db.utc_now()),
                )
        # Before the restart, the stale pending row locks tourist out.
        try:
            with conn:
                conn.execute(
                    "INSERT INTO jobs (kind, target, started_at) VALUES ('sync', 'tourist', ?)",
                    (db.utc_now(),),
                )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("a second unfinished job for tourist was accepted BEFORE cleanup")
    finally:
        conn.close()

    marked = db.fail_orphaned_jobs(path)  # the web app starting again

    conn = db.connect(path)
    try:
        rows = {r["target"]: dict(r) for r in conn.execute("SELECT target, state, finished_at, error FROM jobs")}
        assert marked == 2, f"fail_orphaned_jobs reported {marked} orphaned jobs, expected 2"
        for t in ("tourist", "alice"):
            assert rows[t]["state"] == "failed", f"{t} is still {rows[t]['state']}"
            assert rows[t]["finished_at"] and rows[t]["error"], f"{t} has no finished_at or error"
        assert rows["bob"]["state"] == "done", "a finished job was modified"
        with conn:
            conn.execute(
                "INSERT INTO jobs (kind, target, started_at) VALUES ('sync', 'tourist', ?)",
                (db.utc_now(),),
            )
    finally:
        conn.close()


check("fail_orphaned_jobs fails pending and running jobs, spares done ones, unblocks the handle", orphaned_jobs)


# The next two start real, separate Python processes against one database file
# holding a sync that is mid-flight -- the situation spec section 12 asked
# about. A second program is simulated by being one, not by calling a function.
def job_state_after_a_program_starts(program):
    path = fresh_path()
    db.init_db(path)
    conn = db.connect(path)
    try:
        job_id = db.create_job(conn, "sync", "tourist")
        db.start_job(conn, job_id)
    finally:
        conn.close()

    env = dict(os.environ, NEXTCF_DB=str(path))
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=os.getcwd(), env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"{program!r} exited {result.returncode}: {result.stderr.strip()}"

    conn = db.connect(path)
    try:
        return db.get_job(conn, job_id)["state"]
    finally:
        conn.close()


def other_program_spares_a_live_sync():
    # What sync.py's main() does at startup, and what collect.py will do.
    state = job_state_after_a_program_starts("import db; db.init_db()")
    assert state == "running", f"another program starting up turned a live sync into {state!r}"


check("another program calling init_db() leaves a running sync alone", other_program_spares_a_live_sync)


def web_app_fails_an_orphaned_sync():
    # The same row, but the program starting is the web app. It is the only
    # program that starts syncs, so a running sync it finds at startup belongs
    # to a process that has died.
    state = job_state_after_a_program_starts("import web")
    assert state == "failed", f"the web app starting up left an orphaned sync {state!r}"


check("...while the web app starting up marks the same sync failed", web_app_fails_an_orphaned_sync)


def thread_rule():
    path = fresh_path()
    db.init_db(path)
    conn = db.connect(path)
    caught = []

    def elsewhere():
        try:
            conn.execute("SELECT 1")
        except sqlite3.ProgrammingError as exc:
            caught.append(exc)

    t = threading.Thread(target=elsewhere)
    t.start()
    t.join(timeout=10)
    conn.close()
    assert caught, "a connection was used from another thread without complaint"


check("a connection used from another thread raises ProgrammingError", thread_rule)


def read_during_write(path, reader_connect):
    """A writer thread takes the strongest write lock and holds it over three
    uncommitted rows while the main thread reads. That lock is what a writer
    holds at the moment of committing; BEGIN EXCLUSIVE forces it so the test
    does not depend on timing. Returns (read during the write, read after).
    """
    written, may_commit, committed = threading.Event(), threading.Event(), threading.Event()
    writer_errors = []

    def writer():
        w = sqlite3.connect(path)  # created inside this thread, per the rule
        try:
            w.execute("BEGIN EXCLUSIVE")
            for i in range(3):
                w.execute(
                    "INSERT INTO submissions (id, handle, problem_id, submitted_at)"
                    " VALUES (?, 'tourist', '1234A', 'x')",
                    (100 + i,),
                )
            written.set()
            may_commit.wait(timeout=10)
            w.commit()
        except Exception as exc:
            writer_errors.append(exc)
        finally:
            written.set()
            committed.set()
            w.close()

    t = threading.Thread(target=writer)
    t.start()
    written.wait(timeout=10)
    reader = reader_connect(path)
    try:
        try:
            during = reader.execute("SELECT count(*) FROM submissions").fetchone()[0]
        except sqlite3.OperationalError as exc:
            during = exc
        may_commit.set()
        committed.wait(timeout=10)
        after = reader.execute("SELECT count(*) FROM submissions").fetchone()[0]
    finally:
        reader.close()
        t.join(timeout=10)
    if writer_errors:
        raise AssertionError(f"writer failed: {writer_errors[0]}")
    return during, after


def wal_read_during_write():
    path = fresh_path()
    db.init_db(path)
    seed_path(path)
    during, after = read_during_write(path, db.connect)
    assert not isinstance(during, Exception), f"reader hit {during!r}"
    assert during == 0, f"reader saw {during} uncommitted rows"
    assert after == 3, f"reader saw {after} rows after the commit"


check("with WAL, a read during a write succeeds and sees 0 uncommitted rows", wal_read_during_write)


def rollback_journal_read_during_write():
    path = fresh_path()
    conn = sqlite3.connect(path)  # same schema, default journal mode, no WAL
    try:
        conn.executescript(db.SCHEMA_PATH.read_text(encoding="utf-8"))
    finally:
        conn.close()
    seed_path(path)
    during, _ = read_during_write(path, lambda p: sqlite3.connect(p, timeout=0.5))
    assert isinstance(during, sqlite3.OperationalError), f"expected 'database is locked', reader got {during!r}"
    assert "locked" in str(during), str(during)


check("...without WAL, the identical read fails with 'database is locked'", rollback_journal_read_during_write)


def timestamp_shape():
    ts = db.utc_now()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ts), ts


check("utc_now() has exactly the spec section 6 shape", timestamp_shape)

def api_sub(sub_id, index="A", name="Watermelon", rating=800, tags=("math",),
            verdict="OK", seconds=1600000000, contest_id=1234, participant="PRACTICE"):
    """One submission shaped the way the Codeforces API shapes them."""
    problem = {"index": index, "name": name, "tags": list(tags)}
    if contest_id is not None:
        problem["contestId"] = contest_id
    if rating is not None:
        problem["rating"] = rating
    sub = {"id": sub_id, "problem": problem, "creationTimeSeconds": seconds,
           "author": {"participantType": participant}}
    if verdict is not None:
        sub["verdict"] = verdict          # the API omits it while judging
    return sub


def synced_db():
    path = fresh_path()
    db.init_db(path)
    return path


print("\ndb.py queries")


def ids_and_times():
    assert db.problem_id({"contestId": 1234, "index": "A"}) == "1234A"
    assert db.problem_id({"contestId": 921, "index": "14"}) == "92114"
    assert db.problem_id({"problemsetName": "acmsguru", "index": "553"}) == "acmsguru553"
    try:
        db.problem_id({"index": "A", "name": "orphan"})
    except ValueError:
        pass
    else:
        raise AssertionError("a problem with neither field produced an id instead of raising")
    assert db.iso_from_unix(0) == "1970-01-01T00:00:00Z", db.iso_from_unix(0)


check("problem_id builds both forms and refuses to invent a third", ids_and_times)


def save_sync_writes_everything():
    path = synced_db()
    conn = db.connect(path)
    try:
        stored = db.save_sync(conn, "tourist", 3800, [api_sub(1), api_sub(2, verdict="WRONG_ANSWER")])
        assert stored == 2, stored
        user = db.get_user(conn, "tourist")
        assert user["last_synced"] is not None, "last_synced was not set"
        assert user["cf_rating"] == 3800
        assert conn.execute("SELECT count(*) FROM problems").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM problem_tags").fetchone()[0] == 1
        rows = db.get_submissions(conn, "tourist")
        assert [r["id"] for r in rows] == [2, 1], [dict(r) for r in rows]
        assert rows[0]["contest_id"] == 1234 and rows[0]["problem_index"] == "A"
    finally:
        conn.close()


check("save_sync stores user, problem, tags and submissions, newest first", save_sync_writes_everything)


def save_sync_is_repeatable():
    path = synced_db()
    conn = db.connect(path)
    try:
        db.save_sync(conn, "tourist", 3800, [api_sub(1, verdict=None, tags=("math", "greedy"))])
        first_seen = db.get_user(conn, "tourist")["first_seen"]

        # Second sync: the submission has now been judged, the problem has
        # been given a rating, and one tag was removed.
        stored = db.save_sync(
            conn, "tourist", 3900,
            [api_sub(1, verdict="OK", rating=1200, tags=("math",))],
        )
        assert stored == 1, f"expected no duplicate row, found {stored}"

        sub = db.get_submissions(conn, "tourist")[0]
        assert sub["verdict"] == "OK", f"verdict stayed {sub['verdict']!r}"
        assert sub["rating"] == 1200, f"rating stayed {sub['rating']!r}"

        tags = [r[0] for r in conn.execute("SELECT tag FROM problem_tags")]
        assert tags == ["math"], f"tags accumulated: {tags}"

        user = db.get_user(conn, "tourist")
        assert user["first_seen"] == first_seen, "first_seen moved on the second sync"
        assert user["cf_rating"] == 3900, "cf_rating was not updated"
    finally:
        conn.close()


check("syncing twice: no duplicates, verdict and rating updated, tags replaced, first_seen kept", save_sync_is_repeatable)


def different_casing_is_the_same_user():
    path = synced_db()
    conn = db.connect(path)
    try:
        db.save_sync(conn, "tourist", None, [api_sub(1)])
        db.save_sync(conn, "TOURIST", None, [api_sub(2)])
        n = conn.execute("SELECT count(*) FROM users").fetchone()[0]
        assert n == 1, f"expected one user row, found {n}"
    finally:
        conn.close()


check("the same handle in another casing updates one user, not two", different_casing_is_the_same_user)


def broken_submission_writes_nothing():
    path = synced_db()
    conn = db.connect(path)
    try:
        broken = api_sub(2, contest_id=None)          # and no problemsetName
        try:
            db.save_sync(conn, "tourist", None, [api_sub(1), broken])
        except ValueError:
            pass
        else:
            raise AssertionError("a submission with no usable problem id was accepted")
        assert db.get_user(conn, "tourist") is None, "a user row survived a failed sync"
        assert conn.execute("SELECT count(*) FROM submissions").fetchone()[0] == 0
    finally:
        conn.close()


check("one broken submission leaves the whole sync unwritten", broken_submission_writes_nothing)


def incomplete_user_returns_none():
    path = synced_db()
    conn = db.connect(path)
    try:
        assert db.get_submissions(conn, "nobody") is None, "unknown handle did not return None"

        # A user row with rows but no last_synced: what an interrupted sync
        # would leave behind if anything had been written.
        with conn:
            conn.execute("INSERT INTO users (handle, first_seen) VALUES ('half', ?)", (db.utc_now(),))
        assert db.get_submissions(conn, "half") is None, "incomplete user did not return None"

        db.save_sync(conn, "empty", None, [])
        assert db.get_submissions(conn, "empty") == [], "a synced user with no submissions should be []"
    finally:
        conn.close()


check("None for never-synced and half-synced, [] for synced with nothing", incomplete_user_returns_none)


def job_lifecycle():
    path = synced_db()
    conn = db.connect(path)
    try:
        job_id = db.create_job(conn, "sync", "tourist")
        assert db.get_active_job(conn, "sync", "tourist")["id"] == job_id

        try:
            db.create_job(conn, "sync", "tourist")
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("a second job for the same handle was created")

        db.start_job(conn, job_id)
        db.set_job_progress(conn, job_id, 300)
        assert db.get_job(conn, job_id)["state"] == "running"
        assert db.get_job(conn, job_id)["progress"] == 300

        db.finish_job(conn, job_id, error="Codeforces did not answer.")
        job = db.get_job(conn, job_id)
        assert job["state"] == "failed" and job["finished_at"] and job["error"]
        assert db.get_active_job(conn, "sync", "tourist") is None, "a finished job still counts as active"

        second = db.create_job(conn, "sync", "tourist")
        db.finish_job(conn, second)
        assert db.get_job(conn, second)["state"] == "done"
    finally:
        conn.close()


check("job lifecycle: one active at a time, retry after it finishes", job_lifecycle)


def job_record_survives_a_failed_sync():
    """ADR 0004: the failure record must outlive the rollback that caused it."""
    path = synced_db()
    conn = db.connect(path)
    try:
        job_id = db.create_job(conn, "sync", "tourist")
        db.start_job(conn, job_id)
        try:
            db.save_sync(conn, "tourist", None, [api_sub(1, contest_id=None)])
        except ValueError as exc:
            db.finish_job(conn, job_id, error=f"could not read a submission: {exc.__class__.__name__}")
        job = db.get_job(conn, job_id)
        assert job is not None, "the job row was rolled back with the sync"
        assert job["state"] == "failed", job["state"]
        assert db.get_user(conn, "tourist") is None, "the user was stored anyway"
    finally:
        conn.close()


check("a job's failure record survives the sync that rolled back", job_record_survives_a_failed_sync)


def job_target_ignores_casing():
    """Otherwise Tourist and tourist could sync at the same time, twice."""
    path = synced_db()
    conn = db.connect(path)
    try:
        db.create_job(conn, "sync", "tourist")
        assert db.get_active_job(conn, "sync", "TOURIST") is not None, "lookup missed another casing"
        try:
            db.create_job(conn, "sync", "Tourist")
        except sqlite3.IntegrityError:
            return
        raise AssertionError("a second job for the same handle in another casing was created")
    finally:
        conn.close()


check("jobs.target ignores casing too, so one handle cannot sync twice at once", job_target_ignores_casing)

shutil.rmtree(SCRATCH, ignore_errors=True)
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
