# Development log

Dated entries: what was tried, what broke, what was learned. Newest at the
bottom.

---

## 2026-08-11 — Picked the project

Spent about a week deciding what to build instead of building. Worth writing
down why, because most of the value was in the rejections.

### What got rejected, and why

**Anything needing permission from the school.** An intramural league
scheduler, a course-selection planner, a club-conflict optimiser. All died the
same death: my school's schedules are fixed by administration and students
have no say, so there is no decision for software to support. Four ideas, one
cause. The lesson is that a project whose value depends on an adult saying yes
is not a project I control.

**A self-hosted judge with diagnostics.** Rejected on taste. The interesting
part was the algorithms — shrinking a failing test case to its smallest form,
estimating a solution's complexity empirically — but the bulk of the work is
sandboxing untrusted C++, Docker, and Linux operations, which I do not want to
spend a winter on.

**Mesh-to-papercraft unfolder.** Killed by thirty minutes of searching.
Blender already ships a Paper Model export add-on, papercraft-maker.com
exists, and polyzamboni has 10,000+ downloads against a 17,000-member
subreddit. I would have been the fourth entrant with no differentiator.

**Minecraft voxeliser.** Several converters already exist, and "I want my
model in Minecraft" is a want, not a problem.

### The origami one, which nearly won

The idea: take a 3D model, extract its structure automatically as a tree —
four legs, tail, neck, body — and generate a box-pleated origami base with
flaps matching that tree. Essentially TreeMaker, except the stick figure comes
from the model instead of being drawn by hand.

I liked this more than anything else and it survived five rounds of culling.
What killed it was looking at the actual tools:

- **TreeMaker** (Lang): you draw the tree, it packs circles and rivers.
- **Box Pleating Studio** (Tsai): you place the flaps, it generates the CP,
  including stretch gadgets. Its own manual says it exists "to help origami
  designers to blueprint their models" — the designer decides.
- **ExplOri 22.5**: you draw the tree, it searches a database of 22.5° crease
  patterns and ranks matches. Also generates reference-point folding
  sequences.
- **Origamizer** (Tachi/Demaine): reproduces a surface exactly, and the output
  is famously impractical to fold.

Three independent tools, three different folding systems, all taking a
hand-drawn tree as input. Nobody automates mesh → tree, so the gap is real —
but the reason nobody does it is visible in ExplOri's editor: drawing a
sixteen-node tree takes about three minutes. I would have spent four months
automating a three-minute task.

Posted on r/origami to check. Top reply pointed at Origamizer, which does not
do what I want, but the fact that a knowledgeable person's first instinct was
"that already exists" is its own signal — I would have spent the project's
life explaining the difference. Another commenter said the *opposite* tool
would be more useful: read a crease pattern, produce a folding sequence.
That is a real and much bigger pain, and also an open research problem. Noted
for later, not attempted now.

Broader lesson: computational geometry for fabrication is a mature research
field. Every problem I found interesting had a professor attached to it. That
is why I kept finding them interesting, and why I cannot win there in three
months.

### What I chose

A recommender for USACO students, built on Codeforces data. Spec is in
`docs/spec.md`.

It survives the tests that killed everything else: I am the user, so nobody's
permission is needed; the audience is reachable through channels I am already
part of; and the result is measurable without needing users at all, by
comparing the model against a rating-only baseline on held-out data.

Its weakness is originality — recommenders exist. The differentiator has to be
that I actually measure whether mine beats the obvious baseline, which nobody
competing appears to have published. If I skip that measurement, this is just
a website.

### Stack

Python, Flask, SQLite, deployed on Railway or Render. Reasoning in the spec.
Chosen for smallest number of new concepts between now and something running,
not for capability.

### Next

Build v0.1: enter a handle, see your submissions, deployed. Seven tasks,
starting with installing Python and getting a page to say hello.

---

## 2026-08-12 — Competitor found; architecture and scope revised

### CF Recommender exists and is mature

Found `cfrecommender.vercel.app` after about six minutes of searching. It does
the whole pipeline I had planned: reads your history, diagnoses weak topics,
calibrates difficulty, outputs a practice queue with solve-probability
estimates. Its Codeforces blog post has +82 and 43 comments, thirteen months
of iteration, and an "overwhelming response from users worldwide."

I am not going to out-feature that as a fourth entrant. What matters is what
the comments on that blog post say:

- The author states plainly that formulating a good weak-topic heuristic is
  what he struggled with, and that a user's suggested fix — accepted-to-
  submission ratio per topic — broke down for higher-rated users.
- A user diagnosed a concrete failure: they avoid DP, so they have few DP
  submissions, so the tool reports DP as a *strength*. Low attempt count read
  as high skill.
- The same user raised tag attribution: solving a problem tagged both `dp` and
  `greedy` using greedy still counts as DP evidence.
- In thirteen months nobody has published a single number showing the
  recommendations beat sorting by rating.

So the project narrowed. It is no longer "build a recommender." It is
**estimate per-topic skill properly and prove it works** — the piece the
incumbent publicly says is hard, with named failure modes to target.

Also relevant: I have 0 Codeforces submissions. I am not currently my own
user, which was this idea's biggest advantage. Fixing that by actually
practising on Codeforces starting now, which I need for Gold anyway.

### Audience widened

Switched from "USACO students" to Codeforces users generally. The tool
requires a Codeforces handle and many USACO students do not have one — an
audience that cannot supply the data the product needs is the wrong audience.
The cost of this is losing one of two differentiators, so measurement is now
the only one.

### Architecture: background jobs, not concurrency

Initial plan had the API fetching done concurrently to speed it up. That was
wrong. Codeforces rate-limits to roughly one request every two seconds, so
2000 users takes about an hour regardless of how many requests are in flight.
The rate limit dominates; concurrency buys nothing and would be complexity for
its own sake.

What the problem does demand: background jobs (an hour-long run cannot happen
inside a web request), resumability (a job that dies at minute 40 must not
restart at zero), rate limiting with backoff, and a nightly scheduler. Added a
`jobs` table and split the code into modules. Milestones extended by roughly
two weeks; v1.0 moves from late October to mid November.

### v2.0 written down rather than built

Knowledge tracing and bandits both belong in this project eventually — the
first makes the "you forgot segment trees" idea real, the second decides when
to recommend an untouched topic instead of a familiar one. Both recorded in
spec §11 and explicitly excluded from v1.0, because anything built there comes
out of the evaluation harness, which is the reason the project exists.

### Name

NextCF.

---

## 2026-08-12 — Pet system considered, scheduled for v1.5

Idea: earn coins by solving recommended problems, spend them on pixel-art pets
with growth stages. Inspired by Forest.

Kept rather than dismissed, for three reasons. Retention is the weakest of the
three v1.0 success criteria, and recommendation quality does not drive it — a
good recommendation makes the user leave for Codeforces. It differentiates
from the incumbent, which is a clean serious tool rather than a game. And it
produces a better experiment than the planned 70% difficulty test, because the
effect is larger and visible within weeks.

The design point that makes it non-trivial: reward has to scale as
`coins ∝ 1 − P(solve)` using this project's own model, or people farm
800-rated problems. That makes the economy depend on the probabilities being
well calibrated, which links the feature to the evaluation work instead of
sitting beside it.

Deferred to v1.5 because it needs user accounts (§5 currently excludes them),
because v1.0 is already at mid-November and this would push it into contest
season, and because gamification amplifies a working product rather than
rescuing a broken one — the model has to be good first.

---

## 2026-08-13 — Python installed; a tooling detour

### Python 3.14.7 is in

First task of v0.1 done. Installed from python.org, all-users
(`C:\Program Files\Python314`), with "Add to PATH" ticked. `pip` 26.2.1,
`sqlite3` 3.50.4 available from the standard library, so the database layer
needs nothing installed.

Pinned the version in spec §7, which previously just said "Python". The
deployed copy will need to match, and hosting platforms want the version
stated explicitly.

### python-lsp-server: attempted, abandoned, removed

Went looking for `python-lsp-server` thinking it was needed. It is a *language
server* — a background program the editor talks to for autocomplete, error
squiggles and go-to-definition, over a shared standard called LSP. The editor
itself is a text box and understands no language; the server does all of it.

The install was attempted and failed partway (see WinError 17 below), then
abandoned once it became clear it was redundant, and the partial install was
removed.

Redundant because VS Code's Python extension already ships **Pylance**, a
language server, and it was already installed here — `ms-python.vscode-pylance`
was in the extension list the whole time. Running two servers on one file means
every error reported twice.

The thing that made this click: C++ has had exactly the same arrangement on
this machine for years, invisibly. `ms-vscode.cpptools` bundles an 18 MB
`cpptools.exe`, which is what produces C++ autocomplete. It is *not* the
compiler — `g++` lives separately in MSYS2 and only runs on build. Two
programs, two independent ways to break, which is why "squiggles everywhere but
it compiles fine" is a real failure mode.

Python's equivalent is split across three extensions rather than one:
`ms-python.python` (finds interpreters and venvs), `ms-python.vscode-pylance`
(the language server), `ms-python.debugpy` (the debugger).

`python-lsp-server` is the right answer only for editors that cannot use
Pylance — Neovim, Helix, Emacs — since Pylance is licensed to Microsoft's build
of VS Code. Revisit only if the editor changes. The switch, if ever needed, is
the `python.languageServer` setting, which accepts `Default | Jedi | Pylance |
None`.

### Open: WinError 17 on pip install --user

`pip install --user` died with `[WinError 17] The system cannot move the file to
a different disk drive` while renaming a file *inside a single directory* under
`AppData\Roaming`. `TEMP` and the target are both on `C:`, so the plain
cross-drive explanation does not hold — something is redirecting that path, most
likely OneDrive folder backup.

Not diagnosed yet, and it is not cosmetic: the same call fails the same way for
`pip install flask`. Resolve before setting up the virtual environment.

### Free-threaded build is the launcher default

`py --list` shows `3.14t` (free-threaded, no GIL) marked as default ahead of
the standard build. Free-threaded is a separate binary target and prebuilt
packages for the scientific stack are not always published for it. Nothing is
broken today, but a virtual environment created from the bare launcher default
could fail to install numpy later, with an error that does not obviously point
at this cause. Recorded as a known risk in spec §7.

### Cleaning up a wrong install

Installed Python 3.13 through winget before settling on 3.14, then removed it
again. Worth recording that `winget uninstall` is not a complete uninstall: it
left empty folders and `HKCU\SOFTWARE\Python` registry keys behind, both of
which had to be cleared by hand. Verified clean afterwards.

### Next

Still v0.1: virtual environment, install Flask, get a page to say hello.

Note: the first script does not need Flask or any third-party package.
`urllib.request` and `json` are both in the standard library, so step one can be
written and run today despite `pip` being broken — fetch one user's submissions
from `user.status` and print them.

---

## 2026-08-12 — Where depth matters, and where it does not

Stopped treating every part of this codebase as equally worth understanding
deeply. Shipping is the priority right now, and the depth-versus-speed
trade-off is better managed per part than enforced across everything.

The line I actually care about: the skill model, the evaluation harness and the
data pipeline are mine to understand, because that is the part of this project
that is not interchangeable, and the part that cannot be debugged without
understanding it. Flask boilerplate, CSS and page layout are delivery
mechanism.

What replaced it is a graduated standard. Boilerplate and CSS get
written and moved past. The API client, rate limiting and background jobs get
read properly, because their failures are silent and specific to this project.
The model, harness and calibration get understood line by line, because a log
loss worse than the baseline cannot be fixed by rewriting the code — that
debugging requires understanding it.

The point is that a single standard applied to both Flask templates and the
evaluation harness treats interchangeable plumbing and the actual contribution
as the same thing, which they are not.

---

## 2026-08-14 — Design promoted to a v1.0 goal

Decided the site must not read as a high-school project, and that the previous
plan — Pico.css plus one design pass at v0.8 — was too weak for that.

My instinct was that this needed "interactive things". That turned out to be
backwards, and it is the useful thing I learned today: **over-animation is a
stronger amateur signal than plainness.** Scroll-triggered entrances, parallax,
particle backgrounds and page transitions read as "someone found a library". The
sites that actually look expensive — Stripe's docs, Linear, Vercel, Tailwind —
are *less* interactive than amateur ones, not more.

What actually causes the amateur read is static and boring to fix: default
fonts, ad-hoc spacing, pure black on pure white, no type hierarchy, and
unhandled states. A Flask traceback when someone mistypes a handle is the
loudest tell of the lot.

So the changes are mostly about restraint, not addition:

- Design tokens move to **v0.1**, not v0.8 — type scale, spacing scale, one
  neutral ramp plus one accent, one typeface, nothing outside the scale.
  Retrofitting spacing across templates later is expensive; polish applied late
  is cheap.
- **Dropped Pico.css** in favour of own CSS. A classless framework gives a floor
  for free but also a recognisable look, and "not templated" is now the goal.
- **Topic-breakdown chart as server-rendered SVG** from Jinja, no chart library,
  promoted to a v0.4 deliverable. It is the one element on the site a template
  cannot produce, and it is the differentiator made visible.
- Three interactive elements total, all justified by the product: that chart,
  the progress page, and the solve probability on each recommendation.
- Everything decorative explicitly out until v1.5.

Written up as `docs/decisions/0001-design-as-a-v1-goal.md` — the first ADR in
this repo, which the definition of done has been asking for since day one.

### The cost, written down so it cannot be quietly forgotten

Budget is roughly 15 hours and it comes out of §9. The tiebreak is stated in
both the spec and the ADR: **if the budget overruns, design stops, not §9.**

§11 already warns that the pet system is "more enjoyable to build than debugging
a likelihood function" and needs a fixed slot rather than an open-ended one.
Design is the same trap wearing a different costume, arriving seven months
earlier. Hence the number.

Also worth keeping in view: for this product the strongest signal of seriousness
is not the CSS, it is publishing a number nobody else has published. Design gets
people to look. §9 is what they find.

### Still true

`.py` files in this repo: 0. v0.1 due end of August, and it now includes the
base stylesheet as well as the handle form.

### Same-day correction to the above

Pushed back on three of the four things that had been written into the spec,
and was right to on all three.

**"Over-animation reads as amateur" was wrong.** I showed the GSAP showcase —
bleibtgleich'26, Nodeck, Bombon, Era Residence — and asked whether that counts
as over-animation. It does not. Those are professional studio sites and they are
excellent. Bad animation reads as amateur; animation does not.

What replaced the bad rule is a better distinction, and it is the useful thing
that came out of this: **the landing page and the tool are different surfaces
with different jobs.** The landing page has to convince a stranger to spend
thirty seconds, and it is the screenshot that goes in the Codeforces blog post —
expressive work belongs there. The progress and results pages are read by
someone under time pressure who wants to leave for Codeforces, and motion there
costs attention and returns nothing. Linear's marketing site is animated; the
Linear app is not.

**The exact token numbers were invented.** 4/8/16/24/48/96 and "exactly one
accent colour" were written in as a rule. They are one reasonable system,
and the one-accent part is contradicted by the showcase sites, which commit hard
to two or three. The real requirement is that a system exists and does not get
broken. Which system is mine to pick.

**Tokens in v0.1 was wrong.** It silently grew v0.1 without changing the
deadline. Moved to v0.2, where it pairs with the progress page anyway. v0.1
answers one question: does this run.

**The 15-hour budget was invented too**, so the number is withdrawn until it is
estimated properly. I kept the mechanism — the budget comes out of §9, and if it
overruns design stops. That is the strictest option and I chose it deliberately,
for the reason §11 already gives about the pet system: this kind of work has no
natural stopping point.

ADR 0001 amended in place with all four corrections and the general lesson:
personal defaults stated in the imperative are indistinguishable from real
constraints, and end up in the spec as if they were.

What I actually want, now written down properly: an expressive landing page, and
a tool that is fast and calm.

---

## 2026-08-14 — Site structure decided; landing page added to the spec

§4's diagram never had a landing page. It went `browser -> enter handle`, which
quietly assumed the tool *was* the site. Fixed.

### Five pages

`/`, `/progress/<job>`, `/results/<handle>`, `/how`, `/privacy`. Written up in
spec §4.1, with reasoning in `docs/decisions/0002-site-structure.md`.

My idea was one landing page holding everything — the pitch, how it works,
privacy, per-version notes — with a link to skip into the tool if you just want
to work. Two changes came out of discussing it.

**The handle input goes in the hero itself**, not behind a skip link. The reason
is §9: it needs 20 people to come back a *second* time, and a returning visitor
does not want the pitch again. With the input in the hero, one page serves both
— the returner types immediately and never scrolls, the newcomer scrolls past it
for the argument. A skip link would charge a click on every visit forever.

The cost, accepted: the hero has to hold a strong visual statement *and* a form
field at the same time. That is harder to compose than either alone.

**Privacy and how-it-works get their own pages.** A page that is simultaneously a
sales pitch and a privacy policy is neither, and splitting them lets the pitch
stay short, which is most of what makes a pitch work.

### `/how` is a v1.0 requirement

Not an appendix. §3 says measurement is the only differentiator, so the §9
number needs a permanent address on the site instead of living only in a
Codeforces blog post that scrolls away. Someone deciding whether to trust the
recommendations should reach that in one click. Scheduled at v0.6, because
that is when the number first exists.

### Changelog cut

Wanted per-version notes on the site. Cut to v2.0 and written into §5. Nobody
with 50 users reads release notes — it looks professional while being a way to
feel productive without shipping. A footer line if I still want it later.

### Style

One token set across both surfaces, used loudly on `/` and quietly in the tool,
so they read as one product rather than two websites. The failure mode to watch
for is the two drifting into different visual languages.

### Still true

`.py` files: 0. v0.1 is now two pages instead of one — both allowed to be crude —
and still due end of August.

---

## 2026-08-14 — WinError 17 diagnosed; it was never OneDrive

### The previous diagnosis was a guess, and it was wrong

The 08-13 entry blamed OneDrive folder backup for `pip install --user` dying with
`[WinError 17] The system cannot move the file to a different disk drive`. Not
true. `%APPDATA%` is `C:\Users\leoma\AppData\Roaming`, and the registry key that
records folder redirection —
`HKCU\...\Explorer\User Shell Folders` — redirects only Desktop, Documents and
Pictures into OneDrive. AppData is untouched.

### What it actually is

The terminal I had been running pip from was hosted inside a **packaged-app
container** (MSIX): a Windows sandbox that hands an application a private view
of the filesystem, so writes to some paths are silently redirected somewhere
else. Measured directly rather than assumed — a file written to

```
C:\Users\leoma\AppData\Roaming\_vtest\marker.txt
```

physically appeared at

```
D:\WpSystem\<SID>\AppData\Local\Packages\<package-id>\LocalCache\Roaming\_vtest\marker.txt
```

The path says `C:`. The bytes are on `D:`.

That is the whole bug. The last step of every pip install is renaming a staged
file into its final home. Under AppData one side of that rename resolves to the
real `C:` and the other to the redirected copy on `D:`. Windows sees a rename
across two volumes — which is not a rename, it is a copy plus a delete — and
returns `ERROR_NOT_SAME_DEVICE`, which Python reports as WinError 17.

It also explains the detail that made no sense before: the failure happened
"inside a single directory". It only looked like a single directory.

A probe over seven rename combinations matches this exactly — every rename with
one end under AppData failed, every rename with both ends in a plain directory
succeeded:

| Rename | Result |
|---|---|
| within `%TEMP%` (not redirected) | OK |
| within the project folder on `D:` | OK |
| within `%APPDATA%` — same directory | **WinError 17** |
| `%TEMP%` → `%APPDATA%` | **WinError 17** |
| `%TEMP%` → `%LOCALAPPDATA%` | **WinError 17** |
| `%APPDATA%` → `%TEMP%` | **WinError 17** |
| `%TEMP%` → `D:` (a genuine cross-volume move) | **WinError 17** |

### Not yet confirmed: whether my own terminal has this problem at all

Everything above was measured from inside the container, so it says nothing about
a normal PowerShell window. `pip install --user` may well work fine there. Worth
one command to find out, but it does not block anything, because the fix below is
what I wanted regardless.

### The fix, verified end to end

A **virtual environment** — a private folder holding its own copy of Python and
its own installed packages, so projects cannot break each other — placed inside
the project on `D:`. It never touches AppData, so the redirection cannot apply.

Created one in a throwaway folder on `D:` and installed Flask into it
with no workarounds, no environment variables, nothing special. Exit code 0.
Flask 3.1.3 imports and constructs an app object. Probe deleted afterwards.

This also confirms the free-threaded risk recorded in spec §7 is real and is
handled by naming the interpreter explicitly. The venv built from the standard
3.14 build pulled `markupsafe-3.0.3-cp314-cp314-win_amd64.whl` — a prebuilt
binary. `cp314`, not `cp314t`. `py` on its own still defaults to `3.14t`, so
environments get created with `py -3.14`, never bare `py`.

### Separately: AppData is EFS-encrypted and the key is missing

Turned up while chasing this and unrelated to pip. Both
`C:\Users\leoma\AppData\Roaming` and `...\AppData\Local` carry the EFS
(Encrypting File System) attribute, and `cipher /c` reports:

```
E Roaming
  Key information cannot be retrieved.
```

If that is accurate on the real filesystem and not an artifact of the container,
it is a data-loss risk with nothing to do with this project: files encrypted with
a key that cannot be produced are unreadable after a Windows reinstall or a
profile reset. Flagged, not acted on. Check from a normal terminal before doing
anything about it.

### Added `.gitignore`

The repo had none, and the venv would have been the first thing committed by
accident. Ignores `.venv/`, `__pycache__/`, `*.db` and `.env`. The database is
generated data and the venv is rebuilt from `requirements.txt`; neither is source.

### Lesson

Two sessions of "it's probably OneDrive" cost more than ten minutes of measuring
would have. The tell was there in the original error and got explained away: a
rename inside one directory cannot fail with a cross-device error, so the
directory was not one directory. When the evidence contradicts the theory, the
theory is wrong — do not invent a mechanism to rescue it.

### Next

Unchanged, and now actually unblocked: virtual environment, Flask, a page that
says hello. Step one still needs no third-party package at all — `urllib.request`
and `json` are standard library, so fetching one user's submissions from
`user.status` can be written first.

---

## 2026-08-14 — Repo published

<https://github.com/LEOMJY/NextCF> — public, 22 commits of history intact.

Created the empty repo through the browser instead of installing the GitHub CLI.
One less thing on the machine for a five-minute job. Left "add a README", "add
.gitignore" and "choose a license" all unticked: any of them puts a commit on
GitHub's side that my local history does not share, and the push then fails with
an error about unrelated histories.

Renamed the branch `master` → `main` before pushing, matching what GitHub has
defaulted to for years.

The point of pushing history rather than uploading files: 22 dated commits are
the evidence this was built over weeks and revised when the evidence said so.
Uploading a folder through the web form publishes the code and throws all of
that away.

### Added before publishing

- `README.md` — says v0.1 plainly. A CLI script, no web interface, no model. Its
  example output was verified by running the script rather than written from
  memory, which caught two wrong claims (100 submissions, not 10, and a column
  a space narrower than written). Writing down output you did not actually see
  is how a README starts lying.
- `requirements.txt` — Flask only. pip resolves the other seven.
- `.gitignore` extended to cover local editor and tooling config, which was
  untracked but *not ignored* — a stray `git add .` would have published
  machine-specific paths. Untracked is not the same as safe.

### Checked before making it public

Audited every tracked file. Nothing sensitive, no keys anywhere. The devlog
stays candid about mistakes — it is a record, not a brochure, and the mistakes
are the part worth reading.

### Known defect, not yet fixed

The results table is misaligned: `RATING` is six characters, the values format
to five, so every row sits one column left of its header. Two separate `>5`
literals in `api_client.py` encode one shared value, which is the actual defect —
they will drift. Wants a module-level constant. Cosmetic now, not cosmetic at
v0.4 when that table *is* the product.

### Open

No LICENSE file, so the default is "all rights reserved". That directly
contradicts the spec §9 stretch goal of releasing the dataset and harness for
other people to measure against — nobody can legally build on a repo with no
licence. Decide before v1.0.

Hosting is now unblocked: spec §7 picks Railway or Render, and both deploy from
GitHub on push.

---

## 2026-08-14 — First code: `api_client.py`

`.py` files: **1**. The venv exists in the project folder, built with
`py -3.14` explicitly, and Flask 3.1.3 installed into it without incident.

### Layout decided

Modules sit flat at the repo root, as spec §4 already listed them — not nested
in a package folder. At eight files a package buys nothing but import
ceremony. `templates/` and `static/` will be separate directories only because
Flask requires those exact names.

### The bug worth remembering

First version caught `urllib.error.URLError` and printed
`could not reach Codeforces: Bad Request` for a handle that does not exist.
Both halves of that sentence are wrong.

Codeforces does **not** answer `200 OK` with `status: FAILED` for a bad handle,
which is what the code assumed and what its comment claimed. It answers
**HTTP 400**, which makes `urlopen` raise before the body is ever parsed — and
the actual explanation is in the body of that error response:

```
{"status":"FAILED","comment":"handle: User with handle nosuchuser42qq not found"}
```

`HTTPError` is itself readable like a response, so the fix is to catch it and
`.read()` it. Now prints
`Codeforces rejected the request: handle: User with handle nosuchuser42qq not found`.

This is the failure mode this file is most exposed to: it
did not crash, it did not produce a stack trace, and the wrong explanation was
sitting in a code comment that read as authoritative. The only reason it was
caught is that the bad-handle path was actually run instead of assumed to work.

Also relevant to §7.1, which calls an unhandled traceback on a mistyped handle
the loudest amateur tell on the site: the message that will eventually reach
the browser now says what was wrong with the input.

### Scope held

No rate limiting, retries or backoff yet — v0.3, per spec §4. `count=100` is
hardcoded; paging through a full history comes with `sync.py` at v0.2.

### Next

`requirements.txt` (via `pip freeze`) so a host can rebuild the venv, then
`web.py` — one route, one template, the handle form. That is v0.1 done bar
deployment.

---

## 2026-08-15 — `web.py`: the site exists

`.py` files: **2**. Two routes, five templates, no CSS. Everything v0.1 asked
for except being deployed.

```
GET  /                 the pitch and the handle input
POST /                 read the field, redirect
GET  /results/<handle> the table
```

### The handle goes in the URL, not in the form submission

The obvious version renders the results straight out of the POST. I did the
POST → redirect → GET version instead, so submitting the form sends the browser
to `/results/tourist` and the table is served from there.

The reason is that a URL containing the handle is bookmarkable, shareable and
safe to reload, and one rendered out of a POST is none of those — reloading it
re-submits the form, which is where the "Confirm Form Resubmission" dialog comes
from. Spec §4.1 had already written `/results/<handle>` as the URL, so this was
really just a matter of building what the spec said rather than what was
shortest.

Used `url_for()` everywhere instead of writing `/results/` as a string. Rename a
route later and every `url_for` follows it; every hardcoded path silently 404s.

### `required` on the input is not validation

The field has `required` and `maxlength`, and both are enforced by the browser
and only by the browser. Nothing stops a request arriving at that URL without
ever loading the page, so the empty check happens again in Python on arrival.
Obvious once stated, easy to not state.

Same reasoning produced a handle pattern check before the API call — cheap junk
filter, deliberately permissive, and explicitly not authoritative, since
Codeforces is what decides whether a handle is real.

### No tracebacks reach the browser

§7.1 calls a Flask traceback on a mistyped handle the loudest amateur tell on
the site, so the two failure paths from `api_client` get real pages and honest
status codes:

| What happened | Page says | Status |
|---|---|---|
| Handle does not exist | Codeforces' own explanation | 404 |
| Network unreachable | could not reach Codeforces | 502 |

502 rather than 404 for the network case because the user did nothing wrong —
4xx means "your request was bad", 5xx means "my end failed". The error page
brings the form back with the bad value still in it, so a typo is one keystroke
from fixed.

Ordering trap noted in a comment: `HTTPError` is a *subclass* of `URLError`, so
if it ever escaped `api_client` the wrong `except` would swallow it. It does
not today, but that is a fact about the other file.

### Templates stay dumb

Deciding what to show for a missing rating happens in `display_row()` in Python,
not in the template. A template that makes decisions is program logic living
somewhere I cannot step through in a debugger.

That does mean the "these fields are sometimes absent" knowledge is now written
in both `api_client.py` and `web.py`. Fine at two call sites; it comes out into
one place when `sync.py` becomes the third.

One thing I nearly got wrong: the missing-rating test is `is not none`, not
`if row.rating`, because `0` is falsy and would print as missing. No Codeforces
problem is rated 0, so it would have worked — a truth test that happens to work
on today's data is a bug with a delay on it.

### Verified rather than assumed

Ran all six paths through Flask's test client, including both failures, before
writing any of this down: `/` renders the form, an empty submission is 400, a
good one redirects to `/results/tourist`, junk input and a nonexistent handle
are both 404 with an explanation, `tourist` returns a table of 100 rows. Also
checked that `/results/<script>` renders escaped — Jinja does that by default,
which is the actual reason not to build HTML with f-strings.

### Deliberately not done

No stylesheet at all. Design tokens are v0.2 and v0.1 answers one question:
does this run. Every request also blocks on a Codeforces call for as long as
that takes — which is exactly the problem the background job and progress page
exist to solve, also v0.2.

### Next

Deployment, which is the last thing v0.1 needs. `app.run(debug=True)` is the
local path only — the debug traceback page has an interactive console in it,
which is remote code execution for anyone who can load it. A host runs the app
under a production server instead.

---

## 2026-08-15 — Deployment prepared: Render and Waitress

Picked the two things §7 had left open as "Railway or Render", written up in
`docs/decisions/0003-hosting.md`.

**Render** over Railway, for a boring reason: Railway's free allowance is trial
credit, and the three months between now and v1.0 are months where nobody is
visiting. Paying for idle capacity during development is the wrong place to
spend money on this. The cost of that choice is that Render's free tier sleeps
when idle, so the first visitor after a quiet spell waits about a minute — and
that lands in exactly the wrong place, since §9 needs 50 strangers arriving at
once from a blog post. Recorded as something to revisit *before launch*, not
before then.

**Waitress** over gunicorn, which is the more standard answer, because gunicorn
does not run on Windows. That would mean the production setup could only ever be
tested by deploying it. Waitress runs the same command on both machines, so
"works locally, breaks on the host" becomes a class of failure I find out about
before pushing rather than after.

### What was actually missing from the code

Three things, none of them in `web.py`:

1. **A real server.** The dev server warning is not boilerplate — it serves one
   request at a time, and debug mode's traceback page has an interactive Python
   console in it.
2. **The port.** `app.run()` hardcodes 5000. A host assigns a port at launch and
   announces it in an environment variable, so it has to be read at runtime.
3. **The interface.** The dev server binds `127.0.0.1`, meaning this machine
   only. On a host that is invisible from outside; it has to be `0.0.0.0`.

All three live in `serve.py`, which imports `app` from `web.py` and hands it to
waitress. Importing does not start the dev server, because that call sits behind
`if __name__ == "__main__"` — so debug mode cannot reach the internet even by
accident.

`serve.py` is a module §4 never listed. It exists so the start command is in the
repo instead of typed into a hosting dashboard, where it would be outside
version control and lost if the service were ever recreated.

### Checked rather than assumed

Pinned `waitress==3.0.2` after querying PyPI for what actually exists, instead
of writing a plausible-looking version number. Same habit as the README output:
a pinned version that was never verified is a build failure with a delay on it.

### Deliberately still open

§7's SQLite risk — hosts wipe the filesystem on redeploy — moved from v0.1 to
v0.2. v0.1 stores nothing, so there is no data to lose yet, and deploying a
stateless app first splits "does the pipeline work" from "does the data
survive". Those are much harder to debug at the same time.

`.python-version` pins 3.14. If Render does not offer it, dropping to 3.13 costs
nothing today, since nothing here uses a 3.14 feature — but that should be a
decision, not whatever the host happens to default to.
