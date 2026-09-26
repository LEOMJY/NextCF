"""Check error handling and logging -- ADR 0022.

No network: a temporary database (NEXTCF_DB), sync.start_sync replaced with a
version that writes a job row and starts no thread, and api_client.call
replaced where a sync is run for real.

The three that matter most:

  * A FAILURE ANSWERS WITH ITS CAUSE. A handle Codeforces refused is 404; a
    Codeforces that could not be reached, or a restart, is 503 with a
    Retry-After; a bug of ours is 500. The page reads the same for all of
    them. Until 2026-09-26 all of them were 200, and that is how a typo came
    to be counted as a visitor.
  * NOTHING BREAKS UNSTYLED. A mistyped URL, a GET to a button, an exception
    in a view -- each gets the site's own page, and an exception's detail
    goes to the log and never to the visitor.
  * NO HANDLE IN THE LOG. /privacy lists what this site keeps, and a log the
    host keeps is kept. Every line is searched for the handle it was about.
"""

import logging
import os
import shutil
import sys
import tempfile
import urllib.error
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="errors-"))

# Must be set before db is imported: db.py reads it at import time.
os.environ["NEXTCF_DB"] = str(SCRATCH / "test.db")
# Paths in this file are relative to the repository root, and the modules
# being checked live there, so go there first. The check then runs the same
# from any directory.
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))


class Captured(logging.Handler):
    """Keeps every line logged anywhere in the program, for reading back.

    Attached to the root logger BEFORE web is imported: Flask gives the app a
    handler of its own on first use only if nothing above it has one, and
    this is that something -- so a traceback lands here instead of on the
    terminal running the check.
    """

    def __init__(self):
        super().__init__(level=logging.INFO)
        self.lines = []

    def emit(self, record):
        self.lines.append(self.format(record))

    def text(self):
        return "\n".join(self.lines)


captured = Captured()
# The same format the site uses, so a traceback is included in a line the way
# it would be on the host.
captured.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
logging.getLogger().addHandler(captured)
logging.getLogger().setLevel(logging.INFO)

import api_client  # noqa: E402
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


# A view that throws, registered before the first request -- Flask refuses new
# routes once it has served one. It exists only in this process.
@web.app.route("/__check_errors_boom")
def boom():
    raise ZeroDivisionError("a secret the visitor must not see")


@web.app.route("/__check_errors_boom/<handle>")
def boom_with_a_handle(handle):
    raise ZeroDivisionError("a page with a handle in its address, throwing")


db.init_db()
client = web.app.test_client()


def a_failed_job(handle, failure, error="Codeforces rejected the request: no such user"):
    conn = db.connect()
    try:
        job_id = db.create_job(conn, "sync", handle)
        db.claim_job(conn, job_id)
        db.finish_job(conn, job_id, error=error, failure=failure)
        return job_id
    finally:
        conn.close()


def styled(html):
    """The site's own page, not Flask's white one."""
    return "style.css" in html and "That did not work" in html


# ------------------------------------------------------------ status by cause
def a_rejected_handle_is_404():
    job_id = a_failed_job("err_rejected", "rejected")
    response = client.get("/results/err_rejected")
    assert response.status_code == 404, response.status_code
    html = response.get_data(as_text=True)
    assert styled(html) and "no such user" in html, "the reason is not on the page"
    assert "Try err_rejected again" in html, "no way past the memory"
    assert "Retry-After" not in response.headers, "a 404 does not ask to be retried"
    # The job's own page is about the job, which exists.
    assert client.get(f"/progress/{job_id}").status_code == 200


def an_unreachable_codeforces_is_503_with_retry_after():
    job_id = a_failed_job("err_unreachable", "unreachable",
                          error="Could not reach Codeforces: timed out")
    response = client.get("/results/err_unreachable")
    assert response.status_code == 503, response.status_code
    retry = int(response.headers.get("Retry-After", "0"))
    # Just failed, so nearly the whole memory is left -- and never more.
    assert web.FAILURE_REMEMBERED_SECONDS - 60 < retry <= web.FAILURE_REMEMBERED_SECONDS, retry
    assert client.get(f"/progress/{job_id}").status_code == 200


def retry_after_counts_down_with_the_memory():
    """Asking again before the memory lapses gets this same page back, so the
    header must not promise a real retry sooner than that."""
    job_id = a_failed_job("err_older", "unreachable", error="Could not reach Codeforces: timed out")
    conn = db.connect()
    try:
        with conn:
            conn.execute("UPDATE jobs SET finished_at = ? WHERE id = ?",
                         (db.utc_ago(web.FAILURE_REMEMBERED_SECONDS - 100), job_id))
    finally:
        conn.close()
    retry = int(client.get("/results/err_older").headers.get("Retry-After", "0"))
    assert 90 <= retry <= 101, f"Retry-After {retry} with about 100 seconds of memory left"


def an_interrupted_sync_is_503():
    a_failed_job("err_interrupted", "interrupted",
                 error="The server restarted before this job finished.")
    response = client.get("/results/err_interrupted")
    assert response.status_code == 503, response.status_code
    assert "Retry-After" in response.headers


def a_bug_of_ours_is_500():
    a_failed_job("err_internal", "internal", error="Something went wrong on our side.")
    assert client.get("/results/err_internal").status_code == 500


def a_failure_from_before_the_cause_was_kept_is_500():
    """A failed row with no cause makes no claim about the handle."""
    job_id = a_failed_job("err_legacy", "rejected")
    conn = db.connect()
    try:
        with conn:
            conn.execute("UPDATE jobs SET failure = NULL WHERE id = ?", (job_id,))
    finally:
        conn.close()
    assert client.get("/results/err_legacy").status_code == 500


def a_failure_page_is_not_a_visit():
    """Not 200, so not counted -- and never under the handle that failed."""
    a_failed_job("err_not_counted", "rejected")
    before = db.visit_counts(db.connect())["visits"]
    client.get("/results/err_not_counted")
    after = db.visit_counts(db.connect())
    assert after["visits"] == before, "a failure page was counted as a visit"


# ---------------------------------------------------------------- error pages
def an_unknown_address_is_the_sites_own_404():
    response = client.get("/no/such/page")
    assert response.status_code == 404, response.status_code
    assert styled(response.get_data(as_text=True)), "Flask's white page"


def a_get_to_a_button_is_the_sites_own_405():
    response = client.get("/results/somebody/sync")
    assert response.status_code == 405, response.status_code
    assert styled(response.get_data(as_text=True)), "Flask's white page"
    # A 405 must say what IS allowed; restyling it must not drop that.
    assert "POST" in response.headers.get("Allow", ""), response.headers.get("Allow")


def an_exception_is_the_sites_own_500_with_nothing_of_it_shown():
    captured.lines.clear()
    response = client.get("/__check_errors_boom")
    html = response.get_data(as_text=True)
    assert response.status_code == 500, response.status_code
    assert styled(html), "Flask's white page"
    assert "Something went wrong on our side" in html, "not the site's own sentence"
    for leak in ("ZeroDivisionError", "a secret the visitor must not see", "Traceback"):
        assert leak not in html, f"{leak} reached the visitor"
    # ...and all of it reached the log, where it belongs.
    assert "ZeroDivisionError" in captured.text(), "the exception was not logged"
    assert "Traceback" in captured.text(), "logged without its traceback"


# -------------------------------------------------------------------- logging
def synced(handle):
    conn = db.connect()
    try:
        db.save_sync(conn, handle, 1500, [{
            "id": 424242,
            "problem": {"contestId": 1234, "index": "A", "name": "Watermelon",
                        "tags": ["math"], "rating": 800},
            "creationTimeSeconds": 1600000000,
            "author": {"participantType": "PRACTICE"},
            "verdict": "OK",
        }])
    finally:
        conn.close()


def every_page_is_logged_by_route_never_by_handle():
    synced("Loggable_Person")
    captured.lines.clear()
    client.get("/results/Loggable_Person")
    client.get("/no/Loggable_Person/here")      # no route: the path is not logged either
    text = captured.text()
    assert "GET /results/<handle> 200" in text, text
    assert "GET (no route) 404" in text, text
    assert "loggable_person" not in text.lower(), f"the handle reached the log:\n{text}"


def an_exception_is_logged_by_route_never_by_handle():
    """Flask's own line for an exception reads "Exception on <path>", and the
    path of a results page is a handle."""
    captured.lines.clear()
    client.get("/__check_errors_boom/Crashing_Person")
    text = captured.text()
    assert "ZeroDivisionError" in text and "Traceback" in text, text
    assert "/__check_errors_boom/<handle>" in text, f"the route is not named:\n{text}"
    assert "crashing_person" not in text.lower(), f"the handle reached the log:\n{text}"


def static_files_are_not_logged():
    captured.lines.clear()
    client.get("/static/style.css")
    assert "/static" not in captured.text(), captured.text()


class FakeCodeforces:
    """api_client.call for one sync: answers, or raises `fail`."""

    def __init__(self, fail=None):
        self.fail = fail

    def __call__(self, method, **params):
        if self.fail is not None:
            raise self.fail
        if method == "user.status":
            return [{"id": 77, "creationTimeSeconds": 1600000000, "verdict": "OK",
                     "author": {"participantType": "PRACTICE"},
                     "problem": {"contestId": 1, "index": "A", "name": "W", "rating": 800,
                                 "tags": ["math"]}}]
        return []


def run_a_sync(handle, fake):
    real = api_client.call
    api_client.call = fake
    conn = db.connect()
    try:
        job_id = db.create_job(conn, "sync", handle)
        captured.lines.clear()
        sync.run_sync(handle, job_id)
        return job_id, db.get_job(conn, job_id), captured.text()
    finally:
        conn.close()
        api_client.call = real


def a_sync_is_logged_by_job_never_by_handle():
    job_id, job, text = run_a_sync("Sync_Log_Person", FakeCodeforces())
    assert job["state"] == "done", job["state"]
    assert f"job {job_id}: started" in text and f"job {job_id}: done" in text, text
    assert "sync_log_person" not in text.lower(), f"the handle reached the log:\n{text}"


def a_rejected_sync_keeps_codeforces_words_out_of_the_log():
    """Codeforces' refusal names the handle. It belongs on the visitor's page
    (the jobs row), not in the log."""
    refusal = RuntimeError("handle: User with handle Refused_Person not found")
    job_id, job, text = run_a_sync("Refused_Person", FakeCodeforces(refusal))
    assert job["failure"] == "rejected", job["failure"]
    assert "Refused_Person" in job["error"], "the visitor lost the reason"
    assert f"job {job_id}: rejected" in text, text
    assert "refused_person" not in text.lower(), f"the handle reached the log:\n{text}"


def a_bug_in_a_sync_is_logged_with_its_traceback():
    job_id, job, text = run_a_sync("buggy_sync", FakeCodeforces(KeyError("result")))
    assert job["failure"] == "internal", job["failure"]
    assert job["error"] == "Something went wrong on our side.", job["error"]
    assert "Traceback" in text and "KeyError" in text, text


def a_retry_warning_names_the_method_not_the_handle():
    """api_client's retry line: the parameters are where the handle is."""
    real_once, real_sleep = api_client._call_once, api_client.time.sleep
    attempts = []

    def flaky(method, params):
        attempts.append(method)
        if len(attempts) == 1:
            raise urllib.error.URLError("connection reset")
        return []

    api_client._call_once = flaky
    api_client.time.sleep = lambda seconds: None
    captured.lines.clear()
    try:
        api_client.call("user.status", handle="Retried_Person")
    finally:
        api_client._call_once, api_client.time.sleep = real_once, real_sleep
    text = captured.text()
    assert "user.status" in text and "retrying" in text, text
    assert "retried_person" not in text.lower(), f"the handle reached the log:\n{text}"


print("a failure answers with its cause")
check("rejected by Codeforces: 404, and the job's page stays 200", a_rejected_handle_is_404)
check("Codeforces unreachable: 503, with Retry-After", an_unreachable_codeforces_is_503_with_retry_after)
check("Retry-After counts down with the memory", retry_after_counts_down_with_the_memory)
check("interrupted by a restart: 503", an_interrupted_sync_is_503)
check("a bug of ours: 500", a_bug_of_ours_is_500)
check("a failure with no recorded cause: 500", a_failure_from_before_the_cause_was_kept_is_500)
check("a failure page is not a visit", a_failure_page_is_not_a_visit)

print("\nnothing breaks unstyled")
check("an unknown address: the site's own 404", an_unknown_address_is_the_sites_own_404)
check("a GET to a button: the site's own 405, still saying Allow", a_get_to_a_button_is_the_sites_own_405)
check("an exception: the site's own 500, detail in the log only",
      an_exception_is_the_sites_own_500_with_nothing_of_it_shown)

print("\nthe log")
check("pages are logged by route, never by handle", every_page_is_logged_by_route_never_by_handle)
check("an exception is logged by route, never by handle", an_exception_is_logged_by_route_never_by_handle)
check("static files are not logged", static_files_are_not_logged)
check("a sync is logged by job id, never by handle", a_sync_is_logged_by_job_never_by_handle)
check("a refusal's words go to the page, not the log", a_rejected_sync_keeps_codeforces_words_out_of_the_log)
check("a bug in a sync is logged with its traceback", a_bug_in_a_sync_is_logged_with_its_traceback)
check("a retry warning names the method, not the handle", a_retry_warning_names_the_method_not_the_handle)

print(f"\n{passed} passed, {failed} failed")
shutil.rmtree(SCRATCH, ignore_errors=True)
sys.exit(1 if failed else 0)
