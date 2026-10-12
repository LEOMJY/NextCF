"""Check the ridge -- the landing page, its field and its tokens, ADR 0031.

No network. The landing page reads nothing but constants and three fitted or
generated files (baseline.json, topic_model.json, static/field.json). What
these hold it to:

  * THE SAMPLE IS REAL, AND NEVER YOURS. The five rows are web.SAMPLE_PACK,
    written by the server so they are there without script, each a link to
    its problem, and labelled a sample.
  * EVERY NUMBER IS THE CODE'S. The aim and its limits, the four
    measurements, the two counts in the top bar, and everything the page's
    script is handed to do its own sums with: read from the constants and
    files the rest of the site uses, so the pitch cannot drift from /how or
    from what the recommender does.
  * THE FIELD IS THE RECOMMENDER'S POOL. static/field.json holds every
    problem that can be recommended and no other, in the order
    model.recommend() breaks its ties.
  * THE THREE LAYERS (spec section 7.1). Nothing is asked of another server;
    the 3D library is fetched only by a device that will draw with it; the
    page stands without script; and no picture ever holds the form.
  * EVERY COLOUR CAN BE READ. Text tokens against the surfaces they sit on,
    at WCAG's 4.5 to 1, in the card table the tool pages still wear and in
    the ridge.
"""

import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="landing-"))

# Must be set before db is imported: db.py reads it at import time.
os.environ["NEXTCF_DB"] = str(SCRATCH / "test.db")
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

import collect  # noqa: E402
import db  # noqa: E402
import model  # noqa: E402
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


client = web.app.test_client()
CSS = Path("static/style.css").read_text(encoding="utf-8")
SCRIPT = Path("static/ridge.js").read_text(encoding="utf-8")
FIELD = json.loads(Path("static/field.json").read_text(encoding="utf-8"))
# The ridge's own values for the tokens: the one block that starts ".ridge {".
RIDGE = re.search(r"\n\.ridge \{\n(.*?)\n\}", CSS, re.S).group(1)


def landing():
    response = client.get("/")
    assert response.status_code == 200, response.status_code
    return response.get_data(as_text=True)


def words(html):
    """A page with its line breaks and indentation folded to single spaces,
    so a sentence can be looked for however the template wraps it."""
    return " ".join(html.split())


def token(name):
    """A colour token's value in style.css's :root, as #rrggbb. The first
    place a name is given a colour is :root: the ridge's block comes after."""
    value = re.search(r"(?<![\w-])" + re.escape(name) + r":\s*(#[0-9a-fA-F]{6});", CSS)
    assert value, f"no {name} colour in :root"
    return value.group(1)


def ridge_token(name):
    """The same token's value in the ridge."""
    value = re.search(r"(?<![\w-])" + re.escape(name) + r":\s*(#[0-9a-fA-F]{6});", RIDGE)
    assert value, f"no {name} colour in the ridge's block"
    return value.group(1)


def contrast(one, other):
    """WCAG's contrast ratio between two #rrggbb colours: 1 to 21."""
    def luminance(colour):
        channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    high, low = sorted((luminance(one), luminance(other)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def handed_to_the_script():
    """The block of JSON the page carries for static/ridge.js."""
    blob = re.search(r'<script type="application/json" id="ridge-data">(.*?)</script>', landing(), re.S)
    assert blob, "the page carries nothing for its script"
    return json.loads(blob.group(1))


def contests_at(rating):
    """The contest ids field.json holds at one rating, the gaps undone."""
    ids = []
    for n, gap in enumerate(FIELD["field"][str(rating)].split(",")):
        ids.append(int(gap) if n == 0 else ids[-1] - int(gap))
    return ids


# ------------------------------------------------------------ the sample
def a_rating_is_read_as_the_rank_it_would_be():
    """Codeforces's bands, at both edges of each: 1199 is a newbie's rating
    and 1200 a pupil's. Master and international master are one orange, and
    every grandmaster rank one red."""
    edges = {
        800: "newbie", 1199: "newbie", 1200: "pupil", 1399: "pupil", 1400: "spec",
        1599: "spec", 1600: "expert", 1899: "expert", 1900: "cm", 2099: "cm",
        2100: "master", 2399: "master", 2400: "gm", 3500: "gm",
    }
    wrong = {rating: web.rarity(rating)[0] for rating, key in edges.items() if web.rarity(rating)[0] != key}
    assert not wrong, f"read as the wrong rank: {wrong}"


def the_five_rows_are_the_sample_pack():
    rows = re.findall(
        r'<li><a class="rank-(\w+)" href="([^"]+)"><span class="sw"></span><span class="id">([^<]+)</span>'
        r'<span class="name">([^<]+)</span><span class="rt">(\d+)</span><b class="ch">(\d+)%</b></a></li>',
        landing())
    assert len(rows) == 5, f"{len(rows)} rows in the list"
    for (key, url, shown_id, shown_name, rating, percent), (problem_id, contest_id, index, name, real_rating, chance) \
            in zip(rows, web.SAMPLE_PACK):
        assert shown_id == problem_id and shown_name == name, (shown_id, problem_id)
        assert key == web.rarity(real_rating)[0], f"{problem_id} is marked {key}"
        assert int(rating) == real_rating, (problem_id, rating)
        # The same rounding the results page uses for a chance (web.py,
        # "percent"), so the sample reads exactly as a real plan would.
        assert int(percent) == round(chance * 100), (problem_id, percent)
        assert url == f"https://codeforces.com/problemset/problem/{contest_id}/{index}", (problem_id, url)


def the_sample_is_labelled_a_sample():
    """Never presented as the visitor's: the caption says whose it is, and
    "Back to the sample" is hidden until the script has shown something
    else."""
    html = landing()
    assert f'<span id="five-says">Sample: one real <b>{web.SAMPLE_RATING}</b>-rated history.</span>' in html, \
        "the five are not called a sample"
    assert '<button class="reset" id="reset" type="button" hidden>' in html, \
        "the way back to the sample is offered while the sample is showing"


def the_sample_pack_is_a_real_plan():
    """Five problems, none twice, each chance near the aim it was given at
    -- what a plan from choose_plan looks like, not a made-up hand. And each
    row's contest id and index are the two halves of its id, written out
    because an id is never split back into them (schema.sql)."""
    ids = [problem_id for problem_id, *_ in web.SAMPLE_PACK]
    assert len(ids) == 5 and len(set(ids)) == 5, ids
    for problem_id, contest_id, index, _, rating, chance in web.SAMPLE_PACK:
        assert f"{contest_id}{index}" == problem_id, f"{problem_id} is written as contest {contest_id}, index {index}"
        assert abs(chance - web.SAMPLE_TARGET) < 0.05, f"{problem_id} at {chance} is far from its aim"
        assert web.RATING_LOWEST <= rating <= web.RATING_HIGHEST and rating % 100 == 0, (problem_id, rating)
    assert model.TARGET_HARDEST <= web.SAMPLE_TARGET <= model.TARGET_EASIEST, web.SAMPLE_TARGET


def the_axis_is_the_ranks_end_to_end():
    """The seven stretches of the rating axis: RARITIES in order, the first
    starting at the lowest rating a problem has, each starting where the one
    before stops, the last ending at the highest. The page draws exactly
    these, and labels every boundary."""
    spans = web.rank_spans()
    assert [span["key"] for span in spans] == [key for _, key, _ in web.RARITIES], "not RARITIES in order"
    assert spans[0]["from"] == web.RATING_LOWEST and spans[-1]["to"] == web.RATING_HIGHEST, (spans[0], spans[-1])
    for before, after in zip(spans, spans[1:]):
        assert before["to"] == after["from"], f"a gap or an overlap between {before} and {after}"
    html = landing()
    drawn = re.findall(r'<i class="rank-(\w+)" data-from="(\d+)" data-to="(\d+)"></i>', html)
    assert [(key, int(a), int(b)) for key, a, b in drawn] == [(s["key"], s["from"], s["to"]) for s in spans], drawn
    ticks = [int(r) for r in re.findall(r'<span data-r="(\d+)"', html)]
    assert ticks == [spans[0]["from"]] + [span["to"] for span in spans], f"labels at {ticks}"
    slider = re.search(r'<input type="range" id="rating" min="(\d+)" max="(\d+)" step="(\d+)" value="(\d+)"', html)
    assert slider, "the rating is not a real slider"
    low, high, _, value = map(int, slider.groups())
    assert low == web.RATING_LOWEST and low <= value == web.SAMPLE_RATING <= high <= web.RATING_HIGHEST, slider.groups()


# ------------------------------------------------------------ the numbers
def every_number_is_the_codes():
    html = words(landing())
    lowest, highest = round(model.TARGET_HARDEST * 100), round(model.TARGET_EASIEST * 100)
    start = round(model.DEFAULT_TARGET * 100)
    assert f"Aimed at about {start}%," in html, "the sentence's aim is not model.DEFAULT_TARGET"
    assert f"The first five aim at {start}%." in html, "the starting aim is not model.DEFAULT_TARGET"
    assert f"from {lowest}% to {highest}%." in html, "the aim's range is not model's"
    ev, forward = web.EVALUATION, web.FORWARD
    assert f"log loss <b>{ev['model']:.4f}</b>, against <b>{ev['baseline']:.4f}</b> for rating alone." in html, \
        "the first measurement is not EVALUATION's"
    assert f"<b>{forward['model']:.4f}</b> against <b>{forward['baseline']:.4f}</b>." in html, \
        "the second measurement is not FORWARD's"


def the_training_count_is_the_models_own():
    """Both pages said "1.58 million", written in, and the first monthly
    refit would have left them describing the model before it (found
    2026-10-01, the day of that refit). The count is read from the fitted
    model, so a different model says a different number -- in the sentence,
    and to the last digit in the top bar."""
    fitted = model.current_topic_model()
    count = f"{fitted['attempts'] / 1_000_000:.2f} million"
    html = words(landing())
    assert f"{count} first attempts by 4,000 other users" in html, "the landing page's count is not the model's"
    assert f"learned from {fitted['attempts']:,} first attempts</p>" in html, "the top bar's count is not the model's"
    how = words(client.get("/how").get_data(as_text=True))
    assert f"and their {count} first attempts" in how, "the count on /how is not the model's"

    real = model.current_topic_model
    model.current_topic_model = lambda: {"attempts": 2_345_678}
    try:
        html = words(landing())
        assert "2.35 million first attempts by 4,000 other users" in html, "the landing page's count is written in"
        assert "learned from 2,345,678 first attempts</p>" in html, "the top bar's count is written in"
        how = words(client.get("/how").get_data(as_text=True))
        assert "and their 2.35 million first attempts" in how, "the count on /how is written in"
    finally:
        model.current_topic_model = real


def the_count_of_problems_is_the_fields_own():
    """The page says how many problems get a chance, twice. Both are the
    count in the file the browser is sent, so the words cannot say one
    number over a different number of dots."""
    assert web.field_count() == FIELD["count"], (web.field_count(), FIELD["count"])
    html = words(landing())
    assert f'<p class="facts">{FIELD["count"]:,} rated problems' in html, "the top bar's count is not the field's"
    assert f"All {FIELD['count']:,} get a chance." in html, "the sentence's count is not the field's"


def the_script_is_told_what_the_server_knows():
    """ridge.js re-picks five in the browser. Everything it does that with
    is handed to it from where the server reads it, so the page and the
    recommender cannot disagree about a number."""
    data = handed_to_the_script()
    baseline = model.current_baseline()
    assert data["curve"] == {"intercept": baseline["intercept"], "slope": baseline["slope"], "scale": model.SCALE}, \
        data["curve"]
    assert data["aim"] == model.DEFAULT_TARGET and data["band"] == model.BAND, (data["aim"], data["band"])
    assert data["sampleRating"] == web.SAMPLE_RATING
    assert [(p["contest"], p["index"], p["name"], p["rating"], p["p"]) for p in data["sample"]] == \
        [row[1:] for row in web.SAMPLE_PACK], "the script's sample is not SAMPLE_PACK"
    assert data["ranks"] == web.rank_spans(), "the script reads ranks from somewhere else"
    assert data["field"] == "/static/field.json" and data["three"] == "/static/vendor/three.module.min.js", \
        (data["field"], data["three"])


def the_scripts_sums_are_the_models():
    """The two sums the script repeats, as the model writes them: the chance
    from two ratings (model.baseline_probability), and the pick nearest the
    aim (model.recommend). Nothing about the fitted curve is written into
    the script: it has no number of its own to go stale after a refit."""
    assert "sigmoid(CURVE.intercept + CURVE.slope * (userRating - problemRating) / CURVE.scale)" in SCRIPT, \
        "the script's chance is not baseline_probability's"
    assert "Math.abs(chance(userRating, r) - AIM)" in SCRIPT, "the script does not pick nearest the aim"
    baseline = model.current_baseline()
    for number in (f"{baseline['intercept']}", f"{baseline['slope']}"):
        assert number not in SCRIPT, f"the fitted curve's {number} is written into the script"
    # And the sums agree where they can be compared here: the rating the
    # script would pick at 1491 is the one the server's own curve puts
    # nearest the aim.
    ratings = sorted(int(r) for r in FIELD["newest"])
    nearest = min(ratings, key=lambda r: abs(model.baseline_probability(web.SAMPLE_RATING, r) - model.DEFAULT_TARGET))
    picked = model.recommend(
        [{"id": f"{c}{i}", "contest_id": c, "problem_index": i, "name": n, "rating": r}
         for r in ratings for c, i, n in FIELD["newest"][str(r)]],
        web.SAMPLE_RATING, model.DEFAULT_TARGET)
    assert {p["rating"] for p in picked} == {nearest}, "rating alone picks from more than one rating"
    assert [[p["contest_id"], p["problem_index"], p["name"]] for p in picked] == FIELD["newest"][str(nearest)], \
        "the five field.json keeps at a rating are not the five recommend() picks there"


# -------------------------------------------------------------- the field
def the_field_file_adds_up():
    """static/field.json against itself: as many contests as it counts, the
    newest of them first at every rating and never out of order, `top` the
    newest of all, and the five kept at each rating the first five there."""
    total = top = 0
    for rating in FIELD["field"]:
        assert web.RATING_LOWEST <= int(rating) <= web.RATING_HIGHEST and int(rating) % 100 == 0, rating
        ids = contests_at(rating)
        assert ids == sorted(ids, reverse=True) and ids[-1] > 0, f"contests at {rating} are out of order"
        kept = FIELD["newest"][rating]
        assert [row[0] for row in kept] == ids[:collect.FIELD_NEWEST], f"the five kept at {rating} are not its newest"
        assert all(isinstance(row[1], str) and row[1] and isinstance(row[2], str) and row[2] for row in kept), rating
        total += len(ids)
        top = max(top, ids[0])
    assert total == FIELD["count"], f"{total} contests for a count of {FIELD['count']}"
    assert top == FIELD["top"], (top, FIELD["top"])
    assert set(FIELD["newest"]) == set(FIELD["field"]), "a rating with dots and no five, or the other way round"


def the_field_is_the_recommenders_pool():
    """collect.write_field on a small problemset: in it, exactly the
    problems anybody could be recommended -- in the problemset, rated, not
    *special -- newest contest first within a rating, then by id."""
    path = SCRATCH / "field.db"
    db.init_db(path)
    conn = db.connect(path)
    try:
        rows = [
            # id, contest, index, name, rating, in the problemset
            ("10A", 10, "A", "Oldest", 800, 1),
            ("30B", 30, "B", "Newest, second by id", 800, 1),
            ("30A", 30, "A", "Newest, first by id", 800, 1),
            ("20C", 20, "C", "Middle", 800, 1),
            ("40A", 40, "A", "Another rating", 1500, 1),
            ("50A", 50, "A", "No rating", None, 1),
            ("60A", 60, "A", "Not in the problemset", 800, 0),
            ("70A", 70, "A", "A special round", 800, 1),
        ]
        with conn:
            conn.executemany(
                "INSERT INTO problems (id, contest_id, problem_index, name, rating, in_problemset) "
                "VALUES (?, ?, ?, ?, ?, ?)", rows)
            conn.execute("INSERT INTO problem_tags (problem_id, tag) VALUES ('70A', '*special')")
            conn.execute("INSERT INTO problem_tags (problem_id, tag) VALUES ('10A', 'math')")
        out = SCRATCH / "field.json"
        count = collect.write_field(conn, out)
    finally:
        conn.close()
    written = json.loads(out.read_text(encoding="utf-8"))
    assert count == written["count"] == 5, f"{count} problems written"
    assert written["top"] == 40, written["top"]
    # 30, 30, 20, 10 as gaps down from the first.
    assert written["field"] == {"800": "30,0,10,10", "1500": "40"}, written["field"]
    assert written["newest"]["800"] == [[30, "A", "Newest, first by id"], [30, "B", "Newest, second by id"],
                                        [20, "C", "Middle"], [10, "A", "Oldest"]], written["newest"]["800"]
    assert not out.with_suffix(".json.tmp").exists(), "the half-written copy was left behind"


# ------------------------------------------------------------ the layers
def nothing_is_asked_of_another_server():
    """Spec 7.1: fonts and libraries are served from this site. Google Fonts
    and the script CDNs are unreliable in mainland China, where a large
    share of Codeforces users are."""
    html = landing()
    asked = re.findall(r'<(?:script|link|img)\b[^>]*?\b(?:src|href)="([^"]+)"', html)
    assert asked, "the page asks for nothing at all"
    elsewhere = [url for url in asked if not url.startswith("/static/")]
    assert not elsewhere, f"asked of another server, or not a static file: {elsewhere}"
    assert not re.search(r'url\(\s*["\']?(?:https?:)?//', CSS), "the stylesheet fetches from another server"
    hosts = set(re.findall(r"https?://([\w.-]+)", SCRIPT))
    # The one address in the script is where a problem's link goes: a place
    # a visitor is sent, not a file the page loads.
    assert hosts <= {"codeforces.com"}, f"the script names other servers: {hosts}"


def the_library_files_are_the_ones_recorded():
    """static/vendor/SOURCES.txt says where each library file came from and
    what its fingerprint was that day. A file that no longer matches was
    edited, or replaced without its record."""
    record = Path("static/vendor/SOURCES.txt").read_text(encoding="utf-8")
    recorded = re.findall(r"^  (\S+\.js)\s+[\d,]+ bytes\n    from\s+\S+\n    sha256\s+([0-9a-f]{64})", record, re.M)
    served = sorted(p.name for p in Path("static/vendor").glob("*.js"))
    assert sorted(name for name, _ in recorded) == served, f"recorded {recorded and [n for n, _ in recorded]}, served {served}"
    for name, fingerprint in recorded:
        actual = hashlib.sha256(Path("static/vendor", name).read_bytes()).hexdigest()
        assert actual == fingerprint, f"{name} is not the file that was recorded"


def the_3d_library_is_fetched_only_to_draw_with():
    """Layer 3 costs 167 KB compressed. The page itself never names the
    file; the script fetches it with import(), once, and only after the
    three cases that stop at the still: less motion asked for, saving data,
    no WebGL."""
    html = landing()
    named = [src for src in re.findall(r'<script[^>]*\bsrc="([^"]+)"', html) if "three" in src]
    assert not named, f"the page loads the 3D library for every visitor: {named}"
    # "import(" with something inside the brackets: the comments say import().
    assert re.findall(r"import\((?!\))[^)]*\)", SCRIPT) == ["import(DATA.three)"], "the library is fetched some other way"
    stop = "if (still || saving || !canDraw()) { settle(points); return; }"
    assert stop in SCRIPT, "the three cases that stop at the still are not together, or not all there"
    assert SCRIPT.index(stop) < SCRIPT.index("import(DATA.three)"), "the library is fetched before deciding to use it"
    # A device that fetched it and cannot use it still gets the still.
    assert "}).catch(function () { settle(points); });" in SCRIPT, "a failed fetch leaves no picture"
    # And the still never needs the library: it is drawn on a plain canvas.
    flat = SCRIPT[SCRIPT.index("function flat(points)"):SCRIPT.index("function live(THREE, points)")]
    assert 'getContext("2d")' in flat and "THREE" not in flat, "the still is not drawn without the library"


def the_frame_rate_is_measured_and_answered():
    """Spec 7.1, step 4: under 30 frames a second the field draws less, and
    still under, it steps down to the still. Checked as far as text can:
    the two answers exist, in that order, and the second is the still."""
    live = SCRIPT[SCRIPT.index("function live(THREE, points)"):]
    measure = live[live.index("function measure(now)"):live.index("function retire()")]
    assert "renderer.setPixelRatio(1)" in measure and "keepCap = 0.45" in measure, "nothing is drawn less"
    assert measure.index("renderer.setPixelRatio(1)") < measure.index("retire();"), "it gives up before drawing less"
    retire = live[live.index("function retire()"):live.index("function onResize()")]
    assert "settle(points);" in retire and "renderer.dispose();" in retire, "giving up does not leave the still"
    # A tab in the background is not a slow device.
    assert "document.hidden" in measure, "a hidden tab is measured as a slow one"


def the_picture_never_holds_the_form():
    """The card table delayed the form to play an animation. The ridge does
    not touch it at all: the form is the browser's own, sent the same with
    the script, without it, and while anything is still moving."""
    html = landing()
    form = re.search(r'<form class="handle-form" method="post" action="/">(.*?)</form>', html, re.S)
    assert form and '<button type="submit">Find my five</button>' in form.group(1), "the form or its button is gone"
    for word in ("submit", "preventDefault", "handle-form\")", "getElementById(\"handle\")"):
        assert word not in SCRIPT, f"ridge.js reaches for the form: {word}"
    # The one thing held back before the page is drawn is the headline, and
    # never for more than three seconds.
    held = re.findall(r"\.arriving ([^{]+)\{([^}]*)\}", CSS)
    assert [(selector.strip(), " ".join(body.split())) for selector, body in held] == \
        [(".headline", "visibility: hidden;")], f"more than the headline is held back: {held}"
    head = html[html.index("<head>"):html.index("</head>")]
    assert 'window.setTimeout(function () { root.classList.remove("arriving"); }, 3000);' in head, \
        "nothing lets the headline go if the script never arrives"
    assert head.index('if (seen || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;') \
        < head.index('root.classList.add("arriving")'), "somebody who asked for less motion still waits for it"


def the_page_stands_without_script():
    """Layer 1: with no script the page is its headline, its sentence, its
    form and the five. Everything only script can draw is not shown, rather
    than shown empty."""
    stage = re.search(r"\n\.stage \{([^}]*)\}", CSS).group(1)
    assert "display: none;" in stage, "the stage is laid out before there is anything to draw in it"
    assert re.search(r"\n\.js \.stage \{\s*display: flex;", CSS), "the stage never appears"
    assert 'root.classList.add("js");' in SCRIPT, "nothing tells the stylesheet the script is running"
    html = landing()
    assert html.index('<h1 class="headline">') < html.index('<p class="lede">') < html.index('<form class="handle-form"') \
        < html.index('<ol id="five">') < html.index('<div class="stage"'), "the page's words are not in reading order"
    # Every script is deferred or inert: none stands between the visitor and
    # the first screen.
    loaded = re.findall(r"<script\b([^>]*)\bsrc=", html)
    assert loaded and all("defer" in attributes for attributes in loaded), f"a script blocks the page: {loaded}"


def with_no_field_the_page_is_its_words():
    """No field file (or no fitted curve) is not an error: the page sends no
    script at all, leaves the numbers it cannot back out of its sentences,
    and is still the form and the sample."""
    empty = SCRATCH / "no-field"
    empty.mkdir()
    web.field_count.cache_clear()
    real = web.app.static_folder
    web.app.static_folder = str(empty)
    try:
        html = landing()
    finally:
        web.app.static_folder = real
        web.field_count.cache_clear()
    assert "<script defer" not in html and 'id="ridge-data"' not in html, "script is sent with nothing to draw"
    assert 'classList.add("arriving")' not in html, "the headline is held back for a script that is not coming"
    assert '<p class="facts">' not in html and "Every rated problem gets a chance." in words(html), \
        "a count is stated with no file behind it"
    assert '<button type="submit">Find my five</button>' in html and html.count('<li><a class="rank-') == 5, \
        "the form or the sample went with the field"


# ------------------------------------------------------------ the tokens
def every_text_colour_can_be_read():
    """WCAG's 4.5 to 1 for text, on every surface the text is drawn on. The
    card table, which the tool pages still wear: the table and its two
    panels, and the cream of a card. The ridge: the yellow ground, and the
    field to type in at rest and focused."""
    low = []
    for ink in ("--ink", "--soft", "--muted", "--accent", "--good", "--warn"):
        for ground in ("--bg", "--panel", "--panel-hover"):
            ratio = contrast(token(ink), token(ground))
            if ratio < 4.5:
                low.append(f"{ink} on {ground}: {ratio:.2f}")
    for ink in ["--card-ink", "--card-muted"] + [f"--t-{key}" for _, key, _ in web.RARITIES]:
        ratio = contrast(token(ink), token("--card"))
        if ratio < 4.5:
            low.append(f"{ink} on --card: {ratio:.2f}")
    ratio = contrast(token("--accent-ink"), token("--accent"))
    if ratio < 4.5:
        low.append(f"--accent-ink on --accent: {ratio:.2f}")

    for ink in ("--ink", "--soft", "--muted", "--warn"):
        for ground in ("--bg", "--panel", "--panel-hover"):
            ratio = contrast(ridge_token(ink), ridge_token(ground))
            if ratio < 4.5:
                low.append(f"the ridge's {ink} on {ground}: {ratio:.2f}")
    ratio = contrast(ridge_token("--accent-ink"), ridge_token("--accent"))
    if ratio < 4.5:
        low.append(f"the ridge's --accent-ink on --accent: {ratio:.2f}")
    assert not low, f"text below 4.5 to 1: {low}"


def every_rank_has_its_colours():
    missing = [f"--{kind}-{key}" for _, key, _ in web.RARITIES for kind in ("r", "t")
               if not re.search(r"--" + kind + "-" + key + r":\s*#", CSS)]
    missing += [f"the ridge's --r-{key}" for _, key, _ in web.RARITIES
                if not re.search(r"--r-" + key + r":\s*#", RIDGE)]
    missing += [f".rank-{key}" for _, key, _ in web.RARITIES
                if f".rank-{key} {{ --rank: var(--r-{key}); }}" not in CSS]
    assert not missing, f"a problem can be marked in a colour that does not exist: {missing}"


def a_rank_colour_is_a_mark_never_text():
    """On yellow, Codeforces's orange is 1.5 to 1 and its cyan 1.9: neither
    can be read. So in the ridge a rank colour only ever fills a small mark,
    and the mark has an edge in the colour of what it sits on, so it is
    still a shape where its fill is close to its ground."""
    assert not re.search(r"(?<![-\w])color:\s*var\(--rank\)", CSS), "a rank colour is used as the colour of text"
    for selector, edge in ((".sw", "outline: 1px solid var(--ink)"), (".flag i", "outline: 1px solid var(--bg)")):
        rule = re.search(r"\n" + re.escape(selector) + r" \{([^}]*)\}", CSS).group(1)
        assert "background: var(--rank)" in rule and edge in rule, f"{selector} is not a mark with an edge"
    assert "border: 1px solid var(--ink)" in re.search(r"\n\.ranks \{([^}]*)\}", CSS).group(1), \
        "the axis's ranks have no edge"


def every_font_travels_with_its_licence():
    """The SIL Open Font License asks for its text to go wherever the font
    files go. One licence file per family, each the OFL; and every file the
    stylesheet names is there to be served."""
    licences = {
        "IBM Plex Mono": "LICENSE.txt", "Unbounded": "LICENSE-Unbounded.txt", "Onest": "LICENSE-Onest.txt",
        "Sofia Sans": "LICENSE-SofiaSans.txt", "Sofia Sans Extra Condensed": "LICENSE-SofiaSans.txt",
    }
    families = set(re.findall(r'@font-face\s*\{[^}]*font-family:\s*"([^"]+)"', CSS))
    assert families == set(licences), f"families served: {sorted(families)}"
    for family, name in licences.items():
        text = Path("static/fonts", name).read_text(encoding="utf-8")
        assert "SIL Open Font License" in text, f"{name} is not the OFL"
    missing = [name for name in re.findall(r'url\("fonts/([^"]+)"\)', CSS) if not Path("static/fonts", name).exists()]
    assert not missing, f"the stylesheet names font files that are not there: {missing}"


def each_page_asks_early_for_the_faces_it_draws_in():
    """A preload is a download whether or not the page uses the file, so a
    page names its own two faces: the ridge's on the landing page, the card
    table's everywhere else. crossorigin, or the file is fetched twice."""
    def preloads(html):
        found = {}
        for attributes in re.findall(r'<link rel="preload"([^>]*)>', html):
            name = re.search(r'href="/static/fonts/([^"]+)"', attributes)
            assert name and 'as="font"' in attributes and "crossorigin" in attributes, \
                f"not preloaded as a font: {attributes}"
            found[name.group(1)] = True
        return sorted(found)

    assert preloads(landing()) == ["SofiaSans-Regular-Latin.woff2", "SofiaSansExtraCondensed-ExtraBold-Latin.woff2"], \
        preloads(landing())
    how = client.get("/how").get_data(as_text=True)
    assert preloads(how) == ["Onest-Latin.woff2", "Unbounded-Latin.woff2"], preloads(how)


def only_the_landing_page_wears_the_ridge():
    """The ridge is asked for with one class on <html>. The tool pages are
    still the card table until their own ground is decided (ADR 0031's
    amendment), and nothing in the ridge's block may reach them by
    accident."""
    assert '<html lang="en" class="ridge">' in landing(), "the landing page does not ask for the ridge"
    for path in ("/how", "/privacy"):
        page = client.get(path).get_data(as_text=True)
        assert '<html lang="en">' in page, f"{path} asks for the ridge"
        assert "Open pack" not in page or path != "/", path
    # The error page keeps the card table's words on its button.
    wrong = client.get("/results/this-is-not-a-handle-at-all-no")
    assert "Find my five" not in wrong.get_data(as_text=True), "the error page's button changed with the landing page's"


print("the sample")
check("a rating is read as the rank it would be", a_rating_is_read_as_the_rank_it_would_be)
check("the five rows are the sample pack", the_five_rows_are_the_sample_pack)
check("the sample is labelled a sample", the_sample_is_labelled_a_sample)
check("the sample pack is a real plan", the_sample_pack_is_a_real_plan)
check("the axis is the ranks, end to end", the_axis_is_the_ranks_end_to_end)

print("\nthe numbers")
check("every number is the code's", every_number_is_the_codes)
check("the training count is the model's own", the_training_count_is_the_models_own)
check("the count of problems is the field's own", the_count_of_problems_is_the_fields_own)
check("the script is told what the server knows", the_script_is_told_what_the_server_knows)
check("the script's sums are the model's", the_scripts_sums_are_the_models)

print("\nthe field")
check("the field file adds up", the_field_file_adds_up)
check("the field is the recommender's pool", the_field_is_the_recommenders_pool)

print("\nthe layers")
check("nothing is asked of another server", nothing_is_asked_of_another_server)
check("the library files are the ones recorded", the_library_files_are_the_ones_recorded)
check("the 3D library is fetched only to draw with", the_3d_library_is_fetched_only_to_draw_with)
check("the frame rate is measured and answered", the_frame_rate_is_measured_and_answered)
check("the picture never holds the form", the_picture_never_holds_the_form)
check("the page stands without script", the_page_stands_without_script)
check("with no field the page is its words", with_no_field_the_page_is_its_words)

print("\nthe tokens")
check("every text colour can be read", every_text_colour_can_be_read)
check("every rank has its colours", every_rank_has_its_colours)
check("a rank colour is a mark, never text", a_rank_colour_is_a_mark_never_text)
check("every font travels with its licence", every_font_travels_with_its_licence)
check("each page asks early for the faces it draws in", each_page_asks_early_for_the_faces_it_draws_in)
check("only the landing page wears the ridge", only_the_landing_page_wears_the_ridge)

shutil.rmtree(SCRATCH, ignore_errors=True)
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
