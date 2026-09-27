# 0023 — Guard rails on what is offered: support, and the easier version first

**Date:** 2026-09-26
**Status:** accepted

## Context

The audit of 2026-09-26 ran the recommender exactly as the site runs it, for
60 users drawn from the dataset. 34% of its picks were 500 or more rating
points above the user. The median spread between the easiest and hardest of
the five was 1,000 points. 18 picks were a "hard version" whose easy version
the user had not solved. For users rated under 1300, the model gave a
2300-rated difficult version 51% and Watermelon (800) 38%. Pressing "too
hard" did not help: the easiest target on the ladder still left a quarter of
the picks 500 or more above the user.

The cause is spec §8's fourth assumption. The model is calibrated on
attempts people chose, and the site chooses for them. A problem's own
first-try record was learned from the people who decided to try it.

The author asked for the model to be fixed rather than for a rule based on
rating. The first candidate was an observable column, "solved the easier
version first". It was screened on validation with ADR 0015's method, and
it gained nothing (devlog, 2026-09-26). The reason is the finding: on
attempts people chose, the model is already right, even for those who
skipped the easy version, because they chose it knowing they could. The
error only exists on attempts nobody would have chosen. Data made of choices
cannot show it, so a fit on that data cannot remove it.

## Decision

**Two rules decide which problems may be offered.** Neither changes a
prediction. They keep the model to problems it has evidence about for this
visitor.

**1. Support.** A problem is offered only if at least **30** people rated
within **200** of the visitor attempted it. "Rated" means the rating
Codeforces computed with at the time of the attempt, the same level the model
reads. The author chose 30 over 60: 60 cut far-above picks to 12% instead of
17%, but left visitors at 800 or 2000 about 960 candidates. That is thin once
the choice narrows to a band around the target.

**2. The easier version first.** A later version (E2, E3...) is not offered
while an easier version of the same contest is still in the visitor's pool,
that is, not solved yet. An easier version the visitor has hidden is not in
the pool, so the harder one may be offered: they have said what they think
of the easy one.

**Outside the data, the nearest edge.** The dataset holds users rated
1000–1999, so almost nobody near 2400 attempted anything, and a strict rule
would give such a visitor an empty page. The ratings covered are the ones
where at least 1,000 problems pass the rule, 800–2100 today. A visitor
outside that range is looked up at its nearest edge, and the page says so.
This is the same idea as `level_range`, ADR 0014's guard rail on the model's
straight lines.

**Never an empty list.** If a rule would leave fewer than five problems, it
stands aside. The easier-first rule stands aside first; if support is lifted,
the page says the problems rest on less evidence.

**The evidence ships as `support.json`**: for each problem, how many people
attempted it at each rating, in bins of 100, about 470 KB. It is built from
`dataset.db` by `model.py build-support`, and by `model.py fit-topic`, so the
monthly refit keeps it in step with no extra step. A dataset-tier check
fails when it no longer matches the data, like `baseline.json`'s.

## Measured

On the same 60 users, through the site's own code:

| | picks 500+ above the user | later version before the easier one | spread of the five |
|---|---|---|---|
| before | 35% | 19 | 950 |
| after | **20%** | **0** | 800 |

The standalone measurement before building predicted 17%. The difference is
the rating used: the built rule uses the rating Codeforces computes with, as
the model does, where the estimate used the one it shows.

## Alternatives

**A rating window**, offering only problems within some distance of the
visitor's rating. It is transparent and would remove far-above picks by
construction. It was turned down by the author: it decides by the one number
the model was built to see past, and it leaves the model's error in place
inside the window.

**Change the model.** The screen above was the first attempt, and ADR 0015
recorded the general reason it cannot work offline. A self-selection
correction cannot be judged on data made of self-selection; it becomes
testable once the site records what it recommended.

**60 attempters** instead of 30: measured above, left thin.

**Filling in the uncovered ratings with the rule turned off.** Simpler, and
visitors at 2200 and above would have got the unguarded list. They are not
§2's audience, but a guard rail that disappears exactly where the model is
least sure is backwards.

## Consequences

- **20% of picks are still 500 or more above the user.** The remainder is
  mostly classic hard problems. 600E, rated 2300, was attempted by 227 people
  near 1491, because mid-rated people work through such problems from
  training lists and tutorials. Support cannot tell a problem people studied
  from one they could solve cold. Only a record of what was recommended, and
  what happened next, can.
- **The pool is smaller.** About 4,000 candidates for a visitor at 1500 and
  about 1,500 at 800. That is enough for five near the target, and it is
  why the rule stands aside rather than failing when it runs out.
- **The visitor can see the rule.** `/how` says what it is, with the
  threshold read from the code, and the results page says when it bent.
- **The model and §9's number are unchanged.** Every probability shown is
  the same number it was. The rules only decide which ones are shown.
- **The monthly refresh writes a second file**, and both are committed
  together.
