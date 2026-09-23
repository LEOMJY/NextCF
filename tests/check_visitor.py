"""Check that the website feeds the model what the evaluation fed it.

The evaluation scores the model on inputs built by evaluate.load, for
everybody at once. The website builds them one visitor at a time, with
model.visitor_attempts. If the two ever differ -- a rating taken at the wrong
moment, an experience count off by one, a position read differently -- the
website runs a model nobody evaluated, section 9's number describes something
else, and no error says so.

So: the same real users from dataset.db, both ways, compared field by field.
Then the website's recommender itself, on a small database.

Skips the dataset half unless the dataset tier is asked for -- see
tests/run.py.
"""

import math
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="visitor-"))
os.environ["NEXTCF_DB"] = str(SCRATCH / "test.db")
# Paths in this file are relative to the repository root, and the modules
# being checked live there, so go there first. The check then runs the same
# from any directory.
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
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


print("the website's inputs, and its recommender")


# ------------------------------------------------------ the same inputs

def the_website_builds_what_the_evaluation_built():
    path = Path("dataset.db")
    if not os.environ.get("NEXTCF_TESTS_DATASET"):
        print("        (dataset tier not asked for -- skipped)")
        return
    if not path.exists():
        print("        (dataset.db absent -- skipped)")
        return
    conn = db.connect(path)
    try:
        everyone = evaluate.load(conn)
        rng = random.Random(1)
        handles = rng.sample(everyone.handles, 25)
        tags_of = model.tags_by_problem(conn)
        for handle in handles:
            u = everyone.handles.index(handle)
            bulk = [i for i in range(len(everyone)) if everyone.u[i] == u]
            one, history, _, _, _ = model.visitor_attempts(conn, handle, tags_of=tags_of)
            assert len(history) == len(bulk), f"{handle}: {len(history)} vs {len(bulk)} attempts"
            for i, j in zip(bulk, history):
                a = (everyone.problems[everyone.p[i]], everyone.c[i], everyone.y[i],
                     everyone.t[i], everyone.month[i],
                     sorted(everyone.tag_names[k] for k in everyone.problem_tags[everyone.p[i]]),
                     everyone.problem_position[everyone.p[i]])
                b = (one.problems[one.p[j]], one.c[j], one.y[j], one.t[j], one.month[j],
                     sorted(one.tag_names[k] for k in one.problem_tags[one.p[j]]),
                     one.problem_position[one.p[j]])
                assert a == b, f"{handle}: {a} vs {b}"
                for field in ("g", "r", "n", "g_shown"):
                    x, y = getattr(everyone, field)[i], getattr(one, field)[j]
                    assert abs(x - y) < 1e-12, f"{handle}: {field} {x} vs {y}"
                for col, name in enumerate(model.HISTORY_COLUMNS):
                    x, y = everyone.h[col][i], one.h[col][j]
                    assert abs(x - y) < 1e-12, f"{handle}: history {name} {x} vs {y}"
        print(f"        ({len(handles)} users, every field of every attempt identical, "
              f"including all {len(model.HISTORY_COLUMNS)} history columns)")
    finally:
        conn.close()


def history_sees_only_the_strict_past():
    """Hand-worked: HistoryState must count only attempts strictly before the
    moment asked about -- same-second attempts do not see each other, a window
    of w reaches back exactly w, and the running share folds an attempt in
    only once a later second arrives."""
    H = model.HistoryState
    st = H()
    t0 = 1_000_000.0
    st.add(t0, 1, ("dp",))
    st.add(t0, 0, ("dp", "math"))               # same second as the first
    same = st.features(t0, ("dp",))             # asked AT t0: sees nothing
    col = {name: v for name, v in zip(model.HISTORY_COLUMNS, same)}
    assert col["all_tries_1h"] == 0 and col["all_wins_ever"] == 0, col
    assert col["last_was_ok"] == 0.5 and col["all_share_recent"] == 0.5, col

    later = dict(zip(model.HISTORY_COLUMNS, st.features(t0 + 60, ("dp",))))
    assert later["all_tries_1h"] == math.log1p(2), later
    assert later["all_wins_1h"] == math.log1p(1), later
    assert later["topic_tries_1h"] == math.log1p(2), later          # both carry dp
    # share: two attempts folded in, newest weighted 1, older 0.8, ghosts 1/1
    assert abs(later["all_share_recent"] - (0.8 * 1 + 0 + 1) / (0.8 + 1 + 2)) < 1e-12, later
    assert later["last_was_ok"] == 0.0, later                       # the later-added one
    assert abs(later["log_hours_since_last"] - math.log1p(60 / 3600)) < 1e-12, later

    edge = dict(zip(model.HISTORY_COLUMNS, st.features(t0 + 3600, ("math",))))
    assert edge["all_tries_1h"] == math.log1p(2), edge                # exactly 1h back: in
    assert edge["topic_tries_1h"] == math.log1p(1), edge              # only one carried math
    gone = dict(zip(model.HISTORY_COLUMNS, st.features(t0 + 3601, ("math",))))
    assert gone["all_tries_1h"] == 0 and gone["all_tries_1d"] == math.log1p(2), gone
    unseen = dict(zip(model.HISTORY_COLUMNS, st.features(t0 + 3601, ("graphs",))))
    assert unseen["topic_tries_ever"] == 0 and unseen["topic_share_recent"] == 0.5, unseen


check("the website builds exactly what the evaluation built", the_website_builds_what_the_evaluation_built)
check("history counts only the strict past, windows exact to the second", history_sees_only_the_strict_past)


# ------------------------------------------------------ the recommender

def api_problem(contest, index, name, rating, tags):
    return {"contestId": contest, "index": index, "name": name, "rating": rating, "tags": tags}


def submission(sid, prob, verdict, when):
    return {"id": sid, "verdict": verdict, "creationTimeSeconds": when,
            "author": {"participantType": "PRACTICE"}, "problem": prob}


def build_world():
    """A problemset of 300 problems, and one synced user with a history and a
    rating history, in a fresh database."""
    db.init_db()
    conn = db.connect()
    rng = random.Random(3)
    tags = ["dp", "greedy", "math", "graphs", "strings"]
    problems = [api_problem(1000 + i, "ABCDE"[i % 5], f"P{i}", 800 + 100 * (i % 20),
                            rng.sample(tags, rng.randint(1, 2))) for i in range(300)]
    db.save_problemset(conn, problems)
    start = 1_600_000_000
    history = [submission(n + 1, problems[rng.randrange(300)],
                          "OK" if rng.random() < 0.6 else "WRONG_ANSWER", start + n * 86400)
               for n in range(120)]
    changes = [{"contestId": 5000 + k, "rank": 1, "oldRating": 1200 + 20 * k,
                "newRating": 1220 + 20 * k, "ratingUpdateTimeSeconds": start - 86400 + k * 20 * 86400}
               for k in range(8)]
    db.save_sync(conn, "visitor", 1360, history, rating_changes=changes)
    return conn, problems


def a_fitted_model(conn, extras=("shape",)):
    """Fit a small topic model on this database's own attempts, and export it
    the way topic_model.json is written."""
    data, idx, _, _, _ = model.visitor_attempts(conn, "visitor")
    m = model.TopicModel(model.GROUPS, {"tag": 3.0, "problem": 3.0, "user": 10.0,
                                        "user_topic": 10.0}, extras=extras)
    m.fit(data, idx)
    return model.export_fitted(m, data, 180)


def the_fast_scorer_matches_predict_exactly():
    """PracticeScorer is a second copy of the model's arithmetic, kept only
    because the host has a tenth of a CPU. This is the condition of keeping
    it: for every problem in the pool, with every extra column switched on
    and both guard rails in play, it must give what TopicModel.predict --
    the code the evaluation scored -- gives."""
    conn = db.connect()
    try:
        model._scorer_cache.clear()
        fitted = a_fitted_model(conn, extras=model.EXTRAS)
        fitted["level_range"] = [-3.0, -2.0]          # 1360 is -1.4: outside, clamped
        now = 1_650_000_000.0
        fitted["trend_until"] = now - 30 * 86400      # the time line has stopped
        pool = db.recommendation_pool(conn, "visitor")

        # the reference: every pool problem as a pseudo-attempt through predict()
        data, history, pidx, tidx, tags_of = model.visitor_attempts(conn, "visitor")
        first = len(data)
        for row in pool:
            data.u.append(0)
            data.p.append(model._register(data, pidx, tidx, tags_of, row["id"], row["problem_index"]))
            data.c.append(0); data.g.append((1360 - row["rating"]) / model.SCALE)
            data.y.append(0); data.t.append(now); data.r.append((1360 - 1500) / model.SCALE)
            data.n.append(math.log1p(len(history))); data.s.append(None); data.month.append("")
        # History columns for the pseudo-attempts, asked of the user's state at
        # `now` WITHOUT adding them to it -- they are hypothetical, and must not
        # see each other. (compute_history would add each one after asking.)
        state = model.HistoryState()
        for i in history:
            state.add(data.t[i], data.y[i], model._tags(data, data.p[i]))
        for i in range(first, len(data)):
            for col, v in enumerate(state.features(now, model._tags(data, data.p[i]))):
                data.h[col].append(v)
        m = model.fitted_model(fitted, pidx, tidx)
        weights = [0.5 ** ((now - data.t[i]) / (180 * 86400.0)) for i in history]
        user = m.fold_in(data, history, weights)
        reference = {row["id"]: m.predict(data, i, user) for i, row in zip(range(first, len(data)), pool)}

        scorer = model.practice_scorer(conn, fitted)
        b, s, n, history_by_name = model.fold_in_visitor(conn, "visitor", fitted, now, scorer.tags_of)
        fast = scorer.scores(1360, math.log1p(n), now, b, s, history_by_name)
        worst = max(abs(fast[pid] - p) for pid, p in reference.items())
        assert worst < 1e-12, f"the fast path differs from predict() by up to {worst:.2e}"
        assert len(reference) == len(pool) > 100
    finally:
        conn.close()
        model._scorer_cache.clear()


def the_recommender_returns_unsolved_problems_near_the_target():
    """The contract since 2026-09-18 (model.choose): five unsolved problems,
    all within BAND of the target when that many exist, spread across topics
    -- each pick shares as few topics with the earlier picks as any other
    candidate in the band could have."""
    conn, _ = build_world()
    try:
        fitted = a_fitted_model(conn)
        pool = db.recommendation_pool(conn, "visitor")
        solved = {r[0] for r in conn.execute(
            "SELECT DISTINCT problem_id FROM submissions WHERE handle='visitor' AND verdict='OK'")}
        picks = model.topic_recommend(conn, "visitor", 1360, pool, 0.5, count=5,
                                      now=1_620_000_000, fitted=fitted)
        assert len(picks) == 5, len(picks)
        assert not ({p["id"] for p in picks} & solved), "a solved problem was recommended"
        assert all(0 < p["probability"] < 1 for p in picks)
        everything = model.topic_recommend(conn, "visitor", 1360, pool, 0.5, count=len(pool),
                                           now=1_620_000_000, fitted=fitted)
        in_band = [p for p in everything if abs(p["probability"] - 0.5) <= model.BAND]
        if len(in_band) >= 5:
            assert all(abs(p["probability"] - 0.5) <= model.BAND for p in picks),                 "a pick outside the band although five were inside it"
        tags = model.tags_by_problem(conn)
        covered = set()
        chosen = {p["id"] for p in picks}
        for p in picks:
            mine = len(set(tags.get(p["id"], ())) & covered)
            better = [q for q in in_band if q["id"] not in chosen
                      and len(set(tags.get(q["id"], ())) & covered) < mine]
            assert not better, f"{p['id']} repeats {mine} topics where another in the band repeats fewer"
            covered |= set(tags.get(p["id"], ()))
    finally:
        conn.close()


def the_recommender_is_deterministic():
    conn = db.connect()
    try:
        fitted = a_fitted_model(conn)
        pool = db.recommendation_pool(conn, "visitor")
        a = model.topic_recommend(conn, "visitor", 1360, pool, 0.5, now=1_620_000_000, fitted=fitted)
        b = model.topic_recommend(conn, "visitor", 1360, pool, 0.5, now=1_620_000_000, fitted=fitted)
        assert a == b
    finally:
        conn.close()


def no_model_file_means_none_not_a_guess():
    conn = db.connect()
    try:
        pool = db.recommendation_pool(conn, "visitor")
        assert model.topic_recommend(conn, "visitor", 1360, pool, 0.5,
                                     fitted=None) is None or model.current_topic_model() is not None
    finally:
        conn.close()


def the_page_says_which_model_chose():
    """With a topic model present the page must use it and SAY so; without
    one it falls back to the baseline and says that instead. The two are
    different claims -- one about a person, one about everybody at a rating
    -- and a page that silently switched between them would be lying half
    the time."""
    import sync
    import web
    sync.start_sync = lambda handle: 1      # never reach Codeforces from a check
    conn = db.connect()
    try:
        fitted = a_fitted_model(conn)
    finally:
        conn.close()
    client = web.app.test_client()
    real = model.current_topic_model
    try:
        model.current_topic_model = lambda path=None: fitted
        html = client.get("/results/visitor").get_data(as_text=True)
        assert "Chosen for you" in html, "the topic model's sentence is missing"
        assert "Rating only" not in html, "the baseline's sentence appeared with a model present"
        assert html.count('class="num chance"') == 5, html.count('class="num chance"')
        model.current_topic_model = lambda path=None: None
        html = client.get("/results/visitor").get_data(as_text=True)
        assert "Rating only" in html, "no model, and the page did not say it fell back"
        assert "Chosen for you" not in html
    finally:
        model.current_topic_model = real


def the_guard_rails_hold():
    """A shipped model must not extrapolate its straight lines without end:
    a level beyond the fitted range predicts exactly as the edge does, and a
    moment beyond trend_until exactly as trend_until does."""
    data = model.Attempts()
    data.problem_tags = [(0,)]
    data.problem_position = [2]
    for level, when in ((50.0, 1_700_000_000.0), (8.7, 1_700_000_000.0),
                        (1.0, 1_900_000_000.0), (1.0, 1_750_000_000.0)):
        data.u.append(0); data.p.append(0); data.c.append(0); data.g.append(1.0)
        data.y.append(0); data.t.append(when); data.r.append(level); data.n.append(2.0)
    model.compute_history(data)
    m = model.TopicModel(("tag",), extras=model.EXTRAS)
    m.w = [0.1 * (a + 1) for a in range(len(m.w))]
    m.level_range = (-11.5, 8.7)
    m.trend_until = 1_750_000_000.0
    assert m.predict(data, 0) == m.predict(data, 1), "a level past the edge moved the prediction"
    assert m.predict(data, 2) == m.predict(data, 3), "the trend kept walking past trend_until"
    fitted = {"level_range": [-11.5, 8.7]}
    assert model.outside_range(fitted, 3528) and not model.outside_range(fitted, 1500)


def an_out_of_range_rating_is_told_so():
    import sync
    import web
    sync.start_sync = lambda handle: 1
    conn = db.connect()
    try:
        fitted = a_fitted_model(conn)
        fitted["level_range"] = [-11.5, 8.7]
        conn.execute("UPDATE users SET cf_rating = 3528 WHERE handle = 'visitor'")
        conn.commit()
    finally:
        conn.close()
    real = model.current_topic_model
    try:
        model.current_topic_model = lambda path=None: fitted
        html = web.app.test_client().get("/results/visitor").get_data(as_text=True)
        assert "extrapolation" in html, "a 3528-rated visitor was not told the numbers are extrapolated"
    finally:
        model.current_topic_model = real
        conn = db.connect()
        conn.execute("UPDATE users SET cf_rating = 1360 WHERE handle = 'visitor'")
        conn.commit()
        conn.close()


def a_new_account_is_told_which_rating_was_used():
    """Codeforces shows a new account less than it computes with, for six
    rated contests (model.HIDDEN_AFTER). The model uses the computed rating,
    so the page must say which number the chances are for -- and must not say
    it for anybody with nothing hidden."""
    import sync
    import web
    sync.start_sync = lambda handle: 1
    conn = db.connect()
    try:
        fitted = a_fitted_model(conn)
        start = 1_650_000_000                      # 2022: the new rule applies
        changes = [{"contestId": 7000 + k, "rank": 1, "oldRating": old, "newRating": new,
                    "ratingUpdateTimeSeconds": start + k * 86400}
                   for k, (old, new) in enumerate([(0, 450), (450, 700)])]
        db.save_sync(conn, "newcomer", 700, [], rating_changes=changes)
        assert model.rating_now(conn, "newcomer", 700) == 1250, model.rating_now(conn, "newcomer", 700)
        assert model.rating_now(conn, "visitor", 1360) == 1360, "eight contests in, nothing is hidden"
        shown = [(f"2022-01-0{k}T00:00:00Z", r) for k, r in enumerate((400, 700, 900, 1000, 1100, 1150, 1200), 1)]
        got = [r for _, r in model.computed_ratings(shown)]
        assert got == [1300, 1250, 1200, 1150, 1150, 1150, 1200], got
        old_rule = [("2019-06-11T00:00:00Z", 1399), ("2019-07-17T00:00:00Z", 1340)]
        assert [r for _, r in model.computed_ratings(old_rule)] == [1399, 1340], "an old account was adjusted"
        assert model.computed_ratings([(model.NEW_RULE_FROM, 500)])[0][1] == 1400, "the rule's first day"
    finally:
        conn.close()
    real = model.current_topic_model
    try:
        model.current_topic_model = lambda path=None: fitted
        client = web.app.test_client()
        html = client.get("/results/newcomer").get_data(as_text=True)
        assert "computes with\n              1250" in html or "computes with 1250" in " ".join(html.split()), \
            "a new account was not told which rating the chances use"
        html = client.get("/results/visitor").get_data(as_text=True)
        assert "computes with" not in html, "the note appeared for an account with nothing hidden"
    finally:
        model.current_topic_model = real


def a_never_rated_visitor_is_served_from_the_chosen_start():
    """ADR 0016. With no rating changes at all, every attempt is taken at
    model.UNRATED_START -- not dropped, which is what the harness does to
    attempts made before a first rated contest -- today's rating is it, and
    the fold-in has their whole history to work from."""
    conn = db.connect()
    try:
        # The visitor's own history, re-saved under a handle with no rating
        # changes: same problems, same outcomes, nothing rated.
        rows = conn.execute(
            "SELECT id, problem_id, verdict, participant_type, submitted_at FROM submissions "
            "WHERE handle = 'visitor'").fetchall()
        subs = []
        for sid, pid, verdict, ptype, at in rows:
            contest, index = conn.execute(
                "SELECT contest_id, problem_index FROM problems WHERE id = ?", (pid,)).fetchone()
            prob = conn.execute("SELECT name, rating FROM problems WHERE id = ?", (pid,)).fetchone()
            tags = [t for (t,) in conn.execute("SELECT tag FROM problem_tags WHERE problem_id = ?", (pid,))]
            subs.append({"id": 10_000_000 + sid, "verdict": verdict,
                         "creationTimeSeconds": int(model._stamp(at)),
                         "author": {"participantType": ptype},
                         "problem": {"contestId": contest, "index": index, "name": prob[0],
                                     "rating": prob[1], "tags": tags}})
        db.save_sync(conn, "never_rated", None, subs, rating_changes=[])
        assert model.rating_now(conn, "never_rated", None) == model.UNRATED_START
        data, history, _, _, _ = model.visitor_attempts(conn, "never_rated")
        rated, rated_history, _, _, _ = model.visitor_attempts(conn, "visitor")
        assert len(history) >= len(rated_history), \
            f"{len(history)} attempts kept for a never-rated visitor, {len(rated_history)} for the rated one"
        assert history, "a never-rated visitor's history was dropped"
        levels = {round(data.r[i] * model.SCALE + 1500) for i in history}
        assert levels == {model.UNRATED_START}, f"attempts taken at ratings {sorted(levels)}"
    finally:
        conn.close()


check("the recommender: unsolved, inside the band, spread across topics",
      the_recommender_returns_unsolved_problems_near_the_target)
check("the fast scorer gives exactly what predict() gives, every problem",
      the_fast_scorer_matches_predict_exactly)
check("the recommender is deterministic", the_recommender_is_deterministic)
check("with no model file, it returns None rather than guessing", no_model_file_means_none_not_a_guess)
check("the page says which model chose, and switches when the file is absent",
      the_page_says_which_model_chose)
check("the guard rails hold: level clamped, trend stopped", the_guard_rails_hold)
check("a rating outside the model's range is told so on the page", an_out_of_range_rating_is_told_so)
check("a new account's hidden rating is added back, and the page says which rating was used",
      a_new_account_is_told_which_rating_was_used)
check("a never-rated visitor's every attempt is taken at the chosen start, and so is today's rating",
      a_never_rated_visitor_is_served_from_the_chosen_start)

shutil.rmtree(SCRATCH, ignore_errors=True)
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
