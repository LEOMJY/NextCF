# usaco-next — Specification

**Status:** draft
**Written:** 2026-08-11
**Author:** Leo Ma

Working name. Change it if a better one appears before v1.0 ships.

---

## 1. What it is

A website that tells a USACO student which problem to solve next.

You enter your Codeforces handle. It reads your public submission history,
works out which topics you are strong and weak at, and recommends problems
that should be just hard enough — roughly a 70% chance you solve them. It also
shows you the topic breakdown it computed, because that is useful on its own.

## 2. Who it is for

High-school students training for USACO, roughly Bronze through Gold, who
already practise on Codeforces.

Not competitive programmers in general. Specifically people in that position.
Every design decision should be made for that person.

## 3. Why it should exist

Codeforces lets you filter the problemset by rating, but that rating is the
average difficulty across everybody — not the difficulty for you. USACO Guide
gives every student the same fixed curriculum. Neither one knows that you are
fine at greedy and weak at trees, and neither remembers that you learned
segment trees in June and have since forgotten them.

Nothing found so far models an individual student's per-topic skill and picks
problems against it.

## 4. How it works

Two separate things run. They are not the same program.

```
  BACKGROUND SCRIPT — run manually, occasionally
  ────────────────────────────────────────────────
    1. fetch every problem from the Codeforces API
    2. fetch ~2000 public users' submission histories
    3. write them to the database
    4. fit the model on that data
  ────────────────────────────────────────────────
                       |
                 [  database  ]
                       |
  WEB APP — runs whenever someone visits
  ────────────────────────────────────────────────
    1. visitor types a handle
    2. fetch that handle's submissions from the API
    3. store them
    4. estimate the visitor's skill per topic
    5. predict solve probability for unattempted problems
    6. show the 5 closest to the target probability
  ────────────────────────────────────────────────
```

Training data comes from ~2000 strangers' public histories, not from the
visitor's own submissions. The visitor's history is used only to locate them
inside a model that was learned from the crowd.

The site never runs or judges anybody's code. Users solve problems on
Codeforces; this reads the outcome from the public API.

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
- No difficulty ratings for USACO's own problems. That is v2.0 and it needs
  real users producing data first.
- No spaced repetition / review scheduling. Also v2.0.

## 6. Data

Three tables. Everything else is computed on demand, not stored, so there is
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
```

Derived and deliberately not stored: per-topic skill estimates, solve
probability predictions, recommendation lists.

## 7. Stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python | Half known already, and every library needed for the modelling later is Python |
| Web framework | Flask | Smallest thing that works; large amount of beginner material |
| Database | SQLite | A single file on disk. Nothing to install, nothing to run |
| Pages | Jinja templates (ships with Flask) | Lists and tables. No JavaScript build step needed |
| Hosting | Railway or Render | Connects to GitHub, redeploys on push |

Explicitly rejected: React (pages are lists; not worth learning a build system
for), FastAPI (more concepts before anything runs), PostgreSQL for local
development (nothing to gain yet).

Known risk: most hosting platforms wipe the filesystem on redeploy, which
would delete a SQLite file. Resolve at v0.1 — either a host with a persistent
disk, or PostgreSQL for the deployed copy only.

## 8. Assumptions

Written down because they are guesses, not facts, and should be revisited.

1. **70% is roughly the right difficulty target.** Taken from learning
   research (desirable difficulty; the "85% rule", Wilson et al. 2019). Not
   established for competitive programming. Testing this properly is a v2.0
   experiment.
2. **Codeforces skill transfers to USACO.** Plausible since USACO students
   already practise there, but unverified.
3. **A submission with verdict "OK" means the problem was learned.** Ignores
   solving after reading an editorial, or after five attempts.
4. **Public Codeforces histories are representative** of the students this is
   aimed at. Selection bias is likely: harder problems are attempted mostly by
   stronger users, so naive difficulty estimates will be biased.

## 9. How we will know it worked

v1.0 is done when all three hold:

1. The model predicts solve/fail on held-out submissions with **lower log loss
   than the rating-only baseline**, and that number is written down.
2. At least **20 people who are not the author** have used it.
3. It is live at a URL and stays up.

Second-order, once recommendations have been acted on: **calibration.** Of the
problems recommended at 70%, roughly 70% should actually get solved. If the
figure is 45%, the model is overconfident and the probabilities are wrong.

## 10. Milestones

| Version | Does | Target |
|---|---|---|
| v0.1 | Enter a handle, see your submissions. Deployed. | end Aug |
| v0.2 | Cache API calls | early Sep |
| v0.3 | Per-topic solve counts | mid Sep |
| v0.4 | Baseline recommender — rating only | late Sep |
| v0.5 | Evaluation harness; measure the baseline | early Oct |
| v0.6 | First real model, scored against the baseline | mid Oct |
| **v1.0** | **First public release** | **late Oct** |
| — | Users, feedback, USACO contest season | Dec–Feb |
| v2.0 | Rebuild what was wrong, using real usage data | spring |

## 11. Open questions

- **Cold start.** What is shown to somebody with 3 submissions? Probably fall
  back to the rating-only baseline. Decide at v0.6.
- **What counts as "solved"?** Solved on the first try, or after five attempts
  and an editorial? The API does not distinguish. Affects everything.
- **SQLite persistence in production.** See §7.
- **How USACO problems get ratings at all**, given USACO publishes no
  submission data. Probably user self-reporting. v2.0.
