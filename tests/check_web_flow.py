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


def what_people_paste_is_read_as_the_handle():
    """Found by the audit of 2026-09-26: the quickest way to copy your handle
    is to copy your profile's address, and pasting it answered "There is
    nothing at this address". An @ in front, as chat apps write names, was
    refused as "not a Codeforces handle"."""
    for typed in ("https://codeforces.com/profile/tourist",
                  "http://codeforces.com/profile/tourist/",
                  "codeforces.com/profile/tourist",
                  "https://m1.codeforces.com/profile/tourist?locale=ru",
                  "@tourist",
                  "  tourist  "):
        response = client.post("/", data={"handle": typed})
        assert response.status_code == 302, (typed, response.status_code)
        assert response.headers["Location"].endswith("/results/tourist"), (typed, response.headers["Location"])


def a_link_that_is_not_a_profile_is_left_alone():
    """Only a profile address is read as a handle. Anything else goes through
    as typed and is refused the usual way -- guessing would be worse."""
    response = client.post("/", data={"handle": "https://codeforces.com/contest/1234"})
    assert not response.headers.get("Location", "").endswith("/results/1234"), response.headers.get("Location")


def the_box_takes_a_whole_profile_address():
    """A browser cuts a paste to maxlength before anything is sent, so the
    server-side reading above is worthless if the box truncates first."""
    import re
    html = client.get("/").get_data(as_text=True)
    limit = int(re.search(r'name="handle"[^>]*maxlength="(\d+)"', html, re.S).group(1))
    longest = len("https://m1.codeforces.com/profile/") + 24
    assert limit >= longest, f"maxlength {limit} cuts a pasted profile address ({longest} characters)"


check("a pasted profile address, or @handle, is read as the handle", what_people_paste_is_read_as_the_handle)
check("the box takes a whole profile address", the_box_takes_a_whole_profile_address)
check("a link that is not a profile is not guessed at", a_link_that_is_not_a_profile_is_left_alone)


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
    # Its own address, written out: a refresh to the address in the bar
    # does not reload in Chromium when a redirect left a fragment there
    # (found 2026-09-28), and the visitor waits here for ever.
    assert f'; url=/progress/{job_id}">' in html, "the refresh relies on the address bar, fragment and all"
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
        db.finish_job(conn, job_id, error="Codeforces rejected the request: handle not found",
                      failure="rejected")
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
    assert "Being judged" in html, "an unjudged submission should say it is being judged"
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
    # A screen reader is told when the sync's state changes, and only then:
    # a live region round the line itself would read the countdown out
    # every second (review of 2026-09-28).
    assert '<p class="sr-only" id="sync-announce" role="status"></p>' in html, "nothing announces the sync"
    assert "line.innerHTML = html;\n              tell();" in html, "the new line is never announced"
    assert "if (!announce || state === said) return;" in html, "the line is announced on every poll"
    assert 'role="status"' not in html.split('id="sync-status"', 1)[1].split("</p>", 1)[0], \
        "the counting line itself is a live region"

    conn = db.connect()
    try:
        active = db.get_active_job(conn, "sync", "epsilon")
    finally:
        conn.close()
    assert active is not None, "nothing was queued to refresh it"


check("stale data is shown at once, with a line saying it is being refreshed", stale_data_is_shown_and_resynced_behind_a_live_line)


def the_browser_is_asked_to_remember_the_handle():
    """A returning visitor should not have to type their own name again. It
    is kept on the device, not here: the visitor cookie is counted (ADR 0017)
    and /privacy promises it is used for nothing else."""
    synced("zeta", [api_sub(9)])
    _, results = get("/results/zeta")
    assert 'localStorage.setItem("nextcf_handle"' in results, "the page remembers nothing"
    assert '"zeta"' in results, "it remembered somebody else"
    # Only a handle typed into the box. Until 2026-09-28 any results page
    # saved its handle, so "Continue as" named whoever was looked up last.
    # The form leaves what was typed in sessionStorage; the page saves only
    # when its handle is in that note, and takes the note either way.
    before, found, after = results.partition('var typed = sessionStorage.getItem("nextcf_typed");')
    assert found, "the page does not look for what was typed"
    assert 'localStorage.setItem("nextcf_handle"' not in before, "the page saves every handle it shows, typed or not"
    assert results.count('localStorage.setItem("nextcf_handle"') == 1, "a second save, outside the test below"
    test = 'if (typed.toLowerCase().indexOf(handle.toLowerCase()) !== -1) {\n          localStorage.setItem("nextcf_handle", handle);'
    assert test in after, "the save does not depend on the handle being what was typed"
    assert after.index('sessionStorage.removeItem("nextcf_typed")') < after.index(test), \
        "the note is kept when it does not match, for the next page this tab opens"

    _, landing = get("/")
    assert 'localStorage.getItem("nextcf_handle")' in landing, "the form never reads it back"
    assert 'addEventListener("submit"' in landing and 'sessionStorage.setItem("nextcf_typed", input.value)' in landing, \
        "the form leaves no note of what was typed"
    assert "Use another handle" in landing, "no way to change what was remembered"

    _, privacy = get("/privacy")
    # A phrase that does not straddle a line break in the template: the page
    # is wrapped at the measure, and matching across a newline is a check that
    # fails when somebody reflows a paragraph.
    assert "never sent here" in privacy, "/privacy does not mention the thing the browser keeps"


check("the browser is asked to remember the handle, and /privacy says so", the_browser_is_asked_to_remember_the_handle)


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
    fw = web.FORWARD
    for value in (fw["baseline"], fw["model"]):
        assert f"{value:.4f}" in html, f"the forward test's {value:.4f} is not on /how"
    cells = html.count('<td class="num">')
    # Two tables of strata with a total each, and one calibration table of
    # three columns: what the model said, 2026, and after it shipped.
    expected = (2 * len(ev["strata"]) + 2) + (2 * len(fw["strata"]) + 2) + 3 * len(ev["calibration"])
    assert cells == expected, f"{cells} number cells on /how, expected {expected}"
    spec = Path("docs/spec.md").read_text(encoding="utf-8")
    section9 = spec[spec.index("## 9. How we will know it worked"):spec.index("## 10.")]
    for band, base, ours in ev["strata"]:
        assert f"{ours:.4f}" in section9 and f"{base:.4f}" in section9, \
            f"{band}: web.EVALUATION says {base:.4f} / {ours:.4f}, spec section 9 does not"
    assert f"**{ev['model']:.4f}**" in section9, "spec section 9's headline is not web.EVALUATION's"
    # The second measurement, the forward test (ADR 0013): the same rule.
    for band, base, ours in fw["strata"]:
        assert f"{ours:.4f}" in section9 and f"{base:.4f}" in section9, \
            f"{band}: web.FORWARD says {base:.4f} / {ours:.4f}, spec section 9 does not"
    assert f"**{fw['model']:.4f}**" in section9, "spec section 9's forward headline is not web.FORWARD's"
    assert fw["attempts"] in section9 and fw["attempts"] in html, "the forward test's size differs between page and spec"
    # The two calibration tables share one column of ranges, so the ranges
    # have to be the same ten once rounded as the page rounds them.
    assert [round(s) for s, _ in ev["calibration"]] == [round(s) for s, _ in fw["calibration"]], \
        "the two calibration tables no longer have the same ranges"
    # Each row of the page's table: what was said, 2026, after it shipped --
    # the third column is FORWARD's, not EVALUATION's printed twice.
    flat = " ".join(html.split())
    for (said, happened), (_, later) in zip(ev["calibration"], fw["calibration"]):
        row = " ".join(f'<td class="num">{value:.0f}%</td>' for value in (said, happened, later))
        assert row in flat, f"no calibration row reads {said:.0f}% / {happened:.0f}% / {later:.0f}%"
    # What the page says in words about the middle of the range comes from
    # the two rows either side of 50%: check the words against the rows.
    for name, rows, claimed in (("2026", ev["calibration"], 52), ("after it shipped", fw["calibration"], 54)):
        (below_said, below), (above_said, above) = rows[4], rows[5]
        at_half = below + (above - below) * (50 - below_said) / (above_said - below_said)
        assert abs(at_half - claimed) < 1, f"{name}: called 50%, happened {at_half:.1f}%, the page says {claimed}%"
        assert f"about {claimed}%" in " ".join(html.split()), f"/how does not say about {claimed}%"


check("/how shows section 9's number, and it is the one the spec records", how_page_holds_the_section_9_number)


def the_tables_on_how_fit_a_phone():
    """Found 2026-10-03, when the calibration table gained a third column:
    64 pixels between columns and a header of sixteen characters made it 428
    pixels wide on a 343-pixel page, and the whole page scrolled sideways.
    Headers do not wrap, so they are kept short; the columns close up on a
    phone; and the table can never be wider than the page."""
    import re
    _, html = get("/how")
    headers = re.findall(r'<th class="num">([^<]+)</th>', html)
    long = [h for h in headers if len(h) > 12]
    assert headers and not long, f"column headers too long for a phone: {long}"
    css = Path("static/style.css").read_text(encoding="utf-8")
    compact = re.search(r"\.prose \.table-wrap\.compact \{([^}]*)\}", css).group(1)
    assert "max-width: 100%" in re.sub(r"/\*.*?\*/", "", compact, flags=re.S),         "the compact table can be wider than the page"
    narrow = css.split("@media (max-width: 640px)", 1)[1]
    rule = re.search(r"\.prose \.compact th,\s*\.prose \.compact td \{([^}]*)\}", narrow)
    assert rule and "padding-right: var(--s3)" in rule.group(1), "the columns do not close up on a phone"


check("the tables on /how fit a phone", the_tables_on_how_fit_a_phone)


def every_page_links_to_how_and_the_pitch_is_current():
    for path in ("/", "/results/eta", "/how"):
        _, html = get(path)
        assert 'href="/how"' in html, f"{path} has no link to /how"
    _, html = get("/")
    assert "does none of that" not in html, "the landing page still says the site does nothing"
    assert "70%" not in html, "the landing page still promises a 70% target"


check("every page links to /how, and the landing page no longer says the site does nothing",
      every_page_links_to_how_and_the_pitch_is_current)


# ------------------------------------------------------- the unusual states
# The audit of 2026-10-01 rendered every state a visitor can arrive in that
# is not the ordinary one. The large ones already had pages (check_errors,
# check_queue); these are the seven small things it found.

def junk_in_the_box_is_answered_at_the_box():
    """A space, another alphabet, a link that is not a profile: refused where
    it was typed, with the text still in the field to be fixed. Before, each
    went on to a results address, and a pasted contest link was answered
    "There is nothing at this address"."""
    import html as escaping
    for typed in ("a b c", "<script>alert(1)</script>", "x" * 40, "Привет",
                  "https://codeforces.com/contest/1234"):
        response = client.post("/", data={"handle": typed})
        page = response.get_data(as_text=True)
        assert response.status_code == 400 and "Location" not in response.headers, \
            (typed, response.status_code, response.headers.get("Location"))
        assert "That does not look like a Codeforces handle." in page, f"{typed!r}: not told why"
        assert f'value="{escaping.escape(typed)}"' in page, f"{typed!r}: what was typed is gone from the field"
        assert "<script>alert(1)</script>" not in page, "what was typed reached the page unescaped"
    # The shape only: a handle that could exist still goes to its page, where
    # Codeforces says whether it does.
    response = client.post("/", data={"handle": "nobody.has-this_handle"})
    assert response.status_code == 302, response.status_code


def one_is_singular_and_thousands_have_a_comma():
    synced("solo", [api_sub(9001, name="Only One", contest_id=9001)])
    _, html = get("/results/solo")
    assert "1 submission," in html and "1 submissions" not in html, "one submission is plural"
    synced("prolific", [api_sub(20000 + n, name=f"Problem {n}", contest_id=20000 + n) for n in range(1001)])
    _, html = get("/results/prolific")
    assert "1,001 submissions," in html, "a thousand and one has no comma"
    assert "most recent of 1,001." in html, "the table's own count has no comma"


def a_verdict_is_words():
    synced("judged", [api_sub(9101, name="Right", contest_id=9101),
                      api_sub(9102, name="Wrong", verdict="WRONG_ANSWER", contest_id=9102),
                      api_sub(9103, name="Slow", verdict="TIME_LIMIT_EXCEEDED", contest_id=9103),
                      api_sub(9104, name="Waiting", verdict=None, contest_id=9104)])
    _, html = get("/results/judged")
    for words in ("Accepted", "Wrong answer", "Time limit exceeded", "Being judged"):
        assert f">{words}</td>" in html, f"no verdict reads {words!r}"
    assert "WRONG_ANSWER" not in html and "TIME_LIMIT_EXCEEDED" not in html, "a verdict is still Codeforces's constant"
    # Green is for an accepted solve and nothing else.
    assert html.count("verdict-ok") == 1, "the accepted verdict lost its class, or another gained it"


def the_fold_under_the_topics_says_only_what_is_true():
    """With nothing solved it asked "why Solved adds up to more than 0", and
    with one solve under one tag it said the column adds to more than 1."""
    synced("tryer", [api_sub(9201, name="Tried", verdict="WRONG_ANSWER", contest_id=9201)])
    _, html = get("/results/tryer")
    assert '<details class="footnote">' not in html, "a fold explaining numbers when nothing is solved"

    synced("onetag", [api_sub(9211, name="One Tag", contest_id=9211)])
    _, html = get("/results/onetag")
    fold = html[html.index('<details class="footnote">'):]
    fold = " ".join(fold[:fold.index("</details>")].split())
    assert "<summary>About these numbers</summary>" in fold, "one solve under one tag is said to add to more than 1"
    assert "adds to more than" not in fold

    two = api_sub(9221, name="Two Tags", contest_id=9221)
    two["problem"]["tags"] = ["math", "dp"]
    untagged = api_sub(9222, name="No Tags", contest_id=9222)
    untagged["problem"]["tags"] = []
    also = api_sub(9223, name="Two More Tags", contest_id=9223)
    also["problem"]["tags"] = ["math", "greedy"]
    # Three solved; the column reads math 2, dp 1, greedy 1: four.
    synced("twotags", [two, also, untagged])
    _, html = get("/results/twotags")
    fold = html[html.index('<details class="footnote">'):]
    fold = " ".join(fold[:fold.index("</details>")].split())
    assert "<summary>Why Solved adds up to more than 3</summary>" in fold, fold[:200]
    assert "more than the 3 problems solved." in fold, fold[:300]
    assert "1 solved problem has no tags at all and appears in no row." in fold, fold[:400]


def a_history_with_nothing_in_it_says_so():
    # The section is drawn for the topics there are to choose, so there has
    # to be a problemset: two problems are enough.
    conn = db.connect()
    try:
        db.save_problemset(conn, [
            {"contestId": 30001, "index": "A", "name": "In The Pool", "rating": 1000, "tags": ["math"]},
            {"contestId": 30002, "index": "A", "name": "Also In The Pool", "rating": 1200, "tags": ["dp"]}])
    finally:
        conn.close()
    synced("blank", [])
    _, html = get("/results/blank")
    assert "0 submissions," in html
    assert "Nothing practised yet." in html and "What you have practised" not in html, \
        "an empty history is introduced as what was practised"
    assert "No submissions found for this handle." in html


def a_trailing_slash_is_the_same_address():
    for path in ("/how/", "/privacy/", "/results/gamma/"):
        response = client.get(path)
        assert response.status_code == 200, (path, response.status_code)


print("\nthe unusual states")
check("junk in the box is answered at the box", junk_in_the_box_is_answered_at_the_box)
check("one is singular, and thousands have a comma", one_is_singular_and_thousands_have_a_comma)
check("a verdict is words", a_verdict_is_words)
check("the fold under the topics says only what is true", the_fold_under_the_topics_says_only_what_is_true)
check("a history with nothing in it says so", a_history_with_nothing_in_it_says_so)
check("a trailing slash is the same address", a_trailing_slash_is_the_same_address)

shutil.rmtree(SCRATCH, ignore_errors=True)
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
