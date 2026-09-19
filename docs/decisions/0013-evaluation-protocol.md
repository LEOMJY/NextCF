# 0013 — The evaluation protocol behind section 9's number

**Date:** 2026-09-18
**Status:** accepted; amended the same day for a second, pre-registered
look at the test set — see "Amendment" at the end

## Context

§9's first criterion is a number: does a model predict held-out attempts with
lower log loss than the rating-only baseline, per rating stratum and as one
total weighted by each stratum's share of the audience. §12 carried four
questions that decide what that number means, all due at v0.5. The author asked
on 2026-09-18 for the most accurate model achievable, which cannot be judged at
all without them, so they are settled here, with the harness, in `evaluate.py`.

A protocol is decided before any model is scored against it, for the same
reason a test is written before it is sat: choices made after seeing results
drift towards the results.

## Decision

**The unit is one attempt per (user, canonical problem) — the first
submission.** A recommendation is a problem. Three wrong answers then an
accepted one are one decision to try it, not four. Aliases are folded first
(ADR 0010).

**The event is that first submission being accepted** (ADR 0012). "Eventually
accepted" happens 94% of the time and barely depends on difficulty, so it can
neither be predicted usefully nor recommended from.

**The split is by date, one cutoff for everybody:**

| part | attempts | from | to |
|---|---|---|---|
| train | 774,258 | the beginning | 2025-06-30 |
| validation | 276,535 | 2025-07-01 | 2025-12-31 |
| test | 527,388 | 2026-01-01 | 2026-09-15 |

**Settings are chosen on validation; the test set is scored once.** The
configuration the validation ladder chooses is written into `evaluate.py` and
committed *before* the test set is first scored, so the record shows the
choice was made without it.

**Predictions go through the fold-in, as the website's will.** A model's
problem, topic and context terms are fitted on everything before the period
being scored. A user's own terms are refitted, month by month, from every
attempt that user made before that month — training period or not, because the
website knows a visitor's whole past — and from nothing after. An attempt on
14 March is predicted from what was known on 1 March. That is slightly staler
than the site, which refits on each visit, so the protocol can only understate
what the site does.

**Excluded, and stated:**
- *Problems outside the pool* — gym and unrated problems. The baseline cannot
  score them and they are never recommended. §12's gym question is answered by
  this: excluded from §9, as the simple answer it proposed, and said so.
- *Attempts before the user's first rated contest* — no rating at the time, so
  neither predictor has its main input. 4.6% of submissions. What to show such
  a user is the cold-start question, which stays open for the product.

**Reported:** log loss per stratum, and one total weighted by each stratum's
*population* in `sample_strata` — 8,091 / 6,708 / 4,155 / 2,281 / 869 — not by
how many attempts it contributed. And calibration: attempts binned by what the
model said, against what happened.

## Alternatives

**A random split.** The usual default, and wrong here in a measurable way.
The baseline's calibration gap was 2.0 points on data it had seen and 3.4 on
the year after, with every band erring the same way; by year of attempt the
error drifts steadily from 2016 to 2026. A random split mixes every year into
both halves and reports the 2.0. A date split reports what a model in use
faces, which is only ever the future.

**A cutoff per user** — each user's own last attempts held back. §12's first
option. It puts one user's test period alongside another's training period, so
a new problem's difficulty can be learned from people attempting it at the
same moment as the attempts being tested. One date for everyone matches the
day a model goes live, when nothing later exists for anybody.

**No validation set: choose settings on the test set.** Every choice made by
looking at a set turns that set into training data a little. With a dozen
regularisation strengths and three half-lives tried, the best of them on the
test set would be optimistic by construction. The cost of a separate
validation half-year is a smaller training set, and it is paid.

**Static user terms**, fitted once in training and reused for every later
month. Cheaper, and it misstates the product: a visitor's terms come from
their whole history up to the visit, not from a snapshot a year old. It would
systematically undervalue exactly the per-user information §3 is about.

**Weighting the total by attempts.** It describes the most active users in the
sample rather than the audience: the 1000–1199 stratum is 37% of active users
in 1000–1999 and submits the least.

## Consequences

- **Leakage has checks, not just rules.** Changing a user's later results must
  move none of their earlier predictions, bit for bit; an attempt's own month
  must not be in its history; the baseline's test predictions must not depend
  on test labels. A leak raises no error, so these are the checks that matter
  most in the project.
- **The baseline in the harness is refitted on the training period**, never
  read from `baseline.json`, which was fitted on everything (ADR 0012).
- **Problem ratings are a small, deliberate leak shared by both sides.**
  Codeforces rates a problem days after its contest, so an in-contest attempt
  is scored using a rating that did not yet exist. Both predictors use it
  identically, so the comparison is fair, and the product only ever
  recommends problems that are already rated. Noted rather than engineered
  away.
- **Half of the test period is new problems.** 51% of 2026's attempts are on
  problems nobody in the dataset attempted before 2026. A model's per-problem
  terms cannot help with those; only what generalises — topics, context, the
  user — can.
- **The same data gives the same number.** Every fit is deterministic and
  converges to the unique optimum of a convex objective; a check refits twice
  and compares bit for bit.
- **When the dataset is extended or re-collected**, the split dates move with
  it, and every number reported under the old dates is reported as such.

## Amendment — 2026-09-18: the test set, looked at a second time

"Scored once" was written for one model. Hours after that model was scored
(0.5989, commit 0100491), a better one was found on validation — the practice
history and the computed rating of ADR 0015, 0.6038 → 0.6010 frozen — and the
only number that could describe *it* on unseen data is a test number.

**Allowed once more, on these terms:**

1. **The configuration is committed first.** `evaluate.FINAL` is set to round
   three and committed before `evaluate.py final` runs, as the first time.
2. **The test number decides nothing.** Round three ships because validation
   chose it. The test number is reported whatever it is — better, the same or
   worse than 0.5989 — and there is no going back to round two on its account.
   A look that could change the choice would make the test set part of the
   choosing, which is the one thing it exists not to be.
3. **Both numbers stay on the record**, each with the configuration and the
   commit it belongs to. §9 shows the latest and says it is the second look.
4. **This is the last look at this test set.** The next model is judged on the
   months after it: the monthly refresh (`collect.py refresh`) brings attempts
   from after 2026-09-15 that no model has seen, and those become the test set
   the next time one is needed, under the same rules.

**Why the risk is small, and what it is.** The danger of a reused test set is
choosing on it: try twenty things, keep whichever the test set liked, and the
number it reports is the luck of the draw. Here nothing was tried on it — every
choice in round three was made on validation — and the two looks are at two
models chosen independently of it. What a second look does cost is the claim
that the test set was never seen when *anything* was decided: round three
was built by someone who knew round two's test result, and knew for example
that 2026 was about two points pessimistic. That knowledge did not choose a
single setting here, but it is stated rather than left for a reader to wonder
about.

**One thing the rerun changes that is not the model.** From this amendment on,
`evaluate.load()` gives every model the rating Codeforces computes with (ADR
0015), and only the baseline the shown one. The baseline's numbers are
therefore unchanged — 0.6533 on validation, 0.6535 on test — and every model
number before this date was measured on shown ratings, which is how the
devlog reports them.
