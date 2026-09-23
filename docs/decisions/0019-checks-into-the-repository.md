# 0019 — The checks become the repository's test suite

**Date:** 2026-09-22
**Status:** accepted

## Context

The project has 181 pass/fail checks in 14 scripts, plus two read-only
diagnostics that print a report about Codeforces' API instead of passing or
failing. They were written beside the code they test, in the same sessions, and
each one tests a claim by making the failure happen: the leakage check changes
a user's later results and demands that no earlier prediction moves, the
staleness check hashes the component sources and fails when the working tree
disagrees, the separation check starts two real processes against a database
holding a running sync.

None of them has ever been in the repository. They live in a directory git
ignores, so from the repository's point of view this project has no tests at
all — while §10 schedules "tests" at v0.7 and the definition of done requires
them. The question at v0.7 is whether its tests are these, or something new
written beside them.

## Decision

**They move into `tests/`, in the repository, under the names they already
have.** Every document in `docs/` says "a check fails if …"; renaming them to
match a convention nobody here uses would make those sentences false.

**No test framework.** A runner script runs every check and prints one line
each and a summary. pytest would be a dependency, an installation and a second
idiom, in exchange for fixtures and parametrisation that 181 working assertions
have not needed.

**Three tiers, because they do not all need the same things:**

| tier | what it needs | when it runs |
|---|---|---|
| default | nothing outside the repository | every time code changes |
| dataset | `dataset.db`, 680 MB, on the author's machine; `check_visitor.py` alone takes about three minutes | before committing anything touching the model, the harness or the queries |
| diagnostics | the network | by hand, never inside a test run |

**Every file is read before it is committed.** The repository is this project's
public record, and a script that was convenient in a private directory is not
automatically fit to publish.

## Alternatives

**Write a fresh, smaller suite in the repository** and leave these outside.
Weaker coverage for the work of writing tests twice, and two sets that drift
apart within a week.

**Leave them outside and call v0.7's tests done.** The repository would have no
tests, the definition of done would not be met, and §9's stretch goal of
releasing the harness assumes somebody else can run it.

**Adopt pytest now.** Reopen if the suite grows shared setup a runner cannot
express, or if a machine other than this one starts running the tests and needs
the reporting.

**Run the default tier automatically on every push.** Genuinely attractive, and
the default tier is exactly the part that could: no large file, no network. Not
decided here — it needs a workflow file and a decision about what a failure
blocks, and it belongs with the deployment rather than with the tests.
Recorded as the obvious next step.

## Consequences

- **Sixteen files of test code enter the repository** and `dataset.db` does
  not, so the dataset tier only runs where the data is. That is a fact about
  the data, not a weakness in the tests.
- **The rules other decisions rest on become rules anybody can run**: the
  staleness hash (ADR 0011), `baseline.json` matching a refit (ADR 0012), the
  website building exactly what the harness builds (ADR 0014), the leakage
  checks (ADR 0013), the two-program separation (ADR 0007).
- **v0.7's new code gets its checks in the same place**: visit counting, the
  queue and its estimate, the scheduler, logging, error handling.
- **Checks that pass on their first run get tested by breaking the code on
  purpose.** Worth keeping now that they are public: a check nobody has seen
  fail is a check nobody has tested.
- **The default tier has to stay fast enough to run every time.** Anything slow
  belongs in the dataset tier, or it will quietly stop being run.
- **The runner refuses to start under an interpreter that lacks the
  dependencies.** Measured on 2026-09-22, by accident: run under the system
  Python instead of the project's environment, four scripts died on an import
  and two more reported 21 passed / 1 failed and 8 passed / 3 failed — numbers
  that
  read exactly like real defects and would have been chased as such. A suite
  that can lie about the code when the environment is wrong is worse than no
  suite, so the runner checks the environment first and stops with one
  sentence.
