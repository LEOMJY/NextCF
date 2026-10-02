"""Check the card table -- the landing page and its tokens, ADR 0029.

No network, no database of any size: the landing page reads nothing but
constants. What these hold it to:

  * THE SAMPLE IS REAL, AND NEVER YOURS. The five cards are web.SAMPLE_PACK,
    drawn as the rest of the site would draw them, and labelled a sample.
  * EVERY NUMBER IS THE CODE'S. The target's limits, the calibration, the
    rating bands: computed from the constants the rest of the site uses, so
    the pitch cannot drift from /how or from what the recommender does.
  * THE PICTURE NEVER HOLDS THE FORM. The animation is decoration; the form
    is sent whether it plays, stalls or throws, and never sent twice.
  * EVERY COLOUR CAN BE READ. Text tokens against the table and the cards,
    at WCAG's 4.5 to 1.
"""

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


def landing():
    response = client.get("/")
    assert response.status_code == 200, response.status_code
    return response.get_data(as_text=True)


def token(name):
    """A colour token's value in style.css's :root, as #rrggbb."""
    value = re.search(r"(?<![\w-])" + re.escape(name) + r":\s*(#[0-9a-fA-F]{6});", CSS)
    assert value, f"no {name} colour in :root"
    return value.group(1)


def contrast(one, other):
    """WCAG's contrast ratio between two #rrggbb colours: 1 to 21."""
    def luminance(colour):
        channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    high, low = sorted((luminance(one), luminance(other)), reverse=True)
    return (high + 0.05) / (low + 0.05)


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


def the_five_cards_are_the_sample_pack():
    html = landing()
    cards = re.findall(r'<li class="card" style="--k: (-?\d); --frame: var\(--r-(\w+)\); '
                       r'--mark: var\(--t-(\w+)\)">(.*?)</li>', html, re.S)
    assert len(cards) == 5, f"{len(cards)} cards in the hand"
    assert [int(k) for k, _, _, _ in cards] == [-2, -1, 0, 1, 2], "the hand is not in order"
    for (_, frame, mark, body), (problem_id, name, rating, tags, chance) in zip(cards, web.SAMPLE_PACK):
        key, band = web.rarity(rating)
        assert frame == mark == key, f"{problem_id} is framed {frame}, not {key}"
        assert f'<span class="card-id">{problem_id}</span>' in body, problem_id
        assert f'<span class="card-rarity">{band}</span>' in body, (problem_id, band)
        assert f'<p class="card-rating">{rating}</p>' in body, (problem_id, rating)
        assert f'<p class="card-name">{name}</p>' in body, (problem_id, name)
        # The same rounding the results page uses for a chance (web.py,
        # "percent"), so the sample reads exactly as a real plan would.
        assert f"<b>{round(chance * 100)}<span>%</span></b>" in body, (problem_id, chance)
        for tag in tags:
            assert f"<span>{tag}</span>" in body, (problem_id, tag)


def the_sample_is_labelled_a_sample():
    """Never presented as the visitor's: the caption says whose it is not,
    and the pack the form fills is empty until the script writes the handle
    typed onto it -- no card ever comes out of it on this page."""
    html = landing()
    caption = re.search(r'<figcaption class="fan-caption">(.*?)</figcaption>', html, re.S)
    assert caption and caption.group(1).startswith("Sample pack"), "the fan is not called a sample"
    assert f"a real {web.SAMPLE_RATING}-rated history" in caption.group(1), caption.group(1)
    assert '<span class="pack-who" id="pack-who"></span>' in html, "the pack carries a name before anybody typed one"
    assert '<div class="pack" id="pack" hidden aria-hidden="true">' in html, "the pack is drawn before the form is sent"


def the_sample_pack_is_a_real_plan():
    """Five problems, none twice, each chance near the aim it was dealt at
    -- what a plan from choose_plan looks like, not a made-up hand."""
    ids = [problem_id for problem_id, *_ in web.SAMPLE_PACK]
    assert len(ids) == 5 and len(set(ids)) == 5, ids
    for problem_id, _, rating, _, chance in web.SAMPLE_PACK:
        assert abs(chance - web.SAMPLE_TARGET) < 0.05, f"{problem_id} at {chance} is far from its aim"
        assert 800 <= rating <= 3500 and rating % 100 == 0, (problem_id, rating)
    assert model.TARGET_HARDEST <= web.SAMPLE_TARGET <= model.TARGET_EASIEST, web.SAMPLE_TARGET


# ------------------------------------------------------------ the numbers
def every_number_is_the_codes():
    html = landing()
    lowest, highest = round(model.TARGET_HARDEST * 100), round(model.TARGET_EASIEST * 100)
    start = round(model.DEFAULT_TARGET * 100)
    assert f"The first is aimed at {start}%." in html, "the starting aim is not model.DEFAULT_TARGET"
    assert f"from {lowest}% to {highest}%." in html, "the aim's range is not model's"
    ev = web.EVALUATION
    dots = re.findall(r'<circle cx="([\d.]+)" cy="([\d.]+)" r="5">', html)
    assert len(dots) == len(ev["calibration"]), f"{len(dots)} dots for {len(ev['calibration'])} groups"
    for (cx, cy), (said, happened) in zip(dots, ev["calibration"]):
        assert abs(float(cx) - (30 + said * 2.4)) < 0.06 and abs(float(cy) - (250 - happened * 2.4)) < 0.06, \
            f"the dot for {said}% is drawn at ({cx}, {cy})"
    said, happened = min(ev["calibration"], key=lambda pair: abs(pair[0] - model.DEFAULT_TARGET * 100))
    assert f"When it said about {said:.0f}%, {happened}% were accepted." in html, "the quoted group is not the one nearest the aim"
    assert f"{ev['attempts']} first attempts" in html and f"off by\n          {ev['gap_model']} points" in html \
        and f"off by\n          {ev['gap_baseline']}." in html, "the calibration sentence is not EVALUATION's"


def the_training_count_is_the_models_own():
    """Both pages said "1.58 million", written in, and the first monthly
    refit would have left them describing the model before it (found
    2026-10-01, the day of that refit). The count is read from the fitted
    model, so a different model says a different number."""
    fitted = model.current_topic_model()
    count = f"{fitted['attempts'] / 1_000_000:.2f} million"
    assert f'<p class="big">{count}</p>' in landing(), "the landing page's count is not the model's"
    how = " ".join(client.get("/how").get_data(as_text=True).split())
    assert f"and their {count} first attempts" in how, "the count on /how is not the model's"

    real = model.current_topic_model
    model.current_topic_model = lambda: {"attempts": 2_345_678}
    try:
        assert '<p class="big">2.35 million</p>' in landing(), "the landing page's count is written in"
        how = " ".join(client.get("/how").get_data(as_text=True).split())
        assert "and their 2.35 million first attempts" in how, "the count on /how is written in"
    finally:
        model.current_topic_model = real


def the_bands_are_listed_as_ranges_with_no_gap():
    html = landing()
    spans = re.findall(r'<li class="tier" style="--frame: var\(--r-(\w+)\);[^"]*"><div><b>([^<]+)</b><span>([^<]+)</span>', html)
    assert [key for key, _, _ in spans] == [key for _, key, _ in web.RARITIES], "the tiers are not RARITIES in order"
    assert spans[0][2] == "below 1200" and spans[-1][2] == "2400 and up", (spans[0], spans[-1])
    # Each band starts where the one before stopped.
    for (_, _, before), (_, _, after) in zip(spans[1:-1], spans[2:-1]):
        assert int(before.split("–")[1]) + 1 == int(after.split("–")[0]), (before, after)


# ------------------------------------------------------------ the motion
def the_picture_never_holds_the_form():
    """The animation delays the form by about a second and a half. It must
    never do more: the two-second timer is set before anything animates, a
    throw sends at once, a second press is swallowed, and coming back to the
    page stops the timer that would send it again."""
    html = landing()
    script = html[html.index("// The card table's motion"):]
    handler = script[script.index('form.addEventListener("submit"'):script.index("function send()")]
    assert handler.index("timer = window.setTimeout(send, 2000);") < handler.index("packAway();"), \
        "the fallback timer is set after the animation starts, or not at all"
    assert "} catch (e) {\n          send();" in handler, "an error in the animation leaves the form unsent"
    assert "if (busy) return;" in handler, "a second press starts a second pack"
    send = script[script.index("function send()"):script.index("function packAway()")]
    assert "if (sent) return;" in send and "form.submit();" in send, "the form can be sent twice"
    restore = script[script.index('addEventListener("pageshow"'):]
    assert "window.clearTimeout(timer);" in restore, "a page restored from the back button sends the form again"
    # Asked for less motion: no animation, and the submit goes as it always did.
    assert script.index("if (still) return;") < script.index('form.addEventListener("submit"'), \
        "reduced motion still delays the form"
    assert "continue-link" not in script, "Continue as plays the pack (ADR 0029 keeps it a plain link)"


def the_script_measures_the_card_it_moves():
    """Found 2026-09-29: --cw is a clamp() on a wide screen, and a custom
    property reaches script as the text it was written with. Read with
    parseFloat it was NaN, and every animation on a desktop silently did
    nothing. The width is measured instead."""
    html = landing()
    script = html[html.index("// The card table's motion"):]
    assert 'token("--cw")' not in script, "the card's width is read from --cw again"
    assert "offsetWidth" in script, "the card's width is not measured"


def the_fan_stands_without_script():
    """The hand's places are in the stylesheet: a card's transform is built
    from its --k, so the fan is drawn with no script, and the script's own
    fan() is the same sum."""
    rule = re.search(r"\n\.card \{([^}]*)\}", CSS).group(1)
    for part in ("var(--k) * var(--spread) * var(--cw)", "var(--k) * var(--k) * var(--cw) * 0.025",
                 "var(--k) * var(--turn) * 1deg"):
        assert part in rule, f"the fan's transform lost {part}"
    html = landing()
    assert "(k * k * w * 0.025)" in html and 'k * w * token("--spread")' in html and 'k * token("--turn")' in html, \
        "the script's fan is not the stylesheet's"


# ------------------------------------------------------------ the tokens
def every_text_colour_can_be_read():
    """WCAG's 4.5 to 1 for text, on every surface the text is drawn on:
    the table and its two panels, and the cream of a card."""
    table = ["--bg", "--panel", "--panel-hover"]
    low = []
    for ink in ("--ink", "--soft", "--muted", "--accent", "--good", "--warn"):
        for ground in table:
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
    assert not low, f"text below 4.5 to 1: {low}"


def every_rank_has_its_two_colours():
    missing = [f"--{kind}-{key}" for _, key, _ in web.RARITIES for kind in ("r", "t")
               if not re.search(r"--" + kind + "-" + key + r":\s*#", CSS)]
    assert not missing, f"a card can be dealt in a colour that does not exist: {missing}"


def every_font_travels_with_its_licence():
    """The SIL Open Font License asks for its text to go wherever the font
    files go. One licence file per family, each the OFL."""
    licences = {"IBM Plex Mono": "LICENSE.txt", "Unbounded": "LICENSE-Unbounded.txt", "Onest": "LICENSE-Onest.txt"}
    families = set(re.findall(r'@font-face\s*\{[^}]*font-family:\s*"([^"]+)"', CSS))
    assert families == set(licences), f"families served: {sorted(families)}"
    for family, name in licences.items():
        text = Path("static/fonts", name).read_text(encoding="utf-8")
        assert "SIL Open Font License" in text, f"{name} is not the OFL"


def the_two_faces_every_page_uses_are_asked_for_early():
    html = landing()
    for name in ("Onest-Latin.woff2", "Unbounded-Latin.woff2"):
        link = re.search(r'<link rel="preload" href="/static/fonts/' + re.escape(name) + r'"([^>]*)>', html)
        assert link and 'as="font"' in link.group(1) and "crossorigin" in link.group(1), \
            f"{name} is not preloaded as a font (without crossorigin it is fetched twice)"


print("the sample")
check("a rating is read as the rank it would be", a_rating_is_read_as_the_rank_it_would_be)
check("the five cards are the sample pack", the_five_cards_are_the_sample_pack)
check("the sample is labelled a sample", the_sample_is_labelled_a_sample)
check("the sample pack is a real plan", the_sample_pack_is_a_real_plan)

print("\nthe numbers")
check("every number is the code's", every_number_is_the_codes)
check("the bands are listed as ranges with no gap", the_bands_are_listed_as_ranges_with_no_gap)
check("the training count is the model's own", the_training_count_is_the_models_own)

print("\nthe motion")
check("the picture never holds the form", the_picture_never_holds_the_form)
check("the script measures the card it moves", the_script_measures_the_card_it_moves)
check("the fan stands without script", the_fan_stands_without_script)

print("\nthe tokens")
check("every text colour can be read", every_text_colour_can_be_read)
check("every rank has its two colours", every_rank_has_its_two_colours)
check("every font travels with its licence", every_font_travels_with_its_licence)
check("the two faces every page uses are asked for early", the_two_faces_every_page_uses_are_asked_for_early)

shutil.rmtree(SCRATCH, ignore_errors=True)
print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
