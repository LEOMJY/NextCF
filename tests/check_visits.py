"""Check of visit counting and the cookie behind it -- ADR 0017, spec 9.

Nothing here touches the network: a temporary database (NEXTCF_DB), and
sync.start_sync replaced with a version that writes a job row and starts no
thread, the same trick check_web_flow.py uses.

The two that matter most:

  * THE PROGRESS PAGE IS NOT COUNTED. It reloads itself every two seconds, so
    counting it would turn one visitor waiting forty seconds into twenty
    people. Section 9's claim is a count of people, and there is no way to
    tell afterwards that a number was inflated by a poll.
  * NOTHING ELSE IS STORED. The privacy page promises four things and no IP
    address; the table is checked column by column, because that promise is
    the kind that erodes one convenient column at a time.
"""

import os
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="visits-"))

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

db.init_db()


def rows():
    conn = db.connect()
    try:
        return conn.execute("SELECT * FROM visits ORDER BY id").fetchall()
    finally:
        conn.close()


def clear():
    conn = db.connect()
    try:
        with conn:
            conn.execute("DELETE FROM visits")
    finally:
        conn.close()


def synced(handle, seconds=1600000000):
    """A user with a finished sync, so /results/<handle> renders instead of
    redirecting to a progress page."""
    conn = db.connect()
    try:
        db.save_sync(conn, handle, 1500, [{
            "id": abs(hash(handle)) % 10**8,
            "problem": {"contestId": 1234, "index": "A", "name": "Watermelon",
                        "tags": ["math"], "rating": 800},
            "creationTimeSeconds": seconds,
            "author": {"participantType": "PRACTICE"},
            "verdict": "OK",
        }])
    finally:
        conn.close()


def fresh_client():
    """A browser that has never been here: its own cookie jar."""
    return web.app.test_client()


def cookie_header(response):
    """The Set-Cookie line for the visitor cookie, or None."""
    for name, value in response.headers:
        if name == "Set-Cookie" and value.startswith(web.VISITOR_COOKIE + "="):
            return value
    return None


def cookie_value(response):
    header = cookie_header(response)
    assert header is not None, "no visitor cookie was set"
    return header.split("=", 1)[1].split(";", 1)[0]


# ------------------------------------------------------------ what is counted
def a_first_visit_is_recorded_with_a_new_cookie():
    clear()
    client = fresh_client()
    response = client.get("/")
    assert response.status_code == 200, response.status_code

    written = rows()
    assert len(written) == 1, f"{len(written)} rows for one visit"
    assert written[0]["path"] == "/", written[0]["path"]
    assert written[0]["handle"] is None, written[0]["handle"]
    assert written[0]["visitor_id"] == cookie_value(response), "row and cookie disagree"
    assert web.VISITOR_ID_PATTERN.match(written[0]["visitor_id"]), written[0]["visitor_id"]


def the_same_browser_is_one_person():
    clear()
    client = fresh_client()
    first = client.get("/")
    # The test client keeps cookies, so this is the same browser coming back.
    second = client.get("/how")

    assert cookie_header(second) is None, "a known browser was given a second id"
    written = rows()
    assert len(written) == 2, f"{len(written)} rows for two visits"
    assert written[0]["visitor_id"] == written[1]["visitor_id"] == cookie_value(first)


def a_cookie_that_is_not_ours_is_replaced():
    """The value comes from the browser, so it comes from outside."""
    clear()
    client = fresh_client()
    client.set_cookie(web.VISITOR_COOKIE, "'; DROP TABLE visits; --", domain="localhost")
    response = client.get("/")

    written = rows()
    assert len(written) == 1, f"{len(written)} rows"
    assert written[0]["visitor_id"] != "'; DROP TABLE visits; --", "kept a junk id"
    assert web.VISITOR_ID_PATTERN.match(written[0]["visitor_id"]), written[0]["visitor_id"]
    assert cookie_header(response) is not None, "no replacement cookie was sent"


def the_results_page_records_the_handle():
    clear()
    synced("tourist")
    client = fresh_client()
    response = client.get("/results/tourist")
    assert response.status_code == 200, response.status_code

    written = rows()
    assert len(written) == 1, f"{len(written)} rows"
    assert written[0]["handle"] == "tourist", written[0]["handle"]
    assert written[0]["path"] == "/results/tourist", written[0]["path"]


def how_and_privacy_are_recorded():
    clear()
    client = fresh_client()
    client.get("/how")
    client.get("/privacy")
    assert [row["path"] for row in rows()] == ["/how", "/privacy"], [r["path"] for r in rows()]


# -------------------------------------------------------- what is NOT counted
def the_progress_page_is_not_counted():
    """It reloads itself every two seconds -- see templates/progress.html."""
    clear()
    job_id = fake_start_sync("somebody_new")
    client = fresh_client()

    for _ in range(20):                      # forty seconds of waiting
        response = client.get(f"/progress/{job_id}")
        assert response.status_code == 200, response.status_code

    assert rows() == [], f"{len(rows())} rows written by a polling page"


def a_redirect_is_not_counted():
    """A stale handle redirects to a sync; the visit counts when the page
    finally renders, not twice."""
    clear()
    client = fresh_client()
    response = client.get("/results/never_synced_before")
    assert response.status_code == 302, response.status_code
    assert rows() == [], f"{len(rows())} rows for a redirect"


def the_form_post_is_not_counted():
    clear()
    client = fresh_client()
    response = client.post("/", data={"handle": "tourist"})
    assert response.status_code == 302, response.status_code
    assert rows() == [], f"{len(rows())} rows for a POST"


def an_error_page_is_not_counted():
    clear()
    client = fresh_client()
    response = client.get("/results/!!!")
    assert response.status_code == 404, response.status_code
    assert rows() == [], f"{len(rows())} rows for a 404"


# ------------------------------------------------------------------ the cookie
def the_cookie_is_locked_down():
    clear()
    header = cookie_header(fresh_client().get("/"))
    assert "HttpOnly" in header, header
    assert "SameSite=Lax" in header, header
    assert f"Max-Age={web.VISITOR_COOKIE_DAYS * 24 * 60 * 60}" in header, header
    # Locally the site is http, and a Secure cookie would never be stored.
    assert "Secure" not in header, header


def the_cookie_is_secure_behind_the_proxy():
    """Render terminates TLS and forwards plain HTTP, so the header is what
    tells the truth about the visitor's connection."""
    clear()
    header = cookie_header(fresh_client().get("/", headers={"X-Forwarded-Proto": "https"}))
    assert "Secure" in header, header


# --------------------------------------------------------- what is not stored
def the_table_holds_only_what_privacy_promises():
    conn = db.connect()
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(visits)")}
    finally:
        conn.close()
    assert columns == {"id", "visitor_id", "handle", "path", "visited_at"}, columns


def no_request_details_are_stored():
    """Nothing about the browser reaches the database, even when it is sent."""
    clear()
    client = fresh_client()
    client.get(
        "/",
        headers={
            "User-Agent": "SomeBrowser/9.9 (a very distinctive string)",
            "Referer": "https://codeforces.com/blog/entry/12345",
            "X-Forwarded-For": "203.0.113.7",
        },
    )
    stored = " ".join(str(value) for value in tuple(rows()[0]))
    for leak in ("SomeBrowser", "codeforces.com/blog", "203.0.113.7"):
        assert leak not in stored, f"{leak} reached the database: {stored}"


def a_failure_to_record_does_not_break_the_page():
    """The page is worth more than the count of it."""
    clear()
    real = db.record_visit

    def broken(*args, **kwargs):
        raise sqlite3.OperationalError("no such table: visits")

    db.record_visit = broken
    try:
        response = fresh_client().get("/")
        assert response.status_code == 200, response.status_code
        assert b"NextCF" in response.data, "the page did not render"
    finally:
        db.record_visit = real


# --------------------------------------------------------------- the counting
def on_a_day(visitor_id, handle, day):
    conn = db.connect()
    try:
        with conn:
            conn.execute(
                "INSERT INTO visits (visitor_id, handle, path, visited_at) VALUES (?, ?, '/', ?)",
                (visitor_id, handle, f"{day}T12:00:00Z"),
            )
    finally:
        conn.close()


def counted(**kwargs):
    conn = db.connect()
    try:
        return db.visit_counts(conn, **kwargs)
    finally:
        conn.close()


def two_visits_in_one_day_are_one_person_who_has_not_returned():
    clear()
    on_a_day("aaaaaaaaaaaaaaaaaaaa", None, "2026-11-20")
    on_a_day("aaaaaaaaaaaaaaaaaaaa", "tourist", "2026-11-20")
    counts = counted()
    assert counts["people"] == 1, counts
    assert counts["returned"] == 0, counts
    assert counts["used"] == 1, counts
    assert counts["visits"] == 2, counts


def a_second_day_is_a_return():
    clear()
    on_a_day("aaaaaaaaaaaaaaaaaaaa", None, "2026-11-20")
    on_a_day("aaaaaaaaaaaaaaaaaaaa", None, "2026-11-21")
    on_a_day("bbbbbbbbbbbbbbbbbbbb", None, "2026-11-21")
    counts = counted()
    assert counts["people"] == 2, counts
    assert counts["returned"] == 1, counts


def handles_are_counted_separately_from_cookies():
    """The second measure, for the day cookies are refused -- and the one that
    under-counts rather than over-counts."""
    clear()
    on_a_day(None, "tourist", "2026-11-20")
    on_a_day(None, "tourist", "2026-11-21")
    on_a_day(None, "Tourist", "2026-11-22")      # COLLATE NOCASE: one person
    on_a_day(None, "somebody", "2026-11-22")
    counts = counted()
    assert counts["people"] == 0, counts
    assert counts["without_cookie"] == 4, counts
    assert counts["handles"] == 2, counts
    assert counts["handles_returned"] == 1, counts


def the_author_is_excluded_by_handle_and_by_browser():
    clear()
    on_a_day("aaaaaaaaaaaaaaaaaaaa", "a_stranger", "2026-11-20")
    on_a_day("tttttttttttttttttttt", "the_author", "2026-11-20")   # by handle
    on_a_day("aaaaaaaaaaaaaaaaaaaa", None, "2026-11-21")
    on_a_day("dddddddddddddddddddd", None, "2026-11-21")           # by browser

    counts = counted(exclude_handles=("the_author",), exclude_visitors=("dddddddddddddddddddd",))
    assert counts["people"] == 1, counts
    assert counts["returned"] == 1, counts
    assert counts["handles"] == 1, counts
    assert counts["visits"] == 2, counts


def excluding_a_browser_excludes_everything_it_did():
    """Not only its anonymous visits: if that browser looked a handle up, the
    handle counts are wrong too unless the whole row goes."""
    clear()
    on_a_day("tttttttttttttttttttt", "the_author", "2026-11-20")
    counts = counted(exclude_visitors=("tttttttttttttttttttt",))
    assert counts["visits"] == 0, counts
    assert counts["handles"] == 0, counts


# ------------------------------------------------------- the page and the code
def the_privacy_page_describes_the_cookie_that_is_actually_set():
    """A promise on a page is only worth what the code does. Both numbers on
    /privacy come from web.py's constants, and this fails if they stop
    matching what the browser is really sent."""
    clear()
    client = fresh_client()
    header = cookie_header(client.get("/"))
    page = client.get("/privacy").get_data(as_text=True)

    assert web.VISITOR_COOKIE in page, "the page does not name the cookie"
    assert f"{web.VISITOR_COOKIE_DAYS} days" in page, "the page does not give the cookie's life"
    assert f"Max-Age={web.VISITOR_COOKIE_DAYS * 24 * 60 * 60}" in header, header
    for promise in ("No IP address", "no referrer"):
        assert promise in page, f"the page stopped promising: {promise}"


print("what is counted")
check("a first visit is recorded, with a new cookie", a_first_visit_is_recorded_with_a_new_cookie)
check("the same browser is one person", the_same_browser_is_one_person)
check("a cookie that is not ours is replaced", a_cookie_that_is_not_ours_is_replaced)
check("the results page records the handle", the_results_page_records_the_handle)
check("/how and /privacy are recorded", how_and_privacy_are_recorded)

print("\nwhat is not counted")
check("the polling progress page is not counted", the_progress_page_is_not_counted)
check("a redirect is not counted", a_redirect_is_not_counted)
check("the form POST is not counted", the_form_post_is_not_counted)
check("a 404 is not counted", an_error_page_is_not_counted)

print("\nthe cookie")
check("HttpOnly, SameSite=Lax, 180 days, not Secure over http", the_cookie_is_locked_down)
check("Secure when the proxy says https", the_cookie_is_secure_behind_the_proxy)

print("\nwhat is never stored")
check("the table holds only what /privacy promises", the_table_holds_only_what_privacy_promises)
check("no IP, user agent or referrer reaches the database", no_request_details_are_stored)
check("a failure to record does not break the page", a_failure_to_record_does_not_break_the_page)

print("\nthe counting")
check("two visits in one day: one person, no return", two_visits_in_one_day_are_one_person_who_has_not_returned)
check("a second day is a return", a_second_day_is_a_return)
check("handles are counted separately from cookies", handles_are_counted_separately_from_cookies)
check("the author is excluded by handle and by browser", the_author_is_excluded_by_handle_and_by_browser)
check("excluding a browser excludes everything it did", excluding_a_browser_excludes_everything_it_did)

print("\nthe page and the code")
check("/privacy describes the cookie that is actually set", the_privacy_page_describes_the_cookie_that_is_actually_set)

print(f"\n{passed} passed, {failed} failed")
shutil.rmtree(SCRATCH, ignore_errors=True)
sys.exit(1 if failed else 0)
