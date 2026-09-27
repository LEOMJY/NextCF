"""Check the record of what was recommended -- ADR 0024.

No network: a small database built here, and a fake problemset.

The two that matter most:

  * THE FIRST SHOWING IS KEPT. The chance a visitor saw before trying a
    problem is the claim being tested; a reload recomputing it must not
    overwrite it, or the report would score the model against numbers
    nobody was shown.
  * ONLY A FIRST SUBMISSION IS SCORED. A problem tried before it was
    recommended is left out, because what happens next is not the event the
    chance was about -- the same unit the model is fitted and judged on.
"""

import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="recommendations-"))

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
HANDLE = "recorded"


def a_problemset(count=60):
    conn = db.connect()
    try:
        db.save_problemset(conn, [
            {"contestId": 1000 + n, "index": "A", "name": f"Problem {n}",
             "rating": 800 + (n % 20) * 100, "tags": ["math"]}
            for n in range(count)])
    finally:
        conn.close()


def a_visitor(rating=1500):
    """A fresh visitor: nothing recommended, nothing hidden, and no
    submissions but the one below. Clearing the submissions matters: without
    it, one check's solve was still there for the next, and a mutation that
    broke the alias fold survived because of it."""
    conn = db.connect()
    try:
        with conn:
            conn.execute("DELETE FROM submissions WHERE handle = ?", (HANDLE,))
        db.save_sync(conn, HANDLE, rating, [{
            "id": 1, "creationTimeSeconds": 1600000000, "verdict": "OK",
            "author": {"participantType": "PRACTICE"},
            "problem": {"contestId": 999, "index": "A", "name": "Solved",
                        "tags": ["math"], "rating": 900}}])
        with conn:
            conn.execute("DELETE FROM recommendations")
            conn.execute("DELETE FROM dismissals")
            # A plan outlives the view that made it (ADR 0026); each check
            # starts without one.
            conn.execute("DELETE FROM plans")
            conn.execute("UPDATE users SET target_prob = 0.70, target_chosen_at = NULL WHERE handle = ?",
                         (HANDLE,))
    finally:
        conn.close()


def recorded():
    conn = db.connect()
    try:
        return {r["problem_id"]: dict(r) for r in conn.execute(
            "SELECT * FROM recommendations WHERE handle = ?", (HANDLE,))}
    finally:
        conn.close()


def shown_on_the_page():
    import re
    html = client.get(f"/results/{HANDLE}").get_data(as_text=True)
    return re.findall(r'class="verdict-form".*?name="problem" value="([^"]+)"', html, re.S)


a_problemset()


# --------------------------------------------------------- what is written
def the_five_shown_are_written_down():
    a_visitor()
    shown = shown_on_the_page()
    rows = recorded()
    assert set(rows) == set(shown), f"recorded {sorted(rows)}, shown {sorted(shown)}"
    for row in rows.values():
        assert 0 < row["probability"] < 1, row
        assert row["target"] == model.DEFAULT_TARGET, row
        assert row["source"] in ("topic", "rating"), row
        assert row["guarded"] in (0, 1), row


def the_chance_is_the_computed_one_not_the_rounded_percent():
    a_visitor()
    shown_on_the_page()
    probabilities = [r["probability"] for r in recorded().values()]
    assert any(round(p, 2) != p for p in probabilities), \
        f"every chance is a whole percent -- the printed number was stored: {probabilities}"


def the_first_showing_is_kept():
    """A reload, or a later visit showing the same problem at a slightly
    different chance, must not overwrite what the visitor saw first."""
    a_visitor()
    shown_on_the_page()
    conn = db.connect()
    try:
        with conn:
            conn.execute("UPDATE recommendations SET probability = 0.123, shown_at = '2026-01-01T00:00:00Z'")
    finally:
        conn.close()
    shown_on_the_page()
    rows = recorded()
    assert len(rows) == 5, f"a reload wrote {len(rows) - 5} more rows"
    assert all(r["probability"] == 0.123 and r["shown_at"] == "2026-01-01T00:00:00Z" for r in rows.values()), \
        "a reload overwrote the first showing"


def what_a_press_brings_is_written_too():
    """A press moves the target for the next plan (ADR 0026), so what it
    brings arrives when the plan is swapped -- and is written down then, at
    the target it was chosen for."""
    a_visitor()
    first = shown_on_the_page()
    client.post(f"/results/{HANDLE}/feedback", data={"problem": first[0], "verdict": "too_hard"})
    conn = db.connect()
    try:
        plan, _ = db.active_plan(conn, HANDLE, "")
    finally:
        conn.close()
    client.post(f"/results/{HANDLE}/plan", data={"plan": plan["id"]})
    second = shown_on_the_page()
    rows = recorded()
    assert set(first) | set(second) <= set(rows), "the new five were not recorded"
    assert rows[first[0]]["target"] == model.DEFAULT_TARGET, "the first row was rewritten"
    fresh = [p for p in second if p not in first]
    assert fresh and all(rows[p]["target"] != model.DEFAULT_TARGET for p in fresh), \
        "the new rows do not carry the new target"


def a_handle_stops_being_recorded_at_the_cap():
    a_visitor()
    conn = db.connect()
    try:
        picks = [{"id": f"{1000 + n}A", "probability": 0.5} for n in range(12)]
        added = db.record_recommendations(conn, HANDLE, picks, 0.5, "topic", None, True, keep=10)
        assert added == 10, added
        added = db.record_recommendations(conn, HANDLE, [{"id": "1050A", "probability": 0.5}],
                                          0.5, "topic", None, True, keep=10)
        assert added == 0, "recorded past the cap"
    finally:
        conn.close()


def a_failure_to_record_does_not_break_the_page():
    a_visitor()
    real = db.record_recommendations

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("no such table: recommendations")

    db.record_recommendations = broken
    try:
        response = client.get(f"/results/{HANDLE}")
        assert response.status_code == 200, response.status_code
        assert "rec-table" in response.get_data(as_text=True), "the page lost its list"
    finally:
        db.record_recommendations = real


# ------------------------------------------------------------- the report
SHOWN_AT = "2026-10-01T00:00:00Z"
SHOWN_SECONDS = 1790812800                     # the same instant


def a_submission(sid, problem_id, when, verdict):
    return {"id": sid, "creationTimeSeconds": when, "verdict": verdict,
            "author": {"participantType": "PRACTICE"},
            "problem": {"contestId": int(problem_id[:-1]), "index": problem_id[-1],
                        "name": f"P{problem_id}", "tags": ["math"], "rating": 1500}}


def the_report_scores_first_submissions_after_the_showing():
    a_visitor()
    after, before = SHOWN_SECONDS + 600, SHOWN_SECONDS - 86400
    conn = db.connect()
    try:
        with conn:
            for pid, p in (("1001A", 0.52), ("1002A", 0.48), ("1003A", 0.50),
                           ("1004A", 0.51), ("1005A", 0.33)):
                conn.execute("INSERT INTO recommendations VALUES (?, ?, ?, ?, 0.5, 'topic', NULL, 1, NULL)",
                             (HANDLE, pid, SHOWN_AT, p))
        db.save_sync(conn, HANDLE, 1500, [
            a_submission(1, "999A", 1600000000, "OK"),        # a_visitor's own solve
            a_submission(11, "1001A", after, "OK"),           # first after the showing: accepted
            a_submission(12, "1002A", after, "WRONG_ANSWER"), # first after: wrong...
            a_submission(13, "1002A", after + 99, "OK"),      # ...and a later OK does not rescue it
            a_submission(14, "1003A", before, "WRONG_ANSWER"),# tried BEFORE it was shown
            a_submission(15, "1003A", after, "OK"),           #   so not scored at all
            a_submission(16, "1005A", after, "OK"),           # 1004A: never tried
        ])
        report = db.recommendation_calibration(conn)
    finally:
        conn.close()
    assert (report["shown"], report["tried_before"], report["tried"]) == (5, 1, 3), report
    bins = {round(low, 1): (n, round(said, 2), happened) for low, n, said, happened in report["bins"]}
    assert bins == {0.3: (1, 0.33, 1.0), 0.4: (1, 0.48, 0.0), 0.5: (1, 0.52, 1.0)}, bins


def the_report_reads_a_solve_under_either_id():
    """ADR 0010: the Div. 2 copy of a recommended problem is the problem."""
    a_visitor()
    conn = db.connect()
    try:
        with conn:
            conn.execute("INSERT INTO recommendations VALUES (?, '1001A', ?, 0.5, 0.5, 'topic', NULL, 1, NULL)",
                         (HANDLE, SHOWN_AT))
        # The sync first: it stores 7001A, which the alias row has to point from.
        db.save_sync(conn, HANDLE, 1500, [a_submission(21, "7001A", SHOWN_SECONDS + 60, "OK")])
        with conn:
            conn.execute("INSERT OR REPLACE INTO problem_aliases (alias_id, canonical_id) VALUES ('7001A', '1001A')")
        report = db.recommendation_calibration(conn)
        with conn:
            conn.execute("DELETE FROM problem_aliases WHERE alias_id = '7001A'")
    finally:
        conn.close()
    assert report["tried"] == 1 and report["bins"][0][3] == 1.0, report


def the_author_is_left_out_of_the_report():
    a_visitor()
    conn = db.connect()
    try:
        with conn:
            conn.execute("INSERT INTO recommendations VALUES (?, '1001A', ?, 0.5, 0.5, 'topic', NULL, 1, NULL)",
                         (HANDLE, SHOWN_AT))
        assert db.recommendation_calibration(conn)["shown"] == 1
        assert db.recommendation_calibration(conn, exclude_handles=(HANDLE,))["shown"] == 0
    finally:
        conn.close()


def privacy_says_it_is_kept():
    page = " ".join(client.get("/privacy").get_data(as_text=True).split())
    assert "which problems were recommended" in page, "/privacy does not mention the record"


print("what is written")
check("the five shown are written down", the_five_shown_are_written_down)
check("the chance is the computed one, not the printed percent", the_chance_is_the_computed_one_not_the_rounded_percent)
check("the first showing is kept through a reload", the_first_showing_is_kept)
check("what a press brings is written too, with its target", what_a_press_brings_is_written_too)
check("a handle stops being recorded at the cap", a_handle_stops_being_recorded_at_the_cap)
check("a failure to record does not break the page", a_failure_to_record_does_not_break_the_page)

print("\nthe report")
check("first submissions after the showing are scored, and only those",
      the_report_scores_first_submissions_after_the_showing)
check("a solve under the other id counts", the_report_reads_a_solve_under_either_id)
check("the author is left out", the_author_is_left_out_of_the_report)
check("/privacy says it is kept", privacy_says_it_is_kept)

print(f"\n{passed} passed, {failed} failed")
shutil.rmtree(SCRATCH, ignore_errors=True)
sys.exit(1 if failed else 0)
