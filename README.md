# NextCF

**<https://nextcf.onrender.com>**

Tells a competitive programmer which Codeforces problem to solve next.

You enter your Codeforces handle. It reads your public submission history,
shows how you do in each topic, and recommends five problems where your first
submission has about an even chance of being accepted — hard enough to teach
you something, and chosen from a model that is measured, not guessed.

---

## Status: v0.6 — the model works; `/how` next

| | |
|---|---|
| Works now | Enter a handle; the history is fetched in the background, then shown with a breakdown by topic and five recommended problems |
| The model | A logistic model of a first submission being accepted, learned from 4,000 other users: the problem's own record, its topics, the user's rating, their recent practice — [ADR 0014](docs/decisions/0014-topic-model.md), [ADR 0015](docs/decisions/0015-practice-history-and-computed-rating.md) |
| Measured | Log loss on the first attempts of 2026, which no model was fitted on: **0.5934** against a rating-only baseline's 0.6535, lower in every rating band ([spec §9](docs/spec.md)) |
| Collected (v0.3) | A dataset of 4000 users stratified by rating: 3.9 million submissions and every rating change, refreshed monthly |
| Next | `/how`, the page that explains the model and its number; then logging, error handling and tests (v0.7) |
| Target for v1.0 | mid-November 2026 |

Hosted on a free instance, which sleeps when idle — the first visit after a
quiet spell takes about half a minute to wake (measured at 31s after three weeks
of no traffic). Why that tradeoff was taken, and when it gets revisited, is in
[`docs/decisions/0003-hosting.md`](docs/decisions/0003-hosting.md).

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
held-out submissions and **that number is written down publicly**. It now is —
see [spec §9](docs/spec.md), and [ADR 0013](docs/decisions/0013-evaluation-protocol.md)
for how it was measured so that it could not flatter itself.

## Running it locally

The deployed copy is at <https://nextcf.onrender.com>. To run your own,
Python 3.14.

```bash
py -3.14 -m venv .venv
```

```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

```bash
.venv\Scripts\python.exe web.py
```

Then open <http://127.0.0.1:5000> and enter a handle. An unknown handle gets an
explanation and a way to retry, not a stack trace.

The same fetch also runs from the command line:

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
> free-threaded build (`3.14t`), which does not reliably have prebuilt packages.
> The model itself needs none: it is plain Python.

## Layout

```
web.py               routes and pages
templates/           the HTML, rendered by Jinja
api_client.py        Codeforces API access
db.py                the database: opening it, creating it, and every query
sync.py              fetches one user's history in the background
collect.py           draws, collects and refreshes the 4000-user dataset — see docs/decisions/0009-dataset-sample.md
model.py             the rating-only baseline and the topic model; fits a visitor into it
evaluate.py          the evaluation harness behind spec §9's number — see docs/decisions/0013-evaluation-protocol.md
baseline.json        the baseline's two fitted numbers
topic_model.json     the topic model's crowd part, refitted monthly
static/style.css     the whole design system — see docs/decisions/0006-design-direction.md
static/fonts/        IBM Plex Mono, served from this site, with its licence
schema.sql           the tables and the view — see docs/spec.md §6
serve.py             production entry point — see docs/decisions/0003-hosting.md
requirements.txt     direct dependencies
.python-version      pins the Python version for the host
docs/spec.md         what is being built, and what is deliberately excluded
docs/devlog.md       dated entries: what was tried, what broke, what was learned
docs/decisions/      one short file per significant technical decision (ADRs)
```

Still to come: `scheduler.py`, the nightly re-sync — see
[spec §4](docs/spec.md).

### Collecting the dataset

Runs on your own machine, into `dataset.db`, never on the server. Draw once,
then run until done — a full run is about four and a half hours, and it resumes
where it stopped:

```bash
.venv\Scripts\python.exe collect.py draw
```

```bash
.venv\Scripts\python.exe collect.py run
```

```bash
.venv\Scripts\python.exe collect.py status
```

Do not use the local site while it runs: each program keeps its own
two-second pace, and together they would go twice as fast as Codeforces allows.

Once a month the same users are fetched again and the model refitted, so it
knows the problems released since — about four and a half hours, resumable,
then about forty minutes of fitting:

```bash
.venv\Scripts\python.exe collect.py refresh
```

```bash
.venv\Scripts\python.exe model.py fit-topic
```

## Stack

Python 3.14, Flask, SQLite, hand-written CSS; the model is plain Python, with
no numerical libraries. Today there is no JavaScript build step and no frontend
framework; React components are planned for the interactive parts of pages
Flask still renders ([ADR 0008](docs/decisions/0008-react-islands.md)). Reasoning, and the list of things explicitly rejected, is in
[spec §7](docs/spec.md).

## Notes

- This site never runs, judges or sandboxes anybody's code. It reads outcomes
  from the public Codeforces API.
- Training data comes from strangers' public submission histories, collected
  into a separate file offline and never stored on the server. A visitor's own
  history is used only to locate them inside a model learned from the crowd.
- There are no accounts and no passwords. A handle is the only identity.

## Author

Leo Ma. This is a learning project, built in the open, mistakes included.
