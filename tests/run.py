"""Run the checks and say plainly what happened.

    python tests/run.py                everything that needs nothing outside
                                       this repository -- seconds
    python tests/run.py --dataset      also the checks that read dataset.db,
                                       680 MB on the author's machine; minutes
    python tests/run.py check_db       one check, by name

Each check runs in a process of its own, so one that crashes cannot take the
rest with it, and the temporary databases they build cannot collide.

The two API diagnostics are never run from here: they talk to Codeforces, and
they print a report rather than passing or failing. Run those by hand --
see docs/decisions/0019-checks-into-the-repository.md.
"""

import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
DIAGNOSTICS = {"check_mirrors.py", "check_problem_ids.py"}

# Every check ends with one line in this shape, and nothing else prints it.
SUMMARY = re.compile(r"(\d+) passed, (\d+) failed")

# A check that skips itself -- no dataset.db, or the dataset tier not asked
# for -- returns without asserting anything, so its own counter calls it
# passed. Counting the skips back out is the difference between "181 passed"
# and the truth.
SKIPPED = "-- skipped)"


def refuse_the_wrong_interpreter():
    """Stop if the dependencies are missing, instead of reporting nonsense.

    Measured by accident on 2026-09-22: run under a Python without Flask, four
    checks die on an import and two more report failures that look real -- 21
    passed 1 failed, 8 passed 3 failed -- because the code falls down paths the
    real environment never takes. A suite that can blame the code for its
    environment is worse than no suite, so this refuses to start.
    """
    missing = [name for name in ("flask", "waitress") if importlib.util.find_spec(name) is None]
    if missing:
        sys.exit(
            f"This interpreter is missing {' and '.join(missing)}, so the checks would\n"
            "fail for the wrong reason. Run them with the project's environment:\n"
            "    .venv\\Scripts\\python.exe tests/run.py\n"
            "README.md has the two commands that create it."
        )


def chosen_checks(arguments):
    """Which files to run: all of them, or the ones named on the command line."""
    named = [word for word in arguments if not word.startswith("-")]
    if not named:
        return [path.name for path in sorted(HERE.glob("check_*.py")) if path.name not in DIAGNOSTICS]

    chosen = []
    for word in named:
        name = word if word.endswith(".py") else word + ".py"
        if not (HERE / name).exists():
            sys.exit(f"No check called {name} in tests/")
        chosen.append(name)
    return chosen


def main():
    refuse_the_wrong_interpreter()
    arguments = sys.argv[1:]
    with_dataset = "--dataset" in arguments

    # The dataset checks read this; without it they skip that part and stay
    # fast enough to run on every change.
    environment = dict(os.environ)
    if with_dataset:
        environment["NEXTCF_TESTS_DATASET"] = "1"
    else:
        environment.pop("NEXTCF_TESTS_DATASET", None)

    # A backstop, not a substitute for each check setting its own database.
    # Since ADR 0017 merely rendering a page writes a visits row, so a check
    # that forgets would write into the real nextcf.db and inflate the one
    # number section 9 depends on. Here nothing can: the default points at a
    # file that is deleted when the run ends.
    scratch = Path(tempfile.mkdtemp(prefix="nextcf-tests-"))
    environment["NEXTCF_DB"] = str(scratch / "run.db")

    started = time.monotonic()
    passed = failed = skipped = 0
    went_wrong = []

    for name in chosen_checks(arguments):
        result = subprocess.run(
            [sys.executable, str(HERE / name)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
        )
        output = (result.stdout or "") + (result.stderr or "")
        matches = SUMMARY.findall(output)

        if not matches:
            # No summary line at all: the file died before it could count.
            print(f"  BROKEN {name:26s} no result (exit {result.returncode})")
            went_wrong.append((name, output))
            failed += 1
            continue

        here_passed, here_failed = (int(number) for number in matches[-1])
        here_skipped = output.count(SKIPPED)
        here_passed -= here_skipped
        passed += here_passed
        failed += here_failed
        skipped += here_skipped
        mark = "ok    " if here_failed == 0 and result.returncode == 0 else "FAILED"
        tail = f", {here_skipped} skipped" if here_skipped else ""
        print(f"  {mark} {name:26s} {here_passed} passed, {here_failed} failed{tail}")
        if here_failed or result.returncode:
            went_wrong.append((name, output))

    for name, output in went_wrong:
        print(f"\n{'-' * 70}\n{name}\n{'-' * 70}\n{output.rstrip()}")

    shutil.rmtree(scratch, ignore_errors=True)

    seconds = time.monotonic() - started
    tail = f", {skipped} skipped" if skipped else ""
    print(f"\n{passed} passed, {failed} failed{tail}, in {seconds:.1f}s")
    if not with_dataset:
        print("(dataset tier not run: python tests/run.py --dataset)")
    return 1 if failed or went_wrong else 0


if __name__ == "__main__":
    sys.exit(main())
