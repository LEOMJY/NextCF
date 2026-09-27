"""Check the per-person offset measurement -- `evaluate.py offsets`, ADR 0027.

The measurement says how far off the model is about one person, and the
staircase's first step was chosen from it. Its answer can only be trusted if
the method gets the right answer where the right answer is KNOWN: people
made up here, with offsets chosen here, and outcomes drawn from them.

No dataset.db needed; seconds.
"""

import math
import os
import random
import sys
from pathlib import Path

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


def people(count, tau, attempts, seed):
    """`count` made-up people, each with a true offset drawn from N(0, tau),
    each attempting `attempts` problems the model puts anywhere from 18% to
    82%. Returns their estimated (offset, variance) pairs."""
    rng = random.Random(seed)
    out = []
    for _ in range(count):
        true = rng.gauss(0, tau)
        zs = [rng.uniform(-1.5, 1.5) for _ in range(attempts)]
        ys = [1 if rng.random() < model.sigmoid(z + true) else 0 for z in zs]
        out.append(evaluate.offset_of(zs, ys))
    return out


def one_person_s_offset_is_found():
    """400 attempts at even odds by somebody 0.4 log-odds stronger than the
    model thinks: the fit lands within its own error bar of 0.4."""
    rng = random.Random(1)
    zs = [0.0] * 400
    ys = [1 if rng.random() < model.sigmoid(0.4) else 0 for _ in zs]
    d, v = evaluate.offset_of(zs, ys)
    assert abs(d - 0.4) < 2 * math.sqrt(v), (d, math.sqrt(v))


def an_all_solved_person_stays_finite():
    """Twenty solves out of twenty is an infinite offset for an exact fit.
    Large, finite, and uncertain is the honest answer."""
    d, v = evaluate.offset_of([0.0] * 20, [1] * 20)
    assert 1 < d < 10 and v > 0, (d, v)


def the_real_spread_is_recovered():
    """The number the first step was chosen from: people truly spread by
    0.166 log-odds (4.1 points), forty attempts each."""
    _, tau = evaluate.real_spread(people(2000, 0.166, 40, seed=2))
    assert abs(tau - 0.166) < 0.04, tau


def few_attempts_do_not_hide_the_spread():
    """Found on 2026-09-28, by this file: the first method fitted each person
    exactly and found 0.073 of a true 0.166 at twenty attempts each, because
    an extreme person's own variance discounted them. offset_of's one step
    keeps the variance independent of the outcome."""
    _, tau = evaluate.real_spread(people(3000, 0.166, 20, seed=4))
    assert tau > 0.11, f"only {tau:.3f} of a true 0.166 found at twenty attempts"


def luck_is_not_mistaken_for_spread():
    """Nobody differs from the model at all; each estimate still wobbles by
    luck. The raw spread of the estimates is large -- that is the mistake
    this method exists to avoid -- and the real spread comes back near 0."""
    est = people(2000, 0.0, 40, seed=3)
    raw = math.sqrt(sum(d * d for d, _ in est) / len(est))
    _, tau = evaluate.real_spread(est)
    assert raw > 0.25, f"the raw spread was only {raw}; this checks nothing"
    assert tau < 0.05, tau


def points_are_measured_at_fifty_percent():
    assert abs(evaluate.as_points(0.166) - 4.1) < 0.05, evaluate.as_points(0.166)
    assert evaluate.as_points(0.0) == 0.0


check("one person's offset is found", one_person_s_offset_is_found)
check("an all-solved person stays finite", an_all_solved_person_stays_finite)
check("the real spread is recovered", the_real_spread_is_recovered)
check("few attempts do not hide the spread", few_attempts_do_not_hide_the_spread)
check("luck is not mistaken for spread", luck_is_not_mistaken_for_spread)
check("points are measured at 50%", points_are_measured_at_fifty_percent)

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
