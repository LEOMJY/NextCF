"""Check for the topic model and the harness -- model.py, evaluate.py.

Three kinds of check, in order of how badly a failure would hurt:

  * LEAKAGE. A prediction must not depend on anything after the moment it is
    made. Proved by changing a user's LATER results and asserting their
    EARLIER predictions do not move by a single bit. A leak inflates section
    9's number and raises no error, so this is the check that matters most.
  * THE FIT IS AT ITS OPTIMUM. On synthetic data from a known model: the
    objective recomputed from the parameters alone equals the one the fit
    kept track of (so the centring moves really are exact), and every
    parameter's gradient is near zero.
  * THE ARITHMETIC of the report: weights by population, not by attempts.
"""

import math
import os
import random
import sys
from pathlib import Path

# Paths in this file are relative to the repository root, and the modules
# being checked live there, so go there first. The check then runs the same
# from any directory.
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
import evaluate  # noqa: E402
import model  # noqa: E402

passed = failed = 0


def check(label, fn):
    global passed, failed
    try:
        fn()
    except AssertionError as exc:
        print(f"  FAIL  {label}: {exc}")
        failed += 1
    except Exception as exc:
        print(f"  FAIL  {label}: crashed with {type(exc).__name__}: {exc}")
        failed += 1
    else:
        print(f"  ok    {label}")
        passed += 1


def synthetic(seed=7, n_users=120, n_probs=200, n_tags=6, n=40_000, untagged=0.1):
    """Attempts from a known topic model, with dates spread over two years."""
    rng = random.Random(seed)
    gamma, beta = [0.2, -0.3, -0.1, 0.0], 0.13
    tau = [rng.gauss(0, 0.4) for _ in range(n_tags)]
    d = [rng.gauss(0, 0.5) for _ in range(n_probs)]
    b = [rng.gauss(0, 0.4) for _ in range(n_users)]
    s = {(u, k): rng.gauss(0, 0.5) for u in range(n_users) for k in range(n_tags)}
    data = evaluate.Attempts()
    data.problem_tags = [() if rng.random() < untagged
                         else tuple(sorted(rng.sample(range(n_tags), rng.randint(1, 3))))
                         for _ in range(n_probs)]
    start = 1_700_000_000
    rows = []
    for _ in range(n):
        u, p = rng.randrange(n_users), rng.randrange(n_probs)
        c, g = rng.choice([0, 0, 0, 1, 2, 3]), rng.uniform(-8, 8)
        tags = data.problem_tags[p]
        z = gamma[c] + beta * g + d[p] + b[u]
        if tags:
            z += sum(tau[k] + s[(u, k)] for k in tags) / len(tags)
        t = start + rng.randrange(2 * 365 * 86400)
        rows.append((t, u, p, c, g, 1 if rng.random() < model.sigmoid(z) else 0))
    rows.sort()
    seen = [0] * n_users
    for t, u, p, c, g, y in rows:
        data.u.append(u); data.p.append(p); data.c.append(c); data.g.append(g)
        data.g_shown.append(g)          # nothing hidden in synthetic ratings
        data.y.append(y); data.t.append(float(t))
        data.month.append(evaluate.datetime.fromtimestamp(t, evaluate.timezone.utc).strftime("%Y-%m"))
        data.s.append(1000 + 200 * (u % 5))
        # A rating that MOVES over the two years, as real ratings do. A
        # rating fixed per user would make the level column exactly collinear
        # with that user's b -- a direction along which the objective is
        # perfectly flat -- and an earlier version of this fixture had exactly
        # that, and a level gradient of 2e-2 that no real data would produce.
        data.r.append(((u % 9) - 4) / 2.0 + (t - start) / (365 * 86400) * ((u % 3) - 1) * 0.5)
        data.n.append(math.log1p(seen[u]))
        seen[u] += 1
    data.problem_position = [p % model.N_POSITIONS for p in range(n_probs)]
    data.population = {1000: 8091, 1200: 6708, 1400: 4155, 1600: 2281, 1800: 869}
    return model.compute_history(data)


DATA = synthetic()
ALL = list(range(len(DATA)))
LAM = {"tag": 3.0, "problem": 3.0, "user": 10.0, "user_topic": 10.0}

print("topic model and harness")


# -------------------------------------------------------------- leakage

def the_future_cannot_change_a_past_prediction():
    """Flip every result a user has in the second year. Their predictions in
    the first year must not move at all -- not by a rounding error."""
    cutoff = DATA.t[len(DATA) // 2]
    train = [i for i in ALL if DATA.t[i] < cutoff]
    evaluated = [i for i in ALL if DATA.t[i] >= cutoff]
    m = model.TopicModel(model.GROUPS, LAM).fit(DATA, train)

    early = evaluated[: len(evaluated) // 3]
    before = evaluate.foldin_predictions(m, DATA, early)
    last_month = max(DATA.month[i] for i in early)
    later = [i for i in evaluated if DATA.month[i] > last_month]
    assert later, "the fixture has no attempts after the early block"
    original = [DATA.y[i] for i in later]
    try:
        for i in later:
            DATA.y[i] = 1 - DATA.y[i]
        after = evaluate.foldin_predictions(m, DATA, early)
    finally:
        for i, y in zip(later, original):
            DATA.y[i] = y
    moved = sum(1 for a, b in zip(before, after) if a != b)
    assert moved == 0, f"{moved} earlier predictions changed when LATER results did"


def the_fold_in_uses_only_the_months_before():
    """An attempt's own result, and the rest of its month, are not history."""
    cutoff = DATA.t[len(DATA) // 2]
    train = [i for i in ALL if DATA.t[i] < cutoff]
    m = model.TopicModel(model.GROUPS, LAM).fit(DATA, train)
    target = next(i for i in ALL if DATA.t[i] >= cutoff)
    month = [i for i in ALL if DATA.u[i] == DATA.u[target] and DATA.month[i] == DATA.month[target]]
    before = evaluate.foldin_predictions(m, DATA, [target])[0]
    original = [DATA.y[i] for i in month]
    try:
        for i in month:
            DATA.y[i] = 1 - DATA.y[i]
        after = evaluate.foldin_predictions(m, DATA, [target])[0]
    finally:
        for i, y in zip(month, original):
            DATA.y[i] = y
    assert before == after, "an attempt's own month leaked into its prediction"


def the_monthly_refit_cannot_see_the_future_either():
    """The monthly refit uses the most data, so it has the most room to leak:
    each month's model is fitted on everything before that month. Flip every
    result from some month on; every month before it must predict exactly as
    it did."""
    cutoff = DATA.t[len(DATA) // 2]
    evaluated = [i for i in ALL if DATA.t[i] >= cutoff]
    months = sorted({DATA.month[i] for i in evaluated})
    early = [i for i in evaluated if DATA.month[i] in months[:2]]
    later = [i for i in ALL if DATA.month[i] > months[1]]
    make = lambda: model.TopicModel(model.GROUPS, LAM)
    before = evaluate.rolling_predictions(make, DATA, early)
    original = [DATA.y[i] for i in later]
    try:
        for i in later:
            DATA.y[i] = 1 - DATA.y[i]
        after = evaluate.rolling_predictions(make, DATA, early)
    finally:
        for i, y in zip(later, original):
            DATA.y[i] = y
    moved = sum(1 for a, b in zip(before, after) if a != b)
    assert moved == 0, f"{moved} earlier predictions changed when LATER results did"


def the_baseline_is_refitted_on_train_only():
    cutoff = DATA.t[len(DATA) // 2]
    train = [i for i in ALL if DATA.t[i] < cutoff]
    test = [i for i in ALL if DATA.t[i] >= cutoff]
    for i in train:
        DATA.g_shown[i] = round(DATA.g_shown[i] * 100) / 100
    before, _ = evaluate.baseline_predictions(DATA, train, test)
    original = [DATA.y[i] for i in test]
    try:
        for i in test:
            DATA.y[i] = 1 - DATA.y[i]
        after, _ = evaluate.baseline_predictions(DATA, train, test)
    finally:
        for i, y in zip(test, original):
            DATA.y[i] = y
    assert before == after, "the baseline's test predictions depend on the test labels"


check("changing LATER results moves no earlier prediction", the_future_cannot_change_a_past_prediction)
check("an attempt's own month is not in its history", the_fold_in_uses_only_the_months_before)
check("the monthly refit cannot see the future either", the_monthly_refit_cannot_see_the_future_either)
check("the baseline is refitted on train only", the_baseline_is_refitted_on_train_only)


# ------------------------------------------------------------ the fit

FIT = model.TopicModel(model.GROUPS, LAM).fit(DATA, ALL, max_sweeps=200, tol=1e-12)


def recompute(m):
    """The objective from the parameters alone, ignoring the fit's own `z`."""
    loss = 0.0
    users = {}
    for i in ALL:
        u = DATA.u[i]
        if u not in users:
            users[u] = (m.b.get(u, 0.0), {k: v for (uu, k), v in m.s.items() if uu == u})
        p = m.predict(DATA, i, users[u])
        loss -= math.log(p) if DATA.y[i] else math.log(1 - p)
    store = {"tag": m.tau, "problem": m.d, "user": m.b, "user_topic": m.s}
    penalty = sum(0.5 * m.lam[g] * sum(v * v for v in store[g].values()) for g in m.groups)
    return (loss + penalty) / len(ALL)


def the_centring_moves_are_exact():
    assert abs(recompute(FIT) - FIT.objective) < 1e-9, (recompute(FIT), FIT.objective)


def every_gradient_is_near_zero():
    grad = {}
    users = {}
    for i in ALL:
        u = DATA.u[i]
        if u not in users:
            users[u] = (FIT.b.get(u, 0.0), {k: v for (uu, k), v in FIT.s.items() if uu == u})
        r = DATA.y[i] - FIT.predict(DATA, i, users[u])
        tags = model._tags(DATA, DATA.p[i])
        w = 1.0 / len(tags)
        for key in (("problem", DATA.p[i]), ("user", u)):
            grad[key] = grad.get(key, 0.0) + r
        for k in tags:
            for key in (("tag", k), ("user_topic", (u, k))):
                grad[key] = grad.get(key, 0.0) + w * r
    store = {"tag": FIT.tau, "problem": FIT.d, "user": FIT.b, "user_topic": FIT.s}
    worst = max(abs(g - FIT.lam[group] * store[group].get(key, 0.0)) for (group, key), g in grad.items())
    assert worst < 1e-3, f"largest gradient {worst:.2e}"


def zero_means_average_in_every_group():
    for name, params in (("b", FIT.b), ("d", FIT.d), ("tau", FIT.tau)):
        mean = sum(params.values()) / len(params)
        assert abs(mean) < 1e-12, f"mean of {name} is {mean}"


def fold_in_reproduces_the_joint_fit():
    """What the website does for a visitor is what training did for a user."""
    u = 3
    history = [i for i in ALL if DATA.u[i] == u]
    b, s = FIT.fold_in(DATA, history, sweeps=500)
    assert abs(b - FIT.b[u]) < 1e-5, (b, FIT.b[u])
    diff = max(abs(s.get(k, 0.0) - v) for (uu, k), v in FIT.s.items() if uu == u)
    assert diff < 1e-5, diff


def the_same_data_gives_the_same_model():
    """Section 9's number has to come out the same every time."""
    again = model.TopicModel(model.GROUPS, LAM).fit(DATA, ALL, max_sweeps=200, tol=1e-12)
    assert again.objective == FIT.objective, (again.objective, FIT.objective)
    assert again.gamma == FIT.gamma and again.d == FIT.d


def every_extra_column_is_exact_and_optimal():
    """The global block with every extra switched on: still exact under the
    centring moves, and its own gradient -- the 5x5 grown to 21 columns --
    near zero, column by column."""
    m = model.TopicModel(model.GROUPS, LAM, extras=model.EXTRAS).fit(
        DATA, ALL, max_sweeps=200, tol=1e-12)
    assert abs(recompute(m) - m.objective) < 1e-9, (recompute(m), m.objective)
    # The measure is |gradient| / curvature -- how far a Newton step would
    # still move the column -- not the raw gradient. A column every attempt
    # pushes on has an enormous curvature, so the same small parameter error
    # shows up as a large raw gradient: an earlier version of this check
    # failed the level column at a raw 2.2e-2, which was a parameter error of
    # 3e-6, smaller than what the sparse groups above are allowed.
    k = len(m.gamma)
    grad = [0.0] * (k + 1 + len(m.w))
    curv = [0.0] * (k + 1 + len(m.w))
    users = {}
    for i in ALL:
        u = DATA.u[i]
        if u not in users:
            users[u] = (m.b.get(u, 0.0), {kk: v for (uu, kk), v in m.s.items() if uu == u})
        p = m.predict(DATA, i, users[u])
        r, v = DATA.y[i] - p, p * (1 - p)
        cols = [(DATA.c[i], 1.0), (k, DATA.g[i])] + [(k + 1 + a, x) for a, x in m._extra(DATA, i)]
        for a, x in cols:
            grad[a] += r * x
            curv[a] += v * x * x
    steps = [abs(g) / h for g, h in zip(grad, curv) if h]
    assert max(steps) < 1e-4, [f"{s:.1e}" for s in steps]


def solve_is_right():
    a = [[4.0, 1.0, 0.5], [1.0, 3.0, 0.2], [0.5, 0.2, 2.0]]
    x_true = [1.0, -2.0, 0.5]
    b = [sum(a[r][c] * x_true[c] for c in range(3)) for r in range(3)]
    x = model._solve(a, b)
    assert max(abs(x[i] - x_true[i]) for i in range(3)) < 1e-12, x


check("centring is exact: the objective recomputed from parameters matches", the_centring_moves_are_exact)
check("every parameter's gradient is near zero at the optimum", every_gradient_is_near_zero)
check("b, d and tau average exactly zero", zero_means_average_in_every_group)
check("fold-in reproduces the joint fit for one user", fold_in_reproduces_the_joint_fit)
check("the same data gives the same model, bit for bit", the_same_data_gives_the_same_model)
check("with every extra column: exact, and every global gradient near zero",
      every_extra_column_is_exact_and_optimal)
check("the 3x3 solver is right", solve_is_right)


# ------------------------------------------------------------ the report

def the_total_is_weighted_by_population():
    """Two strata, the smaller one with far more attempts: the weighted total
    must follow the populations, not the attempt counts."""
    d = evaluate.Attempts()
    d.population = {1000: 3, 1800: 1}
    d.y = [1] * 10 + [0] * 1000
    d.s = [1000] * 10 + [1800] * 1000
    idx = list(range(len(d.y)))
    ps = [0.5] * 10 + [0.1] * 1000
    r = evaluate.report(d, idx, ps)
    want = (3 * math.log(2) + 1 * -math.log(0.9)) / 4
    assert abs(r["total"] - want) < 1e-12, (r["total"], want)


def the_split_is_by_date():
    d = evaluate.Attempts()
    stamp = lambda s: evaluate.datetime.strptime(s, "%Y-%m-%d").replace(
        tzinfo=evaluate.timezone.utc).timestamp()
    d.t = [stamp("2025-06-30"), stamp("2025-07-01"), stamp("2025-12-31"), stamp("2026-01-01")]
    assert evaluate.split(d) == ([0], [1, 2], [3])


check("the total is weighted by population, not attempts", the_total_is_weighted_by_population)
check("the split is by date, at the documented boundaries", the_split_is_by_date)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
