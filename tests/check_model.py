"""Check for the rating-only baseline -- model.py, spec section 9.

This is the yardstick every later model is measured against, so the checks
that matter most are the ones on the arithmetic:

  * the fit recovers a curve it was GIVEN. Synthetic counts drawn from known
    a and b go in; the same a and b must come out. A fitting routine that
    only ever runs on real data can be wrong forever, because nobody knows
    what the right answer was.
  * baseline.json is what the data says TODAY. It is committed, like the
    React bundle in ADR 0011, so it can go stale the same way: somebody
    changes the alias map or the event and forgets to refit. Skipped
    unless the dataset tier is asked for.

No network: web is imported, and the fetch it can
start is started only by its entry points.
"""

import json
import math
import os
import shutil
import sys
import tempfile
import threading
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="model-"))
os.environ["NEXTCF_DB"] = str(SCRATCH / "test.db")
# Paths in this file are relative to the repository root, and the modules
# being checked live there, so go there first. The check then runs the same
# from any directory.
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import model  # noqa: E402
import sync  # noqa: E402
import web  # noqa: E402

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


FAKE = {"event": "first_try", "intercept": 0.25, "slope": 0.12}

print("rating-only baseline")


# --------------------------------------------------------------- the curve

def sigmoid_and_logit_are_inverses():
    for p in (0.01, 0.3, 0.5, 0.7, 0.99):
        assert abs(model.sigmoid(model.logit(p)) - p) < 1e-12, p


def sigmoid_survives_extremes():
    """exp(1000) overflows; the two-branch sigmoid must not call it."""
    assert model.sigmoid(1000) == 1.0
    assert model.sigmoid(-1000) == 0.0


def rating_for_probability_inverts_the_curve():
    for user in (900, 1500, 2400):
        for target in (0.3, 0.5, 0.7):
            r = model.rating_for_probability(user, target, FAKE)
            back = model.baseline_probability(user, r, FAKE)
            assert abs(back - target) < 1e-9, (user, target, r, back)


def harder_problems_are_less_likely():
    ps = [model.baseline_probability(1500, r, FAKE) for r in (800, 1200, 1500, 1900, 2500)]
    assert ps == sorted(ps, reverse=True), ps


check("sigmoid and logit are inverses", sigmoid_and_logit_are_inverses)
check("sigmoid survives +-1000 without overflow", sigmoid_survives_extremes)
check("rating_for_probability inverts the curve", rating_for_probability_inverts_the_curve)
check("a harder problem is never more likely", harder_problems_are_less_likely)


# ----------------------------------------------------------------- the fit

def the_fit_recovers_a_known_curve():
    """Expected counts from a known curve in; the same curve out.

    Expected counts rather than random draws, so the right answer is exact
    and the check cannot flake. With k = n * p exactly, the maximum-likelihood
    estimate is the generating curve itself.
    """
    a_true, b_true = 0.31, 0.147
    counts = {}
    for gap in range(-1200, 1201, 25):
        n = 1000
        counts[gap] = [n, n * model.sigmoid(a_true + b_true * gap / model.SCALE)]
    a, b, loss = model.fit_logistic(counts)
    assert abs(a - a_true) < 1e-6, (a, a_true)
    assert abs(b - b_true) < 1e-6, (b, b_true)
    assert 0 < loss < math.log(2), loss


def a_flat_curve_fits_as_flat():
    """No relationship in the data -> slope zero, not something invented."""
    counts = {gap: [500, 350] for gap in range(-800, 801, 100)}
    a, b, _ = model.fit_logistic(counts)
    assert abs(b) < 1e-9, b
    assert abs(model.sigmoid(a) - 0.7) < 1e-9, model.sigmoid(a)


def log_loss_matches_the_formula():
    counts = {0: [4, 1], 100: [2, 2]}
    a, b, loss = model.fit_logistic(counts)
    by_hand = 0.0
    for gap, (n, k) in counts.items():
        p = model.sigmoid(a + b * gap / model.SCALE)
        by_hand -= k * math.log(p) + (n - k) * math.log(1 - p)
    assert abs(loss - by_hand / 6) < 1e-12, (loss, by_hand / 6)


check("the fit recovers a curve it was given", the_fit_recovers_a_known_curve)
check("a flat curve fits as flat", a_flat_curve_fits_as_flat)
check("log loss is the average of the formula", log_loss_matches_the_formula)


# -------------------------------------------------------- recommend()

def row(pid, contest, rating):
    return {"id": pid, "contest_id": contest, "problem_index": "A",
            "name": pid, "rating": rating}


def picks_the_rating_nearest_the_target():
    pool = [row(f"{c}A", c, r) for c, r in
            ((10, 800), (11, 1200), (12, 1500), (13, 1900), (14, 2400))]
    best = model.recommend(pool, 1500, 0.5, count=1, baseline=FAKE)[0]
    want = model.rating_for_probability(1500, 0.5, FAKE)
    nearest = min((r["rating"] for r in pool), key=lambda r: abs(r - want))
    assert best["rating"] == nearest, (best, want)


def ties_go_to_the_newest_contest():
    pool = [row("100A", 100, 1500), row("900A", 900, 1500), row("500A", 500, 1500)]
    got = [p["id"] for p in model.recommend(pool, 1500, 0.5, count=3, baseline=FAKE)]
    assert got == ["900A", "500A", "100A"], got


def returns_at_most_count():
    pool = [row(f"{c}A", c, 1500) for c in range(1, 20)]
    assert len(model.recommend(pool, 1500, 0.5, count=5, baseline=FAKE)) == 5
    assert model.recommend([], 1500, 0.5, baseline=FAKE) == []


check("picks the rating nearest the target", picks_the_rating_nearest_the_target)
check("ties go to the newest contest", ties_go_to_the_newest_contest)
check("returns at most `count`, and [] from an empty pool", returns_at_most_count)


# --------------------------------------------------- recommendation_pool()

def api_problem(contest, index, name, rating, tags=()):
    return {"contestId": contest, "index": index, "name": name,
            "rating": rating, "tags": list(tags)}


def submission(sid, prob, verdict="OK"):
    return {"id": sid, "verdict": verdict, "creationTimeSeconds": 1700000000 + sid,
            "author": {"participantType": "PRACTICE"}, "problem": prob}


def pool_ids(conn, handle):
    return {r["id"] for r in db.recommendation_pool(conn, handle)}


def fresh_conn():
    path = SCRATCH / f"pool-{fresh_conn.n}.db"
    fresh_conn.n += 1
    db.init_db(path)
    return db.connect(path)


fresh_conn.n = 0


def the_pool_leaves_out_what_was_solved_under_either_id():
    """Solving the Div. 2 copy removes the listed Div. 1 copy -- ADR 0010."""
    conn = fresh_conn()
    db.save_problemset(conn, [
        api_problem(1292, "A", "NEKO", 1400), api_problem(1500, "B", "Other", 1400)])
    db.save_sync(conn, "u", 1500, [submission(1, api_problem(1293, "C", "NEKO", 1400))])
    db.rebuild_aliases(conn)
    assert pool_ids(conn, "u") == {"1500B"}, pool_ids(conn, "u")


def a_failed_problem_stays_in_the_pool():
    conn = fresh_conn()
    db.save_problemset(conn, [api_problem(1500, "B", "Hard", 1400)])
    db.save_sync(conn, "u", 1500, [
        submission(1, api_problem(1500, "B", "Hard", 1400), "WRONG_ANSWER")])
    assert pool_ids(conn, "u") == {"1500B"}


def unrated_and_unlisted_problems_are_not_in_the_pool():
    conn = fresh_conn()
    db.save_problemset(conn, [
        api_problem(1500, "A", "Rated", 1400), api_problem(1500, "B", "Unrated", None)])
    db.save_sync(conn, "u", 1500, [
        submission(1, api_problem(9999, "A", "Only seen in a history", 1400), "WRONG_ANSWER")])
    assert pool_ids(conn, "u") == {"1500A"}, pool_ids(conn, "u")


def the_pool_is_none_for_a_half_synced_user():
    conn = fresh_conn()
    db.save_problemset(conn, [api_problem(1500, "A", "P", 1400)])
    conn.execute("INSERT INTO users (handle, first_seen) VALUES ('u', '2026-01-01T00:00:00Z')")
    conn.commit()
    assert db.recommendation_pool(conn, "u") is None


check("the pool leaves out what was solved, under either id", the_pool_leaves_out_what_was_solved_under_either_id)
check("a failed problem stays in the pool", a_failed_problem_stays_in_the_pool)
check("unrated and unlisted problems are not in the pool", unrated_and_unlisted_problems_are_not_in_the_pool)
check("the pool is None for a half-synced user (ADR 0004)", the_pool_is_none_for_a_half_synced_user)


# ------------------------------------------------------------- the page

def seed_page(handle, rating):
    conn = db.connect()
    try:
        db.save_sync(conn, handle, rating, [
            submission(1, api_problem(1000, "A", "Warm-up", 800, ["math"]))])
    finally:
        conn.close()


seed_page("rated", 1500)
seed_page("unrated", None)
client = web.app.test_client()


def an_unrated_user_starts_from_the_chosen_rating_or_is_told_why():
    """ADR 0016. With the topic model, somebody with no rating gets five
    problems, and the page says which starting rating they were worked out
    from. Without the model file the rating-only fallback has nothing to go
    on, and the page says that instead of showing numbers."""
    html = client.get("/results/unrated").get_data(as_text=True)
    assert html.count('class="num chance"') == 5, f"{html.count('class=\"num chance\"')} rows for an unrated user"
    assert "no rating yet" in html and str(model.UNRATED_START) in html, \
        "the page does not say where an unrated user's chances start from"
    real = model.current_topic_model
    try:
        model.current_topic_model = lambda path=None: None
        html = client.get("/results/unrated").get_data(as_text=True)
        assert "no rating for unrated" in html, "without a model, the unrated sentence is missing"
        assert 'class="num chance"' not in html, "a probability was shown with no rating and no model"
    finally:
        model.current_topic_model = real


def before_the_problemset_arrives_the_page_says_so():
    html = client.get("/results/rated").get_data(as_text=True)
    assert "still loading" in html, "the not-ready sentence is missing"


def with_a_problemset_there_are_five():
    conn = db.connect()
    try:
        db.save_problemset(conn, [api_problem(2000 + i, "A", f"P{i}", 1000 + 100 * (i % 10))
                                  for i in range(40)])
    finally:
        conn.close()
    html = client.get("/results/rated").get_data(as_text=True)
    assert html.count('class="num chance"') == 5, html.count('class="num chance"')
    assert "problemset/problem/" in html
    assert "Warm-up" not in html.split("<h2>Topics</h2>")[0], "a solved problem was recommended"
    assert ".0," not in html and ".0 " not in html.split("<h2>Topics</h2>")[0], \
        "a float leaked into the sentence (the 2800.0 bug)"


check("before the problemset arrives, the page says so", before_the_problemset_arrives_the_page_says_so)
check("with a problemset: five rows, links, nothing already solved", with_a_problemset_there_are_five)
check("an unrated user is served from the chosen start, or told why when there is no model",
      an_unrated_user_starts_from_the_chosen_rating_or_is_told_why)


def the_chance_is_the_only_new_accent():
    """ADR 0006. The accent now appears on exactly two things: an OK verdict,
    and the probability on a recommendation. Anything else reaching for it is
    a new meaning, and the colour only works while it has one."""
    import re
    css = Path("static/style.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    users = sorted({
        selector.strip()
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
        # (?<![\w-]) so that "border-color:" and "border-bottom-color:" do
        # not count. A focused input's border in the accent is the form saying
        # "type here", which is its meaning; text drawn in it is the question.
        if re.search(r"(?<![\w-])color:\s*var\(--accent\)", body)
    })
    allowed = {".verdict-ok", ".chance", "a:hover", ".eyebrow", ".hero h1 .accent",
               ".brand::before"}
    unexpected = [s for s in users if s not in allowed]
    assert not unexpected, f"new users of the accent colour: {unexpected}"


def importing_web_starts_no_fetch():
    """Every check imports web. None of them may reach Codeforces."""
    names = [t.name for t in threading.enumerate()]
    assert "problemset" not in names, names


check("the chance is the only new use of the accent", the_chance_is_the_only_new_accent)
check("importing web starts no problemset fetch", importing_web_starts_no_fetch)


# --------------------------------------------------------- baseline.json

def baseline_json_is_what_the_data_says():
    if not os.environ.get("NEXTCF_TESTS_DATASET"):
        print("        (dataset tier not asked for -- skipped)")
        return
    if not Path("dataset.db").exists():
        print("        (dataset.db absent -- skipped)")
        return
    stored = json.loads(Path("baseline.json").read_text(encoding="utf-8"))
    conn = db.connect(Path("dataset.db"))
    try:
        fresh, _ = model.fit_baseline(conn, stored["event"])
    finally:
        conn.close()
    for key in ("intercept", "slope", "attempts", "log_loss"):
        assert fresh[key] == stored[key], \
            f"{key}: baseline.json says {stored[key]}, the data says {fresh[key]} -- refit"
    print(f"        ({stored['event']}: a={stored['intercept']}, b={stored['slope']}, "
          f"{stored['attempts']:,} attempts, still current)")


check("baseline.json is what dataset.db says today", baseline_json_is_what_the_data_says)

shutil.rmtree(SCRATCH, ignore_errors=True)
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
