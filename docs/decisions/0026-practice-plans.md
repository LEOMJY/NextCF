# 0026 — Practice plans: the five stay until they are done

**Date:** 2026-09-27
**Status:** accepted

## Context

Until now the five on a results page were recomputed every time the page was
drawn. A sync, a press of "too hard", or a month's refit could replace all of
them. Nothing on the site remembered which five a visitor had been given,
or whether they did them. The author compared the incumbent's Training Lab,
where a plan of problems is kept, each problem is settled one way or another,
and past plans are listed. Two things the site lacked were named: the plan
is not recorded, and a returning visitor retypes their handle.

The second is answered without accounts (spec §5, reconsidered and kept): the
browser remembers the last handle, and the landing page offers to continue
as it. Proving a handle is yours is v1.5 (§11).

There is also a reason in §9. Its second criterion, 20 people who come back,
is the one a good recommender does not earn by itself: a good
recommendation sends the visitor to Codeforces. A plan that is still there
when they return, with the problems they solved ticked, is a reason to
return that does not depend on anything new having happened.

## Decision

The author decided the product questions:

**1. The five on a page are a plan, automatically.** The first time a list
is shown (the overall five, or one topic's), its five are kept as that
list's plan. There is no "start" button.

**2. Each problem in a plan is settled once:**
- *solved*: an accepted submission after the plan began, read from the
  synced history. The visitor presses nothing, and the tick appears after
  the next sync;
- *too hard* or *too easy*: the buttons, as before (ADR 0021). The problem
  is hidden everywhere and the list's target moves. The target now moves
  **for the next plan**; this plan keeps its five, and the settled one stays
  on the page marked, not replaced.

**3. A plan ends in one of two ways.** Every problem is settled: the plan is
complete and the page offers the next five. Or the visitor presses "swap
the five": an unfinished plan ends early. It never expires by itself.

**4. Past plans are listed**: when each began, which list it was, how many
were solved, how many were settled, and how it ended.

What follows from those, decided in the build:

- **One plan per list.** Overall and each topic (ADR 0025) keep their own
  plan and history, as they keep their own target. A partial unique index
  stops two active plans for one list, so two tabs opening a page together
  cannot create two.
- **A plan stores what the visitor was shown**: each problem's chance as
  computed, whether it passed the guard rail, and the target and the notes
  the list had when it was made. So the page says the same thing about a
  plan on every visit, and the notes about walls and scatter describe the
  five actually there.
- **"Solved" is derived, never stored.** It comes from `submissions`, the
  same way ADR 0024's report derives outcomes, so a rejudged verdict cannot
  leave the plan disagreeing with the history.
- **The record of what was shown stays** (ADR 0024). Plans are the
  visitor's; that table is the calibration sample, first showing only, and
  it keeps that job.
- **A plan keeps the ratings it was made at**: the one the chooser used,
  and the one Codeforces showed. The notes that explain the chances ("these
  use 1250", "an extrapolation", the baseline's "rated around 1400") read
  those, not today's. A contest in the middle of a plan moves the rating,
  and without this the page would explain five problems with a number they
  were not chosen with.
- **A press settles the problem in every running plan that holds it**, not
  only the list it was pressed on. Hiding is global (ADR 0021). Settled in
  one list only, the problem stayed "to do" in the other, with buttons that
  could no longer do anything, since the same answer said twice is ignored.
- **Solved beats a press.** Somebody who called a problem too hard and then
  solved it anyway solved it.
- **"Put back" is the undo for a press.** A settled row has no buttons, so
  putting the hidden problems back also returns them to "to do" in the
  plans still running. Ended plans keep what was said while they ran,
  because they are a record.
- **The button names the plan it ends.** A double-click sends two POSTs. By
  the second, the page may already have made the next plan, and without
  the id the second press would end that one too, before it was ever seen.
- **What a list's recent plans held sits out that list for a week.** Found
  by the checks: "swap the five" gave back the same five. Nothing about
  them had changed, so they were still the nearest to the target. Leaving
  out only the last plan's five would make repeated swaps alternate
  between two sets. Leaving them out for good would hide problems the
  visitor never pressed anything on, where "put back" cannot reach them. A
  week sits between the two, and a list with nothing else left gets them
  back rather than nothing. The length is a first choice
  (`web.PLAN_REST_SECONDS`), to be revisited with real use.

## Alternatives

**Manual start** ("start a plan"), like the incumbent. The page would have
to explain two states, a plan and a live list, and every visitor without a
plan would see the old behaviour. Turned down.

**Replace a settled problem at once**, so a plan always has five to do. A
plan would then never finish, and "you did this plan" would mean nothing.
Turned down.

**Expire a plan after 7 days**, as the incumbent does. It keeps lists fresh,
and it throws away problems somebody meant to come back to. Turned down: a
plan waits.

**Skip, and save for later**, as outcomes. Not asked for now. An "upsolve"
list was offered the same day and not chosen.

## Consequences

- **The five no longer change under a visitor.** A sync ticks what they
  solved instead of replacing it. A press settles one problem instead of
  redrawing the list. And the target they moved shows in the next plan, not
  this one. The page says what the next plan will aim at.
- **No accounts, so a handle's plans are anybody's.** Anybody who types
  `tourist` sees and can settle tourist's plan. That is ADR 0021's
  consequence again, answered by v1.5's sign-in (§11), not here.
- **The guard rail, the chooser and the target are applied when a plan is
  made.** A plan made before a refit keeps its chances until it ends.
- **Two new tables**, `plans` and `plan_problems`, filled only on the server.
  Like everything else there, they survive only once the disk is attached
  (ADR 0017).

## Amendment — 2026-09-28: how a plan's presses move the target

"The target now moves for the next plan" is kept, and made exact by ADR
0027. A press no longer moves the target when it is made. When a plan ends,
its presses are counted together, "too easy" against "too hard", and the
target takes one step of an adaptive staircase, in the same transaction
that ends the plan. Solves are not counted; the model learns from them
through the visitor's history.
