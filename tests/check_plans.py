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
            conn.execute("UPDATE users SET target_prob = 0.70, target_chosen_at = NULL WHERE handle = ?",
                         (HANDLE,))
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
    assert "Your plan since" in flat(html), "the page does not say it is a plan"
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
            db.record_feedback(conn, HANDLE, problem_id, "too_hard", 0.55, keep=len(every))
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
    assert second[0]["target"] == model.nudge_target(model.DEFAULT_TARGET, "too_hard"), \
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
    assert response.headers["Location"].endswith("?topic=dp"), response.headers["Location"]
    assert history()[0]["list"] == "dp", history()


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
    assert 'localStorage.removeItem("nextcf_handle");\n          } catch (e) {}\n          box.hidden = true;' in html, \
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

print("\nhistory")
check("no history until a plan ends", no_history_until_a_plan_ends)
check("ended plans are listed, newest first", history_lists_ended_plans_newest_first)
check("a solve after a plan ended is not counted in it", a_solve_after_a_plan_ended_is_not_counted_in_it)

print("\nwhat the page says, kept")
check("a plan keeps the rating it was made at", a_plan_keeps_the_rating_it_was_made_at)

print("\nthe landing page")
check("the landing page can offer to continue", the_landing_page_can_offer_to_continue)

print(f"\n{passed} passed, {failed} failed")
shutil.rmtree(SCRATCH, ignore_errors=True)
sys.exit(1 if failed else 0)
