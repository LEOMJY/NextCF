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


# -------------------------------------------------------- the forward test
#
# `evaluate.py forward` scores a shipped FILE on attempts made after its data
# ended (ADR 0013, 2026-10-03). A leak here is the same silent kind as
# everywhere above, so it is proved the same way: by flipping results.
#
# The stand-in for "a model that shipped": fitted on the first half of the
# synthetic history with every extra column switched on, exported exactly as
# model.py fit-topic exports topic_model.json, and loaded back by name.

SHIP_DAY = evaluate.datetime.fromtimestamp(DATA.t[len(DATA) // 2], evaluate.timezone.utc).strftime("%Y-%m-%d")
SHIP = evaluate.datetime.strptime(SHIP_DAY, "%Y-%m-%d").replace(tzinfo=evaluate.timezone.utc).timestamp()
BEFORE = [i for i in ALL if DATA.t[i] < SHIP]
WINDOW = [i for i in ALL if DATA.t[i] >= SHIP]
# Names for the synthetic problems and tags: the file is keyed by name.
DATA.problems = [f"P{p}" for p in range(len(DATA.problem_tags))]
DATA.tag_names = [f"tag{k}" for k in range(1 + max(k for tags in DATA.problem_tags for k in tags))]

SHIPPED_MODEL = model.TopicModel(model.GROUPS, LAM, extras=model.EXTRAS).fit(DATA, BEFORE)
SHIPPED = model.export_fitted(SHIPPED_MODEL, DATA, 180)
# export_fitted describes a model fitted on ALL of its data; this one saw
# only BEFORE, so the two facts the forward test reads are set to match.
SHIPPED["attempts"] = len(BEFORE)
SHIPPED["trend_until"] = max(DATA.t[i] for i in BEFORE) + evaluate.TREND_MARGIN
_, (A, B) = evaluate.baseline_predictions(DATA, BEFORE, WINDOW)
SHIPPED_BASELINE = {"intercept": A, "slope": B, "attempts": len(BEFORE)}


def loaded():
    """The file's numbers back on the data, as run_forward places them."""
    return model.fitted_model(SHIPPED, {pid: p for p, pid in enumerate(DATA.problems)},
                              {name: k for k, name in enumerate(DATA.tag_names)})


def flipped(indices, then):
    """Run `then` with every result in `indices` reversed and the history
    columns rebuilt from the reversed results; put everything back after."""
    original = [DATA.y[i] for i in indices]
    try:
        for i in indices:
            DATA.y[i] = 1 - DATA.y[i]
        model.compute_history(DATA)
        return then()
    finally:
        for i, y in zip(indices, original):
            DATA.y[i] = y
        model.compute_history(DATA)


def a_window_result_cannot_reach_back():
    """Flip every result in the second half of the window. Every prediction
    in the first half must be the same number, to the last bit: a user's own
    numbers come from before the window, and an attempt's columns from before
    the attempt."""
    half = DATA.t[WINDOW[len(WINDOW) // 2]]
    early = [i for i in WINDOW if DATA.t[i] < half]
    later = [i for i in WINDOW if DATA.t[i] >= half]
    m = loaded()
    predict = lambda: evaluate.frozen_predictions(m, DATA, early, SHIP, 180)
    before = predict()
    after = flipped(later, predict)
    moved = sum(1 for a, b in zip(before, after) if a != b)
    assert moved == 0, f"{moved} of {len(early)} earlier predictions moved when LATER results did"


def an_attempts_own_result_is_not_an_input():
    """The narrowest leak: one attempt's result changing its own prediction."""
    m = loaded()
    for target in (WINDOW[0], WINDOW[len(WINDOW) // 3], WINDOW[-1]):
        predict = lambda: evaluate.frozen_predictions(m, DATA, [target], SHIP, 180)[0]
        assert predict() == flipped([target], predict), "an attempt's result changed its own prediction"


def what_came_before_the_window_does_count():
    """The two checks above would pass for a predictor that ignored the user
    altogether. This one makes sure they are not passing for that reason: flip
    one person's results BEFORE the window and their predictions in it move."""
    m = loaded()
    user = DATA.u[WINDOW[0]]
    theirs = [i for i in WINDOW if DATA.u[i] == user]
    past = [i for i in BEFORE if DATA.u[i] == user]
    assert len(past) > 20 and theirs, "the fixture gives this user no history to learn from"
    predict = lambda: evaluate.frozen_predictions(m, DATA, theirs, SHIP, 180)
    before = predict()
    after = flipped(past, predict)
    assert max(abs(a - b) for a, b in zip(before, after)) > 0.01, \
        "a user's whole history was reversed and their predictions did not notice"


def an_attempt_from_before_the_window_is_refused():
    m = loaded()
    try:
        evaluate.frozen_predictions(m, DATA, [BEFORE[-1]], SHIP, 180)
    except ValueError:
        return
    raise AssertionError("an attempt from before the cutoff was scored as if it were after it")


def the_file_predicts_as_the_model_it_was_written_from():
    """The forward test scores what topic_model.json holds, loaded by name.
    If the round trip through the file changed the model, it would be
    scoring something that never ran. The file rounds to six decimal places,
    which moves a probability by about a millionth."""
    m = loaded()
    SHIPPED_MODEL.level_range = tuple(SHIPPED["level_range"])
    SHIPPED_MODEL.trend_until = SHIPPED["trend_until"]
    try:
        direct = evaluate.frozen_predictions(SHIPPED_MODEL, DATA, WINDOW, SHIP, 180)
    finally:
        SHIPPED_MODEL.level_range = SHIPPED_MODEL.trend_until = None
    through_file = evaluate.frozen_predictions(m, DATA, WINDOW, SHIP, 180)
    worst = max(abs(a - b) for a, b in zip(direct, through_file))
    assert worst < 1e-5, f"the file's predictions differ from the model's by up to {worst:.2e}"


def a_model_that_saw_the_window_is_refused():
    """The one way the forward test can lie, and it would print a splendid
    number doing it. A file fitted on attempts inside the window is turned
    away, by the date the file itself records."""
    import contextlib
    import io

    def refusal(fitted, baseline, since):
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                evaluate.run_forward(DATA, fitted, baseline, since)
        except SystemExit as stop:
            return str(stop)
        return ""

    seen = dict(SHIPPED, trend_until=max(DATA.t) + evaluate.TREND_MARGIN)
    assert "has seen the answers" in refusal(seen, SHIPPED_BASELINE, SHIP_DAY), \
        "a model fitted on the window's own attempts was scored on them"
    # One second inside the window is inside it.
    barely = dict(SHIPPED, trend_until=SHIP + evaluate.TREND_MARGIN)
    assert "has seen the answers" in refusal(barely, SHIPPED_BASELINE, SHIP_DAY), \
        "a model whose newest attempt is at the window's first second was scored"
    other = dict(SHIPPED_BASELINE, attempts=len(BEFORE) + 1)
    assert "not from the same data" in refusal(SHIPPED, other, SHIP_DAY), \
        "a baseline from other data was compared with the model"
    assert "no first attempts" in refusal(SHIPPED, SHIPPED_BASELINE, "2031-01-01"), \
        "an empty window was reported on"


def the_command_prints_what_the_harness_computes():
    """End to end: the total run_forward prints is report()'s total for the
    file's predictions, and the gap it prints lies inside its own interval."""
    import contextlib
    import io
    import re
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        evaluate.run_forward(DATA, SHIPPED, SHIPPED_BASELINE, SHIP_DAY)
    text = out.getvalue()
    ps = evaluate.frozen_predictions(loaded(), DATA, WINDOW, SHIP, 180)
    base = [model.sigmoid(A + B * DATA.g_shown[i]) for i in WINDOW]
    want_model = evaluate.report(DATA, WINDOW, ps)["total"]
    want_base = evaluate.report(DATA, WINDOW, base)["total"]
    assert f"forward: {want_base:.4f} -> {want_model:.4f}" in text, text[-600:]
    assert f"{len(WINDOW):,} first attempts" in text, text[:200]
    low, high = (float(x) for x in re.search(r"fall between (-?[\d.]+) and (-?[\d.]+)", text).groups())
    gap = want_base - want_model
    assert low <= gap <= high, f"the gap {gap:.4f} is outside its own interval {low:.4f}..{high:.4f}"
    # The synthetic users really do differ, so the model must beat the
    # rating-only curve here by more than luck -- or the interval is broken.
    assert low > 0, f"the model's lead over the baseline could be luck: {low:.4f}..{high:.4f}"


def the_interval_is_the_same_every_time_and_zero_for_equals():
    ps = evaluate.frozen_predictions(loaded(), DATA, WINDOW, SHIP, 180)
    base = [model.sigmoid(A + B * DATA.g_shown[i]) for i in WINDOW]
    first = evaluate.interval(DATA, WINDOW, base, ps, rounds=200)
    assert first == evaluate.interval(DATA, WINDOW, base, ps, rounds=200), "the interval changes from run to run"
    assert evaluate.interval(DATA, WINDOW, ps, ps, rounds=200) == (0.0, 0.0), \
        "a model compared with itself has a gap"


print("\nthe forward test")
check("a result inside the window moves no earlier prediction", a_window_result_cannot_reach_back)
check("an attempt's own result is not an input to its prediction", an_attempts_own_result_is_not_an_input)
check("what came before the window does count", what_came_before_the_window_does_count)
check("an attempt from before the window is refused", an_attempt_from_before_the_window_is_refused)
check("the file predicts as the model it was written from", the_file_predicts_as_the_model_it_was_written_from)
check("a model that saw the window is refused", a_model_that_saw_the_window_is_refused)
check("the command prints what the harness computes", the_command_prints_what_the_harness_computes)
check("the interval is reproducible, and zero for equals", the_interval_is_the_same_every_time_and_zero_for_equals)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
