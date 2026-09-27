"""Check problems by topic -- ADR 0025, without the browser component.

No network: a small database built here, a fake problemset with a few
topics, one of them tiny, and support.json replaced by a small fake so the
guard rail has something to say.

The ones that matter most:

  * A TOPIC'S BUTTONS MOVE ONLY THAT TOPIC'S TARGET. "Too hard" on the dp
    list must leave the overall five, and greedy, exactly where they were.
  * A SMALL TOPIC IS FILLED, NOT UNGUARDED. The problems that passed the
    guard rail come first; only the empty places are filled from the rest,
    and those rows -- and only those -- say so.
  * THE PAGE AND THE DATA ENDPOINT AGREE. The component and the no-script
    page must never show two different fives for one topic.
"""

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="by-topic-"))
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


def fake_start_sync(handle):
    conn = db.connect()
    try:
        active = db.get_active_job(conn, "sync", handle)
        return active["id"] if active is not None else db.create_job(conn, "sync", handle)
    finally:
        conn.close()


sync.start_sync = fake_start_sync
db.init_db()
client = web.app.test_client()
HANDLE = "topical"

# Four ordinary topics, twenty problems each, and "fft" with only two.
TOPICS = ("math", "dp", "greedy", "graphs")
problems = []
for n in range(80):
    problems.append({"contestId": 2000 + n, "index": "A", "name": f"P{n}",
                     "rating": 800 + (n % 20) * 100, "tags": [TOPICS[n % 4]]})
problems += [{"contestId": 2100 + n, "index": "A", "name": f"F{n}", "rating": 1500,
              "tags": ["fft"]} for n in range(2)]
# "2-sat": five ordinary problems and a hard version whose easy version is
# tagged math only -- so on the 2-sat list the easy one is not in the pool.
problems += [{"contestId": 2200 + n, "index": "A", "name": f"S{n}", "rating": 1500,
              "tags": ["2-sat"]} for n in range(5)]
problems += [{"contestId": 2300, "index": "C1", "name": "Pair (easy version)", "rating": 1400, "tags": ["math"]},
             {"contestId": 2300, "index": "C2", "name": "Pair (hard version)", "rating": 1500, "tags": ["2-sat"]}]
conn = db.connect()
db.save_problemset(conn, problems)
conn.close()

# The guard rail's evidence: every problem attempted by plenty of people near
# 1500 -- except most of fft, so fft's list has to be filled.
FAKE_SUPPORT = {
    "covered": [800, 2100], "min_attempters": 2,
    "problems": {f"{p['contestId']}{p['index']}": [1500, 10] for p in problems
                 if p["name"] not in ("F1",)},
}
model.current_support = lambda: FAKE_SUPPORT


def a_visitor():
    conn = db.connect()
    try:
        with conn:
            conn.execute("DELETE FROM submissions WHERE handle = ?", (HANDLE,))
            conn.execute("DELETE FROM dismissals WHERE handle = ?", (HANDLE,))
            conn.execute("DELETE FROM topic_targets WHERE handle = ?", (HANDLE,))
            conn.execute("DELETE FROM recommendations WHERE handle = ?", (HANDLE,))
            conn.execute("DELETE FROM plans WHERE handle = ?", (HANDLE,))
        db.save_sync(conn, HANDLE, 1500, [{
            "id": 1, "creationTimeSeconds": 1600000000, "verdict": "OK",
            "author": {"participantType": "PRACTICE"},
            "problem": {"contestId": 1999, "index": "A", "name": "Solved",
                        "tags": ["math"], "rating": 900}}])
        with conn:
            conn.execute("UPDATE users SET target_prob = 0.70, target_chosen_at = NULL, "
                         "target_step = NULL, target_direction = NULL WHERE handle = ?", (HANDLE,))
    finally:
        conn.close()


def page(topic=None):
    url = f"/results/{HANDLE}" + (f"?topic={topic}" if topic else "")
    response = client.get(url)
    return response, response.get_data(as_text=True)


def shown(html):
    return re.findall(r'name="problem" value="([^"]+)"', html)


def tags_of(pid):
    conn = db.connect()
    try:
        return {r[0] for r in conn.execute("SELECT tag FROM problem_tags WHERE problem_id = ?", (pid,))}
    finally:
        conn.close()


def targets():
    conn = db.connect()
    try:
        user = db.get_user(conn, HANDLE)
        overall = user["target_prob"] if user["target_chosen_at"] else model.DEFAULT_TARGET
        return overall, {r[0]: r[1] for r in conn.execute(
            "SELECT tag, target_prob FROM topic_targets WHERE handle = ?", (HANDLE,))}
    finally:
        conn.close()


def press(problem, verdict, topic=None):
    data = {"problem": problem, "verdict": verdict}
    if topic:
        data["topic"] = topic
    return client.post(f"/results/{HANDLE}/feedback", data=data)


def end(topic=None):
    """Swap the list's plan: what moves its target, since ADR 0027."""
    conn = db.connect()
    try:
        plan, _ = db.active_plan(conn, HANDLE, topic or "")
    finally:
        conn.close()
    data = {"plan": str(plan["id"])}
    if topic:
        data["topic"] = topic
    return client.post(f"/results/{HANDLE}/plan", data=data)


def one_step(direction, target=None):
    """Where a target that has never moved goes on its first step."""
    return model.step_target(model.DEFAULT_TARGET if target is None else target,
                             None, None, direction)[0]


a_visitor()


# --------------------------------------------------------------- the list
def a_topic_list_holds_only_that_topic():
    a_visitor()
    response, html = page("dp")
    assert response.status_code == 200, response.status_code
    ids = shown(html)
    assert len(ids) == 5, ids
    assert all("dp" in tags_of(pid) for pid in ids), [(pid, tags_of(pid)) for pid in ids]
    text = " ".join(html.split())
    assert "Next in dp" in text and "All topics" in text, "the page does not say which list this is"


def an_unknown_topic_is_a_404():
    a_visitor()
    response, _ = page("not-a-topic")
    assert response.status_code == 404, response.status_code


def every_topic_is_a_link_that_works_without_script():
    """Layer 1 (spec 7.1): the component only takes these over."""
    a_visitor()
    _, html = page()
    for tag in ("math", "dp", "greedy", "graphs", "fft"):
        assert f"?topic={tag}" in html, f"no link to {tag}"
    assert "Not practised yet" in html, "unpractised topics are not offered"


def the_current_topic_is_marked():
    a_visitor()
    _, html = page("math")
    assert re.search(r'topic=math"\s*aria-current="page"', html), "the chosen topic is not marked"


# ------------------------------------------------------------- the target
def a_topic_starts_from_the_overall_target_and_says_so():
    a_visitor()
    _, html = page("dp")
    assert "The same as your overall target" in " ".join(html.split()), "the borrowed target went unsaid"


def a_press_on_a_topic_list_moves_only_that_topic():
    """At the end of that topic's plan (ADR 0027), and nowhere else."""
    a_visitor()
    _, html = page("dp")
    response = press(shown(html)[0], "too_hard", topic="dp")
    assert response.status_code == 302, response.status_code
    assert response.headers["Location"].endswith("?topic=dp"), response.headers["Location"]
    assert targets() == (model.DEFAULT_TARGET, {}), f"a press moved a target before its plan ended: {targets()}"
    end("dp")
    overall, per_topic = targets()
    assert overall == model.DEFAULT_TARGET, f"the overall target moved to {overall}"
    assert per_topic == {"dp": one_step("easier")}, per_topic
    _, html = page("dp")
    assert "own target" in " ".join(html.split()), "the page does not say dp now has its own"


def a_topic_target_moves_from_where_it_stands():
    """Two plans pointing the same way: the second step is the first grown
    by half -- the topic's own staircase."""
    a_visitor()
    for _ in range(2):
        _, html = page("greedy")
        press(shown(html)[0], "too_easy", topic="greedy")
        end("greedy")
    _, per_topic = targets()
    first = model.step_target(model.DEFAULT_TARGET, None, None, "harder")
    second = model.step_target(*first, "harder")
    assert per_topic.get("greedy") == second[0], (per_topic, second)


def a_press_on_the_overall_list_leaves_topics_alone():
    a_visitor()
    _, html = page("dp")
    press(shown(html)[0], "too_hard", topic="dp")
    end("dp")
    _, html = page()
    press(shown(html)[0], "too_easy")
    end()
    overall, per_topic = targets()
    assert overall == one_step("harder"), overall
    assert per_topic == {"dp": one_step("easier")}, per_topic


def hiding_is_global():
    """'Not this problem' is about the problem, not the list it was seen in."""
    a_visitor()
    _, html = page("graphs")
    hidden = shown(html)[0]
    press(hidden, "too_hard", topic="graphs")
    for topic in (None, "graphs"):
        _, html = page(topic)
        assert hidden not in shown(html), f"a problem hidden in graphs came back in {topic or 'the overall five'}"


def an_unknown_topic_in_a_press_is_refused():
    a_visitor()
    _, html = page()
    response = press(shown(html)[0], "too_hard", topic="nonsense")
    assert response.status_code == 400, response.status_code
    assert targets()[1] == {}, "a target was stored for a topic that does not exist"


def putting_back_returns_to_the_topic():
    a_visitor()
    _, html = page("dp")
    press(shown(html)[0], "too_hard", topic="dp")
    response = client.post(f"/results/{HANDLE}/restore", data={"topic": "dp"})
    assert response.headers["Location"].endswith("?topic=dp"), response.headers["Location"]


# ------------------------------------------------------------- small topic
def a_small_topic_is_filled_and_only_the_filled_rows_say_so():
    """fft has two problems and only one passes the guard rail: both are
    shown -- five are not possible -- and only the one that did not pass is
    marked. A topic that small fills what it can."""
    a_visitor()
    _, html = page("fft")
    ids = shown(html)
    assert set(ids) == {"2100A", "2101A"}, ids
    rows = re.findall(r'<tr>\s*<td>(.*?)</td>', html, re.S)
    thin_rows = [r for r in rows if "thin-note" in r]
    assert len(thin_rows) == 1 and "F1" in thin_rows[0], thin_rows


def a_hard_version_waits_even_when_its_easy_one_is_in_another_topic():
    """Found in the browser: 1249C2 on the meet-in-the-middle list, its easy
    version tagged otherwise and unsolved. The page must look for the easy
    version in everything unsolved, not in the topic's list."""
    a_visitor()
    _, html = page("2-sat")
    assert "2300C2" not in shown(html), "the hard version was offered before its easy one"
    assert len(shown(html)) == 5, shown(html)


def a_filled_row_is_recorded_as_unguarded():
    a_visitor()
    page("fft")
    conn = db.connect()
    try:
        rows = {r["problem_id"]: dict(r) for r in conn.execute(
            "SELECT problem_id, guarded, topic FROM recommendations WHERE handle = ?", (HANDLE,))}
    finally:
        conn.close()
    assert rows["2100A"]["guarded"] == 1 and rows["2101A"]["guarded"] == 0, rows
    assert all(r["topic"] == "fft" for r in rows.values()), rows


# --------------------------------------------------------- the data route
def the_data_route_gives_the_same_five_as_the_page():
    a_visitor()
    _, html = page("greedy")
    response = client.get(f"/results/{HANDLE}/recommendations?topic=greedy")
    assert response.status_code == 200, response.status_code
    data = response.get_json()
    assert [p["id"] for p in data["recs"]["problems"]] == shown(html), "two different fives for one topic"
    assert data["recs"]["topic"] == "greedy", data["recs"]["topic"]


def the_data_route_records_what_it_shows():
    a_visitor()
    client.get(f"/results/{HANDLE}/recommendations?topic=math")
    conn = db.connect()
    try:
        topics = {r[0] for r in conn.execute(
            "SELECT topic FROM recommendations WHERE handle = ?", (HANDLE,))}
    finally:
        conn.close()
    assert topics == {"math"}, topics


def the_data_route_refuses_what_the_page_refuses():
    a_visitor()
    assert client.get(f"/results/{HANDLE}/recommendations?topic=nonsense").status_code == 404
    assert client.get("/results/!!!/recommendations").status_code == 404
    assert client.get("/results/never_synced_xyz/recommendations").status_code == 404


def the_page_hands_the_component_what_it_drew():
    """The embedded data is the component's starting point; it must be the
    five the template drew, or the first render would change the page."""
    import json
    a_visitor()
    _, html = page("dp")
    blob = re.search(r'<script type="application/json" id="topic-island-data">(.*?)</script>', html, re.S)
    assert blob, "no data for the component"
    data = json.loads(blob.group(1))
    assert [p["id"] for p in data["recs"]["problems"]] == shown(html)
    assert data["urls"]["recommendations"].endswith(f"/results/{HANDLE}/recommendations"), data["urls"]


print("the list")
check("a topic's list holds only that topic, and says so", a_topic_list_holds_only_that_topic)
check("an unknown topic is a 404", an_unknown_topic_is_a_404)
check("every topic is a link that works without script", every_topic_is_a_link_that_works_without_script)
check("the chosen topic is marked", the_current_topic_is_marked)

print("\nthe target")
check("a topic starts from the overall target, and says so", a_topic_starts_from_the_overall_target_and_says_so)
check("a press on a topic's list moves only that topic", a_press_on_a_topic_list_moves_only_that_topic)
check("a topic's target moves from where it stands", a_topic_target_moves_from_where_it_stands)
check("a press on the overall list leaves topics alone", a_press_on_the_overall_list_leaves_topics_alone)
check("hiding is global", hiding_is_global)
check("an unknown topic in a press is refused", an_unknown_topic_in_a_press_is_refused)
check("putting back returns to the topic", putting_back_returns_to_the_topic)

print("\na small topic")
check("filled, and only the filled rows say so", a_small_topic_is_filled_and_only_the_filled_rows_say_so)
check("a filled row is recorded as unguarded, with its topic", a_filled_row_is_recorded_as_unguarded)
check("a hard version waits even when its easy one is in another topic",
      a_hard_version_waits_even_when_its_easy_one_is_in_another_topic)

print("\nthe data route")
check("the same five as the page", the_data_route_gives_the_same_five_as_the_page)
check("it records what it shows", the_data_route_records_what_it_shows)
check("it refuses what the page refuses", the_data_route_refuses_what_the_page_refuses)
check("the page hands the component what it drew", the_page_hands_the_component_what_it_drew)

print(f"\n{passed} passed, {failed} failed")
shutil.rmtree(SCRATCH, ignore_errors=True)
sys.exit(1 if failed else 0)
