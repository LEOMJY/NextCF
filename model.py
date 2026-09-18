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
from collections import defaultdict
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
    args = parser.parse_args()

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


if __name__ == "__main__":
    sys.exit(main())
