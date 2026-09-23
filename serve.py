"""Production entry point.

`web.py` starts Flask's own development server, which is fine on a laptop and
must never face the public internet: it serves one request at a time and is
built for convenience rather than exposure. This file runs the same app under
waitress, a real WSGI server, and is what the host executes.

Nothing here is Flask-specific. It reads two settings from the environment and
hands the app over.

Usage (identical locally and on the host):
    .venv\\Scripts\\python.exe serve.py
"""

import os

from waitress import serve

# Importing `app` runs web.py top to bottom, defining the routes. It does NOT
# start the development server -- that call is guarded by
# `if __name__ == "__main__"`, which is false when the file is imported. So
# debug mode, and its interactive console, cannot reach the internet.
import sync
from web import app, start_problemset_fetch

# An environment variable is a named value living outside the program, set by
# whoever starts it. The host picks a port at launch and announces it this way,
# so it cannot be hardcoded. 8000 is the fallback for running this by hand.
PORT = int(os.environ.get("PORT", "8000"))

# Render ends TLS at its own proxy and forwards plain HTTP to this process, so
# the only way the app can know a visitor arrived over https is the
# X-Forwarded-Proto header the proxy adds. Waitress DELETES those headers
# unless it is told that a proxy is in front of it, and deleting them is the
# right default -- anything that can reach the server directly could otherwise
# claim to be anybody, from anywhere, over any scheme.
#
# Without this the app believed every request was plain http, and the visitor
# cookie went out with no Secure flag on the live site (ADR 0017). Measured on
# 2026-09-23 by running waitress both ways against the same app.
#
# "*" trusts whatever connects, which is correct here for the reason above
# turned around: on Render nothing but their proxy can reach this port.
#
# In one place, and exported, so that a check can start a real server with the
# same configuration -- the earlier check set the header on a Flask test
# client, which never goes through waitress and therefore passed while the
# live site was wrong.
WAITRESS_OPTIONS = {
    "trusted_proxy": "*",
    "trusted_proxy_headers": {"x-forwarded-for", "x-forwarded-proto", "x-forwarded-host"},
}

# 0.0.0.0 means "accept connections arriving on any network interface".
# 127.0.0.1, which the dev server uses, means "this machine only" -- correct
# for a laptop and invisible to the outside world on a host.
HOST = "0.0.0.0"

if __name__ == "__main__":
    # Before serve(), which blocks for as long as the server runs. Both are
    # background threads, so the server starts answering at once while the
    # problemset arrives behind it -- ADR 0010.
    start_problemset_fetch()

    # The one thread that runs syncs, one at a time, in the order they were
    # asked for -- ADR 0018. Without it a visitor's sync is queued and never
    # runs, and the progress page counts down forever.
    sync.start_worker()
    print(f"serving on http://{HOST}:{PORT}")
    serve(app, host=HOST, port=PORT, **WAITRESS_OPTIONS)
