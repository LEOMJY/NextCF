# NextCF

Tells a competitive programmer which Codeforces problem to solve next.

You enter your Codeforces handle. It reads your public submission history, works
out which topics you are strong and weak at, and recommends problems that should
be just hard enough — roughly a 70% chance you solve them.

---

## Status: v0.1, in progress

**Nothing on this page is finished yet.** What exists today is a command-line
script that fetches and prints one user's submissions. There is no web
interface, no database and no model.

| | |
|---|---|
| Works now | Fetch a handle's submissions from the Codeforces API and print them |
| Next | A web page with a handle input, deployed |
| Target for v1.0 | mid-November 2026 |

Full plan in [`docs/spec.md`](docs/spec.md); what has actually been tried and
broken is in [`docs/devlog.md`](docs/devlog.md).

## Why this exists

Codeforces lets you filter the problemset by rating, but that rating is the
average difficulty across everybody — not the difficulty for *you*. It doesn't
know you are fine at greedy and weak at trees. Static problem "ladders" have the
same issue: one list for everyone.

Other Codeforces recommenders do exist, and some are good. What none of them
publish is **evidence that their recommendations beat simply sorting the
problemset by rating.**

That measurement is the point of this project, not an appendix to it. v1.0 is
not done until the model scores a lower log loss than a rating-only baseline on
held-out submissions and **that number is written down publicly**. Skip it and
this is just a website — see [spec §9](docs/spec.md).

## Running it

Requires Python 3.14.

```bash
py -3.14 -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

```bash
.venv\Scripts\python.exe api_client.py tourist
```

Output:

```
tourist: 100 submissions

RATING  VERDICT                 PROBLEM
 3000  OK                      NPC Challenge
 2800  OK                      Familiar?
 2300  OK                      Tom and Jerry
 1700  OK                      Construct an Array (Easy Version)
```

The handle is optional and defaults to `tourist`. An unknown handle prints an
explanation rather than a stack trace.

> On Windows, use `py -3.14` rather than bare `py`. The launcher defaults to the
> free-threaded build (`3.14t`), which does not reliably have prebuilt packages
> for the scientific libraries this project needs later.

## Layout

```
api_client.py        Codeforces API access
requirements.txt     direct dependencies
docs/spec.md         what is being built, and what is deliberately excluded
docs/devlog.md       dated entries: what was tried, what broke, what was learned
docs/decisions/      one short file per significant technical decision (ADRs)
```

Modules still to come — `db.py`, `sync.py`, `collect.py`, `model.py`,
`evaluate.py`, `web.py`, `scheduler.py` — are described in
[spec §4](docs/spec.md).

## Stack

Python 3.14, Flask, SQLite, hand-written CSS. No JavaScript build step, no
frontend framework. Reasoning, and the list of things explicitly rejected, is in
[spec §7](docs/spec.md).

## Notes

- This site never runs, judges or sandboxes anybody's code. It reads outcomes
  from the public Codeforces API.
- Training data comes from strangers' public submission histories. A visitor's
  own history is used only to locate them inside a model learned from the crowd.
- There are no accounts and no passwords. A handle is the only identity.

## Author

Leo Ma. This is a learning project, built in the open, mistakes included.
