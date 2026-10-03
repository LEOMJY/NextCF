"""The evaluation harness -- spec section 9, ADR 0013.

Section 9's first criterion is computed here and nowhere else: does a model
predict held-out first attempts with lower log loss than the rating-only
baseline, per rating stratum and as one total weighted by each stratum's real
share of the audience.

THE PROTOCOL, and why each part is what it is (ADR 0013 has the argument):

  unit      one attempt per (user, canonical problem) -- the FIRST submission.
            A recommendation is a problem, not a submission.
  event     that first submission was accepted (ADR 0012).
  split     by DATE, one cutoff for everybody:
                train       before 2025-07-01
                validation  2025-07-01 .. 2025-12-31   choose settings here
                test        from 2026-01-01           look ONCE, at the end
            A random split mixes every year into both halves and flatters a
            model by several points; measured 2026-09-18, the baseline's
            calibration gap was 2.0 points in-sample and 3.4 on later data.
            A date split asks what a model in use faces: the future.
  excluded  problems outside the pool (gym, unrated) -- the baseline cannot
            score them and they are never recommended; and attempts made
            before the user's first rated contest, which have no "rating at
            the time". Both are stated, not silent.

LEAKAGE RULES, which fail without an error message if broken:
  * every fitted number is fitted on train only -- including the baseline,
    which is refitted here and never read from baseline.json (that file saw
    the test set);
  * a user's history may be used to predict their LATER attempts, never their
    earlier ones -- the fold-in below refits a user from what came before the
    month being predicted, which is exactly what the website can know;
  * settings are chosen on validation. The test set is scored once, by
    `evaluate.py final`, and a number from it is never used to change
    anything, or it stops being a test.

Usage, on the author's machine:
    .venv\\Scripts\\python.exe evaluate.py baseline
    .venv\\Scripts\\python.exe evaluate.py ladder
    .venv\\Scripts\\python.exe evaluate.py offsets     how far off, per person
    .venv\\Scripts\\python.exe evaluate.py final
    .venv\\Scripts\\python.exe evaluate.py forward --shipped 0d4360c
                the files that were live at that commit, scored on the first
                attempts made after their data ended -- run after a refresh
"""

import argparse
import bisect
import math
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import db
import model

VALIDATION_FROM = "2025-07-01"
TEST_FROM = "2026-01-01"

# Defined in model.py, because the website builds a visitor's inputs with the
# same definitions this harness builds everybody's with. Named here too so the
# rest of this file reads naturally.
CONTEXTS = model.CONTEXTS
POSITIONS = model.POSITIONS
position_of = model.position_of


# ----------------------------------------------------------------- the data

# The container for attempts lives in model.py, because the website builds
# one for each visitor; this harness builds one for everybody.
Attempts = model.Attempts


def load(conn):
    """Read every first attempt out of dataset.db. About 30 seconds."""
    data = Attempts()

    for stratum, population in conn.execute("SELECT stratum, population FROM sample_strata"):
        data.population[stratum] = population
    stratum_of = dict(conn.execute("SELECT handle, stratum FROM sample_candidates"))

    shown = defaultdict(list)
    for handle, rated_at, rating in conn.execute(
        "SELECT handle, rated_at, new_rating FROM rating_changes ORDER BY handle, rated_at"
    ):
        shown[handle].append((rated_at, rating))
    # The rating Codeforces computes with, which a new account's profile
    # understates for six contests (model.HIDDEN_AFTER). The shown one is kept
    # for the baseline alone.
    history = {h: model.computed_ratings(v) for h, v in shown.items()}
    moments = {h: [at for at, _ in v] for h, v in history.items()}

    tags_of = defaultdict(list)
    for pid, tag in conn.execute("SELECT problem_id, tag FROM problem_tags ORDER BY tag"):
        tags_of[pid].append(tag)

    # The query the website runs for one visitor, run here for everybody.
    rows = conn.execute(model.FIRST_ATTEMPTS_SQL.format(where="")).fetchall()

    kept = []
    for handle, pid, at, prating, ok, ptype, pindex in rows:
        i = bisect.bisect_right(moments.get(handle, []), at)
        if i == 0:
            continue                              # no rating at the time
        rating = history[handle][i - 1][1]
        kept.append((at, handle, pid, rating - prating, ok, ptype, rating, pindex,
                     shown[handle][i - 1][1] - prating))
    kept.sort()

    user_index, problem_index, tag_index = {}, {}, {}
    context_index = {name: i for i, name in enumerate(CONTEXTS)}
    seen = defaultdict(int)
    for at, handle, pid, gap, ok, ptype, rating, pindex, gap_shown in kept:
        if handle not in user_index:
            user_index[handle] = len(data.handles)
            data.handles.append(handle)
        if pid not in problem_index:
            problem_index[pid] = len(data.problems)
            data.problems.append(pid)
            tags = []
            for tag in tags_of[pid]:
                if tag not in tag_index:
                    tag_index[tag] = len(data.tag_names)
                    data.tag_names.append(tag)
                tags.append(tag_index[tag])
            data.problem_tags.append(tuple(tags))
            data.problem_position.append(position_of(pindex))

        data.r.append((rating - 1500) / model.SCALE)
        # `kept` is in time order, so this counts only EARLIER attempts.
        data.n.append(math.log1p(seen[handle]))
        seen[handle] += 1
        data.u.append(user_index[handle])
        data.p.append(problem_index[pid])
        data.c.append(context_index.get(ptype, 0))
        data.g.append(gap / model.SCALE)
        data.g_shown.append(gap_shown / model.SCALE)
        data.y.append(ok)
        data.t.append(datetime.strptime(at, db.TIMESTAMP_FORMAT)
                      .replace(tzinfo=timezone.utc).timestamp())
        data.s.append(stratum_of.get(handle))
        data.month.append(at[:7])
    # The practice-history columns, attempt by attempt, each from what came
    # strictly before it -- the same HistoryState the website uses.
    model.compute_history(data)
    return data


def split(data):
    """Indices of train, validation and test, by the date of the attempt."""
    v = datetime.strptime(VALIDATION_FROM, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    t = datetime.strptime(TEST_FROM, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()
    train, valid, test = [], [], []
    for i, when in enumerate(data.t):
        (train if when < v else valid if when < t else test).append(i)
    return train, valid, test


# -------------------------------------------------------------- the metrics

def log_loss(ps, ys):
    """Average of -[y log p + (1-y) log(1-p)]. Clipped so one p of exactly 0
    or 1 cannot make the average infinite -- which is a real risk for a model
    that is confident enough, and exactly the confidence log loss exists to
    punish."""
    total = 0.0
    for p, y in zip(ps, ys):
        p = min(max(p, 1e-12), 1 - 1e-12)
        total -= math.log(p) if y else math.log(1 - p)
    return total / len(ys)


def report(data, idx, ps):
    """Section 9's number, and the calibration behind it.

    Returns {"total", "by_stratum", "ece", "bins"}. `total` is weighted by each
    stratum's POPULATION (sample_strata), not by how many attempts it
    contributed: 1000-1199 is 37% of the active audience in 1000-1999 but its
    users submit least, so an unweighted average would describe the sample's
    most active users, not the people the site is for (ADR 0009).
    """
    ys = [data.y[i] for i in idx]
    strata = defaultdict(lambda: ([], []))
    for i, p in zip(idx, ps):
        strata[data.s[i]][0].append(p)
        strata[data.s[i]][1].append(data.y[i])
    by_stratum = {s: log_loss(p, y) for s, (p, y) in strata.items() if s is not None}
    weight = sum(data.population[s] for s in by_stratum)
    total = sum(data.population[s] * v for s, v in by_stratum.items()) / weight

    # Calibration: bins by what the model SAID, which works for any model --
    # binning by rating gap only made sense while the gap was the only input.
    bins = defaultdict(lambda: [0, 0, 0.0])
    for p, y in zip(ps, ys):
        b = min(int(p * 10), 9)
        bins[b][0] += 1
        bins[b][1] += y
        bins[b][2] += p
    ece = sum(abs(k / n - e / n) * n for n, k, e in bins.values()) / len(ys)
    return {
        "total": total,
        "unweighted": log_loss(ps, ys),
        "by_stratum": dict(sorted(by_stratum.items())),
        "ece": ece,
        "bins": {b: (n, k / n, e / n) for b, (n, k, e) in sorted(bins.items())},
    }


def print_report(name, r, calibration=False):
    strata = "  ".join(f"{s}:{v:.4f}" for s, v in r["by_stratum"].items())
    print(f"{name:<34} {r['total']:.4f}   calib {r['ece'] * 100:4.1f}pt   {strata}")
    if calibration:
        print(f"{'':>6}{'model said':>12}{'real':>8}{'attempts':>11}")
        for b, (n, real, said) in r["bins"].items():
            print(f"{'':>6}{said:>12.1%}{real:>8.1%}{n:>11,}")


# ------------------------------------------------------------- the baseline

def baseline_predictions(data, train, idx):
    """The rating-only baseline, refitted on TRAIN ONLY, scoring `idx`.

    Not read from baseline.json: that file was fitted on all of dataset.db,
    test set included, and using it here would let the baseline see the
    answers -- ADR 0012's first consequence.

    On the SHOWN rating's gap, as the baseline has always been defined: it is
    the fixed reference, and the fact that a new account's profile
    understates its rating is something a model gets credit for knowing."""
    counts = defaultdict(lambda: [0, 0])
    for i in train:
        gap = round(data.g_shown[i] * model.SCALE)
        counts[gap][0] += 1
        counts[gap][1] += data.y[i]
    a, b, _ = model.fit_logistic(dict(counts))
    return [model.sigmoid(a + b * data.g_shown[i]) for i in idx], (a, b)


# ------------------------------------------------------------- the fold-in

def month_start(month):
    """"2026-03" -> seconds since 1970 at 2026-03-01T00:00:00Z."""
    return datetime.strptime(month + "-01", "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()


def foldin_predictions(m, data, idx, halflife_days=None, log=None):
    """Predict `idx` the way the website will: each user refitted from their
    OWN history before the month being predicted, the rest of the model fixed.

    For every (user, month) in `idx`, the user's history is every attempt
    they made before the first of that month -- in training or not, because
    the website knows a visitor's whole past -- and none after. Their
    parameters are fitted to it by m.fold_in(), and that month's attempts are
    predicted with them. Monthly, not per attempt: an attempt on 14 March is
    predicted from what was known on 1 March. That is a little staler than
    the site, which refits on every visit, so these numbers slightly UNDER-
    state what the site will do, never over-state it.

    `halflife_days` makes an attempt count half as much for every that-many
    days of age, measured from the month being predicted. None = no decay.
    """
    times = defaultdict(list)
    attempts = defaultdict(list)
    for i in range(len(data)):
        times[data.u[i]].append(data.t[i])
        attempts[data.u[i]].append(i)

    groups = defaultdict(list)
    for i in idx:
        groups[(data.u[i], data.month[i])].append(i)

    predicted, warm = {}, {}
    started = time.time()
    for n, (u, month) in enumerate(sorted(groups)):
        cutoff = month_start(month)
        history = attempts[u][:bisect.bisect_left(times[u], cutoff)]
        weights = None
        if halflife_days is not None and history:
            decay = halflife_days * 86400.0
            weights = [0.5 ** ((cutoff - data.t[i]) / decay) for i in history]
        user = m.fold_in(data, history, weights, start=warm.get(u))
        warm[u] = user
        for i in groups[(u, month)]:
            predicted[i] = m.predict(data, i, user)
        if log and (n + 1) % 5000 == 0:
            log(f"    fold-in {n + 1:,}/{len(groups):,} ({time.time() - started:.0f}s)")
    return [predicted[i] for i in idx]


# --------------------------------------------------------------- the ladder
#
# Information added one kind at a time, each measured on VALIDATION, so the
# gain of every step is known separately. If a step does not lower validation
# log loss, it does not go in -- however reasonable it sounded.
#
# Each rung's regularisation is chosen from a small grid on validation.
# The grids differ by group because the groups differ in how much evidence
# each parameter gets: a problem's d is pushed by every attempt on it with
# weight 1, while a user's s for one topic is pushed by their attempts in
# that topic with weight 1/(tags), and its curvature by 1/(tags)^2 -- so the
# same lam means roughly nine times more doubt for s than for d.

RUNGS = (
    ("+ context", (), {}),
    ("+ topic difficulty", ("tag",), {"tag": (1.0, 3.0, 10.0)}),
    ("+ problem difficulty", ("tag", "problem"), {"problem": (1.0, 3.0, 10.0, 30.0)}),
    ("+ user, beyond rating", ("tag", "problem", "user"), {"user": (10.0, 30.0, 100.0, 300.0)}),
    ("+ user in each topic", ("tag", "problem", "user", "user_topic"),
     {"user_topic": (3.0, 10.0, 30.0, 100.0)}),
)
HALFLIVES = (730, 365, 180)


def evaluate_model(m, data, train, idx, halflife_days=None, log=None):
    """Fit on train, predict idx: with a fold-in when there are user terms."""
    m.fit(data, train)
    if {"user", "user_topic"} & m.groups:
        return foldin_predictions(m, data, idx, halflife_days, log)
    return [m.predict(data, i) for i in idx]


def run_ladder(data, train, valid):
    """Every rung on validation. Prints the table the devlog records."""
    log = lambda msg: print(msg, flush=True)
    ps, _ = baseline_predictions(data, train, valid)
    best = report(data, valid, ps)
    print_report("baseline (rating only)", best)

    chosen = {}
    for name, groups, grid in RUNGS:
        (group, values), = grid.items() if grid else ((None, (None,)),)
        results = []
        for value in values:
            lam = dict(chosen)
            if group:
                lam[group] = value
            started = time.time()
            m = model.TopicModel(groups, lam)
            r = report(data, valid, evaluate_model(m, data, train, valid))
            label = f"{name}" + (f" (lam {value:g})" if group else "")
            print_report(label, r)
            log(f"{'':>36}{m.sweeps} sweeps, {time.time() - started:.0f}s")
            results.append((r["total"], value, r))
        total, value, r = min(results, key=lambda x: x[0])
        if group:
            chosen[group] = value
        verdict = "better" if total < best["total"] else "no gain"
        print(f"{'':>36}-> {verdict}: {best['total'] - total:+.4f}\n", flush=True)
        if total < best["total"]:
            best = r
        last = r

    # The comparison for "no decay" is the LAST rung -- the full model, which
    # is what the decay is applied to -- not `best`, which may be a smaller
    # model if the last rung did not help.
    groups = RUNGS[-1][1]
    results = [(last["total"], None)]
    for halflife in HALFLIVES:
        m = model.TopicModel(groups, chosen)
        r = report(data, valid, evaluate_model(m, data, train, valid, halflife))
        print_report(f"+ recent history counts more ({halflife}d)", r)
        results.append((r["total"], halflife))
    halflife = min(results, key=lambda x: x[0])[1]
    print(f"{'':>36}-> half-life: {halflife}\n", flush=True)

    # ABLATION. The rungs above add each kind of information in one order, so
    # each gain is measured given only what came before it. Topic difficulty,
    # for instance, may matter little on its own and a lot once problems have
    # their own terms -- it is what a problem never seen before falls back on.
    # So: the full model with each group taken out, one at a time. A group
    # whose removal does not hurt does not belong in the model.
    print("ablation -- the full model, minus one group at a time")
    full = report(data, valid, evaluate_model(
        model.TopicModel(groups, chosen), data, train, valid, halflife))
    print_report("full model", full)
    for group in groups:
        m = model.TopicModel([g for g in groups if g != group], chosen)
        r = report(data, valid, evaluate_model(m, data, train, valid, halflife))
        print_report(f"  without {group}", r)
        print(f"{'':>36}removing it costs {r['total'] - full['total']:+.4f}", flush=True)
    print(f"\nchosen: groups {groups}, regularisation {chosen}, half-life {halflife}")


# ------------------------------------------------------- the second ladder
#
# The first ladder added the sparse groups. This one adds global columns to
# whatever the first chose -- each a question the first round's residuals
# raised -- and then asks whether a calibration layer is needed on top.

def platt(ps, ys):
    """Fit P' = sigmoid(a + b * logit(P)): one line through the model's own
    log-odds. Two parameters, so it can fix a model that is systematically
    too confident, or not confident enough, or shifted -- and nothing else.
    It cannot overfit to speak of, and it cannot reorder anybody's problems:
    it is monotone, so the five nearest 50% are chosen by the same ranking."""
    counts = defaultdict(lambda: [0, 0])
    for p, y in zip(ps, ys):
        x = round(model.logit(min(max(p, 1e-9), 1 - 1e-9)) * 100)
        counts[x][0] += 1
        counts[x][1] += y
    a, b, _ = model.fit_logistic(dict(counts))
    return a, b


def apply_platt(ps, a, b):
    return [model.sigmoid(a + b * model.logit(min(max(p, 1e-9), 1 - 1e-9))) for p in ps]


def run_extras(data, train, valid, base):
    """Each extra column on top of `base`, measured on validation, kept only
    if it helps; then a calibration layer, judged fairly."""
    groups, lam, halflife = base["groups"], base["lam"], base["halflife"]
    fit = lambda extras: report(data, valid, evaluate_model(
        model.TopicModel(groups, lam, extras=extras), data, train, valid, halflife))

    best = fit(())
    print_report("round 1's model", best)
    kept = []
    for extra in model.EXTRAS:
        started = time.time()
        r = fit(tuple(kept) + (extra,))
        print_report(f"+ {extra}", r)
        gain = best["total"] - r["total"]
        print(f"{'':>36}{time.time() - started:.0f}s -> "
              f"{'KEEP' if gain > 0 else 'drop'}: {gain:+.4f}", flush=True)
        if gain > 0:
            kept.append(extra)
            best = r

    # Calibration. Fitting a correction on validation and scoring it on the
    # same validation would flatter it, so it is fitted on the first three
    # months of validation and judged on the last three.
    m = model.TopicModel(groups, lam, extras=kept)
    ps = evaluate_model(m, data, train, valid, halflife)
    first = [n for n, i in enumerate(valid) if data.month[i] <= "2025-09"]
    last = [n for n, i in enumerate(valid) if data.month[i] > "2025-09"]
    a, b = platt([ps[n] for n in first], [data.y[valid[n]] for n in first])
    raw = report(data, [valid[n] for n in last], [ps[n] for n in last])
    fixed = report(data, [valid[n] for n in last], apply_platt([ps[n] for n in last], a, b))
    print(f"\ncalibration layer: a={a:+.4f} b={b:.4f}, fitted on 2025-07..09, judged on 2025-10..12")
    print_report("  without it", raw, calibration=True)
    print_report("  with it", fixed, calibration=True)
    print(f"\nchosen extras: {kept}")


# ------------------------------------------------------- the monthly refit
#
# Everything above FREEZES the crowd's part of the model at the start of the
# period being predicted. That is honest for a dataset collected once and never
# again -- and it wastes the most valuable part of the model. A problem's own
# difficulty was worth more than every other kind of information put together
# (+0.026 on validation), and half of 2026's attempts are on problems released
# after any frozen model was fitted, so for them it is simply zero.
#
# The alternative is a product decision, not a trick: re-collect every month
# and refit. This measures what that decision buys, with the same rule as
# everything else -- a month is predicted only from what existed before it.

def rolling_predictions(make, data, idx, halflife_days=None, log=None):
    """Refit the whole model on the first of every month, from every attempt
    before that day, then fold each user in and predict that month."""
    by_month = defaultdict(list)
    for i in idx:
        by_month[data.month[i]].append(i)
    predicted = {}
    m = make()
    for month in sorted(by_month):
        started = time.time()
        # `data` is in time order, so "everything before the first of the
        # month" is a prefix of it.
        before = list(range(bisect.bisect_left(data.t, month_start(month))))
        m.fit(data, before)          # starts from last month's answer
        for i, p in zip(by_month[month],
                        foldin_predictions(m, data, by_month[month], halflife_days)):
            predicted[i] = p
        if log:
            log(f"    {month}: refitted on {len(before):,}, {m.sweeps} sweeps, "
                f"{time.time() - started:.0f}s")
    return [predicted[i] for i in idx]


def run_rolling(data, train, valid, config):
    """Frozen against refitted monthly, on validation, same configuration."""
    make = lambda: model.TopicModel(config["groups"], config["lam"],
                                    extras=config.get("extras", ()))
    log = lambda msg: print(msg, flush=True)
    frozen = report(data, valid, evaluate_model(make(), data, train, valid, config["halflife"]))
    print_report("frozen at the start of validation", frozen)
    rolling = report(data, valid, rolling_predictions(make, data, valid, config["halflife"], log))
    print_report("refitted on the 1st of every month", rolling)
    print(f"\nmonthly refit is worth {frozen['total'] - rolling['total']:+.4f} on validation")


# ------------------------------------------------- how far off, per person
#
# Added 2026-09-28 for ADR 0027. The "too hard" / "too easy" staircase needs a
# first step, and the right size depends on how wrong the model usually is
# about ONE person -- which section 9's log loss, an average over everybody,
# does not say. This measures it on validation, with the same frozen fit and
# fold-in as the ladder.

def logit(p):
    """Probability -> log-odds, clipped so 0 and 1 stay finite."""
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def offset_of(zs, ys):
    """One person's offset: roughly the shift in log-odds, added to every one
    of their predictions, that would make them fit that person's outcomes.

    `zs` are the model's log-odds for their attempts, `ys` what happened.
    (solves - expected solves) / information -- one Newton step from zero.
    Returns (offset, variance): the variance is how much of the offset could
    be luck, one over the information in their attempts. Twenty coin-flip
    attempts carry little; five hundred carry a lot.

    One step, not a fit run to convergence, and on purpose. The first version
    fitted each person exactly and took the variance at that fit. Checked on
    made-up people with a known spread (tests/check_offsets.py), it found
    less than half of it when people had 20 attempts: an extreme estimate
    came with a large variance of its own, so real_spread discounted exactly
    the people who carried the signal. Here the variance comes from the
    model's probabilities alone, the same whatever the person did, and the
    spread comes back within a tenth even at 20 attempts. What is given up is
    a little accuracy for people far from the model, whose offset one step
    understates -- a few percent at the sizes measured.
    """
    ps = [model.sigmoid(z) for z in zs]
    information = sum(p * (1 - p) for p in ps)
    return sum(y - p for y, p in zip(ys, ps)) / information, 1 / information


def real_spread(estimates):
    """How much people really differ, with the luck taken out.

    Every person's offset is estimated with noise, so the offsets you SEE are
    more spread out than the offsets people HAVE. This is DerSimonian-Laird,
    the method meta-analyses use to combine studies of different sizes: weigh
    each estimate by how precise it is, measure how much more they disagree
    than their own noise explains, and call the excess the real spread, tau.
    Returns (mean, tau), both in log-odds.
    """
    w = [1 / v for _, v in estimates]
    total = sum(w)
    mean = sum(wi * d for wi, (d, _) in zip(w, estimates)) / total
    q = sum(wi * (d - mean) ** 2 for wi, (d, _) in zip(w, estimates))
    tau2 = (q - (len(estimates) - 1)) / (total - sum(wi * wi for wi in w) / total)
    return mean, math.sqrt(max(0.0, tau2))


def as_points(d):
    """A shift in log-odds, as percentage points at 50% -- the unit of the
    target, so the answer reads directly as a staircase step."""
    return 100 * (model.sigmoid(d) - 0.5)


def run_offsets(data, train, valid, min_attempts=20):
    """Section 9's model on validation, and how far off it is per person."""
    log = lambda msg: print(msg, flush=True)
    cfg = ROUND_THREE
    m = model.TopicModel(cfg["groups"], cfg["lam"], extras=cfg["extras"])
    ps = evaluate_model(m, data, train, valid, cfg["halflife"], log=log)
    base, _ = baseline_predictions(data, train, valid)
    print_report("round three, frozen, validation", report(data, valid, ps))

    def spread_of(predictions, months=None, least=min_attempts):
        """Each person's (offset, variance), for those with `least` attempts
        in `months` (None: all of validation)."""
        by_user = defaultdict(lambda: ([], []))
        for i, p in zip(valid, predictions):
            if months is None or data.month[i] in months:
                by_user[data.u[i]][0].append(logit(p))
                by_user[data.u[i]][1].append(data.y[i])
        return {u: offset_of(zs, ys) for u, (zs, ys) in by_user.items() if len(ys) >= least}

    # Normal around the mean with sd tau: the share of people off by more
    # than x. From tau, not from each person's estimate -- those are pulled
    # toward the mean by their own noise and would understate the tails.
    def beyond(mean, tau, x):
        cdf = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))
        return (1 - cdf((x - mean) / tau)) + cdf((-x - mean) / tau)

    print(f"\n{'':<24}{'people':>8}{'bias':>7}{'spread':>8}   off by more than 5 / 7.5 / 10 points")
    for name, predictions in (("topic model", ps), ("rating-only baseline", base)):
        est = spread_of(predictions)
        mean, tau = real_spread(list(est.values()))
        shares = "  ".join(f"{beyond(mean, tau, logit(0.5 + x / 100)):4.0%}" for x in (5, 7.5, 10))
        print(f"{name:<24}{len(est):>8,}{as_points(mean):>+7.1f}{as_points(tau):>8.1f}   {shares}")

    # Is an offset a trait? The luck in two halves of the same person's
    # attempts is independent, so the covariance of their two estimates is
    # the variance of the part that lasts.
    # 15 attempts a quarter rather than 20: half the time, nearly as much to
    # go on per attempt, and enough people left in both halves.
    q3 = spread_of(ps, ("2025-07", "2025-08", "2025-09"), least=15)
    q4 = spread_of(ps, ("2025-10", "2025-11", "2025-12"), least=15)
    both = [u for u in q3 if u in q4]
    a = [q3[u][0] for u in both]
    b = [q4[u][0] for u in both]
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    lasting = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / (len(both) - 1)
    print(f"\nthe part that lasts from one quarter to the next: "
          f"{as_points(math.sqrt(max(lasting, 0.0))):.1f} points ({len(both):,} people in both)")


# ---------------------------------------------------------------- the test

# What each ladder chose on validation. Filled in from the ladders' output and
# committed BEFORE `evaluate.py final` is ever run, so the choice is on record
# as having been made without the test set.
# Round one, 2026-09-18, validation (276,535 attempts): baseline 0.6533; +
# context 0.6515; + topic difficulty 0.6456; + problem difficulty 0.6195; +
# user 0.6148; + user in each topic 0.6147; half-life 180 days 0.6139
# (730: 0.6143, 365: 0.6141). Regularisation as chosen by each rung's grid.
ROUND_ONE = {
    "groups": ("tag", "problem", "user", "user_topic"),
    "lam": {"tag": 10.0, "problem": 3.0, "user": 30.0, "user_topic": 30.0},
    "halflife": 180,
}
# Round two, 2026-09-18, on top of round one: + shape 0.6126; + level 0.6058;
# + experience 0.6049; + position 0.6044; + trend 0.6038, with calibration down
# from 3.0 points to 1.0. Half-lives re-checked: 120d 0.6139, 90d 0.6140, 60d
# 0.6144 against 180d's 0.6139 -- a shallow U, 180 kept. A calibration layer
# fitted on 2025-07..09 made 2025-10..12 WORSE (0.5996 -> 0.6006): the trend
# column had already fixed what it was there for, so there is none.
ROUND_TWO = dict(ROUND_ONE, extras=("shape", "level", "experience", "position", "trend"))

# Round three, 2026-09-18, on top of round two (ADR 0015). Validation, frozen:
# + the 23 practice-history columns 0.6012 (from 0.6038), every stratum
# better, calibration 1.0 point; then the rating Codeforces computes with in
# place of the one it shows, for a new account's first six contests: 0.6010.
# Screened and not kept, each on top of history: the hidden amount as two
# learned columns 0.6008 and with rating dynamics 0.6008 -- differences below
# what validation can resolve, and learned from a sample drawn on its FUTURE
# rating (ADR 0015); level x topic +0.0006 and three others ~0 in the screen.
# The computed rating is not a switch here: evaluate.load() builds every
# model's inputs from it, and only the baseline keeps the shown one.
ROUND_THREE = dict(ROUND_TWO, extras=ROUND_TWO["extras"] + ("history",))

# The configuration section 9's number is reported for. Chosen on validation
# and committed before `evaluate.py final` is run for it.
#
# The first FINAL was ROUND_TWO: refitting on the 1st of every month was worth
# +0.0031 on validation (0.6038 frozen, 0.6007 monthly), in every stratum,
# with calibration unchanged at 1.0 point -- so the product re-collects and
# refits monthly (ADR 0014). It scored 0.5989 on the test set, once, on
# 2026-09-18 (commit 0100491).
#
# This is the second, and the second look at the same test set: ADR 0013's
# amendment says why that is allowed once and on what terms. Round three
# ships on its validation result; the test number is reported whatever it is,
# and does not decide between the two. Refitted monthly it scored 0.5980 on
# validation (round two 0.6007), and on the test set, on 2026-09-18, 0.5934 --
# lower than round two's 0.5989 in every stratum. The test set is now spent.
FINAL = dict(ROUND_THREE, rolling=True, platt=False)


def run_final(data, train, valid, test):
    """Section 9's number. Run once.

    Both predictors are refitted on train + validation -- everything before
    the test period -- because that is what each would have known on the day
    the test period began. Then the test period is scored, by the same
    fold-in the website uses, and printed per stratum with calibration.
    """
    if FINAL is None:
        raise SystemExit("FINAL is not set: run the ladder, record its choice, then this.")
    log = lambda msg: print(msg, flush=True)
    before = train + valid
    ps, _ = baseline_predictions(data, before, test)
    base = report(data, test, ps)
    print_report("baseline (rating only), TEST", base, calibration=True)
    print()
    make = lambda: model.TopicModel(FINAL["groups"], FINAL["lam"], extras=FINAL["extras"])
    if FINAL.get("rolling"):
        ps = rolling_predictions(make, data, test, FINAL["halflife"], log=log)
    else:
        ps = evaluate_model(make(), data, before, test, FINAL["halflife"], log=log)
    if FINAL.get("platt"):
        # The correction is learned where it can be learned honestly: from the
        # train-fitted model's predictions on validation, which is the same
        # six-months-ahead situation the test period is in. The test set
        # contributes nothing to it.
        held_out = evaluate_model(make(), data, train, valid, FINAL["halflife"])
        a, b = platt(held_out, [data.y[i] for i in valid])
        log(f"calibration layer from validation: a={a:+.4f} b={b:.4f}")
        ps = apply_platt(ps, a, b)
    r = report(data, test, ps)
    print_report("topic model, TEST", r, calibration=True)
    print(f"\nsection 9: {base['total']:.4f} -> {r['total']:.4f} "
          f"({(base['total'] - r['total']) / base['total']:.1%} lower)")
    for s in r["by_stratum"]:
        print(f"  {s}-{s + 199}: {base['by_stratum'][s]:.4f} -> {r['by_stratum'][s]:.4f}")


# ------------------------------------------------- the model that shipped
#
# Added 2026-10-03 (ADR 0013, the forward test). `final` scores a KIND of
# model: the configuration, refitted inside this harness, on a year it was
# not fitted on. This scores a FILE: the topic_model.json that was serving
# visitors, on first attempts made after the newest attempt it was fitted
# on. Nothing is refitted. It is the plainest question the project can ask of
# itself: the predictions the site was actually making -- did they come true?
#
# WHAT IS FROZEN, and what is not:
#   * the crowd's part of the model -- every number in the file -- is exactly
#     as committed. It is read out of git, not off the disk, so the file
#     scored is the file that shipped, byte for byte;
#   * each user's own numbers (b, and s per topic) are folded in ONCE, from
#     their attempts before the window opens. The site folds a visitor in
#     again on every visit, from everything up to that visit, so this is a
#     little staler than the site and UNDERstates it -- the same direction
#     as the monthly fold-in above, and for the same reason: a number that
#     flatters the model is worth nothing;
#   * the columns that describe one attempt -- the rating at the time, how
#     many attempts came before, what was practised in the last hour and
#     day -- are built from what came strictly before THAT attempt, as they
#     are everywhere in this file. An attempt's own result is never an input
#     to its own prediction, and a check proves it by flipping results.
#
# The window opens on a whole day, after every user's last fetch for the
# data the model saw (the last one was 2026-09-15T09:24Z).
FORWARD_FROM = "2026-09-16"

# The model file records the newest attempt it was fitted on, indirectly:
# trend_until is that moment plus this many seconds (model.export_fitted).
TREND_MARGIN = 183 * 86400.0


def committed(revision, name):
    """A file as it was committed at `revision`, parsed as JSON.

    `git show <revision>:<name>`, read here rather than copied to disk by
    hand, for two reasons. A copy on disk can be edited, or be the wrong
    one; the revision is the record of which model was scored. And on
    Windows a shell's `>` rewrites the file in another encoding on the way.
    """
    import json
    import subprocess
    shown = subprocess.run(["git", "show", f"{revision}:{name}"], capture_output=True)
    if shown.returncode:
        raise SystemExit(f"git has no {name} at {revision}: {shown.stderr.decode(errors='replace').strip()}")
    return json.loads(shown.stdout.decode("utf-8"))


def frozen_predictions(m, data, idx, cutoff, halflife_days=None):
    """Predict `idx` from what was known at `cutoff`: each user is folded in
    once, from their attempts before `cutoff`, and every attempt of theirs in
    `idx` is predicted with those numbers.

    The difference from foldin_predictions is the moment of the fold-in. That
    one refits a user on the first of every month, because it follows a model
    through a year. Here there is one moment that matters -- the last one the
    shipped model knew anything about -- and using a later one would let
    results from inside the window shape the user's numbers.
    """
    history = defaultdict(list)
    for i in range(len(data)):
        if data.t[i] < cutoff:
            history[data.u[i]].append(i)
    users, predicted = {}, []
    for i in idx:
        if data.t[i] < cutoff:
            raise ValueError("an attempt from before the cutoff was asked to be scored")
        u = data.u[i]
        if u not in users:
            weights = None
            if halflife_days is not None and history[u]:
                decay = halflife_days * 86400.0
                weights = [0.5 ** ((cutoff - data.t[j]) / decay) for j in history[u]]
            users[u] = m.fold_in(data, history[u], weights)
        predicted.append(m.predict(data, i, users[u]))
    return predicted


def interval(data, idx, base, ps, rounds=2000, seed=20261003):
    """How far the gap between baseline and model could be luck: a 95%
    interval for (baseline's total - model's total), by bootstrap.

    A bootstrap asks "if a different 4,000 people had been sampled, how
    different would this number be?" by drawing people from the ones we have,
    with replacement, and recomputing -- here `rounds` times. The middle 95%
    of the results is the interval. If it does not include zero, the gap is
    larger than the luck of who happened to be in the sample.

    USERS are drawn, not attempts. One person's attempts rise and fall
    together -- a good fortnight, a hard contest -- so treating 40,000
    attempts as 40,000 independent coin flips would make the interval far
    too narrow. Drawn within each stratum, because the total is weighted by
    stratum and the sample was drawn that way (ADR 0009).

    The seed is fixed: the same data gives the same interval, so a number
    written down can be reproduced.
    """
    import random
    loss = lambda p, y: -math.log(min(max(p if y else 1 - p, 1e-12), 1.0))
    # Each user's contribution, once: (their attempts, baseline loss, model loss).
    per_user = defaultdict(lambda: [0, 0.0, 0.0])
    stratum_of = {}
    for i, b, p in zip(idx, base, ps):
        if data.s[i] is None:
            continue
        row = per_user[data.u[i]]
        row[0] += 1
        row[1] += loss(b, data.y[i])
        row[2] += loss(p, data.y[i])
        stratum_of[data.u[i]] = data.s[i]
    by_stratum = defaultdict(list)
    for u, row in per_user.items():
        by_stratum[stratum_of[u]].append(row)
    weight = sum(data.population[s] for s in by_stratum)

    rng = random.Random(seed)
    gaps = []
    for _ in range(rounds):
        gap = 0.0
        for s, rows in by_stratum.items():
            n = base_loss = model_loss = 0.0
            for _ in rows:
                count, b, p = rows[rng.randrange(len(rows))]
                n += count
                base_loss += b
                model_loss += p
            gap += data.population[s] * (base_loss - model_loss) / n
        gaps.append(gap / weight)
    gaps.sort()
    return gaps[int(0.025 * rounds)], gaps[int(0.975 * rounds) - 1]


def run_forward(data, fitted, baseline, since=FORWARD_FROM, users=None):
    """The shipped files, on the first attempts made since `since`.

    `fitted` and `baseline` are topic_model.json and baseline.json as they
    were committed. Prints the same report as `final`, then the same two
    numbers for problems the model had a difficulty for and for problems
    released since, and how much of the gap could be luck.
    """
    cutoff = datetime.strptime(since, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp()

    # THE ONE WAY THIS CAN LIE: scoring a model on attempts it was fitted
    # on. The file says how recent its newest attempt was, so ask it, and
    # refuse. Without this, pointing the command at today's model would
    # print a splendid number and no error.
    newest = fitted["trend_until"] - TREND_MARGIN
    if newest >= cutoff:
        seen = datetime.fromtimestamp(newest, timezone.utc).strftime(db.TIMESTAMP_FORMAT)
        raise SystemExit(f"this model was fitted on attempts up to {seen}, inside the window "
                         f"that opens {since}: it has seen the answers. Score an earlier file.")
    if baseline.get("attempts") != fitted.get("attempts"):
        raise SystemExit(f"the baseline was fitted on {baseline.get('attempts'):,} attempts and the "
                         f"model on {fitted.get('attempts'):,}: they are not from the same data.")

    window = [i for i in range(len(data)) if data.t[i] >= cutoff]
    if users:
        window = [i for i in window if data.u[i] < users]
    if not window:
        raise SystemExit(f"no first attempts on or after {since} in this dataset: "
                         "has collect.py refresh been run since?")

    # The file's numbers, placed on this dataset's problems and tags by name.
    # A problem the file has no difficulty for gets none -- zero, the average
    # -- exactly as the site scores a problem released since the last fit.
    problem_index = {pid: p for p, pid in enumerate(data.problems)}
    tag_index = {name: k for k, name in enumerate(data.tag_names)}
    m = model.fitted_model(fitted, problem_index, tag_index)

    ps = frozen_predictions(m, data, window, cutoff, fitted.get("halflife"))
    # The baseline file's curve, on the rating Codeforces shows, as the
    # baseline has always been defined (baseline_predictions).
    a, b = baseline["intercept"], baseline["slope"]
    base = [model.sigmoid(a + b * data.g_shown[i]) for i in window]

    last = datetime.fromtimestamp(max(data.t[i] for i in window), timezone.utc)
    people = len({data.u[i] for i in window})
    print(f"{len(window):,} first attempts by {people:,} people, {since} to {last:%Y-%m-%d}; "
          f"model fitted on {fitted['attempts']:,} attempts up to "
          f"{datetime.fromtimestamp(newest, timezone.utc):%Y-%m-%d}\n")

    rb, rm = report(data, window, base), report(data, window, ps)
    print_report("baseline file (rating only), FORWARD", rb, calibration=True)
    print()
    print_report("shipped model, FORWARD", rm, calibration=True)
    print(f"\nforward: {rb['total']:.4f} -> {rm['total']:.4f} "
          f"({(rb['total'] - rm['total']) / rb['total']:.1%} lower)")
    for s in rm["by_stratum"]:
        print(f"  {s}-{s + 199}: {rb['by_stratum'][s]:.4f} -> {rm['by_stratum'][s]:.4f}")
    low, high = interval(data, window, base, ps)
    print(f"  the gap is {rb['total'] - rm['total']:.4f}; with other people sampled it would "
          f"fall between {low:.4f} and {high:.4f} (95%)")

    # The same, split by whether the file knew the problem. A problem
    # released after the fit has no difficulty of its own until the next one:
    # this is what a month without a refit costs.
    known = [k for k, i in enumerate(window) if data.problems[data.p[i]] in fitted["d"]]
    new = [k for k, i in enumerate(window) if data.problems[data.p[i]] not in fitted["d"]]
    for name, part in (("problems the model had a difficulty for", known),
                       ("problems released since", new)):
        if not part:
            continue
        idx = [window[k] for k in part]
        print(f"\n{name}: {len(part):,} attempts")
        print_report("  baseline", report(data, idx, [base[k] for k in part]))
        print_report("  shipped model", report(data, idx, [ps[k] for k in part]))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("command", choices=("baseline", "ladder", "extras", "rolling", "offsets",
                                            "final", "forward"))
    parser.add_argument("--db", default="dataset.db")
    parser.add_argument("--shipped", default=None,
                        help="forward: the git revision whose topic_model.json and "
                             "baseline.json are scored, e.g. 0d4360c")
    parser.add_argument("--since", default=FORWARD_FROM,
                        help="forward: the first day of the window, YYYY-MM-DD")
    parser.add_argument("--users", type=int, default=None,
                        help="keep only the first N users -- a quick run that "
                             "exercises everything, for checking the code, never "
                             "for a number that gets written down")
    args = parser.parse_args()

    started = time.time()
    conn = db.connect(Path(args.db))
    try:
        data = load(conn)
    finally:
        conn.close()
    train, valid, test = split(data)
    if args.users:
        keep = set(range(args.users))
        train, valid, test = ([i for i in part if data.u[i] in keep]
                              for part in (train, valid, test))
    print(f"{len(data):,} first attempts: train {len(train):,}, validation {len(valid):,}, "
          f"test {len(test):,}  ({time.time() - started:.0f}s)\n")

    if args.command == "baseline":
        ps, (a, b) = baseline_predictions(data, train, valid)
        print(f"baseline refitted on train: a={a:.4f} b={b:.4f}\n")
        print_report("baseline, validation", report(data, valid, ps), calibration=True)
        return

    if args.command == "ladder":
        run_ladder(data, train, valid)
        return

    if args.command == "extras":
        if ROUND_ONE is None:
            raise SystemExit("ROUND_ONE is not set: run the ladder and record its choice first.")
        run_extras(data, train, valid, ROUND_ONE)
        return

    if args.command == "rolling":
        config = ROUND_THREE or ROUND_TWO or ROUND_ONE
        if config is None:
            raise SystemExit("record a ladder's choice first.")
        run_rolling(data, train, valid, config)
        return

    if args.command == "offsets":
        run_offsets(data, train, valid)
        return

    if args.command == "final":
        run_final(data, train, valid, test)
        return

    if args.command == "forward":
        if not args.shipped:
            raise SystemExit("forward needs the revision that was live: --shipped <git revision>, "
                             "the commit before the refit that followed it.")
        run_forward(data, committed(args.shipped, "topic_model.json"),
                    committed(args.shipped, "baseline.json"), args.since, users=args.users)


if __name__ == "__main__":
    sys.exit(main())
