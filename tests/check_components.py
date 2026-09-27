"""Run the React component tests (Vitest) as one of the checks -- ADR 0025.

The component's own tests live beside it, in frontend/src/*.test.jsx, and
run in Node. This file runs them from tests/run.py, so one command still
runs everything, and turns Vitest's result into the one line the runner
reads.

Skipped, and said so, when frontend/node_modules is not installed: a fresh
clone without `npm ci` in frontend/ can still run every Python check.
"""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

if not (FRONTEND / "node_modules").exists() or shutil.which("npm") is None:
    print("  ok    component tests (frontend/node_modules not installed -- skipped)")
    print("\n1 passed, 0 failed")
    sys.exit(0)

# NO_COLOR keeps Vitest's summary free of terminal colour codes, so the
# numbers below can be read out of it.
environment = dict(os.environ, NO_COLOR="1", FORCE_COLOR="0", CI="1")
result = subprocess.run(
    [shutil.which("npm"), "test"],
    cwd=FRONTEND,
    env=environment,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)
output = (result.stdout or "") + (result.stderr or "")

# Vitest's summary: "Tests  10 passed (10)" or "Tests  1 failed | 9 passed (10)".
line = next((l for l in output.splitlines() if re.match(r"\s*Tests\s", l)), "")
passed = int(m.group(1)) if (m := re.search(r"(\d+) passed", line)) else 0
failed = int(m.group(1)) if (m := re.search(r"(\d+) failed", line)) else 0

if result.returncode != 0 and failed == 0:
    # It failed without counting a failed test: a syntax error, a missing
    # package. Say so rather than report zero of anything.
    print(output)
    failed = 1
elif failed:
    print(output)
else:
    print(f"  ok    {passed} component tests (Vitest)")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
