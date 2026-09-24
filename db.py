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


def _names_from(variable):
    """A comma-separated setting from the environment, blanks dropped."""
    return tuple(part.strip() for part in os.environ.get(variable, "").split(",") if part.strip())


# Spec section 9 counts 50 people **who are not the author**. Who the author is
# is a setting on the host rather than a fact about the software, the same way
# DB_PATH is: the author's own handles, and the random visitor ids in the
# author's browsers (read one out of the cookie, or out of a visits row).
#
#     NEXTCF_AUTHOR_HANDLES=some_handle,another
#     NEXTCF_AUTHOR_VISITORS=Xq2f...,b7Lp...
AUTHOR_HANDLES = _names_from("NEXTCF_AUTHOR_HANDLES")
AUTHOR_VISITORS = _names_from("NEXTCF_AUTHOR_VISITORS")

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


def has_complete_data(conn, handle):
    """Is this handle's stored history known to be a WHOLE history? ADR 0004.

    False means "no usable data", and it covers two situations the caller must
    not tell apart: never synced, and a sync that started and did not finish.
    Both leave last_synced NULL, which is written inside the same transaction
    as the rows themselves, so it cannot drift out of step with them.

    Every function that reads the submissions table asks this first. That is
    the whole defence: the failure ADR 0004 exists to prevent is not missing
    rows, it is missing rows that LOOK complete, and it only takes one reader
    that forgot to ask.
    """
    user = get_user(conn, handle)
    return user is not None and user["last_synced"] is not None


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
    "not known" is not "none". ADR 0004's completeness rule is enforced by
    has_complete_data() below, which every reader of the submissions table goes
    through, and which is why nothing else should query that table directly.
    """
    if not has_complete_data(conn, handle):
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


# ------------------------------------------------------- the topic breakdown
#
# One user's practice history collapsed from submissions to PROBLEMS, which is
# the unit everything below counts in. Three wrong answers and an accepted one
# are four submissions and one problem, and nobody has solved a topic four
# times by failing it three times first.
#
# Written once and shared by the two queries under it, because they have to
# agree. If one folded aliases and the other did not, a page could show 40
# problems solved and topic bars adding to 43, and the only clue would be
# arithmetic that nearly works.
#
# COALESCE returns its first argument that is not NULL. The LEFT JOIN supplies
# a canonical id when this problem is an alias of another and NULL when it is
# not, so this reads: the problemset's id for this problem, or its own if the
# problemset lists it. That is what makes a Div. 2 contestant's 1293C and a
# Div. 1 contestant's 1292A one problem and not two -- ADR 0010.
#
# MAX over a CASE is "did ANY submission on this problem get accepted". The
# CASE rather than `verdict = 'OK'` because a submission still being judged has
# verdict NULL, and NULL = 'OK' is NULL, not 0 -- MAX would then skip the row
# instead of counting it as unsolved.
_MY_PROBLEMS = """
    WITH mine AS (
        SELECT COALESCE(a.canonical_id, s.problem_id)      AS canonical_id,
               MAX(CASE WHEN s.verdict = 'OK' THEN 1 ELSE 0 END) AS solved
          FROM submissions s
          LEFT JOIN problem_aliases a ON a.alias_id = s.problem_id
         WHERE s.handle = ?
         GROUP BY COALESCE(a.canonical_id, s.problem_id)
    )
"""


def topic_breakdown(conn, handle):
    """Per-topic practice for one user. None if there is no usable data.

    Rows of (tag, solved, attempted, rated_solved, mean_solved_rating), the
    most-solved topic first.

    THE TAGS COME FROM THE CANONICAL PROBLEM, never from the alias -- ADR
    0010. Codeforces tags the two copies of a shared problem differently:
    1292A is data structures, dsu, implementation; 1293C, which is the same
    problem, is constructive algorithms, implementation. Three quarters of the
    alias pairs in the dataset disagree like that, so until now the topic a
    solve was filed under depended on which division the solver was in. The
    alias's own tag rows stay in the table and are simply never joined to.

    A problem carries about three tags and counts once under each, so these
    numbers add up to more than the user's problem count -- see
    problem_totals(). Correct, and not obvious, so a page showing this has to
    say so.

    **`attempted` is here for completeness, not as a weakness signal.** The
    plan was that the gap between solved and attempted would show where
    somebody is struggling. Measured across the whole dataset, it does not:
    of 1,817,020 (user, problem) pairs ever attempted, 1,701,748 were
    eventually solved -- 93.7%. Competitive programmers mostly submit when
    they believe they are right and then keep going until the problem falls,
    so the ratio sits near 95% for nearly every user and nearly every topic,
    and a number that is always 95% distinguishes nobody. It stays because
    "0 of 30" and "0 of 0" are genuinely different and it costs nothing to
    keep, not because a chart should be built on it.

    **The difficulty columns are the ones that carry information.** For one
    1718-rated user, the mean rating of solved problems runs from about 1800
    in trees and 1700 in graphs down to 1300 in implementation -- a 400-point
    spread where the solve ratio spread was four points.

    Mean rather than median: SQLite has no median, working one out needs
    either a window function or a second pass in Python, and problem ratings
    are bounded and roughly symmetric within one user's range, which is
    exactly the case where the two agree. (The 09-15 devlog entry's warning
    about means is about heavy-tailed data, like submissions per user. This is
    not that.)

    `rated_solved` is how many solves that mean rests on, and it is separate
    because a third of the problemset has no rating at all. A mean over three
    problems is not the same claim as a mean over three hundred, and the two
    must not look alike in a chart.

    **What this is NOT: a skill estimate,** and the difference matters enough
    to be spelled out. These are facts about a history, not about a person.
    Worse, the per-topic means cannot be compared with each other as they
    stand: tree problems are rated higher than implementation problems for
    everybody, so a higher mean in trees may say something about trees rather
    than about this user. Removing that confound -- asking how far up each
    topic's OWN difficulty range this user has climbed, relative to people
    like them -- is the whole job of model.py at v0.6. This function is the
    input it starts from, and the chart built on it at v0.4 has to describe
    practice rather than claim skill.
    """
    if not has_complete_data(conn, handle):
        return None

    # AVG and COUNT both skip NULL, so the CASE does two jobs at once: it
    # drops unsolved problems, and it drops solved ones Codeforces has never
    # rated. What is left is "the rated problems this user actually solved",
    # which is the only set either number should describe.
    return conn.execute(
        _MY_PROBLEMS + """
        SELECT t.tag,
               SUM(m.solved)                                 AS solved,
               COUNT(*)                                      AS attempted,
               COUNT(CASE WHEN m.solved = 1 THEN p.rating END) AS rated_solved,
               AVG(CASE WHEN m.solved = 1 THEN p.rating END)   AS mean_solved_rating
          FROM mine m
          JOIN problem_tags t ON t.problem_id = m.canonical_id
          JOIN problems     p ON p.id         = m.canonical_id
         GROUP BY t.tag
         ORDER BY solved DESC, attempted DESC, t.tag
        """,
        (handle,),
    ).fetchall()


def problem_totals(conn, handle):
    """(solved, attempted, solved_untagged) for one user. None if not synced.

    Not derivable from topic_breakdown(): a problem with three tags appears in
    three of its rows, so summing that column counts it three times. These are
    distinct problems, which is the number a page can put next to the chart
    without lying.

    `solved_untagged` is the third number because it explains a gap somebody
    will otherwise find by hand. A solved problem with no tags at all is in no
    topic bar, so the bars can never account for it. In the collected dataset
    these are almost entirely gym problems: 16,874 gym problems and 92 of them
    tagged. Gym is deliberately included here -- it is practice the user
    really did -- even though it is outside the recommendation pool, because
    "what you have done" and "what to do next" are different questions.
    """
    if not has_complete_data(conn, handle):
        return None

    return conn.execute(
        _MY_PROBLEMS + """
        SELECT SUM(m.solved) AS solved,
               COUNT(*)      AS attempted,
               SUM(CASE WHEN m.solved = 1
                         AND NOT EXISTS (SELECT 1 FROM problem_tags t
                                          WHERE t.problem_id = m.canonical_id)
                        THEN 1 ELSE 0 END) AS solved_untagged
          FROM mine m
        """,
        (handle,),
    ).fetchone()


# ------------------------------------------------------------ recommendations

def problemset_size(conn):
    """How many problems the problemset lists here. 0 until one is fetched.

    The web app fetches the problemset in a thread when it starts (ADR 0010),
    so for the first few seconds after a start -- and for as long as a failed
    fetch stays failed -- this is 0 and there is nothing to recommend from.
    The results page asks this rather than guessing from an empty pool,
    because an empty pool also happens to somebody who has solved everything,
    and the two need different sentences.
    """
    return conn.execute(
        "SELECT count(*) FROM problems WHERE in_problemset = 1"
    ).fetchone()[0]


def recommendation_pool(conn, handle):
    """Every problem this user could be recommended. None if not synced.

    Problemset problems that have a rating, minus the ones this user has
    solved. 11,102 rows before the subtraction; model.recommend() scores all
    of them, which is a few milliseconds of arithmetic.

    Solved is decided on CANONICAL ids -- ADR 0010. Without that fold, a Div. 2
    contestant who solved 1293C would be recommended 1292A, which is the same
    problem, and 3,360 of the 4,000 users in the dataset have at least one
    solve that only the fold can see.

    Attempted-and-failed problems stay in the pool on purpose. "You tried this
    and it beat you" is not a reason never to suggest it again, and whether it
    should be suggested SOONER or LATER is a question for a model that knows
    about time, which is v2.0 (spec section 11, knowledge tracing).

    Only rated problems, because the baseline's whole input is the rating; a
    problem without one cannot be given a probability, and showing it with a
    made-up one would be worse than leaving it out.

    NOT IN with a subquery is safe here only because the subquery can never
    produce NULL -- COALESCE falls back to s.problem_id, which is NOT NULL.
    If it ever could, `x NOT IN (..., NULL)` is NULL rather than true for
    every x, and the pool would silently come back empty.
    """
    if not has_complete_data(conn, handle):
        return None

    return conn.execute(
        """
        SELECT p.id, p.contest_id, p.problem_index, p.name, p.rating
          FROM problems p
         WHERE p.in_problemset = 1
           AND p.rating IS NOT NULL
           AND p.id NOT IN (
                 SELECT COALESCE(a.canonical_id, s.problem_id)
                   FROM submissions s
                   LEFT JOIN problem_aliases a ON a.alias_id = s.problem_id
                  WHERE s.handle = ?
                    AND s.verdict = 'OK')
        """,
        (handle,),
    ).fetchall()


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


def claim_job(conn, job_id):
    """Take a pending job, if nobody else has it. True if this caller got it.

    One statement, so the test and the claim cannot come apart. A read
    followed by a write leaves a gap in which two runners both see 'pending',
    both start, and the same user is fetched twice -- which on a rate-limited
    API means everybody queued behind them waits twice as long.

    Inside the web app that race is not reachable: ADR 0018 runs one worker
    thread. What makes this a statement rather than a rule somebody has to
    remember is sync.py run by hand, which is a second process on the same
    file, and now loses the claim instead of duplicating the work.

    Was start_job(), which set the state unconditionally and told the caller
    nothing.
    """
    with conn:
        cursor = conn.execute(
            "UPDATE jobs SET state = 'running' WHERE id = ? AND state = 'pending'",
            (job_id,),
        )
    return cursor.rowcount == 1


def next_pending_job(conn, kind="sync"):
    """The oldest job still waiting, or None. ADR 0018's queue.

    Oldest by id, because id IS the arrival order: SQLite hands out increasing
    integer keys, so nothing has to be ordered by a timestamp that two rows
    created in the same second could share.
    """
    return conn.execute(
        """
        SELECT id, kind, target, state, progress, started_at, finished_at, error
          FROM jobs
         WHERE kind = ? AND state = 'pending'
         ORDER BY id
         LIMIT 1
        """,
        (kind,),
    ).fetchone()


def recent_failed_job(conn, kind, target, since):
    """The last failed job for this target, if it failed after `since`.

    What stops one mistyped character costing two API requests and a
    four-second wait on every reload, out of a queue everybody shares: the
    answer is already on disk, so it is given back instead of fetched again.
    Newest first, because a handle can fail, be created, and succeed.
    """
    return conn.execute(
        """
        SELECT id, kind, target, state, progress, started_at, finished_at, error
          FROM jobs
         WHERE kind = ? AND target = ? AND state = 'failed'
           AND finished_at >= ?
         ORDER BY id DESC
         LIMIT 1
        """,
        (kind, target, since),
    ).fetchone()


def count_unfinished_jobs(conn, kind="sync"):
    """How many jobs are waiting or running. What the scheduler asks before
    adding work of its own: a visitor waiting for their first page comes
    before keeping somebody else's history warm (ADR 0020)."""
    return conn.execute(
        "SELECT count(*) FROM jobs WHERE kind = ? AND state IN ('pending', 'running')",
        (kind,),
    ).fetchone()[0]


def next_user_to_refresh(conn, seen_since, synced_before):
    """The handle most in need of a nightly refresh, or None. ADR 0020.

    "Seen" means somebody opened a page for that handle, from the visits
    table -- the people who come back are the ones worth keeping fresh, and
    they are exactly who section 9 counts. "In need" means their stored
    history is older than the caller's cutoff, oldest first.

    Deliberately asks the database rather than remembering a schedule. This
    process restarts several times a day on the free instance, so a plan kept
    in memory would either be repeated on every restart or lost with it;
    rows that are already on disk cannot forget.
    """
    row = conn.execute(
        """
        SELECT u.handle
          FROM users u
         WHERE u.last_synced IS NOT NULL
           AND u.last_synced < ?
           AND u.handle IN (SELECT handle FROM visits
                             WHERE handle IS NOT NULL AND visited_at >= ?)
         ORDER BY u.last_synced
         LIMIT 1
        """,
        (synced_before, seen_since),
    ).fetchone()
    return row["handle"] if row is not None else None


def jobs_ahead(conn, job_id):
    """How many unfinished jobs were asked for before this one.

    What the progress page turns into "you are 7th in the queue". Under ADR
    0018 syncs run one at a time in id order, so this is exactly how many have
    to finish first: 0 means this job is running now, or is next.

    It is only a number anybody can quote BECAUSE they run one at a time.
    While every sync ran in its own thread and the rate limiter interleaved
    their requests, everybody finished at the end together and there was no
    such thing as a position.
    """
    return conn.execute(
        """
        SELECT count(*)
          FROM jobs
         WHERE state IN ('pending', 'running')
           AND id < ?
        """,
        (job_id,),
    ).fetchone()[0]


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


# ------------------------------------------------------------------- visits
#
# Spec section 9's second criterion -- 50 people who are not the author have
# used it, and 20 of them came back -- is the one number that cannot be worked
# out later from anything else. Every other number in this project can be
# recomputed from data Codeforces still has; a visit that was not written down
# is simply gone. That is why these two functions exist before there is
# anybody to count (ADR 0017).


def record_visit(conn, visitor_id, handle, path):
    """Write one row: somebody opened this page.

    Commits on its own, like the job functions above and for the same reason.
    A visit is not part of whatever else the request is doing, and it must
    neither be rolled back with it nor commit it early.

    `handle` is the handle whose page this is, or None for a page that looks
    nothing up. `visitor_id` is the random cookie value, or None if the
    browser kept none.
    """
    with conn:
        conn.execute(
            """
            INSERT INTO visits (visitor_id, handle, path, visited_at)
                 VALUES (?, ?, ?, ?)
            """,
            (visitor_id, handle, path, utc_now()),
        )


def visit_counts(conn, exclude_handles=(), exclude_visitors=()):
    """Section 9's second criterion, counted both ways it can be counted.

    Returns a dict:

        people            distinct cookie ids
        returned          those seen on two or more different days
        used              those who looked a handle up, not only read
        handles           distinct handles looked up
        handles_returned  handles looked up on two or more different days
        visits            rows counted
        without_cookie    rows from a browser that kept no cookie

    THE TWO COUNTS BRACKET THE TRUTH, and neither is it. A browser that
    refuses cookies gets a new id on every visit, so `people` counts that
    person once per visit -- too many. `handles` misses everybody who read the
    landing page and left, and merges two people who look up the same handle
    -- too few. Report both, and say which one a claim about section 9 uses.

    "A different day" is `substr(visited_at, 1, 10)`, which is only a
    legitimate way to ask that because every timestamp in this database has
    one fixed shape (spec section 6). UTC days, not the visitor's.

    Exclusions are section 9's words: 50 people **who are not the author**.
    Both lists come from the host's configuration rather than from the code,
    because who the author is is not a fact about the software.
    """
    handles = tuple(exclude_handles)
    visitors = tuple(exclude_visitors)

    conditions = []
    parameters = []
    if handles:
        # Placeholders are generated, the values are still bound: the only
        # thing formatted into the SQL is the number of question marks.
        marks = ", ".join("?" for _ in handles)
        conditions.append(f"(handle IS NULL OR handle NOT IN ({marks}))")
        parameters.extend(handles)
    if visitors:
        marks = ", ".join("?" for _ in visitors)
        conditions.append(f"(visitor_id IS NULL OR visitor_id NOT IN ({marks}))")
        parameters.extend(visitors)
    where = " AND ".join(conditions) if conditions else "1 = 1"

    # The CTE holds the rows that count; the placeholders appear once, inside
    # it, so the parameters are bound once however many times it is read.
    # count(DISTINCT x) ignores NULLs, which is what makes the cookie-less
    # rows fall out of `people` on their own.
    row = conn.execute(
        f"""
        WITH counted AS (SELECT * FROM visits WHERE {where})
        SELECT
          (SELECT count(DISTINCT visitor_id) FROM counted) AS people,
          (SELECT count(*) FROM (SELECT visitor_id FROM counted
                                  WHERE visitor_id IS NOT NULL
                                  GROUP BY visitor_id
                                 HAVING count(DISTINCT substr(visited_at, 1, 10)) > 1
                                )) AS returned,
          (SELECT count(DISTINCT visitor_id) FROM counted
            WHERE handle IS NOT NULL) AS used,
          (SELECT count(DISTINCT handle) FROM counted) AS handles,
          (SELECT count(*) FROM (SELECT handle FROM counted
                                  WHERE handle IS NOT NULL
                                  GROUP BY handle
                                 HAVING count(DISTINCT substr(visited_at, 1, 10)) > 1
                                )) AS handles_returned,
          (SELECT count(*) FROM counted) AS visits,
          (SELECT count(*) FROM counted WHERE visitor_id IS NULL) AS without_cookie
        """,
        parameters,
    ).fetchone()
    return dict(row)


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

        # Section 9's second criterion, from this file. On the server this is
        # the number the whole storage decision exists to protect (ADR 0017);
        # here it mostly says whether the recording works at all.
        counts = visit_counts(conn, AUTHOR_HANDLES, AUTHOR_VISITORS)
        print("\nvisits, the author excluded (spec section 9):")
        print(f"  people (by cookie)  {counts['people']}, of whom {counts['returned']} came back on another day")
        print(f"  looked a handle up  {counts['used']}")
        print(f"  handles (by name)   {counts['handles']}, of whom {counts['handles_returned']} on another day")
        print(f"  page views          {counts['visits']}, {counts['without_cookie']} from browsers keeping no cookie")
        if not AUTHOR_HANDLES and not AUTHOR_VISITORS:
            print("  (nobody is excluded yet: set NEXTCF_AUTHOR_HANDLES and NEXTCF_AUTHOR_VISITORS)")
    finally:
        conn.close()

    return 0


# Runs only when this file is executed directly -- not when sync.py or web.py
# imports it. Same guard as api_client.py.
if __name__ == "__main__":
    sys.exit(main())
