# 0014 — The topic model: what it is, how it is fitted, what each part is worth

**Date:** 2026-09-18
**Status:** accepted

## Context

On 2026-09-18 the author asked for the most accurate prediction achievable, by
any means, as the foundation for everything the recommender does after it. That
brought v0.6's model forward, ahead of the React work v0.4 still owed.

What "accurate" can mean was settled first. One first attempt is a coin toss
even to a model that knows the true probabilities, so "perfect" is not on
offer. What is: the lowest log loss on data the model has never seen, and
probabilities that mean what they say — when it says 50%, half succeed. The
protocol that measures both is ADR 0013.

## Decision

A logistic model of the first attempt, additive in its parts:

```
logit P = gamma[context] + beta * gap + hinges(gap)       context, the rating gap
        + w_level * rating level + w_exp * experience     who is attempting
        + w_position[A..G+] + w_trend * years             the problem's slot; time
        + mean over the problem's tags of tau[tag]        how hard the topic is
        + d[problem]                                      how hard THIS problem is
        + b[user]                                         the user, beyond rating
        + mean over the problem's tags of s[user, tag]    the user in each topic
```

**Fitted by block coordinate Newton, in pure Python.** Every parameter outside
the global block touches only its own attempts, so each gets an exact
one-dimensional Newton step; the global block — context intercepts, the gap,
and the extra columns — gets a full Newton step. The objective, log loss plus
an L2 penalty per group, is convex: one minimum, and every run finds the same
one, bit for bit (checked).

**Exact centring moves** after every sweep. An additive model has directions
along which parameters trade a constant without moving a single prediction;
the loss is flat there, only the penalties change, and the minimum along each
has a closed form. Coordinate steps crawl along them — the first version hit
its 60-sweep ceiling on every fit; with the moves, 5 to 13. They matter for
more than speed: each level ends up holding what the level below shares, which
is all a problem or a user the training data never saw can fall back on. Seven
directions: a topic's share of its users' skills and of its problems'
difficulties into the topic; a position's share of its problems into the
position column; a user's share of their topics into the user; and the users,
problems and topics into the intercepts. A check recomputes the objective from
the parameters alone and compares it with the running value, which is what
proves the moves move nothing.

**Regularisation per group, chosen on validation:** topic 10, problem 3, user
30, user in topic 30.

**The website's path is the fold-in.** Topic, problem and global terms come
from the crowd; a visitor's own terms are fitted from their history with
everything else held fixed, an attempt counting half as much for every 180
days of age. The fold-in reproduces the joint fit exactly (checked), and the
website builds a visitor's inputs with the same SQL and the same derivations
the harness used — 25 real users, every field of every attempt compared.

**Refitted monthly.** Worth +0.0031 on validation, the largest single gain after
the problem and level terms: half of any month's attempts are on problems too
new for a frozen model to know anything about.

## What each part is worth — validation, 276,535 attempts

Log loss, population-weighted (ADR 0013). The gain is against the row above.

| | log loss | gain |
|---|---|---|
| rating-only baseline | 0.6533 | |
| + context (contest, practice, virtual) | 0.6515 | 0.0018 |
| + topic difficulty | 0.6456 | 0.0059 |
| + **each problem's own difficulty** | **0.6195** | **0.0261** |
| + the user, beyond their rating | 0.6148 | 0.0046 |
| + the user in each topic | 0.6147 | 0.0001 |
| + older history halves every 180 days | 0.6139 | 0.0008 |
| + the gap's curve may bend | 0.6126 | 0.0012 |
| + **the user's rating level, not only the gap** | **0.6058** | **0.0069** |
| + experience | 0.6049 | 0.0009 |
| + position in the contest | 0.6044 | 0.0005 |
| + a straight line in time | 0.6038 | 0.0005 |
| refitted on the 1st of every month | 0.6007 | 0.0031 |

Taking each first-round group back out of the full first-round model: each
problem's difficulty +0.0240, the user +0.0044, topic difficulty +0.0029, the
user in each topic +0.0002. Half-lives around the chosen one: 730 days 0.6143,
365 0.6141, 180 0.6139, 120 0.6139, 90 0.6140, 60 0.6144.

Calibration went the wrong way through the first round, 1.8 points for the
baseline to 3.0, and came back to 1.0 by the end of the second: the time line
is what fixed it. A calibration layer on top made log loss worse (0.5996 to
0.6006 on the last three months of validation) and is not used.

## The test — 527,388 attempts in 2026, scored once

| | baseline | topic model |
|---|---|---|
| **weighted total** | **0.6535** | **0.5989** — 8.4% lower |
| 1000–1199 | 0.6684 | 0.6043 |
| 1200–1399 | 0.6540 | 0.6018 |
| 1400–1599 | 0.6416 | 0.5913 |
| 1600–1799 | 0.6328 | 0.5906 |
| 1800–1999 | 0.6225 | 0.5824 |
| calibration gap | 4.8 points | 1.6 points |

Lower in every stratum. §9's first criterion is met.

The model is still slightly pessimistic about 2026: it said 45.2% and 47.9%
happened, 55.1% and 57.1%. The baseline, for comparison, said 45.6% where 51.0%
happened.

## What the numbers say about the product

**The problem, more than the person.** A problem's own first-try record,
measured from the crowd, is worth more than every other part together. Its
rating says how hard it is to solve; its record says how treacherous it is to
submit — edge cases, output formats, limits that invite a timeout — and rating
does not carry that.

**Topics, as a property of the topic.** Constructive algorithms is harder on a
first try than its rating says, for everybody. That is worth something.

**Not, measurably, as a property of the person.** The user in each topic — §3's
"fine at greedy and weak at trees" — is worth +0.0002: it helps, and it is
nowhere near the story. The likeliest reason is the one §8's fourth assumption
named. People choose their own problems; somebody weak at trees attempts the
tree problems they can do, and the weakness hides inside the choosing. A
recommender that chooses *for* them removes that, which makes it the one
setting where the signal could surface. It stays in the model and is measured
again once recommendations are acted on.

## Alternatives

**A library** (scikit-learn, statsmodels). Not installed, uncertain on this
Python (§7), and the fit is the part of the project most in need of being
understood rather than called. Pure Python fits 1.58 million attempts in about
three minutes.

**Gradient-boosted trees or a neural network.** Often more accurate on tabular
data; not chosen, for three reasons. The objective stops being convex, so the
number stops being reproducible without care. A visitor who was never in
training cannot be folded in, and the fold-in is the only way the website can
use a model at all. And the result explains nothing, where `/how` is meant to
show what the model knows.

**Per-user topic skill as a low-rank factorisation** — users strong in graphs
are probably strong in trees, so sharing evidence across related topics might
recover what the independent version cannot. Not tried: non-convex, and the
independent version's best regularisation was heavy, which says the signal is
small against its noise. The first thing to try if the topic question is
reopened.

**A frozen model**, fitted once on the collected dataset. 0.0031 worse on
validation, and worse every month it ages.

## Consequences

- **The dataset is re-collected and the model refitted every month.** That is
  what the monthly-refit row costs: about four and a half hours of collection,
  unattended, then `model.py fit-topic` and a commit. `collect.py` has no
  refresh mode yet — it skips users already collected — so that has to be
  built before the first refresh.
- **`topic_model.json` is how the model reaches the server**: the crowd's part,
  keyed by tag name and problem id, 244 KB, committed like `baseline.json`. It
  answers §12's question for this model, not for every model: a larger one may
  not fit in a repository.
- **Syncs fetch the rating history**, a third request. Without it a visitor's
  past attempts would be judged at today's rating, and anybody who has climbed
  would be judged weaker than they are. *Amended 2026-09-18:* `user.info` was
  then dropped, since the rating history and the submissions already carry
  what it was fetched for, so a sync is two requests again (spec §12).
- **Guard rails on the shipped model.** Straight lines are only safe inside the
  data they were fitted to. The level term is held to the middle 99.8% of
  levels the model saw — roughly 350 to 2370 — and the page tells a visitor
  outside it that the chances are an extrapolation. The time line stops
  183 days after the newest attempt, so if the monthly refits stop, predictions
  stop drifting. Neither applies during evaluation, so no measured number
  changed.
- **Without `topic_model.json` the site falls back to the baseline**, and the
  page says which of the two chose the problems.
- **The recommendations are only as calibrated as the model is in 2026**: about
  two points pessimistic in the middle of the range. A problem shown as 50% is
  closer to 52% in practice. Whether that holds for problems the site chooses,
  rather than ones people chose, is §9's calibration question, answerable only
  once recommendations are acted on.
