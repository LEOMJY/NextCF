"""Check the committed React bundle is the one its sources build -- ADR 0011.

The bundle (static/app/app.js) is built on the author's machine and
committed, because the host never runs Node. The risk that decision carries
is a component edited and never rebuilt: the site would run code that is not
in its own repository, and nothing would say so. So the build writes a hash
of its sources beside the bundle (frontend/vite.config.js), and this
recomputes the same hash from the working tree. They must agree.

Hashing the INPUTS, not rebuilding and comparing the output, because a build
is not byte-for-byte reproducible across machines and tool versions, and a
harmless upgrade of Vite must not fail a check (ADR 0011).

No Node needed here: the hash is recomputed in Python, by the rule the
config states.
"""

import hashlib
import os
import shutil
import sys
import tempfile
from pathlib import Path

SCRATCH = Path(tempfile.mkdtemp(prefix="bundle-"))
os.environ["NEXTCF_DB"] = str(SCRATCH / "test.db")
ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

FRONTEND = ROOT / "frontend"
BUNDLE = ROOT / "static" / "app" / "app.js"
RECORDED = ROOT / "static" / "app" / "sources.sha256"

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


def source_files(frontend):
    """The same list vite.config.js hashes: src/ without tests, and the three
    files that decide how it is built -- as sorted paths with "/"."""
    files = [p for p in (frontend / "src").rglob("*")
             if p.is_file() and not p.name.endswith((".test.jsx", ".test.js"))]
    files += [frontend / name for name in ("package.json", "package-lock.json", "vite.config.js")]
    return sorted(p.relative_to(frontend).as_posix() for p in files)


def source_hash(frontend):
    """vite.config.js's sourceHash(), in Python: path, newline, contents with
    CRLF turned into LF, newline -- for every file, in order."""
    digest = hashlib.sha256()
    for rel in source_files(frontend):
        text = (frontend / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
        digest.update((rel + "\n").encode("utf-8"))
        digest.update(text.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def the_bundle_is_committed():
    assert BUNDLE.exists() and BUNDLE.stat().st_size > 0, "static/app/app.js is missing -- run npm run build"
    assert RECORDED.exists(), "static/app/sources.sha256 is missing -- run npm run build"


def the_bundle_matches_its_sources():
    recorded = RECORDED.read_text(encoding="utf-8").strip()
    now = source_hash(FRONTEND)
    assert recorded == now, (
        "a component changed and the bundle was not rebuilt -- run `npm run build` in frontend/ "
        f"(built from {recorded[:12]}, sources are now {now[:12]})")


def the_hash_moves_when_a_source_does():
    """Otherwise the check above could pass for ever."""
    copy = SCRATCH / "frontend"
    shutil.copytree(FRONTEND, copy, ignore=shutil.ignore_patterns("node_modules"))
    before = source_hash(copy)
    target = copy / "src" / "Recommendations.jsx"
    target.write_text(target.read_text(encoding="utf-8") + "\n// an edit\n", encoding="utf-8")
    assert source_hash(copy) != before, "editing a component did not change the hash"


def line_endings_do_not_move_it():
    """git may check a file out with CRLF on one machine and LF on another."""
    copy = SCRATCH / "endings"
    shutil.copytree(FRONTEND, copy, ignore=shutil.ignore_patterns("node_modules"))
    before = source_hash(copy)
    for rel in source_files(copy):
        path = copy / rel
        lf = path.read_bytes().replace(b"\r\n", b"\n")
        path.write_bytes(lf.replace(b"\n", b"\r\n"))
    assert source_hash(copy) == before, "the same sources with CRLF gave a different hash"


def a_test_edit_does_not_count():
    """Tests are not in the bundle; editing one must not demand a rebuild."""
    copy = SCRATCH / "tests-only"
    shutil.copytree(FRONTEND, copy, ignore=shutil.ignore_patterns("node_modules"))
    before = source_hash(copy)
    test = copy / "src" / "TopicIsland.test.jsx"
    test.write_text(test.read_text(encoding="utf-8") + "\n// a note\n", encoding="utf-8")
    assert source_hash(copy) == before, "a test edit changed the bundle's hash"


def the_results_page_loads_it_and_the_site_serves_it():
    import web
    client = web.app.test_client()
    response = client.get("/static/app/app.js")
    assert response.status_code == 200, response.status_code
    assert "javascript" in response.headers.get("Content-Type", ""), response.headers.get("Content-Type")
    template = (ROOT / "templates" / "results.html").read_text(encoding="utf-8")
    assert "filename='app/app.js'" in template, "the results page does not load the bundle"


check("the bundle is committed", the_bundle_is_committed)
check("the bundle matches its sources (ADR 0011)", the_bundle_matches_its_sources)
check("the hash moves when a source does", the_hash_moves_when_a_source_does)
check("line endings do not move it", line_endings_do_not_move_it)
check("a test edit does not count", a_test_edit_does_not_count)
check("the results page loads it, and the site serves it", the_results_page_loads_it_and_the_site_serves_it)

print(f"\n{passed} passed, {failed} failed")
shutil.rmtree(SCRATCH, ignore_errors=True)
sys.exit(1 if failed else 0)
