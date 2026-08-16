# 0003 — Hosting on Render, served by Waitress

**Date:** 2026-08-15
**Status:** accepted

## Context

§7 named "Railway or Render" and never picked one. v0.1's last requirement is
that the site is deployed, so the choice has to be made now.

Two separate questions were hiding in that one line: which company runs the
computer, and which program actually serves the requests. Flask's built-in
server prints a warning telling you not to use it in production, and it is
right to — it serves one request at a time and its debug mode carries an
interactive Python console, which is remote code execution for anyone who can
load the page.

## Decision

**Render**, with **Waitress** as the web server, started by `serve.py`.

## Alternatives

**Railway** does not sleep, so there is no cold start, and its setup is
smoother. Its free allowance is trial credit rather than a standing free tier,
so it costs a few dollars a month. Rejected because the three months between
now and v1.0 are months where nobody is visiting, and paying for idle capacity
during development is the wrong place to spend money on this project.

Render's free tier sleeps after a period with no traffic, so the first visitor
after a quiet spell waits roughly a minute for it to wake. That cost is real
and lands in exactly the wrong place: §9 needs 50 strangers to try this, most
arriving at once from a Codeforces blog post. **Revisit before launch, not
before then** — the fix is a paid instance, and it is a payment decision that
should be made when there is something worth paying for.

**Gunicorn** is the industry default and what nearly every Flask deployment
guide assumes, which makes its error messages easier to search. Rejected
because it does not run on Windows at all, so the production setup could only
ever be tested by deploying it. Waitress runs the same command on both
machines, which turns a class of "works locally, breaks on the host" failures
into ones that show up before pushing.

## Consequences

- `serve.py` is a new module not in §4's list. It exists so the start command
  lives in the repository rather than in a hosting dashboard, where it would be
  invisible to version control and lost if the service is recreated.
- The port is read from the `PORT` environment variable and the app binds
  `0.0.0.0`. Hardcoding either is the standard way a deployment silently fails
  to accept traffic.
- `.python-version` pins 3.14. If the host does not offer it, dropping to 3.13
  costs nothing today — no 3.14-specific feature is used — but it must be
  decided consciously rather than by whatever the host defaults to.
- The SQLite persistence risk in §7 is **not** resolved by this and was moved
  to v0.2. v0.1 stores nothing, so a filesystem wipe on redeploy destroys
  nothing. Deploying a stateless app first separates "does the pipeline work"
  from "does the data survive", which are much harder to debug together.
