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

Deliberately not here yet:
    re-fetching the problemset nightly       v0.7, with the scheduler
    syncs one at a time, behind a queue      v0.7, ADR 0018

Usage:
    .venv\\Scripts\\python.exe web.py
    then open http://127.0.0.1:5000
"""

import os
import re
import secrets
import sqlite3
import sys
import threading

from flask import Flask, g, jsonify, redirect, render_template, request, url_for

import api_client
import db
import model
import sync

# Flask has to find templates/ and static/, and it locates them relative to
# this file. __name__ is how it works out where this file is. That is the only
# reason this argument exists.
app = Flask(__name__)

# Codeforces handles are letters, digits, underscore, hyphen, and dots on some
# older accounts. This is a cheap filter to keep obvious junk out of an
# outgoing API request -- it is NOT authoritative. Codeforces decides what a
# real handle is, and says HTTP 400 when it is not one. If this pattern is ever
# wrong it will be wrong by rejecting something valid, so keep it permissive.
HANDLE_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,24}$")

# How long a stored history counts as fresh. Since ADR 0018, opening a results
# page older than this shows what is stored AND re-syncs behind it, rather
# than making the visitor watch a queue first.
#
# The trade: too short and every visit costs a fetch and a wait; too long and
# somebody who just solved a problem is shown a page saying they did not. Ten
# minutes is long enough that reloading never re-fetches, and short enough that
# coming back after a contest does. It gets cheaper to shorten this once a
# re-sync can stop early at submissions already stored -- v0.7 work.
FRESH_FOR_SECONDS = 600

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
# The recommendations arrived at v0.4 and went ABOVE this table rather than
# replacing it, as this comment used to predict. The log is still how a
# visitor checks that the numbers above it are about them.
RESULTS_LIMIT = 100

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
db.fail_orphaned_jobs()


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
    until it is. A failure is printed and not retried here. On the free
    instance a restart comes several times a day anyway; the nightly job at
    v0.7 is the real retry, and it belongs in the scheduler, not bolted on.
    """
    conn = db.connect()
    try:
        problems = api_client.fetch_problemset()["problems"]
        stored, aliases = db.save_problemset(conn, problems)
        print(f"problemset: {stored} problems, {aliases} aliases", file=sys.stderr)
    except Exception as exc:
        # The same reasoning as sync.run_sync: an exception escaping a thread
        # dies in silence, and here nobody would even see a stuck job. The log
        # is the only place this can be told.
        print(f"problemset fetch failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    finally:
        conn.close()


def start_problemset_fetch():
    """Start load_problemset() in the background. Called by the entry points.

    Deliberately NOT called at import. Every check imports this module, and
    they are built to run with no network; a fetch started by the import
    itself would put a real Codeforces request inside every one of them. So
    the two programs that actually serve -- serve.py, and `python web.py`
    below -- start it, and importing web stays free of the network.

    daemon=True: a daemon thread does not keep the process alive, so stopping
    the server never waits on a download.
    """
    threading.Thread(target=load_problemset, name="problemset", daemon=True).start()


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

    # view_args holds the variable parts of the URL, so this is the handle on
    # /results/<handle> and nothing at all on the pages without one. It is the
    # spelling that was typed; the column is COLLATE NOCASE, so counting
    # distinct handles does not care.
    handle = (request.view_args or {}).get("handle")

    try:
        db.record_visit(get_db(), visitor_id, handle, request.path)
    except sqlite3.Error as exc:
        # Logged rather than raised, and logged rather than swallowed. The
        # visitor gets their page; the failure is somewhere it can be found.
        app.logger.warning("could not record a visit to %s: %s", request.path, exc)

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
        handle = request.form.get("handle", "").strip()

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
        # Nothing stored, so there is nothing to show but the queue. Nothing
        # here waits on Codeforces: start_sync writes one row and returns, and
        # if this handle is already syncing it returns that job rather than
        # queueing a second.
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

    rows = db.get_submissions(conn, handle, limit=RESULTS_LIMIT)

    return render_template(
        "results.html",
        # The spelling Codeforces uses, not the one that was typed. The two
        # match for lookups because both columns are COLLATE NOCASE, but the
        # page should show the real one.
        handle=user["handle"],
        rows=[display_row(row) for row in rows],
        total=db.count_submissions(conn, handle),
        last_synced=user["last_synced"],
        topics=topic_rows(db.topic_breakdown(conn, handle)),
        totals=db.problem_totals(conn, handle),
        recs=recommendation_view(conn, user),
        # Older than the freshness window: the page says so rather than
        # letting the numbers pass for current.
        stale=stale,
        # Everything the live line needs, or None when nothing is running.
        # The line's wording lives in templates/_sync_line.html, which the
        # status endpoint below renders too, so the page and the updates it
        # receives cannot drift into two different sentences.
        syncing=queue_view(conn, job_id) if job_id is not None else None,
        state=active["state"] if active is not None else "pending",
        here=url_for("results", handle=handle),
    )


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
    )


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


def recommendation_view(conn, user):
    """Everything the recommendations section needs, or the reason there are none.

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
        return {"state": "not_ready"}

    # model.DEFAULT_TARGET, not user["target_prob"] -- see the comment on the
    # constant for why the column is not read yet.
    target = model.DEFAULT_TARGET
    pool = db.recommendation_pool(conn, user["handle"])

    # The topic model when topic_model.json exists, the rating-only baseline
    # when it does not. Never silently: `source` goes to the page, which says
    # in words which of the two chose these problems, because they are
    # different claims -- one is about everybody at a rating, the other about
    # this person.
    #
    # The topic model reads the rating Codeforces COMPUTES with, which for a
    # new account's first six rated contests is more than its profile shows
    # (model.HIDDEN_AFTER); the page says so when the two differ. The
    # baseline keeps the shown one, as it was fitted on (ADR 0012).
    #
    # Somebody with no rating at all is served by the topic model from
    # model.UNRATED_START, which rating_now returns for them; without the
    # model file there is nothing to serve them from.
    rating = model.rating_now(conn, user["handle"], user["cf_rating"])
    picks = model.topic_recommend(conn, user["handle"], rating, pool, target)
    source = "topic"
    if picks is None:
        if unrated:
            return {"state": "unrated"}
        picks = model.recommend(pool, user["cf_rating"], target)
        source = "rating"
    if not picks:
        return {"state": "exhausted"}

    baseline = model.current_baseline()
    return {
        "state": "ok",
        "source": source,
        # A rating outside what the model was fitted on is answered, but as an
        # extrapolation, and the page says so -- see model.outside_range.
        "extrapolated": source == "topic" and model.outside_range(
            model.current_topic_model(), rating),
        "hidden": source == "topic" and not unrated and rating != user["cf_rating"],
        "unrated": unrated,
        "shown": user["cf_rating"],
        "computed": rating,
        "target": round(target * 100),
        # The rating the curve puts at exactly the target, for the sentence
        # that explains the list. Clamped to the problemset's real range:
        # an 1100-rated user at 70% comes out at 613, and there are no
        # problems below 800 to point at.
        #
        # int() because round(x, -2) on a float returns a float: 2800.0,
        # which is what the first version printed on the page.
        #
        # Only the baseline's sentence uses it, and the baseline never serves
        # somebody unrated -- who has no rating to put into the curve.
        "centre": (max(800, int(round(model.rating_for_probability(user["cf_rating"], target), -2)))
                   if not unrated else None),
        "event": baseline["event"],
        "problems": [
            {
                "name": pick["name"],
                "rating": pick["rating"],
                # Whole percentages. The curve is fitted to three decimal
                # places and is not that good; "71%" claims enough.
                "percent": round(pick["probability"] * 100),
                "url": (
                    f"https://codeforces.com/problemset/problem/"
                    f"{pick['contest_id']}/{pick['problem_index']}"
                ),
            }
            for pick in picks
        ],
    }


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
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        start_problemset_fetch()
        # The one thread that runs syncs (ADR 0018). Started here rather than
        # at import for the same reason as the fetch above: every check
        # imports this module, and a worker looking for jobs inside a check
        # would reach for Codeforces in tests built to touch no network.
        sync.start_worker()
    app.run(debug=True)
