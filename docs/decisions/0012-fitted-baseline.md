# 0012 — The rating-only baseline is fitted to the data, not Elo's formula

**Date:** 2026-09-17
**Status:** accepted, except the event it predicts — **provisional**, pending
§12's "what counts as solved?" (see the last section)

## Context

§9 defines success as a model that predicts solve/fail "with lower log loss than
the rating-only baseline". So the baseline is not a stepping stone; it is the
yardstick. A baseline that is too weak makes any model look good, and §9's
number then says nothing. v0.4 builds it, and the recommender on the results
page runs on it until the model replaces it.

The obvious candidate is Elo's formula, `1 / (1 + 10^(-gap/400))`, because
Codeforces ratings are Elo-style. It was measured before anything was built,
against 1,578,181 first attempts in `dataset.db` — one per (user, canonical
problem), with the user's rating **at the time** from `rating_changes`, as
ADR 0009 requires:

| user − problem | first try accepted | eventually accepted | Elo says |
|---|---|---|---|
| ≤ −800 | 37% | 82% | 1% |
| −600..−401 | 43% | 88% | 5% |
| −400..−201 | 45% | 91% | 15% |
| −200..−1 | 50% | 93% | 36% |
| +0..+199 | 58% | 95% | 64% |
| +200..+399 | 65% | 97% | 85% |
| +400..+599 | 72% | 98% | 95% |
| +600..+799 | 77% | 99% | 98% |
| ≥ +800 | 83% | 99% | 99% |

Elo is several times too steep under either reading of "solved". Where it says
1%, a third of first attempts succeed. People attempt a hard problem when they
already have a good chance at it — after reading the editorial, or because it
is in their strong topic — which is the selection effect §8's assumption 4
predicted, measured.

A first draft of this measurement had the two middle columns identical in every
row. That was a bug, not a finding: it used SQLite's rule that a bare column in
a `MIN()` query comes from the row holding the minimum, and that rule holds only
when the query has exactly one `min` or `max`. It had two. The version above
numbers each user's attempts with `ROW_NUMBER()` and depends on no such rule.

## Decision

**The baseline is a logistic curve in the rating gap, fitted to the data.**

```
P(solve) = sigmoid(a + b · (user_rating − problem_rating) / 100)
```

- **Fitted by maximum likelihood**, Newton's method, written out in `model.py`
  — two parameters do not need a library, and every step of the fit is
  readable. On `dataset.db`: `a = 0.2550`, `b = 0.1215`, log loss 0.639 over
  1,578,181 attempts.
- **One observation per (user, canonical problem)**, not per submission: a
  recommendation is a problem, and three wrong answers then an accepted one are
  one decision to try it. Aliases are folded first (ADR 0010).
- **The rating at the time of the first attempt**, never today's.
- **Fitted on counts per distinct gap**, not on 1.5 million rows. Ratings are
  integers and problem ratings are multiples of 100, so there are a few
  thousand distinct gaps, and for logistic regression those counts carry all
  the information there is: the answer is identical, and the fit is instant.
- **Stored in `baseline.json`**, committed, and loaded on first use. A check
  refits from `dataset.db` and fails if the file no longer matches — the same
  pattern ADR 0011 uses for the React bundle, for the same reason.

**The recommender** scores every problemset problem the visitor has not solved,
with their current rating, and shows the five nearest their target probability.
Ties — hundreds of problems share each rating — go to the newest contest.

**Provisional: the event is "first submission accepted".** See the last section.

## Alternatives

**Elo's formula, unfitted.** The table above rejects it. Worse than being
inaccurate, it would make §9 dishonest: any model at all would beat it, and the
win would come from calibration rather than from knowing about topics, which is
the only claim §3 makes.

**"Eventually accepted" as the event.** Its curve runs from 82% to 99% across
1,600 rating points — people keep submitting until the problem falls, so it
barely depends on difficulty. A 70% target does not exist anywhere on it; the
fitted curve puts 70% at problems **1,318 points above** the user, far outside
the data, where the number is extrapolation and nothing else.

**scikit-learn.** Would give the same two numbers. Not installed, and §7
already records that prebuilt scientific packages are uncertain on this Python.
For two parameters the hand-written fit is shorter than the install notes, and
it is the part of this project that most needs to be understood rather than
called.

**A curve per rating stratum.** §9 reports per stratum, and five curves would
be a stronger baseline. Not rejected — deferred to the harness at v0.5, where
the baseline's exact form is part of the evaluation protocol. One curve is the
simplest defensible baseline, and simpler is right for a yardstick until there
is a measured reason otherwise.

## Consequences

- **`baseline.json` must never score §9's test set.** It is fitted on *all* of
  `dataset.db`, including whatever v0.5 holds back for testing. The harness has
  to refit the baseline on its training portion only; using the committed file
  would give the baseline a look at the answers, and nothing would warn anyone.
  The page's curve and the harness's curve are different objects, and both
  have to exist.
- **Log losses are not comparable across events.** "Eventually" scores 0.207
  and "first try" 0.639, and the lower number means nothing: an event that
  happens 94% of the time is easy to predict whatever the model. §9's
  comparison is only meaningful between predictors of the *same* event.
- **The page says exactly what the number means**: "a first submission from
  somebody at your rating is accepted about 70% of the time". A bare "70%" lets
  the reader supply a meaning, and the two meanings above differ by 1,800
  rating points.
- **Everybody at one rating is shown the same five problems.** That is not a
  flaw in the baseline; it is the baseline. §3's complaint about sorting by
  rating is exactly that it treats everyone at a rating as the same person, and
  the page says so in a sentence. The v0.6 model's job is to stop doing it.
- **At 70%, low-rated users hit the floor.** The curve puts an 1100-rated
  user's 70% at 613; there are no problems below 800, so they are shown 800s.
- **The hard end of the curve is optimistic for a recommendation.** It is
  fitted on problems people chose. A problem the site chooses for them has no
  editorial-reading, strong-topic selection behind it, so the real chance on a
  hard recommendation is probably lower than printed. Measurable only once
  recommendations are acted on — §9's calibration, second-order.
- **The first instance of §12's "how does what the model learned reach the
  server?"**, in miniature: two numbers in a committed file. It does not settle
  that question for v0.6, where the result may be too large to commit, or need
  refitting on a schedule.
- **The web app now fetches the problemset when it starts** (ADR 0010), in a
  background thread started by the two entry points and never by importing the
  module, so the checks stay off the network.

## The open part: what event, and what target

§12 scheduled "what counts as solved?" for v0.5. The recommender cannot choose
a problem without it, so it arrived at v0.4. Recorded here as provisional,
because it is the author's decision and was not made in this ADR.

The two choices are coupled. Under "first try", with this curve:

| target | a 1100 user is shown | a 1500 user | a 1900 user |
|---|---|---|---|
| 70% | 800 (floor; 613 on the curve) | ~1000 | ~1400 |
| 60% | ~1000 | ~1400 | ~1800 |
| 50% | ~1300 | ~1700 | ~2100 |

So the 70% in §1 and §8 means problems about 500 points *below* the user's
rating under the only event where 70% exists at all. Common practice advice is
the opposite direction — a little above your rating — which this curve puts
near 50%. §8 already calls 70% a guess "not established for competitive
programming"; this is the first measurement that bears on it.

**Provisional choice: "first try", target unchanged at 70%.** "First try" is
the only event with enough range to predict and to recommend from, and it gives
the v0.5 harness a clean label for every attempt. The target is left alone
because it is a product decision stated in §1, and changing it belongs to the
author.
