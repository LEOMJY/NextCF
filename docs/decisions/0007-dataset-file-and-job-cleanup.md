# 0007 — The training set gets its own file; only the web app cleans up jobs

**Date:** 2026-09-13
**Status:** accepted

## Context

Two questions had to be answered before `collect.py` could be written, and they
turned out to share an answer.

**Where the data lives.** §7 has carried a known risk since 08-11: the host
wipes the server's files. It was moved to v0.2, carried past v0.2 unanswered,
and the devlog said twice that it had to be settled before v0.3. Checking
Render's documentation made it worse than §7 said. A free instance loses every
file it wrote not only on a redeploy but on any restart, and whenever it spins
down after 15 minutes without traffic — so in practice several times a day.
Free instances cannot attach a persistent disk.

That matters differently for each kind of data:

| Data | Comes from | If it is wiped |
|---|---|---|
| A visitor's submissions | Codeforces, in seconds | One re-sync |
| The ~2000-user training set | An hour of API calls | An hour |
| Who visited, and when | Exists only on the server | §9's "20 have returned" is unmeasurable |

**Who may clean up abandoned jobs.** `init_db()` marked every unfinished job
failed at startup. That is right for the web app: when it starts, every sync
thread from its previous run died with the old process. §12 asked what happens
once a second program uses the same file.

It was not a future problem. `sync.py`'s `main()`, run by hand, already called
`init_db()`. Start the site, type a handle, run `sync.py` in a terminal while
that sync is running, and the visitor is told "The server restarted before this
job finished" while the job carries on. No data is damaged — ADR 0004 sees to
that — but the visitor is shown a failure that did not happen, and a retry
starts a second sync of the same handle.

## Decision

**The training set lives in `dataset.db`, on the author's machine, and never
goes to the server.** `collect.py`, `model.py` and `evaluate.py` run there.
`nextcf.db` on the server is a cache of public data and is allowed to vanish.

**Only the web app cleans up jobs.** The cleanup moves out of `init_db()` into
`fail_orphaned_jobs()`. `init_db()` only creates what is missing, so any program
may call it at any time. `fail_orphaned_jobs()` is called once, by `web.py`, at
startup. The rule behind it: the program that starts a kind of job is the only
one that may declare those jobs abandoned.

**`collect.py` writes no job rows.** The jobs table exists so a background
thread can report to a web page. `collect.py` has no page; it runs in a
terminal and prints its progress there. It resumes from what ADR 0004 already
provides: a user whose `last_synced` is set in `dataset.db` is complete and is
skipped, and a user interrupted mid-fetch wrote nothing and is fetched again.

**The nightly re-sync runs as a thread inside the web app** at v0.7, not as a
separate program — so the web app stays the only program that starts syncs.

## Alternatives

**One shared file on the author's machine**, with the web app and `collect.py`
both using `nextcf.db`. Rejected. The web app re-syncs any handle older than ten
minutes, so looking up a user who is in the training set would change that
user's rows. `evaluate.py` run twice would then give two different numbers, and
the §9 number has to be reproducible. A separate file is a frozen snapshot, and
it is also the dataset §9 proposes to publish.

**Collect on the server.** Rejected: an hour of calls written to a file that is
wiped on the next spin-down.

**A paid persistent disk now.** Rejected for now. Nothing on the server is worth
paying to keep until strangers visit. It is one of the two candidates at v0.7.

**A heartbeat.** Each running job writes "still alive" every few seconds, and a
job silent for longer than some limit is dead, whoever checks. This works for
any number of programs, even on different machines, and it is how larger job
systems do it. Rejected, for costs specific to this code:

- The heartbeat can only be written between API calls, and one call can be
  silent for up to 36 seconds — three attempts at a 10-second timeout, plus 2
  and 4 seconds of waiting, all set in `api_client.py`. Too short a limit kills
  live syncs; too long leaves a visitor watching a dead job.
- That makes a timeout in `api_client.py` silently decide when jobs are killed
  in `db.py`. Raising it later would start failing live syncs with nothing
  pointing at the cause.
- After a restart a dead job would spin until the limit passed, where the
  chosen option clears it the moment the web app starts.
- It needs a new column.

It solves the problem of many programs sharing one file, which this decision
removes. It is the upgrade if that ever changes.

## Consequences

- `init_db()` and `fail_orphaned_jobs()` are safe for different programs. The
  split is enforced only by convention: nothing in the code stops a future
  program calling `fail_orphaned_jobs()`. The docstring and this ADR are the
  guard, and a check starts real separate processes against a file holding a
  running sync to prove both halves.
- The rule breaks if two copies of the web app ever share one database file. A
  free instance runs one copy.
- `jobs.kind` still permits `"collect"` in `schema.sql`. Nothing writes it.
  Removing it needs the database rebuilt, which is left for the next schema
  change so one rebuild covers both.
- **Visit records have a deadline: v0.7**, before anyone who is not the author
  uses the site. A visit that was not recorded cannot be recovered. Counting
  visits is not built yet either, and is now in v0.7's row in §10.
- **The model is fitted on one machine and used on another.** What it learned
  has to reach the server in a way that survives a restart. Open in §12 for
  v0.6.
- `dataset.db` is not backed up. Losing it costs one re-run of `collect.py`,
  about an hour, and that is accepted.
