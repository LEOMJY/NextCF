"""Check of the topic-breakdown chart on /results -- spec section 7.1.

A temporary database and no network. Two things here are worth more than the
rest:

  * the bar widths, because they are the only arithmetic on the page and a
    chart that is wrong is worse than no chart -- it is wrong confidently;
  * the accent rule, because ADR 0006 spends one colour on one meaning and
    "add a splash of green to the bars" is the most tempting single edit
    anybody will ever make to this stylesheet.
"""

import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="chart-"))
os.environ["NEXTCF_DB"] = str(SCRATCH / "test.db")
# Paths in this file are relative to the repository root, and the modules
# being checked live there, so go there first. The check then runs the same
# from any directory.
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

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


sync.start_sync = lambda handle: 1          # never reached; nothing here is stale
client = web.app.test_client()

# ------------------------------------------------------------------ the fixture
#
# Chosen so the numbers in the assertions below are checkable by hand:
#
#   greedy    150 solved            the biggest, so 100%
#   dp         15 solved, 3 failed  10% of the biggest, and 15/18 in the page
#   flows       1 solved            0.67% of the biggest -> floored to 1%
#   geometry    0 solved, 2 failed  a true zero, and no bar at all
#   sortings    4 solved, 2 unrated so the average rests on 2 of 4

def seed():
    submissions, sid = [], 0

    def add(contest, tags, verdict="OK", rating=1200):
        nonlocal sid
        sid += 1
        submissions.append({
            "id": sid, "verdict": verdict, "creationTimeSeconds": 1700000000 + sid,
            "author": {"participantType": "PRACTICE"},
            "problem": {"contestId": contest, "index": "A", "name": f"P{contest}",
                        "rating": rating, "tags": tags},
        })

    for i in range(150):
        add(1000 + i, ["greedy"])
    for i in range(15):
        add(2000 + i, ["dp"])
    for i in range(3):
        add(2500 + i, ["dp"], "WRONG_ANSWER")
    add(3000, ["flows"])
    for i in range(2):
        add(3500 + i, ["geometry"], "WRONG_ANSWER")
    for i in range(2):
        add(4000 + i, ["sortings"], rating=1600)
    for i in range(2):
        add(4500 + i, ["sortings"], rating=None)

    conn = db.connect()
    try:
        db.save_sync(conn, "chartuser", 1500, submissions)
    finally:
        conn.close()


seed()
HTML = client.get("/results/chartuser").get_data(as_text=True)
ROWS = re.findall(r'<tr style="--bar: ([\d.]+)%">\s*<th scope="row" class="topic-name">([^<]+)', HTML)
BARS = {tag.strip(): float(pct) for pct, tag in ROWS}

print("topic chart")


def the_page_rendered_at_all():
    assert "Topics" in HTML, "no chart section on the page"
    assert BARS, f"no bar rows parsed out of {len(HTML)} bytes of HTML"
    for marker in ("{#", "#}", "{%"):
        assert marker not in HTML, f"template syntax {marker!r} leaked onto the page"


def the_biggest_topic_fills_the_row():
    assert BARS["greedy"] == 100.0, BARS


def the_rest_are_proportional_to_it():
    # 15 of 150.
    assert BARS["dp"] == 10.0, BARS


def a_single_solve_is_floored_so_it_can_be_seen():
    # 1 of 150 is 0.67%, which draws as a pixel. The floor is 1%.
    assert BARS["flows"] == 1.0, f"expected the 1% floor, got {BARS.get('flows')}"


def nothing_solved_draws_nothing():
    """The floor must never turn "none" into "a little"."""
    assert BARS["geometry"] == 0.0, BARS
    row = re.search(r'--bar: [\d.]+%">\s*<th[^>]*>geometry</th>(.*?)</tr>', HTML, re.S)
    assert row, "no geometry row found"
    assert "0<span" in row.group(1) or ">0<" in row.group(1), "geometry should show 0 solved"


check("the page renders, with bar rows and no template syntax", the_page_rendered_at_all)
check("the biggest topic fills the row", the_biggest_topic_fills_the_row)
check("the rest are proportional to it", the_rest_are_proportional_to_it)
check("a single solve is floored to 1% so it can be seen", a_single_solve_is_floored_so_it_can_be_seen)
check("nothing solved draws nothing", nothing_solved_draws_nothing)


# --------------------------------------------------------------- what it says

def it_shows_solved_out_of_attempted():
    assert "15<span class=\"of\">/18</span>" in HTML.replace("\n", ""), \
        "dp should read 15/18"


def the_rated_count_appears_only_when_it_differs():
    """Two of the four sortings solves are unrated, so that row must say so.

    And dp, where every solve is rated, must not -- a caveat on every row is a
    caveat nobody reads.
    """
    sortings = re.search(r'>sortings</th>(.*?)</tr>', HTML, re.S).group(1)
    dp = re.search(r'>dp</th>(.*?)</tr>', HTML, re.S).group(1)
    assert "(2 rated)" in sortings, sortings
    assert "rated)" not in dp, dp


def the_footnote_explains_the_arithmetic():
    """Somebody will add the column up. It should agree with them first."""
    assert "adds to more than the 170 problems solved" in " ".join(HTML.split()), \
        "the footnote does not state the real total"


def it_refuses_to_claim_skill():
    assert "Not yet how good you are at it" in HTML
    assert "not yet comparable between rows" in " ".join(HTML.split())


check("it shows solved out of attempted", it_shows_solved_out_of_attempted)
check("the rated count appears only when it differs", the_rated_count_appears_only_when_it_differs)
check("the footnote explains the arithmetic", the_footnote_explains_the_arithmetic)
check("it refuses to claim skill", it_refuses_to_claim_skill)


# ----------------------------------------------------------------- the accent

def no_accent_anywhere_in_the_chart():
    """ADR 0006: the accent means one thing, and 39 green bars is not it.

    Checked in the stylesheet rather than the page because that is where it
    would be changed. Any rule whose selector names a chart element must not
    reach for --accent.
    """
    css = Path("static/style.css").read_text(encoding="utf-8")
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)       # comments mention it
    offenders = [
        selector.strip()
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css)
        if re.search(r"\.topics|\.bar\b|\.topic-name", selector)
        and "--accent" in body
    ]
    assert not offenders, f"the chart uses the accent colour: {offenders}"


def the_bar_is_a_background_not_a_column():
    """The column version collapsed to 2px on a phone. It must not come back."""
    css = Path("static/style.css").read_text(encoding="utf-8")
    assert re.search(r"\.topics tbody tr\s*\{[^}]*linear-gradient", css), \
        "the row gradient is gone -- has the bar become an element again?"


check("no accent anywhere in the chart", no_accent_anywhere_in_the_chart)
check("the bar is a row background, not a column", the_bar_is_a_background_not_a_column)


# ------------------------------------------------------------------ the empty

def a_user_with_no_topics_gets_no_chart():
    conn = db.connect()
    try:
        db.save_sync(conn, "empty", 900, [])
    finally:
        conn.close()
    html = client.get("/results/empty").get_data(as_text=True)
    assert "Topics" not in html, "an empty chart section was rendered"
    assert "No submissions found" in html


check("a user with no topics gets no chart, not an empty one", a_user_with_no_topics_gets_no_chart)

shutil.rmtree(SCRATCH, ignore_errors=True)
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
