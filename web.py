"""NextCF web app.

v0.2: every page reads from the database, and no request waits on Codeforces.
Asking for a handle starts a background sync (sync.py) and sends the visitor
to a progress page, which polls the jobs table until the work is done.

    GET  /                   the pitch, and the handle input
    POST /                   read the field, send them to /results/<handle>
    GET  /results/<handle>   the table, out of the database
    GET  /progress/<job>     a sync in flight, reported honestly

Deliberately not here yet:
    styling and design tokens      v0.2, and the last thing it needs
    recommendations, the model     v0.4 onwards

Usage:
    .venv\\Scripts\\python.exe web.py
    then open http://127.0.0.1:5000
"""

import re

from flask import Flask, g, redirect, render_template, request, url_for

import db
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
# v0.4 replaces this table with five recommendations, so this is a stopgap.
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
    app.run(debug=True)
