"""Check practice plans -- ADR 0026.

No network: a small database built here, and a fake problemset, as in
check_difficulty.py.

What the plan promises, and what these hold it to:

  * THE FIVE STAY. The first view of a list keeps its five as the list's
    plan, and every view after -- a reload, a sync, a press -- shows the same
    five until the visitor asks for the next.
  * EACH IS SETTLED ONCE, AND SAYS HOW. A solve after the plan began ticks
    it, read from the history rather than stored; a press marks it, in every
    plan that holds it; "put back" is the undo, in the plans still running.
  * A PLAN ENDS ONLY BY ASKING, and only the plan the button was drawn for:
    a double-click cannot end the next one too.
"""

import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="plans-"))

# Must be set before db is imported: db.py reads it at import time.
os.environ["NEXTCF_DB"] = str(SCRATCH / "test.db")
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


# ------------------------------------------------------------------ no network
def fake_start_sync(handle):
    conn = db.connect()
    try:
        active = db.get_active_job(conn, "sync", handle)
        if active is not None:
            return active["id"]
        return db.create_job(conn, "sync", handle)
    finally:
        conn.close()


sync.start_sync = fake_start_sync
db.init_db()
client = web.app.test_client()

HANDLE = "planner"

# The one solve every visitor starts with, long before any plan.
WARM_UP = {"id": 1, "creationTimeSeconds": 1600000000, "verdict": "OK",
           "author": {"participantType": "PRACTICE"},
           "problem": {"contestId": 999, "index": "A", "name": "Solved",
                       "tags": ["math"], "rating": 900}}


def a_problemset(count=60):
    """Every problem tagged math, every third dp too: "math" is then a topic
    whose pool is the whole pool, and "dp" a smaller one."""
    conn = db.connect()
    try:
        db.save_problemset(conn, [
            {"contestId": 1000 + n, "index": "A", "name": f"Problem {n}",
             "rating": 800 + (n % 20) * 100,
             "tags": ["math", "dp"] if n % 3 == 0 else ["math"]}
            for n in range(count)])
    finally:
        conn.close()


def a_visitor(rating=1500):
    """A fresh visitor: one old solve, nothing hidden, the default target, and
    no plans. Every check starts here."""
    conn = db.connect()
    try:
        with conn:
            conn.execute("DELETE FROM submissions WHERE handle = ?", (HANDLE,))
        db.save_sync(conn, HANDLE, rating, [WARM_UP])
        with conn:
            conn.execute("DELETE FROM dismissals WHERE handle = ?", (HANDLE,))
            conn.execute("DELETE FROM topic_targets WHERE handle = ?", (HANDLE,))
            conn.execute("DELETE FROM plans WHERE handle = ?", (HANDLE,))
            conn.execute("UPDATE users SET target_prob = 0.70, target_chosen_at = NULL, "
                         "target_step = NULL, target_direction = NULL WHERE handle = ?", (HANDLE,))
    finally:
        conn.close()


def page(topic=None):
    query = f"?topic={topic}" if topic else ""
    return client.get(f"/results/{HANDLE}{query}").get_data(as_text=True)


def flat(html):
    """The page's words with the tags out and the whitespace collapsed: the
    template wraps sentences at the measure."""
    import re
    return " ".join(re.sub(r"(?s)<[^>]+>", " ", html).split())


def the_plan(topic=None):
    """(plan, rows) for a list's active plan -- viewing the page first, since
    that is what makes one -- or None."""
    page(topic)
    conn = db.connect()
    try:
        return db.active_plan(conn, HANDLE, topic or "")
    finally:
        conn.close()


def ids(topic=None):
    found = the_plan(topic)
    return [row["id"] for row in found[1]] if found else []


def press(problem_id, verdict, topic=None):
    data = {"problem": problem_id, "verdict": verdict}
    if topic:
        data["topic"] = topic
    return client.post(f"/results/{HANDLE}/feedback", data=data)


def end(topic=None, plan_id=None):
    """Press "swap the five" / "next five" for this list's plan (or for a
    named plan, as a stale page would)."""
    if plan_id is None:
        plan_id = the_plan(topic)[0]["id"]
    data = {"plan": str(plan_id)}
    if topic:
        data["topic"] = topic
    return client.post(f"/results/{HANDLE}/plan", data=data)


def a_solve(problem_id, seconds_from_now=60):
    """A sync that finds `problem_id` accepted, `seconds_from_now` after now
    -- after any plan made so far, if positive."""
    contest, index = problem_id[:-1], problem_id[-1]
    conn = db.connect()
    try:
        db.save_sync(conn, HANDLE, 1500, [WARM_UP, {
            "id": 2 + abs(hash(problem_id)) % 100000,
            "creationTimeSeconds": int(time.time()) + seconds_from_now, "verdict": "OK",
            "author": {"participantType": "PRACTICE"},
            "problem": {"contestId": int(contest), "index": index, "name": "x",
                        "tags": ["math"], "rating": 1500}}])
    finally:
        conn.close()


def active_plans():
    conn = db.connect()
    try:
        return conn.execute("SELECT * FROM plans WHERE handle = ? AND state = 'active'",
                            (HANDLE,)).fetchall()
    finally:
        conn.close()


def outcome(plan_id, problem_id):
    conn = db.connect()
    try:
        return conn.execute("SELECT outcome FROM plan_problems WHERE plan_id = ? AND problem_id = ?",
                            (plan_id, problem_id)).fetchone()[0]
    finally:
        conn.close()


def history():
    conn = db.connect()
    try:
        return db.plan_history(conn, HANDLE)
    finally:
        conn.close()


a_problemset()


# ----------------------------------------------------------- the five stay
def the_first_view_makes_a_plan_of_five():
    a_visitor()
    assert not active_plans(), "a plan before anything was shown"
    five = ids()
    assert len(five) == 5, five
    html = page()
    assert "plan started just now" in flat(html), "the page does not say it is a plan"
    assert "0 of 5 done, 0 solved" in flat(html), "no progress line"


def a_reload_shows_the_same_five():
    a_visitor()
    first = ids()
    for _ in range(3):
        assert ids() == first, "a reload changed the plan"
    assert len(active_plans()) == 1, "a reload made a second plan"


def the_json_route_serves_the_same_plan():
    """The topic chart swaps lists through /recommendations (ADR 0025); it
    must be the same plan the page shows, not a second choice."""
    a_visitor()
    first = ids()
    data = client.get(f"/results/{HANDLE}/recommendations").get_json()
    assert [p["id"] for p in data["recs"]["problems"]] == first, "the data route chose again"
    assert data["recs"]["plan"]["id"] == the_plan()[0]["id"]


def a_change_in_target_waits_for_the_next_plan():
    """The target moved from elsewhere -- a press on another list's plan, say
    -- does not redraw this one."""
    a_visitor()
    first = ids()
    conn = db.connect()
    try:
        with conn:
            conn.execute("UPDATE users SET target_prob = 0.55, target_chosen_at = ? WHERE handle = ?",
                         (db.utc_now(), HANDLE))
    finally:
        conn.close()
    assert ids() == first, "a target change redrew the plan"
    assert "Your next five will aim at 55%" in flat(page()), "the next target went unsaid"


def the_chooser_runs_once_per_plan():
    """ADR 0026: the chooser, the guard rail and the target are applied when
    a plan is made, not on every view. A mutation that chose again on every
    view survived the checks above, because the one-active-plan index
    refused each new plan and handed back the old one."""
    a_visitor()
    real = web.choose_plan
    calls = []
    web.choose_plan = lambda *args, **kwargs: calls.append(1) or real(*args, **kwargs)
    try:
        for _ in range(3):
            page()
    finally:
        web.choose_plan = real
    assert len(calls) == 1, f"the chooser ran {len(calls)} times for one plan"


def a_plan_outlives_an_emptied_pool():
    """Every problem pressed away, so the pool has nothing left: the plan is
    still on screen, marked, with its "next five" -- not "nothing left",
    which is the answer only once it has ended."""
    a_visitor()
    first = ids()
    conn = db.connect()
    try:
        every = [row[0] for row in conn.execute("SELECT id FROM problems WHERE in_problemset = 1")]
        for problem_id in every:
            db.record_feedback(conn, HANDLE, problem_id, "too_hard", keep=len(every))
    finally:
        conn.close()
    html = page()
    assert "rec-table" in html, "the plan vanished when the pool emptied"
    assert "Next five" in html, "a settled plan did not offer the next"
    end()
    assert "rec-table" not in page(), "a plan was made from an empty pool"
    assert ids() == [], first


def two_views_at_once_make_one_plan():
    """Two tabs opening one list at the same moment: the unique index lets
    one plan in, and the other request shows it (db.create_plan)."""
    a_visitor()
    start = threading.Barrier(2)

    def one_view():
        start.wait()
        web.app.test_client().get(f"/results/{HANDLE}")

    views = [threading.Thread(target=one_view) for _ in range(2)]
    for t in views:
        t.start()
    for t in views:
        t.join()
    assert len(active_plans()) == 1, f"{len(active_plans())} active plans for one list"


def a_second_insert_returns_the_first_plan():
    """The same race, without threads: the second create_plan is refused by
    the index and hands back the plan already there, five problems and all."""
    a_visitor()
    conn = db.connect()
    try:
        picks = [{"id": f"{1000 + n}A", "probability": 0.5} for n in range(5)]
        other = [{"id": f"{1010 + n}A", "probability": 0.5} for n in range(5)]
        kw = dict(target=0.5, source="topic", rating=1500, shown=1500,
                  looked_up_at=None, unguarded=False)
        first, _ = db.create_plan(conn, HANDLE, "", picks, **kw)
        second, rows = db.create_plan(conn, HANDLE, "", other, **kw)
    finally:
        conn.close()
    assert second["id"] == first["id"], "a second active plan was made"
    assert [r["id"] for r in rows] == [p["id"] for p in picks], "the second insert's problems got in"
    # Asked directly too: without the index the second row goes in and the
    # read above can still happen to return the first.
    assert len(active_plans()) == 1, f"{len(active_plans())} active plans for one list"


def each_list_keeps_its_own_plan():
    a_visitor()
    overall = ids()
    dp = ids("dp")
    assert len(active_plans()) == 2, "the overall list and dp share a plan"
    end("dp")
    assert ids() == overall, "ending dp's plan ended the overall one"
    assert ids("dp") != dp, "dp's plan did not end"


# ------------------------------------------------------------- settled once
def a_solve_after_the_plan_began_is_ticked():
    a_visitor()
    first = ids()
    a_solve(first[1])
    html = page()
    assert ids() == first, "a solve redrew the plan"
    assert "&#10003; solved" in html, "the solve is not ticked"
    assert "1 of 5 done, 1 solved" in flat(html), "the progress line did not count it"
    assert html.count('name="verdict" value="too_hard"') == 4, "a solved row still has its buttons"


def a_solve_before_the_plan_began_is_not_the_plan_s():
    """Solved is read from the history since the plan began, and only then."""
    a_visitor()
    first = ids()
    a_solve(first[0], seconds_from_now=-3600)
    conn = db.connect()
    try:
        plan, _ = db.active_plan(conn, HANDLE, "")
        before = db.solved_since(conn, HANDLE, first, plan["started_at"])
        # And the other edge: a plan that has ended counts nothing after it.
        after = db.solved_since(conn, HANDLE, first, "2000-01-01T00:00:00Z", "2001-01-01T00:00:00Z")
    finally:
        conn.close()
    assert first[0] not in before, "a solve from before the plan was counted in it"
    assert not after, "a solve after the window was counted in it"


def a_solve_under_the_other_id_counts():
    """ADR 0010: the Div. 2 copy of a planned Div. 1 problem is the problem."""
    a_visitor()
    first = ids()
    a_solve("7001A")
    conn = db.connect()
    try:
        with conn:
            conn.execute("INSERT OR REPLACE INTO problem_aliases (alias_id, canonical_id) VALUES ('7001A', ?)",
                         (first[2],))
        html = page()
        with conn:
            conn.execute("DELETE FROM problem_aliases WHERE alias_id = '7001A'")
    finally:
        conn.close()
    assert "1 of 5 done, 1 solved" in flat(html), "a solve under the alias was not ticked"


def a_press_settles_one_without_refilling():
    a_visitor()
    first = ids()
    press(first[0], "too_hard")
    html = page()
    assert ids() == first, "a press refilled the plan"
    assert "marked too hard" in html, "the pressed row is not marked"
    assert html.count('name="verdict" value="too_hard"') == 4, "the pressed row kept its buttons"
    assert "1 of 5 done, 0 solved" in flat(html), flat(html)


def a_press_settles_it_in_every_plan_that_holds_it():
    """The hiding is global (ADR 0021), so the marking is too. Found in the
    build: marked in the list pressed only, the problem stayed "to do" in the
    other plan, with buttons that could no longer do anything -- the same
    answer twice is ignored."""
    a_visitor()
    overall_plan, overall_rows = the_plan()
    math_plan, math_rows = the_plan("math")
    shared = {r["id"] for r in overall_rows} & {r["id"] for r in math_rows}
    assert shared, "the two plans share nothing; this checks nothing"
    problem = sorted(shared)[0]
    press(problem, "too_easy", topic="math")
    assert outcome(math_plan["id"], problem) == "too_easy", "not marked where it was pressed"
    assert outcome(overall_plan["id"], problem) == "too_easy", "not marked in the other plan"


def solved_wins_over_a_press():
    """Called too hard, then solved anyway: it was solved."""
    a_visitor()
    first = ids()
    press(first[0], "too_hard")
    a_solve(first[0])
    html = page()
    assert "&#10003; solved" in html, "the solve lost to the press"
    assert "marked too hard" not in html


def put_back_unsettles_the_running_plans_only():
    """The undo for a press: a settled row has no buttons, so this is the
    only way back. An ended plan is a record and keeps what was said."""
    a_visitor()
    first = ids()
    press(first[0], "too_hard")
    ended = the_plan()[0]["id"]
    end()
    second = ids()
    press(second[0], "too_hard")
    client.post(f"/results/{HANDLE}/restore")
    running = the_plan()[0]["id"]
    assert outcome(running, second[0]) is None, "put back left the running plan's mark"
    assert outcome(ended, first[0]) == "too_hard", "put back rewrote an ended plan"


# --------------------------------------------------------------- ending one
def swapping_ends_it_and_the_next_aims_at_the_new_target():
    a_visitor()
    first = ids()
    press(first[0], "too_hard")                        # target moves to 55%
    response = end()
    assert response.status_code == 302, response.status_code
    assert history()[0]["state"] == "swapped", history()
    second = the_plan()
    assert second[0]["target"] == model.step_target(model.DEFAULT_TARGET, None, None, "easier")[0], \
        f"the next plan aims at {second[0]['target']}"
    assert first[0] not in [r["id"] for r in second[1]], "the pressed problem came back"


def a_finished_plan_offers_the_next_five_and_ends_completed():
    a_visitor()
    first = ids()
    assert "Swap the five" in page() and "Next five" not in page()
    for problem in first:
        press(problem, "too_easy")
    html = page()
    assert "Next five" in html and "All five done" in html, "a finished plan did not offer the next"
    assert "Swap the five" not in html
    end()
    assert history()[0]["state"] == "completed", history()


def a_double_click_ends_one_plan():
    """Two POSTs naming the same plan: the first ends it and the page makes
    the next; the second names a plan already gone and changes nothing."""
    a_visitor()
    stale = the_plan()[0]["id"]
    end(plan_id=stale)
    fresh = the_plan()[0]["id"]
    end(plan_id=stale)
    assert the_plan()[0]["id"] == fresh, "the second click ended the next plan"
    assert len(history()) == 1, f"{len(history())} plans ended by one double-click"


def the_page_s_button_names_its_plan():
    """The checks above POST by hand; this is the form a visitor presses. It
    must carry the plan's id -- the double-click guard -- and, on a topic's
    list, the topic."""
    a_visitor()
    plan_id = the_plan()[0]["id"]
    html = page()
    assert f'action="/results/{HANDLE}/plan"' in html, "no swap form"
    assert f'name="plan" value="{plan_id}"' in html, "the form does not name its plan"
    dp_id = the_plan("dp")[0]["id"]
    html = page("dp")
    assert f'name="plan" value="{dp_id}"' in html, "dp's form names another plan"
    form = html[html.index(f'action="/results/{HANDLE}/plan"'):]
    form = form[:form.index("</form>")]
    assert 'name="topic" value="dp"' in form, "dp's form does not carry its topic"


def a_week_later_they_may_come_back():
    """Swapped problems sit out their list for PLAN_REST_SECONDS, not for
    good: after that, with nothing else changed, the nearest five are the
    first five again."""
    a_visitor()
    first = ids()
    end()
    second = ids()
    assert set(second) != set(first), "the swap gave back the same five"
    end()
    conn = db.connect()
    try:
        with conn:
            conn.execute("UPDATE plans SET ended_at = ? WHERE handle = ? AND state != 'active'",
                         (db.utc_ago(web.PLAN_REST_SECONDS + 86400), HANDLE))
    finally:
        conn.close()
    assert ids() == first, "a week on, the swapped five were still left out"


def the_plan_route_refuses_junk():
    a_visitor()
    plan_id = str(the_plan()[0]["id"])
    assert client.post(f"/results/{HANDLE}/plan", data={"plan": "abc"}).status_code == 400
    assert client.post(f"/results/{HANDLE}/plan", data={}).status_code == 400
    assert client.post(f"/results/{HANDLE}/plan",
                       data={"plan": plan_id, "topic": "nonsense"}).status_code == 400
    assert client.get(f"/results/{HANDLE}/plan").status_code == 405
    assert client.post("/results/!!!/plan", data={"plan": plan_id}).status_code == 404
    # A handle nobody has looked up: nothing to end, and nothing breaks.
    assert client.post("/results/nobody_here/plan", data={"plan": plan_id}).status_code == 302
    assert the_plan()[0]["id"] == int(plan_id), "junk ended a plan"


def a_topic_plan_is_ended_on_its_own_list():
    """The form carries the topic, and the redirect comes back to it."""
    a_visitor()
    ids()
    response = end("dp")
    assert response.headers["Location"].endswith("?topic=dp#next"), response.headers["Location"]
    assert history()[0]["list"] == "dp", history()


# ------------------------------------------ the target moves when a plan ends
def the_user():
    conn = db.connect()
    try:
        return db.get_user(conn, HANDLE)
    finally:
        conn.close()


def a_plans_presses_move_the_target_once_by_their_balance():
    """ADR 0027: three "too easy" and one "too hard" in one plan are one
    step harder, taken when the plan ends -- not three steps, and not before."""
    a_visitor()
    first = ids()
    for problem, verdict in zip(first, ("too_easy", "too_easy", "too_easy", "too_hard")):
        press(problem, verdict)
    assert the_user()["target_chosen_at"] is None, "the target moved before the plan ended"
    end()
    user = the_user()
    assert (user["target_prob"], user["target_step"], user["target_direction"]) == \
        model.step_target(model.DEFAULT_TARGET, None, None, "harder"), dict(user)


def a_plan_nobody_pressed_leaves_the_target():
    """Solves teach the model through the visitor's history; they do not move
    the target (devlog, 2026-09-28: one plan's results cannot tell a right
    model from one 4 points off)."""
    a_visitor()
    first = ids()
    for problem in first:
        a_solve(problem, seconds_from_now=0)
    end()
    assert history()[0]["state"] == "completed", history()
    assert the_user()["target_chosen_at"] is None, "a plan of solves moved the target"


def the_staircase_grows_and_turns_across_plans():
    """Two plans pointing harder, then one pointing easier: 2.5, then 3.75,
    then back by half of that."""
    a_visitor()
    expected = (model.DEFAULT_TARGET, None, None)
    for verdict, direction in (("too_easy", "harder"), ("too_easy", "harder"), ("too_hard", "easier")):
        press(ids()[0], verdict)
        end()
        expected = model.step_target(*expected, direction)
        user = the_user()
        assert (user["target_prob"], user["target_step"], user["target_direction"]) == expected, \
            (dict(user), expected)
    assert abs(expected[1] - model.FIRST_STEP * model.GROWTH * model.SHRINK) < 1e-4, expected


def the_page_says_what_the_end_will_do():
    """The "next five will aim at" line and the move made at the plan's end
    are one function (web.next_move); checked here as a visitor sees them."""
    a_visitor()
    first = ids()
    press(first[0], "too_easy")
    press(first[1], "too_easy")
    said = flat(page())
    end()
    moved = round(the_user()["target_prob"] * 100)
    assert f"Your next five will aim at {moved}%" in said, (moved, said[:300])
    # And what the buttons do NOT do, which is the question that led here: a
    # visitor who calls a 50% problem too easy expects the chance to change.
    assert "move where the next five aim, not the chances" in said, "the page does not say what a press moves"


def privacy_says_plans_are_kept():
    page_text = " ".join(client.get("/privacy").get_data(as_text=True).split())
    assert "practice plans" in page_text, "/privacy does not mention the plans"
    assert "not stored" in page_text, "/privacy does not say solved is read, not kept"


def each_list_keeps_its_own_staircase():
    """The overall list's two steps harder do not make dp's first step big."""
    a_visitor()
    for _ in range(2):
        press(ids()[0], "too_easy")
        end()
    press(ids("dp")[0], "too_easy", topic="dp")
    end("dp")
    conn = db.connect()
    try:
        row = db.topic_target(conn, HANDLE, "dp")
    finally:
        conn.close()
    assert row["step"] == model.FIRST_STEP, f"dp's first step was {row['step']}"


def a_failed_move_leaves_the_plan_running():
    """Ending the plan and moving the target are one transaction: if the
    move cannot be written, the plan is not ended either, and the visitor can
    press again."""
    a_visitor()
    first = ids()
    press(first[0], "too_easy")
    plan_id = the_plan()[0]["id"]
    conn = db.connect()
    try:
        with conn:
            conn.execute("CREATE TRIGGER failing_write BEFORE UPDATE OF target_prob ON users "
                         "BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
        response = end(plan_id=plan_id)
    finally:
        with conn:
            conn.execute("DROP TRIGGER IF EXISTS failing_write")
        conn.close()
    assert response.status_code == 500, response.status_code
    assert the_plan()[0]["id"] == plan_id, "the plan ended though its move was never written"
    assert the_user()["target_chosen_at"] is None, "the target moved"


# ------------------------------------------------------ skip, and undo one
def undo(problem_id, topic=None):
    data = {"problem": problem_id}
    if topic:
        data["topic"] = topic
    return client.post(f"/results/{HANDLE}/undo", data=data)


def hidden():
    conn = db.connect()
    try:
        return {r[0]: r[1] for r in conn.execute(
            "SELECT problem_id, reason FROM dismissals WHERE handle = ?", (HANDLE,))}
    finally:
        conn.close()


def a_skip_settles_without_a_vote():
    """ADR 0028: three skips and one "too easy" are one vote, harder -- the
    skips say the visitor did not want those problems, nothing about how
    hard the next five should be."""
    a_visitor()
    first = ids()
    for problem in first[:3]:
        press(problem, "skip")
    press(first[3], "too_easy")
    html = page()
    assert html.count("skipped") >= 3, "the skipped rows are not marked"
    assert "4 of 5 done" in flat(html), flat(html)[:300]
    end()
    user = the_user()
    assert (user["target_prob"], user["target_step"], user["target_direction"]) == \
        model.step_target(model.DEFAULT_TARGET, None, None, "harder"), dict(user)
    assert model.plan_direction(["skip", "skip", None]) is None, "skips voted"


def a_skipped_problem_is_hidden_and_can_be_put_back():
    a_visitor()
    first = ids()
    press(first[0], "skip")
    assert hidden() == {first[0]: "skip"}, hidden()
    end()
    assert first[0] not in ids(), "a skipped problem came back in the next plan"
    assert "Put back the problem you hid" in page(), "put back does not count the skip"


def undo_takes_back_one_answer_only():
    """A slip on one row: that row goes back to "to do" and its problem is
    no longer hidden; the other answers in the plan stand, and still vote."""
    a_visitor()
    first = ids()
    press(first[0], "too_hard")
    press(first[1], "too_easy")
    response = undo(first[0])
    assert response.status_code == 302, response.status_code
    assert hidden() == {first[1]: "too_easy"}, hidden()
    html = page()
    assert f'class="verdict-form"' in html and first[0] in \
        __import__("re").findall(r'class="verdict-form".*?name="problem" value="([^"]+)"', html, __import__("re").S), \
        "the undone row did not get its buttons back"
    assert "marked too easy" in html, "undo took back the other answer too"
    end()
    assert the_user()["target_direction"] == "harder", "the undone answer still voted"


def undo_leaves_ended_plans_alone():
    """Like put back: an ended plan is a record of what was said."""
    a_visitor()
    first = ids()
    press(first[0], "too_hard")
    ended = the_plan()[0]["id"]
    end()
    undo(first[0])
    assert outcome(ended, first[0]) == "too_hard", "undo rewrote an ended plan"
    assert first[0] not in hidden(), "undo did not un-hide the problem"


def undo_on_a_topic_list_comes_back_to_it():
    a_visitor()
    dp = ids("dp")
    press(dp[0], "skip", topic="dp")
    response = undo(dp[0], topic="dp")
    assert response.headers["Location"].endswith(f"?topic=dp#p-{dp[0]}"), response.headers["Location"]


def undo_refuses_junk():
    a_visitor()
    first = ids()
    assert client.post("/results/!!!/undo", data={"problem": first[0]}).status_code == 404
    assert undo("9999ZZ").status_code == 404
    assert client.post(f"/results/{HANDLE}/undo", data={}).status_code == 404
    assert undo(first[0], topic="nonsense").status_code == 400
    assert client.get(f"/results/{HANDLE}/undo").status_code == 405


def a_marked_row_offers_undo():
    a_visitor()
    first = ids()
    press(first[0], "skip")
    html = page()
    import re
    # The form AND a button in it: a mutation that removed only the button
    # left a form nobody could submit, and a check that looked for the form
    # alone passed it.
    form = re.search(rf'action="/results/{HANDLE}/undo">(.*?)</form>', html, re.S)
    assert form, "no undo on the marked row"
    assert re.search(r'<button type="submit" aria-label="undo: [^"]+">undo</button>', form.group(1)),         "the undo form has no button"
    assert 'name="verdict" value="skip"' in html, "no skip on the rows still to do"


# ---------------------------------------------------------- the small things
def times_are_said_in_words():
    """web.ago: the words on the page instead of the database's timestamp."""
    import datetime
    now = datetime.datetime(2026, 9, 28, 12, 0, 0, tzinfo=datetime.UTC)
    cases = {
        "2026-09-28T11:59:30Z": "just now",
        "2026-09-28T12:00:05Z": "just now",
        "2026-09-28T11:59:00Z": "1 minute ago",
        "2026-09-28T11:05:00Z": "55 minutes ago",
        "2026-09-28T10:00:00Z": "2 hours ago",
        "2026-09-27T11:00:00Z": "yesterday",
        "2026-09-25T12:00:00Z": "3 days ago",
        "2026-09-07T12:00:00Z": "3 weeks ago",
        "2026-06-28T12:00:00Z": "3 months ago",
        "2024-09-28T12:00:00Z": "2 years ago",
    }
    for stamp, words in cases.items():
        assert web.ago(stamp, now) == words, (stamp, web.ago(stamp, now), words)


def the_page_says_when_in_words():
    a_visitor()
    ids()
    html = page()
    assert "last synced" in html and 'title="' in html
    assert "Z</time>" not in html, "a raw timestamp is still printed in a <time>"


def crawlers_are_kept_off_the_pages_that_do_things():
    response = client.get("/robots.txt")
    assert response.status_code == 200 and response.mimetype == "text/plain", response
    text = response.get_data(as_text=True)
    assert "Disallow: /results/" in text and "Disallow: /progress/" in text, text
    assert "Disallow: /\n" not in text, "the whole site is closed to crawlers"


def the_icon_is_served_and_its_old_address_redirects():
    html = client.get("/").get_data(as_text=True)
    assert 'rel="icon"' in html and "favicon.svg" in html, "no icon linked"
    assert client.get("/static/favicon.svg").status_code == 200
    response = client.get("/favicon.ico")
    assert response.status_code == 301 and response.headers["Location"].endswith("/static/favicon.svg"), \
        (response.status_code, response.headers.get("Location"))


def the_buttons_are_targets_a_finger_can_hit():
    """Measured 2026-09-28 at phone width: the words that steer the
    difficulty were 16 pixels tall. On a touch screen they are 44, and every
    one of them is in the rule; for a mouse, 24 without moving the layout."""
    import re
    css = Path("static/style.css").read_text(encoding="utf-8")
    coarse = css.split("@media (pointer: coarse)", 1)[1].split("\n}\n", 1)[0]
    # The selectors of the rule that gives 44 pixels, not merely somewhere in
    # the block: a second rule there naming the summaries let a mutation that
    # took them out of the 44-pixel rule pass (2026-09-28).
    # Past the @media rule's own opening brace, then a rule whose body holds
    # the 44 pixels; group 1 is its selector list.
    sized = re.search(r"([^{}]*)\{[^{}]*min-height: 44px[^{}]*\}", coarse.split("{", 1)[1])
    assert sized, "no 44-pixel height on a touch screen"
    for selector in (".verdict-form button", ".restore button", ".plan-mark button",
                     ".plan-next button", ".continue button", ".topics summary", ".plans summary"):
        assert selector in sized.group(1), f"{selector} is not in the touch-screen rule"
    fine = re.search(r"\.verdict-form button,\s*\.restore button,\s*\.plan-mark button \{(.*?)\}", css, re.S)
    assert fine and "padding-top: 4px" in fine.group(1) and "margin-top: -4px" in fine.group(1), \
        "the 24-pixel target for a mouse is gone"
    # "skip" and "undo" are narrower than 44 pixels. Widened, a button
    # centres its words, and the gap before "skip" was 26 pixels where the
    # gap before "too easy" was 16 (measured 2026-10-04: now 16 and 16).
    wide = re.search(r"\.verdict-form button,\s*\.plan-mark button \{([^{}]*min-width: 44px[^{}]*)\}",
                     re.sub(r"/\*.*?\*/", "", coarse, flags=re.S))
    assert wide and "text-align: left" in wide.group(1), \
        "a short button's words are centred in its 44 pixels again: uneven gaps between the answers"


def a_press_comes_back_to_where_it_was_made():
    """Found 2026-09-28 at phone width: every button reloaded the page at its
    top, 700 to 1,200 pixels from the row pressed. A press on a row comes
    back to that row, and a press on the whole list to the list -- and the
    ids the addresses name are on the page to be found."""
    a_visitor()
    first = ids()
    response = press(first[0], "too_hard")
    assert response.headers["Location"].endswith(f"/results/{HANDLE}#p-{first[0]}"), \
        response.headers["Location"]
    html = page()
    # Every row, not only the pressed one, and on the <tr> itself.
    for problem_id in first:
        assert f'<tr id="p-{problem_id}"' in html, f"no row carries the id p-{problem_id}"
    response = undo(first[0])
    assert response.headers["Location"].endswith(f"#p-{first[0]}"), response.headers["Location"]

    press(first[1], "skip")
    response = client.post(f"/results/{HANDLE}/restore", data={})
    assert response.headers["Location"].endswith(f"/results/{HANDLE}#next"), response.headers["Location"]
    response = end()
    assert response.headers["Location"].endswith(f"/results/{HANDLE}#next"), response.headers["Location"]
    assert '<section class="recs" id="next"' in page(), "the list does not carry the id the address names"
    # And it lands a step below the top edge, not against it.
    import re
    css = Path("static/style.css").read_text(encoding="utf-8")
    landing = re.search(r"\.recs,\s*\.rec-table tr \{([^}]*)\}", css)
    assert landing and "scroll-margin-top: var(--s3)" in landing.group(1), "a press lands against the top edge"


def the_hidden_attribute_beats_every_class():
    """Found 2026-09-28 on the live site: `.continue { display: flex }`
    outranked the browser's own `[hidden] { display: none }`, so every first
    visit was shown an empty "Continue as" box pointing at /results/__HANDLE__.
    The rule that puts hidden back on top is what every hidden box on the
    site now rests on."""
    import re
    css = Path("static/style.css").read_text(encoding="utf-8")
    rule = re.search(r"(?m)^\[hidden\] \{([^}]*)\}", css)
    assert rule, "no [hidden] rule: any class that sets display shows a hidden element"
    assert "display: none !important" in rule.group(1), rule.group(1)


# ------------------------------------------- the review of 2026-09-28
def the_five_come_first():
    """Six paragraphs stood between the heading and the first problem, which
    on a phone was 701 pixels down a 812-pixel screen. Now one line, then
    the table, then everything that explains it, in one group."""
    import html as entities
    a_visitor()
    ids()
    text = page()
    status, table, notes = (text.index(mark) for mark in
                            ('class="meta recs-status"', 'class="rec-table"', 'class="notes"'))
    assert status < table < notes, (status, table, notes)
    # Nothing between the status line and the table but the line itself.
    between = flat(text[status:table])
    assert "Chance is yours" not in between and "follows your overall" not in between, between
    import re
    line = entities.unescape(flat(text[status:table]))
    assert re.search(r"Aiming at \d+% · 0 of 5 done, 0 solved · plan started just now", line), line
    after = flat(text[notes:])
    assert "Rating is Codeforces’ own" in entities.unescape(after) and "Chance is yours" in after, \
        "the two column names are not explained under the table"
    assert "Chosen for you" not in text, "the old sentence above the table is back"


def every_button_names_its_problem():
    """To a screen reader, five rows of "too hard, too easy, skip" were
    fifteen buttons that did not say which problem they were for."""
    import html as entities
    import re
    a_visitor()
    first = ids()
    press(first[0], "skip")
    text = page()
    for verdict in ("too hard", "too easy", "skip"):
        labels = re.findall(rf'aria-label="{verdict}: ([^"]+)">{verdict}</button>', text)
        assert len(labels) == 4, (verdict, labels)
    undo = re.findall(r'aria-label="undo: ([^"]+)">undo</button>', text)
    assert len(undo) == 1, undo
    names = [entities.unescape(n) for n in re.findall(r'<td>\s*<a href="[^"]+">([^<]+)</a>', text)]
    assert entities.unescape(undo[0]) in names, (undo, names)


def put_back_is_not_a_second_undo():
    """One skip offered "undo" on its row and "put back the 1 problem"
    under the list. "Put back" is for hidden problems that have no undo on
    screen, and says "you", like the rest of the page."""
    a_visitor()
    first = ids()
    press(first[0], "skip")
    assert "Put back" not in page(), "put back offered beside the row's own undo"
    end()
    ids()
    assert "Put back the problem you hid" in page(), "no way back for a problem hidden in an ended plan"
    assert " I hid" not in page()
    # Pressed, then solved: the row shows the solve and has no undo, and
    # nothing is offered back -- a solved problem is never offered again.
    a_visitor()
    first = ids()
    press(first[0], "too_hard")
    a_solve(first[0])
    text = page()
    assert "&#10003; solved" in text, "the solve after the press was not read; this checks nothing"
    assert "Put back" not in text, "put back offered for a problem that is solved"


def what_is_kept_but_not_read_every_visit_is_folded():
    a_visitor()
    first = ids()
    a_solve(first[0], seconds_from_now=0)
    end()
    text = page()
    # Its summary is one of two, by what the numbers do (check_web_flow).
    assert '<details class="footnote">' in text and (
        "<summary>Why Solved adds up to more than" in text
        or "<summary>About these numbers</summary>" in text), "the Solved column's footnote is not folded"
    assert '<details class="meta other-topics"' in text and "Not practised yet:" in text, \
        "the unpractised topics are not folded"
    plans = text.split('<section class="plans">', 1)[1].split("</section>", 1)[0]
    assert "<h2>Past plans</h2>" in plans and "<details>" in plans and "1 ended plan</summary>" in plans, plans[:300]
    assert "<th>Outcome</th>" in plans and "<th>Ended</th>" not in plans, "the column headed like a date"
    # Closed on another list; open when the topic on screen is one of them,
    # so the link marked as the current page is not folded away.
    assert '<details class="meta other-topics">' in text, "folded open on a list that is not one of them"
    assert '<details class="meta other-topics" open>' in page("dp"), "the current topic's link is folded away"


def token(css, name):
    """A colour token's value in style.css's :root, as #rrggbb."""
    import re
    value = re.search(r"(?<![\w-])" + re.escape(name) + r":\s*(#[0-9a-fA-F]{6});", css)
    assert value, f"no {name} colour in :root"
    return value.group(1)


def contrast(one, other):
    """WCAG's contrast ratio between two #rrggbb colours: 1 to 21."""
    def luminance(colour):
        channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    high, low = sorted((luminance(one), luminance(other)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def the_stylesheet_carries_the_review():
    """The field's edge, the loading dim, the notes' one width and the
    hidden announcement: a line or two of CSS each, and a regression in any
    is invisible to every other check."""
    import re
    css = Path("static/style.css").read_text(encoding="utf-8")
    # The field's edge is its fill since v0.8 (ADR 0029): cream on the navy.
    # Whatever the two tokens become, that edge is held to WCAG's 3 to 1 for
    # a control's boundary -- the review found it at 1.3.
    field = re.search(r"\.handle-form input \{([^}]*)\}", css).group(1)
    fill = re.search(r"background: var\((--[\w-]+)\)", field)
    assert fill, "the handle field has no fill of its own"
    ratio = contrast(token(css, fill.group(1)), token(css, "--bg"))
    assert ratio >= 3, f"the handle field's edge is {ratio:.2f} to 1 against the page"
    busy = re.search(r'\.recs\[aria-busy="true"\] \{([^}]*)\}', css)
    assert busy and "opacity" in busy.group(1), "nothing shows that a topic's five are loading"
    notes = re.search(r"\.notes \{([^}]*)\}", css).group(1)
    # Both: the measure is in ch, a width of the element's own font, so the
    # group has to be at the notes' size for them all to be one width.
    assert "max-width: var(--measure)" in notes and "font-size: var(--text-small)" in notes, \
        "the notes run at two widths again"
    hidden = re.search(r"\.sr-only \{([^}]*)\}", css)
    assert hidden and "clip: rect(0, 0, 0, 0)" in hidden.group(1) and "position: absolute" in hidden.group(1), \
        "the announcement a screen reader hears is drawn on the page"


def the_field_comes_before_the_argument():
    """The handle field was 830 pixels down a phone's 812-pixel screen on a
    first visit, under the two paragraphs; spec 4.1 puts it in the hero so
    a returning visitor types at once. Since v0.8 (ADR 0029) one sentence
    stands between the headline and the field -- measured at 375 by 812,
    the field's top is at 335 pixels and the button's bottom at 458, 602
    with "Continue as" above them -- and the argument is the sections after
    the hero."""
    import re
    html = client.get("/").get_data(as_text=True)
    assert html.index('<h1>') < html.index('class="lede"') < html.index('class="handle-form"') \
        < html.index('<section class="band"'), "the form is not in the hero, under the headline"
    lede = re.search(r'<p class="lede">(.*?)</p>', html, re.S).group(1)
    words = " ".join(re.sub(r"<[^>]+>|&\w+;", " ", lede).split())
    assert len(words) <= 200, f"the sentence above the field has grown to {len(words)} characters"
    between = html[html.index('<h1>'):html.index('class="hero-form"')]
    assert between.count("<p") == 1, "more than the one sentence between the headline and the field"
    assert "Enter your handle." not in html, "the lede still tells somebody to fill in a field above it"


def the_landing_page_does_not_scroll_past_the_continue_box():
    """Found at phone width: an autofocus attribute scrolled the offer to
    continue off the screen. The field is focused by script, and only when
    there is no offer above it."""
    html = client.get("/").get_data(as_text=True)
    assert "autofocus" not in html.split("<form", 1)[1].split("</form>", 1)[0], "the field still has autofocus"
    assert "if (!resume || resume.hidden) input.focus();" in html, "the field is never focused"


# ---------------------------------------------------------------- history
def no_history_until_a_plan_ends():
    a_visitor()
    ids()
    assert "Past plans" not in page(), "a history with nothing in it"


def history_lists_ended_plans_newest_first():
    a_visitor()
    first = ids()
    # Now, not a minute ahead: the plan ends in a moment, and a solve after
    # it ended is not the plan's (see the check after this one).
    a_solve(first[0], seconds_from_now=0)
    press(first[1], "too_hard")
    end()
    ids("dp")
    end("dp")
    listed = history()
    assert [p["list"] for p in listed] == ["dp", ""], listed
    assert listed[1]["solved"] == 1 and listed[1]["settled"] == 2 and listed[1]["size"] == 5, listed[1]
    text = flat(page())
    assert "Past plans" in text
    assert "swapped, 2 done" in text, "the history row does not say how it ended"


def a_solve_after_a_plan_ended_is_not_counted_in_it():
    a_visitor()
    first = ids()
    end()
    a_solve(first[0])
    assert history()[0]["solved"] == 0, "a solve after the plan ended was credited to it"


# ------------------------------------------------ what the page says, kept
def a_plan_keeps_the_rating_it_was_made_at():
    """Found in the build: the notes explaining the chances read today's
    rating while the chances were worked out at the plan's. After a contest
    in the middle of a plan the page would explain five problems with a
    number they were not chosen with."""
    a_visitor(rating=1500)
    ids()
    before = the_plan()[0]
    conn = db.connect()
    try:
        with conn:
            conn.execute("UPDATE users SET cf_rating = 1900 WHERE handle = ?", (HANDLE,))
        user = db.get_user(conn, HANDLE)
        recs = web.recommendation_view(conn, user)
    finally:
        conn.close()
    assert before["shown"] == 1500, before["shown"]
    assert recs["shown"] == 1500 and recs["computed"] == before["rating"], \
        f"the plan's notes moved with the rating: shown {recs['shown']}, computed {recs['computed']}"


# ------------------------------------------------------ the landing page
def the_landing_page_can_offer_to_continue():
    """The box is hidden, and filled only by the script from this browser's
    own memory; the address is url_for's, with a placeholder the script
    swaps. The browser check is where it is seen working."""
    html = client.get("/").get_data(as_text=True)
    assert 'id="continue" hidden' in html, "the continue box is not hidden by default"
    assert 'href="/results/__HANDLE__"' in html, "the continue address is not built from the route"
    # Its own way out, and the form left empty while it is offered: both
    # filled with one name was two bright buttons doing one thing. The
    # lines themselves, not a mention of an id -- the page names the box in
    # more than one place, and a mutation removing the hiding once passed a
    # check that looked only for the name.
    assert 'id="continue-forget"' in html, "no way to forget the remembered handle"
    import re
    assert re.search(r'localStorage\.removeItem\("nextcf_handle"\);\s*\} catch \(e\) \{\}\s*box\.hidden = true;', html), \
        "forgetting the handle leaves the continue box"
    assert 'if (document.getElementById("continue")) return;' in html, \
        "the form is filled in with the handle the continue box already offers"


print("the five stay")
check("the first view makes a plan of five", the_first_view_makes_a_plan_of_five)
check("a reload shows the same five", a_reload_shows_the_same_five)
check("the data route serves the same plan", the_json_route_serves_the_same_plan)
check("a change in target waits for the next plan", a_change_in_target_waits_for_the_next_plan)
check("the chooser runs once per plan", the_chooser_runs_once_per_plan)
check("a plan outlives an emptied pool", a_plan_outlives_an_emptied_pool)
check("two views at once make one plan", two_views_at_once_make_one_plan)
check("a second insert returns the first plan", a_second_insert_returns_the_first_plan)
check("each list keeps its own plan", each_list_keeps_its_own_plan)

print("\nsettled once")
check("a solve after the plan began is ticked", a_solve_after_the_plan_began_is_ticked)
check("a solve outside the plan's time is not the plan's", a_solve_before_the_plan_began_is_not_the_plan_s)
check("a solve under the other id counts", a_solve_under_the_other_id_counts)
check("a press settles one without refilling", a_press_settles_one_without_refilling)
check("a press settles it in every plan that holds it", a_press_settles_it_in_every_plan_that_holds_it)
check("solved wins over a press", solved_wins_over_a_press)
check("put back unsettles the running plans only", put_back_unsettles_the_running_plans_only)

print("\nending one")
check("swapping ends it, and the next aims at the new target",
      swapping_ends_it_and_the_next_aims_at_the_new_target)
check("a finished plan offers the next five, and ends completed",
      a_finished_plan_offers_the_next_five_and_ends_completed)
check("a double-click ends one plan", a_double_click_ends_one_plan)
check("the page's button names its plan", the_page_s_button_names_its_plan)
check("a week later, swapped problems may come back", a_week_later_they_may_come_back)
check("the plan route refuses junk", the_plan_route_refuses_junk)
check("a topic's plan is ended on its own list", a_topic_plan_is_ended_on_its_own_list)

print("\nthe target moves when a plan ends")
check("a plan's presses move the target once, by their balance",
      a_plans_presses_move_the_target_once_by_their_balance)
check("a plan nobody pressed leaves the target", a_plan_nobody_pressed_leaves_the_target)
check("the staircase grows and turns across plans", the_staircase_grows_and_turns_across_plans)
check("the page says what the end will do", the_page_says_what_the_end_will_do)
check("each list keeps its own staircase", each_list_keeps_its_own_staircase)
check("a failed move leaves the plan running", a_failed_move_leaves_the_plan_running)
check("/privacy says plans are kept", privacy_says_plans_are_kept)

print("\nskip, and undo one")
check("a skip settles without a vote", a_skip_settles_without_a_vote)
check("a skipped problem is hidden, and can be put back", a_skipped_problem_is_hidden_and_can_be_put_back)
check("undo takes back one answer only", undo_takes_back_one_answer_only)
check("undo leaves ended plans alone", undo_leaves_ended_plans_alone)
check("undo on a topic list comes back to it", undo_on_a_topic_list_comes_back_to_it)
check("undo refuses junk", undo_refuses_junk)
check("a marked row offers undo, the rest offer skip", a_marked_row_offers_undo)

print("\nthe small things")
check("times are said in words", times_are_said_in_words)
check("the page says when, in words", the_page_says_when_in_words)
check("crawlers are kept off the pages that do things", crawlers_are_kept_off_the_pages_that_do_things)
check("the icon is served, and its old address redirects", the_icon_is_served_and_its_old_address_redirects)
check("the buttons are targets a finger can hit", the_buttons_are_targets_a_finger_can_hit)
check("the landing page does not scroll past the continue box",
      the_landing_page_does_not_scroll_past_the_continue_box)
check("a press comes back to where it was made", a_press_comes_back_to_where_it_was_made)
check("the hidden attribute beats every class", the_hidden_attribute_beats_every_class)

print("\nthe review of 2026-09-28")
check("the five come first, and the notes after them", the_five_come_first)
check("every button names its problem", every_button_names_its_problem)
check("put back is not a second undo", put_back_is_not_a_second_undo)
check("what is kept but not read every visit is folded", what_is_kept_but_not_read_every_visit_is_folded)
check("the stylesheet carries the review", the_stylesheet_carries_the_review)
check("the field comes before the argument", the_field_comes_before_the_argument)

print("\nhistory")
check("no history until a plan ends", no_history_until_a_plan_ends)
check("ended plans are listed, newest first", history_lists_ended_plans_newest_first)
check("a solve after a plan ended is not counted in it", a_solve_after_a_plan_ended_is_not_counted_in_it)

print("\nwhat the page says, kept")
check("a plan keeps the rating it was made at", a_plan_keeps_the_rating_it_was_made_at)

print("\nthe landing page")
check("the landing page can offer to continue", the_landing_page_can_offer_to_continue)


# ------------------------------------------- a press without a reload
# ADR 0030. The page's script sends a press asking for data, and draws the
# five that come back; a browser sending the form gets the redirect it always
# got. Whatever else the server says -- a refusal, a page -- the script sends
# the form the ordinary way, so those must stay pages.
AS_DATA = {"Accept": "application/json"}
AS_A_BROWSER = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"}


def five(response):
    """The five a press answered with, by id, and how many are hidden."""
    assert response.status_code == 200 and response.mimetype == "application/json", \
        (response.status_code, response.mimetype)
    data = response.get_json()
    return {row["id"]: row for row in data["recs"]["problems"]}, data


def a_press_sent_by_script_is_answered_with_the_five():
    a_visitor()
    first = ids()
    rows, data = five(client.post(f"/results/{HANDLE}/feedback", headers=AS_DATA,
                                  data={"problem": first[0], "verdict": "too_hard"}))
    assert list(rows) == first, "the five changed with a press"
    assert rows[first[0]]["outcome"] == "too_hard", rows[first[0]]
    assert data["dismissed"] == 1 and hidden() == {first[0]: "too_hard"}, (data["dismissed"], hidden())
    # The same five the page draws after a reload, and the island asks for.
    again, _ = five(client.get(f"/results/{HANDLE}/recommendations"))
    assert again == rows, "the answer to a press is not the list the page would show"


def a_browser_still_gets_the_redirect():
    """No Accept header, a browser's own, or anything at all: the redirect
    to the row, as before ADR 0030 -- the form without script depends on
    it."""
    a_visitor()
    first = ids()
    for headers in ({}, AS_A_BROWSER, {"Accept": "*/*"}):
        response = client.post(f"/results/{HANDLE}/feedback", headers=headers,
                               data={"problem": first[0], "verdict": "skip"})
        assert response.status_code == 302 and response.headers["Location"].endswith(f"#p-{first[0]}"), \
            (headers, response.status_code, response.headers.get("Location"))
    for path, data in (("undo", {"problem": first[0]}), ("restore", {})):
        response = client.post(f"/results/{HANDLE}/{path}", headers=AS_A_BROWSER, data=data)
        assert response.status_code == 302, (path, response.status_code)


def undo_and_put_back_answer_with_the_five_too():
    a_visitor()
    first = ids()
    press(first[0], "skip")
    rows, data = five(client.post(f"/results/{HANDLE}/undo", headers=AS_DATA, data={"problem": first[0]}))
    assert rows[first[0]]["outcome"] is None and data["dismissed"] == 0, (rows[first[0]], data["dismissed"])
    end()
    second = ids()
    press(second[0], "too_easy")
    rows, data = five(client.post(f"/results/{HANDLE}/restore", headers=AS_DATA, data={}))
    assert data["dismissed"] == 0 and hidden() == {}, hidden()
    assert list(rows) == second, "put back changed the five"


def a_press_on_a_topic_list_answers_with_that_list():
    a_visitor()
    first = ids("dp")
    rows, data = five(client.post(f"/results/{HANDLE}/feedback", headers=AS_DATA,
                                  data={"problem": first[0], "verdict": "too_hard", "topic": "dp"}))
    assert data["recs"]["topic"] == "dp" and list(rows) == first, (data["recs"]["topic"], list(rows), first)
    # A list that does not exist is not drawn from: the redirect, which ends
    # at the page that says so.
    response = client.post(f"/results/{HANDLE}/restore", headers=AS_DATA, data={"topic": "no such topic"})
    assert response.status_code == 302, response.status_code


def a_refused_press_is_still_the_page_that_says_why():
    a_visitor()
    first = ids()
    response = client.post(f"/results/{HANDLE}/feedback", headers=AS_DATA,
                           data={"problem": first[0], "verdict": "much too hard"})
    assert response.status_code == 400 and response.mimetype == "text/html", (response.status_code, response.mimetype)
    response = client.post(f"/results/{HANDLE}/undo", headers=AS_DATA, data={"problem": "999999Z"})
    assert response.status_code == 404 and response.mimetype == "text/html", (response.status_code, response.mimetype)


def the_page_has_somewhere_to_say_what_a_press_did():
    """The island fills it (Recommendations.jsx); the template draws it
    empty, inside the section the island replaces, so the two match."""
    a_visitor()
    ids()
    html = page()
    section = html[html.index('<section class="recs" id="next">'):]
    assert section.index('<p class="sr-only" role="status"></p>') < section.index("</section>"), \
        "no status line for a screen reader inside the five's section"


print("\na press without a reload")
check("a press sent by script is answered with the five", a_press_sent_by_script_is_answered_with_the_five)
check("a browser still gets the redirect", a_browser_still_gets_the_redirect)
check("undo and put back answer with the five too", undo_and_put_back_answer_with_the_five_too)
check("a press on a topic list answers with that list", a_press_on_a_topic_list_answers_with_that_list)
check("a refused press is still the page that says why", a_refused_press_is_still_the_page_that_says_why)
check("the page has somewhere to say what a press did", the_page_has_somewhere_to_say_what_a_press_did)

print(f"\n{passed} passed, {failed} failed")
shutil.rmtree(SCRATCH, ignore_errors=True)
sys.exit(1 if failed else 0)
