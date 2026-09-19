# 0016 — Visitors with no rating start from 1000

**Date:** 2026-09-19
**Status:** accepted

## Context

§12's cold-start question was half answered on 2026-09-18: somebody with a
few rated attempts is folded in like anybody else. The other half was a
visitor with **no rating at all** — never in a rated contest. The model is
built on the rating at the time of each attempt, the gap to the problem and
the level, and without one the page said so and recommended nothing.

That visitor is not rare. It is everybody before their first contest, which
is exactly when "what should I practise?" is the question.

The data already holds their situation. The harness drops the first attempts
people made before their first rated contest ("no rating at the time", ADR
0013): 47,842 in the training period, 15,952 in validation, 15,659 in 2026.
Those are what an unrated visitor's history looks like — and because every
decision so far excluded them, the 2026 ones have never been scored, and are
a fresh test for this one.

## Decision

**An unrated visitor is served by the topic model from a starting rating of
1000** (`model.UNRATED_START`), and folded in from every first attempt they
have made, like anybody else. `rating_now()` returns 1000 for them;
`visitor_attempts()` takes each of their attempts at 1000 instead of dropping
it. The page says so: the chances start from 1000 and move with their own
practice. Without `topic_model.json` the rating-only fallback still has
nothing to go on, and the page still says that.

**Chosen on validation.** Round three fitted on the training period, as the
harness fits it; then validation's pre-rating attempts predicted the way the
site would serve an unrated visitor, for several starting ratings:

| starting rating | log loss, model + the visitor's own history |
|---|---|
| (always guessing the usual rate, 51.6%) | 0.6888 |
| 800 | 0.5981 |
| **1000** | **0.5927** |
| 1200 | 0.5936 |
| 1400 — Codeforces' own start | 0.5990 |
| 1600 | 0.6081 |

The rating-only curve, given any of these starting ratings, scores 0.68–0.72:
no better than guessing, because the rating it needs is exactly what is
missing. The topic model does about as well for unrated attempts as it does
for rated ones (0.6010), because most of what it knows is about the problem —
its own record, its topics — and the rest comes from the visitor's practice.

## Alternatives

**1400, what Codeforces itself computes a new account from.** The consistent
choice after ADR 0015, which reads the rating Codeforces computes with — and
measurably too hopeful: problems it put at 55% were solved first time 49% of
the time. A new account's first contest usually takes its rating down from
1400, and the people who have not entered one yet are, on average, weaker
than the number the system starts them at.

**Estimating the rating from the visitor's solved problems.** That is what the
fold-in already does: a visitor's own number b moves them from the start in
proportion to the evidence. The starting rating only decides where somebody
with little history sits.

**Still showing nothing.** Honest, and it turns away the visitors who most
need the answer.

## Consequences

- **A sample drawn on its future, again.** Everybody in these attempts reached
  1000–1999 later (ADR 0009), so they are the successful part of the unrated.
  Real unrated visitors are likely weaker on average, which is one more reason
  to take the lower of 1000 and 1200, the two that validation cannot tell
  apart.
- **Only never-rated visitors change.** A rated visitor's attempts from before
  their first contest are still dropped, as in training and evaluation, so the
  check that the website builds exactly what the harness built still holds
  for everybody it compares.
- **Tested once on 2026**, with this configuration committed first: the
  15,659 pre-rating attempts of 2026, which no decision has seen, predicted by
  round three fitted on everything before 2026 and frozen there — no monthly
  refits, so the number can only understate the site. The result is recorded
  below, whatever it is.
