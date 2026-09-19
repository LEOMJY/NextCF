# 0015 — What the user did lately, and the rating Codeforces computes with

**Date:** 2026-09-18
**Status:** accepted

## Context

ADR 0014's model predicts a first attempt from who the user is — their own
number b and one per topic — what the problem is, and the user's rating at the
time. It scored 0.5989 on the test year. Two things it could not see were
found on the same day, by asking what else a first submission depends on and
reading what the student-modelling literature has already measured.

**What the user has been doing lately.** A rating moves only at contests, and
b is one number per user, refitted monthly. Between contests nothing tells the
model that somebody has solved twelve problems this week, or failed their last
five. The literature has a name for this and a standard answer. DAS3H (Choffin
et al., EDM 2019) adds to exactly this model's shape — ability, item and skill
difficulty — counts of the learner's recent attempts and successes, per skill,
in time windows, and reported AUC 0.04 to 0.055 above a model of ability and
difficulty alone. Gervet et al. (JEDM 2020) compared that family with deep
knowledge tracing: logistic regression on such counts did best on datasets
"of moderate size or containing a very large number of interactions per
student", deep models on the largest datasets and where precise timing
matters most. Ours has hundreds of attempts per user. The logistic knowledge
tracing papers (Pavlik et al.) add a recency-weighted share of recent
successes.

**That the rating on a new account's profile is not the one Codeforces uses.**
Since May 2020 a new account is computed from 1400 but shown 0, and what is
shown gets 500, 350, 250, 150, 100 and 50 added after its first six rated
contests. After one contest the profile understates the rating Codeforces
itself works with by 900 points, after two by 550, then 300, 150, 50, then
nothing. The model read the shown number as the user's level, and 12% of all
attempts in `dataset.db` are by accounts still inside those six contests. On
validation the model was ten points too pessimistic about users one contest
in (said 46.3%, happened 56.7%), nine points two in, three points three in —
the error shrinking exactly as the hidden amount does.

Both were screened before either was built: candidate information stacked on
the existing model's validation predictions, fitted on 2025-07..09, scored on
2025-10..12. That says whether information exists that the model lacks, in
minutes rather than an hour a fit.

## Decision

**1. Twenty-three practice-history columns**, a new extra ("history"):

- attempts and successes, overall and in the problem's topics, in the last
  hour, day, week and 30 days — as log(1 + count);
- attempts and successes in the problem's topics ever, and successes ever;
- a recency-weighted share of recent successes, overall and in the topics
  (each earlier attempt weighing 0.8 of the one after it, starting from one
  success in two);
- whether the previous attempt succeeded, and log(1 + hours since it).

Topic columns are the mean over the problem's tags, as everything topical in
this model is. Every column counts **strictly earlier seconds only**: two
attempts in the same second do not see each other, a window of a week reaches
back exactly a week, and a check works examples by hand to hold it there. One
class, `HistoryState`, computes them for the evaluation and for the website,
and the check comparing the two on 25 real users compares all 23 columns of
every attempt.

**2. The rating the model reads is the one Codeforces computes with.**
`computed_ratings()` adds back what is still hidden after each contest, for
accounts whose first rated contest was on or after 2020-05-20. Older accounts
started at 1500, shown and computed alike; the API gives both a first
`oldRating` of 0, so the rule is by date. In `dataset.db` the last first
contest under the old rule is 1355 (2020-05-16) and the first under the new
one 1358 (2020-05-26). The **baseline keeps the shown rating**: it is the
fixed reference, defined on the number on the profile (ADR 0012), and knowing
better is something a model gets credit for. When the two differ, the results
page says which number the chances were worked out for.

**Measured on validation, frozen at the start of it:**

| | log loss | calibration |
|---|---|---|
| round two (ADR 0014) | 0.6038 | 1.0 pt |
| + practice history | **0.6012** | 1.0 pt |
| + practice history, computed rating | **0.6010** | 1.1 pt |

Refitted on the 1st of every month, as the product does, round three scores
**0.5980** on validation against round two's 0.6007 — the monthly refit is
worth +0.0030 to it, as it was to round two, and the two gains add.

**On the test set** — the second look, on ADR 0013's amended terms — round
three scores **0.5934** against round two's 0.5989 and the baseline's 0.6535,
lower in every stratum by 0.004 to 0.006, calibration 1.5 points against 1.6.
The gain on 2026 is twice the gain on validation, which fits the account of
where it comes from: the newer the attempt, the more of it is made by new
accounts and by users mid-way through a burst of practice.

History is worth 0.0026, and helps every stratum — 1000–1199 by 0.0033 and
1800–1999 by 0.0040. Round two's five extra columns together were worth
0.0101, so this is a quarter as much again from the user's own recent past.
The biggest weights are the recent share of successes in the problem's topics
(+0.62), successes in the last hour (+0.35) and all-time successes (+0.29).

## Alternatives

**The hidden amount as learned columns** (how much it is, and whether any is
left), instead of adding it back: 0.6008, against the computed rating's
0.6010. The difference is below what validation can resolve, and the learned
version has a flaw the arithmetic does not. Users were drawn on their rating
in September 2026 (ADR 0009), so every new account in the sample is one that
reached 1000 within a year or two — the successes of their cohort. A weight
learned from them partly measures that, and a real newcomer visiting the site
is not preselected to succeed. Adding back what Codeforces hid is the rating
system's own arithmetic, true of every account.

**Rating dynamics** — peak minus current, the last change, the change over
three contests, contests so far, days since the last: +0.0011 alone in the
screen, nothing on top of history (0.6008 with or without them). Recent
contests say less about recent form than recent practice does.

**Level × topic** — topic difficulty allowed to depend on the level: +0.0006
in the screen, 39 more parameters. Not tried in the full model; the next
candidate if more is wanted.

**Screened at about zero:** having taken part in the problem's contest before
attempting it; the problem's age at the attempt (upsolving against archive
practice).

**Deep knowledge tracing** (DKT, SAKT and their successors). Needs a deep
learning stack this project does not have and would have to install, for a
kind of dataset — hundreds of attempts per learner — where the comparison
above found logistic models doing best. §5 keeps knowledge tracing *as
a product* — trajectories, forgetting, spaced repetition — in v2.0; what is
decided here is only that recent practice is information the prediction uses.

**Knowledge tracing machines** (Vie & Kashima, AAAI 2019): a factorisation
machine over users, items and skills. This model already is one with the
pairs that matter; the pair it lacks, user × problem, is the thing being
predicted.

**Correcting for self-selection** — people choose their own problems, so the
recorded attempts are not a random sample of what they could attempt (TSDR,
2026, and doubly robust estimators generally). Not applied: the test set is
chosen the same way, so no offline number could say whether it helped. It
becomes testable once people act on recommendations the site chose.

**A joint Newton step for the global columns and every user's b.** The fit
with history needs 33 sweeps against round two's 5–13, and the suspicion was
that the history columns and b, which both describe how strong a user is,
were undoing each other's steps. Stepping them together is exact and cheap
(each attempt has one user, so the users can be eliminated one by one), and
it was built, checked and measured: still short of converging after 27
sweeps, against the plain step's 33 to finish. The slow direction is
elsewhere — most likely the topic columns against each user's topic numbers,
which cannot be eliminated so cheaply — and seventy lines that save a tenth
of a fit were taken out again.

## Consequences

- **The evaluation's history is fresher than the website's.** Each attempt is
  scored with its history counted up to the second before it; the website
  counts up to the moment the page is opened, and the attempt comes later.
  Measured by refitting with the columns counted as of a fixed time before
  each attempt: an hour earlier 0.6007, a day earlier 0.6015, against 0.6010
  at the moment and 0.6031 without history. The gain survives an hour's
  staleness untouched and a day's with three quarters of it left.
- **A fit takes about 14 minutes on the training period, not 3.** The monthly
  refit on everything took 41 sweeps and 37 minutes; it runs unattended.
- **The website's cost is small**: 40 to 46 ms for one real history's
  recommendations, 93 to 102 ms for tourist's, timed side by side. The scorer
  adds the overall history once per page and each topic's once per topic; per
  problem only a mean over its
  tags. A check scores every problem both ways against `predict()` with every
  column on and fails on any difference.
- **A second look at the test set**, on the terms in ADR 0013's amendment.
- **The numbers before and after are on different ratings.** Every model
  number up to round two was measured on shown ratings; from here on, computed.
  The baseline's are unchanged.
- **The sample's selection is now a known bias, not a suspicion.** Drawing
  users on their current rating means that the closer an attempt is to the
  draw, the more surely its author was on the way to 1000–1999. New accounts
  in 2026 are the clearest case: even with both changes the model is about
  three points pessimistic about them on validation (said 54.7%, happened
  57.6%). Part of that is the model and
  part is the sample, and this data cannot say how much of each. A future
  sample drawn on the rating at the *start* of its test period would not have
  the problem.
- **The monthly refit now has a way to happen**: `collect.py refresh` fetches
  every collected user again, oldest first, resumable by the same last-synced
  marker the first collection used, and never draws anybody new.
