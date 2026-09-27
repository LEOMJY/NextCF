# 0028 — Skip, and undo one answer

**Date:** 2026-09-28
**Status:** accepted

## Context

Since ADR 0027 the buttons under a problem do two jobs: they take the problem
off the plan, and when the plan ends they steer the difficulty. A review of
the site the same day found two things that stopped fitting.

**Not wanting a problem is not a judgement of its difficulty.** Somebody who
has read the editorial, who does not want an interactive problem today, or
who finds a statement unreadable had two ways to get rid of it: call it too
hard or too easy, which moves the target for a reason that has nothing to do
with difficulty, or swap all five. ADR 0026 had recorded "skip" as not asked
for yet. Once presses steered the target, the reason to wait was gone.

**A slip could not be taken back on its own.** The buttons were 16 pixels
tall on a phone. A marked row had no buttons, and the only undo was "put
back the N problems I hid", which un-hides every one of them and clears
every answer in the running plans with it.

## Decision

The author chose to add skip. From that choice:

1. **"Skip" is a third answer.** It hides the problem and settles it in the
   plans that hold it, exactly like the other two, and it is not a vote:
   `model.plan_direction` counts only "too easy" and "too hard". It takes
   one of the 50 places a handle keeps (ADR 0021), and "put back" returns it
   with the rest.
2. **Every marked row has "undo".** It takes back that answer alone: the
   problem is un-hidden and goes back to "to do" in the plans still running,
   so it counts for nothing when they end. Ended plans keep what was said
   while they ran, as with "put back". `POST /results/<handle>/undo`.
3. **The buttons became targets a finger can hit.** At least 24 by 24 pixels
   for any pointer, without moving anything on the page, and 44 on a touch
   screen, where the rows grow a little to make the room.

## Alternatives

**A skipped problem comes back in a later plan**, instead of being hidden.
Closer to "not now". Turned down for now because the week-long rest already
does that for a swapped plan (ADR 0026), and a problem someone has read the
editorial of should not keep returning. "Save for later" was also offered on
2026-09-27 and was not chosen.

**Undo only through "put back".** Simple, and it throws away every other
answer to recover one.

**A confirmation before each press.** It would make every deliberate press
slower in order to catch a rare slip. Undo catches the slip after the fact
and costs nothing otherwise.

## Consequences

- **The first migration that rebuilds a table.** The answers are listed in a
  `CHECK` on `dismissals.reason` and `plan_problems.outcome`, and SQLite
  cannot change a `CHECK`. Both tables are rebuilt: a new table made to the
  new definition, every row copied in, the old one dropped, the new one
  renamed into its place, all in one explicit transaction (`db._migrate`).
  On the live server both tables were empty; `dataset.db` gets the same
  rebuild, of empty tables, at its next refresh.
- **Three words under each problem**, where there were two. Still under the
  name rather than in a column, for the reason in ADR 0021.
- **Skips are counted separately from votes in what the plans record**, so a
  later look at how the staircase behaved can tell "didn't want it" from
  "wrong difficulty".
