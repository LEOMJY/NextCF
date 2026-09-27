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


def hide_everything():
    """Every problem in the pool dismissed, which is what leaves the page
    with nothing to recommend -- the state the undo matters most in."""
    conn = db.connect()
    try:
        ids = [row[0] for row in conn.execute(
            "SELECT id FROM problems WHERE in_problemset = 1")]
        for problem_id in ids:
            # keep= past the cap: a real pool holds 11,000 problems and the
            # cap is 50, so only a nearly exhausted pool can be emptied by
            # hiding -- this builds that pool out of sixty.
            db.record_feedback(conn, HANDLE, problem_id, "too_hard", 0.55, keep=len(ids))
    finally:
        conn.close()
    return len(ids)


def the_undo_survives_an_empty_list():
    """Found on review: the undo sat inside the branch that draws five
    problems, so the moment dismissals emptied the pool the button went with
    them -- and the dismissals, which are stored, stayed in force. The one
    visitor who most needs the way back was the one who could not see it."""
    a_visitor()
    hidden = hide_everything()
    html = client.get(f"/results/{HANDLE}").get_data(as_text=True)
    assert "rec-table" not in html, "the pool was not emptied; this checks nothing"
    assert f"Put back the {hidden} problems I hid" in html, "no way back from an empty list"


def an_empty_list_caused_by_hiding_does_not_claim_everything_is_solved():
    """'You have solved every rated problem' is false when they were hidden."""
    a_visitor()
    hide_everything()
    html = client.get(f"/results/{HANDLE}").get_data(as_text=True)
    assert "You have solved every rated problem" not in html, "blamed the visitor's solving"


def the_undo_survives_a_missing_problemset():
    """The few seconds after a restart, or a failed fetch: no list, and the
    visitor's dismissals are still theirs to undo."""
    a_visitor()
    press(shown_problems()[0], "too_hard")
    conn = db.connect()
    try:
        with conn:
            conn.execute("UPDATE problems SET in_problemset = 0")
        html = client.get(f"/results/{HANDLE}").get_data(as_text=True)
    finally:
        conn.close()
        a_problemset()
    assert "still loading" in html, "the problemset was not missing; this checks nothing"
    assert "Put back the 1 problem I hid" in html, "no way back while the list is loading"


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


# ------------------------------------------------------------- one press, once
def saying_the_same_thing_twice_moves_the_target_once():
    """Found by the audit of 2026-09-26: a double-click sends the same POST
    twice, and each moved the target a step -- 65% to 55% for one press."""
    a_visitor()
    problem = shown_problems()[0]
    press(problem, "too_easy")
    once = the_user()["target_prob"]
    press(problem, "too_easy")
    assert the_user()["target_prob"] == once, \
        f"the same answer twice moved the target to {the_user()['target_prob']}"


def a_double_click_arriving_at_once_moves_the_target_once():
    """Both requests in flight together, on two of the server's threads with
    two connections. Holds even for a naive check-then-write, because both
    requests read the target before either writes and so write the same
    number (see db.record_feedback); kept because "two clicks at once, one
    step" is the promise, whichever way the code keeps it."""
    import threading
    a_visitor()
    problem = shown_problems()[0]
    start = threading.Barrier(2)

    def one_click():
        start.wait()
        web.app.test_client().post(f"/results/{HANDLE}/feedback",
                                   data={"problem": problem, "verdict": "too_easy"})

    clicks = [threading.Thread(target=one_click) for _ in range(2)]
    for t in clicks:
        t.start()
    for t in clicks:
        t.join()
    expected = model.nudge_target(model.DEFAULT_TARGET, "too_easy")
    assert the_user()["target_prob"] == expected, \
        f"two clicks at once moved the target to {the_user()['target_prob']}, not {expected}"


def changing_your_mind_still_counts():
    """Too hard, then too easy on the same problem: two different answers,
    so the target goes one way and back."""
    a_visitor()
    problem = shown_problems()[0]
    press(problem, "too_hard")
    press(problem, "too_easy")
    assert the_user()["target_prob"] == model.DEFAULT_TARGET, the_user()["target_prob"]


# ------------------------------------------------------------------ the cap
def all_problem_ids():
    conn = db.connect()
    try:
        return [row[0] for row in conn.execute(
            "SELECT id FROM problems WHERE in_problemset = 1 ORDER BY id")]
    finally:
        conn.close()


def hidden_ids():
    conn = db.connect()
    try:
        return {row[0] for row in conn.execute(
            "SELECT problem_id FROM dismissals WHERE handle = ?", (HANDLE,))}
    finally:
        conn.close()


def a_handle_keeps_only_the_latest_fifty():
    """Found on review: no limit but the size of the problemset, for any
    handle, from anybody. Past the cap the oldest goes -- the author's
    choice over refusing the press (ADR 0021, amended)."""
    a_visitor()
    ids = all_problem_ids()[:db.DISMISSALS_KEPT + 1]
    conn = db.connect()
    try:
        for problem_id in ids:
            db.record_feedback(conn, HANDLE, problem_id, "too_hard", 0.55)
    finally:
        conn.close()
    hidden = hidden_ids()
    assert len(hidden) == db.DISMISSALS_KEPT, f"{len(hidden)} kept"
    assert ids[0] not in hidden, "the oldest was not the one pushed out"
    assert ids[-1] in hidden, "the newest was not kept"


def pressing_an_old_one_again_makes_it_the_newest():
    """It is the latest thing the visitor said about it."""
    a_visitor()
    ids = all_problem_ids()[:db.DISMISSALS_KEPT + 1]
    conn = db.connect()
    try:
        for problem_id in ids[:db.DISMISSALS_KEPT]:
            db.record_feedback(conn, HANDLE, problem_id, "too_hard", 0.55)
        db.record_feedback(conn, HANDLE, ids[0], "too_easy", 0.50)        # the oldest, again
        db.record_feedback(conn, HANDLE, ids[-1], "too_hard", 0.55)       # one past the cap
    finally:
        conn.close()
    hidden = hidden_ids()
    assert ids[0] in hidden, "re-pressing did not make it the newest"
    assert ids[1] not in hidden, "the next oldest should have gone instead"


def the_page_says_when_the_oldest_will_come_back():
    a_visitor()
    conn = db.connect()
    try:
        for problem_id in all_problem_ids()[:db.DISMISSALS_KEPT - 1]:
            db.record_feedback(conn, HANDLE, problem_id, "too_hard", 0.55)
        below = client.get(f"/results/{HANDLE}").get_data(as_text=True)
        db.record_feedback(conn, HANDLE, all_problem_ids()[db.DISMISSALS_KEPT], "too_hard", 0.55)
        at = client.get(f"/results/{HANDLE}").get_data(as_text=True)
    finally:
        conn.close()
    assert "stay hidden" not in below, "warned before the cap"
    assert f"Only the latest {db.DISMISSALS_KEPT} stay hidden" in at, "no word at the cap"


# ------------------------------------------------------- the walls, said aloud
def at(rating, target):
    """The results page for a visitor at `rating` whose target is `target`."""
    a_visitor(rating=rating)
    conn = db.connect()
    try:
        with conn:
            conn.execute(
                "UPDATE users SET target_prob = ?, target_chosen_at = ? WHERE handle = ?",
                (target, db.utc_now(), HANDLE),
            )
    finally:
        conn.close()
    return client.get(f"/results/{HANDLE}").get_data(as_text=True)


def the_floor_is_said():
    """Found on review: at the bottom of the problemset, "too hard" gave back
    the same five with no word why. Nothing is rated below 800."""
    html = at(400, model.TARGET_EASIEST)
    assert "Nothing left on Codeforces is as easy as" in html, "the floor went unsaid"


def the_ceiling_is_said():
    html = at(3500, model.TARGET_HARDEST)
    assert "Nothing left on Codeforces is as hard as" in html, "the ceiling went unsaid"


def the_end_of_the_ladder_is_said_when_the_list_is_fine():
    html = at(1500, model.TARGET_EASIEST)
    assert "Nothing left" not in html, "called a reachable target unreachable"
    assert "is as easy as the target goes" in html, "the end of the ladder went unsaid"


def a_near_miss_is_not_a_wall():
    """Five problems all a point under the target are on target as far as the
    model can tell (model.BAND), and the page must not call that a floor.
    Added after a mutation that dropped the band survived every page-level
    check: the real pages here never happen to land all on one side."""
    near = [{"probability": model.DEFAULT_TARGET - model.BAND / 2} for _ in range(5)]
    assert web.target_limits(near, model.DEFAULT_TARGET)["reach"] is None, "a near miss called a floor"
    far = [{"probability": model.DEFAULT_TARGET - 2 * model.BAND} for _ in range(5)]
    assert web.target_limits(far, model.DEFAULT_TARGET)["reach"] == "easiest", "a real floor missed"


def five_scattered_around_the_target_are_said():
    """Found in the browser on a small topic: 30%, 31%, 63% at a target of
    50%. Neither wall applies -- the five straddle the target -- and without
    this the page said nothing about why they were so far from it."""
    far = [{"probability": p} for p in (0.30, 0.31, 0.63, 0.40, 0.47)]
    assert web.target_limits(far, 0.5)["scattered"] is True
    near = [{"probability": p} for p in (0.48, 0.52, 0.49, 0.51, 0.50)]
    assert web.target_limits(near, 0.5)["scattered"] is False
    # A wall already explains a list that is all on one side.
    low = [{"probability": p} for p in (0.30, 0.31, 0.32, 0.33, 0.34)]
    assert web.target_limits(low, 0.5)["scattered"] is False


def places_the_band_cannot_fill_go_to_the_nearest():
    """Found in the browser on 2026-09-26: with too few problems inside the
    band, choose() widened it and then picked by topic and contest alone --
    15% and 73% chosen at a target of 50% while nearer problems were left.
    Outside the band, nearness decides."""
    rows = lambda *ids: [{"id": i, "contest_id": 1, "name": i, "problem_index": "A"} for i in ids]
    candidates = list(zip((0.50, 0.49, 0.15, 0.73, 0.29, 0.62, 0.60), rows("a", "b", "c", "d", "e", "f", "g")))
    picked = {row["id"] for _, row in model.choose(candidates, 0.5, 5, {})}
    assert picked == {"a", "b", "g", "f", "e"}, f"picked {sorted(picked)}: the nearest outside the band are 0.60, 0.62, 0.29"


def an_ordinary_page_says_neither():
    html = at(1500, model.DEFAULT_TARGET)
    assert "Nothing left" not in html and "as the target goes" not in html, "a wall where there is none"
    # Not asserted here: that the list is not "scattered". This file's fake
    # problemset has three problems per rating, and near 50% for a 1500
    # visitor it really has only two -- the note is true of it. The rule is
    # checked directly in five_scattered_around_the_target_are_said.


# ---------------------------------------------- the guard rail, on the page
def with_support(problem_bins, covered, fn):
    """Run fn with support.json replaced by a small one about this file's
    fake problemset (ADR 0023)."""
    conn = db.connect()
    try:
        ids = [r[0] for r in conn.execute("SELECT id FROM problems WHERE in_problemset = 1")]
    finally:
        conn.close()
    table = {}
    for pid in ids:
        bins = problem_bins(pid)
        if bins:
            lo = min(bins)
            table[pid] = [lo] + [bins.get(b, 0) for b in range(lo, max(bins) + 1, model.SUPPORT_BIN)]
    fake = {"covered": list(covered), "min_attempters": 2, "problems": table}
    real = model.current_support
    model.current_support = lambda: fake
    try:
        return fn()
    finally:
        model.current_support = real


def outside_the_data_the_page_says_where_it_looked():
    html = with_support(lambda pid: {1900: 5}, (800, 2000), lambda: at(2600, model.DEFAULT_TARGET))
    text = " ".join(html.split())          # the template breaks lines mid-sentence
    assert "people rated around 2000 have actually tried" in text, "the clamp went unsaid"
    # One note, not two beginning "Your rating is outside": 2600 is also past
    # the model's own level range, and that point rides in the same sentence.
    assert text.count("Your rating is outside") == 1, "two notes saying nearly the same thing"


def when_the_rule_stands_aside_the_page_says_so():
    html = with_support(lambda pid: None, (800, 2000), lambda: at(1500, model.DEFAULT_TARGET))
    assert "rec-table" in html, "no list at all"
    assert "rest on less evidence" in html, "the fallback went unsaid"


def an_ordinary_visitor_hears_nothing_about_it():
    html = with_support(lambda pid: {1400: 3, 1500: 3}, (800, 2000), lambda: at(1500, model.DEFAULT_TARGET))
    assert "actually tried" not in html and "less evidence" not in html, "a note where the rule held"


def with_a_failing_write(trigger_sql, fn):
    """Run fn while one write the route makes is made to fail, the way a
    crash or a full disk would. A trigger in the file, so the web app's own
    connection meets it."""
    conn = db.connect()
    try:
        with conn:
            conn.execute(trigger_sql)
        return fn()
    finally:
        with conn:
            conn.execute("DROP TRIGGER IF EXISTS failing_write")
        conn.close()


def half_a_verdict_is_never_stored():
    """Found on review: hiding the problem and moving the target were two
    transactions, so a failure in the second left the first standing -- the
    problem gone and the target unmoved, half of what was asked."""
    a_visitor()
    problem = shown_problems()[0]
    response = with_a_failing_write(
        "CREATE TRIGGER failing_write BEFORE UPDATE OF target_prob ON users "
        "BEGIN SELECT RAISE(ABORT, 'simulated failure'); END",
        lambda: press(problem, "too_hard"),
    )
    assert response.status_code == 500, response.status_code
    conn = db.connect()
    try:
        assert db.count_dismissals(conn, HANDLE) == 0, "the problem was hidden and the target never moved"
    finally:
        conn.close()
    assert the_user()["target_chosen_at"] is None, "the target moved"


def a_failure_at_the_write_is_not_blamed_on_the_problem():
    """Found on review: every IntegrityError was reported as "not a problem
    this site knows", though the insert has two foreign keys and SQLite does
    not say which refused. A real problem, and the write failing anyway,
    must read as ours."""
    a_visitor()
    problem = shown_problems()[0]
    response = with_a_failing_write(
        "CREATE TRIGGER failing_write BEFORE INSERT ON dismissals "
        "BEGIN SELECT RAISE(ABORT, 'simulated failure'); END",
        lambda: press(problem, "too_hard"),
    )
    html = response.get_data(as_text=True)
    assert "not one this site knows" not in html, "blamed the problem for a failure of ours"
    assert response.status_code == 500, response.status_code


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
check("the undo survives an empty list", the_undo_survives_an_empty_list)
check("an empty list from hiding is not 'solved everything'",
      an_empty_list_caused_by_hiding_does_not_claim_everything_is_solved)
check("the undo survives a missing problemset", the_undo_survives_a_missing_problemset)

print("\nwhat cannot be said")
check("a verdict that is not one of the two", a_verdict_that_is_not_one_of_the_two_is_refused)
check("a problem that does not exist", a_problem_that_does_not_exist_is_refused)
check("only a POST can say it", only_a_post_can_say_it)
check("a junk handle is refused", a_junk_handle_is_refused)
print("\none press, once")
check("saying the same thing twice moves the target once", saying_the_same_thing_twice_moves_the_target_once)
check("a double-click arriving at once moves the target once", a_double_click_arriving_at_once_moves_the_target_once)
check("changing your mind still counts", changing_your_mind_still_counts)

print("\nthe cap")
check("a handle keeps only the latest fifty", a_handle_keeps_only_the_latest_fifty)
check("pressing an old one again makes it the newest", pressing_an_old_one_again_makes_it_the_newest)
check("the page says when the oldest will come back", the_page_says_when_the_oldest_will_come_back)

print("\nthe walls, said aloud")
check("the floor is said", the_floor_is_said)
check("the ceiling is said", the_ceiling_is_said)
check("the end of the ladder is said when the list is fine", the_end_of_the_ladder_is_said_when_the_list_is_fine)
check("a near miss is not a wall", a_near_miss_is_not_a_wall)
check("five scattered around the target are said", five_scattered_around_the_target_are_said)
check("places the band cannot fill go to the nearest", places_the_band_cannot_fill_go_to_the_nearest)
check("an ordinary page says neither", an_ordinary_page_says_neither)

print("\nthe guard rail, on the page")
check("outside the data, the page says where it looked", outside_the_data_the_page_says_where_it_looked)
check("when the rule stands aside, the page says so", when_the_rule_stands_aside_the_page_says_so)
check("an ordinary visitor hears nothing about it", an_ordinary_visitor_hears_nothing_about_it)

print("\nwhen a write fails")
check("half a verdict is never stored", half_a_verdict_is_never_stored)
check("a failure at the write is not blamed on the problem", a_failure_at_the_write_is_not_blamed_on_the_problem)

print(f"\n{passed} passed, {failed} failed")
shutil.rmtree(SCRATCH, ignore_errors=True)
sys.exit(1 if failed else 0)
