-- NextCF database schema.
--
-- Five tables, per spec section 6. Run once at startup via db.py's init_db();
-- every statement is IF NOT EXISTS, so running it again is harmless.
--
-- Two settings that are NOT here, because they belong to the connection
-- rather than to the schema, and live in db.py:
--     PRAGMA foreign_keys = ON    -- off by default, and per connection.
--                                    Without it every REFERENCES clause below
--                                    is decorative and enforces nothing.
--     PRAGMA journal_mode = WAL   -- lets the progress page read while the
--                                    sync thread writes. Without it one
--                                    blocks the other and raises
--                                    "database is locked".
--
-- STRICT on every table: without it SQLite treats column types as
-- suggestions and will happily store the text "banana" in an INTEGER column.
-- STRICT makes that an error. Needs SQLite 3.37+; this machine has 3.50.4.
--
-- STRICT also makes PRIMARY KEY columns implicitly NOT NULL, which plain
-- SQLite does not do -- a legacy quirk where a TEXT PRIMARY KEY can be NULL.


-- Everyone whose history has been fetched. A handle is the only identity the
-- product has (spec section 5: no accounts).
CREATE TABLE IF NOT EXISTS users (
    -- COLLATE NOCASE is load-bearing, not tidiness. Codeforces handles are
    -- case-insensitive for lookup, so without this "Tourist" and "tourist"
    -- become two rows holding two disjoint submission sets -- one person
    -- counted twice, silently, inside the section 9 dataset. NOCASE makes
    -- the database treat them as one key, so the second insert is caught.
    handle       TEXT    PRIMARY KEY COLLATE NOCASE,

    -- Absent for users who have never competed, so nullable. NULL means "not
    -- known", which is not the same as 0.
    cf_rating    INTEGER,

    -- Difficulty target from spec section 1. Nothing sets it before v0.4, so
    -- it is 0.70 on every row until then.
    target_prob  REAL    NOT NULL DEFAULT 0.70,

    -- ISO-8601 UTC text, e.g. "2026-09-09T14:03:00Z". SQLite has no date
    -- type; spec section 6 has the reasoning for text over integer seconds.
    first_seen   TEXT    NOT NULL,

    -- THE COMPLETENESS FLAG, and the reason ADR 0004 works. NULL until a
    -- sync finishes, and written inside the same transaction as that user's
    -- submissions -- so the rows and the "this user is complete" mark become
    -- permanent together, or neither does.
    --
    -- Everything reading submissions treats NULL as "no data for this user",
    -- never as "this user has no submissions". Those mean opposite things.
    last_synced  TEXT
) STRICT;


-- Every problem seen in anybody's history. Stored once, not repeated on each
-- of the thousands of submissions that reference it.
CREATE TABLE IF NOT EXISTS problems (
    -- contestId + index, e.g. "1234A".
    --
    -- The acmsguru archive (453 problems) has no contestId at all -- web.py's
    -- display_row already handles this -- so for those the id is
    -- problemsetName + index, e.g. "acmsguru553". It cannot collide with the
    -- normal form: contest ids are numeric, and this starts with letters.
    --
    -- db.py owns building this string, and raises if the API object has
    -- neither field, rather than quietly storing "None553".
    --
    -- NEVER SPLIT THIS BACK INTO ITS PARTS -- read the two columns below.
    -- It looks splittable at the first letter, but contest 921 has 14
    -- problems whose index is a number ("01" to "14"), so their ids look
    -- like "92114". Nothing in that string says whether it means contest 921
    -- problem 14, or contest 9211 problem 4.
    --
    -- One row per contest a problem appeared in, NOT one per problem. When a
    -- Div. 1 and a Div. 2 round run together they share problems under
    -- different ids -- 1292A and 1293C are the same problem -- and each
    -- submission is stored under the id it was actually made against. Read
    -- spec section 12 before assuming that one id means one problem.
    id             TEXT    PRIMARY KEY,

    -- The two halves of the id, kept as their own columns so nothing ever
    -- has to parse the string. Needed to build a problem's link on the
    -- results page, and to recognise gym problems (contest ids from 100000
    -- up). NULL for acmsguru.
    contest_id     INTEGER,

    -- Not named "index": INDEX is an SQL keyword (as in CREATE INDEX), and
    -- SQLite rejects a column named index with a syntax error unless the
    -- name is quoted in every statement that touches it.
    problem_index  TEXT    NOT NULL,

    name           TEXT    NOT NULL,

    -- Often absent (spec section 6), so nullable. This is exactly what makes
    -- the rating-only baseline in section 9 non-trivial: a baseline that
    -- cannot score a third of the problemset is not much of a baseline.
    rating         INTEGER,

    -- The id and its two halves are the same fact stored twice, and two
    -- copies can drift apart. This makes a disagreement an error at the
    -- write, instead of a broken link months later. || joins two values as
    -- text; SQLite converts the integer on the way.
    CHECK (contest_id IS NULL OR id = contest_id || problem_index)
) STRICT;


-- One row per (problem, tag) pair -- ADR 0005. Roughly 30,000 rows.
CREATE TABLE IF NOT EXISTS problem_tags (
    -- ON DELETE CASCADE: deleting a problem takes its tags with it, so no
    -- orphan rows are left pointing at nothing. Requires foreign_keys = ON.
    problem_id  TEXT    NOT NULL REFERENCES problems(id) ON DELETE CASCADE,

    -- One tag, e.g. "dp". Never a list.
    tag         TEXT    NOT NULL,

    -- The pair is the key, so INSERT OR IGNORE silently drops a tag that is
    -- already recorded. That is what makes re-syncing a problem safe.
    PRIMARY KEY (problem_id, tag)
) STRICT;

-- The primary key above indexes (problem_id, tag), which makes "this
-- problem's tags" fast but does nothing for "every problem tagged dp",
-- because tag is not the leading column. That second query is what the topic
-- breakdown at v0.4 runs, so it gets an index of its own.
CREATE INDEX IF NOT EXISTS idx_problem_tags_tag ON problem_tags(tag);


-- Every submission fetched. The largest table by far: ~2000 users at up to a
-- few thousand submissions each, so roughly two million rows after v0.3.
CREATE TABLE IF NOT EXISTS submissions (
    -- Codeforces' own submission id, not one generated here. That is what
    -- makes the sync repeatable: fetching the same submission twice produces
    -- the same row, so INSERT OR IGNORE turns a duplicate into a no-op
    -- instead of an error or a second copy.
    --
    -- Declared exactly "INTEGER PRIMARY KEY", which in SQLite makes this the
    -- table's internal row id -- the fastest lookup available, and it costs
    -- no extra index space.
    id                INTEGER PRIMARY KEY,

    -- COLLATE NOCASE again, for the same reason as users.handle, and so the
    -- index below is case-insensitive too. Without it here, a lookup for
    -- "Tourist" would miss rows stored as "tourist".
    handle            TEXT    NOT NULL COLLATE NOCASE
                              REFERENCES users(handle) ON DELETE CASCADE,

    problem_id        TEXT    NOT NULL REFERENCES problems(id),

    -- "OK", "WRONG_ANSWER", "TIME_LIMIT_EXCEEDED", and so on. Nullable,
    -- because a submission still being judged has no verdict at all.
    -- api_client.format_submission substitutes "TESTING" for display, but
    -- that is a display decision and does not belong in storage. NULL is the
    -- honest value for "not judged yet".
    verdict           TEXT,

    -- "CONTESTANT", "VIRTUAL", "PRACTICE", ... Not in spec section 6's
    -- original list. Added because section 12's "what counts as solved?" and
    -- section 8's assumption 4 about selection bias both need it eventually.
    --
    -- The reason to add it now rather than later: adding a column later is
    -- trivial, but FILLING IT IN later means re-fetching 2000 users at two
    -- seconds a request -- the v0.3 collection run, done twice. While the API
    -- response is already in memory, storing this costs nothing.
    participant_type  TEXT,

    -- ISO-8601 UTC text, converted from the API's creationTimeSeconds.
    submitted_at      TEXT    NOT NULL
) STRICT;

-- For "this user's submissions, newest first" -- the results page, and the
-- query model.py and evaluate.py both start from. submitted_at is included
-- so the sort is served by the index instead of being done afterwards;
-- SQLite reads an index backwards happily, so one ascending index covers
-- DESC too. Without this, that query scans every row in the table.
CREATE INDEX IF NOT EXISTS idx_submissions_handle
    ON submissions(handle, submitted_at);

-- For "everyone who attempted this problem" -- what the model needs at v0.6
-- to estimate a problem's difficulty from the crowd rather than from
-- Codeforces' own rating.
CREATE INDEX IF NOT EXISTS idx_submissions_problem
    ON submissions(problem_id);


-- Long work cannot happen inside a web request, so it happens in a worker
-- thread and its state lives here, where a page can poll it (spec section 7).
CREATE TABLE IF NOT EXISTS jobs (
    id           INTEGER PRIMARY KEY,

    -- CHECK turns a typo into an error at the write, rather than a row that
    -- silently matches nothing three weeks later.
    kind         TEXT    NOT NULL CHECK (kind IN ('sync', 'collect')),

    -- Which handle, or which batch.
    target       TEXT    NOT NULL,

    state        TEXT    NOT NULL DEFAULT 'pending'
                         CHECK (state IN ('pending', 'running', 'done', 'failed')),

    -- Submissions fetched so far. Under ADR 0004 this drives the progress
    -- page rather than resumption -- an interrupted sync writes nothing, so
    -- there is nothing to resume from. It becomes a resume point only if the
    -- incremental option in ADR 0004 is ever adopted.
    progress     INTEGER NOT NULL DEFAULT 0,

    started_at   TEXT    NOT NULL,

    -- NULL while the job is unfinished. Without this there is no way to tell
    -- a job that is still working from one that stopped.
    finished_at  TEXT,

    -- Why it failed, if it did. Written OUTSIDE the user's transaction: if it
    -- were inside, the rollback would erase the record that the failure ever
    -- happened, which is the one thing that must survive.
    error        TEXT
) STRICT;

-- At most one unfinished job per target, so two people typing "tourist" at
-- the same moment cannot start two syncs and double the API load.
--
-- The WHERE clause makes this a partial index: it covers only rows in those
-- two states, so done and failed jobs are exempt and retrying after a
-- failure is allowed.
CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_one_active_per_target
    ON jobs(kind, target)
    WHERE state IN ('pending', 'running');
