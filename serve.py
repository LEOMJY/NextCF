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
from web import app

# An environment variable is a named value living outside the program, set by
# whoever starts it. The host picks a port at launch and announces it this way,
# so it cannot be hardcoded. 8000 is the fallback for running this by hand.
PORT = int(os.environ.get("PORT", "8000"))

# 0.0.0.0 means "accept connections arriving on any network interface".
# 127.0.0.1, which the dev server uses, means "this machine only" -- correct
# for a laptop and invisible to the outside world on a host.
HOST = "0.0.0.0"

if __name__ == "__main__":
    print(f"serving on http://{HOST}:{PORT}")
    serve(app, host=HOST, port=PORT)
