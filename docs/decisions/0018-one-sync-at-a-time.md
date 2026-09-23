# 0018 — One sync at a time, and a progress page that can count

**Date:** 2026-09-22
**Status:** accepted; decisions 3 and 4 amended the same day, once the
page they describe existed to look at -- see "Amendment" at the end

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
  the numbers are from then. *(As amended below, it says that and offers a
  button, rather than announcing a fetch it started by itself.)* Making the
  state look deliberate is §7.1's unhandled-states work at v0.8; the sentence
  itself has to exist at v0.7, or the page lies.
- **One worker means one stuck job holds the queue.** A single request is
  already bounded — three attempts at a 10-second timeout with waits between,
  about 36 seconds at worst — so nothing hangs forever, but the job as a whole
  wants its own limit when error handling is written in this milestone.
- **The progress page shows a position rather than a count.** It lost the count
  on 2026-09-13, when one request replaced paging (§6); a position is the
  number a waiting visitor actually wants.

## Amendment — 2026-09-22: the visitor presses the button

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
