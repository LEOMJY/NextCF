"""NextCF web app.

v0.1 scope: a handle input on `/`, and a plain table of that handle's most
recent submissions on `/results/<handle>`. Every request calls the Codeforces
API and waits for the answer.

Deliberately not here yet:
    styling and design tokens      v0.2  -- see docs/spec.md section 7.1
    background job, progress page  v0.2  -- see docs/spec.md section 4
    database                       v0.2
    recommendations, the model     v0.4 onwards

Usage:
    .venv\\Scripts\\python.exe web.py
    then open http://127.0.0.1:5000
"""

import re
import urllib.error

from flask import Flask, redirect, render_template, request, url_for

import api_client

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

        # Do not render the results here. Redirect to their own URL instead.
        #
        # A redirect is a response that says "the thing you want is at this
        # other address, go there". The browser follows it immediately, so the
        # user sees /results/tourist in the address bar -- bookmarkable,
        # shareable, and safe to reload. Rendering results straight out of a
        # POST instead means reloading the page re-submits the form, which is
        # the "Confirm Form Resubmission" dialog everyone has seen.
        #
        # url_for("results", handle=handle) builds "/results/tourist" by asking
        # the routing table, rather than hardcoding the string. Change the
        # route later and every url_for follows; every hardcoded "/results/"
        # silently 404s.
        return redirect(url_for("results", handle=handle))

    return render_template("index.html")


@app.route("/results/<handle>")
def results(handle):
    """Show one handle's recent submissions.

    `<handle>` in the route is a variable part of the path: /results/tourist
    matches, and "tourist" arrives as the `handle` argument. The names have to
    agree -- <handle> in the rule, handle in the signature.
    """
    if not HANDLE_PATTERN.match(handle):
        return render_template(
            "error.html",
            handle=handle,
            message="That does not look like a Codeforces handle.",
        ), 404

    try:
        submissions = api_client.fetch_submissions(handle)
    except RuntimeError as exc:
        # Codeforces answered and refused. Nearly always a handle that does
        # not exist, and api_client has already dug the real explanation out
        # of the error body, so `exc` reads like
        #     "handle: User with handle nosuchuser42qq not found"
        # This is exactly the case spec section 7.1 calls the loudest amateur
        # tell on the site if it reaches the user as a traceback.
        return render_template("error.html", handle=handle, message=str(exc)), 404
    except urllib.error.URLError as exc:
        # The network itself failed: no DNS, no route, timed out, TLS refused.
        # Nothing the user did wrong, so it is a 5xx, not a 4xx. 502 Bad
        # Gateway = "I am a server, and the server I depend on let me down."
        #
        # Ordering note: urllib.error.HTTPError is a SUBCLASS of URLError, so
        # if HTTPError ever escaped api_client this clause would swallow it.
        # It does not -- api_client converts it to RuntimeError -- but that is
        # a fact about the other file, and worth rechecking if it changes.
        return render_template(
            "error.html",
            handle=handle,
            message=f"Could not reach Codeforces: {exc.reason}",
        ), 502

    rows = [display_row(sub) for sub in submissions]
    return render_template("results.html", handle=handle, rows=rows)


def display_row(sub):
    """Turn one raw API submission into just the fields the table shows.

    This exists so the template stays dumb. A template that decides things --
    what to show when a field is missing, how to build a URL -- is program
    logic living somewhere you cannot test, debug or step through.

    The two absent-field cases are the same ones api_client.format_submission
    handles, and that is now duplicated knowledge across two files. Fine at two
    call sites; pull it into one place when sync.py becomes the third.
    """
    problem = sub["problem"]

    # Unrated, brand new and gym problems have no "rating" (spec section 6),
    # and a submission still being judged has no "verdict".
    rating = problem.get("rating")
    verdict = sub.get("verdict", "TESTING")

    # contestId is absent for a few problem sources, e.g. acmsguru. Without it
    # there is no problem URL to build, so the template shows plain text.
    contest_id = problem.get("contestId")
    url = None
    if contest_id is not None:
        url = f"https://codeforces.com/contest/{contest_id}/problem/{problem['index']}"

    return {"rating": rating, "verdict": verdict, "name": problem["name"], "url": url}


if __name__ == "__main__":
    # debug=True does two things locally: it reloads the app when a file is
    # saved, and it shows the full traceback in the browser instead of a blank
    # 500 page.
    #
    # It must never be on for the deployed copy. The debug traceback page
    # includes an interactive Python console, which is remote code execution
    # for anyone who can load the page. The host will not run this line anyway
    # -- a real deployment imports `app` and runs it under a production server
    # (that is the next task), so this block is the local-only path.
    app.run(debug=True)
