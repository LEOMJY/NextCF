"""NextCF web app.

Every page reads from the database, and no request waits on Codeforces. Asking
for a handle starts a background sync (sync.py) and sends the visitor to a
progress page, which polls the jobs table until the work is done.

    GET  /                   the pitch, and the handle input
    POST /                   read the field, send them to /results/<handle>
    GET  /results/<handle>   five recommendations, the topic breakdown, and
                             the submissions table
    GET  /progress/<job>     a sync in flight, reported honestly

The recommendations come from the topic model (ADR 0014) when
topic_model.json is present, and from the rating-only baseline when it is not;
the page says which. Both draw on the problemset this program fetches when it
starts (ADR 0010).

Deliberately not here yet:
    /how, which shows the section 9 number   next
    re-fetching the problemset nightly       v0.7, with the scheduler

Usage:
    .venv\\Scripts\\python.exe web.py
    then open http://127.0.0.1:5000
"""

import os
import re
import sys
import threading

from flask import Flask, g, redirect, render_template, request, url_for

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

# How long a stored history counts as fresh. Opening a results page older than
# this starts a re-sync instead of showing it.
#
# The trade: too short and every visit costs a fetch and a wait; too long and
# somebody who just solved a problem is shown a page saying they did not. Ten
# minutes is long enough that reloading never re-fetches, and short enough that
# coming back after a contest does. It gets cheaper to shorten this once a
# re-sync can stop early at submissions already stored -- v0.7 work.
FRESH_FOR_SECONDS = 600

# How many submissions the table shows. The database keeps every one of them --
# Benq has 8,574 -- but a page carrying 8,574 rows is slow to build, heavy to
# send and impossible to read. The count of what is NOT shown goes on the page
# too, because silently truncating a list is its own kind of lying.
#
# The recommendations arrived at v0.4 and went ABOVE this table rather than
# replacing it, as this comment used to predict. The log is still how a
# visitor checks that the numbers above it are about them.
RESULTS_LIMIT = 100

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
    # 0004. Staleness is a plain text comparison because every timestamp has
    # the same fixed shape -- see db.utc_ago.
    if (
        user is None
        or user["last_synced"] is None
        or user["last_synced"] < db.utc_ago(FRESH_FOR_SECONDS)
    ):
        # Nothing here waits on Codeforces. start_sync writes one row, hands
        # the work to a thread, and returns immediately -- and if this handle
        # is already syncing it returns that job rather than starting a second.
        return redirect(url_for("progress", job_id=sync.start_sync(handle)))

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
    )


@app.route("/progress/<int:job_id>")
def progress(job_id):
    """A sync in flight.

    <int:job_id> matches digits only, so /progress/nonsense is a 404 from the
    router and never reaches this function.
    """
    job = db.get_job(get_db(), job_id)

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

    return render_template("progress.html", job=job)


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

        unrated    Codeforces has no rating for them, and a rating-only
                   baseline has literally nothing to go on. What to show
                   instead is spec section 12's cold-start question, due at
                   v0.6, and this does not answer it early.
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
    if user["cf_rating"] is None:
        return {"state": "unrated"}

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
    picks = model.topic_recommend(conn, user["handle"], user["cf_rating"], pool, target)
    source = "topic"
    if picks is None:
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
            model.current_topic_model(), user["cf_rating"]),
        "target": round(target * 100),
        # The rating the curve puts at exactly the target, for the sentence
        # that explains the list. Clamped to the problemset's real range:
        # an 1100-rated user at 70% comes out at 613, and there are no
        # problems below 800 to point at.
        #
        # int() because round(x, -2) on a float returns a float: 2800.0,
        # which is what the first version printed on the page.
        "centre": max(800, int(round(model.rating_for_probability(user["cf_rating"], target), -2))),
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
    app.run(debug=True)
