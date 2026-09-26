# 0022 — Errors answer with their cause, and the log names no handle

**Date:** 2026-09-26
**Status:** accepted

## Context

§10 puts logging and error handling in v0.7. On 2026-09-26, before any of it
was written, the site behaved like this:

| what happened | what the visitor got | what the log got |
|---|---|---|
| a URL that matches nothing (404), a GET to a POST-only button (405) | Flask's own white page, unstyled | nothing |
| an exception in a view (500) | the same white page | the traceback |
| a sync that failed, remembered for ten minutes | the site's error page, **200** | one `print` line, some of them naming the handle |
| a sync, a page, a problemset fetch that worked | — | nothing at all |

Two defects hid in that table, and a review found the first one. The
remembered-failure page answered 200 whatever the cause, so a mistyped
handle was recorded as somebody using the site (fixed the same morning by a
different route; see the devlog). And a sync that failed because Codeforces
kept saying "Call limit exceeded" through every retry was reported as
"Codeforces rejected the request". The reason was that `TemporaryFailure`
subclasses `RuntimeError` and was caught as one.

One more thing had been waiting since ADR 0018: "one stuck job holds the
queue". `urlopen`'s ten-second timeout covers each wait for the next bytes,
not the whole body. A server that sends one byte every nine seconds never
trips it, the single worker never finishes, and Python cannot stop a thread
from outside.

## Decision

**1. A failure answers with a status code for its cause.** Each failed job
records one of four causes in a new column, `jobs.failure`, beside the
sentence in `jobs.error`:

| cause | meaning | `/results/<handle>` answers |
|---|---|---|
| `rejected` | Codeforces answered and refused, nearly always a handle that does not exist | 404 |
| `unreachable` | Codeforces could not be reached, or was still failing after every retry | 503, with `Retry-After` |
| `interrupted` | this server restarted before the job finished | 503, with `Retry-After` |
| `internal` | a bug here | 500 |

The page is the same for all four: the reason in words, and a button to try
again. `Retry-After` is the time left before the failure stops being
remembered, because a reload before then gets the same page back.
`/progress/<job>` stays 200 in every case. That page is about a job, and the
job exists.

`db.finish_job` refuses a failure that has a sentence but no cause, or a
cause but no sentence. A failed row from before the column existed has no
cause. It is answered 500, which is the only code that makes no claim about
the handle or about Codeforces.

**2. Every error Flask answers is on the site's own page.** One handler, for
every `HTTPException`. It keeps the status code and the headers (a 405 still
says `Allow: POST`) and changes only the page. An exception that no view
caught reaches the same handler as a 500, after Flask has written the
traceback to the log. The visitor sees one true sentence, and nothing of the
exception.

**3. One log, written with Python's `logging`, configured in one place.**
`logs.py` sets the format (time, level, module, message) and sends
everything to standard error, which Render collects. Only the entry points
call it, so the checks print as they always did. It records:

- every request: method, the route's **pattern**, status, milliseconds;
- every sync: started, and done or failed with its cause and duration;
- the problemset fetch, the upkeep thread's actions, unfinished jobs failed
  at startup;
- every unexpected exception, **with its traceback**. The old `print` lines
  kept only the message.

**4. The log never names a handle.** Syncs are logged by job id, pages by
route pattern (`/results/<handle>`, never `/results/tourist`), and a request
that matched no route by a placeholder rather than its path. Codeforces'
refusal names the handle, so it goes to the jobs row, which the visitor's
page reads, and not to the log. `api_client`'s retry warning names the
method and not the parameters. Flask's own line for an exception, "Exception
on /results/tourist [GET]", is replaced with one that names the route. `/privacy` lists what this site keeps, the
host keeps this log, and so `/privacy` now says the log holds no handle and
no IP address, and the code is written so that the sentence stays true.

**5. One attempt may spend at most 60 seconds receiving its body.** The
body is read in chunks and the clock is checked between them. Past the
deadline the read raises the same `TimeoutError` a stalled read already
raised, so it is retried as a network failure and ends as `unreachable`. A
job can now hold the queue for about three minutes at worst, not forever.

## Alternatives

**Keep 200 for every failure** ("the request worked; the sync did not").
Consistent with the progress page, and no schema change. Rejected because
anything that is not a person reads the status and nothing else: a crawler
indexes a typo as a page, and a count of 5xx in the log means nothing. The
visit counting read it too, and that is how the defect above happened.

**One error status for every failure, such as 404.** No schema change. It
tells a browser a handle does not exist on a morning when Codeforces is down,
and a 404 can be cached.

**Read the cause out of the error sentence** instead of storing it. No
schema change, and it breaks silently the day either side rephrases a
sentence. The sentence is for people and the column is for the program.

**Log handles.** Debugging is faster ("tourist's sync failed"). It would
turn `/privacy`'s "that is the whole list" into a list that also has to
describe a log, how long the host keeps it, and who can read it. The job id
leads back to the handle through the jobs table, which `/privacy` already
covers, so the cost is one query when debugging.

**A log file, or a hosted logging service.** A file on the free instance is
wiped several times a day, and on the paid one it is a second copy nobody
reads. A service is a third party `/privacy` would have to name, and it is
the kind of thing §7 rejects until a problem demands it.

**A deadline on the whole job** instead of on each body. A thread cannot be
stopped from outside, so a job-level limit could only mark the row failed
while the thread carried on holding the worker. The deadline has to be
inside the loop that reads.

## Consequences

- **A schema change**: `ALTER TABLE jobs ADD COLUMN failure`, which is
  metadata only, like ADR 0010's. The column checks its value is one of the
  four. It cannot also check "set exactly when the job failed", because
  SQLite tests a new column's CHECK against existing rows, and old failed
  rows have no cause. `finish_job` enforces that instead.
- **A failure page is no longer counted as a visit**, because the visit
  record counts only 200s. This agrees with the other path a typo takes,
  the progress page, which was never counted.
- **"Codeforces is not answering properly"** replaces the old "Codeforces
  rejected the request: Call limit exceeded" for a bad minute that outlasts
  the retries.
- **The feedback route stopped guessing.** It used to catch any
  `IntegrityError` and blame the problem. It now checks that the problem
  exists before writing, and it writes the dismissal and the new target in
  one transaction (`db.record_feedback`), so a failure part-way through
  leaves neither. A failure at the write is a 500 and a traceback, as a bug
  should be.
- **Found on the first real run:** every page is followed by a 404 for
  `/favicon.ico`, because the site declares no icon. That was invisible until
  requests were logged. The icon is a design decision, for v0.8.
- **Log volume** is one line per request, and a waiting visitor's progress
  page polls every 2 to 10 seconds. A crowd of ten waiting visitors is a few
  lines a second. That is fine at this scale, and it is the first thing to
  quieten if it stops being fine.
