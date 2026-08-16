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

Three programs sharing one database. They are not the same process and they do
not run at the same times.

```
  api_client.py   Codeforces API — rate limiting, retries, backoff
  db.py           schema and queries
  sync.py         fetch one user's history, as a resumable background job
  collect.py      bulk collection of ~2000 users, run manually
  model.py        skill estimation and solve-probability prediction
  evaluate.py     the harness — train/test split, scoring
  web.py          routes and pages
  scheduler.py    nightly re-sync of users already known
```

```
  BULK COLLECTION — run manually, takes about an hour
  ─────────────────────────────────────────────────────
    collect.py  →  api_client.py  →  database
    fetch every problem, then ~2000 users' histories
    resumable: dies at minute 40, restarts at minute 40
  ─────────────────────────────────────────────────────
                          |
                    [  database  ]
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
  SCHEDULER — nightly
  ─────────────────────────────────────────────────────
    scheduler.py → re-sync users seen in the last 30 days
  ─────────────────────────────────────────────────────
```

Two things drive the shape of this. First, fetching a user with 2000
submissions takes tens of seconds, and a bulk run takes about an hour —
neither fits inside a web request, so both must be background jobs with
progress that the page can poll. Second, any job that long **will** be
interrupted, so job state lives in the database and work resumes rather than
restarting.

Training data comes from ~2000 strangers' public histories, not from the
visitor's own submissions. The visitor's history is used only to locate them
inside a model that was learned from the crowd.

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

Four tables. Everything else is computed on demand, not stored, so there is
only one copy of the truth.

```
users
  handle         text     — Codeforces handle, unique
  cf_rating      integer  — their Codeforces rating, may be absent
  target_prob    real     — difficulty target, default 0.70
  first_seen     datetime
  last_synced    datetime

problems
  id             text     — contestId + index, e.g. "1234A"
  name           text
  rating         integer  — Codeforces' own rating, often absent
  tags           text     — comma separated for now

submissions
  id             integer  — Codeforces' submission id
  handle         text     — who submitted
  problem_id     text     — which problem
  verdict        text     — "OK", "WRONG_ANSWER", "TIME_LIMIT_EXCEEDED", ...
  submitted_at   datetime

jobs
  id             integer
  kind           text     — "sync" or "collect"
  target         text     — which handle, or which batch
  state          text     — "pending", "running", "done", "failed"
  progress       integer  — how far through, so work can resume
  started_at     datetime
  error          text     — why it failed, if it did
```

Derived and deliberately not stored: per-topic skill estimates, solve
probability predictions, recommendation lists.

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
| Scheduling | A timed loop, or the host's cron if it has one | Nightly re-sync |
| Web server | Waitress | Flask's built-in server is development-only. Pure Python, so the deployed setup also runs on Windows and can be tested before pushing |
| Hosting | Render | Connects to GitHub, redeploys on push. Free tier, at the cost of sleeping when idle — see `docs/decisions/0003-hosting.md` |

Explicitly rejected:

- **React, and React component or animation libraries** — the pages are a
  form, a progress bar, and a list of five problems. React buys interactivity
  that is not needed, at the cost of npm, a build step, bundling and
  deployment complexity. Looking professional is a CSS problem, not a
  framework problem. Reconsider only for the v1.5 pet system, where animation
  would actually earn its place.
- **FastAPI** — more concepts before anything runs.
- **PostgreSQL locally** — nothing to gain yet.
- **asyncio / concurrent requests** — the Codeforces API allows roughly one
  request every two seconds, so the rate limit dominates and concurrency buys
  nothing. 2000 users takes about an hour either way. Adding async would be
  complexity with no benefit.
- **A job queue library (Celery, RQ)** — needs a separate server process and a
  message broker. One worker thread and a database table does the same job at
  this scale.

Known risk: most hosting platforms wipe the filesystem on redeploy, which
would delete a SQLite file. Either a paid persistent disk, or PostgreSQL for
the deployed copy only.

Moved from v0.1 to **v0.2**, when `db.py` first exists. v0.1 stores nothing, so
there is no data to lose and the question cannot be answered by testing yet.
Deploying an app with no database first is deliberate: it separates "does the
deployment pipeline work" from "does the database survive a redeploy", and
debugging those together is much harder than debugging them in sequence.

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

The React rejection in §7 was re-examined against this section and stands: SVG
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
| v0.3 | Bulk collection of ~2000 users — rate limited, resumable | mid Sep |
| v0.4 | Per-topic solve counts; rating-only baseline recommender; topic-breakdown chart | late Sep |
| v0.5 | Evaluation harness; the baseline number written down | early Oct |
| v0.6 | First real model (logistic / Rasch), scored against the baseline; `/how` | late Oct |
| v0.7 | Nightly re-sync, logging, error handling, tests; `/privacy` | early Nov |
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
- **SQLite persistence in production.** See §7.
- **What happens when a sync job is interrupted mid-user?** Partial data in the
  database is worse than none. Decide at v0.2.
