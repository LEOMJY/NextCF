"""Solve-probability prediction, and the recommendations built on it.

v0.4 holds one predictor: the RATING-ONLY BASELINE. It is the yardstick spec
section 9 measures everything else against -- "the model predicts solve/fail on
held-out submissions with lower log loss than the rating-only baseline" -- so
it has to be a fair one. A baseline that is too weak makes any model look good
and the section 9 number mean nothing.

    P(solve) = sigmoid(a + b * (user_rating - problem_rating) / 100)

Two numbers, a and b, fitted to the collected dataset and stored in
baseline.json beside this file. Nothing else about the user or the problem is
used, which is what "rating-only" means.

WHY FITTED, AND NOT THE ELO CURVE. Codeforces ratings are Elo-style, and the
obvious baseline is Elo's own formula, 1 / (1 + 10^(-gap/400)). Measured
against 1,578,181 first attempts in dataset.db, it is not close:

    user - problem   first try accepted   Elo says
    <= -800                 37%              1%
    -200..-1                50%             36%
    +400..+599              72%             95%

Elo is several times too steep. People attempt hard problems when they already
have a good chance at them, and practise easy ones they could get wrong -- the
selection effect spec section 8's assumption 4 predicted. A baseline that says
1% where the truth is 37% would be beaten by anything, and "beating it" would
say nothing about topics. Fitting the curve to the data removes that free win:
whatever the v0.6 model gains over THIS baseline, it gains from information
beyond rating.

Usage, on the author's machine where dataset.db lives:
    .venv\\Scripts\\python.exe model.py fit-baseline
    .venv\\Scripts\\python.exe model.py fit-baseline --event eventually
"""

import argparse
import bisect
import functools
import json
import math
import sys
from array import array
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import db

HERE = Path(__file__).resolve().parent
BASELINE_PATH = HERE / "baseline.json"

# What counts as solving a problem, for the purpose of predicting it. This is
# spec section 12's "what counts as solved?", and the answer changes which
# problems get recommended -- see the ADR on the baseline.
#
#   first_try   the user's FIRST submission on the problem was accepted
#   eventually  ANY of their submissions on it was accepted
#
# Measured across the dataset, the two are completely different curves.
# "eventually" runs from 82% to 99% across 1,600 rating points: people keep
# submitting until the problem falls, so it hardly depends on difficulty at
# all, and a 70% target does not exist anywhere on it. "first_try" runs from
# 37% to 83% and contains every target worth asking for.
EVENTS = ("first_try", "eventually")

# The probability recommendations aim at: a FIRST submission accepted half the
# time. Decided 2026-09-18 -- ADR 0012's last section. Three reasons, and they
# point the same way:
#
#   * under the fitted baseline, 50% is a problem about 200 points ABOVE the
#     user's rating, which is where the ordinary advice to practise sits. 70%
#     was about 500 points below -- five problems that would look too easy to
#     the person they were meant for;
#   * a problem solved first time 50% of the time is solved EVENTUALLY about
#     93% of the time (the -200..-1 band in ADR 0012's table): reachable, with
#     effort, which is the "desirable difficulty" spec section 8 wants;
#   * an attempt at 50% tells the model the most about the person making it.
#     In a Rasch model an item's information about a person's skill is
#     P * (1 - P), largest at P = 0.5 -- the reason adaptive exams choose
#     questions a candidate has an even chance at. Every recommendation acted
#     on is also data, and this is the setting where that data is worth most.
#
# users.target_prob still holds 0.70 and is NOT read: nobody can choose a
# target until the control ADR 0008 plans exists, and changing the column's
# default would mean rebuilding the users table, which the submissions table
# refers to. When the control ships, reading the column comes back.
DEFAULT_TARGET = 0.50

# Ratings are divided by this before they reach the curve, so that `b` reads
# as "change in log-odds per 100 rating points" rather than per single point.
# Nothing about the fit depends on it except readability and the numerical
# conditioning of Newton's method, which is much better with inputs near 1
# than near 1,000.
SCALE = 100.0


# ------------------------------------------------------------------ the curve

def sigmoid(x):
    """1 / (1 + e^-x), written so a very negative x cannot overflow exp()."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def logit(p):
    """The inverse of sigmoid: log(p / (1 - p))."""
    return math.log(p / (1.0 - p))


@functools.cache
def current_baseline(path=BASELINE_PATH):
    """The fitted curve, as written by `model.py fit-baseline`. Read once.

    Loaded on first USE rather than at import, because `model.py
    fit-baseline` is the program that creates the file, and it could never
    run if merely importing this module needed the file to exist already.

    A missing or unreadable file still raises, on the first prediction,
    rather than falling back to anything: a recommender quietly running on
    made-up numbers is exactly the failure this module exists to prevent.
    functools.cache is what makes "read once" true -- the file is opened on
    the first call and the parsed result is returned on every call after.
    """
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def baseline_probability(user_rating, problem_rating, baseline=None):
    """P(solve) for a user at `user_rating` on a problem at `problem_rating`."""
    baseline = baseline or current_baseline()
    gap = (user_rating - problem_rating) / SCALE
    return sigmoid(baseline["intercept"] + baseline["slope"] * gap)


def rating_for_probability(user_rating, target, baseline=None):
    """The problem rating at which this user's P(solve) equals `target`.

    The curve inverted by hand, which is why a closed form exists at all:

        target = sigmoid(a + b * (u - r) / 100)
        logit(target) = a + b * (u - r) / 100
        r = u - 100 * (logit(target) - a) / b

    Not used to choose problems -- recommend() ranks every problem by its own
    probability -- but it is the one number that explains a recommendation
    list in a sentence, and the page shows it.
    """
    baseline = baseline or current_baseline()
    return user_rating - SCALE * (logit(target) - baseline["intercept"]) / baseline["slope"]


# ------------------------------------------------------------ recommendations

def recommend(pool, user_rating, target, count=5, baseline=None):
    """The `count` problems whose predicted P(solve) is nearest `target`.

    `pool` is rows from db.recommendation_pool(): problemset problems with a
    rating, minus the ones this user has already solved.

    Returns dicts with the problem's fields plus `probability`.

    Every problem at one rating has the same probability under a rating-only
    curve, and the problemset holds hundreds at each rating, so the tie-break
    decides most of what is actually shown. It is the NEWEST contest first:
    deterministic, explainable in one sentence, and it favours problems
    written in the style Codeforces uses now.

    It also means two users at the same rating are shown the same five
    problems. That is not a bug in the baseline -- it IS the baseline. Spec
    section 3's complaint about sorting by rating is precisely that it treats
    everybody at one rating as the same person. The model's job at v0.6 is to
    stop doing that, and this is what it will be compared against.
    """
    baseline = baseline or current_baseline()
    scored = []
    for row in pool:
        p = baseline_probability(user_rating, row["rating"], baseline)
        scored.append((abs(p - target), -(row["contest_id"] or 0), row["id"], p, row))
    scored.sort(key=lambda item: item[:3])

    return [
        {
            "id": row["id"],
            "contest_id": row["contest_id"],
            "problem_index": row["problem_index"],
            "name": row["name"],
            "rating": row["rating"],
            "probability": p,
        }
        for _, _, _, p, row in scored[:count]
    ]


# -------------------------------------------------------------------- fitting

def training_counts(conn, event):
    """{rating gap: [attempts, successes]} over every first attempt in the data.

    One entry per (user, problem) -- per PROBLEM, not per submission, because a
    recommendation is a problem and three wrong answers then an accepted one
    are one decision to try it, not four. Aliases are folded first (ADR 0010),
    so a Div. 2 contestant's 1293C and a Div. 1 contestant's 1292A are both
    attempts at 1292A.

    THE RATING IS THE ONE THE USER HAD AT THE TIME, taken from rating_changes:
    the latest new_rating at or before the first submission. Using today's
    rating would be leakage -- a submission from three years ago predicted
    with knowledge of how strong its author later became -- and ADR 0009
    collected rating histories specifically to prevent it.

    Skipped, and each for its own reason:
      a problem outside the pool     no rating to put in the gap
      before the user's first rated  no rating at the time at all; spec
        contest                      section 12 has this for v0.5 (4.6% of
                                     submissions)

    Returned as counts per distinct gap rather than as 1.5 million rows.
    Ratings are integers and problem ratings are multiples of 100, so there
    are only a few thousand distinct gaps, and for logistic regression the
    counts are all the information there is -- fitting on them gives exactly
    the same answer as fitting on every row, in a fraction of the time.
    """
    if event not in EVENTS:
        raise ValueError(f"unknown event {event!r}; expected one of {EVENTS}")

    history = defaultdict(list)
    for handle, rated_at, rating in conn.execute(
        "SELECT handle, rated_at, new_rating FROM rating_changes ORDER BY handle, rated_at"
    ):
        history[handle].append((rated_at, rating))
    moments = {h: [at for at, _ in changes] for h, changes in history.items()}

    # ROW_NUMBER() numbers each user's submissions on one problem oldest first,
    # so rn = 1 is the genuinely first attempt. An earlier draft used
    # SQLite's "bare column" rule instead -- a plain column in a MIN() query
    # comes from the row holding the minimum -- and got "first try" identical
    # to "eventually" in every row of the output. That rule only holds when the
    # query has exactly ONE min or max, and that query had two. The window
    # function states what it means and does not depend on a rule.
    rows = conn.execute(
        """
        WITH attempts AS (
            SELECT s.handle,
                   COALESCE(a.canonical_id, s.problem_id)            AS problem_id,
                   s.submitted_at,
                   s.verdict,
                   ROW_NUMBER() OVER (
                       PARTITION BY s.handle, COALESCE(a.canonical_id, s.problem_id)
                       ORDER BY s.submitted_at, s.id)                AS nth,
                   MAX(CASE WHEN s.verdict = 'OK' THEN 1 ELSE 0 END) OVER (
                       PARTITION BY s.handle,
                                    COALESCE(a.canonical_id, s.problem_id)) AS ever
              FROM submissions s
              LEFT JOIN problem_aliases a ON a.alias_id = s.problem_id
        )
        SELECT t.handle, t.submitted_at, p.rating,
               CASE WHEN t.verdict = 'OK' THEN 1 ELSE 0 END AS first_try,
               t.ever                                       AS eventually
          FROM attempts t
          JOIN problems p ON p.id = t.problem_id
         WHERE t.nth = 1
           AND p.in_problemset = 1
           AND p.rating IS NOT NULL
        """
    )

    column = 3 if event == "first_try" else 4
    counts = defaultdict(lambda: [0, 0])
    for row in rows:
        handle, first_at = row[0], row[1]
        i = bisect.bisect_right(moments.get(handle, []), first_at)
        if i == 0:
            continue
        gap = history[handle][i - 1][1] - row[2]
        counts[gap][0] += 1
        counts[gap][1] += row[column]
    return dict(counts)


def fit_logistic(counts, iterations=25):
    """Maximum-likelihood a and b for P = sigmoid(a + b * gap / 100).

    Newton's method, by hand. For logistic regression the log-likelihood is
    concave, so Newton converges to the one global maximum, typically in five
    or six steps; 25 is a ceiling, not an expectation.

    For each distinct gap x (in hundreds) with n attempts and k successes, and
    p = sigmoid(a + b*x):

        gradient   g_a = sum(k - n*p)          g_b = sum((k - n*p) * x)
        curvature  w = n * p * (1 - p)
                   H = -[[sum(w),   sum(w*x)  ],
                         [sum(w*x), sum(w*x*x)]]

    and each step solves H * delta = -g, the 2x2 system done out long below.

    Returns (a, b, log_loss), log loss being the average over every attempt of
    -[y log p + (1 - y) log(1 - p)] -- the number section 9 is written in.
    """
    a = b = 0.0
    for _ in range(iterations):
        ga = gb = haa = hab = hbb = 0.0
        for gap, (n, k) in counts.items():
            x = gap / SCALE
            p = sigmoid(a + b * x)
            r = k - n * p
            w = n * p * (1.0 - p)
            ga += r
            gb += r * x
            haa += w
            hab += w * x
            hbb += w * x * x
        det = haa * hbb - hab * hab
        da = (hbb * ga - hab * gb) / det
        db_ = (haa * gb - hab * ga) / det
        a += da
        b += db_
        if abs(da) < 1e-10 and abs(db_) < 1e-10:
            break

    total = loss = 0.0
    for gap, (n, k) in counts.items():
        p = sigmoid(a + b * gap / SCALE)
        loss -= k * math.log(p) + (n - k) * math.log(1.0 - p)
        total += n
    return a, b, loss / total


def calibration(counts, a, b, width=200):
    """Observed against predicted, by band of rating gap. For reading the fit."""
    bands = defaultdict(lambda: [0, 0, 0.0])
    for gap, (n, k) in counts.items():
        band = max(-800, min(800, math.floor(gap / width) * width))
        bands[band][0] += n
        bands[band][1] += k
        bands[band][2] += n * sigmoid(a + b * gap / SCALE)
    return [(band, n, k / n, expected / n) for band, (n, k, expected) in sorted(bands.items())]


def fit_baseline(conn, event):
    """Fit the curve on everything in dataset.db and return what to store."""
    counts = training_counts(conn, event)
    a, b, loss = fit_logistic(counts)
    return {
        "event": event,
        "intercept": round(a, 6),
        "slope": round(b, 6),
        "attempts": sum(n for n, _ in counts.values()),
        "log_loss": round(loss, 6),
        "fitted_on": "dataset.db",
        "fitted_at": db.utc_now(),
    }, counts


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    fit = sub.add_parser("fit-baseline", help="fit the rating-only curve and write baseline.json")
    fit.add_argument("--event", choices=EVENTS, default="first_try")
    fit.add_argument("--dry-run", action="store_true", help="print, do not write baseline.json")
    fit.add_argument("--db", default="dataset.db")
    sub.add_parser("fit-topic", help="fit evaluate.FINAL on all of dataset.db and write "
                                     "topic_model.json")
    args = parser.parse_args()

    if args.command == "fit-topic":
        import evaluate
        if evaluate.FINAL is None:
            raise SystemExit("evaluate.FINAL is not set: the configuration is chosen on "
                             "validation and scored on test before anything ships.")
        result = fit_topic(evaluate.FINAL)
        TOPIC_PATH.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        print(f"wrote {TOPIC_PATH.name}: {len(result['d']):,} problems, "
              f"{len(result['tau'])} topics, from {result['attempts']:,} attempts")
        return

    conn = db.connect(Path(args.db))
    try:
        result, counts = fit_baseline(conn, args.event)
    finally:
        conn.close()

    a, b = result["intercept"], result["slope"]
    print(f"event {result['event']}: {result['attempts']:,} first attempts")
    print(f"P = sigmoid({a:+.4f} {b:+.4f} * gap/100)    log loss {result['log_loss']:.4f}")
    print(f"\n{'user - problem':>15}{'attempts':>11}{'observed':>10}{'fitted':>9}")
    for band, n, observed, fitted in calibration(counts, a, b):
        label = "<=-800" if band == -800 else (">=+800" if band == 800 else f"{band:+d}..{band + 199:+d}")
        print(f"{label:>15}{n:>11,}{observed:>10.1%}{fitted:>9.1%}")

    if args.dry_run:
        print("\n--dry-run: baseline.json not written")
        return
    BASELINE_PATH.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {BASELINE_PATH.name}")


# ================================================ practice history features

class HistoryState:
    """One user's practice history, and the HISTORY_COLUMNS it implies at any
    moment. The ONE implementation of those features: evaluate.load builds
    everybody's through it attempt by attempt, and the website builds a
    visitor's through it once per page -- the same code, so the same numbers.

    Every feature counts only attempts STRICTLY before the moment asked
    about. Two attempts in the same second do not see each other; the website
    asks about five hypothetical problems at once without adding them, so
    they never see each other either. The window counts get that from bisect
    on the sorted times. The running shares, the last outcome and the time
    since it do not bisect, so an attempt is held back in `pending` until an
    attempt at a LATER second arrives, and only then folded in.

    Keys of `tags` can be anything hashable: tag indices in the harness, tag
    names on the website.
    """

    def __init__(self):
        self.times, self.wins = [], [0]                    # wins: prefix sums
        self.tag_times, self.tag_wins = {}, {}
        self.num = self.den = 0.0
        self.tag_num, self.tag_den = {}, {}
        self.last_y = self.last_t = None
        self.pending, self.pending_t = [], None

    def _fold(self, before):
        """Fold held-back attempts into the running values, if they are
        strictly older than `before`."""
        if self.pending and self.pending_t < before:
            for t, y, tags in self.pending:
                self.num = SHARE_DECAY * self.num + y
                self.den = SHARE_DECAY * self.den + 1.0
                for k in tags:
                    self.tag_num[k] = SHARE_DECAY * self.tag_num.get(k, 0.0) + y
                    self.tag_den[k] = SHARE_DECAY * self.tag_den.get(k, 0.0) + 1.0
                self.last_y, self.last_t = y, t
            self.pending = []

    def add(self, t, y, tags):
        """Record an attempt at time t. Times must not go backwards."""
        self._fold(t)
        self.times.append(t)
        self.wins.append(self.wins[-1] + y)
        for k in tags:
            self.tag_times.setdefault(k, []).append(t)
            wins = self.tag_wins.setdefault(k, [0])
            wins.append(wins[-1] + y)
        self.pending.append((t, y, tags))
        self.pending_t = t

    def overall(self, t):
        """The columns that do not depend on the problem's topics, at time t:
        per window (tries, wins); then all-time wins; the recent success share;
        the last outcome; log hours since the last attempt."""
        self._fold(t)
        hi = bisect.bisect_left(self.times, t)
        out = []
        for w in HISTORY_WINDOWS:
            lo = bisect.bisect_left(self.times, t - w)
            out.append((math.log1p(hi - lo), math.log1p(self.wins[hi] - self.wins[lo])))
        rest = (math.log1p(self.wins[hi]),
                (self.num + 1.0) / (self.den + 2.0),
                0.5 if self.last_y is None else float(self.last_y),
                math.log1p((t - self.last_t) / 3600.0) if self.last_t is not None
                else math.log1p(24 * 365))
        return out, rest

    def per_tag(self, t, k):
        """The topic columns for one tag at time t: per window (tries, wins);
        all-time (tries, wins); the tag's recent success share."""
        self._fold(t)
        times = self.tag_times.get(k, ())
        wins = self.tag_wins.get(k, (0,))
        hi = bisect.bisect_left(times, t)
        out = []
        for w in HISTORY_WINDOWS:
            lo = bisect.bisect_left(times, t - w)
            out.append((math.log1p(hi - lo), math.log1p(wins[hi] - wins[lo])))
        share = (self.tag_num.get(k, 0.0) + 1.0) / (self.tag_den.get(k, 0.0) + 2.0)
        return out, (math.log1p(hi), math.log1p(wins[hi])), share

    @staticmethod
    def combine(overall, per_tags):
        """HISTORY_COLUMNS, in order, from overall() and one per_tag() for each
        of the problem's tags -- topic columns are the mean over its tags."""
        windows, rest = overall
        n = len(per_tags)
        row = []
        for w in range(len(HISTORY_WINDOWS)):
            row.append(windows[w][0])
            row.append(windows[w][1])
            row.append(sum(pt[0][w][0] for pt in per_tags) / n)
            row.append(sum(pt[0][w][1] for pt in per_tags) / n)
        row.append(sum(pt[1][0] for pt in per_tags) / n)
        row.append(sum(pt[1][1] for pt in per_tags) / n)
        row.append(rest[0])
        row.append(rest[1])
        row.append(sum(pt[2] for pt in per_tags) / n)
        row.append(rest[2])
        row.append(rest[3])
        return row

    def features(self, t, tags):
        return self.combine(self.overall(t), [self.per_tag(t, k) for k in tags])


def compute_history(data):
    """Fill data.h with HISTORY_COLUMNS for every attempt in `data`, which must
    be in time order. One HistoryState per user, asked BEFORE each attempt is
    added -- so no attempt ever sees itself or anything after it."""
    n = len(data)
    data.h = [array("d", bytes(8 * n)) for _ in HISTORY_COLUMNS]
    states = {}
    for i in range(n):
        state = states.get(data.u[i])
        if state is None:
            state = states[data.u[i]] = HistoryState()
        tags = _tags(data, data.p[i])
        for c, v in enumerate(state.features(data.t[i], tags)):
            data.h[c][i] = v
        state.add(data.t[i], data.y[i], tags)
    return data


# ======================================================== the topic model
#
# v0.6's model, brought forward on 2026-09-18 when the author asked for the
# most accurate prediction possible. The baseline above stays exactly as it
# is: it is the yardstick, and a yardstick that changes is not one.
#
#   logit P(first try accepted) =
#         gamma[context] + beta * gap          context, and rating at the time
#       + mean over the problem's tags of tau[tag]      how hard the TOPIC is
#       + d[problem]                                    how hard THIS problem is
#       + b[user]                                       this user, beyond rating
#       + mean over the problem's tags of s[user, tag]  this user, in this topic
#
# Every part answers something the baseline measurably got wrong on
# 2026-09-18: contest attempts fail more than their rating says; constructive
# algorithms is 6.5 points harder on a first try than its rating suggests;
# users rated 1000-1199 succeed more than theirs does. None of those can be
# seen from one number per side.
#
# MEAN over tags, not sum. A problem with five tags would otherwise get five
# topic terms and a problem with one tag one, so the number of tags someone
# happened to attach would change the prediction.
#
# L2 REGULARISATION on everything except the global block. Each parameter pays
# lam/2 * value^2 into the objective, which pulls it towards 0 -- "no
# different from average" -- and the pull wins when there is little evidence.
# A problem attempted by three people cannot be declared hard from three
# results. `lam` reads as roughly "how many attempts' worth of doubt", since
# one attempt contributes at most 0.25 to the curvature.
#
# The objective -- total log loss plus the penalties -- is CONVEX in all the
# parameters together, because the logit is linear in them. So there is one
# minimum, every run finds the same one, and section 9's number is
# reproducible. That is the main reason for this model's form over anything
# that is not convex.

GROUPS = ("tag", "problem", "user", "user_topic")

# The tag an untagged problem is given. Every problem then has at least one
# tag, and that is what makes the centring steps in fit() EXACT: shifting
# every topic term by the same amount moves every attempt by that amount, so
# it can be handed to the intercept without changing a single prediction. An
# untagged problem with no topic term at all would break that, and break it
# silently. A real tag cannot collide with it: tag indices count up from 0.
NO_TAG = -1


def layout(extras):
    """({extra: its first column in w}, total columns), in EXTRAS order. The
    one place that decides where each extra's weights sit: the model, the
    centring moves and the website's scorer all read it, so none of them can
    count the columns differently from the others."""
    widths = {"shape": len(KNOTS), "level": 1, "experience": 1,
              "position": N_POSITIONS - 1, "trend": 1, "history": len(HISTORY_COLUMNS)}
    starts, col = {}, 0
    for name in EXTRAS:
        if name in extras:
            starts[name] = col
            col += widths[name]
    return starts, col


def _tags(data, problem):
    return data.problem_tags[problem] or (NO_TAG,)


# Extra columns for the global block, each switchable, each a question the
# first ladder could not ask:
#
#   shape       the rating gap bends. The baseline's curve is one straight
#               line in log-odds, and ADR 0012's table is steeper on the side
#               where the user is above the problem than below it. Hinges --
#               max(0, gap - knot), one per knot -- let the slope change at
#               each knot while staying one continuous curve.
#   level       the user's rating itself, not only the gap. The baseline was
#               3.9 points low for users at 1000-1199 and 1.7 high at
#               1800-1999, at the same gaps.
#   experience  log(1 + earlier first attempts by this user).
#   position    A, B, C... in the contest. Known the day a problem appears,
#               so it reaches the half of 2026's attempts that are on
#               problems with no history. "A" is the reference and gets no
#               column: eight one-hot columns would always sum to 1, the same
#               as the four context columns, and the system would have no
#               unique solution.
#   trend       years since 2025-01-01. Measured on 2026-09-18: the
#               baseline's error drifted steadily by year of attempt, from 6
#               to 9 points too optimistic in 2016-2018 to 3 points too
#               pessimistic in 2026. A model fitted on the past predicts the
#               future, and if the world is moving, one straight line in time
#               is the simplest thing that can follow it. Extrapolating a line
#               is a risk, which is exactly what validation -- itself the
#               future of the training data -- is there to judge.
#   history     what the user has done RECENTLY, counted before each attempt:
#               23 columns, from the student-modelling literature's answer to
#               "the rating lags the skill". DAS3H (Choffin et al., EDM 2019)
#               adds to exactly this model's shape -- ability, item and skill
#               difficulty -- log-counts of attempts and successes in time
#               windows, per skill; Best-LR (Gervet et al., JEDM 2020) adds
#               overall counts, and found a logistic model with such features
#               matches deep knowledge tracing where students have many
#               interactions each, which is this dataset. LKT's R-PFA adds a
#               decayed success share. See HISTORY_COLUMNS for the list.
EXTRAS = ("shape", "level", "experience", "position", "trend", "history")

# The windows, in seconds: an hour catches the contest in progress, a day
# the session, a week and a month the stretch of practice. DAS3H's own set,
# minus its "forever" window, which is here as separate all-time columns.
HISTORY_WINDOWS = (3600.0, 86400.0, 7 * 86400.0, 30 * 86400.0)
HISTORY_COLUMNS = tuple(
    [f"{scope}_{kind}_{name}" for name in ("1h", "1d", "7d", "30d")
     for scope in ("all", "topic") for kind in ("tries", "wins")]
    + ["topic_tries_ever", "topic_wins_ever", "all_wins_ever",
       "all_share_recent", "topic_share_recent", "last_was_ok", "log_hours_since_last"])
# A success share over the last attempts, each one counting 0.8 of the one
# after it -- R-PFA's "propdec" -- with one imaginary success and one failure
# so that a user with no history reads as 1/2 rather than 0/0.
SHARE_DECAY = 0.8

# Participant types, in a fixed order so each maps to the same index in every
# run and every file. Anything Codeforces adds later is read as practice, the
# commonest and least special case, rather than failing.
CONTEXTS = ("PRACTICE", "CONTESTANT", "VIRTUAL", "OUT_OF_COMPETITION")

# A problem's position in its contest, from the first character of its index:
# A to F each on their own, G and later together, anything not a letter (the
# numbered problems of contest 921) as "other".
POSITIONS = ("A", "B", "C", "D", "E", "F", "G+", "other")


def position_of(problem_index):
    first = problem_index[:1].upper()
    if first and first in "ABCDEF":
        return POSITIONS.index(first)
    if first.isalpha():
        return POSITIONS.index("G+")
    return POSITIONS.index("other")


class Attempts:
    """Every first attempt in the pool, oldest first, as parallel lists.

    Parallel lists rather than one object per attempt: 1.5 million small
    objects cost a lot of memory and a lot of attribute lookups in the inner
    loops of a fit, and every loop here is an inner loop.

        u[i]  user index            p[i]  canonical problem index
        c[i]  context index         g[i]  (user rating - problem rating) / 100,
                                          the user's rating AT THE TIME, as
                                          Codeforces computes with it -- see
                                          computed_ratings()
        y[i]  1 if accepted         t[i]  seconds since 1970, first submission
        s[i]  the user's stratum    month[i]  "2026-03", for the fold-in
        r[i]  (user rating at the time - 1500) / 100: the LEVEL, where g is
              the gap. Two attempts with the same gap, one at 1100 and one at
              1900, need not behave alike.
        n[i]  log(1 + how many first attempts this user made before this
              one): experience. Counted from earlier rows only, so it is
              known at the moment of the attempt.
        g_shown[i]  the gap by the rating Codeforces SHOWS. Read by the
              rating-only baseline and nothing else: the baseline is the
              reference every model is measured against, defined on the
              number on the profile (ADR 0012), and stays exactly that.

    plus the lookups that turn indices back into names, each problem's tags
    as a tuple of tag indices, and each problem's position in its contest
    (see POSITIONS).
    """

    def __init__(self):
        self.handles, self.problems, self.tag_names = [], [], []
        self.problem_tags = []
        self.problem_position = []
        self.u, self.p, self.c, self.g, self.y, self.t, self.s = [], [], [], [], [], [], []
        self.r, self.n = [], []
        self.g_shown = []
        self.month = []
        self.population = {}

    def __len__(self):
        return len(self.y)


# The rating Codeforces SHOWS a new account is not the one it computes with.
# Since May 2020 a new account is computed from 1400 but shown 0, and what is
# shown gets 500, 350, 250, 150, 100 and 50 added after its first six rated
# contests -- 1400 in all. So after one contest the profile says 900 less than
# the rating Codeforces itself works with, after two 550, then 300, 150, 50,
# and from the sixth contest on the two agree. Read as the user's level, the
# shown number made the model 10 points too pessimistic about users one
# contest in (said 46%, happened 57%, on validation) and 9 points two in. 12%
# of all attempts in dataset.db are made by accounts still in those six.
HIDDEN_AFTER = (1400, 900, 550, 300, 150, 50)

# Accounts first rated before the change started at 1500, shown and computed
# alike, and the API cannot tell them apart by their first oldRating: it is 0
# for both. In dataset.db the last first contest under the old rule is 1355
# (2020-05-16, straight to about 1400 after it) and the first under the new
# one is 1358 (2020-05-26, to about 400).
NEW_RULE_FROM = "2020-05-20T00:00:00Z"


def computed_ratings(changes):
    """[(rated_at, rating as Codeforces computes with it)] from a user's
    [(rated_at, new_rating)], oldest first -- the shown rating plus whatever
    is still hidden after that many contests (see HIDDEN_AFTER)."""
    new_rule = bool(changes) and changes[0][0] >= NEW_RULE_FROM
    return [
        (at, rating + (HIDDEN_AFTER[k] if new_rule and k < len(HIDDEN_AFTER) else 0))
        for k, (at, rating) in enumerate(changes, 1)
    ]


def rating_now(conn, handle, shown):
    """A visitor's rating as Codeforces computes with it today: `shown` when
    nothing is hidden any more (or they have no rating changes stored)."""
    changes = conn.execute(
        "SELECT rated_at, new_rating FROM rating_changes WHERE handle = ? ORDER BY rated_at",
        (handle,),
    ).fetchall()
    if not changes or shown is None:
        return shown
    return shown + computed_ratings(changes)[-1][1] - changes[-1][1]


# Every first attempt at a pool problem: one row per (user, canonical problem),
# oldest first within each. SHARED by evaluate.load, which runs it for every
# user in dataset.db, and user_attempts below, which runs it for one visitor
# on the website -- so the model is scored on exactly the inputs the website
# will give it. `{where}` is either empty or a filter on one handle.
#
# ROW_NUMBER, not SQLite's bare-column rule: see training_counts for the bug
# that rule caused.
FIRST_ATTEMPTS_SQL = """
    WITH attempts AS (
        SELECT s.handle,
               COALESCE(a.canonical_id, s.problem_id) AS problem_id,
               s.submitted_at, s.verdict, s.participant_type,
               ROW_NUMBER() OVER (
                   PARTITION BY s.handle, COALESCE(a.canonical_id, s.problem_id)
                   ORDER BY s.submitted_at, s.id) AS nth
          FROM submissions s
          LEFT JOIN problem_aliases a ON a.alias_id = s.problem_id
         {where}
    )
    SELECT t.handle, t.problem_id, t.submitted_at, p.rating,
           CASE WHEN t.verdict = 'OK' THEN 1 ELSE 0 END, t.participant_type,
           p.problem_index
      FROM attempts t
      JOIN problems p ON p.id = t.problem_id
     WHERE t.nth = 1 AND p.in_problemset = 1 AND p.rating IS NOT NULL
"""
TREND_ORIGIN = 1735689600.0          # 2025-01-01T00:00:00Z
YEAR = 365.25 * 86400.0
KNOTS = (-4.0, -2.0, 0.0, 2.0, 4.0)
N_POSITIONS = 8


def _solve(a, b):
    """Solve a x = b for a small dense system, by Gaussian elimination.

    Only ever 5x5 here (four context intercepts and the rating slope). Partial
    pivoting -- swapping in the row with the largest entry -- keeps it from
    dividing by something near zero.
    """
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(col + 1, n):
            f = m[r][col] / m[col][col]
            for k in range(col, n + 1):
                m[r][k] -= f * m[col][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][k] * x[k] for k in range(r + 1, n))) / m[r][r]
    return x


def _p(z):
    """sigmoid for the inner loops: clipped instead of branched, which is
    faster in pure Python and loses nothing -- sigmoid(35) is 1 - 6e-16."""
    if z > 35.0:
        z = 35.0
    elif z < -35.0:
        z = -35.0
    return 1.0 / (1.0 + math.exp(-z))


class TopicModel:
    """The model above. Groups can be switched off, which is how the ladder in
    evaluate.py measures what each kind of information is worth."""

    def __init__(self, groups=GROUPS, lam=None, n_contexts=4, extras=()):
        self.groups = set(groups)
        self.lam = {group: 10.0 for group in GROUPS}
        self.lam.update(lam or {})
        self.extras = tuple(e for e in EXTRAS if e in extras)
        self.gamma = [0.0] * n_contexts
        self.beta = 0.0
        self.w = [0.0] * self._n_extra()
        self.tau, self.d, self.b, self.s = {}, {}, {}, {}
        # Guard rails for the SHIPPED model only; None while fitting and
        # evaluating, so every number measured is unaffected. A straight line
        # is safe inside the data it was fitted to and nowhere else: the level
        # column weighs about -0.1 per 100 rating points, fitted on users
        # 99.9% of whom were below 2373, and at tourist's 3528 it would add
        # -1.95 to the log-odds -- a thousand points of pure extrapolation.
        self.level_range = None      # (lowest, highest) level, in hundreds
        self.trend_until = None      # latest moment the time line is followed

    def _n_extra(self):
        return layout(self.extras)[1]

    def _extra(self, data, i):
        """The extra global columns of attempt i, as (column, value) pairs,
        zeros left out. Built on the fly rather than stored: 774,000 attempts
        times a handful of pairs is hundreds of megabytes of small objects."""
        out = []
        col = 0
        if "shape" in self.extras:
            g = data.g[i]
            for knot in KNOTS:
                if g > knot:
                    out.append((col, g - knot))
                col += 1
        if "level" in self.extras:
            level = data.r[i]
            if self.level_range is not None:
                level = min(max(level, self.level_range[0]), self.level_range[1])
            out.append((col, level))
            col += 1
        if "experience" in self.extras:
            if data.n[i]:
                out.append((col, data.n[i]))
            col += 1
        if "position" in self.extras:
            position = data.problem_position[data.p[i]]
            if position:
                out.append((col + position - 1, 1.0))
            col += N_POSITIONS - 1
        if "trend" in self.extras:
            when = data.t[i]
            if self.trend_until is not None:
                when = min(when, self.trend_until)
            out.append((col, (when - TREND_ORIGIN) / YEAR))
            col += 1
        if "history" in self.extras:
            for c, column in enumerate(data.h):
                value = column[i]
                if value:
                    out.append((col + c, value))
        return out

    # ------------------------------------------------------------ fitting

    def fit(self, data, idx, max_sweeps=60, tol=1e-8, log=None):
        """Minimise the penalised log loss over attempts `idx`.

        BLOCK COORDINATE NEWTON. Every parameter outside the global block
        touches only the attempts that involve it -- d[p] only p's attempts,
        s[u, k] only u's attempts on problems tagged k -- so each is updated
        by a one-dimensional Newton step with the others held still:

            grad = sum(w * (y - p)) - lam * theta
            curv = sum(w^2 * p * (1 - p)) + lam
            theta += grad / curv

        where w is 1 for d and b, and 1/(number of tags) for tau and s,
        because those enter as a mean. The global block -- four context
        intercepts and the rating slope -- is five numbers that touch every
        attempt, so it gets a full 5x5 Newton step instead.

        One sweep updates everything once. Sweeps stop when a whole sweep
        improves the objective by less than `tol` per attempt. The logit of
        every attempt is kept in `z` and nudged as parameters move, so
        nothing is recomputed from scratch.
        """
        n = len(idx)
        C = [data.c[i] for i in idx]
        G = [data.g[i] for i in idx]
        Y = [data.y[i] for i in idx]
        P = [data.p[i] for i in idx]
        U = [data.u[i] for i in idx]
        T = [_tags(data, p) for p in P]
        W = [1.0 / len(t) for t in T]

        by = {group: defaultdict(list) for group in GROUPS}
        for j in range(n):
            by["problem"][P[j]].append(j)
            by["user"][U[j]].append(j)
            for k in T[j]:
                by["tag"][k].append(j)
                by["user_topic"][(U[j], k)].append(j)
        store = self._store()
        weighted = {"tag": True, "problem": False, "user": False, "user_topic": True}

        extra = (lambda j: self._extra(data, idx[j])) if self.w else None
        z = [self.gamma[C[j]] + self.beta * G[j] for j in range(n)]
        if extra:
            for j in range(n):
                z[j] += sum(self.w[a] * x for a, x in extra(j))
        for group in GROUPS:
            if group not in self.groups:
                continue
            for key, members in by[group].items():
                theta = store[group].get(key, 0.0)
                if theta:
                    for j in members:
                        z[j] += (W[j] if weighted[group] else 1.0) * theta

        s_keys_by_user = defaultdict(list)
        s_keys_by_tag = defaultdict(list)
        for key in by["user_topic"]:
            s_keys_by_user[key[0]].append(key)
            s_keys_by_tag[key[1]].append(key)
        problems_by_tag = defaultdict(list)
        problems_by_position = defaultdict(list)
        for p in by["problem"]:
            for k in _tags(data, p):
                problems_by_tag[k].append(p)
            if "position" in self.extras:
                problems_by_position[data.problem_position[p]].append(p)
        keys = (s_keys_by_user, s_keys_by_tag, problems_by_tag,
                {p: len(_tags(data, p)) for p in by["problem"]}, problems_by_position)

        previous = math.inf
        for sweep in range(max_sweeps):
            self._global_step(C, G, Y, z, extra)
            for group in GROUPS:
                if group in self.groups:
                    self._block(by[group], store[group], self.lam[group],
                                W if weighted[group] else None, Y, z)
            self._center(*keys)
            objective = self._objective(Y, z)
            if log:
                log(f"  sweep {sweep + 1:>2}: objective {objective / n:.6f}")
            if previous - objective < tol * n:
                break
            previous = objective
        self.sweeps = sweep + 1
        # Kept so a check can recompute the objective from the parameters
        # alone and compare: if the running logits `z` ever drift from what
        # the parameters say -- a centring move that was not exact, say --
        # the two disagree, and nothing else would notice.
        self.objective = objective / n
        return self

    def _store(self):
        return {"tag": self.tau, "problem": self.d, "user": self.b, "user_topic": self.s}

    def _center(self, s_keys_by_user, s_keys_by_tag, problems_by_tag, n_tags,
                problems_by_position=None):
        """Slide shared parts of the parameters to where they belong. Exact.

        The model is additive, so it has directions in which parameters can
        trade a constant without changing a single prediction: add 0.1 to
        every user's b and take 0.1 off every context intercept, and every
        logit is where it was. Along such a direction the log loss is flat and
        only the penalties change, so the best point on it has a closed form
        -- and coordinate steps, which move one parameter at a time, crawl
        along it for dozens of sweeps without getting there. The first run of
        this model hit its 60-sweep ceiling on every fit.

        The moves, each to the exact minimum of the penalty along its line:

            s[*, k] -> tau[k]  what every user shares in topic k is the topic
            d[p with k] -> tau[k]   what every k problem shares is the topic
            s[u, *] -> b[u]    what a user shares across topics is the user
            b, d, tau -> gamma what everybody shares is the intercept

        Each leaves every training prediction unchanged, which is why `z` is
        not touched here -- and why every problem has at least one tag
        (NO_TAG), without which the tau moves would not be exact. A check
        recomputes the objective from the parameters to prove it.

        A consequence that matters more than the speed: each level ends up
        holding exactly what is common to the level below it. That is what a
        problem or user the training data never saw is predicted from -- 0
        for its own terms, so the topic and intercept must carry the shared
        part. Half of the attempts in 2026 are on problems nobody attempted
        before 2026, and every visitor to the website is a user the training
        data never saw. The first version, without the two tau moves, left a
        gradient of 0.06 on the topic terms: part of each topic's difficulty
        was parked in individual problems and users, where a new problem or
        a new visitor could not reach it.
        """
        lam = self.lam
        if "tag" in self.groups and "user_topic" in self.groups:
            for k, keys in s_keys_by_tag.items():
                tau = self.tau.get(k, 0.0)
                delta = ((lam["user_topic"] * sum(self.s[key] for key in keys) - lam["tag"] * tau)
                         / (lam["user_topic"] * len(keys) + lam["tag"]))
                for key in keys:
                    self.s[key] -= delta
                self.tau[k] = tau + delta
        if "tag" in self.groups and "problem" in self.groups:
            # tau[k] += delta and d[p] -= delta / n_tags[p] for every problem
            # carrying k: each such problem's logit moves by delta/n - delta/n.
            for k, problems in problems_by_tag.items():
                tau = self.tau.get(k, 0.0)
                pull = sum(self.d.get(p, 0.0) / n_tags[p] for p in problems)
                weight = sum(1.0 / (n_tags[p] * n_tags[p]) for p in problems)
                delta = (lam["problem"] * pull - lam["tag"] * tau) / (lam["problem"] * weight + lam["tag"])
                for p in problems:
                    self.d[p] = self.d.get(p, 0.0) - delta / n_tags[p]
                self.tau[k] = tau + delta
        if "user" in self.groups and "user_topic" in self.groups:
            for u, keys in s_keys_by_user.items():
                b = self.b.get(u, 0.0)
                delta = ((lam["user_topic"] * sum(self.s[key] for key in keys) - lam["user"] * b)
                         / (lam["user_topic"] * len(keys) + lam["user"]))
                for key in keys:
                    self.s[key] -= delta
                self.b[u] = b + delta
        for group, params in (("user", self.b), ("problem", self.d), ("tag", self.tau)):
            if group in self.groups and params:
                delta = sum(params.values()) / len(params)
                for key in params:
                    params[key] -= delta
                for c in range(len(self.gamma)):
                    self.gamma[c] += delta
        if "problem" in self.groups and "position" in self.extras and problems_by_position:
            # A position is a property of the problem, so what every B problem
            # shares can sit in the B column or in each B problem's own d --
            # a flat direction the global Newton step cannot see, and which
            # left the position gradients at 4e-3 before this was added. The
            # column is not penalised, so the minimum is the mean of d.
            # Position A is the reference and has no column: its shared part
            # goes to the intercepts, and comes back off every other column so
            # that problems at other positions do not move.
            first = layout(self.extras)[0]["position"]
            for position, problems in problems_by_position.items():
                delta = sum(self.d.get(p, 0.0) for p in problems) / len(problems)
                for p in problems:
                    self.d[p] = self.d.get(p, 0.0) - delta
                if position:
                    self.w[first + position - 1] += delta
                else:
                    for c in range(len(self.gamma)):
                        self.gamma[c] += delta
                    for q in range(1, N_POSITIONS):
                        self.w[first + q - 1] -= delta

    def _global_step(self, C, G, Y, z, extra=None):
        """One full Newton step on the global block: the context intercepts,
        the rating slope, and whatever extra columns are switched on.

        Without extras this is the original 5x5 step, kept as its own fast
        path because the first ladder ran on it. With them, every attempt
        contributes to the gradient and curvature through its non-zero
        columns only, which is a handful even with every extra on.
        """
        k = len(self.gamma)
        dim = k + 1 + len(self.w)
        grad = [0.0] * dim
        hess = [[0.0] * dim for _ in range(dim)]
        if extra is None:
            for j in range(len(Y)):
                p = _p(z[j])
                r = Y[j] - p
                v = p * (1.0 - p)
                c, g = C[j], G[j]
                grad[c] += r
                grad[k] += r * g
                hess[c][c] += v
                hess[c][k] += v * g
                hess[k][k] += v * g * g
            for c in range(k):
                hess[k][c] = hess[c][k]
        else:
            for j in range(len(Y)):
                p = _p(z[j])
                r = Y[j] - p
                v = p * (1.0 - p)
                cols = [(C[j], 1.0), (k, G[j])]
                cols.extend((k + 1 + a, x) for a, x in extra(j))
                for a, xa in cols:
                    grad[a] += r * xa
                    row = hess[a]
                    t = v * xa
                    for b, xb in cols:
                        row[b] += t * xb
        # A context nobody used in this data would leave a row of zeros and
        # make the system singular. A tiny ridge keeps it solvable and does
        # nothing measurable to a column with real data.
        for c in range(dim):
            hess[c][c] += 1e-9
        step = _solve(hess, grad)
        for c in range(k):
            self.gamma[c] += step[c]
        self.beta += step[k]
        for a in range(len(self.w)):
            self.w[a] += step[k + 1 + a]
        for j in range(len(Y)):
            z[j] += step[C[j]] + step[k] * G[j]
            if extra is not None:
                z[j] += sum(step[k + 1 + a] * x for a, x in extra(j))

    @staticmethod
    def _block(index, params, lam, W, Y, z):
        """One Newton step for every parameter in one group. W is None when
        every attempt counts with weight 1."""
        for key, members in index.items():
            theta = params.get(key, 0.0)
            grad = -lam * theta
            curv = lam
            if W is None:
                for j in members:
                    p = _p(z[j])
                    grad += Y[j] - p
                    curv += p * (1.0 - p)
                delta = grad / curv
                params[key] = theta + delta
                for j in members:
                    z[j] += delta
            else:
                for j in members:
                    p = _p(z[j])
                    w = W[j]
                    grad += w * (Y[j] - p)
                    curv += w * w * p * (1.0 - p)
                delta = grad / curv
                params[key] = theta + delta
                for j in members:
                    z[j] += W[j] * delta

    def _objective(self, Y, z):
        loss = 0.0
        for j in range(len(Y)):
            p = _p(z[j])
            loss -= math.log(p) if Y[j] else math.log(1.0 - p)
        store = self._store()
        for group in self.groups:
            loss += 0.5 * self.lam[group] * sum(v * v for v in store[group].values())
        return loss

    # --------------------------------------------------------- predicting

    def offset(self, data, i):
        """The part of the logit that does not depend on who is attempting:
        context, rating gap, topic, problem. Held fixed during a fold-in."""
        tags = _tags(data, data.p[i])
        z = self.gamma[data.c[i]] + self.beta * data.g[i] + self.d.get(data.p[i], 0.0)
        z += sum(self.tau.get(k, 0.0) for k in tags) / len(tags)
        if self.w:
            z += sum(self.w[a] * x for a, x in self._extra(data, i))
        return z

    def predict(self, data, i, user=(0.0, None)):
        """P(first try accepted) for attempt i, given `user` = (b, {tag: s})
        from fold_in(): the user as known at the moment of the attempt."""
        b, s = user
        z = self.offset(data, i) + b
        if s:
            tags = _tags(data, data.p[i])
            z += sum(s.get(k, 0.0) for k in tags) / len(tags)
        return _p(z)

    def fold_in(self, data, history, weights=None, sweeps=30, start=None):
        """Fit ONE user's parameters from their history, everything else fixed.

        This is what the website does with a visitor, who was never in the
        training data: problems, topics and the curve are known from the
        crowd, and only the visitor's own numbers -- b, and s per topic -- are
        worked out from their history. Spec section 4: "the visitor's history
        is used only to locate them inside a model that was learned from the
        crowd."

        `weights`, if given, is one number per history attempt, multiplying
        its pull. evaluate.py uses it to let old attempts count less than
        recent ones, because a skill moves and a rating lags behind it.

        `start`, if given, is a previous (b, s) for the same user to continue
        from. A month's worth of new history moves a user a little, so
        starting from last month's answer converges in a few sweeps instead
        of thirty. It changes how fast the answer is reached, never what it
        is: the objective is convex, so there is one answer.

        Returns (b, {tag: s}).
        """
        if not history or not ({"user", "user_topic"} & self.groups):
            return 0.0, None
        Y = [data.y[i] for i in history]
        T = [_tags(data, data.p[i]) for i in history]
        W = [1.0 / len(t) for t in T]
        O = weights if weights is not None else [1.0] * len(history)
        z = [self.offset(data, i) for i in history]
        by_tag = defaultdict(list)
        for j, tags in enumerate(T):
            for k in tags:
                by_tag[k].append(j)
        b, s = 0.0, {}
        if start is not None:
            b, s = start[0], dict(start[1] or {})
            if b:
                z = [v + b for v in z]
            if s:
                for j, tags in enumerate(T):
                    z[j] += W[j] * sum(s.get(k, 0.0) for k in tags)
        lam_b, lam_s = self.lam["user"], self.lam["user_topic"]
        for _ in range(sweeps):
            moved = 0.0
            if "user" in self.groups:
                grad, curv = -lam_b * b, lam_b
                for j in range(len(Y)):
                    p = _p(z[j])
                    grad += O[j] * (Y[j] - p)
                    curv += O[j] * p * (1.0 - p)
                delta = grad / curv
                b += delta
                moved = abs(delta)
                for j in range(len(Y)):
                    z[j] += delta
            if "user_topic" in self.groups:
                for k, members in by_tag.items():
                    theta = s.get(k, 0.0)
                    grad, curv = -lam_s * theta, lam_s
                    for j in members:
                        p = _p(z[j])
                        grad += O[j] * W[j] * (Y[j] - p)
                        curv += O[j] * W[j] * W[j] * p * (1.0 - p)
                    delta = grad / curv
                    s[k] = theta + delta
                    moved = max(moved, abs(delta))
                    for j in members:
                        z[j] += W[j] * delta
            # The same centring as in fit(), for this one user: the average of
            # their topic numbers slides into b without moving any prediction.
            if "user" in self.groups and "user_topic" in self.groups and s:
                delta = (lam_s * sum(s.values()) - lam_b * b) / (lam_s * len(s) + lam_b)
                for k in s:
                    s[k] -= delta
                b += delta
            if moved < 1e-6:
                break
        return b, s


# ================================================== the topic model, in use
#
# Fitted on the author's machine by `model.py fit-topic`, written to
# topic_model.json, committed -- the same route as baseline.json, and the
# first real answer to spec section 12's "how does what the model learned
# reach the server?": the crowd's part of the model, keyed by NAME (tag names,
# problem ids), a few hundred kilobytes. A visitor's own part is never stored:
# it is worked out from their history on every visit, by the fold-in.

TOPIC_PATH = HERE / "topic_model.json"
NO_TAG_NAME = "(untagged)"


@functools.cache
def current_topic_model(path=TOPIC_PATH):
    """The fitted topic model, or None if there is none. Read once."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _stamp(iso):
    return datetime.strptime(iso, db.TIMESTAMP_FORMAT).replace(tzinfo=timezone.utc).timestamp()


def tags_by_problem(conn):
    """Every problem's tags in one query: 30,000 rows, a few milliseconds.
    One query per problem instead would be 11,000 queries per results page."""
    tags = defaultdict(list)
    for pid, tag in conn.execute("SELECT problem_id, tag FROM problem_tags ORDER BY tag"):
        tags[pid].append(tag)
    return tags


def visitor_attempts(conn, handle, data=None, problem_index=None, tag_index=None,
                     tags_of=None):
    """One user's first attempts, built EXACTLY as evaluate.load builds
    everybody's: the same SQL, the same rating-at-the-time, the same
    experience count, the same positions. A check compares the two on real
    users, because the day they drift apart, the website is running a model
    nobody evaluated.

    Appends to `data` (a fresh Attempts if None), with every attempt as user
    0, and returns (data, history indices, problem_index, tag_index).
    """
    data = data if data is not None else Attempts()
    problem_index = problem_index if problem_index is not None else {}
    tag_index = tag_index if tag_index is not None else {}
    tags_of = tags_of if tags_of is not None else tags_by_problem(conn)
    shown = conn.execute(
        "SELECT rated_at, new_rating FROM rating_changes WHERE handle = ? ORDER BY rated_at",
        (handle,),
    ).fetchall()
    changes = computed_ratings(shown)
    moments = [at for at, _ in changes]
    rows = conn.execute(FIRST_ATTEMPTS_SQL.format(where="WHERE s.handle = ?"), (handle,)).fetchall()

    kept = []
    for _, pid, at, prating, ok, ptype, pindex in rows:
        i = bisect.bisect_right(moments, at)
        if i == 0:
            continue                          # no rating at the time
        rating = changes[i - 1][1]
        kept.append((at, pid, rating - prating, ok, ptype, rating, pindex, shown[i - 1][1] - prating))
    kept.sort()

    contexts = {name: i for i, name in enumerate(CONTEXTS)}
    history = []
    for n, (at, pid, gap, ok, ptype, rating, pindex, gap_shown) in enumerate(kept):
        history.append(len(data))
        data.u.append(0)
        data.p.append(_register(data, problem_index, tag_index, tags_of, pid, pindex))
        data.c.append(contexts.get(ptype, 0))
        data.g.append(gap / SCALE)
        data.g_shown.append(gap_shown / SCALE)
        data.y.append(ok)
        data.t.append(_stamp(at))
        data.r.append((rating - 1500) / SCALE)
        data.n.append(math.log1p(n))
        data.s.append(None)
        data.month.append(at[:7])
    compute_history(data)
    return data, history, problem_index, tag_index, tags_of


def _register(data, problem_index, tag_index, tags_of, pid, pindex):
    """The index of problem `pid` in `data`, adding it with its tags if new."""
    if pid not in problem_index:
        problem_index[pid] = len(data.problems)
        data.problems.append(pid)
        tags = []
        for tag in tags_of.get(pid, ()):
            if tag not in tag_index:
                tag_index[tag] = len(data.tag_names)
                data.tag_names.append(tag)
            tags.append(tag_index[tag])
        data.problem_tags.append(tuple(tags))
        data.problem_position.append(position_of(pindex))
    return problem_index[pid]


class PracticeScorer:
    """Every problemset problem's chance of a first-try accept, for one
    visitor practising NOW -- the same arithmetic as TopicModel.predict, split
    so that what does not depend on the visitor is done once per process.

    The logit of a practice attempt on problem p is

        [gamma_practice + d[p] + mean tau[p's tags] + position[p]]    <- per problem
      + beta * g + sum of hinge weights * max(0, g - knot)            <- the gap
      + w_level * level + w_exp * experience + w_trend * years + b    <- per visitor
      + mean over p's tags of s[tag]                                  <- both

    The bracket is the same for every visitor, so it is computed when the
    scorer is built -- once per fitted model and problemset -- and a request
    adds the rest in one tight loop. Measured on a real history, 42% of a
    results page went on scoring problems one predict() call at a time, and
    the free host has a tenth of a CPU.

    It is a second copy of the model's arithmetic, which is exactly what this
    project avoids elsewhere, so a check scores every problem both ways for
    real users and fails on any difference. If that check is ever deleted,
    delete this class too.
    """

    def __init__(self, fitted, problems):
        """`problems`: (id, rating, problem_index, tag names) for each
        problemset problem with a rating."""
        self.fitted = fitted
        w = list(fitted["w"])
        self.beta = fitted["beta"]
        starts, _ = layout(fitted["extras"])
        self.hinges = ([(knot, w[starts["shape"] + a]) for a, knot in enumerate(KNOTS)]
                       if "shape" in starts else [])
        self.w_level = w[starts["level"]] if "level" in starts else 0.0
        self.w_exp = w[starts["experience"]] if "experience" in starts else 0.0
        self.w_trend = w[starts["trend"]] if "trend" in starts else 0.0
        positions = [0.0] * N_POSITIONS
        if "position" in starts:
            for q in range(1, N_POSITIONS):
                positions[q] = w[starts["position"] + q - 1]
        self.w_history = (w[starts["history"]:starts["history"] + len(HISTORY_COLUMNS)]
                          if "history" in starts else None)
        self.level_range = fitted.get("level_range")
        self.trend_until = fitted.get("trend_until")

        tau, d = fitted["tau"], fitted["d"]
        practice = fitted["gamma"][CONTEXTS.index("PRACTICE")]
        self.rows = []
        for pid, rating, pindex, tags in problems:
            names = tuple(tags) or (NO_TAG_NAME,)
            base = (practice + d.get(pid, 0.0)
                    + sum(tau.get(k, 0.0) for k in names) / len(names)
                    + positions[position_of(pindex)])
            self.rows.append((pid, rating, names, base))

    def scores(self, rating, experience, now, b, s_by_name, history=None):
        """{problem id: P(first-try accept)} for every problem it was built with.

        `history` is the visitor's HistoryState keyed by tag NAME, as
        fold_in_visitor returns it. The history columns are split exactly:
        the topic columns are a mean over the problem's tags and a dot
        product distributes over a mean, so

            w . combine(overall, [each tag]) = w . combine(overall, [nothing])
                                             + mean over tags of w . combine(nothing, [tag])

        -- the overall part once per page, each tag's part once per tag, and
        per problem only the mean. combine() itself does both halves, so the
        column order lives in one place."""
        level = (rating - 1500) / SCALE
        if self.level_range:
            level = min(max(level, self.level_range[0]), self.level_range[1])
        when = now if self.trend_until is None else min(now, self.trend_until)
        visitor = (b + self.w_level * level + self.w_exp * experience
                   + self.w_trend * (when - TREND_ORIGIN) / YEAR)
        tag_part = {}
        if self.w_history is not None:
            state = history if history is not None else HistoryState()
            dot = lambda row: sum(wc * v for wc, v in zip(self.w_history, row))
            windows = [(0.0, 0.0)] * len(HISTORY_WINDOWS)
            no_tag = (windows, (0.0, 0.0), 0.0)
            visitor += dot(HistoryState.combine(state.overall(now), [no_tag]))
            no_overall = (windows, (0.0, 0.0, 0.0, 0.0))
            for _, _, names, _ in self.rows:
                for k in names:
                    if k not in tag_part:
                        tag_part[k] = dot(HistoryState.combine(no_overall, [state.per_tag(now, k)]))
        beta, hinges = self.beta, self.hinges
        out = {}
        for pid, prating, names, base in self.rows:
            g = (rating - prating) / SCALE
            z = base + visitor + beta * g
            for knot, weight in hinges:
                if g > knot:
                    z += weight * (g - knot)
            if s_by_name:
                z += sum(s_by_name.get(k, 0.0) for k in names) / len(names)
            if tag_part:
                z += sum(tag_part[k] for k in names) / len(names)
            out[pid] = _p(z)
        return out


def fitted_model(fitted, problem_index, tag_index):
    """A TopicModel carrying topic_model.json's numbers for the problems and
    tags one Attempts object knows about -- the reference implementation the
    fold-in runs on, and the one the check compares PracticeScorer against."""
    m = TopicModel(fitted["groups"], fitted["lam"], extras=fitted["extras"])
    m.gamma, m.beta, m.w = list(fitted["gamma"]), fitted["beta"], list(fitted["w"])
    if fitted.get("level_range"):
        m.level_range = tuple(fitted["level_range"])
    m.trend_until = fitted.get("trend_until")
    for name, value in fitted["tau"].items():
        key = NO_TAG if name == NO_TAG_NAME else tag_index.get(name)
        if key is not None:
            m.tau[key] = value
    d = fitted["d"]
    for pid, index in problem_index.items():
        if pid in d:
            m.d[index] = d[pid]
    return m


def fold_in_visitor(conn, handle, fitted, now, tags_of=None):
    """The visitor's own numbers, from their history as known NOW.

    Returns (b, {tag name: s}, number of attempts in their history, their
    HistoryState keyed by tag name). The same
    fold-in the evaluation scored, on inputs built by the same code the
    evaluation used (visitor_attempts), with older attempts counting half as
    much for every `halflife` days.
    """
    data, history, problem_index, tag_index, _ = visitor_attempts(conn, handle, tags_of=tags_of)
    m = fitted_model(fitted, problem_index, tag_index)
    weights = None
    if fitted.get("halflife") and history:
        decay = fitted["halflife"] * 86400.0
        weights = [0.5 ** ((now - data.t[i]) / decay) for i in history]
    b, s = m.fold_in(data, history, weights)
    name = lambda k: NO_TAG_NAME if k == NO_TAG else data.tag_names[k]
    # The same history again, keyed by tag NAME, for the scorer's pool --
    # replayed through the same HistoryState, so it cannot disagree with the
    # columns the fold-in above just used.
    by_name = HistoryState()
    for i in history:
        by_name.add(data.t[i], data.y[i], tuple(name(k) for k in _tags(data, data.p[i])))
    return b, {name(k): v for k, v in (s or {}).items()}, len(history), by_name


_scorer_cache = {}


def practice_scorer(conn, fitted):
    """The PracticeScorer for this fitted model and this problemset, built
    once per process and rebuilt when either changes. The problemset is only
    fetched when the web app starts (ADR 0010) and the model changes only
    with a deploy, so in practice it is built once per start."""
    size = conn.execute("SELECT count(*) FROM problems WHERE in_problemset = 1").fetchone()[0]
    key = (fitted.get("fitted_at"), size)
    if key not in _scorer_cache:
        tags = tags_by_problem(conn)
        problems = [(pid, rating, pindex, tags.get(pid, ()))
                    for pid, rating, pindex in conn.execute(
                        "SELECT id, rating, problem_index FROM problems "
                        "WHERE in_problemset = 1 AND rating IS NOT NULL")]
        _scorer_cache.clear()
        scorer = PracticeScorer(fitted, problems)
        # Kept with the scorer so a visitor's history reuses it rather than
        # reading 30,000 tag rows again on every page.
        scorer.tags_of = tags
        _scorer_cache[key] = scorer
    return _scorer_cache[key]


def topic_recommend(conn, handle, current_rating, pool, target, count=5, now=None,
                    fitted=None):
    """The `count` problems whose chance of a first-try accept is nearest
    `target`, for this user, under the topic model. None if no model exists.

    The crowd's numbers come from topic_model.json; the user's own are fitted
    here, from their history, with everything else held fixed, and their
    older attempts counting less -- exactly the fold-in the evaluation scored.
    Each unsolved problem in `pool` is then scored as an attempt made NOW: in
    practice, at today's rating, with today's experience.

    Ties, now rare because problems no longer share a probability by rating
    alone, go to the newest contest as in recommend().
    """
    fitted = fitted or current_topic_model()
    if fitted is None:
        return None
    now = now if now is not None else datetime.now(timezone.utc).timestamp()

    scorer = practice_scorer(conn, fitted)
    b, s_by_name, n_history, history = fold_in_visitor(conn, handle, fitted, now, scorer.tags_of)
    chances = scorer.scores(current_rating, math.log1p(n_history), now, b, s_by_name, history)

    candidates = [(chances[row["id"]], row) for row in pool if row["id"] in chances]
    return [
        {"id": row["id"], "contest_id": row["contest_id"],
         "problem_index": row["problem_index"], "name": row["name"],
         "rating": row["rating"], "probability": p}
        for p, row in choose(candidates, target, count, scorer.tags_of)
    ]


# How close to the target counts as "at the target". The model's calibration
# gap on the test year was 1.6 points, so it cannot tell 50.1% from 50.4% --
# and for a typical user 143 unsolved problems sit within half a point of 50%,
# 531 within two. Picking "the nearest" among those picked on differences far
# below the model's precision, and the five reshuffled whenever the clock
# moved the time line or the history weights a little.
BAND = 0.025


def choose(candidates, target, count, tags_of):
    """`count` of (probability, row), all within BAND of `target`, spread
    across as many topics as possible.

    Inside the band every problem is equally right as far as the model can
    tell, so the choice between them is made on something that means
    something: each pick is the problem sharing the FEWEST topics with the
    picks before it, the newest contest breaking ties -- so the first pick is
    simply the newest problem in the band. Five problems on five topics is a
    better practice set than five on one, and the same inputs always give the
    same five.

    Fewest shared, not most new: the first version picked the problem adding
    the most uncovered topics, and so always opened with whatever problem
    carried the most tags -- eleven, for one real user. A long tag list says
    more about how a problem was labelled than about what it teaches.

    If fewer than `count` problems are in the band -- a very strong user, a
    nearly exhausted pool -- it widens, doubling, until there are enough.
    """
    for band in (BAND, 2 * BAND, 4 * BAND, 8 * BAND, 1.0):
        near = [(p, row) for p, row in candidates if abs(p - target) <= band]
        if len(near) >= count:
            break
    near.sort(key=lambda pr: (-(pr[1]["contest_id"] or 0), pr[1]["id"]))
    chosen, covered = [], set()
    while near and len(chosen) < count:
        best = min(range(len(near)),
                   key=lambda i: (len(set(tags_of.get(near[i][1]["id"], ())) & covered), i))
        p, row = near.pop(best)
        chosen.append((p, row))
        covered |= set(tags_of.get(row["id"], ()))
    return chosen


def outside_range(fitted, rating):
    """Is this rating outside the levels the model was fitted on?

    The page says so when it is. The model still answers -- its level term is
    held at the nearest edge -- but the answer is an extrapolation, and a
    3500-rated visitor should be told that rather than handed five numbers
    that look as solid as everybody else's."""
    if not fitted or not fitted.get("level_range"):
        return False
    level = (rating - 1500) / SCALE
    return not fitted["level_range"][0] <= level <= fitted["level_range"][1]


def fit_topic(config):
    """Fit `config` on ALL of dataset.db and return what topic_model.json holds.

    Everything, not the training period: the choices were made on validation
    and scored once on test (ADR 0013); what ships is the same model fitted
    on every attempt there is, because the newest attempts are the most like
    the visitors it will meet.
    """
    import evaluate
    conn = db.connect(HERE / "dataset.db")
    try:
        data = evaluate.load(conn)
    finally:
        conn.close()
    m = TopicModel(config["groups"], config["lam"], extras=config.get("extras", ()))
    m.fit(data, list(range(len(data))), log=lambda msg: print(msg, flush=True))
    return export_fitted(m, data, config.get("halflife"))


def export_fitted(m, data, halflife):
    """The crowd's part of a fitted model, keyed by name, as topic_model.json
    holds it. The users' own parameters are left out on purpose: a visitor is
    folded in from their own history, never looked up."""
    tag_name = lambda k: NO_TAG_NAME if k == NO_TAG else data.tag_names[k]
    # The guard rails (see TopicModel.__init__): the middle 99.8% of the
    # levels the model was fitted on, and half a year past the newest attempt
    # for the time line -- monthly refits keep that to one month in practice,
    # and if they stop, predictions stop drifting instead of walking off.
    levels = sorted(data.r)
    level_range = [levels[int(0.001 * (len(levels) - 1))], levels[int(0.999 * (len(levels) - 1))]]
    trend_until = max(data.t) + 183 * 86400.0
    return {
        "groups": sorted(m.groups),
        "lam": m.lam,
        "extras": list(m.extras),
        "halflife": halflife,
        "level_range": level_range,
        "trend_until": trend_until,
        "gamma": m.gamma,
        "beta": m.beta,
        "w": m.w,
        "tau": {tag_name(k): round(v, 6) for k, v in sorted(m.tau.items())},
        "d": {data.problems[p]: round(v, 6) for p, v in sorted(m.d.items())},
        "attempts": len(data),
        "objective": round(m.objective, 8),
        "fitted_on": "dataset.db",
        "fitted_at": db.utc_now(),
    }


if __name__ == "__main__":
    sys.exit(main())
