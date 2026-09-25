# 0021 — "Too hard" and "too easy": two words that move one number

**Date:** 2026-09-24
**Status:** accepted

## Context

The recommender aims at a 50% first-try accept (ADR 0012, ADR 0013) and every
visitor gets that same target. A UX walk-through on 2026-09-24 scored the site
29/40 against Nielsen's heuristics and put "user control" at 2 out of 4 for one
reason: somebody who finds the five problems too hard has nowhere to say so.
The only exit is to close the page.

§7.1 has planned a control for this since v0.4 — "a target-probability control
that re-ranks both" is in its list of interactivity that is in scope — and
`users.target_prob` has been in the schema since v0.2 waiting for it, unread,
with a comment saying so. What was missing was the decision about what the
control actually is.

## Decision

**Two buttons under every recommendation: "too hard" and "too easy".** They are
a judgement about the problem, and the site takes them as two things at once:

**1. That problem goes away, and stays away.** Stored in a new `dismissals`
table, not kept for the page: a problem somebody has just pushed away coming
back on the next reload reads as not having listened.

**2. The visitor's difficulty target moves one step**, `model.TARGET_STEP` =
0.05 of probability. "Too hard" asks for *easier* problems, which is a *higher*
probability of solving them — the inversion this feature will be got backwards
in, which is why it is one named function (`model.nudge_target`) with a check
of its own rather than a sign inside a route.

**Five points, because that is what a visible change costs.** On the fitted
baseline (ADR 0012: a = 0.2550, b = 0.1215 per 100 rating points) 50% sits 210
rating points above the visitor and 55% sits 45 above, so one press is worth
about **165 rating points**. Small enough that two presses are not absurd,
large enough that the five problems visibly change — which they must, or the
button looks broken.

**The ladder runs 0.30 to 0.65**, and stops there. 0.65 rather than 0.70 is
deliberate: 0.70 is the value `users.target_prob` was created with, and keeping
it unreachable leaves "this number was never chosen by anybody" something the
data can still say.

**The preference belongs to the handle**, in `users.target_prob`, with
`users.target_chosen_at` recording that it was chosen. The timestamp is the
point: the column's own default is 0.70 and a visitor could also choose 0.70,
and without the timestamp those are the same number.

**An undo, for the dismissals only.** The page offers "put back the N problems
I hid" when there are any. It does not touch the target, because hiding a
problem and moving the target are two different things and the way back from
the target is the other button.

**Forms and POSTs.** Two submit buttons sharing one name and carrying different
values, so it works with scripting off; a redirect afterwards, so a reload does
not repeat it; and no GET that changes anything, because a GET is followed by
prefetchers, crawlers and link checkers.

## Alternatives

**One pair of buttons for the whole list**, rather than per problem. Fewer
controls, and it asks the visitor to judge five problems at once when they have
just looked at one. Judging is easier per item; the *effect* is global either
way, which is why the per-item press moves the shared target.

**Only move the target, and store nothing.** Half a day cheaper: no table, no
undo, no schema change. Rejected because at ±0.05 a dismissed problem can still
sit within the window at the new target, so the thing the visitor pushed away
can come back on the next page — the one outcome that makes the button feel
ignored.

**Only hide the problem, and leave the target alone.** Precise, and it answers
"not this one" without answering "these are all too hard", which is what
somebody pressing it three times is saying.

**Store the preference per browser** (in `localStorage`, like the remembered
handle). It would avoid two people who look up one handle sharing a target.
Rejected: the server picks the problems, so the target has to reach the server
anyway, and §5 says a handle is the only identity this product has. The
consequence is accepted below rather than engineered around.

**A slider, or a "show me harder" link with a number.** More precise and more
to understand. Two words that name the complaint are what somebody can press
without reading anything.

## Consequences

- **Anybody can change anybody's target**, because there are no accounts (§5).
  Two people looking up `tourist` share one. What it affects is which five
  problems that page shows, and pressing the other button undoes it, so the
  worst case is a stranger seeing an unexpected list once. Named here rather
  than solved, because solving it means accounts.
- **This is the first record of a visitor judging a recommendation.** Which is
  what §9's calibration needs, and what the v1.5 pet system would be built on:
  `dismissals` says which problems were offered and rejected, and why. The
  matching record of what was *offered and taken* still does not exist — see
  the open question below.
- **`users.target_prob` is read again** after being dead since 2026-09-18, and
  `target_chosen_at` is the column that made reading it safe without rebuilding
  the table.
- **The recommendation pool gains a second exclusion.** It already dropped
  solved problems by canonical id (ADR 0010); dismissals are excluded the same
  way and for the same reason.
- **Nothing here tells the model anything.** A dismissal changes what this
  visitor is shown; it does not change what the model believes about the
  problem, and it never reaches a fit. Feeding it back is a separate decision
  that needs its own evaluation, because "users say this is hard" and "this
  problem is hard" are different claims and the first is selected by who
  pressed the button.
- **Still open: recording what was recommended.** Until the site stores the
  five it showed, it cannot say "you solved two of the five" and cannot answer
  §9's calibration question for problems it chose. That is the next piece, and
  the natural place for it is beside this table.
