# 0017 — Visit records: SQLite on a paid disk, and the payment waits for launch

**Date:** 2026-09-22
**Status:** accepted

## Context

§9's second criterion — 50 people who are not the author have used the site,
and 20 of them have come back — is the only one of the three that cannot be
recovered after the fact. A model can be refitted and a number recomputed; a
visit that was never recorded is gone.

§7 has carried the reason since 08-11 and ADR 0007 sharpened it: Render's free
instance loses every file it wrote on a redeploy, on a restart, and whenever it
spins down after 15 minutes without traffic, and a free instance cannot attach
a persistent disk. §12 has carried the question with a deadline of v0.7, before
any stranger visits.

Prices and free-tier limits move, so they were checked on 2026-09-22 rather
than remembered:

| | what free gives | what paid costs | the catch |
|---|---|---|---|
| Render web service | spins down after 15 idle minutes, about a minute to wake; 750 instance hours per workspace per month | Starter $7/month, 512 MB, 0.5 CPU, always on | a free instance cannot have a disk |
| Render persistent disk | — | $0.25 per GB per month | paid instances only, and a disk ends zero-downtime deploys |
| Render Postgres | 1 GB, one per workspace | Basic-256mb $6/month plus $0.30 per GB | **a free database expires 30 days after it is created** and is deleted 14 days later |
| Neon — hosted Postgres | 0.5 GB per project, 100 compute-hours and 5 GB of transfer a month; passing a limit suspends compute and deletes nothing | usage-based | scales to zero after 5 idle minutes, and that cannot be turned off |
| Supabase — hosted Postgres | 500 MB, two projects | $25/month | **a free project pauses after a week without activity** and is restored by hand |
| Turso — hosted SQLite | 5 GB, 500M rows read and 10M rows written a month | $4.99/month | metered on rows scanned rather than requests; the smallest supplier of the three |

Two of those are disqualified by their own documentation. Render's free
Postgres expires inside a month, and these records have to outlive months.
Supabase pauses after a week without activity, which is exactly the state a
site with no users is in most days — it would be paused on the morning the
blog post goes out.

## Decision

**1. `nextcf.db` stays a single SQLite file, and gains a `visits` table.** No
second database, no second SQL dialect, no network hop on the path that records
a visit.

**2. Before the first stranger arrives, the service becomes a Starter instance
with a 1 GB persistent disk**, and the database file moves onto that disk.
$7.25 a month.

**3. The payment waits until then.** Development continues on the free
instance, and that costs nothing, because this decision needs no storage code:
the file is SQLite either way, and the only thing that changes on the day it is
paid for is the path it lives at, which comes from configuration. Every visit
recorded before that day is the author's own, and §9 excludes the author.

**4. A visit records both identities** — the handle that was looked up, and a
random visitor id kept in a first-party cookie. "50 people used it" has to
include somebody who read the landing page and left, and "20 came back" has to
survive a person using two handles.

**5. Nothing else about a visitor is stored**: no IP address, no user agent, no
referrer. What `/privacy` has to describe is then short enough that somebody
will read it.

## Alternatives

**Visits only, in a free hosted database** (Neon or Turso), with `nextcf.db`
left as the cache that may vanish. The serious contender, and genuinely free.
Rejected for what it leaves behind rather than what it costs: the web app still
sleeps, so the nightly re-sync scheduled in this same milestone has no process
to run in at night, and a returning visitor's submissions are still wiped
several times a day, so ADR 0018's (c1) — showing a returning visitor their
stored results at once — cannot work. It also adds a driver, a second dialect,
a network round trip on every visit, and a third party that `/privacy` must
name.

**Turso in particular** is the strongest of the free options and is worth
recording: it speaks SQLite, and its `/v2/pipeline` endpoint takes SQL over
HTTPS with a bearer token, so it needs no client library — the standard library
is enough. It still loses on the two consequences above.

**Render's own free Postgres.** Out on its own documentation: expires 30 days
after creation.

**Third-party analytics** (GoatCounter, Umami and the like). No schema change
and no storage decision, and it breaks §7.1's rule that everything a page needs
is served from this site, because the CDNs that serve such scripts are
unreliable in mainland China, where a large share of the audience is. It also
cannot answer "did this handle come back", so §9's number would be somebody
else's definition of a returning visitor.

**The handle alone, with no cookie.** Simpler, and it raises no consent
question at all. It cannot count a visitor who read the landing page and left,
which is where most of the 50 will stop, and it counts one person's two handles
as two people.

**A cookie alone.** Counts people and cannot connect a visit to what was looked
up, so nothing can be learned later about what a returning visitor did.

**Accepting that §9's second criterion cannot be measured.** It is a third of
the definition of done.

## Consequences

- **The $7.25 buys three things, and the visit records are only one of them.**
  The cold start ADR 0003 deferred "until before launch" — about a minute for
  the first visitor after a quiet spell — ends on the same day, and it ends at
  exactly the moment §9 depends on, when a blog post sends people at once. And
  the nightly re-sync (ADR 0007) cannot run at all on an instance that is
  asleep at night: a scheduler thread inside a sleeping process does not wake
  up.
- **A disk ends zero-downtime deploys.** Render stops the old instance before
  starting the new one, so every push makes the site unavailable for a few
  seconds. It replaces a minute of cold start several times a day, so the trade
  runs the right way.
- **1 GB, growable, never shrinkable.** `dataset.db` holds 4,000 full histories
  in 680 MB, about 170 KB a user, so 1 GB is a few thousand visitors of cache.
- **The cookie is first-party, random, and used for nothing else**:
  `SameSite=Lax`, `Secure`, 180 days, no sharing, nothing cross-site. Whether
  it needs a consent line or falls under an audience-measurement exemption is a
  `/privacy` question in this same milestone, and the fallback if that goes
  badly is decision 4 without the cookie.
- **§9's counts exclude the author**, by handle and by a short list of visitor
  ids kept in configuration rather than in the database.
- **`/privacy` now has a definite subject**: a public handle, a random id, the
  times of visits, nothing else, on this project's own disk, removable on
  request.
- **The free instance keeps wiping the file until the disk is attached.**
  Nothing §9 counts is lost, but the visits table cannot be trusted for
  anything before that day, and the first thing to verify after paying is that
  the file really is on the disk.
- **The prices above are dated.** Render's free-Postgres expiry and Supabase's
  pause are the kind of term that changes; if this is reopened they get checked
  again rather than quoted from here.
