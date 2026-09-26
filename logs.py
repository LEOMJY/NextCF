"""How the running site writes its log -- ADR 0022.

Every module asks for a logger of its own (`logging.getLogger(__name__)`) and
writes to it. None of them decides what a line looks like or where it goes;
this file does, once, and only the entry points call it -- serve.py on the
host, and `python web.py` on a laptop. A check that imports web never calls
it, so the checks print only what they print today.

Where the lines go: standard error. Render collects whatever the process
writes to its output and shows it in the dashboard, so a file here would be
a second copy nobody reads, on a disk that is wiped on the free instance.

What never goes in a line: a handle, an IP address, or anything else /privacy
does not list. Every module is written to that rule -- job ids instead of
handles, a route's pattern instead of its path -- because /privacy says what
this site keeps, and a log the host keeps is kept.

Usage:
    import logs
    logs.configure()        # once, before anything else is imported
"""

import logging
import sys

# One line per event:
#   2026-09-26 18:04:11 INFO sync: job 41: done, 1843 submissions, 4.2s
# The time first, so lines sort; the level, so warnings can be searched for;
# the module, so a line says which part of the program wrote it.
FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure(level=logging.INFO):
    """Send every logger's lines to standard error, in one format.

    INFO and above: a sync starting and finishing, a problemset fetched, a
    page served. DEBUG is not used anywhere yet; the level is a parameter so
    that day costs nothing.

    Safe to call twice -- `force=True` replaces what the first call set up
    rather than adding a second handler, which would print every line twice.
    """
    logging.basicConfig(
        level=level,
        format=FORMAT,
        datefmt=DATE_FORMAT,
        stream=sys.stderr,
        force=True,
    )

    # Flask gives its app a handler of its own the first time app.logger is
    # used, with a different format. With the root handler above in place too,
    # every line from the app would appear twice. Flask checks for an existing
    # handler before adding its own, and the one above is it -- but if the app
    # had already used its logger before this ran, that handler is already
    # attached, so it is taken off here rather than trusted to be absent. By
    # searching, because the app's logger is named after whatever the module
    # was called: "web" under serve.py, "__main__" under `python web.py`.
    from flask.logging import default_handler

    for logger in logging.root.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            logger.removeHandler(default_handler)
