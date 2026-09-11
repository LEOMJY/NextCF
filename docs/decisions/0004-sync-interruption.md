# 0004 — An interrupted sync writes nothing

**Date:** 2026-09-07
**Status:** accepted

## Context

§12 has asked since 08-11 what happens when a sync job dies partway through a
user, and answered itself with "partial data in the database is worse than
none." That had to be settled before `db.py` existed, because the answer
decides whether `last_synced` is a cache timestamp or something stronger.

The claim in §12 is not quite right, and the precise version changes the
design. Partial data is not inherently worse than none. Partial data that is
*indistinguishable from complete data* is worse than none.

The failure it describes runs like this. 300 of a user's 5000 submissions are
fetched, the process dies, and the database holds 300 rows and a `last_synced`
of five seconds ago. Nothing crashed and nothing was logged. Every later reader
— the results page, `model.py`, `evaluate.py` — sees a user marked synced and
reads 300 submissions as the complete truth. The model then learns that this
user has solved twelve DP problems when the real figure is four hundred, and
that corruption ends up inside the §9 number, which is the one output of this
project that has to be trustworthy.

The damage is not the missing rows. It is that nothing in the database records
that they are missing. So the goal is not "prevent partial writes", it is
"make completeness explicit and machine-checkable". Once it is explicit,
partial data is strictly better than none, because it is work not repeated.

## Decision

**One transaction per user.** Fetch that user's whole history into memory,
then open a transaction, insert the rows, set `users.last_synced`, and commit.
A transaction either takes effect entirely or not at all, so a process killed
at any point before the commit leaves the database exactly as it was.

`last_synced` is written **inside that same transaction** and is therefore the
completeness flag: NULL means no usable data for this user, regardless of how
many submission rows happen to exist. It cannot drift out of step with the rows
because there is no moment at which one exists without the other.

**Resumability lives at the user boundary**, not inside a user. §4's "dies at
minute 40, restarts at minute 40" describes `collect.py` at v0.3, where the
unit of work is one user out of ~2000. Within a single user, redoing the work
costs about 100 seconds.

**One gatekeeping function in `db.py`** returns a user's submissions and
refuses to return anything for a user whose `last_synced` is NULL. Nothing
reads the table directly. The rule is enforced in one place rather than
remembered in five.

## Alternatives

**Incremental writes plus a completeness flag.** Write each page of 100 as it
arrives, each in its own transaction, and leave `last_synced` NULL until the
user finishes. Resumable at page granularity, and the rows are never wrong,
only incomplete. Rejected for v0.2 as more machinery than the problem needs
today — but it is the designated upgrade path, and it costs nothing to move to
later precisely because the completeness flag already exists and already means
the right thing. Adopt it if one user's sync ever becomes too slow to redo.

**A staging table and an atomic swap.** Write to `submissions_staging`, move
everything across in one transaction at the end. This is the standard answer in
production data systems and it delivers the same guarantee as the chosen option
with more moving parts. Rejected on the same grounds §7 rejects Celery.

## Consequences

- A user's entire history is held in memory during a sync. A few megabytes at
  this scale; revisit only if it ever stops being.
- An interrupted sync is invisible in the database, which means the `jobs` row
  is the only record that it happened. `jobs` must therefore be written
  *outside* the user transaction, or its failure record would roll back too.
- A job killed by the host leaves `state = 'running'` forever, and
  `/progress/<job>` would poll it forever. Because §7 commits to one worker
  thread in one process, any unfinished job at startup is by definition
  orphaned, so `init_db()` marks them all failed. This is correct *because*
  there is a single process, and stops being correct the day there are two.
- *Amended 2026-09-11:* "unfinished" means `pending` as well as `running`. The
  first version of this ADR named only `running`. But the partial unique index
  on `jobs` refuses a second unfinished job for the same handle, so a `pending`
  row orphaned by a restart would have blocked that handle from ever being
  synced again — worse than a spinner that never stops.
- If incremental writes are adopted later, they are safe here only because of a
  property of somebody else's API: `user.status` returns newest first, so
  submissions arriving during a restart shift the paging window such that a
  resume re-fetches rows already held rather than skipping rows never held.
  Duplicates are absorbed by `INSERT OR IGNORE` on Codeforces' stable
  submission id. Were the ordering oldest-first, the same restart would leave a
  permanent hole with nothing to detect it. That ordering needs a comment in
  `sync.py`, because if it ever changes the failure is silent.
- `/results/<handle>` needs a real page for a user who is mid-sync, since the
  gatekeeping function will decline to serve one. That page is v0.2 work
  anyway, alongside `/progress/<job>`.
