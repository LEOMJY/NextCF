# 0024 — What was recommended is written down

**Date:** 2026-09-26
**Status:** accepted

## Context

Every number this project has published is about attempts people chose for
themselves. The product's claim is about problems it chooses for them, and
the audit of 2026-09-26 showed the two are not the same. ADR 0023's guard
rail took the share of picks 500 or more above the user from 35% to 20%, and
the remainder cannot be judged from any data the project has. A validation
screen showed why: in data made of choices, the model is already right,
including where it is wrong for a recommendation.

Spec §9 has always named the question, as "second-order, once
recommendations have been acted on". ADR 0021 left it open: the site did not
record what it offered, so it could not say "you solved two of the five" or
check its own chances. The author chose to record now, and to leave the page
alone until there is data.

## Decision

**A `recommendations` table in `nextcf.db`: one row per (handle, problem),
written the first time the problem is shown, never changed.** A row holds
when it was shown, the chance as computed (not the whole percent printed),
the visitor's target, which predictor chose it, which monthly fit of the
model (`fitted_at`), and whether ADR 0023's guard rail held.

**First showing only.** The chance a visitor saw before trying the problem
is the claim under test. A reload that recomputed it and overwrote the row
would score the model against numbers nobody was shown.

**The outcome is not stored.** It is the handle's first submission to that
problem after `shown_at`, read from `submissions` under the canonical id
(ADR 0010). A problem tried before it was shown is left out of the scoring,
because what happens next is not a first attempt, which is the only event
the model predicts (ADR 0013). A problem never tried is counted as shown and
not scored. The upkeep thread's re-sync of recent visitors (ADR 0020) is
what brings those later submissions in.

**At most 500 rows per handle**, then nothing new is recorded for that
handle. This has the same reason as `dismissals`' cap: nothing a visitor can
press should be able to fill the disk. Unlike that cap, this one stops
instead of pushing out the oldest, because the first recommendations a
visitor saw are the sample, and a report reading the rows that survived a
purge would be biased.

**The report is `python db.py`**, beside the visit counts and with the same
exclusion of the author's handles. It prints how many problems were shown,
how many were tried before being shown, how many were tried afterwards, and
the table of what the site said against what happened, in bins of 10
points.

**`/privacy` says so.** Recording what was shown is a new kind of row about
a handle, and the page's promise is that its list is the whole list.

## Alternatives

**A row for every showing.** This would record how often a problem was
seen, and how its chance moved between visits. It was turned down by the
author: most rows would be repeats, and the calibration report would have to
remove them before it could count anything.

**Storing the outcome** in the row, filled in by the sync. It is a second
copy of what `submissions` already says. It could disagree with it the day a
verdict is rejudged, and it adds work to the one transaction ADR 0004 keeps
simple.

**Showing it on the page now** ("you solved 2 of the 5 we suggested"). A
product decision with its own design questions: where it goes, what it says
at 0 of 5, whether it counts problems hidden with "too hard". The author
chose to wait until the data exists.

**Recording in the browser.** It would never reach the report.

## Consequences

- **It records nothing that counts until the disk is attached.** On the free
  instance the file is wiped several times a day, and every visit before
  launch is the author's own. The table is ready for the day ADR 0017's disk
  is bought.
- **The first honest measurement of the product's claim.** `db.py`'s table,
  once it has rows, is the number that says whether "about 50%" means 50% on
  problems the site chose. Spec §9's calibration criterion reads from it.
  So does the decision about ADR 0023's remaining 20%.
- **Each monthly model is judged separately**, because each row says which
  fit chose it. A refit that made recommendations worse would show in the
  table.
- **One more row per problem shown**, at most 500 a handle. At the cap, 1 GB
  holds tens of thousands of visitors' records.
