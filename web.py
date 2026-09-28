"""NextCF web app.

Every page reads from the database, and no request waits on Codeforces. Asking
for a handle starts a background sync (sync.py) and sends the visitor to a
progress page, which polls the jobs table until the work is done.

    GET  /                   the pitch, and the handle input
    POST /                   read the field, send them to /results/<handle>
    GET  /results/<handle>   five recommendations, the topic breakdown, and
                             the submissions table
    GET  /progress/<job>     a sync in flight, reported honestly
    GET  /how                what the model knows, and section 9's number
    GET  /privacy            what is read, what is kept, how to have it gone

The recommendations come from the topic model (ADR 0014) when
topic_model.json is present, and from the rating-only baseline when it is not;
the page says which. Both draw on the problemset this program fetches when it
starts (ADR 0010).

Every page except the progress page also records that somebody opened it, so
that section 9's second criterion can be measured at all -- see
record_visit() below and ADR 0017.

When something fails, the status code says why (ADR 0022): a handle
Codeforces refused is 404, Codeforces unreachable or a restart is 503, a bug
here is 500 -- always on the site's own error page. Every request is logged
by its route's pattern, never its path, so no handle reaches the log.

Usage:
    .venv\\Scripts\\python.exe web.py
    then open http://127.0.0.1:5000
"""

import datetime
import logging
import os
import re
import secrets
import sqlite3
import time

from flask import Flask, g, jsonify, redirect, render_template, request, url_for
from werkzeug.exceptions import HTTPException

import api_client
import db
import model
import sync

# Flask has to find templates/ and static/, and it locates them relative to
# this file. __name__ is how it works out where this file is. That is the only
# reason this argument exists.
app = Flask(__name__)

# This module's log lines. The same logger Flask itself writes to when a page
# throws, because Flask names the app's logger after the module too -- so an
# unhandled exception and everything else this file says land together, in
# the format logs.py sets.
log = logging.getLogger(__name__)

# Codeforces handles are letters, digits, underscore, hyphen, and dots on some
# older accounts. This is a cheap filter to keep obvious junk out of an
# outgoing API request -- it is NOT authoritative. Codeforces decides what a
# real handle is, and says HTTP 400 when it is not one. If this pattern is ever
# wrong it will be wrong by rejecting something valid, so keep it permissive.
HANDLE_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,24}$")

# A Codeforces profile address, on the main site or a mirror (m1.codeforces.com
# and the like), with or without the scheme, a trailing slash or a query. The
# quickest way to copy your own handle is to copy this from the address bar.
PROFILE_ADDRESS = re.compile(
    r"^(?:https?://)?(?:[a-z0-9-]+\.)*codeforces\.com/profile/([^/?#\s]+)/?(?:[?#].*)?$",
    re.IGNORECASE,
)


def handle_from_input(typed):
    """What somebody typed into the handle box, read the way they meant it.

    Found by the audit of 2026-09-26: a pasted profile address answered
    "There is nothing at this address", and "@tourist" -- the way chat apps
    write a name -- was refused. Both are unambiguous, so both are read as
    the handle. Anything else is passed through as typed, including a
    codeforces.com address that is not a profile: guessing a handle out of a
    contest link would be worse than saying it is not one.
    """
    text = typed.strip()
    match = PROFILE_ADDRESS.match(text)
    if match:
        return match.group(1)
    return text.removeprefix("@")

# How long a stored history counts as fresh. Since ADR 0018, opening a results
# page older than this shows what is stored AND re-syncs behind it, rather
# than making the visitor watch a queue first.
#
# The trade: too short and every visit costs a fetch and a wait; too long and
# somebody who just solved a problem is shown a page saying they did not. Ten
# minutes is long enough that reloading never re-fetches, and short enough that
# coming back after a contest does. Shortening it would not make a refresh
# cheaper: a sync is one request for the whole history either way, and
# fetching only the newest submissions was dropped on 2026-09-13 because it
# saves no request and misses verdicts that change after they were stored.
FRESH_FOR_SECONDS = 600

# How long a failed sync is believed before it is attempted again. Measured on
# 2026-09-24 and it was the worst friction on the site: a mistyped handle cost
# four seconds and two API requests, and reloading the page cost them again,
# for ever. A handle that does not exist will not start existing in the next
# ten minutes; a handle that failed because Codeforces was down might, which is
# why the page that says so carries a button that ignores this.
FAILURE_REMEMBERED_SECONDS = 600

# The status code a remembered failure is answered with, by its cause (ADR
# 0022). The page is the same for all four -- the reason in words, and a
# button to try again -- and the code is what tells everything that is not a
# person what happened: a crawler that should not index a typo as a page, a
# browser deciding what to cache, a log that is searched for 5xx.
#
#   rejected     404  the handle's page does not exist, as far as anybody
#                     can tell -- Codeforces says so
#   unreachable  503  temporary, and not the handle's fault; Retry-After says
#                     when asking again will really ask again
#   interrupted  503  the same: this server restarted, and the handle may be
#                     perfectly fine
#   internal     500  a bug here
#
# /progress/<job> stays 200 for all of them. That page is about a job, and
# the job exists; it is the handle's page that may not.
FAILURE_STATUS = {
    "rejected": 404,
    "unreachable": 503,
    "interrupted": 503,
    "internal": 500,
}

# ------------------------------------------------------------------- visits
#
# ADR 0017. Section 9 needs 50 people who are not the author, 20 of them
# twice, and on the free instance nothing written survives a spin-down -- so
# the recording has to be in place before the first stranger arrives, and the
# file has to move onto a paid disk before that too.

# A random value, kept in a cookie this site sets itself, used for nothing but
# counting. It is not a login and it identifies nobody: it says only "this
# browser has been here before". A handle cannot answer that, because most
# visitors read the landing page and leave without typing one.
VISITOR_COOKIE = "nextcf_visitor"

# Long enough to cover the measuring period in section 9 and no longer.
VISITOR_COOKIE_DAYS = 180

# What a cookie value has to look like before it is believed. Anything else is
# treated as no cookie at all and replaced -- the value comes from the browser,
# which means it comes from outside, which means it is never trusted.
VISITOR_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{16,64}$")

# Which pages count as a visit, by endpoint name (the view function's name).
#
# `progress` is deliberately absent. That page reloads itself every two
# seconds with a meta refresh, so one visitor waiting forty seconds would
# write twenty rows and one person would look like a crowd.
RECORDED_ENDPOINTS = {"index", "results", "how", "privacy"}

# -------------------------------------------------------------- the queue
#
# ADR 0018. Syncs run one at a time in the order they arrived (sync.py), which
# is what lets this page say how long the wait is instead of guessing.

# Two requests a sync, each waiting its turn in api_client's limiter. Worked
# out from those two numbers rather than typed as 4, so that the page's
# arithmetic follows the day either of them changes.
SECONDS_PER_SYNC = 2 * api_client.SECONDS_BETWEEN_REQUESTS

# How often the progress page reloads itself. Often at the front of the queue,
# rarely at the back: a visitor with eight syncs ahead of them has nothing new
# to read for half a minute, and polling every two seconds would only make a
# launch spike expensive -- every reload is a whole page rendered on half a
# CPU. The countdown in between is done in the browser.
MIN_REFRESH_SECONDS = 2
MAX_REFRESH_SECONDS = 10

# How many submissions the table shows. The database keeps every one of them --
# Benq has 8,574 -- but a page carrying 8,574 rows is slow to build, heavy to
# send and impossible to read. The count of what is NOT shown goes on the page
# too, because silently truncating a list is its own kind of lying.
#
# Cut from 100 to 10 on 2026-09-24, after reading the page on a phone: it ran
# to twelve and a half screens, of which nine were this table. The table's job
# is not to be a copy of the visitor's Codeforces profile -- they have one of
# those. It is the only evidence on the page that this site really read THEIR
# history, for somebody who has just handed over a handle and wants to see
# that their last solve is in there. Ten rows prove that; a hundred bury it,
# and bury the five recommendations that are the actual product.
RESULTS_LIMIT = 10

# How many problems a list offers. Five since v0.4; named since a topic's
# list has to be filled up to it (ADR 0025).
RECOMMENDED = 5

# How long the problems of an ended plan sit out their list's next plans
# (ADR 0026, web.choose_plan). A week: long enough that swapping again and
# again brings new five rather than the last ones back, short enough that
# nothing is hidden for good without the visitor having said so.
PLAN_REST_SECONDS = 7 * 24 * 3600

# Spec section 9's number, for /how: `evaluate.py final` on 2026-09-18, the
# second look at the 2026 test set (ADR 0013's amendment), for the model that
# ships. It is the same table as spec section 9, so change the two together --
# and only after a new test. A monthly refit does not change it: the test
# measured how well this KIND of model predicts a year it never saw.
#
# Log losses are population-weighted across the five strata, as section 9
# reports them. "average" is the score of always guessing the success rate
# seen before 2026 (57.4%), the honest zero point: a predictor that knows
# nothing about the user or the problem.
EVALUATION = {
    "attempts": "527,388",
    "coin": 0.6931,
    "average": 0.6720,
    "baseline": 0.6535,
    "model": 0.5934,
    "strata": [
        ("1000–1199", 0.6684, 0.5992),
        ("1200–1399", 0.6540, 0.5956),
        ("1400–1599", 0.6416, 0.5855),
        ("1600–1799", 0.6328, 0.5868),
        ("1800–1999", 0.6225, 0.5766),
    ],
    # (model said, happened), in per cent, for the test year's attempts binned
    # by what the model said. From the same run.
    "calibration": [
        (7.8, 8.4), (16.4, 18.8), (25.6, 27.8), (35.3, 37.6), (45.2, 47.5),
        (55.1, 57.1), (65.1, 66.5), (75.0, 75.9), (84.4, 84.3), (93.1, 91.3),
    ],
    "gap_model": 1.5,
    "gap_baseline": 4.8,
}

# Create the tables if they are missing, then fail any job left behind by a
# process that died. Runs on import, which means once per server start, before
# any request is served.
#
# The second call belongs here and nowhere else. It marks EVERY unfinished job
# failed, which is only true at the moment the program that starts syncs has
# just started -- ADR 0007. Every other program calls init_db() alone.
db.init_db()
_orphaned = db.fail_orphaned_jobs()
if _orphaned:
    # Each of these is a visitor whose sync died with the last process and
    # who is now told so. Worth one line: a number that is high after every
    # deploy says the deploys are cutting syncs off.
    log.warning("marked %d unfinished jobs from before this start as interrupted", _orphaned)


def load_problemset():
    """Fetch the problemset, store it, rebuild the alias map. Runs in a thread.

    ADR 0010: the recommender draws from the problemset, and until 2026-09-15
    nothing but collect.py ever fetched it, so the server's database knew only
    the problems its visitors had submitted to -- a recommender there would
    have had nothing to recommend but problems the visitor had already tried.

    One request. It waits its two-second turn in api_client's limiter like any
    sync, so it cannot jump ahead of a visitor, and a visitor cannot collide
    with it.

    A thread, not a step in startup, because the server should answer while
    this is in flight: the landing page and a stored history do not need it.
    The results page asks db.problemset_size() and says "not ready" honestly
    until it is. A failure is logged and not retried here: the scheduler
    asks again on its next tick (ADR 0020), which is where a retry belongs.
    """
    conn = db.connect()
    try:
        problems = api_client.fetch_problemset()["problems"]
        stored, aliases = db.save_problemset(conn, problems)
        log.info("problemset: %d problems, %d aliases", stored, aliases)
        return True
    except Exception:
        # The same reasoning as sync.run_sync: an exception escaping a thread
        # dies in silence, and here nobody would even see a stuck job. The log
        # is the only place this can be told, and the traceback goes with it.
        log.exception("problemset fetch failed")
        # Said rather than raised, and answered rather than swallowed: the
        # scheduler asks for this and tries again on its next tick (ADR 0020).
        return False
    finally:
        conn.close()


def get_db():
    """The database connection for this request, opened on first use.

    A sqlite3 connection belongs to the thread that created it, and the server
    runs requests on a pool of threads it reuses. So a connection is opened and
    closed inside a single request rather than shared between them.

    `g` is Flask's scratch space for one request. It is emptied when the
    request ends, which is what makes the teardown below possible.
    """
    if "db" not in g:
        g.db = db.connect()
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """Flask calls this when a request ends, whether or not it went well.

    Without it, every request would leak a connection and an open file handle.
    """
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@app.after_request
def record_visit(response):
    """Count this page view, and give a new browser an id to be known by.

    Flask calls this for every request, after the page has been built and
    before it is sent. Doing it here rather than inside each view means one
    place decides what a visit is, and a new page cannot forget to count.

    Four conditions, each ruling out something that is not a person reading a
    page: an endpoint not in RECORDED_ENDPOINTS (the progress page reloads
    itself every two seconds), a POST (the form, which redirects to a page
    that is counted), a redirect or an error (a stale results page redirects
    to the sync, and that visit is counted when the page finally renders), and
    a request whose database connection never opened.

    It runs after the response exists, so a failure here cannot change what
    the visitor sees -- and must not: a visit that cannot be recorded is worth
    less than the page it happened on.
    """
    if request.endpoint not in RECORDED_ENDPOINTS:
        return response
    if request.method != "GET" or response.status_code != 200:
        return response

    # A value from the browser is a value from outside. If it is missing or
    # malformed, this is a new browser as far as the count is concerned.
    sent = request.cookies.get(VISITOR_COOKIE, "")
    known = bool(VISITOR_ID_PATTERN.match(sent))

    # token_urlsafe, not random: `secrets` is the module meant for values that
    # must not be guessable. Somebody who guessed another visitor's id would
    # gain nothing here -- there is nothing to steal -- but a predictable id
    # would make two visitors collide, which is a wrong count.
    visitor_id = sent if known else secrets.token_urlsafe(16)

    # The handle whose page was actually shown, as the view declared it with
    # shown_handle() -- NOT the one in the URL. Until 2026-09-26 this read
    # request.view_args, and a mistyped handle answered from a remembered
    # failure (a 200, because that request did work) was written down as
    # somebody using the site under a handle that does not exist. Only the
    # view knows whether the page it built was that handle's page, so only
    # the view gets to say so. Every other page records the visit with no
    # handle: somebody came, and looked nothing up.
    handle = g.get("shown_handle")

    try:
        db.record_visit(get_db(), visitor_id, handle, request.path)
    except sqlite3.Error as exc:
        # Logged rather than raised, and logged rather than swallowed. The
        # visitor gets their page; the failure is somewhere it can be found.
        # The route's pattern, not the path: the path of a results page is a
        # handle, and the log does not keep handles (ADR 0022).
        log.warning("could not record a visit to %s: %s", request.url_rule.rule, exc)

    if not known:
        response.set_cookie(
            VISITOR_COOKIE,
            visitor_id,
            max_age=VISITOR_COOKIE_DAYS * 24 * 60 * 60,
            # Nothing in the browser reads this, so nothing in the browser
            # should be able to: httponly keeps it out of JavaScript's reach.
            httponly=True,
            # Not sent when another site links to or embeds this one, which is
            # the whole of what SameSite is for. Lax rather than Strict so
            # that following a link from a Codeforces blog post still arrives
            # with the cookie and counts as a return.
            samesite="Lax",
            # HTTPS only in production. Render terminates TLS at its proxy and
            # forwards plain HTTP, so request.is_secure is False there and the
            # forwarded header is what tells the truth. Locally it is http,
            # and a Secure cookie would simply never be stored.
            secure=request.is_secure or request.headers.get("X-Forwarded-Proto") == "https",
        )

    return response


@app.before_request
def start_clock():
    """Note when this request began, for the line log_request writes."""
    g.started = time.perf_counter()


@app.after_request
def log_request(response):
    """One line per page served: method, route, status, milliseconds.

    What it is for: "how often does anything fail, and is anything slow",
    answered by reading the host's log -- which until now held nothing about
    a request that went well, so there was nothing to compare a failure with.

    The route's PATTERN, never the path. /results/tourist would put a handle
    in a log the host keeps, and /privacy lists what this site keeps; it lists
    no log of handles (ADR 0022). A request matching no route logs a
    placeholder rather than the path it asked for, which could be anything.

    Static files are skipped. They are one stylesheet, a font and a bundle per
    page, and would bury the pages among them.

    Flask runs this for a response built by an error handler too, so a 404
    and a 500 are logged here like anything else. For a 500 Flask has already
    logged the traceback, just before.
    """
    if request.endpoint == "static":
        return response
    route = request.url_rule.rule if request.url_rule is not None else "(no route)"
    started = g.get("started")
    elapsed = f"{(time.perf_counter() - started) * 1000:.0f}ms" if started is not None else "?"
    log.info("%s %s %d %s", request.method, route, response.status_code, elapsed)
    return response


def log_exception(exc_info):
    """Flask's line for an exception no view caught, minus the path.

    Flask's own version writes "Exception on /results/tourist [GET]" -- the
    path, which on a results page is a handle, into a log /privacy promises
    holds none (ADR 0022). Found by reading the diff after every other line
    had been made to name routes. Same traceback, same level; the route's
    pattern in place of the path.

    Flask calls app.log_exception(exc_info), so replacing that one attribute
    on this one app is the whole change -- no subclass needed.
    """
    route = request.url_rule.rule if request.url_rule is not None else "(no route)"
    log.error("exception on %s %s", request.method, route, exc_info=exc_info)


app.log_exception = log_exception


@app.errorhandler(HTTPException)
def http_error(error):
    """Every error Flask answers for us, on the site's own page.

    Without this, a mistyped URL or a GET to a POST-only button got Flask's
    white "Not Found" page -- unstyled, and the kind of thing spec section 7.1
    names as what makes a site read as unfinished. The views that answer 404
    for a reason of their own already render error.html; this covers
    everything Flask decides before a view runs.

    It covers a bug too. An exception no view caught reaches here as a 500:
    Flask wraps it in InternalServerError, which is one of these, AFTER
    writing the traceback to the log. That is where the detail goes, and
    nowhere else -- the visitor gets a true sentence and a way to carry on,
    and showing them the exception would be useless to them and a gift to
    anyone probing the site. (A separate 500 handler was written first, and a
    mutation removing it changed nothing: this one was already answering.)

    The status code is kept exactly: this changes what the page looks like,
    not what it says to a browser. The headers are kept too -- a 405 must say
    which methods ARE allowed. Nothing here touches the database, because the
    fault may be the database.
    """
    messages = {
        404: "There is nothing at this address.",
        405: "That address does not take this kind of request.",
        500: "Something went wrong on our side. It has been logged.",
    }
    message = messages.get(error.code, error.description)
    response = app.make_response((render_template("error.html", handle=None, message=message), error.code))
    for name, value in error.get_headers():
        if name.lower() != "content-type":
            response.headers[name] = value
    return response


def shown_handle(handle):
    """Tell record_visit that this response is this handle's own page.

    Called by a view just before it renders a page built from a handle's
    stored history, with the spelling Codeforces uses. A view that renders
    anything else -- an error, a failure it remembers -- does not call it, and
    the visit is recorded without a handle. Opt-in rather than read from the
    URL, because a URL says what was asked for, not what was found.
    """
    g.shown_handle = handle


def remembered_failure(handle, job):
    """The page for a handle whose sync failed in the last few minutes.

    The same words and the same button whatever the cause; a status code
    that says which cause it was (FAILURE_STATUS, ADR 0022). Until
    2026-09-26 every cause answered 200 -- "this request worked, the sync did
    not" -- and that is how a typo came to be counted as a visitor using the
    site under a handle that does not exist.

    A failure closed before the cause was recorded has none, and is answered
    as ours: the one code that makes no claim about the handle or about
    Codeforces.
    """
    status = FAILURE_STATUS.get(job["failure"], 500)
    response = app.make_response((
        render_template("error.html", handle=handle, message=job["error"], retry=True,
                        failure=job["failure"]),
        status,
    ))
    if status == 503:
        # When asking again will really ask Codeforces again: the moment this
        # failure stops being remembered. Before that, a reload gets this same
        # page back, so telling a client to retry sooner would be untrue.
        failed_at = datetime.datetime.fromisoformat(job["finished_at"])
        age = (datetime.datetime.now(datetime.UTC) - failed_at).total_seconds()
        response.headers["Retry-After"] = str(max(1, int(FAILURE_REMEMBERED_SECONDS - age)))
    return response


def queue_view(conn, job_id):
    """Where a job is in the queue, how long that is, and when to ask again.

    One function because three places show the same numbers and must not
    drift: the progress page, the line on a results page whose history is
    being refreshed, and the status endpoint that keeps that line current.

    The seconds are arithmetic, not a guess -- syncs run one at a time (ADR
    0018), every sync is two requests, every request waits two seconds. They
    can only run LATE, because api_client retries a failed request, so
    everything that shows this number says "about" and asks again.
    """
    ahead = db.jobs_ahead(conn, job_id)
    return {
        "job_id": job_id,
        "position": ahead + 1,
        "seconds": int((ahead + 1) * SECONDS_PER_SYNC),
        # Quickly at the front of the queue, rarely at the back: with eight
        # syncs ahead there is nothing new to say for half a minute.
        "poll_in": min(MAX_REFRESH_SECONDS, max(MIN_REFRESH_SECONDS, ahead + 2)),
    }


# Where a redirect lands on the results page. The part of an address after
# "#" is a fragment: the browser never sends it to the server, and on arrival
# it scrolls to the element with that id.
#
#   LIST_ANCHOR    the five's section, <section id="next">: after a button that
#                  changes the whole list ("put back", "swap the five")
#   row_anchor()   one problem's row, <tr id="p-...">: after a button on it
#
# Found 2026-09-28 at phone width: every press came back to the top of the
# page, 700 to 1,200 pixels from the row that was pressed.
#
# A redirect that names no fragment keeps the one the browser already had,
# so one of these can reach /progress -- a results page whose data was wiped
# by a restart sends the visitor there. Chromium's meta refresh on an address
# with a fragment does not reload the page, and the visitor would wait there
# for ever. progress.html names its own address, without one, for that
# reason. Found the same day, trying a fragment to mark a typed handle.
LIST_ANCHOR = "next"


def row_anchor(problem_id):
    """The id a recommendation's row carries: results.html and
    Recommendations.jsx both write it as p-<problem id>."""
    return f"p-{problem_id}"


@app.route("/", methods=["GET", "POST"])
def index():
    """The landing page: the pitch, and the handle input inside it.

    One function, two jobs, because it answers two different HTTP methods:
        GET  -- somebody opened the page. Show the form.
        POST -- somebody submitted the form. Read it and send them onwards.

    A route answers GET only unless you list the methods explicitly, so
    without `methods=` below, submitting this form would return 405 Method
    Not Allowed.
    """
    if request.method == "POST":
        # `request` is the incoming request. It is not passed in as an
        # argument -- Flask makes it available for the duration of this call,
        # which is why it is imported rather than declared as a parameter.
        #
        # request.form holds the submitted fields, keyed by the `name`
        # attribute in the HTML. .get() rather than [] so a request without
        # that field is a normal empty answer instead of a 400 from Flask.
        handle = handle_from_input(request.form.get("handle", ""))

        if not handle:
            # The form has `required` on it, but that is enforced by the
            # browser and a browser is not the only thing that can POST here.
            # Anything arriving from outside is unchecked input, always.
            # 400 = "your request was malformed", which is accurate.
            return render_template("index.html", error="Enter a Codeforces handle."), 400

        # Do not decide anything here beyond where to send them. Whether the
        # data needs fetching is the results page's question, and asking it in
        # one place means a link somebody shares behaves the same as the form.
        #
        # A redirect is a response saying "the thing you want is at this other
        # address". The browser follows it, so the visitor sees
        # /results/tourist in the address bar -- bookmarkable, shareable, and
        # safe to reload. Rendering out of a POST instead means reloading
        # re-submits the form, which is the "Confirm Form Resubmission" dialog
        # everyone has seen.
        return redirect(url_for("results", handle=handle))

    return render_template("index.html")


@app.route("/results/<handle>")
def results(handle):
    """The submissions table, read from the database.

    Three outcomes: the data is here and fresh, so show it; the data is
    missing or stale, so start a sync and show its progress; or that is not a
    handle, so say so.

    `<handle>` in the route is a variable part of the path: /results/tourist
    matches, and "tourist" arrives as the `handle` argument.
    """
    if not HANDLE_PATTERN.match(handle):
        return render_template(
            "error.html",
            handle=handle,
            message="That does not look like a Codeforces handle.",
        ), 404

    conn = get_db()
    user = db.get_user(conn, handle)

    # last_synced is NULL until a sync finishes, so "never synced" and "a sync
    # that died halfway" are the same case here, which is the point of ADR
    # 0004.
    if user is None or user["last_synced"] is None:
        # Already being fetched -- by this visitor a moment ago, or by
        # somebody else asking for the same handle. Watch that one.
        active = db.get_active_job(conn, "sync", handle)
        if active is not None:
            return redirect(url_for("progress", job_id=active["id"]))

        # Asked for recently and refused. A handle that does not exist will
        # not start existing in the next ten minutes, and the answer is
        # already on disk: give it back now instead of spending two requests
        # and four seconds of everybody's queue to be told the same thing.
        # The page carries a button for the case where that is wrong.
        failed = db.recent_failed_job(
            conn, "sync", handle, db.utc_ago(FAILURE_REMEMBERED_SECONDS)
        )
        if failed is not None:
            return remembered_failure(handle, failed)

        # Nothing stored and nothing known against it. Nothing here waits on
        # Codeforces: start_sync writes one row and returns.
        return redirect(url_for("progress", job_id=sync.start_sync(handle)))

    # Stored: show it NOW, and refresh it behind the page -- ADR 0018, as
    # amended twice on the day it was written. The visitor never waits for a
    # queue, and the page never quietly shows old numbers: it carries a line
    # saying a sync is running, where it is in the queue and how long that is,
    # and the browser keeps that line current from the status endpoint below.
    #
    # Staleness is a plain text comparison because every timestamp has the
    # same fixed shape -- see db.utc_ago.
    stale = user["last_synced"] < db.utc_ago(FRESH_FOR_SECONDS)

    # Somebody may already be syncing this handle -- this visitor a minute
    # ago, or another visitor entirely. Then this page watches that job rather
    # than queueing a second one for the same work.
    active = db.get_active_job(conn, "sync", handle)
    job_id = active["id"] if active is not None else None
    if job_id is None and stale:
        job_id = sync.start_sync(handle)

    # One topic's five instead of the overall five (ADR 0025). Checked against
    # the topics the pool can hold: a hand-typed ?topic=nonsense is a page
    # that does not exist, not an empty list.
    topic = request.args.get("topic") or None
    if topic is not None and topic not in db.pool_topics(conn):
        return render_template("error.html", handle=None,
                               message="There is no topic by that name."), 404

    rows = db.get_submissions(conn, handle, limit=RESULTS_LIMIT)

    # This is the one page that counts as somebody using the site under a
    # handle (section 9) -- a stored history, found and shown.
    shown_handle(user["handle"])

    recs = recommendation_view(conn, user, topic)
    if recs["state"] == "ok":
        record_shown(conn, user, recs)
    topics = topic_rows(db.topic_breakdown(conn, handle))
    dismissed = db.count_dismissals(conn, handle)
    totals = db.problem_totals(conn, handle)
    # Topics this visitor has never practised are offered too: somebody who
    # has never solved an fft problem may be exactly who is asking for one.
    practised = {row["tag"] for row in topics}
    other_topics = [tag for tag in db.pool_topics(conn) if tag not in practised]

    return render_template(
        "results.html",
        # The spelling Codeforces uses, not the one that was typed. The two
        # match for lookups because both columns are COLLATE NOCASE, but the
        # page should show the real one.
        handle=user["handle"],
        rows=[display_row(row) for row in rows],
        total=db.count_submissions(conn, handle),
        last_synced=user["last_synced"],
        topics=topics,
        other_topics=other_topics,
        totals=totals,
        recs=recs,
        # Older than the freshness window: the page says so rather than
        # letting the numbers pass for current.
        stale=stale,
        # How many problems this visitor has pushed away, so the page can
        # offer to put them back (ADR 0021).
        dismissed=dismissed,
        dismissals_kept=db.DISMISSALS_KEPT,
        # Plans this visitor has finished or swapped, every list's, newest
        # first (ADR 0026). Drawn by the template only: it is outside the
        # island, and choosing a topic does not change it.
        plans=db.plan_history(conn, user["handle"]),
        # Everything the live line needs, or None when nothing is running.
        # The line's wording lives in templates/_sync_line.html, which the
        # status endpoint below renders too, so the page and the updates it
        # receives cannot drift into two different sentences.
        syncing=queue_view(conn, job_id) if job_id is not None else None,
        state=active["state"] if active is not None else "pending",
        here=url_for("results", handle=handle, topic=topic),
        # What the topic chart component starts from (ADR 0025): the same
        # data this template has just drawn, so the component's first render
        # is this page, not a second opinion about it.
        island=island_data(user["handle"], recs, dismissed, topics, other_topics, totals),
    )


def island_data(handle, recs, dismissed, topics, other_topics, totals):
    """Everything the topic chart component needs, as plain data -- ADR 0025.

    Embedded in the page as JSON, so the component renders the same five and
    the same chart the template drew; the addresses are worked out here, by
    Flask, so the component never builds a URL of its own that could drift
    from the routes.
    """
    return {
        "handle": handle,
        "recs": recs,
        "dismissed": dismissed,
        "dismissals_kept": db.DISMISSALS_KEPT,
        "topics": topics,
        "other_topics": other_topics,
        "totals": dict(totals),
        "urls": {
            "results": url_for("results", handle=handle),
            "recommendations": url_for("recommendations_data", handle=handle),
            "feedback": url_for("feedback", handle=handle),
            "restore": url_for("restore", handle=handle),
            "undo": url_for("undo", handle=handle),
            "plan": url_for("new_plan", handle=handle),
            "how": url_for("how"),
        },
    }


@app.route("/results/<handle>/recommendations")
def recommendations_data(handle):
    """One topic's five -- or the overall five -- as data, for the topic chart
    to swap in without reloading the page (ADR 0025).

    The same recommendation_view the page calls, so a topic's five cannot
    depend on whether JavaScript ran; and shown is shown, so they are
    recorded here as they are on the page (ADR 0024). A GET, because it
    changes nothing a visitor chose: the record of what was shown is the
    site's own bookkeeping, the same as a visit.
    """
    if not HANDLE_PATTERN.match(handle):
        return jsonify({"error": "not a handle"}), 404
    conn = get_db()
    user = db.get_user(conn, handle)
    if user is None or user["last_synced"] is None:
        return jsonify({"error": "no stored history for this handle"}), 404
    topic = request.args.get("topic") or None
    if topic is not None and topic not in db.pool_topics(conn):
        return jsonify({"error": "no such topic"}), 404
    recs = recommendation_view(conn, user, topic)
    if recs["state"] == "ok":
        record_shown(conn, user, recs)
    return jsonify({"recs": recs, "dismissed": db.count_dismissals(conn, handle)})


def record_shown(conn, user, recs):
    """Write down the five this page is about to show -- ADR 0024.

    The first showing of each problem only (db.record_recommendations), with
    the chance as computed and which fit of the model computed it, so that
    once visitors have tried them the site can say how often its chances
    came true on problems it chose.

    Like record_visit, a failure here is logged and swallowed: the page is
    worth more than the record of it.
    """
    fitted = model.current_topic_model() if recs["source"] == "topic" else None
    try:
        db.record_recommendations(
            conn, user["handle"], recs["problems"],
            target=recs["target"] / 100,
            source=recs["source"],
            model_version=fitted.get("fitted_at") if fitted else None,
            guarded=not recs["unguarded"],
            # Which list: None for the overall five, else the topic -- and
            # each problem carries its own "guarded", since a small topic's
            # five can mix both (ADR 0025).
            topic=recs["topic"],
        )
    except sqlite3.Error as exc:
        log.warning("could not record what %s showed: %s", request.url_rule.rule, exc)


@app.route("/results/<handle>/sync", methods=["POST"])
def resync(handle):
    """Fetch this handle again because the visitor pressed the button.

    The automatic refresh above only happens when the stored copy is older
    than FRESH_FOR_SECONDS. This is for the other case, and it is the common
    one for somebody who has just solved something: they were here eight
    minutes ago, the page is technically fresh, and they know perfectly well
    that it is out of date.

    POST, not a link. A GET that starts work is followed by whatever walks the
    page -- a browser prefetching what it thinks will be clicked, a crawler, a
    link checker -- and each would take a turn in a queue everybody shares.

    It redirects back to the results page rather than to the queue. The
    visitor is in the middle of reading something; the live line there already
    shows the position, the estimate and the end of the sync, so there is
    nothing the progress page could add except taking their page away.
    Redirecting at all is what makes the button safe to press twice: the
    second press reloads a page rather than repeating a POST.
    """
    if not HANDLE_PATTERN.match(handle):
        return render_template(
            "error.html",
            handle=handle,
            message="That does not look like a Codeforces handle.",
        ), 404

    sync.start_sync(handle)
    return redirect(url_for("results", handle=handle))


@app.route("/results/<handle>/feedback", methods=["POST"])
def feedback(handle):
    """"Too hard" or "too easy" on one recommendation -- ADR 0021.

    The problem is hidden and settled in its plan, where it stays, marked
    (ADR 0026). The difficulty target moves later: when the plan ends, by
    what all of its presses say together (ADR 0027). The page says now where
    the next plan will aim.

    POST and a redirect, like every other button here: a GET that changes
    something is followed by anything that walks the page, and a redirect is
    what makes a reload safe.
    """
    if not HANDLE_PATTERN.match(handle):
        return render_template("error.html", handle=handle,
                               message="That does not look like a Codeforces handle."), 404

    verdict = request.form.get("verdict", "")
    problem_id = request.form.get("problem", "")
    # "skip" since ADR 0028: hidden and settled like the other two, with no
    # vote on the target when the plan ends.
    if verdict not in ("too_hard", "too_easy", "skip") or not problem_id:
        # Anything can POST here, so the value is checked rather than trusted.
        return render_template("error.html", handle=handle,
                               message="That is not something you can say about a problem."), 400

    conn = get_db()
    user = db.get_user(conn, handle)
    if user is None or user["last_synced"] is None:
        return redirect(url_for("results", handle=handle))

    # Asked, not inferred from an error. The first version caught any
    # IntegrityError from the insert and blamed the problem -- but the insert
    # has two foreign keys, and SQLite's message does not say which one
    # refused. Checking the one thing a visitor can get wrong, before
    # writing, means a failure at the write is never passed off as theirs: it
    # reaches the 500 page and the log, as a bug should.
    if not db.problem_exists(conn, problem_id):
        # A hand-made POST, or a problemset that has moved under us.
        return render_template("error.html", handle=handle,
                               message="That problem is not one this site knows about."), 404

    # The list the press was made on, for the way back. Checked like ?topic=
    # on the page: anything can POST here.
    topic = request.form.get("topic") or None
    if topic is not None and topic not in db.pool_topics(conn):
        return render_template("error.html", handle=handle,
                               message="There is no topic by that name."), 400

    # Hidden, and settled in the plans that hold it, in one transaction
    # (db.record_feedback). The target does not move here: the plan's presses
    # move it together when the plan ends (ADR 0027, new_plan). The stored
    # spelling, not the typed one, so every row about this person names them
    # the same way.
    db.record_feedback(conn, user["handle"], problem_id, verdict)
    # Back to the list the press was made on, at the row: it now says what
    # was pressed, which is the confirmation.
    return redirect(url_for("results", handle=handle, topic=topic, _anchor=row_anchor(problem_id)))


@app.route("/results/<handle>/undo", methods=["POST"])
def undo(handle):
    """Take back one answer about one problem -- ADR 0028.

    The "undo" beside a marked row. The problem comes back, and goes back
    to "to do" in the plans still running (db.undo_feedback); nothing else
    changes. "Put back" below the list is still there for everything at
    once. POST and a redirect, like every button here: anything can POST,
    so the handle, the problem and the topic are all checked.
    """
    if not HANDLE_PATTERN.match(handle):
        return render_template("error.html", handle=handle,
                               message="That does not look like a Codeforces handle."), 404
    problem_id = request.form.get("problem", "")
    conn = get_db()
    if not problem_id or not db.problem_exists(conn, problem_id):
        return render_template("error.html", handle=handle,
                               message="That problem is not one this site knows about."), 404
    topic = request.form.get("topic") or None
    if topic is not None and topic not in db.pool_topics(conn):
        return render_template("error.html", handle=handle,
                               message="There is no topic by that name."), 400
    user = db.get_user(conn, handle)
    if user is not None:
        db.undo_feedback(conn, user["handle"], problem_id)
    # At the row, which has its buttons back.
    return redirect(url_for("results", handle=handle, topic=topic, _anchor=row_anchor(problem_id)))


@app.route("/results/<handle>/restore", methods=["POST"])
def restore(handle):
    """Put back every problem this visitor has pushed away.

    The undo for the buttons above. It does not touch the difficulty target:
    hiding a problem and moving the target are two things, and somebody who
    wants the target back presses the other button.
    """
    if not HANDLE_PATTERN.match(handle):
        return render_template("error.html", handle=handle,
                               message="That does not look like a Codeforces handle."), 404

    db.clear_dismissals(get_db(), handle)
    # Back to the list the visitor was on. Only used to build the address,
    # and url_for escapes it, so an unknown topic costs a 404 page at worst.
    return redirect(url_for("results", handle=handle, topic=request.form.get("topic") or None,
                            _anchor=LIST_ANCHOR))


@app.route("/results/<handle>/plan", methods=["POST"])
def new_plan(handle):
    """End this list's plan, so the page makes the next -- ADR 0026.

    "Next five" when every problem is settled, "swap the five" when not: one
    route, and db.end_plan records which it was. It does not choose the next
    five itself. The results page does that when it finds no plan running,
    the same way it does the first time, so there is one place a plan is
    made.

    POST and a redirect, like every button here. The form names the plan it
    was drawn for, and only that plan ends (db.end_plan): a double-click's
    second POST finds it already gone and changes nothing, instead of ending
    the plan the first press made.
    """
    if not HANDLE_PATTERN.match(handle):
        return render_template("error.html", handle=handle,
                               message="That does not look like a Codeforces handle."), 404
    # Anything can POST here, so both values are checked rather than trusted.
    plan_id = request.form.get("plan", "")
    if not plan_id.isdecimal():
        return render_template("error.html", handle=handle,
                               message="That is not a plan this site made."), 400
    conn = get_db()
    topic = request.form.get("topic") or None
    if topic is not None and topic not in db.pool_topics(conn):
        return render_template("error.html", handle=handle,
                               message="There is no topic by that name."), 400
    user = db.get_user(conn, handle)
    if user is not None:
        # The plan's presses, together, move the list's target -- once, now
        # that the plan is over (ADR 0027). Worked out from the plan as it
        # stands; db.end_plan writes it only if this request is the one that
        # ends the plan, so a double-click moves the target once.
        found = db.active_plan(conn, user["handle"], topic or "")
        move = next_move(conn, user, topic, [row["outcome"] for row in found[1]]) if found else None
        # The stored spelling: the plan was made under it. NOCASE would find
        # it either way; this keeps every row about a person naming them one way.
        db.end_plan(conn, user["handle"], topic or "", int(plan_id), move)
    # At the list, where the next five now are.
    return redirect(url_for("results", handle=handle, topic=topic, _anchor=LIST_ANCHOR))


def list_target(conn, user, topic=None):
    """Where one list's target stands, and its staircase's memory -- ADR 0027.

    Returns {"target", "step", "direction", "own"}. For the overall list:
    the visitor's own target once it has moved, else the product default.
    target_chosen_at is what separates the two, because target_prob's own
    default is 0.70, which is a number somebody could also reach (ADR 0021).
    For a topic: its own row once its target has moved (ADR 0025); until
    then it starts from wherever the overall target is, with a staircase of
    its own that has not moved yet. `own` says which, for the page.
    """
    overall = user["target_prob"] if user["target_chosen_at"] else model.DEFAULT_TARGET
    if topic is None:
        return {"target": overall, "step": user["target_step"],
                "direction": user["target_direction"], "own": user["target_chosen_at"] is not None}
    row = db.topic_target(conn, user["handle"], topic)
    if row is None:
        return {"target": overall, "step": None, "direction": None, "own": False}
    return {"target": row["target_prob"], "step": row["step"],
            "direction": row["direction"], "own": True}


def next_move(conn, user, topic, outcomes):
    """Where a list's target goes when a plan with these presses ends:
    (target, step, direction) from model.step_target, or None if the presses
    point nowhere and it stays -- ADR 0027. The page's "your next five will
    aim at" and the end of the plan both ask this, so they cannot differ."""
    direction = model.plan_direction(outcomes)
    if direction is None:
        return None
    now = list_target(conn, user, topic)
    return model.step_target(now["target"], now["step"], now["direction"], direction)


@app.route("/progress/<int:job_id>/status")
def sync_status(job_id):
    """The live line on a results page, asked for again every few seconds.

    It answers with the line itself -- the same fragment the page was built
    with -- rather than with numbers the browser would have to turn into a
    sentence. Two copies of that sentence, one in Jinja and one in
    JavaScript, is exactly how a page ends up saying two different things.

    The fragment carries its own state and its own next interval in data
    attributes, so the script does not need to know the queue's arithmetic
    either: it swaps the line in and reads when to ask again.
    """
    conn = get_db()
    job = db.get_job(conn, job_id)
    if job is None:
        # A job that has been cleaned away. 404 rather than an empty line: the
        # script stops asking, and the page keeps the words it already has.
        return jsonify({"state": "missing"}), 404

    return render_template(
        "_sync_line.html",
        state=job["state"],
        syncing=queue_view(conn, job_id) if job["state"] in ("pending", "running") else None,
        here=url_for("results", handle=job["target"]),
    )


@app.route("/progress/<int:job_id>")
def progress(job_id):
    """A sync in flight.

    <int:job_id> matches digits only, so /progress/nonsense is a 404 from the
    router and never reaches this function.
    """
    conn = get_db()
    job = db.get_job(conn, job_id)

    if job is None:
        return render_template(
            "error.html",
            handle=None,
            message="There is no sync with that number.",
        ), 404

    if job["state"] == "done":
        return redirect(url_for("results", handle=job["target"]))

    if job["state"] == "failed":
        # 200, not an error status. This request worked perfectly, and the
        # honest answer to it is a page explaining that the job did not. A
        # status code describes the request for this page, not the job the
        # page reports on.
        return render_template(
            "error.html",
            handle=job["target"],
            message=job["error"] or "The sync stopped without saying why.",
            # A sync that failed is worth one more try on demand: the reason
            # may have been Codeforces rather than the handle.
            retry=True,
            failure=job["failure"],
        )

    # Where this visitor is in the queue, which is a count rather than an
    # estimate -- and it is only quotable because syncs run one at a time
    # (ADR 0018). While every sync had its own thread and the limiter
    # interleaved them, every visitor was last.
    view = queue_view(conn, job_id)

    return render_template(
        "progress.html",
        job=job,
        position=view["position"],
        seconds=view["seconds"],
        refresh=view["poll_in"],
    )


@app.route("/how")
def how():
    """How the model works, and section 9's number (spec section 4.1).

    Static apart from the numbers, which come from EVALUATION above so that
    the page and the spec are updated from one place in the code.
    """
    ev = EVALUATION
    return render_template(
        "how.html",
        ev=ev,
        # How far below the know-nothing guess each predictor gets: the plain
        # way to say "the model knows about four times as much as the rating".
        gain_baseline=ev["average"] - ev["baseline"],
        gain_model=ev["average"] - ev["model"],
        unrated_start=model.UNRATED_START,
        # From the constant, so the page cannot describe a guard rail the
        # code does not have (ADR 0023).
        support_min=model.SUPPORT_MIN,
    )


@app.route("/favicon.ico")
def favicon():
    """The icon's old address, which browsers and bots still ask for on their
    own: sent on to the real one, instead of a 404 in the log for every
    visit (templates/base.html links the real one directly)."""
    return redirect(url_for("static", filename="favicon.svg"), code=301)


# What crawlers are asked to leave alone. The results and progress pages
# DO things when opened: a results page makes a practice plan for each list
# it is asked for (ADR 0026), and records what it showed (ADR 0024). One
# public link to somebody's page, followed by a crawler through its thirty-
# odd topic links, would make thirty plans nobody asked for and put a
# hundred-odd "showings" nobody saw into the calibration record. The pages
# a crawler should read -- the landing page, /how, /privacy -- stay open.
ROBOTS = """User-agent: *
Disallow: /results/
Disallow: /progress/
"""


@app.route("/robots.txt")
def robots():
    return app.response_class(ROBOTS, mimetype="text/plain")


@app.route("/privacy")
def privacy():
    """What this site reads, what it keeps, and how to have it removed.

    Spec section 4.1 puts this page at v0.7 for a reason that is not legal
    procedure: v0.7 is when the site starts writing down that somebody was
    here, and a page that records visitors without saying so is the kind of
    thing this project should not ship.

    The page is told the cookie's name and life from the constants above, so
    that it cannot drift out of step with what the code actually sets.
    """
    return render_template(
        "privacy.html",
        cookie_name=VISITOR_COOKIE,
        cookie_days=VISITOR_COOKIE_DAYS,
        fresh_minutes=FRESH_FOR_SECONDS // 60,
    )


@app.template_filter("ago")
def ago(stamp, now=None):
    """How long ago a timestamp was, in words: "just now", "5 minutes ago",
    "yesterday", "3 weeks ago".

    Pages say this rather than the timestamp itself (2026-09-28). A raw
    "2026-09-27T17:51:51Z" is the database's format, not a reader's, and it
    is in UTC: for somebody in China, eight hours ahead, a date near midnight
    is the wrong day. Worded here, by the server, so the page, the topic
    component and a page without script all say the same thing. The exact
    instant stays in each <time> element's datetime attribute and title.

    A template filter: `{{ last_synced | ago }}` in Jinja calls this.
    """
    now = now or datetime.datetime.now(datetime.UTC)
    seconds = (now - datetime.datetime.fromisoformat(stamp)).total_seconds()

    def count(n, unit):
        return f"{n} {unit}{'' if n == 1 else 's'} ago"

    # A stamp a moment in the future -- two clocks a second apart -- is now.
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        return count(int(seconds // 60), "minute")
    if seconds < 86400:
        return count(int(seconds // 3600), "hour")
    days = int(seconds // 86400)
    if days == 1:
        return "yesterday"
    if days < 14:
        return count(days, "day")
    if days < 60:
        return count(days // 7, "week")
    if days < 365:
        return count(days // 30, "month")
    return count(days // 365, "year")


def display_row(row):
    """Turn one database row into just the fields the table shows.

    This exists so the template stays dumb. A template that decides things --
    what to show when a value is missing, how to build a URL -- is program
    logic living somewhere you cannot step through in a debugger.

    Note what is no longer here. The old version read raw API dicts and had to
    know which Codeforces fields go missing; that knowledge now lives in one
    place, db.save_sync, which was the plan recorded on 08-15. What is left is
    a display decision: an unjudged submission has no verdict in the database,
    and the word "TESTING" belongs on the page rather than in a column.
    """
    url = None
    if row["contest_id"] is not None:
        # contest_id and problem_index are separate columns exactly so that
        # nothing has to split a problem id to build this -- see the comment on
        # problems.id in schema.sql.
        url = f"https://codeforces.com/contest/{row['contest_id']}/problem/{row['problem_index']}"

    return {
        "rating": row["rating"],
        "verdict": row["verdict"] or "TESTING",
        # What counts as a solve is program logic and belongs here; which CSS
        # class that turns into is presentation and belongs in the template.
        # Assumption 3 in spec section 8: "OK" means solved, and that
        # assumption is worth being able to find in one place when v0.6 has to
        # revisit it.
        "ok": row["verdict"] == "OK",
        "name": row["name"],
        "url": url,
    }


def recommendation_view(conn, user, topic=None):
    """Everything the recommendations section needs, or the reason there are none.

    The five are the list's plan (ADR 0026): chosen once, the first time the
    list is shown with no plan running (choose_plan), then kept -- the same
    five on every visit, each ticked when a sync finds it solved or marked
    when "too hard" or "too easy" is pressed, until the visitor asks for the
    next five (new_plan).

    With `topic`, the five are that topic's (ADR 0025): the pool filtered to
    its tag, aimed at the topic's own target -- the overall one until
    "too hard" or "too easy" has been pressed on that topic's list -- and, in
    a topic too small for five to pass ADR 0023's guard rail, the empty places
    filled from the rest and marked `thin` row by row.

    Four outcomes, and each gets its own sentence on the page, because "no
    recommendations" means four different things and a visitor deserves to
    know which:

        unrated    Codeforces has no rating for them AND there is no topic
                   model to fall back on: the rating-only baseline has
                   literally nothing to go on. With the model, an unrated
                   visitor is served from model.UNRATED_START (ADR 0016).
        not_ready  the problemset has not arrived yet -- the few seconds after
                   a restart, or a fetch that failed (ADR 0010).
        exhausted  the pool is empty because they have solved everything
                   rated. Nobody will see this; it costs one line to be true.
        ok         five problems.

    The rating used is TODAY's -- the visitor is choosing now. Fitting used the
    rating each user had at the time of each attempt (model.training_counts),
    and the difference is the point: the past is predicted from what was known
    then, the future from what is known now.
    """
    unrated = user["cf_rating"] is None

    if db.problemset_size(conn) == 0:
        return {"state": "not_ready", "topic": topic}

    # Where this list's target stands now (list_target): what a NEW plan is
    # made at. The plan on screen keeps the one it was made with (ADR 0026).
    standing = list_target(conn, user, topic)
    target_now = standing["target"]

    # ADR 0026: the list's plan, if it has one -- the same five until the
    # visitor asks for the next -- else a new plan made from a fresh choice.
    list_key = topic or ""
    found = db.active_plan(conn, user["handle"], list_key)
    if found is None:
        # The topic model reads the rating Codeforces COMPUTES with, which
        # for a new account's first six rated contests is more than its
        # profile shows (model.HIDDEN_AFTER); the page says so when the two
        # differ. The baseline keeps the shown one, as it was fitted on (ADR
        # 0012). Somebody with no rating at all is served by the topic model
        # from model.UNRATED_START, which rating_now returns for them.
        rating = model.rating_now(conn, user["handle"], user["cf_rating"])
        made = choose_plan(conn, user, topic, rating, target_now, unrated)
        if "state" in made:
            return made
        found = db.create_plan(
            conn, user["handle"], list_key, made["picks"],
            target=target_now, source=made["source"],
            # The rating the chooser used, and the one Codeforces showed.
            rating=rating if made["source"] == "topic" else user["cf_rating"],
            shown=user["cf_rating"],
            looked_up_at=made["looked_up_at"], unguarded=made["unguarded"])
    plan, rows = found
    target = plan["target"]
    source = plan["source"]
    # Every note below about how the chances were worked out reads the plan's
    # ratings, not today's: a contest in the middle of a plan moves the
    # rating, and the five on screen were chosen at the old one.
    used, shown = plan["rating"], plan["shown"]

    probabilities = [{"probability": row["probability"]} for row in rows]
    settled = sum(1 for row in rows if row["solved"] or row["outcome"])
    # Where the next plan will aim if this one ended now: this plan's presses
    # taken together, one step of the staircase (ADR 0027) -- the same
    # next_move the end of the plan applies.
    move = next_move(conn, user, topic, [row["outcome"] for row in rows])
    next_target = move[0] if move else target_now
    baseline = model.current_baseline()
    return {
        "state": "ok",
        "source": source,
        # The topic this list is filtered to, None for the overall five, and
        # whether its target is its own or still the overall one (ADR 0025).
        "topic": topic,
        "own_target": standing["own"] if topic else False,
        "overall_target": round(list_target(conn, user)["target"] * 100),
        # A rating outside what the model was fitted on is answered, but as an
        # extrapolation, and the page says so -- see model.outside_range.
        "extrapolated": source == "topic" and model.outside_range(
            model.current_topic_model(), used),
        "hidden": source == "topic" and shown is not None and used != shown,
        "unrated": shown is None,
        "shown": shown,
        "computed": used,
        # What this plan aims at, and what the next one will: they differ once
        # this plan's presses point one way (ADR 0026, 0027).
        "target": round(target * 100),
        "next_target": round(next_target * 100),
        # The guard rail's two notes, as they were when the plan was made: the
        # rating it looked the visitor up at when theirs is outside the data,
        # and whether it had to stand aside (model.guard_pool).
        "looked_up_at": plan["looked_up_at"],
        "unguarded": bool(plan["unguarded"]),
        # Whether the target can be reached at all, whether the ladder has
        # run out, and whether the five are scattered -- about the five in
        # this plan, at the target they were chosen for (target_limits).
        **target_limits(probabilities, target),
        # The rating the curve puts at exactly the target, for the baseline's
        # sentence. Clamped to the problemset's real range: an 1100-rated user
        # at 70% comes out at 613, and there are no problems below 800. int()
        # because round(x, -2) on a float returns a float. The baseline never
        # serves somebody unrated, who has no rating to put into the curve.
        "centre": (max(800, int(round(model.rating_for_probability(shown, target), -2)))
                   if shown is not None else None),
        "event": baseline["event"],
        # The plan itself (ADR 0026): when it began, and how far along it is.
        # Complete when every problem is settled -- solved, or pressed.
        "plan": {
            # Which plan the "next five" button ends (new_plan).
            "id": plan["id"],
            "started_at": plan["started_at"],
            # In words, worded here so the component need not (ago).
            "started_ago": ago(plan["started_at"]),
            "size": len(rows),
            "settled": settled,
            "solved": sum(1 for row in rows if row["solved"]),
            "complete": settled == len(rows),
        },
        "problems": [
            {
                # The id goes to the page because the two buttons beside each
                # row have to name the problem they are about (ADR 0021).
                "id": row["id"],
                "name": row["name"],
                "rating": row["rating"],
                # Whole percentages. The curve is fitted to three decimal
                # places and is not that good; "71%" claims enough.
                "percent": round(row["probability"] * 100),
                # The chance as computed, for the record of what was shown
                # (ADR 0024) -- the page prints only the whole percent.
                "probability": row["probability"],
                "url": (
                    f"https://codeforces.com/problemset/problem/"
                    f"{row['contest_id']}/{row['problem_index']}"
                ),
                # Filled into a small topic's list without the guard rail's
                # evidence (ADR 0025); the row says so, and the record of
                # what was shown marks it unguarded.
                "thin": bool(row["thin"]),
                "guarded": not row["thin"] and not plan["unguarded"],
                # How it is settled (ADR 0026): solved, read from the history
                # since the plan began, or the button that was pressed. None
                # while it is still to do.
                "solved": row["solved"],
                "outcome": row["outcome"],
            }
            for row in rows
        ],
    }


def choose_plan(conn, user, topic, rating, target, unrated):
    """Choose the five a new plan will keep -- ADR 0026 -- or say why there
    are none: {"state": "unrated" | "exhausted", "topic": ...}.

    The choice is the one the page always made: the pool, less what is
    solved and hidden (db.recommendation_pool); ADR 0023's guard rail; the
    topic model's nearest to the target, or the rating-only baseline when
    there is no model file (the page says which, in words). Returns
    {"picks", "source", "looked_up_at", "unguarded"}, each pick carrying its
    id, its chance and, in a small topic's list, "thin".
    """
    pool = db.recommendation_pool(conn, user["handle"], topic)

    # ADR 0026: what this list's recent plans held sits out this one -- a
    # swap asks for different five, and the same five are otherwise still the
    # nearest. For a while, not for good: they were set aside, not hidden,
    # and "put back" knows nothing about them. A list with nothing else left
    # gets them back rather than nothing.
    resting = db.recently_planned(conn, user["handle"], topic or "",
                                  db.utc_ago(PLAN_REST_SECONDS))
    pool = [row for row in pool if row["id"] not in resting] or pool

    # ADR 0023: offer only what people near this visitor have actually tried,
    # and a harder version only after the easier one. On a topic's list, the
    # easier-version rule looks at everything the visitor has not solved, not
    # only this topic's problems: an easy version can carry different tags
    # from its hard one (model.guard_pool).
    unsolved = db.recommendation_pool(conn, user["handle"]) if topic else None
    pool, guard = model.guard_pool(pool, rating, fill=topic is not None, unsolved=unsolved)

    def choose_from(rows, count):
        """The topic model's `count` nearest the target, or the baseline's
        when there is no model file -- None if neither can serve."""
        chosen = model.topic_recommend(conn, user["handle"], rating, rows, target, count=count)
        if chosen is not None:
            return chosen, "topic"
        if unrated:
            return None, None
        return model.recommend(rows, user["cf_rating"], target, count=count), "rating"

    picks, source = choose_from(pool, RECOMMENDED)
    if picks is None:
        return {"state": "unrated", "topic": topic}
    # A topic too small for five to pass the guard rail: the empty places,
    # and only those, from what did not pass -- marked, row by row.
    if topic and len(picks) < RECOMMENDED and guard["rest"]:
        extra, _ = choose_from(guard["rest"], RECOMMENDED - len(picks))
        picks = picks + [dict(pick, thin=True) for pick in extra]
    if not picks:
        return {"state": "exhausted", "topic": topic}
    return {"picks": picks, "source": source,
            "looked_up_at": guard["looked_up_at"], "unguarded": guard["fallback"]}

def target_limits(picks, target):
    """Say when "too hard" or "too easy" can no longer change the list.

    Two different walls, and the page names whichever one is hit:

        reach   The target is fine but no problem left gets near it. The
                problemset has nothing rated below 800 (ADR 0012's floor), so
                for a newcomer even the easiest problems left sit below a
                high target; at the other end a very strong visitor runs out
                of hard ones. The five shown are then the nearest there are,
                and pressing again hides one without finding anything nearer.
                "easiest" or "hardest", from which side every pick misses.
        at_end  The target itself is at the end of the ladder
                (model.TARGET_EASIEST / TARGET_HARDEST), so the next press in
                that direction moves nothing. "easiest" or "hardest".

    A pick "misses" when it is further from the target than model.BAND, the
    width inside which the model cannot tell problems apart anyway -- so a
    list the model would call on target is never called off it.
    """
    probabilities = [pick["probability"] for pick in picks]
    reach = None
    if all(p < target - model.BAND for p in probabilities):
        reach = "easiest"
    elif all(p > target + model.BAND for p in probabilities):
        reach = "hardest"

    at_end = None
    if target >= model.TARGET_EASIEST:
        at_end = "easiest"
    elif target <= model.TARGET_HARDEST:
        at_end = "hardest"

    # A third case, found in the browser on a small topic's list (ADR 0025):
    # the five straddle the target but some are far from it -- 30%, 31%,
    # 63% at a target of 50% -- because the topic has too few problems near
    # it. Neither wall above says that. "Far" is twice the model's band.
    scattered = reach is None and any(abs(p - target) > 2 * model.BAND for p in probabilities)

    return {"reach": reach, "at_end": at_end, "scattered": scattered}


def topic_rows(rows):
    """Turn db.topic_breakdown() rows into what the chart draws.

    Same job as display_row: the template stays dumb, and the one arithmetic
    decision in the chart -- how long each bar is -- happens somewhere it can
    be stepped through and checked.

    Bars are scaled against the LARGEST topic, not against the user's total or
    a fixed number. Against the total, every bar would be a sliver, because a
    problem counts under each of its three tags and the total counts it once.
    Against a fixed number, the chart would look different for a beginner and
    an expert for reasons that are about the scale rather than about them.
    Relative to their own biggest topic, the shape is the same question at
    every level: what has this person spent their time on.
    """
    if not rows:
        return []

    # `or 1` guards a user who has attempted problems and solved none: every
    # bar is then zero-wide, which is correct, and the division is not.
    widest = max(row["solved"] for row in rows) or 1

    return [
        {
            "tag": row["tag"],
            "solved": row["solved"],
            "attempted": row["attempted"],
            "rated_solved": row["rated_solved"],
            # `is not None`, never a truth test. A mean of 0 is impossible
            # today and a truth test that happens to work is a bug waiting for
            # the data to change -- the same trap the rating column in
            # results.html already carries a comment about.
            "mean": (
                round(row["mean_solved_rating"])
                if row["mean_solved_rating"] is not None
                else None
            ),
            # A floor, not the raw proportion. One solve against a best of 948
            # is 0.1% of the row, which draws as a pixel or two and reads as
            # "nothing here" -- but "you have solved one" and "you have never
            # solved one" are exactly the distinction this chart exists to
            # show. 1% is a visible sliver at every width, the exact figure is
            # in the next column, and a topic with nothing solved still gets a
            # true zero.
            "width": (
                0.0 if row["solved"] == 0
                else max(1.0, round(100 * row["solved"] / widest, 1))
            ),
        }
        for row in rows
    ]


if __name__ == "__main__":
    # debug=True does two things locally: it reloads the app when a file is
    # saved, and it shows the full traceback in the browser instead of a blank
    # 500 page.
    #
    # It must never be on for the deployed copy. The debug traceback page
    # includes an interactive Python console, which is remote code execution
    # for anyone who can load the page. The host does not run this line anyway
    # -- serve.py imports `app` and runs it under waitress -- so this block is
    # the local-only path.
    #
    # The debug reloader runs this file twice: a parent that only watches for
    # saved files, and a child that serves, which it marks with this variable.
    # Fetching in both would spend two requests on one problemset.
    # The same log format as the deployed site (ADR 0022). Here rather than
    # at the top of the file, because only running this file should set it:
    # every check imports this module and prints its own way.
    import logs  # noqa: E402

    logs.configure()

    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        import scheduler  # noqa: E402 -- it imports this module, so not at the top

        # The one thread that runs syncs (ADR 0018), and the one that keeps
        # the problemset current -- including fetching it for the first time,
        # a few seconds from now (ADR 0020). Started here rather than at
        # import: every check imports this module, and a thread reaching for
        # Codeforces inside a check would put a real request in tests built
        # to make none.
        sync.start_worker()
        scheduler.start()
    app.run(debug=True)
