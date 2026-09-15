# 0009 — Who is in the dataset: 4000 users, stratified by rating

**Date:** 2026-09-13
**Status:** accepted; per stratum raised from 400 to 800 on 2026-09-15 — see
"Amendment" at the end

## Context

The model learns from the users `collect.py` fetches and from nobody else. If
they do not look like the people who use NextCF, the model is tuned to the
wrong people, and §9's number describes them rather than the visitors.

Two needs pull against each other. The sample should look like the audience in
§2, and every part of that audience needs enough people for the model to learn
their level rather than guess it.

`user.ratedList` with `activeOnly=true` — users in a rated contest within the
last month — measured on 2026-09-13: 40,929 users, median last online two days
earlier.

```
  200–799    10,941   26.7%
  800–999     8,434   20.6%
 1000–1199    7,685   18.8%
 1200–1399    6,351   15.5%
 1400–1599    3,919    9.6%
 1600–1799    2,118    5.2%
 1800–1999      835    2.0%
 2000–2199      376    0.9%
 2200+          266    0.6%
```

Two things in that table shape the decision. People thin out fast above 1600.
And below 1000 are many accounts still in their first six rated contests, whose
displayed rating Codeforces raises step by step towards their real level.

## Decision

**Stratified random sample.** Ratings 1000–1999 in five strata of 200 points,
**400 users drawn at random from each**, with a recorded seed.

**Rating history is collected with every history** — `user.rating`, one more
request per user.

**Nothing is filtered at collection time.** Every user drawn is fetched.
Thresholds such as a minimum number of problems belong to the analysis, where
they are a `WHERE` clause and can change.

**The draw is recorded in `dataset.db`:** the seed, when the rated list was
fetched, and every handle drawn with its stratum and rating at that moment.

## Alternatives

**Simple random sample of 1000–1999.** Most like the audience and the simplest
to report. Proportional shares put about 80 of 2000 users in 1800–1999, so the
model would be weakest for the top of the audience, and a single average would
hide it behind the crowded lower strata.

**Simple random sample of all active rated users.** About 47% would land under
1000, many of them accounts whose rating is not yet their level, and an hour of
collection would go mostly outside the audience.

**Popular users, contribution rankings, friends lists.** Different from ordinary
users in ways no reweighting can undo.

**A stratum for 2000+.** 642 active users in total, too few to draw 400 at
random from one stratum without taking most of it.

**Current rating only, no rating history.** An hour less. But a submission from
three years ago would be predicted with the rating the user has today — the
model would know how strong they later became. That is data leakage: the
evaluation uses information that did not exist at the moment being predicted,
so both the baseline and the model look better than they are, and §9's
comparison stops meaning anything. Adding it later means fetching all 2000
users again, the exact backfill §6 warns about.

## Consequences

- **§9 is reported per stratum, and as one total weighted by each stratum's
  real share.** 1000–1199 is 37% of active users in 1000–1999 but 20% of the
  sample, so each user in it counts for more in the total, and 1800–1999 for
  less. An unweighted average would describe the sample, not the audience.
- **Collection takes about two hours and a quarter**: two requests per user,
  each waiting its two-second turn. Resumable at the user boundary (ADR 0004),
  so it can run in more than one sitting.
- **`dataset.db` needs two things `nextcf.db` does not have yet**: rating
  changes, and the record of the draw. Designed with `collect.py`, in §6.
- **Users who have never entered a rated contest are not in the sample.**
  NextCF will meet them; they are the cold-start question in §12, not this one.
- **2000+ is absent**, so the model says nothing reliable about users above the
  audience.
- **The sample is a snapshot.** Ratings and histories move on after the day it
  was drawn; the recorded date is what makes that explicit.
- **Releasing the dataset (§9 stretch goal) raises whether handles should be
  anonymised.** Not decided here.

## Amendment — 2026-09-15: 800 per stratum

The real draw was made on 2026-09-15 with seed 1918731084: 8,091 / 6,708 /
4,155 / 2,281 / 869 candidates from 1000–1199 up to 1800–1999, about 1,100 more
active users than on the 13th, because "active" is a moving window.

The same night, with 211 users collected, per stratum was raised from 400 to
800 — 4000 users in total.

**Why.** The collection runs unattended overnight either way, so the extra
users cost hours that were going unused, not attention. More users mean more
attempts per problem, which is what a model estimating problem difficulty from
the crowd is short of, and more submissions to hold back for testing (§12).

**Why it needed no redraw.** The draw stores every stratum's whole shuffled
order, so raising the number takes the next candidates in line — exactly the
users a draw of 800 with the same seed would have taken. Nobody already
collected was fetched again. `collect.py extend` makes the change; it refuses
to lower the number or to exceed the smallest stratum's population, and
`sample_size_changes` records it.

**What it costs.**
- About four and a half hours of collection instead of two and a quarter.
- `dataset.db` roughly doubles, to an estimated 1.3 GB from the first 56
  users' average.
- 1800–1999 now takes 800 of its 869 candidates. The stratum is close to fully
  enumerated rather than sampled, which is statistically fine; it also leaves
  only 69 replacements if handles turn out unavailable.
- §9's weights are unchanged: they come from each stratum's population, not
  from how many were collected.
