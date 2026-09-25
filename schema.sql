-- NextCF database schema.
--
-- Twelve tables and one view, per spec section 6. Run once at startup via
-- db.py's init_db(); every statement is IF NOT EXISTS, so running it again is
-- harmless -- and also means a CHANGE to an existing table here does nothing
-- to a database that already has it.
--
-- Both database files use this one schema (ADR 0007). The last four tables
-- and the view are filled only in dataset.db, by collect.py; on the server
-- they exist and stay empty. `visits` is the mirror image: written only by
-- the web app, empty in dataset.db.
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

    -- Difficulty target from spec section 1, and READ AGAIN since
    -- 2026-09-24: the "too hard" and "too easy" buttons on each
    -- recommendation move it one step (ADR 0021).
    --
    -- The DEFAULT is still the 0.70 this column was created with, and it is
    -- not the product default -- that is model.DEFAULT_TARGET, 0.50 (ADR
    -- 0012). Changing a column default on an existing table means rebuilding
    -- it, and submissions and dismissals refer to this one. The column below
    -- is what makes the stale default harmless: until somebody presses a
    -- button, nothing here is read at all.
    target_prob  REAL    NOT NULL DEFAULT 0.70,

    -- When this visitor last moved their own target, or NULL if never. The
    -- point is the NULL: it separates "chose 0.70" from "never chose
    -- anything and is still carrying the default this table was born with".
    -- Without it the two are the same number and the code has to guess.
    target_chosen_at TEXT,

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
    -- submission is stored under the id it was actually made against.
    -- problem_aliases below is what ties those rows back together; read
    -- ADR 0010 before assuming that one id means one problem.
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

    -- 1 if problemset.problems lists this id, 0 otherwise. Two things need it
    -- and neither could be written without it (ADR 0010):
    --
    --   the recommendation pool is "in_problemset = 1 AND rating IS NOT NULL"
    --   -- 11,102 problems of the 11,401 listed;
    --
    --   and problem_aliases below points every OTHER id of the same problem
    --   at the one copy the problemset lists.
    --
    -- A snapshot, exactly like rating beside it: a contest can be removed and
    -- its problems leave the problemset. save_problemset() therefore clears
    -- the flag and re-sets it on every fetch -- the same shape as ADR 0005's
    -- rule that tags are replaced rather than added to. save_sync() never
    -- touches this column, so a problem learned from somebody's submission
    -- can neither list nor un-list itself.
    in_problemset  INTEGER NOT NULL DEFAULT 0 CHECK (in_problemset IN (0, 1)),

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


-- One problem, many ids -- ADR 0010. A Div. 1 and a Div. 2 round running
-- together share problems, and each shared problem gets an id in BOTH
-- contests. problemset.problems lists one of them; a Div. 2 contestant's
-- submissions carry the other. 1,807 of the 13,208 non-gym ids in the
-- collected dataset are unlisted this way.
--
-- This table is the only derived data spec section 6 allows to be stored, and
-- the reasons are in ADR 0010: it depends on the whole problems table, so it
-- cannot be worked out for one visitor's page, and section 9 has to be
-- reproducible from the file.
--
-- Rebuilt whole by db.rebuild_aliases(), inside the same transaction that
-- writes in_problemset. Never edited by hand.
CREATE TABLE IF NOT EXISTS problem_aliases (
    -- PRIMARY KEY, not just a column: an id has at most one canonical form.
    -- Two rows for one alias would make "has this user solved it?" depend on
    -- which row a query happened to read.
    alias_id      TEXT PRIMARY KEY REFERENCES problems(id) ON DELETE CASCADE,

    -- Always a row with in_problemset = 1, which is why no alias ever points
    -- at another alias and nothing here has to be followed more than one step.
    canonical_id  TEXT NOT NULL    REFERENCES problems(id) ON DELETE CASCADE,

    -- A problem is not its own alias. Cheap, and it turns the worst possible
    -- bug in the builder -- matching a problem to itself, which would make
    -- every count silently double -- into a failed write.
    CHECK (alias_id <> canonical_id)
) STRICT;

-- For "every id this problem is also known by", which is the direction the
-- topic counts read it in. The primary key above only serves the other one.
CREATE INDEX IF NOT EXISTS idx_problem_aliases_canonical
    ON problem_aliases(canonical_id);

-- The alias builder joins problems to problems on (name, rating). Without
-- this it is 13,000 rows scanned once per candidate; the web app rebuilds the
-- map at every startup (ADR 0010), so it is worth the index.
CREATE INDEX IF NOT EXISTS idx_problems_name_rating
    ON problems(name, rating);


-- Every submission fetched. The largest table by far: 3,875,775 rows in the
-- v0.3 dataset, from 4000 users -- a mean of 969 each and a median far lower,
-- because a few histories run past 13,000.
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
    -- 'sync' is the only kind anything writes: collect.py reports to a
    -- terminal rather than a web page, so it writes no job rows (ADR 0007).
    --
    -- 'collect' is still permitted here, and ADR 0007 said to remove it at
    -- "the next schema change so one rebuild covers both". ADR 0010 was that
    -- change and it did NOT cover this, because its premise turned out to be
    -- wrong: adding a column rewrites nothing, so there was no rebuild to
    -- share. Removing a value from a CHECK still means rebuilding this table
    -- on its own, for a value nothing writes. It waits for a change that
    -- rebuilds a table for a real reason.
    kind         TEXT    NOT NULL CHECK (kind IN ('sync', 'collect')),

    -- Which handle, or which batch. COLLATE NOCASE for the same reason as
    -- users.handle: without it "Tourist" and "tourist" are different targets,
    -- the unique index below would happily allow one unfinished job of each,
    -- and the same person would be fetched twice at the same time.
    target       TEXT    NOT NULL COLLATE NOCASE,

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


-- Problems a visitor has said no to, and why -- ADR 0021. "Too hard" and
-- "too easy" are the only two answers, because they are the two the site can
-- act on: each one hides that problem and moves this user's difficulty target
-- one step.
--
-- Stored rather than kept for the page, for the obvious reason: a problem the
-- visitor has just pushed away must not come back on the next reload. It is
-- also the first record this project keeps of a visitor JUDGING a
-- recommendation, which is what section 9's calibration and the v1.5 pet
-- system will both need.
--
-- Canonical ids (ADR 0010): the pool is problemset members, so a dismissal is
-- about the problem, not about which division's copy of it was shown.
CREATE TABLE IF NOT EXISTS dismissals (
    handle       TEXT NOT NULL COLLATE NOCASE
                      REFERENCES users(handle) ON DELETE CASCADE,
    problem_id   TEXT NOT NULL REFERENCES problems(id),
    reason       TEXT NOT NULL CHECK (reason IN ('too_hard', 'too_easy')),
    dismissed_at TEXT NOT NULL,

    -- One row per (person, problem): pressing the other button later replaces
    -- the first answer rather than keeping both, because only the latest one
    -- is what they think.
    PRIMARY KEY (handle, problem_id)
) STRICT;


-- Who came, and when -- spec section 9's second criterion, and the only thing
-- on this server that cannot be fetched again once it is lost. That is the
-- whole reason for ADR 0017: before the first stranger arrives, nextcf.db
-- moves onto a disk that survives a restart.
--
-- Filled only in nextcf.db. collect.py never writes it, so in dataset.db this
-- table exists and stays empty -- the mirror image of the four tables below.
--
-- TWO IDENTITIES, because section 9 counts two different things. The handle
-- says what somebody did. The cookie id counts somebody who read the landing
-- page and left, which the handle cannot. Either may be missing: a browser
-- that keeps no cookie leaves visitor_id NULL, and a page that looks nothing
-- up leaves handle NULL. Counted by cookie, a browser that refuses cookies
-- looks like a new person every time, which OVER-counts people; counted by
-- handle, everybody who only read the pitch is invisible, which UNDER-counts
-- them. Neither is the truth on its own; together they bracket it.
--
-- What is NOT here is the point: no IP address, no user agent, no referrer.
-- Nothing stored here identifies anybody off this site, which is what keeps
-- /privacy short enough to be read.
CREATE TABLE IF NOT EXISTS visits (
    id          INTEGER PRIMARY KEY,

    -- A random string from a first-party cookie, derived from nothing about
    -- the visitor. NULL when the browser sent none and kept none.
    visitor_id  TEXT,

    -- The handle whose page this was, or NULL for a page that looks nothing
    -- up. COLLATE NOCASE for the same reason as users.handle: "Tourist" and
    -- "tourist" are one person.
    --
    -- Deliberately NOT a foreign key to users. A visit is a record that
    -- something happened, and it stays true after that user's cached rows are
    -- gone -- which on the free instance is several times a day.
    handle      TEXT    COLLATE NOCASE,

    -- Which page. This is what tells "used it" from "read about it", and it
    -- is the only thing here that says anything at all about what was done.
    path        TEXT    NOT NULL,

    visited_at  TEXT    NOT NULL
) STRICT;

-- Both section 9 questions -- how many people, and which of them came back on
-- another day -- group by identity and then look at time.
CREATE INDEX IF NOT EXISTS idx_visits_visitor ON visits(visitor_id, visited_at);
CREATE INDEX IF NOT EXISTS idx_visits_handle ON visits(handle, visited_at);


-- ============================================================ the dataset
--
-- Everything below is written by collect.py into dataset.db (ADR 0009).
-- Changing it after the collection means collecting again, so these
-- columns were chosen before the first real run, not after.


-- Every change to a collected user's rating: one row per rated contest, from
-- user.rating. This is what lets an old submission be predicted from the
-- rating its author had THEN rather than today -- without it, the evaluation
-- would know how strong a user later became (data leakage, ADR 0009).
CREATE TABLE IF NOT EXISTS rating_changes (
    -- ON DELETE CASCADE, as for submissions: removing a user removes their
    -- whole record, not most of it.
    handle      TEXT    NOT NULL COLLATE NOCASE
                        REFERENCES users(handle) ON DELETE CASCADE,

    contest_id  INTEGER NOT NULL,

    -- The user's place in that contest. The API calls it "rank", a word that
    -- on Codeforces also means a title such as "expert", hence the rename.
    -- Not needed by the rating-only
    -- baseline, but it is in the response already, and it is the one thing a
    -- model of contest performance would want that cannot be rebuilt from
    -- submissions. Same reasoning as submissions.participant_type: storing it
    -- now is free, and filling it in later is two thousand requests.
    place       INTEGER NOT NULL,

    old_rating  INTEGER NOT NULL,
    new_rating  INTEGER NOT NULL,

    -- When the new rating took effect, converted from ratingUpdateTimeSeconds.
    -- A submission made before this moment was made at old_rating -- including
    -- every submission during the contest itself, since ratings update after
    -- it ends.
    rated_at    TEXT    NOT NULL,

    -- A user has at most one rating change per contest, so a second one for
    -- the same pair is a bug to catch at the write, not a duplicate to average.
    PRIMARY KEY (handle, contest_id)
) STRICT;

-- For "this user's rating at time T": the latest change with rated_at <= T.
-- The primary key is ordered by contest, not by time, so it cannot answer
-- that; this index can, without a scan.
CREATE INDEX IF NOT EXISTS idx_rating_changes_time
    ON rating_changes(handle, rated_at);


-- How a sample was drawn. One row per draw -- collect.py refuses a second,
-- because a second draw would silently change who is in the dataset.
CREATE TABLE IF NOT EXISTS samples (
    id                 INTEGER PRIMARY KEY,

    -- random.Random(seed).shuffle over the candidates sorted by handle. The
    -- seed makes the draw repeatable from the same list; the stored order in
    -- sample_candidates is the real record, because the list itself changes
    -- every day and is not kept.
    seed               INTEGER NOT NULL,

    -- Which list the users came from, and when it was fetched. The sample
    -- describes that day's active users, not Codeforces in general.
    source             TEXT    NOT NULL,
    source_fetched_at  TEXT    NOT NULL,

    -- The strata: rating_min to rating_max inclusive, in steps of
    -- stratum_width, per_stratum users wanted from each. 1000, 1999, 200 and
    -- 800 in ADR 0009 (drawn at 400; see sample_size_changes).
    rating_min         INTEGER NOT NULL,
    rating_max         INTEGER NOT NULL,
    stratum_width      INTEGER NOT NULL,
    per_stratum        INTEGER NOT NULL,

    CHECK (rating_min <= rating_max AND stratum_width > 0 AND per_stratum > 0)
) STRICT;


-- Every user in range on the day of the draw -- all ~21,000 of them, not only
-- the 2000 collected -- in the order the seeded shuffle put them.
--
-- Keeping the whole order is what makes three things simple. The sample is
-- "the first per_stratum available candidates in each stratum", so a handle
-- that has vanished is replaced by the next in line, deterministically. The
-- count of candidates per stratum is that stratum's population, which is the
-- weight section 9's total needs. And a stopped collection resumes exactly
-- where it was, because the order does not depend on anything that changes.
CREATE TABLE IF NOT EXISTS sample_candidates (
    sample_id          INTEGER NOT NULL REFERENCES samples(id),

    -- The stratum's lower bound: 1000, 1200, 1400, 1600 or 1800.
    stratum            INTEGER NOT NULL,

    -- 0, 1, 2, ... within the stratum, after the shuffle.
    position           INTEGER NOT NULL,

    handle             TEXT    NOT NULL COLLATE NOCASE,

    -- Their rating in the list on the day of the draw. It decides the stratum,
    -- and it stays fixed even if their rating changes before they are
    -- collected -- otherwise a user could move between strata mid-collection.
    rating_when_drawn  INTEGER NOT NULL,

    -- NULL, or why this candidate could not be collected, in Codeforces' own
    -- words ("handle: User with handle ... not found"). Only answers that
    -- will not change are recorded here; a network failure is not, so a
    -- stopped run never turns into a skipped user.
    --
    -- Whether a candidate WAS collected is deliberately not a column: that
    -- fact already lives in users.last_synced, and a second copy could
    -- disagree with the first.
    unavailable        TEXT,

    PRIMARY KEY (sample_id, stratum, position),
    UNIQUE (sample_id, handle),
    CHECK (position >= 0)
) STRICT;


-- Every time a sample's per_stratum was raised after the draw -- ADR 0009 was
-- drawn at 400 and raised to 800 the same night. samples.per_stratum holds the
-- current number; this is how it got there, so the dataset's size is never a
-- number nobody can account for.
--
-- Only upwards, enforced here as well as in collect.py. Lowering it would
-- leave users collected who are no longer part of the sample.
CREATE TABLE IF NOT EXISTS sample_size_changes (
    sample_id        INTEGER NOT NULL REFERENCES samples(id),
    changed_at       TEXT    NOT NULL,
    old_per_stratum  INTEGER NOT NULL,
    new_per_stratum  INTEGER NOT NULL,
    CHECK (new_per_stratum > old_per_stratum)
) STRICT;


-- Per stratum: how many users were in range (the weight), how many are
-- wanted, how many are collected, how many turned out unavailable. What
-- `collect.py status` prints, and what section 9's weighted total reads.
CREATE VIEW IF NOT EXISTS sample_strata AS
SELECT c.sample_id,
       c.stratum,
       count(*)             AS population,
       s.per_stratum        AS wanted,
       count(u.handle)      AS collected,
       count(c.unavailable) AS unavailable
  FROM sample_candidates c
  JOIN samples s ON s.id = c.sample_id
  LEFT JOIN users u ON u.handle = c.handle AND u.last_synced IS NOT NULL
 GROUP BY c.sample_id, c.stratum;
