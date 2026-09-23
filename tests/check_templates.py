"""Check that no template prints its own comments onto the page.

A Jinja comment ends at the FIRST closing marker, and comments do not nest, so
writing that marker inside a comment silently spills the rest of it into the
HTML. That is not a syntax error and nothing warns about it -- the only way to
catch it is to render the page and look.

Makes no network calls: both pages are rejected before
web.py reaches the API.
"""

import os
import re
import sys
from pathlib import Path

# Paths in this file are relative to the repository root, and the modules
# being checked live there, so go there first. The check then runs the same
# from any directory.
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
from web import app  # noqa: E402

# Anything from inside a template comment, and the two comment markers.
LEAKS = ("{#", "#}", "{%", "Jinja comment", "would be sent", "url_for")

failed = 0
client = app.test_client()

print("rendered pages")
for path in ("/", "/how", "/results/!!!"):
    response = client.get(path)
    html = response.get_data(as_text=True)
    found = [marker for marker in LEAKS if marker in html]
    if found:
        print(f"  FAIL  {path}: the page contains {found}")
        failed += 1
    else:
        print(f"  ok    {path}: {response.status_code}, {len(html)} bytes, no template syntax on the page")

# The POST path renders the same base template with an error in it.
response = client.post("/", data={"handle": ""})
html = response.get_data(as_text=True)
found = [marker for marker in LEAKS if marker in html]
if found or response.status_code != 400:
    print(f"  FAIL  POST /: status {response.status_code}, contains {found}")
    failed += 1
else:
    print(f"  ok    POST / with an empty handle: 400, no template syntax on the page")

# ------------------------------------------------------------ no other servers
# Every resource a page needs comes from this site (spec section 7.1). Links
# TO Codeforces are fine; a stylesheet, font or script FROM elsewhere is not,
# because in some countries that one request stalls the whole page.
external = []
for path in ("/", "/how"):
    html = client.get(path).get_data(as_text=True)
    external += re.findall(r'<(?:link|script)[^>]+(?:href|src)="(https?://[^"]+)"', html)
if external:
    print(f"  FAIL  pages load resources from other servers: {external}")
    failed += 1
else:
    print("  ok    / and /how load nothing from another server (links out are fine)")

# ------------------------------------------------------------- the font files
# Every url() in an @font-face must be a real file, served as a font. A typo
# here fails silently: the browser just uses the fallback mono and says nothing.
css = Path("static/style.css").read_text(encoding="utf-8")
faces = re.findall(r"@font-face\s*\{[^}]*\}", css)
urls = [u for face in faces for u in re.findall(r'url\("?([^")]+)"?\)', face)]
problems = []
if len(faces) < 2:
    problems.append(f"expected an @font-face for each of two weights, found {len(faces)}")
for u in urls:
    path = "/static/" + u.removeprefix("./")
    r = client.get(path)
    body = r.get_data()
    if r.status_code != 200:
        problems.append(f"{path}: {r.status_code}")
    elif not body.startswith(b"wOF2"):
        problems.append(f"{path}: not a woff2 file")
    elif "woff2" not in r.headers.get("Content-Type", ""):
        problems.append(f"{path}: served as {r.headers.get('Content-Type')}")
if problems or not urls:
    print(f"  FAIL  font files: {problems or 'no url() in any @font-face'}")
    failed += 1
else:
    print(f"  ok    {len(urls)} font files exist and are served as font/woff2")

print(f"\n{6 - failed} passed, {failed} failed")
sys.exit(1 if failed else 0)
