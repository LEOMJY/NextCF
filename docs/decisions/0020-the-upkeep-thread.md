# 0020 — The upkeep thread: a question asked, not a schedule kept

**Date:** 2026-09-23
**Status:** accepted

## Context

§4 and §7 have named a nightly scheduler since 08-11, and ADR 0007 fixed its
shape: a thread inside the web app, not the host's cron, because a cron
service on Render cannot read this service's disk and a second program
starting syncs would break the rule that only the web app does. §10 puts it at
v0.7. What it should actually do was never written down beyond "re-sync users
already known", and one of its two jobs turned out to matter more than that
one.

**The problemset ages.** Codeforces runs contests every week, and a problem
that is not in the pool can never be recommended (ADR 0010). The app fetches
the pool once, at startup. On the free instance that happens several times a
day, so today it is refreshed by accident; on the paid instance of ADR 0017,
which stays up, a process could run for weeks recommending from the pool it
had on the morning it started. The same fetch has no retry: `load_problemset`
logs a failure and gives up, and its own comment says the scheduler is where
the retry belongs.

**Re-syncing recent visitors is worth less than it was.** It was written down
when a stale page meant a queue and a wait. Since ADR 0018 a returning visitor
sees their page at once and the refresh runs behind it in about four seconds,
so a nightly re-sync now saves those four seconds rather than a wait. It is
still worth having -- a page that is already fresh is better than one that
becomes fresh while you read it -- and it is the mechanism §9's calibration
will need when the site starts recording what it recommended. It is no longer
the reason the thread exists.

## Decision

**One thread, waking every 30 seconds, asking what is due.**

**1. The problemset is fetched whenever the pool is empty, and again whenever
it is more than six hours old.** An empty pool means the file is new or the
last fetch failed, and until it is fixed the recommender has no candidates at
all, so that case does not wait six hours. A failed fetch does not move the
clock, so the next tick tries again rather than in six hours.

The empty case is also the startup fetch: the first tick finds nothing stored
and goes. **This thread is therefore the only thing that fetches the
problemset**, which it was not at first -- the entry points started a fetch of
their own, the two raced, and every start made two identical requests. It was
visible in serve.py's own output, printed twice, the first time it was run.

**2. One recent visitor's history is re-synced at a time.** "Recent" is
somebody whose handle appears in `visits` in the last 30 days (ADR 0017);
"worth it" is a stored history older than 20 hours, oldest first. Twenty
rather than twenty-four so that somebody who visits at the same hour each day
is always due.

**3. Visitors first: nothing is queued while any sync is waiting or
running.** A background refresh in front of somebody watching a progress page
is four seconds they did not ask for. It also means this can never build a
queue of its own -- there is at most one of its jobs in flight, and under load
it does nothing at all. The problemset is exempt: one request, and it stands
in nobody's way.

**4. Nothing is remembered that a restart would lose.** What is due is a
question asked of rows already on disk -- the visits, and each user's
`last_synced`. The one exception is when the problemset was last fetched,
which is kept in memory deliberately: losing it costs one extra request after
a restart, and the alternative is a stored row that has to be kept in step
with something the database cannot see.

## Alternatives

**A schedule: "run at 03:00".** The obvious shape, and wrong for this process.
The free instance restarts several times a day and sleeps at night, so a plan
held in memory would be repeated on every restart or never fire at all, and a
plan held in the database needs a row, a clock and an argument about time
zones. Asking "whose history is old?" needs none of that and is correct after
any number of restarts.

**The host's cron.** Rejected in ADR 0007 before this was written: on Render a
cron service is a separate program with its own disk, so it could neither read
this database nor start a job in this app.

**Re-syncing everybody nightly, in a batch.** With one worker and two requests
a sync, fifty users is two hundred seconds of queue. Done at 3am that is free
-- but only on an instance that is awake at 3am, which the free one is not,
and a batch that starts while somebody is waiting is exactly what decision 3
exists to prevent. One at a time when idle reaches the same place without ever
being in the way.

**Not building it at all**, and refreshing the problemset only. Considered
seriously, because the visitor half lost most of its value to ADR 0018. Kept
because the author asked for both and because the half that remains is what
§9's calibration will be built on.

## Consequences

- **It does almost nothing until the disk is attached** (ADR 0017). On the
  free instance the process sleeps at night and `visits` is wiped on every
  spin-down, so "seen in the last 30 days" is usually empty. What it does do
  today is retry a failed problemset fetch, which is already worth its
  thirty-line loop.
- **The problemset costs four requests a day.** Out of a budget of one every
  two seconds, and it never waits for a visitor.
- **Nightly work is invisible in the jobs table**, because it uses the same
  `kind = 'sync'` rows a visitor's sync uses. That was deliberate: a new kind
  means changing a CHECK constraint, which means rebuilding the table (ADR
  0010's note), for a distinction nothing needs yet. It will need one the day
  the queue gets priorities.
- **A tick that throws is logged and the loop carries on**, like the sync
  worker. A thread that dies takes its own error message with it, and nothing
  else would notice that the problemset had stopped being refreshed.
- **`web.load_problemset` now answers whether it worked.** It used to log and
  return nothing, which is fine for a startup thread and useless to a caller
  that has to decide whether to try again.
- **`web.start_problemset_fetch` is gone**, and the entry points start two
  threads rather than three. One owner for "the problemset is current" is
  what removes the double fetch; two owners could not agree on when it had
  been done.
