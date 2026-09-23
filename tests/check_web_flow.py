"""Check of the whole v0.2 web flow, with no network.

Uses a temporary database (NEXTCF_DB) and replaces sync.start_sync with a
version that records a job but starts no thread, so nothing here talks to
Codeforces. The real sync is checked by running it for real.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="webflow-"))

# Must be set before db is imported: db.py reads it at import time.
os.environ["NEXTCF_DB"] = str(SCRATCH / "test.db")
# Paths in this file are relative to the repository root, and the modules
# being checked live there, so go there first. The check then runs the same
# from any directory.
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import db  # noqa: E402
import sync  # noqa: E402
import web  # noqa: E402

passed = failed = 0
LEAKS = ("{#", "#}", "{%", "Jinja comment", "would be sent")


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
    """Records the job the way the real one does, and starts no thread."""
    conn = db.connect()
    try:
        active = db.get_active_job(conn, "sync", handle)
        if active is not None:
            return active["id"]
        return db.create_job(conn, "sync", handle)
    finally:
        conn.close()


sync.start_sync = fake_start_sync
client = web.app.test_client()


def get(path):
    response = client.get(path)
    html = response.get_data(as_text=True)
    leaked = [m for m in LEAKS if m in html]
    assert not leaked, f"{path} leaked template syntax: {leaked}"
    return response, html


def api_sub(sub_id, name="Watermelon", verdict="OK", contest_id=1234, index="A", seconds=1600000000):
    # index has to vary with the name: contest id + index IS the problem id, so
    # two different names under one index are one problem that changed its
    # name, and only the first is stored. That is correct, and it caught a
    # careless fixture here.
    problem = {"index": index, "name": name, "tags": ["math"], "rating": 800}
    if contest_id is not None:
        problem["contestId"] = contest_id
    sub = {"id": sub_id, "problem": problem, "creationTimeSeconds": seconds,
           "author": {"participantType": "PRACTICE"}}
    if verdict is not None:
        sub["verdict"] = verdict
    return sub


def synced(handle, submissions):
    conn = db.connect()
    try:
        db.save_sync(conn, handle, 1500, submissions)
    finally:
        conn.close()


print("web flow")


def landing_page():
    response, html = get("/")
    assert response.status_code == 200, response.status_code
    assert "Codeforces handle" in html


check("GET / renders the form", landing_page)


def empty_submission():
    response = client.post("/", data={"handle": ""})
    assert response.status_code == 400, response.status_code


check("POST / with nothing typed is 400", empty_submission)


def form_redirects_to_results():
    response = client.post("/", data={"handle": "alpha"})
    assert response.status_code == 302, response.status_code
    assert response.headers["Location"].endswith("/results/alpha"), response.headers["Location"]


check("POST / sends the visitor to /results/<handle>", form_redirects_to_results)


def unknown_handle_starts_a_sync():
    response = client.get("/results/alpha")
    assert response.status_code == 302, response.status_code
    location = response.headers["Location"]
    assert "/progress/" in location, location
    conn = db.connect()
    try:
        assert db.get_active_job(conn, "sync", "alpha") is not None, "no job was created"
    finally:
        conn.close()


check("a handle with no data redirects to a new sync", unknown_handle_starts_a_sync)


def progress_page_invents_no_number():
    # A sync is one request now, so there is no true number while it runs: the
    # count goes from nothing to everything at once. The page must not show
    # one, even when the jobs row holds it.
    conn = db.connect()
    try:
        job_id = db.get_active_job(conn, "sync", "alpha")["id"]
        db.claim_job(conn, job_id)
        db.set_job_progress(conn, job_id, 1234)
    finally:
        conn.close()
    response, html = get(f"/progress/{job_id}")
    assert response.status_code == 200, response.status_code
    assert "alpha" in html, "the page does not say whose history it is reading"
    assert 'http-equiv="refresh"' in html, "the page does not reload itself"
    assert "1234" not in html, "a submission count is on a page that cannot know one mid-sync"
    assert "%" not in html, "a percentage appeared on a page that cannot know one"


check("a running sync names the handle, reloads itself, and shows no number or percentage", progress_page_invents_no_number)


def finished_sync_redirects_to_results():
    conn = db.connect()
    try:
        job_id = db.get_active_job(conn, "sync", "alpha")["id"]
        db.finish_job(conn, job_id)
    finally:
        conn.close()
    response = client.get(f"/progress/{job_id}")
    assert response.status_code == 302, response.status_code
    assert response.headers["Location"].endswith("/results/alpha"), response.headers["Location"]


check("a finished sync sends the visitor on to the results", finished_sync_redirects_to_results)


def failed_sync_explains_itself():
    conn = db.connect()
    try:
        job_id = db.create_job(conn, "sync", "beta")
        db.finish_job(conn, job_id, error="Codeforces rejected the request: handle not found")
    finally:
        conn.close()
    response, html = get(f"/progress/{job_id}")
    assert response.status_code == 200, response.status_code
    assert "handle not found" in html, "the reason it failed is not on the page"


check("a failed sync shows the reason, in words", failed_sync_explains_itself)


def results_page_reads_the_database():
    synced("gamma", [api_sub(1), api_sub(2, name="Two Buttons", verdict=None, index="B")])
    response, html = get("/results/gamma")
    assert response.status_code == 200, response.status_code
    assert "Watermelon" in html and "Two Buttons" in html, "the problems are missing"
    assert "codeforces.com/contest/1234/problem/A" in html, "the problem link is wrong"
    assert "TESTING" in html, "an unjudged submission should read TESTING on the page"
    assert "last synced" in html


check("a synced handle renders its table straight from the database", results_page_reads_the_database)


def acmsguru_problem_has_no_link():
    sub = api_sub(3, name="A guru problem", contest_id=None)
    sub["problem"]["problemsetName"] = "acmsguru"
    sub["problem"]["index"] = "553"
    synced("delta", [sub])
    response, html = get("/results/delta")
    assert "A guru problem" in html, "the problem is missing"
    assert "codeforces.com/contest/None" not in html, "a broken link was built"


check("a problem with no contest id is shown as text, not a broken link", acmsguru_problem_has_no_link)


def stale_data_is_shown_and_resynced_behind_a_live_line():
    """Changed by ADR 0018 and its amendment, both on 2026-09-22. Until then a
    stale page redirected to a queue and the visitor waited again. Now the
    stored page is served at once and the fresh fetch runs behind it, with a
    line saying so -- which sync the numbers are from, where the new one is in
    the queue, and how long that is."""
    synced("epsilon", [api_sub(4)])
    conn = db.connect()
    try:
        with conn:
            conn.execute("UPDATE users SET last_synced = '2020-01-01T00:00:00Z' WHERE handle = 'epsilon'")
    finally:
        conn.close()

    response, html = get("/results/epsilon")
    assert response.status_code == 200, f"a returning visitor was sent to a queue ({response.status_code})"
    assert "Re-syncing" in html, "the page did not say a sync was running"
    assert "The numbers below are from the sync above" in html, "old numbers shown as if current"

    conn = db.connect()
    try:
        active = db.get_active_job(conn, "sync", "epsilon")
    finally:
        conn.close()
    assert active is not None, "nothing was queued to refresh it"


check("stale data is shown at once, with a line saying it is being refreshed", stale_data_is_shown_and_resynced_behind_a_live_line)


def fresh_data_is_not_refetched():
    synced("zeta", [api_sub(5)])
    response = client.get("/results/zeta")
    assert response.status_code == 200, "fresh data was re-fetched instead of shown"
    conn = db.connect()
    try:
        assert db.get_active_job(conn, "sync", "zeta") is None, "a sync was started for fresh data"
    finally:
        conn.close()


check("data inside the freshness window is shown without another fetch", fresh_data_is_not_refetched)


def long_history_is_cut_short_and_says_so():
    many = [api_sub(100 + i, name=f"Problem {i}", contest_id=1000 + i) for i in range(150)]
    synced("eta", many)
    response, html = get("/results/eta")
    assert response.status_code == 200, response.status_code
    rendered = html.count("codeforces.com/contest/")
    assert rendered == web.RESULTS_LIMIT, f"{rendered} rows rendered, expected {web.RESULTS_LIMIT}"
    assert "150" in html, "the page does not say how many there are in total"
    assert "most recent" in html, "the page does not say the list is cut short"


check("a long history shows one page and says how many it is hiding", long_history_is_cut_short_and_says_so)


def bad_addresses():
    response, _ = get("/results/!!!")
    assert response.status_code == 404, response.status_code
    response, _ = get("/progress/999999")
    assert response.status_code == 404, response.status_code
    response = client.get("/progress/not-a-number")
    assert response.status_code == 404, response.status_code


check("junk handles and missing job numbers are 404, not tracebacks", bad_addresses)


def how_page_holds_the_section_9_number():
    """Spec section 4.1: the number one click away, and the SAME number the
    spec records -- a page and a document that disagree about the one claim
    the project exists to make would be worse than either alone."""
    response, html = get("/how")
    assert response.status_code == 200, response.status_code
    ev = web.EVALUATION
    for value in (ev["baseline"], ev["model"]):
        assert f"{value:.4f}" in html, f"{value:.4f} is not on /how"
    cells = html.count('<td class="num">')
    expected = 2 * len(ev["strata"]) + 2 + 2 * len(ev["calibration"])
    assert cells == expected, f"{cells} number cells on /how, expected {expected}"
    spec = Path("docs/spec.md").read_text(encoding="utf-8")
    section9 = spec[spec.index("## 9. How we will know it worked"):spec.index("## 10.")]
    for band, base, ours in ev["strata"]:
        assert f"{ours:.4f}" in section9 and f"{base:.4f}" in section9, \
            f"{band}: web.EVALUATION says {base:.4f} / {ours:.4f}, spec section 9 does not"
    assert f"**{ev['model']:.4f}**" in section9, "spec section 9's headline is not web.EVALUATION's"


check("/how shows section 9's number, and it is the one the spec records", how_page_holds_the_section_9_number)


def every_page_links_to_how_and_the_pitch_is_current():
    for path in ("/", "/results/eta", "/how"):
        _, html = get(path)
        assert 'href="/how"' in html, f"{path} has no link to /how"
    _, html = get("/")
    assert "does none of that" not in html, "the landing page still says the site does nothing"
    assert "70%" not in html, "the landing page still promises a 70% target"


check("every page links to /how, and the landing page no longer says the site does nothing",
      every_page_links_to_how_and_the_pitch_is_current)

shutil.rmtree(SCRATCH, ignore_errors=True)
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
