"""Database access for NextCF.

v0.2 scope so far: open a connection correctly, create the database, and
answer the questions web.py and sync.py actually ask of it -- one function per
question, and none written ahead of a caller that needs it.

Every table, column and constraint lives in schema.sql, not here. This file
owns what is NOT a property of the schema:

    foreign key enforcement     per connection, and OFF unless switched on
    WAL journal mode            per database file, set once at startup
    rows readable by name       per connection
    the timestamp format        utc_now(), iso_from_unix()
    how a problem id is built   problem_id()
    what "synced" means         get_submissions(), and only there
    ADR 0004's one transaction  save_sync(), which is why it is one function

Deliberately not here yet:
    calling init_db() when the app starts    with sync.py, when there is a use
    where the file lives in production       undecided -- spec section 7, due before v0.3

Usage:
    .venv\\Scripts\\python.exe db.py
    creates nextcf.db beside this file if it is missing, then reports what is in it
"""

import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Both paths are worked out from where THIS file is, not from wherever the
# program happened to be started. A bare "nextcf.db" would mean "in the current
# working directory" -- the repo root when web.py is run by hand, and whatever
# the host chose when it runs serve.py. Same reason web.py hands Flask __name__.
HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "schema.sql"

# Overridable from the environment, the way serve.py reads PORT, because where
# this file lives in production is undecided (spec section 7): a free Render
# instance wipes its disk on every redeploy, and the likely fix -- a mounted
# persistent disk -- appears at a different path. When that is decided it
# becomes a setting on the host, not a code change.
DB_PATH = Path(os.environ.get("NEXTCF_DB", HERE / "nextcf.db"))

# The one timestamp shape, from spec section 6. Two functions produce
# timestamps -- utc_now() for "now", iso_from_unix() for what the API sends --
# and they have to agree exactly, so the format is written once.
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def utc_now():
    """The current time, in the one timestamp format this database uses.

    ISO-8601, UTC, whole seconds, literal Z: "2026-09-11T14:03:00Z".
    Text sorts and compares correctly as time only if every row has exactly
    the same shape (spec section 6), so nothing should format a timestamp by
    hand. Call this.
    """
    # timezone.utc rather than datetime.utcnow(): utcnow() returns a time with
    # no timezone attached, which is deprecated because it is so easily
    # mistaken for local time.
    #
    # strftime pins the shape exactly. isoformat() would give
    # "2026-09-11T14:03:00.123456+00:00", and as text that sorts BEFORE
    # "2026-09-11T14:03:00Z" from the same second -- "." comes before "Z" --
    # so mixing the two silently breaks every ORDER BY on a time column.
    return datetime.now(timezone.utc).strftime(TIMESTAMP_FORMAT)


def connect(path=DB_PATH):
    """Open a connection, configured the way every caller needs it.

    ONE CONNECTION PER THREAD. Create it in the thread that uses it, close it
    when that thread is finished, and never keep one in a module-level
    variable for everyone to share. sqlite3 enforces this: a connection used
    from any thread but the one that created it raises ProgrammingError. That
    check is left on deliberately -- check_same_thread is not passed.

    `with conn:` wraps a transaction: commit if the block succeeds, roll back
    if it raises. It does NOT close the connection. Close it yourself:

        conn = db.connect()
        try:
            with conn:
                ...
        finally:
            conn.close()
    """
    # If another connection is partway through a write, wait up to 5 seconds
    # for it to finish before giving up with "database is locked". 5.0 is
    # sqlite3's default, written out so the number is visible here on the day
    # that error appears.
    conn = sqlite3.connect(path, timeout=5.0)

    # Rows come back usable by column name -- row["handle"] -- rather than as
    # bare tuples. With tuples, code says row[3], and quietly reads the wrong
    # column the day a column is added.
    conn.row_factory = sqlite3.Row

    # Without this, SQLite ignores every REFERENCES clause in schema.sql. It
    # has to be switched on again for every single connection. It must also
    # run before any transaction starts: inside one, SQLite treats it as a
    # no-op and does not say so. First thing after connecting, it is safe.
    conn.execute("PRAGMA foreign_keys = ON")

    # "Does not say so" is the reason for checking. A pragma SQLite does not
    # act on fails silently, and what it breaks is invisible: rows pointing at
    # users that do not exist, accepted without complaint. Asking costs one
    # query and turns that into a crash on the first connection.
    if conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
        conn.close()
        raise RuntimeError("SQLite did not enable foreign key enforcement")

    return conn


def init_db(path=DB_PATH):
    """Create the database if it is missing, and make it ready for work.

    Safe to call on every startup, and meant to be called exactly there:
    before any request is served and before any worker thread starts.

    Returns how many unfinished jobs it found and marked failed, so the
    caller can log it.
    """
    conn = connect(path)
    try:
        # Write-ahead logging. Without it, while the sync thread is writing,
        # the progress page cannot read -- and v0.2 creates exactly that
        # situation on purpose. With it, readers carry on, and see the
        # database as it was before the write began, never half of it.
        #
        # A property of the file, not of a connection, so it is set here once
        # rather than in connect(). SQLite answers with the mode actually in
        # effect, and a filesystem that cannot do WAL answers with the old
        # mode instead of raising -- so the answer is checked.
        mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
        if mode != "wal":
            raise RuntimeError(f"could not switch {path} to WAL mode (still {mode!r})")

        # Every statement in schema.sql is IF NOT EXISTS: this creates what is
        # missing and leaves an existing database, and its data, alone.
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

        # Orphaned jobs. This runs at startup, and there is only ever one
        # process (spec section 7), so no job can genuinely be in progress
        # right now. Anything unfinished belongs to a process that has died:
        # a redeploy, a crash, the host cycling the instance mid-sync.
        #
        # 'pending' as well as 'running' -- ADR 0004 originally named only
        # 'running'. A stale pending row is worse than untidy: the unique
        # index on jobs refuses a second unfinished job for the same handle,
        # so that user could never be synced again.
        #
        # CORRECT ONLY WHILE ONE PROGRAM USES THE DATABASE. Spec section 4
        # plans three programs on this one file -- the web app, collect.py and
        # scheduler.py -- and the web app never stops running. If either of
        # the others ran this while the web app was mid-sync, it would mark
        # that live sync failed. Before a second program touches the jobs
        # table (collect.py, v0.3), decide which program may run this cleanup:
        # spec section 12.
        with conn:
            cursor = conn.execute(
                """
                UPDATE jobs
                   SET state       = 'failed',
                       finished_at = ?,
                       error       = 'The server restarted before this job finished.'
                 WHERE state IN ('pending', 'running')
                """,
                (utc_now(),),
            )
        return cursor.rowcount
    finally:
        conn.close()


# --------------------------------------------------------------- conversions
#
# Both of these exist so that one rule lives in one place. Every timestamp in
# the database comes from this file, and every problem id is built by this
# file -- two callers formatting either by hand is two chances to format them
# differently, and the difference would not show up until a query quietly
# returned the wrong rows.


def iso_from_unix(seconds):
    """Codeforces' creationTimeSeconds -> the format utc_now() produces."""
    return datetime.fromtimestamp(seconds, timezone.utc).strftime(TIMESTAMP_FORMAT)


def problem_id(problem):
    """Build a problem's primary key from the API's problem object.

    Normally contestId + index ("1234A"). The acmsguru archive has no
    contestId, so those use problemsetName + index ("acmsguru553").

    Raises ValueError when an object has neither, rather than returning
    "None553" and storing a problem nothing can ever match again.
    """
    contest_id = problem.get("contestId")
    if contest_id is not None:
        return f"{contest_id}{problem['index']}"

    problemset = problem.get("problemsetName")
    if problemset:
        return f"{problemset}{problem['index']}"

    raise ValueError(f"problem has neither contestId nor problemsetName: {problem!r}")


# --------------------------------------------------------------------- reads
#
# Every one of these takes an open connection rather than making its own, so
# the caller keeps control of the thread rule and can put several calls in one
# transaction. Values always travel as ? placeholders, never formatted into
# the SQL -- the same reason web.py does not build HTML with f-strings.


def get_user(conn, handle):
    """One user's row, or None if this handle has never been seen.

    Serves the landing page's question -- do we already have this handle, and
    how old is it -- as well as the completeness check below.
    """
    # The columns are listed rather than SELECT *, so that adding a column to
    # the table later cannot silently change the shape of what callers get.
    return conn.execute(
        """
        SELECT handle, cf_rating, target_prob, first_seen, last_synced
          FROM users
         WHERE handle = ?
        """,
        (handle,),
    ).fetchone()


def get_submissions(conn, handle, limit=None):
    """One user's submissions, newest first, joined to their problems.

    THE RETURN VALUE HAS THREE CASES, and the difference matters:

        None  -- no usable data. Either the handle was never synced, or a sync
                 started and did not finish. Show the progress page, not a
                 table.
        []    -- synced successfully, and this user genuinely has no
                 submissions.
        rows  -- synced successfully, here they are.

    None versus [] is the same distinction as NULL versus 0 in the database:
    "not known" is not "none". This is the only place the completeness rule
    from ADR 0004 is enforced, which is why nothing else should query the
    submissions table directly.
    """
    user = get_user(conn, handle)
    if user is None or user["last_synced"] is None:
        return None

    # contest_id and problem_index come back as their own columns so the page
    # can build a Codeforces link without ever splitting the id -- see the
    # comment on problems.id in schema.sql.
    sql = """
        SELECT s.id, s.verdict, s.submitted_at, s.participant_type,
               p.id AS problem_id, p.contest_id, p.problem_index,
               p.name, p.rating
          FROM submissions s
          JOIN problems    p ON p.id = s.problem_id
         WHERE s.handle = ?
         ORDER BY s.submitted_at DESC, s.id DESC
    """
    params = [handle]
    if limit is not None:
        # The clause is added to the query text; the number still travels as a
        # placeholder. Assembling SQL is fine, pasting values into it is not.
        sql += " LIMIT ?"
        params.append(limit)

    return conn.execute(sql, params).fetchall()


def get_job(conn, job_id):
    """One job's row, or None. What /progress/<job> polls."""
    return conn.execute(
        """
        SELECT id, kind, target, state, progress, started_at, finished_at, error
          FROM jobs
         WHERE id = ?
        """,
        (job_id,),
    ).fetchone()


def get_active_job(conn, kind, target):
    """The unfinished job for this target, or None.

    Call this before create_job. The unique index on jobs allows only one
    unfinished job per target, so creating a second one raises -- and the
    right answer for a visitor whose handle is already syncing is to send them
    to the progress page of the job that is already running.
    """
    return conn.execute(
        """
        SELECT id, kind, target, state, progress, started_at, finished_at, error
          FROM jobs
         WHERE kind = ? AND target = ? AND state IN ('pending', 'running')
        """,
        (kind, target),
    ).fetchone()


# -------------------------------------------------------------- job bookkeeping
#
# EACH OF THESE COMMITS ON ITS OWN. Do not call them inside a `with conn:`
# block: leaving a nested `with conn:` commits the outer transaction too, so a
# progress update in the middle of a write would make half a user permanent --
# exactly what ADR 0004 exists to prevent.
#
# That separation is deliberate rather than accidental. A job's failure record
# has to survive the rollback that destroyed the work it was describing, so
# jobs are written outside the transaction that writes the user.


def create_job(conn, kind, target):
    """Record a new pending job and return its id.

    Raises sqlite3.IntegrityError if that target already has an unfinished
    job -- see get_active_job.
    """
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO jobs (kind, target, state, progress, started_at)
                 VALUES (?, ?, 'pending', 0, ?)
            """,
            (kind, target, utc_now()),
        )
    # lastrowid is the id SQLite assigned to the row just inserted, which for
    # an INTEGER PRIMARY KEY column is the value of that column.
    return cursor.lastrowid


def start_job(conn, job_id):
    """Mark a pending job as running."""
    with conn:
        conn.execute("UPDATE jobs SET state = 'running' WHERE id = ?", (job_id,))


def set_job_progress(conn, job_id, progress):
    """Record how many submissions have been fetched so far.

    This drives the progress page only. Under ADR 0004 an interrupted sync
    writes nothing, so this is not a position to resume from.
    """
    with conn:
        conn.execute("UPDATE jobs SET progress = ? WHERE id = ?", (progress, job_id))


def finish_job(conn, job_id, error=None):
    """Close a job out: done, or failed with a reason.

    `error` is shown to whoever is watching the progress page, so it should
    read as a sentence rather than as a stack trace.
    """
    with conn:
        conn.execute(
            "UPDATE jobs SET state = ?, finished_at = ?, error = ? WHERE id = ?",
            ("failed" if error else "done", utc_now(), error, job_id),
        )


# -------------------------------------------------------------------- the sync
#
# One function, because ADR 0004 is a promise about a transaction and the only
# way to keep it is to make the whole write one call that nothing can use
# halfway.


def save_sync(conn, handle, cf_rating, submissions):
    """Write one user's entire history in a single transaction. ADR 0004.

    `submissions` is the raw list from api_client.fetch_submissions -- the
    dicts Codeforces sent, not something pre-digested. Keeping the knowledge
    of which API fields are missing sometimes in one place was the plan from
    the 08-15 devlog entry, and this is that place.

    `handle` must be the spelling the API returned, not the one a visitor
    typed. COLLATE NOCASE makes the two match for lookups either way, but the
    stored spelling is the one pages display.

    `cf_rating` may be None: the API omits it for anyone who has never
    competed.

    Either everything here is stored or nothing is. Returns how many
    submission rows this user has afterwards.
    """
    now = utc_now()

    # Everything is shaped into rows BEFORE the transaction opens. A malformed
    # submission then raises before a single row is written, which is even
    # better than rolling one back, and it keeps the transaction as short as
    # possible -- a transaction is a lock, and a lock is time other threads
    # spend waiting.
    problems = {}
    tags = []
    rows = []
    for sub in submissions:
        problem = sub["problem"]
        pid = problem_id(problem)

        # The same problem appears on many of a user's submissions. A dict
        # keyed by id collapses those to one row each.
        if pid not in problems:
            problems[pid] = (
                pid,
                problem.get("contestId"),
                problem["index"],
                problem["name"],
                # Absent for unrated, very new, and gym problems.
                problem.get("rating"),
            )
            for tag in problem.get("tags", []):
                tags.append((pid, tag))

        rows.append(
            (
                sub["id"],
                handle,
                pid,
                # Absent while a submission is still being judged. NULL is the
                # honest value; "TESTING" is a display decision, and web.py
                # makes it.
                sub.get("verdict"),
                sub.get("author", {}).get("participantType"),
                iso_from_unix(sub["creationTimeSeconds"]),
            )
        )

    with conn:
        # excluded is SQLite's name for the row that the INSERT tried to add
        # and could not. So this reads: insert the user, or, if that handle is
        # already there, keep the row and update these two columns from what
        # we were about to insert. first_seen is deliberately not in the list
        # -- it means the first time, and a later sync must not move it.
        conn.execute(
            """
            INSERT INTO users (handle, cf_rating, first_seen, last_synced)
                 VALUES (?, ?, ?, ?)
            ON CONFLICT(handle) DO UPDATE SET cf_rating   = excluded.cf_rating,
                                              last_synced = excluded.last_synced
            """,
            (handle, cf_rating, now, now),
        )

        # Problems are updated, not ignored, because their facts change:
        # Codeforces assigns a rating to a new problem days or weeks after the
        # contest, and that rating is what the section 9 baseline is built on.
        conn.executemany(
            """
            INSERT INTO problems (id, contest_id, problem_index, name, rating)
                 VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET name   = excluded.name,
                                          rating = excluded.rating
            """,
            list(problems.values()),
        )

        # Tags are replaced rather than added to -- ADR 0005. Codeforces edits
        # tags, and inserting without deleting would accumulate every tag a
        # problem has ever had, with no way to tell the stale ones apart.
        conn.executemany(
            "DELETE FROM problem_tags WHERE problem_id = ?",
            [(pid,) for pid in problems],
        )
        conn.executemany("INSERT INTO problem_tags (problem_id, tag) VALUES (?, ?)", tags)

        # Codeforces' submission ids are stable, so re-syncing hits this
        # conflict for every submission already stored and no duplicate row is
        # ever created. Only the verdict is updated, because it is the only
        # field that changes: a submission fetched while it was still being
        # judged has no verdict, and a rejudge or a successful hack can change
        # one that was already there.
        conn.executemany(
            """
            INSERT INTO submissions (id, handle, problem_id, verdict,
                                     participant_type, submitted_at)
                 VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET verdict = excluded.verdict
            """,
            rows,
        )

        stored = conn.execute(
            "SELECT count(*) FROM submissions WHERE handle = ?", (handle,)
        ).fetchone()[0]

    return stored


def main():
    orphaned = init_db()

    conn = connect()
    try:
        print(f"database:      {DB_PATH}")
        print(f"journal mode:  {conn.execute('PRAGMA journal_mode').fetchone()[0]}")
        print(f"foreign keys:  {'on' if conn.execute('PRAGMA foreign_keys').fetchone()[0] else 'OFF'}")
        print(f"orphaned jobs: {orphaned} marked failed\n")

        # sqlite_master is SQLite's own table describing every table and index
        # in the file -- the schema, readable as ordinary rows.
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name")
        for row in tables.fetchall():
            name = row["name"]
            # The one place a value is formatted into SQL rather than passed as
            # a ? placeholder, and it has to be: placeholders stand in for
            # VALUES, never for table or column names. Safe here only because
            # the names come from sqlite_master, not from anybody outside.
            count = conn.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
            print(f"  {name:<14} {count} rows")
    finally:
        conn.close()

    return 0


# Runs only when this file is executed directly -- not when sync.py or web.py
# imports it. Same guard as api_client.py.
if __name__ == "__main__":
    sys.exit(main())
