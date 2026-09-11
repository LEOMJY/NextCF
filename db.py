"""Database access for NextCF.

v0.2 scope so far: open a connection correctly, and create the database.

Every table, column and constraint lives in schema.sql, not here. This file
owns what is NOT a property of the schema:

    foreign key enforcement     per connection, and OFF unless switched on
    WAL journal mode            per database file, set once at startup
    rows readable by name       per connection
    the timestamp format        utc_now() -- the one shape from spec section 6

Deliberately not here yet:
    the queries sync.py and web.py need      next step, one function per need
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
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


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
