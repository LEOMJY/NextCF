# 0027 — The target moves by a staircase, once per plan

**Date:** 2026-09-28
**Status:** accepted

## Context

Since ADR 0021 every press of "too hard" or "too easy" moved the visitor's
target 5 points at once. Two things made that wrong.

**Plans (ADR 0026).** A plan keeps its five until the visitor asks for the
next, and its target is fixed when it is made. So several presses in one
plan are all answers about the same five, at the same target. Counted one
by one, three presses on one plan moved the target 15 points before the
visitor had seen a single problem chosen at the new one.

**What a press means.** The author noticed that "too easy" moves the target
and teaches the model nothing: a problem called too easy at 50% was really
easier than 50% for them, yet the next plan's chances are on the same
uncorrected scale. Two readings of the button were set apart. It can be a
preference ("I want harder"), or evidence ("your 50% for me is wrong"). For
choosing problems the two are nearly the same: a shift δ in a person's
log-odds and a target moved from 50% to sigmoid(−δ) pick the same five. They
differ in the number the page shows, and in how large a step should be.

So the step size was measured rather than guessed (devlog, 2026-09-28;
`evaluate.py offsets`). On validation, how far off the topic model is about
one person has a real spread of **4.2 points** at 50%, luck taken out:
25% of people are off by more than 5 points, 8% by more than 7.5, 2% by
more than 10. The rating-only baseline's spread is 9.6. About half of a
person's offset lasts from one quarter to the next. And one plan's five first
attempts cannot tell a model that is right from one 4 points off: 5/5 or
0/5 happens by luck 6% of the time either way.

## Decision

The author decided:

1. **One step per plan.** A plan's presses are counted together when it
   ends: "too easy" points harder, "too hard" easier, and the majority
   decides. A tie, or no presses, moves nothing.
2. **The step adapts.** Moving the same way as last time, it grows by half:
   2.5 → 3.75 → 5.6 → 8.4 points. The author chose ×1.5 over the usual ×2
   because a person's real error is rarely large, and the measurement then
   backed it.

Decided from the measurement, when the author asked for what had been
proposed:

3. **The first step is 2.5 points**, about 80 rating points on the baseline.
   It was 5, which is larger than most people's real error. Three steps the
   same way cover what 95% of people are off by.
4. **Turning round halves the step**, the standard rule. The answer is
   between the last two places, so this is binary search with a person as
   the judge. Steps stay between 1 and 10 points, and the target between
   30% and 65% as before.
5. **Solves do not vote.** First-try results were part of the design until
   the measurement showed one plan's results are mostly luck. The model
   already learns from solves, through the visitor's history, at every
   sync. The staircase listens to presses only, so nothing is counted twice.
6. **The page shows the model's chance, not a corrected one.** The buttons
   move where the next five aim. For three people in four the model is
   within 5 points, so its number is usually close. Correcting it by
   presses would mix a person's reading of a problem into a number that can
   otherwise be checked (ADR 0024). The page says so under the table: "The
   buttons move where the next five aim, not the chances: those come from
   your own history, and change as your solves arrive."

Each list keeps its own staircase: overall in `users` (`target_step`,
`target_direction`), each topic in `topic_targets` (`step`, `direction`).
The move is written in the same transaction that ends the plan, and only
by the request that ended it, so a double-click moves the target once.

## Alternatives

**Keep 5 points per press.** Simple, and wrong twice over, for the reasons
above.

**Correct the chance by presses** (a per-person offset shown on the page).
With one global offset it picks the same problems as moving the target, so
the only change is the number shown. That number would stop being the
model's, and could no longer be checked against what happened.

**Let first-try results vote.** Designed, then measured, then dropped: one
plan's results cannot see a typical error. If the recommendations record
(ADR 0024) later shows larger errors on site-chosen problems, results
pooled over several plans are where to look again.

**×2 growth.** The textbook choice. It overshoots when errors are small,
and they are.

## Consequences

- **A press moves nothing until the plan ends.** The page says at once
  where the next five will aim, and it gets that from the same function
  that makes the move (`web.next_move`), so the two cannot differ.
- **Targets are no longer multiples of 5.** They are shown as whole
  percentages.
- **Every number here is a first choice.** 2.5, ×1.5, ½, 1 and 10 were
  set from data about self-chosen problems, and the site chooses for its
  visitors (ADR 0023), where errors may be larger. The plans table records
  every plan's presses and every move, and that is where they get tuned
  once there are real users, if the disk keeps it (ADR 0017).
- **The measurement's own method was corrected the day it was made.** Its
  first version found 4.1 points. Checked against made-up people with a
  known spread (`tests/check_offsets.py`), it found less than half the true
  spread when people had 20 attempts each. The method was changed, and the
  number re-measured: 4.2. The conclusion did not change, but it was not
  safe to assume it would not.
