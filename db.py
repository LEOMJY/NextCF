"""Database access for NextCF.

Open a connection correctly, create the database, and answer the questions
web.py, sync.py and collect.py actually ask of it -- one function per question,
and none written ahead of a caller that needs it. The same functions serve
both database files (ADR 0007); every one takes a path or a connection.

Every table, column and constraint lives in schema.sql, not here. This file
owns what is NOT a property of the schema:

    foreign key enforcement     per connection, and OFF unless switched on
    WAL journal mode            per database file, set once at startup
    rows readable by name       per connection
    the timestamp format        utc_now(), iso_from_unix()
    how a problem id is built   problem_id()
    what "synced" means         get_submissions(), and only there
    ADR 0004's one transaction  save_sync(), which is why it is one function
    the sample (ADR 0009)       save_draw(), next_candidate(), get_strata(), ...

Two startup functions, because they are safe for different programs:
    init_db()               any program, any time
    fail_orphaned_jobs()    the web app only, once, at startup -- ADR 0007

Usage:
    .venv\\Scripts\\python.exe db.py
    creates nextcf.db beside this file if it is missing, then reports what is in it
"""

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Both paths are worked out from where THIS file is, not from wherever the
# program happened to be started. A bare "nextcf.db" would mean "in the current
# working directory" -- the repo root when web.py is run by hand, and whatever
# the host chose when it runs serve.py. Same reason web.py hands Flask __name__.
HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "schema.sql"

# Overridable from the environment, the way serve.py reads PORT. On the free
# Render instance this file is a cache that is allowed to vanish: the instance
# loses its disk on every redeploy, restart and spin-down, and everything in
# here can be fetched again (ADR 0007). The day something stored here cannot be
# fetched again -- visit records, v0.7 -- it moves to storage that survives, at
# a different path, and that becomes a setting on the host, not a code change.
DB_PATH = Path(os.environ.get("NEXTCF_DB", HERE / "nextcf.db"))

# The one timestamp shape, from spec section 6. Two functions produce
# timestamps -- utc_now() for "now", iso_from_unix() for what the API sends --
# and they have to agree exactly, so the format is written once.
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# Codeforces numbers gym contests from 100000 up. Gym problems carry no rating
# and are never in the problemset, so they are outside the recommendation pool
# and outside the alias map (ADR 0010). 9.1% of the collected dataset's
# submissions are to them, which is why this needs a name rather than a bare
# 100000 repeated wherever the question comes up.
GYM_CONTEST_ID_FLOOR = 100000


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


def utc_ago(seconds):
    """The timestamp `seconds` ago, in the same shape as utc_now().

    For "is this older than ten minutes?". Because every timestamp in the
    database has one fixed shape, that question is a plain text comparison --
    no parsing, and SQLite can ask it inside a query. That is the payoff for
    the format decision in spec section 6.
    """
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).strftime(TIMESTAMP_FORMAT)


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

    Safe for ANY program to call, at any time, including while another
    program is using the same file: it creates what is missing and changes
    nothing that exists. Cleaning up abandoned jobs used to happen here too,
    and was not safe to share -- it is fail_orphaned_jobs() now.
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

        # ...which is also the limitation that makes the next line necessary.
        _migrate(conn)
    finally:
        conn.close()


def _migrate(conn):
    """Bring an existing database up to the current schema. Idempotent.

    A MIGRATION is a change to the structure of a database that already holds
    data, applied without rebuilding it from scratch. It is needed because of
    the sentence at the top of schema.sql: every statement there is
    IF NOT EXISTS, so it creates missing tables and indexes but does nothing
    at all to a table that already exists. A new column added to `problems` in
    schema.sql appears in a database created tomorrow and never appears in
    dataset.db, which holds 3.9 million rows nobody wants to collect twice.

    Each change below is guarded by a test of what the database currently
    looks like, so running this on an up-to-date file does nothing, and
    running it on a half-migrated file finishes the job. There is deliberately
    no schema_version counter: the guards ARE the version, they cannot
    disagree with reality, and a counter would be a second copy of the truth.
    When this grows long enough to be hard to read, that is the moment to
    replace it with numbered migration files -- not before.
    """
    # ADR 0010. ALTER TABLE ... ADD COLUMN is metadata only: SQLite records the
    # new column and its default and does not touch a single row, so this
    # returns instantly on a 680 MB file. NOT NULL is allowed here precisely
    # because there is a non-null DEFAULT for the existing rows to take.
    columns = {row[1] for row in conn.execute("PRAGMA table_info(problems)")}
    if "in_problemset" not in columns:
        with conn:
            conn.execute(
                "ALTER TABLE problems ADD COLUMN in_problemset INTEGER NOT NULL "
                "DEFAULT 0 CHECK (in_problemset IN (0, 1))"
            )


def fail_orphaned_jobs(path=DB_PATH):
    """Mark every unfinished job failed. ONLY the web app may call this.

    Call it once, when the web app starts, after init_db() and before any
    request is served. Returns how many jobs it marked, so the caller can log
    it.

    Why only the web app (ADR 0007): this is correct only when run by the
    program that starts jobs, at the moment that program starts. The web app
    is the only program that starts sync jobs, and when it starts, every sync
    thread from its previous run died with the old process -- a redeploy, a
    crash, the host restarting the instance. So anything unfinished is
    genuinely abandoned.

    Any OTHER program calling this has no such guarantee. If sync.py run by
    hand, or collect.py, called it while the web app was mid-sync, it would
    mark that live sync failed and tell the visitor the server had restarted
    when it had not. That is exactly what init_db() used to do to them.
    """
    conn = connect(path)
    try:
        # 'pending' as well as 'running' -- ADR 0004 originally named only
        # 'running'. A stale pending row is worse than untidy: the unique
        # index on jobs refuses a second unfinished job for the same handle,
        # so that user could never be synced again.
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


def count_submissions(conn, handle):
    """How many submissions are stored for this user.

    The results page shows only the newest hundred, and this is what lets it
    say "of 8,574" truthfully without fetching 8,574 rows in order to count
    them. Counting is the database's job and it is fast; loading rows to
    measure them is neither.
    """
    return conn.execute(
        "SELECT count(*) FROM submissions WHERE handle = ?", (handle,)
    ).fetchone()[0]


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


def save_sync(conn, handle, cf_rating, submissions, rating_changes=None):
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

    `rating_changes` is the raw list from api_client.fetch_rating_changes, or
    None when the caller did not fetch it. When given, it replaces this user's
    stored rating changes inside the same transaction, so in dataset.db a set
    last_synced means the history AND the rating changes are complete.

    Either everything here is stored or nothing is. Returns how many
    submission rows this user has afterwards.
    """
    now = utc_now()

    # Everything is shaped into rows BEFORE the transaction opens. A malformed
    # submission then raises before a single row is written, which is even
    # better than rolling one back, and it keeps the transaction as short as
    # possible -- a transaction is a lock, and a lock is time other threads
    # spend waiting.
    problems, tags = _shape_problems(sub["problem"] for sub in submissions)
    rows = [
        (
            sub["id"],
            handle,
            problem_id(sub["problem"]),
            # Absent while a submission is still being judged. NULL is the
            # honest value; "TESTING" is a display decision, and web.py
            # makes it.
            sub.get("verdict"),
            sub.get("author", {}).get("participantType"),
            iso_from_unix(sub["creationTimeSeconds"]),
        )
        for sub in submissions
    ]

    # Rating changes, when the caller fetched them -- collect.py does, a web
    # sync does not. [] means "fetched, and there are none"; None means "not
    # fetched", and leaves whatever is stored alone. Same distinction as
    # get_submissions' None and [].
    changes = None
    if rating_changes is not None:
        changes = [
            (
                handle,
                change["contestId"],
                change["rank"],
                change["oldRating"],
                change["newRating"],
                iso_from_unix(change["ratingUpdateTimeSeconds"]),
            )
            for change in rating_changes
        ]

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
        _write_problems(conn, problems, tags)

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

        # The whole history arrives every time, so replacing is exact: a
        # contest Codeforces later unrated disappears instead of lingering.
        if changes is not None:
            conn.execute("DELETE FROM rating_changes WHERE handle = ?", (handle,))
            conn.executemany(
                """
                INSERT INTO rating_changes (handle, contest_id, place,
                                            old_rating, new_rating, rated_at)
                     VALUES (?, ?, ?, ?, ?, ?)
                """,
                changes,
            )

        stored = conn.execute(
            "SELECT count(*) FROM submissions WHERE handle = ?", (handle,)
        ).fetchone()[0]

    return stored


def save_problemset(conn, problems):
    """Store the whole problemset, from api_client.fetch_problemset()["problems"].

    One transaction. Adds problems nobody has submitted to yet -- a sample's
    histories only ever mention problems someone in it tried, and a
    recommender needs the rest too. Returns (problems written, aliases built).

    Three things happen here and they are one transaction on purpose. The rows
    are written; `in_problemset` is cleared and re-set so it describes THIS
    fetch and not an older one; and the alias map is rebuilt from the result.
    An alias map is only meaningful against the membership it was built from,
    so there must be no moment at which a reader can see one without the
    other -- ADR 0010.
    """
    shaped, tags = _shape_problems(problems)
    with conn:
        _write_problems(conn, shaped, tags)

        # Membership is a snapshot, like a rating: a contest can be removed
        # and take its problems out of the problemset. Clearing first is what
        # makes this a replacement rather than an accumulation -- the same
        # shape as ADR 0005's rule for tags. Without the clear, an id that
        # left the problemset in March would still be offered as a
        # recommendation today.
        conn.execute("UPDATE problems SET in_problemset = 0 WHERE in_problemset = 1")
        conn.executemany(
            "UPDATE problems SET in_problemset = 1 WHERE id = ?",
            [(pid,) for pid in shaped],
        )
        aliases = _rebuild_aliases(conn)
    return len(shaped), aliases


def rebuild_aliases(conn):
    """Rebuild the alias map on its own, in its own transaction.

    save_problemset() already does this, and that is the normal path. This
    exists for the check that rebuilds the map and compares it against the
    independent method in ADR 0010, and for a database whose problemset
    membership is already correct.
    """
    with conn:
        return _rebuild_aliases(conn)


def _rebuild_aliases(conn):
    """Replace problem_aliases from the problems table. Call inside a transaction.

    Method B of ADR 0010: an id the problemset does not list is an alias of a
    listed problem when they share a name and a rating AND exactly one listed
    problem matches. 1,527 of the 1,680 unlisted contest ids in the collected
    dataset, 91%.

    The "exactly one" is the whole safety argument. The problemset holds three
    different problems called "Game" rated 800, and seven called "Elections";
    when a group is ambiguous this produces NO row rather than a wrong one.
    56 of 11,044 (name, rating) pairs in the problemset are ambiguous that way.

    Excluded, and each for its own reason:
      rating IS NULL   -- nothing to match on, and NULL = NULL is never true
                          in SQL anyway, so this is documentation as much as a
                          filter
      contest_id NULL  -- acmsguru; problemset.problems returns none of it, so
                          there is no listed copy for one to point at
      contest_id big   -- gym, which is never in the problemset either

    Returns how many aliases were written.
    """
    # Rebuilt whole rather than updated. The inputs -- names, ratings,
    # membership -- can all change under us, so a row that was right last
    # month can be wrong now, and there is no way to tell which ones from the
    # map alone. 1,500 rows is nothing to rewrite.
    conn.execute("DELETE FROM problem_aliases")

    # The subquery appears twice: once to prove there is exactly one candidate,
    # once to fetch it. Written this way rather than as a GROUP BY with a bare
    # column, which SQLite allows and which would do the same thing by a rule
    # most readers would have to look up. idx_problems_name_rating is what
    # keeps both cheap.
    cursor = conn.execute(
        """
        INSERT INTO problem_aliases (alias_id, canonical_id)
        SELECT a.id,
               (SELECT c.id FROM problems c
                 WHERE c.in_problemset = 1
                   AND c.name = a.name
                   AND c.rating = a.rating)
          FROM problems a
         WHERE a.in_problemset = 0
           AND a.rating IS NOT NULL
           AND a.contest_id IS NOT NULL
           AND a.contest_id < ?
           AND (SELECT COUNT(*) FROM problems c
                 WHERE c.in_problemset = 1
                   AND c.name = a.name
                   AND c.rating = a.rating) = 1
        """,
        (GYM_CONTEST_ID_FLOOR,),
    )
    return cursor.rowcount


def _shape_problems(problem_dicts):
    """API problem objects -> (rows keyed by id, (id, tag) pairs). No writing.

    Shared by save_sync and save_problemset so there is one definition of how
    a problem becomes a row. The underscore marks it as private to this file:
    callers outside db.py should never need it.
    """
    problems = {}
    tags = []
    for problem in problem_dicts:
        pid = problem_id(problem)

        # The same problem appears on many of a user's submissions. A dict
        # keyed by id collapses those to one row each.
        if pid in problems:
            continue
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
    return problems, tags


def _write_problems(conn, problems, tags):
    """Upsert problems and replace their tags. Call inside a transaction."""
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


# ------------------------------------------------------------------ the sample
#
# collect.py decides who is drawn (ADR 0009). These only store and read it.


def save_draw(conn, seed, source, source_fetched_at, rating_min, rating_max,
              stratum_width, per_stratum, candidates):
    """Record a draw and its whole ordered candidate list, in one transaction.

    `candidates` is (stratum, position, handle, rating_when_drawn) tuples.
    Returns the new sample's id.
    """
    with conn:
        cursor = conn.execute(
            """
            INSERT INTO samples (seed, source, source_fetched_at, rating_min,
                                 rating_max, stratum_width, per_stratum)
                 VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (seed, source, source_fetched_at, rating_min, rating_max, stratum_width, per_stratum),
        )
        sample_id = cursor.lastrowid
        conn.executemany(
            """
            INSERT INTO sample_candidates (sample_id, stratum, position, handle, rating_when_drawn)
                 VALUES (?, ?, ?, ?, ?)
            """,
            [(sample_id, *candidate) for candidate in candidates],
        )
    return sample_id


def get_sample(conn):
    """The one sample in this database, or None if nothing has been drawn."""
    return conn.execute(
        """
        SELECT id, seed, source, source_fetched_at, rating_min, rating_max,
               stratum_width, per_stratum
          FROM samples
         ORDER BY id
         LIMIT 1
        """
    ).fetchone()


def raise_per_stratum(conn, sample_id, new_per_stratum):
    """Raise a sample's per_stratum and record the change, in one transaction.

    Returns the old value. collect.extend() decides whether the new number is
    allowed; sample_size_changes' CHECK refuses a decrease regardless.
    """
    with conn:
        old = conn.execute(
            "SELECT per_stratum FROM samples WHERE id = ?", (sample_id,)
        ).fetchone()[0]
        conn.execute(
            """
            INSERT INTO sample_size_changes (sample_id, changed_at, old_per_stratum, new_per_stratum)
                 VALUES (?, ?, ?, ?)
            """,
            (sample_id, utc_now(), old, new_per_stratum),
        )
        conn.execute(
            "UPDATE samples SET per_stratum = ? WHERE id = ?", (new_per_stratum, sample_id)
        )
    return old


def get_strata(conn, sample_id):
    """Per stratum: population, wanted, collected, unavailable. Lowest first."""
    return conn.execute(
        """
        SELECT stratum, population, wanted, collected, unavailable
          FROM sample_strata
         WHERE sample_id = ?
         ORDER BY stratum
        """,
        (sample_id,),
    ).fetchall()


def next_candidate(conn, sample_id, stratum):
    """The first candidate in this stratum not yet collected and not known to
    be unavailable, or None when the stratum has run out of candidates.

    "Collected" is read from users.last_synced, so a user whose save rolled
    back (ADR 0004) is still next in line -- which is exactly what resuming
    after a stop needs.
    """
    return conn.execute(
        """
        SELECT c.handle, c.position, c.rating_when_drawn
          FROM sample_candidates c
          LEFT JOIN users u ON u.handle = c.handle AND u.last_synced IS NOT NULL
         WHERE c.sample_id = ? AND c.stratum = ?
           AND c.unavailable IS NULL
           AND u.handle IS NULL
         ORDER BY c.position
         LIMIT 1
        """,
        (sample_id, stratum),
    ).fetchone()


def mark_unavailable(conn, sample_id, handle, reason):
    """Record that Codeforces will not give us this candidate, and why.

    Only for answers that will not change -- a handle that no longer exists.
    Never for a network failure: that would turn a bad connection into a
    permanently skipped user.
    """
    with conn:
        conn.execute(
            "UPDATE sample_candidates SET unavailable = ? WHERE sample_id = ? AND handle = ?",
            (reason, sample_id, handle),
        )


def main():
    # init_db() only. This is a program run by hand, possibly while the web app
    # is running on the same file, so it reports unfinished jobs and does not
    # touch them -- see fail_orphaned_jobs().
    init_db()

    conn = connect()
    try:
        unfinished = conn.execute(
            "SELECT count(*) FROM jobs WHERE state IN ('pending', 'running')"
        ).fetchone()[0]
        print(f"database:        {DB_PATH}")
        print(f"journal mode:    {conn.execute('PRAGMA journal_mode').fetchone()[0]}")
        print(f"foreign keys:    {'on' if conn.execute('PRAGMA foreign_keys').fetchone()[0] else 'OFF'}")
        print(f"unfinished jobs: {unfinished} (left alone; only the web app cleans these up)\n")

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
