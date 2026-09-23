# 0018 — One sync at a time, and a progress page that can count

**Date:** 2026-09-22
**Status:** accepted; decision 3 amended twice the same day, once the page
it describes existed to look at. **The second amendment supersedes the
first** -- read them in order at the end.

## Context

§12 has asked since v0.3 what the tenth visitor in a queue sees, with a
deadline of v0.7. The pace itself cannot be changed: Codeforces allows one
request every two seconds, an API key does not raise that, and spreading
requests over several addresses would break its rules. Since 2026-09-18 a sync
is two requests — the whole history, and the rating history — so ten visitors
arriving together is 20 requests and 40 seconds for the last of them.

What has never been decided is the **order**. Today every sync runs in a thread
of its own (`sync.start_sync`), and `api_client.RateLimiter` hands the next
time slot to whichever thread asks for it, so requests interleave and all ten
visitors finish near the 40-second mark together.

**Interleaving was never chosen.** It is what falls out of one thread per sync
plus one shared limiter. It was also the right behaviour until 2026-09-13:
while a sync paged the history a thousand submissions at a time, jobs differed
in size — a dozen requests for a long history against two for a short one — and
interleaving stopped one long history from holding up everybody behind it. ADR
0004's amendment made a sync one request for the whole history, and every job
has been the same size since, so the protection has had nothing left to
protect.

§12's arithmetic, sitting there undecided ever since: finishing one job before
starting the next leaves the last visitor's wait unchanged at 40 seconds, cuts
the average from 31 seconds to 22, and the first visitor's from 22 to 4.

## Decision

**1. One sync at a time.** A single worker thread takes jobs from the `jobs`
table in the order they were created. That table already recorded what was
pending; it becomes the queue.

**2. The progress page says where the visitor is and how long it will be** —
position in the queue, an estimate in seconds, and a countdown that moves
between polls and is corrected by every poll.

**3. A returning visitor whose rows are still stored sees their previous
results at once**, labelled with when they were synced, while a fresh sync runs
behind them. This is §12's option (c).

**4. Under a rush, anybody with stored rows is served from them and everybody
else waits**, with the estimate above. The queue has no cap.

## Alternatives

**Keep interleaving.** Defensible only while jobs differ in size, which they no
longer do. Its cost is that every visitor waits as long as the last one.

**Cap the queue** — past some number of waiting visitors, tell newcomers to
come back later. It protects the experience by turning away exactly the
strangers §9 counts, at the one moment they all arrive.

**Never show stale results**, the other half of §12's (c). Honest, and it
throws away the one case that is cheap to serve: the returning visitor, who is
the visitor §9's second criterion is about.

**Fetching only a returning visitor's newest submissions.** Dropped on
2026-09-13: under one request per history it saves no request, and stopping at the
first submission already stored misses a verdict that changed after it was
stored.

## Consequences

- **The estimate is honest because the pace is deterministic.** Two requests a
  job, two seconds a request, one job at a time: four seconds for each job
  ahead, plus what is left of the one running. `api_client` retries a failed
  request up to three times, waiting 2 then 4 seconds, so an estimate can be
  tens of seconds late in the worst case. Each poll corrects it, and the page
  must not promise what it cannot know — a countdown that reaches zero and
  keeps waiting is the failure to design against.
- **Head-of-line blocking returns the day jobs stop being the same size.**
  Simulated on 2026-09-13: one ten-request job ahead of nine two-request ones
  costs 38 seconds on average one at a time, against 34 interleaved. A job of a
  different
  shape — a deeper fetch, a second endpoint — makes this worth recomputing.
- **Decision 3 depends on ADR 0017's disk.** Until it is attached a spin-down
  wipes the rows, so almost every visitor is a first visitor and the path
  exists without being taken. It becomes the common path the day the site is
  paid for.
- **Stale results need a visible timestamp** and a page that says plainly that
  the numbers are from then. *(As finally amended below: it says that in a
  line that also gives the position, the estimate and the end of the sync, and
  keeps saying it.)* Making the state look deliberate is §7.1's
  unhandled-states work at v0.8; the sentence itself has to exist at v0.7, or
  the page lies.
- **One worker means one stuck job holds the queue.** A single request is
  already bounded — three attempts at a 10-second timeout with waits between,
  about 36 seconds at worst — so nothing hangs forever, but the job as a whole
  wants its own limit when error handling is written in this milestone.
- **The progress page shows a position rather than a count.** It lost the count
  on 2026-09-13, when one request replaced paging (§6); a position is the
  number a waiting visitor actually wants.

## Amendment — 2026-09-22: the visitor presses the button

*Superseded the same day by the amendment below. Kept because the argument
in it is still the argument, and because a decision record that quietly
drops the version it changed its mind about is worth less than one that
does not.*

Decision 3 said a returning visitor's stored page is served at once "while a
fresh sync runs behind them". Built and looked at, that is wrong in a way the
words hid.

**It was not their decision.** The page announced the sync after starting it,
which is not the same as being asked. Nobody but the visitor knows whether
they have solved anything since the last sync, so nobody but the visitor can
say whether two more requests are worth making.

**And those two requests come out of a queue everybody shares.** That is the
part that matters at the moment this ADR was written for. Decision 4 is about
the day a blog post sends a crowd: under the original wording, every returning
visitor who merely opened a page added two requests in front of somebody who
was actually waiting. The amendment makes that case strictly better -- a
returning visitor costs nothing at all unless they ask.

**What the page does now.** It shows what is stored, says which sync the
numbers are from when they are older than the freshness window, and offers a
button. Pressing it queues the sync and lands on the progress page, where the
visitor sees the same position and estimate as anybody else. If a sync for
that handle is already running -- theirs from a minute ago, or another
visitor's -- the page offers a link to that job instead of a button that would
queue a second.

**A form, not a link.** A GET that starts work is followed by whatever walks
the page: a browser prefetching what it thinks will be clicked, a crawler, a
link checker. Each would take a turn in the queue. A POST cannot be followed
by accident, and it redirects to the progress page so that reloading does not
ask again.

**The button is offered inside the freshness window too**, without the
sentence about old numbers. Somebody who solved a problem two minutes ago is
exactly the person who wants it, and the ten-minute window would otherwise
tell them to wait for no reason.

**What it costs.** A returning visitor's page stays stale until they press the
button, where before it refreshed itself. Accepted: the click sits where the
knowledge is, and the page no longer spends anybody else's place in the queue
to answer a question that was not asked.

## Amendment — 2026-09-22, later: automatic again, and visible

The button was the wrong answer to a right complaint. The complaint was that
the visitor could not tell what was happening: the page said a sync was
running, once, at the top, and then never mentioned it again -- no idea how
long, no idea whether it had finished, nothing to do but reload and guess.
Making them press a button answers that by removing the thing rather than
showing it.

**So the sync is automatic again, and the page shows it while it happens.**
Under the timestamp the numbers belong to:

    ● Re-syncing, 2 syncs ahead of yours — about 12 seconds.
      The numbers below are from the sync above.

It counts down, and it keeps itself current: the browser asks
`/progress/<job>/status` for the line again on the interval the line itself
carries -- two seconds at the front of the queue, ten at the back. When the
sync finishes the line becomes "Fresh numbers are ready — show them", and the
asking stops. When it fails it says so plainly, and the asking stops. A
visitor who reads the page for a minute is told three times over what is true.

**The line is one template, `_sync_line.html`, rendered by both the page and
the endpoint.** The endpoint answers with the line, not with numbers, so there
is no second copy of the sentence in JavaScript to drift out of step with the
first. The fragment carries its own state and its own next interval, so the
script knows nothing about the queue's arithmetic either.

**Without JavaScript the line is still there**, with the position and the
estimate the page was built with. It stops changing, which is the only thing
that is lost, and every word on the page remains true.

**What this keeps from the button, and what it gives back.** The queue
argument in the amendment above stands: a returning visitor who merely opens a
page spends two requests in front of somebody waiting for a first sync. It is
accepted deliberately now, because the freshness window already limits it to
one refresh per visitor per ten minutes, and because the alternative charged
every returning visitor a click and a wait for something they will almost
always want. **The lever, if launch day proves it wrong:** lengthen the
freshness window, or start automatically only while the queue is short and
offer the button beyond that. Recorded here so it is a trigger rather than a
surprise.

**What is gone with the button:** a visitor inside the freshness window has no
way to force a refresh. Two minutes after solving something they see the old
numbers with no control to press. Re-adding the button for that case is a
half-hour of work and the ADR is unchanged by it; nobody has asked yet.
