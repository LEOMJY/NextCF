# NextCF — Specification

**Status:** draft
**Written:** 2026-08-11
**Author:** Leo Ma

---

## 1. What it is

A website that tells a competitive programmer which problem to solve next.

You enter your Codeforces handle. It reads your public submission history,
works out which topics you are strong and weak at, and recommends problems
that should be just hard enough — roughly a 70% chance you solve them. It also
shows you the topic breakdown it computed, because that is useful on its own.

## 2. Who it is for

Anyone who practises on Codeforces and does not know what to solve next.
Realistically that skews toward the 1000–1900 rating range, where people are
actively training rather than competing at the top.

Chosen over the narrower "USACO students" audience for one reason: the tool
requires a Codeforces handle, and many USACO students do not have one. An
audience that cannot supply the data the product needs is the wrong audience.

Positioning is a separate question from the audience. The product is built for
Codeforces users generally; contest preparation, including USACO, is one use
case worth mentioning when launching, not a constraint on the design.

## 3. Why it should exist

Codeforces lets you filter the problemset by rating, but that rating is the
average difficulty across everybody — not the difficulty for you. USACO Guide
gives every student the same fixed curriculum. Neither one knows that you are
fine at greedy and weak at trees, and neither remembers that you learned
segment trees in June and have since forgotten them.

Nothing found so far models an individual user's per-topic skill and picks
problems against it. Static problem "ladders" exist, but they are the same
list for everybody and most are unmaintained.

**The differentiator is measurement, and it is the only one.** Recommenders in
this space are not hard to build, and several have been. What none of them
publish is evidence that their recommendations beat sorting the problemset by
rating. §9 is therefore not an optional extra at the end — it is the reason
this project exists. Skip it and this is a website.

Still to verify: search for existing Codeforces recommenders and training
tools, and if abandoned ones turn up, work out why they were abandoned.

## 4. How it works

Two places, two database files, and the files never meet. Bulk collection and
model fitting happen on the author's own machine, into `dataset.db`. The web app
runs on the server, on `nextcf.db`. Both files use the same schema.

```
  api_client.py   Codeforces API — rate limiting, retries, backoff
  db.py           schema and queries
  sync.py         fetch one user's history as a background job, all or nothing
  collect.py      bulk collection of ~2000 users, run manually
  model.py        skill estimation and solve-probability prediction
  evaluate.py     the harness — train/test split, scoring
  web.py          routes and pages
  scheduler.py    nightly re-sync of users already known
```

```
  ON THE AUTHOR'S MACHINE — run by hand
  ─────────────────────────────────────────────────────
    collect.py  →  api_client.py  →  [ dataset.db ]
    fetch every problem, then ~2000 users' histories
    resumable: dies at minute 40, restarts at minute 40
    progress is printed to the terminal; no jobs rows

    model.py, evaluate.py  ←  [ dataset.db ]
  ─────────────────────────────────────────────────────

  ON THE SERVER
  ─────────────────────────────────────────────────────
                    [ nextcf.db ]
         a cache of public data; may vanish at any time (§7)
                          |
  WEB APP
  ─────────────────────────────────────────────────────
      /  landing page
         |    the pitch, and the handle input in the hero itself
         |    scroll past it for how it works; /how and /privacy in nav
         |
         |  enter handle
         v
      web.py  ──── starts job ────>  sync.py
         |                              |
         |  <── polls "done yet?" ──────┘
         v
    progress page
         |
         v
    results page  ←── model.py predicts, picks 5 near target
  ─────────────────────────────────────────────────────
                          |
  SCHEDULER — nightly, a thread inside the web app
  ─────────────────────────────────────────────────────
    scheduler.py → re-sync users seen in the last 30 days
  ─────────────────────────────────────────────────────
```

Two things drive the shape of this. First, fetching a user with 2000
submissions takes tens of seconds, and a bulk run takes about an hour —
neither fits inside a web request, so both must be background jobs with
progress that the page can poll. Second, any job that long **will** be
interrupted, so job state lives in the database. What that buys differs by
job: a bulk run resumes at the user it died on, while one user's sync is
written in a single transaction and simply runs again, because redoing it
costs tens of seconds — see `docs/decisions/0004-sync-interruption.md`.

Training data comes from ~2000 strangers' public histories, not from the
visitor's own submissions. The visitor's history is used only to locate them
inside a model that was learned from the crowd.

The training data gets its own file for two reasons. The server loses its disk
whenever the free instance restarts, which would take an hour of collection
with it. And the web app re-syncs any handle it is asked about, so a training
set sharing its file would change under the evaluation whenever somebody looked
up a user in it — and §9's number has to come out the same every time it is
computed. A separate file is a frozen snapshot, which is also the dataset §9
proposes to publish. See `docs/decisions/0007-dataset-file-and-job-cleanup.md`.

Only the web app may clean up abandoned jobs, because only it starts them. The
scheduler is a thread inside the web app rather than a program of its own, for
the same reason and because the host will not let a separate service read the
web app's disk. Same ADR.

The site never runs or judges anybody's code. Users solve problems on
Codeforces; this reads the outcome from the public API.

## 4.1 Pages

Five URLs. Two are the tool, three are everything else, and the split matters
because the landing page has a different job from the tool — see §7.1.

| URL | Job | Milestone |
|---|---|---|
| `/` | The pitch, **with the handle input in the hero itself** | v0.1 |
| `/progress/<job>` | Show a long job making progress without lying about it | v0.2 |
| `/results/<handle>` | Five problems, the probability on each, the topic breakdown | v0.1 crude, v0.4 real |
| `/how` | How the model works, and the §9 number | v0.6 |
| `/privacy` | What data is read, what is stored, how to have it removed | v0.7 |

### Why the input is in the hero, not behind a "start" link

§9 requires 20 people to come back a second time. A returning visitor does not
need the pitch again — they need to type a handle and leave. Putting the input
in the hero serves both audiences from one page: the returner types immediately
and never scrolls, the newcomer scrolls past it for the argument.

The alternative considered was a pure visual statement with a skip link, which
costs the returning visitor a click on every visit for no gain.

The cost is that the hero has to carry a strong visual statement *and* a form
field at the same time, which is harder to compose. Accepted.

Nothing on the landing page is compulsory reading. Scrolling is optional; the
tool is always one action away.

### Why `/how` is not an appendix

§3 states the differentiator is measurement and that it is the only one. The
number from §9 needs a permanent home on the site, not just a Codeforces blog
post that scrolls away. A visitor who wants to know whether to trust the
recommendations should be able to find out in one click.

### Deliberately not a page

**A changelog.** A tool with 50 users has nobody reading release notes. It looks
professional and is mostly a way to feel productive without shipping anything.
One line in the footer if wanted; a page is v2.0.

## 5. What it does NOT do

None of the following are in v1.0, regardless of how good they sound in
October. Anything added here must be argued for as a change to this document,
not slipped in while coding.

- No accounts, passwords, or login. A handle is the only identity.
- No mobile app.
- No running, judging, or sandboxing of code.
- No social features — no friends, leaderboards, or comparison to others.
- No hints, editorials, or explanations of problems.
- No AI chat, of any kind, anywhere.
- No changelog page — see §4.1.
- No knowledge tracing, bandits, spaced repetition, or USACO problem ratings.
  All v2.0 — see §11.

## 6. Data

Five tables. Everything else is computed on demand, not stored, so there is
only one copy of the truth.

```
users
  handle         text     — Codeforces handle, unique, primary key
  cf_rating      integer  — their Codeforces rating, may be absent
  target_prob    real     — difficulty target, default 0.70
  first_seen     text     — ISO-8601 UTC
  last_synced    text     — ISO-8601 UTC; NULL until a sync completes

problems
  id             text     — contestId + index, e.g. "1234A"; never parsed back
  contest_id     integer  — the contest half; absent for acmsguru
  problem_index  text     — the index half: "A", "E1", or in one contest "14"
  name           text
  rating         integer  — Codeforces' own rating, often absent

problem_tags
  problem_id     text     — which problem
  tag            text     — one tag, e.g. "dp"
                            one row per (problem, tag) pair

submissions
  id               integer  — Codeforces' submission id, primary key
  handle           text     — who submitted
  problem_id       text     — which problem
  verdict          text     — "OK", "WRONG_ANSWER", ...; absent while judging
  participant_type text     — "CONTESTANT", "VIRTUAL", "PRACTICE", ...
  submitted_at     text     — ISO-8601 UTC

jobs
  id             integer
  kind           text     — "sync"; the schema also permits "collect", which
                            nothing writes since ADR 0007
  target         text     — which handle, or which batch
  state          text     — "pending", "running", "done", "failed"
  progress       integer  — submissions fetched so far; drives the progress page
  started_at     text     — ISO-8601 UTC
  finished_at    text     — ISO-8601 UTC; NULL while the job is unfinished
  error          text     — why it failed, if it did
```

Derived and deliberately not stored: per-topic skill estimates, solve
probability predictions, recommendation lists.

**Dates and times are ISO-8601 UTC text**, e.g. `2026-09-07T21:20:00Z`. SQLite
has no date or time type, so the only choice is text or an integer count of
seconds since 1970. Text sorts and compares correctly given one fixed format,
and it is legible when the file is opened by hand — which is most of what
happens to this file between now and v1.0. The API supplies Unix seconds
regardless, so exactly one conversion happens on the way in.

**`last_synced` is the completeness flag**, not merely a cache timestamp. It is
NULL until a user's sync finishes, and it is written inside the same
transaction as that user's rows, so the two cannot disagree. Anything reading
submissions treats NULL as "no data for this user" rather than "this user has
no submissions" — see `docs/decisions/0004-sync-interruption.md`.

**Tags are their own table**, not a comma-separated column, because per-topic
skill is the axis the entire product works along — see
`docs/decisions/0005-tags-as-a-table.md`.

**`problems.id` is never parsed back into its parts.** It looks splittable at
the first letter, but contest 921 numbers its problems `01` to `14`, producing
ids like `92114` that could equally mean contest 921 or contest 9211.
`contest_id` and `problem_index` are stored as columns of their own, and a
`CHECK` rejects any row whose id disagrees with them. There is one row per
contest a problem appeared in, not one per problem — see §12.

**`participant_type` is stored now and unused until v0.6.** It records whether
a submission was made in-contest, virtually, or in practice, which §12's "what
counts as solved?" and §8's assumption 4 about selection bias both eventually
need. It is stored early because adding the column later is trivial while
*filling it in* later means re-fetching ~2000 users at two seconds a request —
the v0.3 collection run, done twice. The general rule: adding a column is
cheap, adding a column that must be backfilled from a slow external source is
not.

`progress` no longer implies resumption. Under ADR 0004 an interrupted sync
writes nothing, so there is no partial state to resume from; the column exists
to drive `/progress/<job>`.

## 7. Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.14 | Half known already, and every library needed for the modelling later is Python |
| Web framework | Flask | Smallest thing that works; large amount of beginner material |
| Database | SQLite | A single file on disk. Nothing to install, nothing to run |
| Pages | Jinja templates (ships with Flask) | Lists and tables. No JavaScript build step needed |
| Styling | Own CSS built on design tokens. No framework, no build step | Promoted from "classless framework" — see §7.1. A framework gives a floor but also a recognisable look, and "does not read as templated" is now an explicit goal. Three pages of hand-written CSS is roughly 200 lines and is fully ours |
| Charts | Server-rendered SVG from Jinja | The topic breakdown is the one thing a template cannot give us. SVG generated from the data needs no JavaScript library, no CDN, and no build step, and it renders in the launch screenshot |
| Background jobs | A worker thread plus the `jobs` table | Long work cannot happen inside a web request, and job state must survive a restart |
| Scheduling | A timed loop in a thread inside the web app | Nightly re-sync. Not the host's cron: a cron service on Render cannot read another service's disk, and a second program would break the job-cleanup rule — ADR 0007 |
| Web server | Waitress | Flask's built-in server is development-only. Pure Python, so the deployed setup also runs on Windows and can be tested before pushing |
| Hosting | Render | Connects to GitHub, redeploys on push. Free tier, at the cost of sleeping when idle — see `docs/decisions/0003-hosting.md` |

Explicitly rejected:

- **React, and React component or animation libraries** — the pages are a
  form, a progress bar, and a list of five problems. React buys interactivity
  that is not needed, at the cost of npm, a build step, bundling and
  deployment complexity. Looking professional is a CSS problem, not a
  framework problem. Reconsider only for the v1.5 pet system, where animation
  would actually earn its place.
  *Reopened 2026-09-12, before v1.0 rather than at v1.5 — see §12.*
- **FastAPI** — more concepts before anything runs.
- **PostgreSQL locally** — nothing to gain yet.
- **asyncio / concurrent requests** — the Codeforces API allows roughly one
  request every two seconds, so the rate limit dominates and concurrency buys
  nothing. 2000 users takes about an hour either way. Adding async would be
  complexity with no benefit.
- **A job queue library (Celery, RQ)** — needs a separate server process and a
  message broker. One worker thread and a database table does the same job at
  this scale.

**The server's database does not survive, and that is accepted until v0.7.**
Render's free instance loses every file it wrote whenever it redeploys,
restarts, or spins down after 15 minutes without traffic, and free instances
cannot attach a persistent disk (Render's docs, checked 2026-09-13). An earlier
version of this paragraph named only redeploys; spin-down means the file is
really wiped several times a day.

What that costs depends on what is in the file:

| Data | Comes from | If it is wiped |
|---|---|---|
| A visitor's submissions | Codeforces, in seconds | One re-sync. Accepted |
| The ~2000-user training set | An hour of API calls | Never on the server — `dataset.db` on the author's machine |
| Who visited, and when | Exists only on the server | §9's "20 have returned" cannot be measured |

So `nextcf.db` on the server is a cache that is allowed to vanish, and the
training data never goes there. The third row needs storage that survives — a
paid disk, or a hosted database — and it is due at v0.7, before any stranger
visits, because a visit that was not recorded cannot be recovered later. See
§12 and `docs/decisions/0007-dataset-file-and-job-cleanup.md`.

History: moved from v0.1 to v0.2 because v0.1 stored nothing, then carried past
v0.2 unanswered although the devlog twice said it was due before v0.3. Answered
at v0.3.

Known risk: the local install is Python 3.14, and the `py` launcher currently
defaults to the free-threaded build (`3.14t`) rather than the standard one.
Free-threaded builds are a separate binary target, and prebuilt packages for
numpy/scipy/scikit-learn — needed for the model in §9 — are not always
published for them. Create environments with the explicit interpreter, not the
bare launcher default. Revisit if an install ever fails with "no matching
distribution".

## 7.1 Design

Promoted to an explicit v1.0 goal, not a v0.8 afterthought. The stated target:
**it must not read as a student project.**

### Two surfaces, judged differently

An earlier draft of this section said animation reads as amateur. That is wrong
as stated, and the correction matters. Heavily animated studio work — the kind
collected in the GSAP showcase — is excellent and is made by professionals. Bad
animation reads as amateur; animation does not.

The distinction that actually applies here is what a given page is *for*:

```
LANDING PAGE — /  (page inventory in §4.1)
  Job: convince a stranger this is worth thirty seconds.
  This is a marketing surface. Expressive type, a strong colour decision,
  a memorable visual idea, motion — all legitimate here.
  It is also the page that appears in the Codeforces blog post screenshot,
  so it has the highest return of anything in this section.
  Constraint it does not get to ignore: the handle input lives in the hero,
  so whatever visual idea is chosen has to accommodate a form field.

THE TOOL — /progress, /results
  Job: return five problems and get out of the way.
  Someone waiting forty seconds on a job does not want cinema, and someone
  comparing five problems wants a table they can read. Calm, fast, legible.

Same tokens on both. The landing page uses them loudly and the tool uses them
quietly, so the two read as one product rather than two websites.
```

Linear's marketing site is animated; the Linear app is not. That is not a
contradiction, it is two kinds of page.

Realistic constraint, not a matter of taste: the showcase sites are weeks of
professional work, often with WebGL, custom illustration and custom type. What
*is* cheap to take from them — and accounts for most of the first impression —
is large confident typography, one decisive colour choice, generous space, and a
single clear visual idea.

### What causes the amateur read, on both surfaces

All static, all boring to fix:

- Browser-default fonts and default form controls
- Spacing chosen ad hoc, so nothing lines up and rhythm is absent
- Pure `#000` on pure `#fff`, or five unrelated colours
- Undifferentiated walls of text, no type hierarchy
- **Unhandled states** — a Flask traceback when a handle is mistyped is the
  single loudest tell on this list

### Design tokens — a system, chosen by the author

The requirement is that **a system exists and is not broken**, as CSS custom
properties in one file. Which system is a design decision and belongs to whoever
is designing.

```
type scale     a fixed set of sizes, from a ratio
spacing scale  a fixed set of steps
colour         a deliberate palette
font           a typeface chosen on purpose
radius/shadow  a decided value, or none
```

The reason this is not a constraint on creativity: the boldest sites run the
tightest systems. A brutal pink-and-yellow showcase site is bold because two
colours were chosen and then applied without flinching. The opposite — eleven
spacing values and nine font sizes — does not read as more creative, it reads as
unfinished, because the eye reads "arbitrary" as "not done yet."

An earlier draft of this section specified exact numbers (a 4/8/16/24/48/96 step
and exactly one accent colour). Those were a reasonable default presented as a
rule, and they are withdrawn. Pick the scale; then hold it.

**Picked on 2026-09-12**, from three directions built as working pages — see
`docs/decisions/0006-design-direction.md`. The system lives in
`static/style.css`: one monospace typeface, five type sizes, five spacing
steps, a dark canvas with a single accent, 3px radius, no shadow.

That is the **working** direction: it makes the v0.2 pages usable and
legible, and it is not necessarily the final look. The final direction is
revisited at the v0.8 design pass — see §12. Because every value is a token in
one file, changing type, colour and spacing later is a one-file change. Layout
can change too, at any point. It just means editing each page's template and
CSS, and any check that looks for specific elements, instead of one file.
That makes it the more expensive part of a late change of direction.

### Interactivity that is in scope

Three things, each because the product needs it rather than because it decorates:

1. **Topic-breakdown visualisation** (v0.4–v0.5). §1 already promises this and
   calls it useful on its own. It is also the only element on the site a
   template cannot produce, and it is the differentiator made visible. Highest
   return of anything in this section.
2. **The progress page** (v0.2). Already required — a job running tens of
   seconds is a product surface, and it is the moment of peak user attention.
3. **Solve probability on each recommendation** (v0.4). "70%" is the entire
   pitch; it earns visual weight.

### Out of scope on the tool surface

On the progress and results pages: scroll-triggered animation, parallax, page
transitions, custom cursors, animated counters. Not because they are amateur,
but because those pages are read under time pressure by someone who wants to
leave, and motion there costs attention without returning any.

**The landing page is not covered by this.** Motion is allowed there if it
carries the visual idea rather than decorating it. The limit on the landing page
is the budget below, not a rule about technique.

The React rejection in §7 was re-examined against this section and stood at
v0.2 (reopened 2026-09-12, §12): SVG
rendered from Jinja and a polling progress page need no client framework. If the
landing page ever wants motion, GSAP loaded from a CDN adds no build step.

### Budget, and what it comes out of

Design work for v1.0 gets **a fixed number of hours, set before starting, taken
from §9**. The mechanism is decided; the number is not yet — an earlier draft
put 15 hours here, but that figure was invented rather than estimated and is
withdrawn until it is worked out against the actual milestones.

That time comes out of §9. This is the trade being made deliberately: a tool
nobody trusts the look of does not get used, but §9 is the reason the project
exists, and a beautiful site with no evaluation is the failure mode this whole
document was written to avoid. If the budget overruns, design stops — not §9.

Worth stating plainly: for *this* product the strongest signal of seriousness is
not the CSS, it is publishing a number nobody else has published. Design makes
people willing to look. §9 is what they find.

## 8. Assumptions

Written down because they are guesses, not facts, and should be revisited.

1. **70% is roughly the right difficulty target.** Taken from learning
   research (desirable difficulty; the "85% rule", Wilson et al. 2019). Not
   established for competitive programming. Testing this properly is a v2.0
   experiment.
2. **Users want to be told what to solve.** Some people enjoy choosing, and
   some deliberately pick problems far above their level to learn new
   techniques. Unknown how large that group is.
3. **A submission with verdict "OK" means the problem was learned.** Ignores
   solving after reading an editorial, or after five attempts.
4. **Public Codeforces histories are representative** of the users this is
   aimed at. Selection bias is likely: harder problems are attempted mostly by
   stronger users, so naive difficulty estimates will be biased.

## 9. How we will know it worked

v1.0 is done when all three hold:

1. The model predicts solve/fail on held-out submissions with **lower log loss
   than the rating-only baseline**, and that number is written down.
2. At least **50 people who are not the author** have used it, and at least
   **20 have returned** after their first visit.
3. It is live at a URL and stays up.

### Stretch goals

Deliberately aimed at being the reference point rather than the fourth
product, because that target does not require anyone to switch tools:

- **Publish the evaluation** as a Codeforces blog post. The question "do
  problem recommenders actually beat sorting by rating?" is one this community
  keeps asking and nobody has answered with data.
- **Release the dataset and the harness.** Nobody has published a clean
  Codeforces submission dataset for skill modelling, a stated evaluation
  protocol, or baseline numbers. All three have to be built anyway; publishing
  them costs almost nothing and makes them the thing others measure against.
- **500 people try it, 50 return.** Achievable if the blog post lands.
- **Someone who is not the author uses the harness or the dataset.**

Explicitly not a goal: more weekly users than the incumbent. Optimising for
that means competing on landing pages and features, which is a losing fight
and would come out of the time budget for the model.

Second-order, once recommendations have been acted on: **calibration.** Of the
problems recommended at 70%, roughly 70% should actually get solved. If the
figure is 45%, the model is overconfident and the probabilities are wrong.

## 10. Milestones

| Version | Does | Target |
|---|---|---|
| v0.1 | Enter a handle, see your submissions. Deployed. | end Aug |
| v0.2 | Background job with a progress page; caching. Design tokens and base stylesheet — see §7.1 | early Sep |
| v0.3 | Bulk collection of ~2000 users into `dataset.db`, on the author's machine — rate limited, resumable | mid Sep |
| v0.4 | Per-topic solve counts; rating-only baseline recommender; topic-breakdown chart | late Sep |
| v0.5 | Evaluation harness; the baseline number written down | early Oct |
| v0.6 | First real model (logistic / Rasch), scored against the baseline; `/how` | late Oct |
| v0.7 | Nightly re-sync, logging, error handling, tests; `/privacy`; visit counting for §9, on storage that survives restarts | early Nov |
| v0.8 | Design polish pass and unhandled states — see §7.1 | early Nov |
| **v1.0** | **First public release** | **mid Nov** |
| — | Users, feedback, USACO contest season | Dec–Feb |
| v2.0 | See §11 | spring |

Dates assume 10–15 hours a week and include no slack. They will slip.

## 11. v1.5 and v2.0 candidates

Recorded so they can be refused now and reconsidered later with real usage
data. **None of these are v1.0.** Anything here that gets built early comes
out of the time budget for §9, which is the point of the project.

### Pet nurturing system — v1.5, spring

Solving a recommended problem earns coins. Coins buy pixel-art pets, which
have growth stages and are raised over time.

Why it is worth doing rather than dismissing:

- **It targets the weakest success criterion.** Good recommendations do not
  cause return visits — a good recommendation makes the user leave for
  Codeforces. Retention needs a separate mechanism, and gamification is the
  one that demonstrably works (Forest, Duolingo, Habitica).
- **It is a genuine differentiator.** The incumbent is a clean, serious tool.
  This is a different product rather than a worse copy, and the audience is
  largely teenagers who play games.
- **It produces a better experiment than the 70% test.** "Does gamification
  increase problems solved per week?" has a larger effect, appears within
  weeks rather than months, and is measurable from data already collected.

Design decisions already made:

- **Reward scales with difficulty**, specifically `coins ∝ 1 − P(solve)` using
  this project's own model. Otherwise users farm 800-rated problems. This also
  makes the economy depend on the probabilities being well calibrated, which
  ties the feature to §9 rather than bolting it on.
- **Shop before chests.** A shop where coins buy a chosen pet is far simpler —
  no rarity balancing — and avoids frustration. Random chests retain better
  because variable-ratio reward is strongly habit-forming, which is also a
  reason to be careful with an audience of teenagers. Add chests only after
  the shop proves people care.

Why it is not v1.0:

1. **It requires accounts.** A collection tied to a typeable handle is broken;
   anyone could spend anyone's coins. Verification without passwords is
   possible — the incumbent has users submit a deliberate compilation error
   within 60 seconds to prove handle ownership — but sessions and ownership
   are still real work, and §5 currently excludes accounts.
2. **Timing.** v1.0 is already mid-November. Adding this pushes into January
   and collides with USACO contest season, which the calendar exists to avoid.
3. **Dependency.** Gamification amplifies a working product and cannot rescue
   a broken one. If the recommendations are poor, rewards feel manipulative.
   The model has to be good first.

Known risk: art, animation and game feel have no natural stopping point, and
this is more enjoyable to build than debugging a likelihood function. It needs
a fixed slot, not an open-ended one.

### Per-topic recommendations

Pick a topic, get problems in that topic near the target probability. The
model already predicts per problem, so this is a filter over the same numbers.
The cost is the page, and the question of what happens when a topic has too
few unsolved problems near the target. Proposed 2026-09-13 as where the 3D
balloon interaction (§12) would lead. Not v1.0, where the results page shows
five problems overall.

### Knowledge tracing

v1.0 models a user as a snapshot: "weak at DP." Knowledge tracing models the
*trajectory*: weak at DP in June, solved eight DP problems in July, moderate
now, decaying by October without practice.

The standard approach (Bayesian Knowledge Tracing) treats each skill as a
hidden on/off state with four probabilities — learn, forget, guess, slip — and
updates the belief after every attempt. This is what makes the "you forgot
segment trees" idea in §3 actually work, and it is what makes spaced
repetition possible.

Needs: submission timestamps (already stored) and enough per-user history.

### Bandits (explore vs exploit)

v1.0 always recommends what the model currently thinks is right. But the model
is most uncertain about topics the user has never attempted — and those are
exactly where a hidden weakness might be.

That trade-off is the multi-armed bandit problem: exploit what you believe, or
explore what you don't know. Standard approaches are ε-greedy, UCB (favour
options you are uncertain about), and Thompson sampling.

Directly useful here, because a recommender that only suggests familiar topics
will never discover a gap.

### The 70% experiment

Assumption 1 is a guess. With enough users, randomly assign target
probabilities of 0.60 / 0.70 / 0.80 and measure who improves fastest — an A/B
test, where randomisation is what makes the result causal rather than
correlational.

Needs far more users than v1.0 will have. Attempting it at n=20 produces a
number that means nothing. Calibration (§9) is the version that works at small
scale and should come first.

### Spaced repetition

Schedule revisits of topics the knowledge-tracing model says have decayed.
Depends on knowledge tracing existing first.

### USACO problem ratings

USACO publishes no submission data, so ratings would have to come from users
self-reporting solves. Needs a user base first, which is why it is not v1.0.

## 12. Open questions

- **Cold start.** What is shown to somebody with 3 submissions? Probably fall
  back to the rating-only baseline. Decide at v0.6.
- **What counts as "solved"?** Solved on the first try, or after five attempts
  and an editorial? The API does not distinguish. Affects everything.
- **Where do visit records live?** §9 needs to know who came back, and on the
  free instance nothing written survives a spin-down (§7). A paid disk keeps
  SQLite and costs money every month; a hosted database costs nothing on some
  free tiers but brings a second SQL dialect and a network hop. Counting visits
  is not built at all yet either. Decide at v0.7, before anyone who is not the
  author uses the site.
- **How does what the model learned reach the server?** The model is fitted on
  the author's machine from `dataset.db`, which never goes to the server. What
  the site needs is the result — per-problem and per-topic numbers, small
  compared to the histories — and it has to arrive in a way that survives a
  restart. Decide at v0.6, when there is a result to move.
- **What does the tenth visitor in a queue see?** Every request from the web
  app waits its turn, one every two seconds (`api_client.RateLimiter`), so
  visitors syncing at the same time share that pace. Measured 2026-09-13: two
  histories synced together alternated requests and took 44 seconds between
  them. §9's launch is a blog post, which sends people at once, and ten visitors
  with long histories would leave the last one waiting minutes while the
  progress page says "0 submissions fetched". The pace cannot be raised; what
  can change is what the page says while a job is waiting, and whether a
  handle already stored is shown straight away. Decide at v0.7, with error
  handling.
- **One problem, two ids.** When a Div. 1 and a Div. 2 round run together,
  each shared problem gets an id in both contests: `1292A` and `1293C` are the
  same problem. `problemset.problems` lists only one copy, but a Div. 2
  contestant's submissions carry the other. In one real Div. 2 history checked
  on 2026-09-11, 29 of 230 solved problems were stored under an id the
  problemset does not list — one history is an example, not an estimate. A
  recommender drawing from the problemset would offer those users problems
  they have already solved, and the audience in §2 is mostly Div. 2. This is
  not a flaw in the id format, since any contest-plus-index scheme has it.
  Storing the id each submission actually used is what keeps it fixable: a
  mapping to the problemset's id can be built later from stored rows, without
  re-fetching anybody. Name matching alone will not build it correctly — the
  problemset holds seven different problems called "Elections", and a reused
  problem is not always in an adjacent contest (`1230D` appears in the
  problemset only as `1210B`). Decide at v0.4, before the first recommendation
  ships.
- **React for the front end?** §7 rejected it. Reopened 2026-09-12: a
  restrained use of React, with components and nothing showy, may be worth
  it for a site that is meant to have real design. What React changes is
  how interactive state in the browser is organised; how the site looks is
  still a CSS question either way. Three options:
  (a) stay with Jinja, own CSS, and small plain JavaScript or GSAP where
  needed. No build step.
  (b) React only for the interactive pieces (topic chart, results filtering,
  later the pet system), mounted into pages Flask still renders. Needs Node
  and a build step for one bundle; routes and templates stay.
  (c) React for the whole front end, with Flask returning JSON only. Every
  template is rewritten, the web-flow checks change, and deployment gains a
  build.
  Decide at v0.4, before the topic-breakdown chart is built. It is the first
  component where the answer changes what gets written.
- **Final design direction.** Terminal (ADR 0006) is the working direction,
  not necessarily the last one. Decide at v0.8, inside the design budget in
  §7.1. If (b) or (c) above is chosen, decide the stack first, because it
  changes what the design pass can do cheaply.
  A second round on 2026-09-13 built four landing directions from things the
  audience already knows (a problem statement, the rank colours, a calibration
  plot, ICPC balloons). Preferred: rank colours, then balloons. The rank colours
  read as stiff when used as large fields. They are the original saturated
  handle colours, with very uneven lightness. Retuning them is part of the
  decision.
- **3D balloons as the landing page's visual idea?** Proposed 2026-09-13: one 3D
  balloon per topic in the centre; clicking one makes it rise with the camera
  following, into that topic's recommendations. Material quality (light,
  reflection, latex or foil) is part of the requirement. To settle first:
  (1) the landing page does not know a visitor's topics until a handle is
  synced, so balloons before the input can only be generic topics;
  (2) per-topic recommendations are not a v1.0 page (§4.1, §11);
  (3) a camera flight on every visit costs the returning visitor §4.1
  protects, and the tool pages are meant to stay calm (§7.1).
  Three ways to build it, at very different cost: real-time 3D in the browser,
  3D rendered offline and played back as video or frames, or a no-code 3D tool
  with its own runtime. Decide at v0.8, after a prototype with a fixed time
  limit shows whether the material quality is reachable inside the budget.

### Answered

- **What happens when a sync job is interrupted mid-user?** *(asked 08-11,
  answered 09-07, at v0.2 as scheduled.)* One transaction per user: the whole
  history is fetched, then written and `last_synced` set in a single
  transaction, so an interruption leaves the database exactly as it was. The
  original framing of the question was subtly wrong. Partial data is not worse
  than none — partial data *indistinguishable from complete data* is, because
  every later reader believes it. Making completeness explicit is the fix, and
  once it is explicit, partial data is strictly better than none. See
  `docs/decisions/0004-sync-interruption.md`.
- **Which program may clean up orphaned jobs?** *(asked 09-11, answered 09-13,
  at v0.3 as scheduled.)* Only the web app. The cleanup is correct only when run
  by the program that starts jobs, at the moment it starts, and the web app is
  the only program that starts syncs. It moved out of `init_db()`, which every
  program calls, into `fail_orphaned_jobs()`, which only `web.py` calls. The
  problem was already reachable, not hypothetical: `sync.py` run by hand called
  `init_db()` and failed any sync the web app had running. `collect.py` writes
  no job rows, and the scheduler runs inside the web app. The alternative — a
  heartbeat that any program could check — was rejected as machinery for a
  problem with one program. See
  `docs/decisions/0007-dataset-file-and-job-cleanup.md`.
- **SQLite persistence in production.** *(a known risk since 08-11, due at v0.2,
  answered 09-13.)* The server's database is a cache that is allowed to vanish;
  the training set lives in `dataset.db` on the author's machine; data that
  exists only on the server waits for v0.7, above. Details in §7.
