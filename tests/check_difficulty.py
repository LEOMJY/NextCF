"""Check the "too hard" and "too easy" buttons -- ADR 0021.

No network: a small database built here, and a fake problemset, so the
recommender has a pool without fetching one.

The two that matter most:

  * THE DIRECTION. "Too hard" asks for EASIER problems, which is a HIGHER
    probability of solving them. Getting that backwards would be invisible in
    the code and obvious to every visitor, once.
  * A DISMISSED PROBLEM STAYS GONE. It is stored rather than remembered for
    the page, so a reload cannot bring back the thing somebody just pushed
    away -- which would read as not having listened.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="difficulty-"))

# Must be set before db is imported: db.py reads it at import time.
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

HANDLE = "chooser"


def a_problemset(count=60):
    """Problems across a range of ratings, so the five picked at one target
    are not the five picked at another."""
    problems = []
    for n in range(count):
        problems.append({
            "contestId": 1000 + n,
            "index": "A",
            "name": f"Problem {n}",
            "rating": 800 + (n % 20) * 100,
            "tags": ["math"],
        })
    conn = db.connect()
    try:
        db.save_problemset(conn, problems)
    finally:
        conn.close()


def a_visitor(rating=1500):
    conn = db.connect()
    try:
        db.save_sync(conn, HANDLE, rating, [{
            "id": 1,
            "problem": {"contestId": 999, "index": "A", "name": "Solved",
                        "tags": ["math"], "rating": 900},
            "creationTimeSeconds": 1600000000,
            "author": {"participantType": "PRACTICE"},
            "verdict": "OK",
        }])
        with conn:
            conn.execute(
                "UPDATE users SET target_prob = 0.70, target_chosen_at = NULL WHERE handle = ?",
                (HANDLE,),
            )
            conn.execute("DELETE FROM dismissals WHERE handle = ?", (HANDLE,))
    finally:
        conn.close()


def the_user():
    conn = db.connect()
    try:
        return db.get_user(conn, HANDLE)
    finally:
        conn.close()


def shown_problems():
    """The ids of the five problems the page is offering."""
    html = client.get(f"/results/{HANDLE}").get_data(as_text=True)
    import re
    return re.findall(r'name="problem" value="([^"]+)"', html)


def quotes_target(target):
    """Does the page say it is aiming at this target?

    Two sentences can carry it, because the topic model and the rating-only
    baseline make different claims and each has its own wording (web.py's
    recommendation_view). A check that knew only one of them would pass or
    fail on which model happened to be loaded.
    """
    percent = round(target * 100)
    html = client.get(f"/results/{HANDLE}").get_data(as_text=True)
    # Whitespace is collapsed first. The templates wrap at the measure, so a
    # sentence to be matched runs across a line break and a plain `in` test
    # fails the next time somebody reflows a paragraph -- which is a check
    # failing for a reason that has nothing to do with the code.
    import re
    flat = " ".join(re.sub(r"(?s)<[^>]+>", " ", html).split())
    return (f"Aiming at {percent}%" in flat
            or f"accepted about {percent}% of the time" in flat)


def press(problem_id, verdict):
    return client.post(f"/results/{HANDLE}/feedback",
                       data={"problem": problem_id, "verdict": verdict})


a_problemset()
a_visitor()


# ------------------------------------------------------------------- the ladder
def too_hard_asks_for_easier_problems():
    """The inversion somebody will get backwards: easier means a HIGHER
    chance of solving it."""
    assert model.nudge_target(0.50, "too_hard") == 0.55, model.nudge_target(0.50, "too_hard")
    assert model.nudge_target(0.50, "too_easy") == 0.45, model.nudge_target(0.50, "too_easy")


def the_ladder_has_ends():
    assert model.nudge_target(model.TARGET_EASIEST, "too_hard") == model.TARGET_EASIEST
    assert model.nudge_target(model.TARGET_HARDEST, "too_easy") == model.TARGET_HARDEST
    # And 0.70 is off the ladder on purpose: it is the value the column was
    # created with, and leaving it unreachable keeps "never chosen" readable.
    assert model.TARGET_EASIEST < 0.70, model.TARGET_EASIEST


def an_untouched_target_is_the_product_default():
    """The column's own default is 0.70, which is not the product's 0.50. The
    timestamp beside it is what tells "never chosen" from "chose 0.70"."""
    a_visitor()
    user = the_user()
    assert user["target_prob"] == 0.70, user["target_prob"]
    assert user["target_chosen_at"] is None, user["target_chosen_at"]

    assert quotes_target(model.DEFAULT_TARGET), "the page used the stale default"


# ------------------------------------------------------------- pressing them
def the_page_offers_both_buttons_on_every_problem():
    a_visitor()
    html = client.get(f"/results/{HANDLE}").get_data(as_text=True)
    assert html.count('value="too_hard"') == 5, html.count('value="too_hard"')
    assert html.count('value="too_easy"') == 5, html.count('value="too_easy"')


def too_hard_moves_the_target_and_says_so():
    a_visitor()
    first = shown_problems()
    response = press(first[0], "too_hard")
    assert response.status_code == 302, response.status_code

    user = the_user()
    expected = model.nudge_target(model.DEFAULT_TARGET, "too_hard")
    assert user["target_prob"] == expected, user["target_prob"]
    assert user["target_chosen_at"] is not None, "the choice was not recorded as one"

    assert quotes_target(expected), "the page still quotes the old target"


def too_easy_moves_it_the_other_way():
    a_visitor()
    press(shown_problems()[0], "too_easy")
    assert the_user()["target_prob"] == model.nudge_target(model.DEFAULT_TARGET, "too_easy")


def the_problem_goes_away_and_stays_away():
    a_visitor()
    first = shown_problems()
    press(first[0], "too_hard")

    after = shown_problems()
    assert first[0] not in after, "the problem came back on the next page"
    again = shown_problems()
    assert first[0] not in again, "it came back on a reload"


def pressing_the_other_button_replaces_the_answer():
    """One row per person and problem: only the latest answer is what they
    think."""
    a_visitor()
    problem = shown_problems()[0]
    press(problem, "too_hard")
    press(problem, "too_easy")

    conn = db.connect()
    try:
        rows = conn.execute(
            "SELECT reason FROM dismissals WHERE handle = ? AND problem_id = ?",
            (HANDLE, problem),
        ).fetchall()
    finally:
        conn.close()
    assert len(rows) == 1, f"{len(rows)} rows for one problem"
    assert rows[0]["reason"] == "too_easy", rows[0]["reason"]


def the_five_change_when_the_target_does():
    """A button that visibly does nothing looks broken."""
    a_visitor()
    before = set(shown_problems())
    for problem in list(before)[:1]:
        press(problem, "too_hard")
    after = set(shown_problems())
    assert after != before, "the list did not move"
    assert len(after - before) >= 1, "nothing new arrived"


# ------------------------------------------------------------------ undoing
def the_page_offers_to_put_them_back():
    a_visitor()
    html = client.get(f"/results/{HANDLE}").get_data(as_text=True)
    assert "Put back" not in html, "offered to undo before anything was hidden"

    press(shown_problems()[0], "too_hard")
    html = client.get(f"/results/{HANDLE}").get_data(as_text=True)
    assert "Put back the 1 problem I hid" in html, "no way to undo"

    response = client.post(f"/results/{HANDLE}/restore")
    assert response.status_code == 302, response.status_code

    conn = db.connect()
    try:
        assert db.count_dismissals(conn, HANDLE) == 0, "the problems stayed hidden"
    finally:
        conn.close()


def putting_them_back_leaves_the_target_alone():
    a_visitor()
    press(shown_problems()[0], "too_hard")
    moved = the_user()["target_prob"]
    client.post(f"/results/{HANDLE}/restore")
    assert the_user()["target_prob"] == moved, "undoing a dismissal moved the target"


# ------------------------------------------------------- what cannot be said
def a_verdict_that_is_not_one_of_the_two_is_refused():
    a_visitor()
    response = press(shown_problems()[0], "too_purple")
    assert response.status_code == 400, response.status_code
    assert the_user()["target_chosen_at"] is None, "a junk verdict moved the target"


def a_problem_that_does_not_exist_is_refused():
    a_visitor()
    response = press("9999ZZ", "too_hard")
    assert response.status_code == 404, response.status_code
    assert the_user()["target_chosen_at"] is None, "a junk problem moved the target"


def only_a_post_can_say_it():
    a_visitor()
    assert client.get(f"/results/{HANDLE}/feedback").status_code == 405
    assert client.get(f"/results/{HANDLE}/restore").status_code == 405


def a_junk_handle_is_refused():
    assert client.post("/results/!!!/feedback", data={"problem": "1", "verdict": "too_hard"}).status_code == 404
    assert client.post("/results/!!!/restore").status_code == 404


print("the ladder")
check("too hard asks for easier problems", too_hard_asks_for_easier_problems)
check("the ladder has ends, and 0.70 is off it", the_ladder_has_ends)
check("an untouched target is the product default", an_untouched_target_is_the_product_default)

print("\npressing them")
check("both buttons on every problem", the_page_offers_both_buttons_on_every_problem)
check("too hard moves the target, and the page says so", too_hard_moves_the_target_and_says_so)
check("too easy moves it the other way", too_easy_moves_it_the_other_way)
check("the problem goes away and stays away", the_problem_goes_away_and_stays_away)
check("the other button replaces the answer", pressing_the_other_button_replaces_the_answer)
check("the five change when the target does", the_five_change_when_the_target_does)

print("\nundoing")
check("the page offers to put them back", the_page_offers_to_put_them_back)
check("putting them back leaves the target alone", putting_them_back_leaves_the_target_alone)

print("\nwhat cannot be said")
check("a verdict that is not one of the two", a_verdict_that_is_not_one_of_the_two_is_refused)
check("a problem that does not exist", a_problem_that_does_not_exist_is_refused)
check("only a POST can say it", only_a_post_can_say_it)
check("a junk handle is refused", a_junk_handle_is_refused)

print(f"\n{passed} passed, {failed} failed")
shutil.rmtree(SCRATCH, ignore_errors=True)
sys.exit(1 if failed else 0)
