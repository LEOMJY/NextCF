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

---

## 2026-08-15 — v0.1 is live

<https://nextcf.onrender.com>

Deployed on the first attempt, which I did not expect. v0.1 done on 15 August
against an end-of-August target.

### Verified from outside, not from the browser tab I had open

| Request | Result |
|---|---|
| `/` | 200, form renders |
| `/results/tourist` | 200, 100 rows |
| `/results/nosuchuser42qq` | 404, error page rather than a crash |

The middle one is the one that mattered. The deployed copy calls the Codeforces
API from a datacenter address in Oregon rather than from my home connection, and
that was the failure I thought most likely — plenty of APIs treat cloud IP ranges
differently. It answered normally. Worth knowing now rather than at v0.3, when
2000 users get fetched from that same address.

The third confirms the error handling survives the move. A mistyped handle on the
public site shows an explanation, not a 500.

### The gotcha in the Render form

Render detects Flask and pre-fills a start command using **gunicorn**. Since
`requirements.txt` has waitress instead, leaving that autofilled value would have
built successfully and then failed to start — the two steps are separate, and a
green build says nothing about whether the app runs.

### Not yet observed

The cold start. Everything above was measured within minutes of deploying, so the
instance was awake; every request came back in under half a second. The ~60s
wake-up only shows up after a genuine idle period, and I have not seen it yet.
Not a problem now, and ADR 0003 already says it gets revisited before launch
rather than before then.

### What v0.1 actually proves

Very little about the product, and that is fine. It answers "does the whole chain
run" — browser, route, API client, Codeforces, table, on a machine that is not
mine. Everything the project is *for* is still ahead: no database, no per-topic
skill estimate, no recommendation, no evaluation. It recommends nothing.

### Next

v0.2: SQLite and `db.py`, fetching moved into a background job with the progress
page, and the base stylesheet and design tokens. The persistence question from §7
becomes real the moment `db.py` exists, since a free Render instance has no
persistent disk — its own pricing page says so.

---

## 2026-09-07 — Three weeks off; the cold start finally measured

Away from the project for three weeks. Nothing was built. Recording it because
the gap is real and the milestone dates in §10 were written assuming 10–15 hours
a week, which did not happen.

### The site stayed up

<https://nextcf.onrender.com> answered after three weeks of zero traffic, no
intervention and no redeploys. That is the third v1.0 criterion in §9 — "it is
live at a URL and stays up" — holding for the first non-trivial stretch.

### Cold start: 31.5 seconds

The 08-15 entry listed this as not yet observed, because everything had been
measured minutes after deploying while the instance was awake. Now measured
properly, on a genuinely idle service:

| | |
|---|---|
| First request after 3 weeks idle | **31.5s** |
| Requests while warm (08-15) | under 0.5s |

ADR 0003 and the README both guessed "about a minute". The real figure is half
that, so the README has been corrected. Still slow enough to matter on the day
the Codeforces blog post lands and fifty strangers arrive at once, which is
exactly when ADR 0003 says to buy a paid instance — that plan is unchanged, and
now it rests on a measurement rather than an estimate.

Worth noting the guess was wrong in the *pessimistic* direction. Same lesson as
the WinError 17 entry, cheaper this time: a number nobody measured is not a
number.

### Where v0.2 stands

Not started. It is four things — `db.py` and the schema from §6, `sync.py` as a
resumable background job, the `/progress/<job>` page, and the design tokens plus
base stylesheet from §7.1 — and §12 has an open question that has to be answered
while building it: what happens when a sync job is interrupted mid-user, given
that partial data in the database is worse than none.

---

## 2026-09-07 — Schema decided before any of it was written

`db.py` does not exist yet and deliberately was not started. Three decisions
had to be made first, because all three change the `CREATE TABLE` text, and
changing that text after the file holds two million rows is a migration rather
than an edit.

### Partial data was the wrong way to state the problem

§12 has said since 08-11 that "partial data in the database is worse than
none." Writing out the actual failure showed the sentence is not quite right,
and the precise version is what decides the design.

Fetch 300 of a user's 5000 submissions, die, and the database holds 300 rows
and a fresh `last_synced`. Nothing crashed, nothing was logged, and every later
reader believes it has the complete history. The model learns the user has
solved twelve DP problems instead of four hundred, and that lands inside the §9
number, which is the one output that has to be trustworthy.

The damage is not the missing rows. It is that **nothing records that they are
missing**. Partial data indistinguishable from complete data is what is worse
than none. Once the distinction is explicit, partial data is strictly better
than none, because it is work not repeated.

That reframing changed the goal from "prevent partial writes" to "make
completeness machine-checkable", and the answer fell out: one transaction per
user, with `last_synced` written inside it, so the flag and the rows cannot
disagree. ADR 0004. Resumability lives at the user boundary, which is where §4's
"dies at minute 40" actually is — that is `collect.py` at v0.3, where the unit
is one user out of 2000. Redoing one user costs about 100 seconds.

Same lesson as the WinError 17 entry and the cold-start entry, in a third form:
the sentence I had written down was a guess phrased as a fact, and it did not
survive being stated precisely.

### Tags moved out of `problems` into their own table

§6 said `tags text — comma separated for now`, and the "for now" was carrying
the whole argument. Not for the performance reason — 10,000 problems scan in
under a millisecond and always will. Because topics are the axis the entire
product works along: §1 promises the breakdown, §3 says it is the
differentiator, and `model.py` at v0.6 wants "this user's submissions on
problems tagged X" as its central query.

Worth recording that the migration would have been cheap — the tag strings are
already stored, so building the table later is one script over rows on disk,
with no re-fetch and no data loss. It was decided on *when* the cost lands, not
how big it is: one `CREATE TABLE` in the week the schema is written, versus
rewriting queries in the week the first model is being fitted. ADR 0005.

### Dates are ISO-8601 UTC text

SQLite has no date type. Text or Unix integer seconds are the only options.
Picked text because it is legible when the file is opened by hand, which is
most of what happens to this file over the next two months, and it sorts
correctly given one fixed format. The API gives Unix seconds either way, so one
conversion happens on write regardless.

### Things the spec got wrong that its own v0.1 code already knew

`web.py:display_row` handles `contestId` being absent — acmsguru problems have
none. §6 defines `problems.id` as contestId + index, so under the spec those
problems cannot be stored at all. The API contradicted the spec and the code
found it first, a month before the schema did.

Same shape: §6 lists `verdict` as text with four example values, but
`api_client.format_submission` already substitutes `"TESTING"` because a
submission still being judged has no verdict at all.

### Still open, to settle while writing `schema.sql`

Not decided yet, listed so they are not silently skipped:

- **Handle casing.** Codeforces handles appear to be case-insensitive for
  lookup. If so, storing what the visitor typed makes `Tourist` and `tourist`
  two users with two disjoint histories, which corrupts the §9 dataset quietly.
  Verify against the API, then store the canonical handle from the response
  rather than the form input, and put `COLLATE NOCASE` on the column.
- **`problems.id` when `contestId` is absent.** Skip those problems, or build
  the id from `problemsetName`. About twenty problems either way.
- **`participantType`.** The API says whether a submission was in-contest,
  virtual or practice. §12's "what counts as solved?" and §8's assumption 4
  both need it eventually. Adding the column later is trivial; *filling it in*
  later means re-fetching 2000 users at two seconds a request. The rule worth
  keeping: adding a column is cheap, adding a column that must be backfilled
  from a slow external source is not.
- **Indexes.** `submissions(handle)` and `submissions(problem_id)`. Every index
  gets a comment naming the query it exists for; one that cannot be named
  should be deleted.
- **`CHECK` on `jobs.state`**, so a typo'd state is an error at the write
  rather than a mystery later.
- **Stale jobs.** A job killed by the host stays `running` forever and
  `/progress` polls it forever. One worker thread in one process means any job
  still marked running at startup is orphaned, so `init_db()` marks them
  failed. Correct only while there is one process — comment it as such.
- **Two things that will bite on the first run:** `PRAGMA foreign_keys = ON`
  (off by default, per connection, so `REFERENCES` is decorative without it),
  and `PRAGMA journal_mode = WAL`, without which the sync thread writing blocks
  the progress page reading and produces "database is locked". The v0.2
  architecture is specifically one thread writing while a request reads, so
  that is not a hypothetical.
- **Threading.** A `sqlite3` connection cannot be used from a thread other than
  the one that created it. One connection per thread, created where it is used,
  never a module-level global.

### Next

`schema.sql`, then `connect()` and `init_db()`, then a throwaway script that
inserts fake rows and inserts them a second time to prove the count does not
change. That last check is the one that proves ADR 0004 works, and it is far
easier to run now than through a background thread later. `nextcf.db` goes in
`.gitignore` — a binary file in version control produces conflicts that cannot
be resolved.

Still unanswered and now due: §7's known risk that Render's free tier has no
persistent disk, so the database is deleted on every redeploy. Not a v0.2
blocker — losing a local cache of public data costs one re-sync — but it has to
be answered before v0.3, when what gets wiped is an hour of API calls.

---

## 2026-09-09 — `schema.sql`

The five tables from §6 exist as a file. No Python yet — `db.py` is next, and
keeping the schema separate means it can be read, diffed and run on its own.

### Every constraint was checked by making it fail

Writing `CHECK` and `REFERENCES` into a file proves nothing. A constraint that
is silently not enforced is worse than no constraint, because it reads as a
guarantee. So each one was tested by attempting the thing it forbids and
asserting the database refused:

```
ok  users.handle is case-insensitive (Tourist == tourist)
ok  STRICT rejects text in an INTEGER column
ok  CHECK rejects a misspelled job state
ok  foreign key rejects a submission by an unknown handle
ok  re-inserting a tag leaves one row
ok  inserting the same 3 submissions twice leaves 3 rows
ok  a second pending job for the same handle is refused
ok  ...but a retry after that job failed is allowed
ok  an interrupted transaction leaves 0 rows and last_synced NULL
ok  join across all three tables reads back (inserted as 'Tourist')
```

Two of those are the ADRs made testable rather than asserted. "Inserting the
same 3 submissions twice leaves 3 rows" is ADR 0005's dedupe and the property
that makes a re-run of a sync harmless. "An interrupted transaction leaves 0
rows and `last_synced` NULL" is ADR 0004 itself — and it checks *both* halves,
because a rollback that discarded the rows while leaving the completeness flag
set would be the exact corruption the ADR exists to prevent.

The foreign-key test is the one that would have quietly passed for the wrong
reason. SQLite has foreign key enforcement **off by default**, per connection.
Without `PRAGMA foreign_keys = ON` in the test setup, every `REFERENCES`
clause in the file is decorative and that test would have "passed" by never
being enforced at all.

### Decisions made while writing it

- **`problems.id` when `contestId` is absent** — the id becomes
  `problemsetName + index`, e.g. `acmsguru100`. No collision with the normal
  `1234A` form is possible, since contest ids are numeric and this one starts
  with letters. `db.py` owns building the string; two callers formatting an id
  by hand is two chances to format it differently.
- **`verdict` is nullable rather than storing `"TESTING"`.** A submission
  still being judged genuinely has no verdict. `"TESTING"` is a display
  decision and belongs in `display_row`, not in storage.
- **`finished_at` added to `jobs`.** Without it there is no way to distinguish
  a job still working from one that stopped.
- **A partial unique index on `jobs`** — at most one job per target in
  `pending` or `running`, so two people typing the same handle at the same
  moment cannot start two syncs. The `WHERE` clause exempts finished and
  failed rows, so a retry after a failure is still allowed. Both halves are
  tested above.
- **`submissions(handle, submitted_at)` rather than `submissions(handle)`.**
  The results page wants that user's rows newest first, and including the
  timestamp lets the index serve the sort as well as the filter. SQLite reads
  an index backwards, so one ascending index covers `DESC` too.
- **`STRICT` on all five tables.** Without it SQLite treats column types as
  suggestions and stores `"banana"` in an INTEGER column without complaint.

### `progress` stopped meaning what §6 said it meant

§6 described `jobs.progress` as "how far through, so work can resume". Under
ADR 0004 an interrupted sync writes nothing, so there is no partial state to
resume from and the column only drives the progress page. Fixed in §6 rather
than left to be misread later — the phrasing predated the decision that
contradicted it.

Also corrected in §6: `participant_type` and `finished_at` are in the schema
and were not in the document.

### `.gitignore` had a hole

It ignores `*.db`, but WAL mode writes `nextcf.db-wal` and `nextcf.db-shm`
next to the database, and neither matches that pattern. Added both before the
first run rather than after wondering what those files were.

### Next

`db.py`: `connect()` and `init_db()`. The two settings deliberately left out
of `schema.sql` live there, because both belong to a connection rather than to
the schema — `PRAGMA foreign_keys = ON`, which the test above proved is not
optional, and `PRAGMA journal_mode = WAL`, without which the sync thread
writing and the progress page reading collide as "database is locked".

`init_db()` also marks any job still in `running` at startup as `failed`. One
worker thread in one process means such a job is orphaned by definition. That
is correct only while there is one process, and needs a comment saying so.

---

## 2026-09-11 — `problems.id` checked against the real API

The 09-09 entry named the id format as the one line in `schema.sql` worth
checking before real data lands, because it becomes the foreign key in roughly
two million submission rows and changing its shape afterwards means rewriting
every one of them. So it was checked against the live API instead of reasoned
about: all 11,385 problems in `problemset.problems`, the 453 in the acmsguru
archive, tourist's 5,474 submissions, and one Div. 2 contest.

### Unique, but not splittable

No id is produced twice. The format itself is sound.

What the data did break is an assumption nobody had written down: that an id
can be split back into contest and index at its first letter. The shapes of
the index field:

| Shape | Problems | Example |
|---|---|---|
| one letter | 10,490 | `1234A` |
| letter and digit | 880 | `1189D1`, the easy/hard version pairs |
| letter and two digits | 1 | |
| digits only | 14 | contest 921, indices `01` to `14` |

Those fourteen make ids like `92114`, and nothing in that string says whether
it is contest 921 problem 14 or contest 9211 problem 4. Nothing collides today.
But the results page will need the contest number back to build every problem
link, and a gym filter needs it too, and for these fourteen it cannot be
recovered by parsing.

Fix: `contest_id` and `problem_index` as columns of their own, so the id is
never parsed, plus a `CHECK` that the id equals the two joined — two copies of
one fact can drift, and this makes drift an error at the write. The column is
`problem_index`, not `index`, because SQLite rejects a column named `index`
with a syntax error. That was tried rather than assumed. Schema tests are now
at 14, three of them for this.

### One problem, two ids

When a Div. 1 and a Div. 2 round run together they share problems, and each
shared problem has an id in both contests. Contest 1293, Codeforces Round 614
(Div. 2), asked for its own problem list:

```
1293A  ConneR and the A.R.C. Markland-N   listed in problemset
1293B  JOE is on TV!                      listed in problemset
1293C  NEKO's Maze Game                   not listed -- problemset has 1292A
1293D  Aroma's Search                     not listed -- problemset has 1292B
1293E  Xenon's Attack on the Gangs        not listed -- problemset has 1292C
1293F  Chaotic V.                         not listed -- problemset has 1292D
```

The problemset keeps one copy. A Div. 2 contestant's submissions carry the
other. In one real Div. 2 participant's full history, **29 of 230 solved
problems were stored under an id the problemset does not list**. One history
is an example, not an estimate — but the audience in §2 is mostly Div. 2, so
it is not a rare case either.

The consequence lands at v0.4: a recommender drawing from the problemset and
checking "already solved?" by id would offer those 29 problems back to that
user as new. It also splits the crowd's attempts on one problem across two ids,
which matters for the per-problem difficulty estimate at v0.6.

This is not a flaw in the id format — any contest-plus-index scheme has it —
and the schema does not change for it. Storing the id each submission was
actually made against is the choice that keeps it fixable, because a mapping to
the problemset's id can be built later from rows already stored. Collapsing
the two ids at write time would destroy which contest a submission came from,
which cannot be undone. Now in §12, due at v0.4.

Name matching will not build that mapping on its own. The problemset holds
seven different problems called "Elections", and reuse is not limited to
adjacent contests: `1230D` appears in the problemset only as `1210B`.

### The first check was aimed at the wrong source

The first attempt looked for duplicates *inside* `problemset.problems` — same
name, contests close together, same rating and tags. It reported 69 pairs. They
were mostly one contest containing seven different problems all named
"Treasure Hunt". And it could never have found the real case, because the
problemset had already dropped one copy of every shared problem before the data
arrived.

What found it was asking the places the data actually comes from: a contest's
own problem list, and a real user's submissions. Checking a derived dataset
for a problem its own construction removed says nothing either way.

### Also found

- **acmsguru is 453 problems.** The 09-07 entry said "about twenty". The rule
  handles all of them, but the number was a guess written as a fact.
- **`user.status` includes gym submissions.** tourist has 155. Store or skip is
  a `sync.py` decision; with `contest_id` stored, `contest_id >= 100000` filters
  them either way.
- **`contest.standings` refuses paging for non-gym contests.** Anonymous callers
  get the whole table or HTTP 400. Relevant if `collect.py` at v0.3 finds users
  through standings.
- **That 400 first arrived with no reason attached**, because the check script
  did not read the error body — the exact lesson from `api_client.py` on 08-14,
  repeated in a throwaway script. The body said precisely what was wrong.

### Handle casing, verified

The 09-07 entry said handles "appear to be" case-insensitive and asked for that
to be checked against the API before `COLLATE NOCASE` was relied on. It was not
checked then, and the comment in `schema.sql` went on to state it as fact
anyway — a guess that hardened into a code comment. Now checked:
`user.status?handle=TOURIST` answers OK, and the submission it returns names
the author as `tourist`.

So `COLLATE NOCASE` on both handle columns now rests on a measurement, and the
second half of that 09-07 item stands: `sync.py` must store the handle the API
returns, never the one typed into the form.

### Next

Unchanged: `db.py`, `connect()` and `init_db()`.

---

## 2026-09-11 — `db.py`: the settings that are not the schema

`db.py` exists with `connect()` and `init_db()`, plus `utc_now()`, because
`init_db()` needed a timestamp and the format in §6 only holds if one function
produces every timestamp. No queries yet, and nothing calls it yet — wiring
`init_db()` into startup comes with `sync.py`, when something needs the data.

### What it owns

`schema.sql` holds everything that is a property of the tables. `db.py` holds
what is not:

| Setting | Applies to | Set in |
|---|---|---|
| `PRAGMA foreign_keys = ON` | every connection; off by default | `connect()` |
| rows readable by column name | every connection | `connect()` |
| `PRAGMA journal_mode = WAL` | the file, and persists | `init_db()`, once |
| one timestamp shape | every writer | `utc_now()` |

### Checked by making each failure happen

```
ok  init_db creates all five tables
ok  running init_db a second time keeps existing data
ok  the file stays in WAL mode, even for a plain connection
ok  connect() refuses a submission by an unknown handle
ok  ...while a plain sqlite3.connect() silently stores the same row
ok  rows are readable by column name
ok  startup fails pending and running jobs, spares done ones, unblocks the handle
ok  a connection used from another thread raises ProgrammingError
ok  with WAL, a read during a write succeeds and sees 0 uncommitted rows
ok  ...without WAL, the identical read fails with 'database is locked'
ok  utc_now() has exactly the spec section 6 shape
```

Two of those are counterfactuals, run deliberately. A test that `connect()`
rejects a bad foreign key would also pass if something else happened to reject
it; sending the identical insert through a plain `sqlite3.connect()` and
watching it succeed is what proves the pragma is doing the work. Same for WAL:
the identical read, on the identical schema, with the journal mode left at its
default, fails with "database is locked" — the error the progress page would
have hit during every sync.

The WAL test also shows ADR 0004 from the reader's side. While the writer held
three uncommitted rows, the reader saw zero, not three. A page reading during a
sync sees the user as they were before it started, never half-written.

The write lock in that test is forced with `BEGIN EXCLUSIVE` so the result does
not depend on timing. It is the lock every writer holds at the moment it
commits, so it is the realistic worst case rather than an invented one.

### Orphaned jobs: `pending` too

ADR 0004 said `init_db()` would mark jobs still `running` at startup as failed.
Writing it exposed a case the ADR missed. A job created but not yet started
when the process died stays `pending` — and the partial unique index from 09-09
refuses a second unfinished job for the same handle. So a stale `pending` row
does not merely sit there: that handle could never be synced again. The cleanup
covers both states, the test reproduces the lockout before cleanup and confirms
it is lifted after, and the ADR is amended.

Worth noticing how it happened. The index was right. The cleanup rule was right
for the case it named. Together they produced a permanent lockout that neither
shows on its own, and it only surfaced because the test inserted a stale row
and then tried to start a new job, instead of checking the two in isolation.

### Small things that were decisions

- **Paths resolve from `db.py`'s own location**, not the working directory. A
  bare `nextcf.db` means "wherever the program was started", which differs
  between running `web.py` by hand and the host running `serve.py`.
- **`NEXTCF_DB` overrides the path**, the way `serve.py` reads `PORT`. Where the
  file lives in production is still the open §7 question; if the answer is a
  mounted disk, it becomes a host setting rather than a code change.
- **`utc_now()` uses `strftime`, not `isoformat()`.** `isoformat()` gives
  `2026-09-11T14:03:00.123456+00:00`, which as text sorts *before*
  `2026-09-11T14:03:00Z` from the same second, because `.` comes before `Z`.
  Two shapes in one column would silently break every `ORDER BY` on it.
- **`connect()` checks that foreign keys actually turned on** rather than
  trusting the pragma, and **`init_db()` checks the journal mode it got back**.
  A pragma SQLite does not act on fails silently, and a filesystem that cannot
  do WAL answers with the old mode instead of raising.
- **The one f-string in the file formats a table name into SQL**, in `main()`.
  Placeholders stand in for values, never for names, so there is no
  alternative — and it is safe only because the names come from
  `sqlite_master`, not from outside.

Also confirmed the database never reaches git: `python db.py` created
`nextcf.db`, and `git check-ignore` matches it, `nextcf.db-wal` and
`nextcf.db-shm`.

### Next

The queries, in `db.py`, one function per caller need — the list is in the
09-07 entry. Two rules to hold while writing them:

- **Every timestamp goes through `db.py`**, including converting the API's
  `creationTimeSeconds`. That conversion belongs beside `utc_now()`, not as a
  second `strftime` written inside `sync.py`.
- **The problem id is built in exactly one function**, which raises when an API
  object has neither `contestId` nor `problemsetName`.

One constraint to carry into v0.3. The orphan cleanup is safe only while one
program uses the database, and §4 plans three — alongside a web app that never
stops, so §4's "they do not run at the same times" cannot literally hold. The
comment in `init_db()` first said "one process" and meant only two copies of
the web app; it now names `collect.py` and `scheduler.py`. §12 has the question
of which program may run the cleanup, due before `collect.py` touches `jobs`.

---

## 2026-09-12 — `db.py`: the queries

One function per question a caller actually asks, and none written ahead of a
caller that asks it. The list is the one from the 09-07 entry and has not grown:

```
reads        get_user, get_submissions, get_job, get_active_job
job records  create_job, start_job, set_job_progress, finish_job
the sync     save_sync
conversions  problem_id, iso_from_unix
```

### `save_sync` is one function because ADR 0004 is a promise about a transaction

The ADR says the rows and `last_synced` become permanent together or not at
all. The only way to keep that promise is to make the whole write a single call
that nothing can use halfway, so the user, its problems, their tags, the
submissions and `last_synced` all sit in one `with conn:` block and `sync.py`
never sees the seams.

The rows are shaped before the transaction opens. A malformed submission then
raises before anything is written at all, which is better than rolling it back,
and it keeps the transaction short — a transaction is a lock, and a lock is
time other threads spend waiting.

### Three decisions that only appeared while writing it

**Submissions update the verdict on conflict rather than being ignored.** ADR
0004 described `INSERT OR IGNORE`: Codeforces' submission ids are stable, so
re-inserting one is a no-op. That is right about duplicates and wrong about
verdicts. A submission fetched while it was still being judged has no verdict
at all, and `OR IGNORE` would leave it NULL for good, however many times the
user re-synced. A rejudge or a successful hack can also change a verdict that
was already there. So the conflict clause updates the verdict and nothing else;
the other five columns are facts that cannot change. Either way no duplicate
row is created, which is the property the ADR actually depends on.

**Problems are updated too**, for the same kind of reason. Codeforces gives a
new problem its rating days or weeks after the contest, so a problem stored
with `rating` NULL on the day of the round has to pick it up later — the
rating-only baseline in §9 is built on exactly that column.

**Tags are deleted and re-inserted**, per ADR 0005. Inserting without deleting
would accumulate every tag a problem has ever had, with nothing marking which
ones are current.

### `get_submissions` returns three different things

`None` for a handle that was never synced, or whose sync did not finish. `[]`
for a user who synced fine and genuinely has no submissions. Rows otherwise.

`None` versus `[]` is the same distinction as NULL versus 0, and it is the
reason nothing else may query the submissions table directly: this is the only
place ADR 0004's completeness rule is enforced, so there is exactly one
function that could get it wrong.

### The job functions commit on their own, and that is the point

Each of `create_job`, `start_job`, `set_job_progress` and `finish_job` has its
own `with conn:`. A job's failure record has to survive the rollback that
destroyed the work it describes, so it cannot be written inside the transaction
doing that work. The test for it creates a job, lets a sync fail, and checks
the job row is still there and can be marked failed while the user it was
syncing is still absent.

The cost is a footgun, now written above those functions in capitals: calling
one inside another `with conn:` would commit the enclosing transaction too, and
make half a user permanent — the exact thing ADR 0004 exists to prevent.

### Checked

19 now, 8 of them new:

```
ok  problem_id builds both forms and refuses to invent a third
ok  save_sync stores user, problem, tags and submissions, newest first
ok  syncing twice: no duplicates, verdict and rating updated, tags replaced, first_seen kept
ok  the same handle in another casing updates one user, not two
ok  one broken submission leaves the whole sync unwritten
ok  None for never-synced and half-synced, [] for synced with nothing
ok  job lifecycle: one active at a time, retry after it finishes
ok  a job's failure record survives the sync that rolled back
```

The casing one turns yesterday's API measurement into a property of the code:
`save_sync` called with `tourist` and then `TOURIST` updates one row instead of
creating a second user.

### Where the API's shape now lives

The 08-15 entry recorded that "these fields are sometimes absent" was written
down in both `api_client.py` and `web.py`, and said it should move into one
place when `sync.py` became the third caller. That place is `save_sync`, which
takes the raw dicts the API sent and is the only code that knows `verdict`,
`rating`, `contestId` and `problemsetName` can be missing.

The cost is that `db.py` now knows Codeforces' field names. The alternative was
a third module translating between the two, which is more ceremony than one
function is worth at this size. The day a second data source appears, that
trade stops being right.

`web.py` still has its own copy in `display_row`, because it still reads from
the API directly. That goes when the results page starts reading from the
database instead — the same change that wires `init_db()` into startup.

### Next

`sync.py`: fetch the pages, update progress as they arrive, call `save_sync`
once at the end. Then `/progress/<job>`, then the design tokens.

Two things it has to do that nothing enforces yet. Pass the handle the API
returned, not the one typed into the form. And call `get_active_job` before
`create_job`, so a second visitor typing a handle that is already syncing joins
that job instead of hitting the unique index.

---

## 2026-09-12 — `sync.py`, and a comment that was printing itself on the live site

### The page has been saying this since 08-15

A screenshot of the landing page, above the title:

```
is a Jinja comment: it is stripped when the page is rendered, so it never
reaches the browser. would be sent. #}
```

`base.html` opened with a comment explaining what a Jinja comment is — and to
explain it, it wrote one out in the middle of itself. Jinja comments do not
nest: they end at the first closing marker. So the comment ended halfway
through its own explanation, and the rest of the sentence became page content.
The `<!-- -->` it mentioned turned into a real HTML comment, which is the hole
in the middle of the sentence.

Every visitor since 08-15 has seen it. Nothing caught it because it is not a
syntax error, the page still answers 200, and every check written so far asked
about status codes and table contents — never about what the page actually
says. The 08-15 entry claimed all six paths were "verified rather than
assumed"; they were, for everything except the words on the screen.

There is now a check that renders `/`, the error page and a rejected POST, and
fails if the HTML contains `{#`, `#}`, `{%`, or any wording from that comment.
It would have caught this on the day. Like the schema and db checks it is a
scratch script rather than part of the repository — tests are v0.7 in §10, and
that gap is now three scripts and 23 checks wide.

The comment now explains the rule without writing the marker, and says why.

### `sync.py`

`user.info` first, for the two things `user.status` does not give: the
canonical spelling of the handle, and the Codeforces rating. Everything after
that uses the API's spelling, never the one typed into the form. Then it pages
through the history writing nothing but `jobs.progress`, and hands the whole
list to `save_sync` in one call.

Run against the live API:

```
job 1: syncing tourist
  1000 submissions fetched
  ...
  5474 submissions fetched
done
5474 submissions stored

  jobs           1 rows
  problem_tags   9029 rows
  problems       3134 rows
  submissions    5474 rows
  users          1 rows
```

### Page size is a trade between requests and progress

`PAGE_SIZE = 1000`. One request for everything is fastest and leaves the
progress bar at zero until it is over. 100 at a time gives the finest progress
and needs 55 requests for a history this size, at an API that asks for one
request every two seconds. 1000 puts almost every user in a single request and
still moves the bar for the heavy ones; tourist took six requests and about
fifteen seconds.

The two-second wait between pages lives in `sync.py`, not `api_client`, and
that is temporary. Real rate limiting — shared by every caller, with retries
and backoff — belongs in `api_client` at v0.3, where `collect.py` will need it
for 2000 users in a row.

### The paging loop is correct because of how somebody else sorts

`user.status` answers newest first, so a submission made *during* the loop
shifts everything down one place and the next page repeats a row already
collected. Repeats are harmless: `save_sync` keys submissions by Codeforces'
own id. If the API answered oldest first, the identical shift would *skip* a
row instead, and nothing in this code would notice. The loop looks equally
correct either way, which is exactly why it is written in a comment there.

### `except Exception` on purpose

`run_sync` catches everything. Normally that hides bugs. Here the opposite: the
thread's only way to tell anybody anything is the `jobs` row, so an exception
that escaped would kill the thread in silence and leave the job marked
`running` forever, with a visitor watching a progress page that will never move
or explain itself. The visitor gets a sentence; the real error goes to the log.

### Two visitors, one handle

`start_sync` looks for an unfinished job first and returns it if there is one.
If two requests both look and both find nothing, the unique index refuses the
second insert and the loser reads back the winner's job. The check is an
optimisation; the index is the guard.

`jobs.target` gained `COLLATE NOCASE`, for the same reason `users.handle` has
it: without it `Tourist` and `tourist` are different targets, the index would
allow one unfinished job of each, and the same person would be fetched twice at
the same time.

### Changing `schema.sql` after a database exists

That `COLLATE NOCASE` never reached the local `nextcf.db`. Every statement in
`schema.sql` is `CREATE TABLE IF NOT EXISTS`, and the table already existed, so
the change was silently skipped. The file was deleted and rebuilt, which costs
nothing today: it holds a cache of public data, and no local copy matters.

That stops being true the first time a database holds something worth keeping.
From then on a change to `schema.sql` needs a migration — a script that
transforms existing data into the new shape — and `IF NOT EXISTS` will quietly
do nothing at all. Worth knowing before the deployed copy holds data, which is
the same §7 question due before v0.3.

### Next

`/progress/<job>`, and the wiring: `web.py` calls `init_db()` at startup,
starts a sync instead of blocking on the API, and the results page reads from
the database. That last change is also when `display_row`'s copy of "these
fields are sometimes absent" finally goes away.

---

## 2026-09-12 — Retries, and a contradiction that sat in §4 for five days

### The spec was arguing with itself

ADR 0004 decided on 09-07 that an interrupted sync writes nothing and simply
runs again. §6 and §12 were updated to match. §4's module list was not:

```
sync.py         fetch one user's history, as a resumable background job
```

So for five days the repository held the decision in one file and the opposite
claim in another — and §4 is the part anybody reads first. Nothing caught it
because nothing checks documents against each other; it surfaced only when
somebody remembered §4 and asked why the code did not match.

Both now agree, and §4's paragraph about interruption says which job resumes
and which one restarts.

### What resumability is worth here, measured rather than assumed

The question behind the re-examination: if a user has 10,000 submissions and
the fetch dies at 8,000, is all that work wasted?

tourist's 5,474 submissions are six requests and about fifteen seconds. At that
rate:

| history | requests | fetch time |
|---|---|---|
| 500, which is most people | 1 | about a second |
| 5,000 | 5 | about 13 seconds |
| 10,000 | 10 | about 28 seconds |
| 20,000 | 20 | about a minute |

The wasted work is tens of seconds. The hour-long job people picture is
`collect.py` at v0.3 — 2,000 users — and that resumes at the user it died on,
losing at most one user's fetch.

### Retrying beats resuming

Three ways not to waste work, in order of value:

1. **Retry the failed request.** Prevents the loss instead of limiting it, and
   covers what actually goes wrong: a blip, a 503, a rate limit.
2. **Stop early on a re-sync**, when the pages reach submissions already
   stored. At v0.7's nightly re-sync this is the difference between six
   requests and one for a 5,000-submission user with three new solves — across
   2,000 users, between an hour and minutes.
3. **Resume mid-user.** Saves tens of seconds, and only when the process was
   killed rather than the request refused.

One more thing that makes the third weaker than it looks: even with
incremental writes the data stays unusable until the sync finishes, because
`last_synced` is still NULL. Resuming saves fetching time; it never makes the
page work sooner.

So `api_client` retries now, and `sync.py` is unchanged.

### What is retried, and what must not be

| Failure | Retried | Why |
|---|---|---|
| HTTP 5xx | yes | their end is broken, not the request |
| dropped connection, timeout | yes | nothing about it is permanent |
| "Call limit exceeded" | yes | our fault, and waiting is exactly the fix |
| handle does not exist | **no** | it will not exist in six seconds either |
| any other 4xx | **no** | the request is wrong; repeating it is pointless |

Three attempts, waiting 2 seconds then 4.

The distinction is carried by `TemporaryFailure`, a subclass of `RuntimeError`
on purpose: `web.py` and `sync.py` already catch `RuntimeError`, so one
escaping after the last attempt is handled correctly by code written before
this existed.

Checked without touching the network, by replacing `urlopen` with a script of
prepared answers and `sleep` with a counter — 7 checks, instant, including that
a nonexistent handle is asked exactly once and waits zero seconds. Retrying
that one would make a visitor wait six seconds to be told the same thing.

### The re-sync proved itself by accident

Running `sync.py tourist` a second time, only to confirm the retry change had
not broken the normal path:

```
first run:   5474 submissions, 3134 problems, 9029 tags
second run:  5476 submissions, 3135 problems, 9033 tags
```

tourist had submitted twice in the fifteen minutes in between. The second run
stored the two new submissions and the one new problem, and duplicated none of
the 5,474 already there. That is the `ON CONFLICT` clause doing the job it was
written for, on real data, without a test having to arrange the situation.

### Next

Unchanged: `/progress/<job>`, then the wiring, then the design tokens.

---

## 2026-09-12 — The site reads from the database

`/progress/<job>` exists, and the pages are wired to the database. Nothing in a
web request waits on Codeforces any more — `web.py` no longer imports
`api_client` at all. Only `sync.py` talks to the API, from a background thread.

### The shape of it

```
POST /              ->  redirect to /results/<handle>
GET  /results/x     ->  fresh data in the database?  show the table
                        missing, unfinished or stale? start a sync,
                                                      redirect to /progress/<job>
GET  /progress/7    ->  running?  the count, and the page reloads itself
                        done?     redirect to /results/<handle>
                        failed?   the reason, in a sentence
```

Deciding in one place matters more than it looks: the form does not decide
anything, so a link somebody shares behaves exactly like typing the handle.

### A connection per request, not per process

`get_db()` opens one on first use and a teardown closes it when the request
ends. A sqlite3 connection belongs to the thread that made it, and the server
runs requests on a pool of threads it reuses, so a connection that outlived a
request would eventually be used from the wrong one. Flask's `g` is the
per-request scratch space that makes this three lines.

### The progress page does not invent a percentage

Codeforces never says how many submissions a person has. The only way to find
out is to keep asking until a page comes back short — which means a percentage
on this page would be a number nobody knows. §4.1 asks this page to show a long
job making progress *without lying about it*, so it shows a count that is true
and no bar that is not.

It reloads itself with `<meta http-equiv="refresh" content="2">`. No
JavaScript: it is the smallest thing that works, it survives scripting being
turned off, and when the job finishes the next reload lands on the redirect to
the results page, so leaving needs no extra code. The cost is the whole page
re-fetched every two seconds. Replacing it with a small `fetch()` against a
JSON endpoint is the upgrade, and it belongs with the design pass.

That cost showed up immediately in an unexpected way: a screenshot of the
progress page times out, because a page that reloads every two seconds never
finishes rendering. Funny, and a fair warning about what the flicker will look
like to a person.

### Ten minutes of freshness

Stored data older than ten minutes starts a re-sync instead of being shown;
inside that window the stored copy is served without touching the API. That is
the caching §10 asks for in v0.2.

The other option was to show stale data at once and refresh behind the back of
the page. Better for somebody returning, worse to reason about, and it needs a
way to tell the page that newer data has arrived. Left for the design pass.

### Run for real

Typed `Benq` into the form in a browser. The progress page counted up —
`5000 submissions fetched so far` — and then redirected itself to a table of
8,574 submissions.

Which exposed the next problem: that page was 8,574 table rows and 50KB of
HTML. The database holding every submission is right; the page showing every
submission is not. The table now shows the newest hundred **and says what it is
hiding** — "Showing the 100 most recent of 8574 submissions" — because a list
quietly cut short reads as "that is all there is".

### The 08-15 plan finished

`display_row` used to read raw API dicts and know which Codeforces fields go
missing. That knowledge now lives once, in `db.save_sync`, which is exactly
what the 08-15 entry said should happen when a third caller appeared. What is
left in `display_row` is a display decision: a submission with no verdict in
the database is shown as `TESTING`.

### Checked

57 checks: 14 schema, 20 database, 7 retry, 3 render, 13 web flow. The web
flow ones run against a temporary database with `start_sync` replaced, so they
touch no network and finish instantly.

One of them failed first time and was right to: two fake submissions had been
given the same contest and index, which makes them the same problem, so only
the first name was stored. The fixture was wrong, not the code — but it is
worth noticing that a test fixture can encode a misunderstanding just as easily
as code can.

### Next

The last thing v0.2 asks for: the design tokens and the base stylesheet from
§7.1. Every page so far is unstyled browser default.

---

## 2026-09-12 — The design system, and v0.2 is finished

### Three directions, built rather than described

§7.1 says the token system is a design decision belonging to whoever is
designing. Describing fonts and colours in words is a bad way to make that
decision, so three complete directions were built as working HTML — editorial,
terminal, product — each rendering both surfaces §7.1 distinguishes, using the
site's real copy and a real 8,574-row history. A design decision made against
lorem ipsum is a decision about lorem ipsum.

Terminal was chosen. ADR 0006 has the alternatives and why they lost.

```
type     IBM Plex Mono, five sizes: 13 / 16 / 20 / 25 / clamp(34, 5.2vw, 64)
space    five steps: 8 / 16 / 32 / 64 / 96
colour   canvas #0b0d10, ink #e8ecf1, muted #79838f, accent #7cf03d
radius   3px
shadow   none
```

### Same tokens, two volumes

The landing page uses the display size, the accent on the headline and the
button, and the two largest spacing steps. The tool pages use the same file:
heading down from display to head, rows tightened from 1.6 to 1.45, and the
accent only on a verdict that says OK — which is the one thing somebody
scanning a table of 100 rows is looking for.

That is what §7.1 means by one product rather than two websites, and it is
cheap to check: the tool pages import no CSS of their own.

### Two things the browser found that reading could not

Both appeared the moment a real page was on screen with real data:

- **The problem names were links and did not look like links.** The underline
  used `--line`, which is the near-invisible colour meant for borders on a dark
  canvas. Discoverable by hovering, which is no use to anyone scanning. They
  are underlined in `--muted` now.
- **The timestamp broke across two lines** — `2026-09-` on one, `12T06:02:52Z`
  on the next. ISO-8601 has no spaces, so the browser broke it at a hyphen. It
  is wrapped in a `<time>` element now, which is the right element anyway, with
  `white-space: nowrap`.

Neither would have been caught by reading the CSS, and neither is the kind of
thing a test can assert without knowing to look for it.

### One piece of motion, on purpose

A blinking block cursor after the number on the progress page. §7.1 rules
scroll-triggered animation and page transitions out of the tool surface because
those pages are read under time pressure — but it also names the progress page
as the one moment of peak attention, and a cursor that blinks is the honest way
to say "still working" without inventing a percentage. It stops blinking under
`prefers-reduced-motion`.

### The type is the one external dependency

The font comes from a CDN, which adds no build step and matches what §7 already
tolerates. A visitor who cannot reach it gets the fallback mono stack and the
same design in a different face, which is a degradation rather than a break.

Worth knowing, and now in ADR 0006: that CDN is blocked in mainland China, and
a real share of Codeforces users are there. Self-hosting the two weights is the
fix if it ever matters.

### v0.2 is done

| | |
|---|---|
| `db.py` and the schema from §6 | done |
| `sync.py` as a background job | done |
| `/progress/<job>` and the wiring | done |
| Design tokens and base stylesheet | done |

57 checks: 14 schema, 20 database, 7 retry, 3 render, 13 web flow. All five
scratch check scripts still live outside the repository, which is now the
largest untidy thing in this project — §10 puts tests at v0.7, and that is
three milestones away from where the coverage actually is.

*Corrected 2026-09-12, after counting:* both totals above first said 43, and
said four scripts. There are five, and 57 checks — `check_schema.py` was left
out of the sum, twice, by adding up the scripts that had been run most recently
instead of running all of them. The commit messages of the day still say 43;
they are history and stay as they are. Same lesson as the cold start and the
acmsguru count, in the cheapest possible form: a number nobody measured is not
a number, and that includes numbers about your own work.

### Next

v0.3: bulk collection of ~2000 users, rate limited and resumable — the first
job that really does run for an hour, and therefore the first place where the
resume boundary in ADR 0004 earns its keep. Two things already written down
that it needs: rate limiting shared across callers in `api_client`, and a
decision about which program may run `init_db`'s orphan cleanup (§12).

---

## 2026-09-12 — Two decisions that were written down harder than they were made

Rereading the design records at the end of v0.2 turned up two places where the
documents said more than I meant.

**The terminal direction is the working look, not the final one.** ADR 0006
said "accepted" with nothing qualifying it. What was actually decided was a
system good enough to make the v0.2 pages usable and legible. The final
direction is now an open question for v0.8. The token file makes that cheap
for type, colour and spacing. Layout can still change. It costs more because
it touches every template, not one file.

**React is open again.** §7 rejected it, and §7.1 said the rejection "stands".
I think a restrained use of React, components without showing off, can be
worth it for a site that is supposed to have real design. Written down as three
options in §12 instead of being decided on a feeling: stay on Jinja, React for
the interactive pieces only, or React for everything. The deadline is v0.4,
because the topic chart is the first thing where the choice changes the code.

What I learned: "accepted" in an ADR reads as permanent to anyone who opens it
later, including me. If a decision is only for now, the status line has to say
so.

---

## 2026-09-13 — Two v0.3 questions, and one answer for both

§12 had one question marked for v0.3: which program may clean up orphaned jobs.
A second one was overdue without being marked. §7's risk that the host wipes the
database was moved from v0.1 to v0.2, carried past v0.2 unanswered, and this log
said twice that it had to be settled before v0.3. ADR 0007 has both.

### The disk is wiped more often than §7 said

Render's documentation, read properly this time: a free instance loses the files
it wrote on a redeploy, on any restart, **and whenever it spins down after 15
minutes without traffic**. §7 only named redeploys. In practice the server's
database disappears several times a day, and a free instance cannot attach a
disk that survives.

Whether that matters depends on what is in the file:

| Data | Comes from | If it is wiped |
|---|---|---|
| A visitor's submissions | Codeforces, in seconds | One re-sync |
| The ~2000-user training set | An hour of API calls | An hour |
| Who visited, and when | Exists only on the server | §9's "20 returned" is unmeasurable |

So the training set lives in its own file, `dataset.db`, on my machine, and never
goes to the server. The server's `nextcf.db` is a cache that is allowed to
vanish.

A separate file rather than the local `nextcf.db` for a second reason: the web
app re-syncs any handle older than ten minutes. Look up somebody in the training
set and their rows change, and `evaluate.py` run twice gives two numbers. The §9
number has to come out the same every time.

Visit records are the row that has nowhere to go yet. Nothing is worth paying to
keep before strangers visit, so they are due at v0.7. Looking for where they
would be built turned up a gap: **no milestone counted visits at all**, though
§9 is measured on them. That is in v0.7's row now.

### The cleanup bug was already reachable

`init_db()` did two things: create missing tables, and mark every unfinished job
failed. The second is right for the web app, because when it starts, every sync
thread from its last run died with the old process. §12 asked what happens when
another program calls it.

It did not need `collect.py` to happen. `sync.py`'s `main()` already called
`init_db()`. Start the site, type a handle, run `sync.py` in a terminal during
the sync, and the visitor is told the server restarted while their job carries
on. No data is damaged — ADR 0004 guarantees that — but the page shows a failure
that did not happen, and a retry starts a second sync of the same handle.

The fix is a split. `init_db()` only creates what is missing, and any program
may call it. `fail_orphaned_jobs()` does the cleanup, and only `web.py` calls
it. `collect.py` will write no job rows at all: it runs in a terminal, prints
its progress there, and resumes by skipping users whose `last_synced` is set.

A heartbeat was the alternative: every running job writes "still alive", and
any program can fail a job that goes quiet. It works for any number of programs,
but the limit has to be longer than the longest silence, and one API call can be
silent for 36 seconds with the current retries. That would make a timeout in
`api_client.py` quietly decide when `db.py` kills jobs. Too much machinery for
one program.

### Checked by being two programs

The check does not call a function and pretend it is a second program. It
starts real, separate Python processes against a file holding a running sync.
`import db; db.init_db()` has to leave the job running; `import web` has to mark
the same job failed. The first one failed before the change, with the live sync
turned into `'failed'` — the bug reproduced, then fixed.

59 checks: 14 schema, 22 database, 7 retry, 3 render, 13 web flow.

### What I learned

A question put off without a date does not wait, it drifts. The persistence
risk moved milestone twice and was then simply behind. The two new questions in
§12 each have a milestone attached.

And a function named for one job should do one job. Anybody reading
`init_db()` at a call site would assume it only creates tables, which is exactly
how `sync.py` came to call it.

### Next

Rate limiting in `api_client`, shared by every caller inside one program. The
first question there is whether two programs on one machine — `collect.py` and
the local site — also need to share it, since Codeforces sees one address
either way. Then `collect.py`.

---

## 2026-09-13 — A second round of design directions

Not v0.8 work yet, and nothing is decided. Written down because it changes what
v0.8 starts from.

### Why the first round felt merely usable

Checked against a list of the defaults generated sites keep landing on, the
first round did badly. All four typefaces are on that list: Instrument Serif,
IBM Plex Mono, Space Grotesk, Inter. Two of the three directions are among the
most common generated looks: near-black with one neon accent (terminal) and
off-white paper with a serif headline and a dark red accent (editorial). The
live landing page also puts a small label above the headline, which a strong
headline does not need. None of these are wrong on their own. Together they
explain why the result looked like a template, even though it was not built
from one.

### Four more, from the audience's own world

This time the starting point was things a Codeforces user already knows by
heart, not what a technical site usually looks like: a problem statement with
the handle input in the Input box, the rank colours, a calibration plot, and
ICPC balloons. The page is `.claude/design-directions-2.html`. The five problems
on it are real; the 1520-rated history and every probability are illustrative.

My ranking: rank colours first, balloons second, statement and calibration
plot flat.

### The rank colours feel stiff, and why

They are the real handle colours: `#808080`, `#008000`, `#03a89e`, `#0000ff`,
`#aa00aa`, `#ff8c00`, `#ff0000`. Two properties make
them harsh as large fields. They are fully saturated, and their lightness
varies wildly: pure blue is far darker than orange at the same saturation, so
a stack of them reads as uneven blocks. They were chosen to colour a handle in
a line of text, not to fill half a screen. Keeping the hues recognisable while
evening out the lightness is a design task, not a reason to drop the idea.

### Balloons: 2D does not explain itself

A flat cartoon balloon asks the visitor to work out what it stands for. The
idea instead: a 3D balloon per topic in the centre of the page; click one, it
rises, the camera follows, and you arrive at that topic's recommendations. The
material has to be right: light, reflection and the feel of latex or foil.

Three problems before it can be built, recorded in §12: the landing page does
not know a visitor's topics until a handle is synced; per-topic recommendations
are not a v1.0 page (added to §11); and a camera flight on every visit charges
the returning visitor that §4.1 exists to protect. A realistic balloon also does
not explain what it means by itself. Labels do that.

---

## 2026-09-13 — Rate limiting, shared by every thread in a program

Codeforces asks for one request every two seconds. Until today only `sync.py`
was polite about it, with a two-second pause between pages of one history. Two
visitors syncing at once were two threads with no idea the other existed, and
nothing at all paced `collect.py`, which does not exist yet but will make
thousands of requests in a row.

### A queue of time slots

`api_client.RateLimiter` sits in front of every attempt at every request. Each
caller takes the next free two-second slot under a lock, moves the marker along,
lets go of the lock and sleeps until its slot.

```
thread A arrives at 0.0   takes slot 0.0   marker → 2.0   goes at once
thread B arrives at 0.1   takes slot 2.0   marker → 4.0   sleeps 1.9
thread A arrives at 1.2   takes slot 4.0   marker → 6.0   sleeps 2.8
```

Four choices in those few lines, each for a reason:

- **The gap is between request starts.** A request that itself takes 1.5
  seconds owes only half a second more. Pausing after each request finishes
  would make every slow request slower for nothing.
- **Sleeping happens outside the lock.** A thread holding the lock while it
  slept would make everybody behind it wait just to ask for a slot.
- **The clock is `time.monotonic()`, not the wall clock.** The wall clock can
  jump when the computer corrects its time, and a jump backwards of an hour
  would become an hour's wait. A monotonic clock only moves forward.
- **Every attempt waits, retries included.** A retry after "Call limit
  exceeded" is the last request that should jump the queue. When the retry has
  already slept 2 or 4 seconds, its slot has arrived and the limiter adds
  nothing — which the retry checks now prove, because the limiter shares their
  fake clock and any extra wait would show up.

`sync.py`'s own pause between pages is gone. Kept, it would have stacked on top
of the limiter.

### The check that proved nothing

The first version of the threads check released four threads at the same
instant and asserted they went 0.2 seconds apart. It passed. Then, as a test of
the test, the lock was deleted — and it still passed, 20 runs out of 20.

Not because the lock is unnecessary. The gap it protects, between reading the
free slot and moving the marker, is a couple of bytecodes, and the GIL almost
never switches threads inside it. Forcing a switch into that gap with a
one-millisecond sleep made two threads take the same slot at once; the same
forced gap with the lock in place did not. That pair is now a check of its own.

It matters more here than in most projects: spec §7 already notes that the
Windows launcher defaults to the free-threaded Python build, which has no GIL,
and there the race needs no forcing.

What I learned: a check that passes is not evidence until it has been seen to
fail. This one was written test-first and did fail first — for the missing
class. That proved it could see the class was missing, not that it could see
the lock was.

### Not shared between programs

Each program that imports `api_client` gets its own limiter. `collect.py` and
the local site running at the same moment would each keep their own pace and
together go twice as fast.

Sharing a limiter between programs needs somewhere both can see: a lock file,
or a row in a database both open. ADR 0007 just gave the two programs different
database files, and file locking behaves differently on Windows and on the
Linux server. All of that buys the ability to do something with an easy
alternative — not running collect.py while using the local site. On the server
there is only ever one program, so there is nothing to share.

### Run for real

Two syncs started at the same moment, every request's start time logged:

```
  0.03s  user.info    Thread-2
  2.03s  user.info    Thread-1
  4.03s  user.status  Thread-2
  6.03s  user.status  Thread-1
  ...
 40.03s  user.status  Thread-2
 42.03s  user.status  Thread-2
 44.03s  user.status  Thread-2
Benq     done   8585
jiangly  done  11147
```

23 requests, exactly two seconds apart, alternating between the threads until
Benq's shorter history finished. No "Call limit exceeded".

That log is also the next problem. Two visitors at once took 44 seconds between
them; ten would leave the last one waiting minutes, and §9's launch is a blog
post that sends people at once. The pace cannot go up. What the progress page
says while a job waits for its turn can change, and so can whether a stored
history is shown before re-syncing. In §12 for v0.7.

67 checks: 14 schema, 22 database, 7 retry, 8 rate limit, 3 render, 13 web flow.

### Next

`collect.py`: fetch the problemset, then ~2000 users' histories into
`dataset.db`, skipping users already complete. The first question is which 2000
users, since that choice decides who the model learns from — §8's assumption 4
about selection bias starts there.

---

## 2026-09-13 — The limit is exact; the number of requests is not

### Checked against the source

The spec said "roughly one request every two seconds", taken from memory. The
Codeforces API documentation says "at most 1 time per two seconds", with
"Call limit exceeded" past that. An API key unlocks private data such as hacks
during a contest; nothing there says it raises the limit. The pace is fixed.

### What a visitor actually waits for

A visitor waits for the requests queued ahead of them, two seconds each. The
pace cannot change, so the only things that can are how many requests there are
and the order they go in.

**How many.** The 44-second run in the previous entry used Benq and jiangly, two
of the longest histories on the site: 23 requests. A history under 1000
submissions is two requests, `user.info` and one page. Ten visitors like that
arriving together is 20 requests, 40 seconds for the last one. Not minutes.

**In what order.** `RateLimiter` hands out slots to whoever asks next, so ten
jobs interleave and all of them finish near the end. Finishing one job before
starting the next does not help the last visitor, but it helps everyone before
them:

```
ten visitors, two requests each      first done   last done   average
interleaved (now)                        22s          40s        31s
one job at a time                         4s          40s        22s
```

This is the scheduling result from greedy problems: shortest job first
minimises the average wait, provable by swapping any adjacent pair that is out
of order. The catch here is that a job's size is unknown until its first page
comes back.

### Two ideas that the free server cancels

Fetching only a returning visitor's newest page, or showing their stored
history at once, both assume the server still has their rows. On the free
instance a spin-down after 15 idle minutes wipes the database, so the next day
there is nothing to top up or show. Both now hang on the v0.7 storage decision,
which until today was only about counting visits. Recorded in §12.

### A wrong estimate in §7

§7 said 2000 users takes "about an hour". That is one request per user. If
`collect.py` also asks `user.info` separately for every user, it is at least
twice that. Two things to try before writing it: `user.info` accepts several
handles in one call (three came back in one request), and `user.ratedList`
returns every rated user with their rating in a single call, which may make
per-user `user.info` unnecessary for choosing the 2000 at all. Its response is
large, so the 10-second timeout may need to be longer for that one call.

### Something that broke without code

`docs/spec.md` and `docs/devlog.md` were found with the last commit's additions
missing: both files had been replaced, in the same instant, by the copies from
the commit before. Most likely an editor still holding the old text saved it
over the new. Git had the right version and `git restore` brought it back,
but a `git commit -a` would have deleted the rate-limiting entry for good.
`git status` and a look at the diff before every commit is what catches this.

### Next

Unchanged: `collect.py`, starting with which 2000 users, and now also how few
requests per user it can manage.

---

## 2026-09-13 — One request per history

### Measured before deciding

Three things were guessed in the previous entries. All three measured today:

| Request | Result | Size | Time |
|---|---|---|---|
| `user.status` jiangly, no count | 11,148 submissions | 6.3 MB | 2.6 s |
| `user.status` Um_nik, no count | 7,369 submissions | 4.1 MB | 2.2 s |
| `user.ratedList`, active only | 40,929 users; 20,544 rated 1000–1900 | 15.2 MB | 3.6 s |

And 25 random active users rated 1000–1900, whole histories through the real
rate limiter: median 685 submissions, 18 of 25 under 1000, the largest 6,594.
Paging 1000 at a time would have been 41 requests for those 25; whole histories
were 25. The slowest single download was 3.0 seconds.

One worry disappears with the numbers. A 10-second timeout looked too short for
a response of several megabytes, but `urlopen`'s timeout is how long to wait for
the *next* piece of data, not a cap on the whole download. A big response that
keeps arriving never trips it.

### Why sync paged at all

Pages of 1000 existed for one reason: so `/progress/<job>` could count upwards.
At v0.2 that cost almost nothing, because nothing made a request wait. Since the
rate limiter, every page is another two-second turn — jiangly was 13 requests
and about 26 seconds, against 2 requests and about 5 in one go. Most people are
a single page either way, so the saving lands on long histories and on
everybody queued behind them.

So a sync is now `user.info` and one `user.status` with no count. The same two
long histories synced together, request start times logged:

```
  0.02s  user.info    Benq
  2.02s  user.info    jiangly
  4.02s  user.status  Benq
  6.02s  user.status  jiangly
  6.06s  Benq done       8,585 stored
  8.87s  jiangly done   11,149 stored
```

8.9 seconds and 4 requests, where the paged version took 44.6 seconds and 23.
In the browser, Um_nik's 7,369 submissions went from the progress page to the
results table in 4 seconds.

### The progress page lost its number, on purpose

With one request there is no true moment between "none" and "all", so the count
went. The alternative was a simulated bar that estimates progress. §4.1 asks
this page to show a job "without lying about it", and a simulated bar is a lie
that usually gets caught — stuck at 99%. On a product whose pitch is a number
people can trust, the first number a visitor sees should not be invented.

The page now shows the blinking cursor alone at display size, "fetching from
Codeforces", and a sentence that says why it can take longer: everyone takes
turns. The CSS class that held the count was `.progress-count`; it holds no
count any more, so it is `.progress-cursor` now.

### Dropped: fetching only what is new

§12 listed topping up a returning visitor with only their newest submissions.
Under one-request syncs it saves no request — still `user.info` plus one call —
only a couple of seconds of download. And it hid a silent bug. Stop at "the
first submission already stored", and the one stored while it was still being
judged is skipped, so its verdict never arrives. An accepted solution hacked
after an Educational round would keep saying OK for the same reason. A full
fetch gets both right with no extra code. Recorded in §12 as dropped, with the
reason, so it is not proposed again without it.

### For later heavy effects: three layers

Nothing on the site is heavy yet. The rule for when something is — the balloon
experiment, video, anything with a big library — is now in §7.1: plain HTML
underneath, a still image above it, the effect on top only when the device can
run it, and everything served from this site rather than a CDN, because the
common CDNs and Google Fonts are blocked or unreliable in mainland China.

68 checks: 14 schema, 22 database, 7 retry, 9 rate limit and request count,
3 render, 13 web flow.

### What I learned

"Asking for everything at once is fastest" was written in `sync.py` on 09-12 and
was true the whole time. What changed was the cost on the other side of the
trade: a progress count was cheap when pages were free and expensive once each
one waited two seconds. A trade-off written down with its reason is worth
rereading when one side of it moves.

### Next

`collect.py`, starting with which 2000 users. `user.ratedList` gives 20,544
active candidates in the target range, with ratings, in one request.

---

## 2026-09-13 — The typeface moves in

### What was actually known about China

ADR 0006 said the font CDN "is blocked" in mainland China. Checked against
GreatFire, which tests addresses from inside the country: `fonts.googleapis.com`
is *unreliable* — one of its last two conclusive tests, on 2026-08-18, showed
interference — and `fonts.gstatic.com`, which serves the files, was reachable
when last tested in March. So a visitor there sometimes gets IBM Plex Mono and
sometimes does not. "Blocked" was stronger than the evidence.

The part that mattered more was not in the ADR at all. The link to Google's
stylesheet sits in `<head>` and blocks rendering: the browser draws nothing until
that request resolves. When interference means a connection that hangs rather
than one that fails, the whole page stays blank until it times out.

### Is self-hosting slower?

Probably not, and the one advantage people remember for Google Fonts is gone.
A browser used to reuse a font another site had already downloaded from Google;
since 2020 every major browser keeps a separate cache per site, so each site
downloads its own copy anyway. What is left is Google's servers being closer to
most visitors, against two fewer connections to open before the text is final.
Not measured — an estimate of tens to hundreds of milliseconds either way, once
per visitor.

Also a privacy point for `/privacy` at v0.7: every page view used to send the
visitor's address to Google. It does not now.

### Which files

IBM publishes Plex Mono split into subsets by alphabet. "Latin1" covers ASCII,
Western European letters, curly quotes and dashes — every handle, and nearly
every problem name. 17,544 and 17,872 bytes for the two weights, about what
Google was sending. Both were checked against the hashes in IBM's repository
after downloading; `LICENSE.txt` failed that check the first time only because
Git on Windows converts line endings before hashing, and matched with
`--no-filters`. The SIL Open Font License asks for that file to travel with the
fonts, so it sits beside them. `.gitattributes` marks `*.woff2` binary so no
line-ending conversion ever touches a font.

### What falls outside the subset

All 11,401 problem names from `problemset.problems`, checked character by
character against the subset's `unicode-range`: 51 names (0.4%) have at least one
character it does not cover. Nearly all are Russian titles; the rest are `√`,
`⅓`, `θ`, `⟩`, `š` and `ō`.

`unicode-range` in the `@font-face` rule sends each such character to the next
font in `--mono`, one character at a time. On Windows that is Consolas. Rendered
next to Plex, it reads fine and stays aligned, but a Russian title is visibly a
different face — thinner, rounder — and a name that mixes Cyrillic and Latin
letters, like `⅓ оf а Рrоblеm`, shows the change mid-word. IBM's Cyrillic,
Latin2 and Pi subsets would cover all of those except `θ` and `⟩`, which Plex
Mono does not have at all; a browser downloads a subset only when a page uses a
character from it.

### Checked

Two new render checks: no page loads a stylesheet, font or script from another
server, and every `url()` in an `@font-face` is a real file that starts with the
woff2 signature and is served as `font/woff2`. The second exists because a typo
in a font path fails silently — the browser just uses the fallback and says
nothing. In the browser both weights report `loaded`, from `/static/fonts/`,
with no request to Google.

70 checks: 14 schema, 22 database, 7 retry, 9 rate limit and request count,
5 render, 13 web flow.

---

## 2026-09-13 — React for the interactive parts

§12 had React open with three options and a v0.4 deadline. Decided early, at
v0.3: **(b)**, React components mounted into pages Flask still renders. ADR 0008
has the alternatives.

### What a table does and does not need

My first reason was "there will be tables". That is not a reason on its own:
the results page has had a 100-row table since v0.2, drawn by Jinja with no
JavaScript at all. React earns its place when pieces in the browser change each
other — pick a topic in the chart and the table filters; move the target
probability and both re-rank. Written by hand, every change has to be pushed
into every place that shows it, and the bug is the one place forgotten. That is
what the results page is heading towards, and the pet system at v1.5 is more of
the same.

### The honest version of the other reason

I also did not want to switch from (a) to (b) later. Moving later would have
added a build and a mount point without rewriting templates or routes, so this
does not avoid a rewrite; it moves the setup cost forward to before the first
interactive component instead of the middle of one. I would rather pay it once
there.

### What it costs, written down so it is not a surprise at v0.4

- Node and a build step. How the bundle reaches the server is open in §12.
- A JavaScript test tool, because the Python checks cannot see inside a
  component.
- Layer 1 from §7.1 still applies: Jinja draws the page first, and a component
  takes a piece of it over. If the bundle fails, the page still works.
- No Tailwind or component kit comes with it. `style.css` stays the only
  styling system.
- The hours come out of the same budget as §9.

Real-time 3D, if the balloon experiment gets that far, is React Three Fiber —
the same three.js renderer, with ready-made pieces for dropping quality on weak
devices that §7.1's layers need. Whether balloons ship is still v0.8.

---

## 2026-09-13 — Russian titles in the same face

The fallback for characters outside Latin1 looked acceptable on paper and not on
screen. Rendered in the browser next to Plex, a Russian title came out in
Consolas — aligned, readable, and obviously a different typeface — and a name
mixing Cyrillic and Latin letters changed face in the middle of a word.

IBM's Cyrillic, Latin2 and Pi subsets cover every such character in the 11,401
problem names except `θ` and `⟩`, which Plex Mono does not have at all. Six more
files, two weights each, 86,504 bytes in the repository, every one checked
against IBM's hashes. The `@font-face` rules were generated from IBM's own CSS
rather than copied by hand, because a mistyped `unicode-range` fails silently.

Measured in the browser: a page in plain English downloads only the two Latin1
files. Put a Russian title, a `√` and an `ō` on it, and exactly the files for
those characters follow — Cyrillic in both weights because one line was bold,
Latin2 and Pi in regular only. Visitors pay for an alphabet only when they see
it.

---

## 2026-09-13 — Who goes into the dataset

`collect.py`'s first question was not how to fetch 2000 users but which 2000.
ADR 0009 has the decision and the alternatives; this is how it was reached.

### Measured first

`user.ratedList` with `activeOnly=true` returned 40,929 users. Half are rated
1000–1900, the range §2 names. Above 1600 they thin out fast: 835 in 1800–1999,
376 in 2000–2199. Below 1000 are many accounts still in their first six rated
contests, whose displayed rating Codeforces raises in steps, so their number is
not yet their level.

### Stratified, not simply random

A simple random draw from 1000–1999 follows the crowd: about 735 users at
1000–1199 and about 80 at 1800–1999. The model would be weakest for the top of
the audience, and one average would hide that. So: five strata of 200 points,
400 users drawn at random from each, and §9 reported per stratum plus one total
weighted back to each stratum's real share. The weighting is the price —
1000–1199 is 37% of the audience and 20% of the sample, and forgetting to
reweight would quietly describe the sample instead of the people using the site.

### Rating history, because of leakage

The rating-only baseline predicts an attempt from the user's rating. An attempt
from three years ago predicted with today's rating lets the prediction know how
strong the user later became. That is data leakage, and it flatters the baseline
and the model alike, which makes the comparison §9 depends on meaningless. So
every user's rating changes are fetched too: one more request each, about an
hour more, and the alternative is fetching 2000 users again later.

### Filters wait for the analysis

Nobody drawn is skipped. "At least thirty problems" is a `WHERE` clause at v0.5,
and changeable; the same rule applied during collection would be permanent. The
rated list does not report submission counts anyway.

### An idea that was never written down

Before any of this, the plan for testing the model was: hold back a user's most
recent submissions, let the model learn from the earlier ones, and see whether it
predicts the recent ones. Checking the documents turned up only "held-out
submissions" in §9 and "train/test split" in §4 — the actual idea existed only in
conversation. It is in §12 now, for v0.5, with the three details it still needs:
one cutoff date for everyone or each user's own latest submissions, a count or a
share, and whether the unit tested is a submission or a problem. "What counts as
solved?" had no deadline at all; it has v0.5 now, because the harness cannot label
a test attempt without it.

### Next

`collect.py` itself, and the two tables `dataset.db` needs that `nextcf.db` does
not have yet: rating changes, and the record of the draw.

---

## 2026-09-13 — `collect.py`

Written, checked, and tried for real on ten users. The full two-hour run has not
started: the tables it fills were shown first, because changing them after two
hours of collection means collecting again.

### Three commands

`draw` fetches the rated list and stores every stratum's shuffled order. `run`
fetches the problemset, then collects users — whole history and rating changes,
two requests, one transaction — until each stratum has 400. `status` prints the
table. `draw` refuses a second draw, before downloading anything, because a
second draw would silently change who is in the dataset.

### Decisions inside the code

- **The whole shuffled order is stored**, about 21,000 candidates, not just the
  2000. A handle that has vanished is replaced by the next in line; the row
  count per stratum is the population the §9 weighting needs; and a stopped run
  resumes in the same order. Each pool is sorted before shuffling, because the
  API does not promise to list users in the same order twice, and the same seed
  over a differently ordered list gives a different draw.
- **Round-robin across strata.** One user per stratum per round, not stratum
  1000 to completion first. A run stopped after an hour leaves every stratum
  about equally full, instead of a half-dataset of low-rated users that looks
  usable and is biased.
- **Only "not found" skips a user.** Any other refusal — a 403, a proxy's
  error page — stops the run. Recording those as unavailable could empty every
  stratum in minutes while looking like progress.
- **"Collected" is not a column.** It is `users.last_synced`, written in the
  user's own transaction; `sample_strata`, a view, joins the two.

### A bug found on the way, in `api_client`

A history is several megabytes, so a download that stalls halfway is the
likeliest interruption of a two-hour run. Tested against a local server that
sends headers and then goes quiet: `read()` raises `TimeoutError`, and a server
that hangs up early raises `IncompleteRead`. Neither is a `URLError`, so neither
was retried — and in `sync.py` both fell through to "Something went wrong on our
side" for what was only a slow network. They are now retried and, if they
persist, reported as the network failure they are.

### Testing the tests

All thirteen collect checks passed on the first implementation, which after the
rate-limiter lock proves nothing on its own. So `collect.py` was broken on
purpose three ways, each in a throwaway copy:

| Broken how | Caught by |
|---|---|
| fill strata one after another | "a run stopped halfway leaves the strata within one user" — `[3, 3, 1, 0, 0]` |
| shuffle without sorting first | "the same seed draws the same order even if the API lists users differently" |
| treat any refusal as "not found" | "a refusal that is not 'handle not found' stops the run" |

The first attempt at the first mutation changed a counter that the next round
recomputed from the database, so it broke nothing, and "not caught" meant a
broken mutant rather than a missing check. A mutation needs checking as much as
a test does.

### The trial

`draw --per-stratum 2` into a throwaway file, then `run`: ten users, 40 seconds,
4 seconds each — 2000 users is about 2 hours 13 minutes. 11,578 problems
(11,401 from the problemset, the rest ids only seen in histories), 307 rating
changes.

The rating changes did what they are for. One collected user is rated 1843 today
and attempted a 1700 problem in May 2023 at 1515; predicting that attempt with
1843 would have been exactly the leakage ADR 0009 describes. Their first
submissions came before their first rated contest, where "rating then" is
nothing at all — a case v0.5 has to decide, not a zero.

75 checks: 14 schema, 22 database, 9 retry, 9 rate limit and request count,
5 render, 13 web flow, 13 collect.

### Next

The real draw and run, once the tables are agreed.

---

## 2026-09-15 — The real draw, and 800 per stratum

`collect.py draw` against the live list: seed 1918731084, 8,091 / 6,708 /
4,155 / 2,281 / 869 candidates per stratum — about 1,100 more active users than
two days earlier, because "rated in the last month" is a moving window. That is
the reason the draw stores the date it was made.

### 400 became 800

The collection was going to run overnight, and two and a quarter hours of it
would have left the rest of the night idle. So, with 211 users collected, each
stratum was raised to 800: 4000 users, about four and a half hours.

It needed no redraw because the whole shuffled order of every stratum was stored
at the draw — the next 400 per stratum are simply the next in line, the same
users a draw of 800 would have picked. A new command, `collect.py extend`, raises
the number and records the change in `sample_size_changes`. It refuses to lower
it, which would leave collected users outside the sample, and refuses anything
above the smallest stratum, 869, which would make the strata unequal. Three new
checks; 78 in total.

Stopping the first run to restart it was the first real use of ADR 0004 on this
dataset. The process was killed mid-user; afterwards `integrity_check` was clean,
no user had `last_synced` unset, and no submission belonged to an incomplete
user. The half-fetched user had simply never been written.

### Keeping the machine awake

An overnight run on a laptop stops when the laptop sleeps. Changing the power
settings would work and would have to be remembered in the morning. Instead the
collection runs under a Windows `SetThreadExecutionState` request, held by the
process that runs it and released when that process ends — nothing to undo. It
does not stop a closed lid from sleeping.

### Measured while it ran

The first 56 users averaged 783 submissions, which puts the finished
`submissions` table near three million rows and `dataset.db` near 1.3 GB.

---

## 2026-09-15 — The dataset is collected, and v0.3 is finished

### The run

Started 00:56, stopped once on purpose at 211 users to raise the target to 800
per stratum, restarted at about 01:23, finished at 05:24. 3,789 users in about
four hours: 3.8 seconds each, close to the 4 measured on the trial.

No handle was unavailable. No request was retried. Nothing stopped the run that
was not meant to. The screen was off from 01:36 and the laptop stayed awake.

### What is in `dataset.db`

| | |
|---|---|
| users | 4,000 — 800 in each stratum, every one complete |
| submissions | 3,875,775 |
| rating changes | 160,633 |
| problems | 30,082, of which 11,401 are the problemset |
| file size | 680 MB |

Checked: `integrity_check` ok, no foreign-key violations, no user without
`last_synced`, no user outside the sample, no user with zero submissions or
zero rating changes.

One cross-check came free. Every user's rating was recorded twice from
different endpoints — `rating_when_drawn` from the rated list, `cf_rating` from
the last entry of `user.rating` — and all 4,000 agree.

| stratum | median submissions | mean | largest |
|---|---|---|---|
| 1000–1199 | 211 | 368 | 5,690 |
| 1200–1399 | 368 | 651 | 7,114 |
| 1400–1599 | 528 | 886 | 10,725 |
| 1600–1799 | 808 | 1,333 | 13,269 |
| 1800–1999 | 990 | 1,607 | 13,845 |

### Two estimates that were wrong

**Size.** Estimated at 1.3 GB from the first 56 users; 680 MB at the end. The
estimate divided a file size that included a large write-ahead log, and the
problem and candidate tables that are the same size whether 56 or 4,000 users
are collected.

**Submissions per user.** Estimated at 783 from the same 56; 969 over all 4,000.
The medians above are far below the means because a few histories are enormous,
and a mean taken from 56 people in a distribution like that is mostly luck.

Neither mattered — the disk had room either way — but both were stated with more
confidence than 56 users can carry.

### What the data already says

- **Gym is 9.1% of submissions**: 353,922 to 16,874 gym problems, from 2,142 of
  the 4,000 users. Gym problems have no rating and are never recommended. New
  question in §12, for v0.5.
- **1,807 non-gym problem ids are not in the problemset.** The upper bound on
  §12's "one problem, two ids", due at v0.4.
- **4.6% of submissions predate their author's first rated contest**, so there
  is no "rating at the time" for them. For v0.5.
- **61% of submissions are practice**, 26% in contest, 11% virtual, 2% out of
  competition.

### Is 4,000 enough?

Asked last night about going to 6,000. The data answers part of it. For each
rated problem, how many of the 4,000 attempted it:

| problem rating | problems | median attempting | fewer than 10 | 30 or more |
|---|---|---|---|---|
| 800–1100 | 2,405 | 165 | 2% | 91% |
| 1200–1500 | 2,122 | 82 | 7% | 76% |
| 1600–1900 | 2,599 | 47 | 15% | 62% |
| 2000–2400 | 2,777 | 26 | 27% | 47% |

The thin end is the hard problems. But who attempts those is the other half of
the answer: 85% of attempts on problems rated 2000–2400 come from the 1600 and
1800 strata, and 1800–1999 is already 800 of its 869 candidates. More users from
the lower strata — which is where 6,000 would have to find most of them — would
add little where the data is thinnest. If v0.6 shows hard problems are estimated
badly, the lever is more users rated 1600–1799, not more users overall.

### v0.3 is done

| | |
|---|---|
| Rate limiting shared across threads | done |
| `collect.py`, resumable | done, and resumed for real |
| The dataset | 4,000 users, stratified |
| §12 questions due at v0.3 | answered |

78 checks. The dataset is on this machine only, as ADR 0007 intends, and is not
backed up; losing it costs one night.

### Next

v0.4: per-topic solve counts, the rating-only baseline, the topic-breakdown
chart — and before any React is set up, the three things written down for that
moment.

---

## 2026-09-15 — One problem, many ids

v0.4 opened with the two §12 questions due at it. This entry is the first one.
It was supposed to be a filter on the recommender and turned out to be a bug in
the thing v0.4 is actually for.

### The question was only half the problem

§12 said: a problem shared by a Div. 1 and a Div. 2 round has an id in both
contests, the problemset lists one, and a recommender drawing from the
problemset would offer people problems they had already solved. All true.
1,807 of the 13,208 non-gym ids in the dataset are unlisted this way, carrying
146,869 submissions and 48,526 solves across 3,528 of the 4,000 users.

The half nobody had looked at is that **Codeforces tags the two copies
differently**.

```
1292A  NEKO's Maze Game  1400  data structures, dsu, implementation   listed
1293C  NEKO's Maze Game  1400  constructive algorithms, implementation    not
```

"Marcin and Training Camp" manages three ids and three different tag sets:
`1210B` with two tags, `1229A` with three, `1230D` with four.

So a solve was filed under different topics depending on which division its
solver was in. Measured after the map was built: of its 1,527 pairs, 1,142 —
three in four — disagree on tags, and 34,856 solves in the dataset sit on the
wrong side of one. It has a direction. The listed copy is the lower contest id
in 1,493 of 1,527 pairs, which is the Div. 1 half, so the misfiled solves are
the Div. 2 ones, and §2 says the audience is mostly Div. 2.

Per-topic solve counts are the first thing v0.4 builds. So this stopped being a
filter on the recommender and became a correctness bug in the measurement, which
is what moved it to the front of the milestone instead of somewhere inside it.

One suspicion was checked and dismissed on the way. `save_problemset` and
`save_sync` share a writer that replaces a problem's tags every time it sees
one, so a later sync could in principle have overwritten good problemset tags
with worse ones. It had not: all 11,401 problemset problems are stored, and all
11,401 have tags identical to the live problemset. The two copies differ at
Codeforces, not here.

### The database could not answer the question

Nothing in `problems` recorded whether an id was in the problemset. The "11,401
are the problemset" line in yesterday's entry came from `collect.py`'s printed
output, not from a query — the number was true and the file could not reproduce
it. Without that fact stored there is no map to build and no pool to recommend
from, and ADR 0007 requires §9 to be recomputable from the file alone.

That is now `problems.in_problemset`, cleared and re-set on every problemset
fetch so it describes the current fetch rather than an older one — the same
shape ADR 0005 already uses for tags.

### Two methods, and why only one ships

**B, which ships.** Same name, same rating, and exactly one listed candidate.
1,527 of 1,680 unlisted contest ids — 91%.

**A, which does not.** A `CONTESTANT` submission can only be made while its
contest is running, so the earliest one per contest says when that contest
started; contests starting within twenty minutes of each other were run
together, and inside such a cluster problems sharing a name are the same
problem. 325 clusters, 1,251 mapped — 74%.

Both were run against the whole dataset before choosing. They fire together on
1,239 ids and **agree on all 1,239**. That is what made B safe to ship alone:
not that it looked reasonable, but that a method built out of completely
different facts reached the same answer every time it had an opinion.

A is now a check rather than dead code, and it earns its place by being
independent. If Codeforces renames a problem, or a rating moves, or the
clustering window stops being right, the two stop agreeing and something fails
loudly instead of quietly changing §9's number.

§12 warned that name matching alone would not work, and gave `1230D`, which the
problemset lists only as `1210B`, as the awkward case. It is: A maps it to
`1229A`, which is not listed either, so A declines. B goes straight to `1210B`.
Both examples from §12 come out right — `1293C → 1292A` and `1230D → 1210B`.

The 153 ids B leaves alone are mostly not a loss. 134 belong to contests the
problemset omits entirely — April Fools rounds, unrated rounds, contests since
removed — which are unrecommendable whatever happens. The real remainder is 7.

### What it buys

3,360 of the 4,000 users have at least one solve that is invisible without the
map; median 6, mean 13, largest 362. By stratum the count rises steeply, because
stronger users simply submit more:

| stratum | solves the map reveals |
|---|---|
| 1000–1199 | 1,389 |
| 1200–1399 | 3,982 |
| 1400–1599 | 7,043 |
| 1600–1799 | 13,508 |
| 1800–1999 | 16,070 |

### The first migration

Changing `schema.sql` does nothing to a database that already exists — every
statement in it is `IF NOT EXISTS`, which is what makes it safe to run at every
startup and useless for changing a table. So `init_db()` gained `_migrate()`:
each change guarded by a test of what the file currently looks like, so running
it twice does nothing and running it on a half-migrated file finishes the job.

No `schema_version` counter. The guards are the version, they cannot disagree
with reality, and a counter would be a second copy of the truth. When the list
gets long enough to be hard to read, that is the moment for numbered migration
files — not before.

`ALTER TABLE ... ADD COLUMN` on the 680 MB file: **0.0 seconds**, because SQLite
records the column and its default and does not touch a row. The whole
migration, the problemset fetch and the map build together took under two
seconds. Afterwards `integrity_check` was ok, `foreign_key_check` clean, no
alias points at an unlisted problem and no listed problem is an alias.

### A promise that did not survive contact with the work

ADR 0007 left removing `'collect'` from `jobs.kind` for "the next schema change
so one rebuild covers both". This was meant to be that change. It is not.

The premise was that a schema change means rebuilding a table, so a second
rebuild rides along free. Adding a column rewrites nothing, so there was no
rebuild to ride on. Removing a value from a `CHECK` still costs a full rebuild
of `jobs` — rename, recreate, copy, drop — and doing it needs either the table's
definition duplicated in Python or string surgery on the definition SQLite
stores. That is real risk for something with no effect on behaviour, since
nothing writes `'collect'`.

Changing `schema.sql` without migrating was considered for about a minute and is
worse than both: a new database would then disagree with every existing one.
So it stays, with the reason written in the schema next to it, and waits for a
change that rebuilds a table for a reason.

### Found while checking: the server has no problems to recommend

`save_problemset` has exactly one caller, `collect.py`. `web.py` has never
fetched the problemset. So `nextcf.db` knows only the problems its visitors
submitted to, and the rating-only baseline — which runs there — would have had
an empty candidate pool and could only have offered people problems they had
already attempted.

Not built yet, deliberately. It belongs with the recommender, where "the pool
is not ready yet" is a state that has to be designed rather than bolted on. The
free instance wipes the file on every spin-down, so it will be a startup fetch
of one request.

### The React questions

Both answered, both recorded: the bundle is built here by Vite and committed,
Render never runs Node, and a check hashes the component sources at build time
so a forgotten rebuild fails instead of shipping. Building on the host was
rejected mostly because a build failure would take the whole site down, on top
of the cold start ADR 0003 already accepted. Node LTS installed; Vitest decided
and deferred to v0.7, where ADR 0008 already put it.

Tailwind was reconsidered properly rather than waved away, and the old reason
for refusing it turned out to be wrong. ADR 0008 said a component library or a
utility-class framework "would collide with the token file", which lumps two
different things together. A component library ships an appearance, so ADR
0001's argument against Pico.css applies to it. Tailwind ships none, and it can
read CSS custom properties as its configuration, so one source of truth is
achievable. The answer is still no, for a reason that is actually true: React
carries a small minority of this site's markup, so adding Tailwind would mean
two ways of writing styles in one codebase rather than one. The trigger to
recompute it — React carrying the majority, which the v1.5 pet system would
cause — is written into §12 so it is a trigger rather than something that
quietly never happens again.

### Counted

101 checks, 13 of them new. The 78 recorded yesterday does not survive a recount
— summing each script's own "N passed" line gives 88 before today. The number
had been carried by hand; it is now counted by running them.

### Next

The rest of v0.4: per-topic solve counts on top of the canonical tags, the
rating-only baseline recommender with the problemset fetch that feeds it, and
the topic-breakdown chart.

---

## 2026-09-15 — Per-topic solve counts, and a signal that was not there

`db.topic_breakdown()` and `db.problem_totals()`. One `GROUP BY` each over a
user's submissions folded to canonical problems, 13 milliseconds for a
1,803-submission history.

Counting is in problems, not submissions. Three wrong answers and an accepted
one are four submissions and one solved problem, and nobody has practised a
topic four times by failing it three times first. Aliases fold first, so a
Div. 2 contestant's `1293C` and a Div. 1 contestant's `1292A` are one problem,
and the tags come from the canonical copy — the rule ADR 0010 settled this
morning, now with a check that would catch it being broken.

### The column that was supposed to show weakness

The plan was solved and attempted per topic, with the gap between them as the
weakness signal: 5 solved of 40 attempted is a topic someone is struggling
with, 5 of 5 is a topic they have barely opened.

It does not work, and it fails for a reason that is obvious in hindsight.
Across the whole dataset, of 1,817,020 (user, problem) pairs ever attempted,
1,701,748 were eventually solved — **93.7%**. Competitive programmers submit
when they think they are right and then keep going until the problem falls.
The first user checked came out at 95–100% on every single topic:

```
greedy                   393 solved / 402 attempted    98%
dp                       173 / 182                     95%
data structures          123 / 129                     95%
constructive algorithms  192 / 199                     96%
```

A number that is 96% for everybody and every topic separates nobody. The
column stays, because "0 of 30" and "0 of 0" really are different and it costs
nothing, but nothing gets built on top of it.

### What was there instead

Difficulty. Same user, same topics, mean rating of the problems they solved:

```
trees            1800        brute force     1399
graphs           1700        greedy          1348
dfs and similar  1700        math            1329
dp               1546        implementation  1323
```

A 400-point spread where the solve ratio had a four-point spread. So the
breakdown gained two columns: `rated_solved` and `mean_solved_rating`.

Mean rather than median: SQLite has no median, and problem ratings are bounded
and roughly symmetric inside one user's range, which is the case where the two
agree. That is not in tension with yesterday's warning about estimating from 56
users — that was about a heavy-tailed quantity, submissions per user, where the
mean is mostly luck. Ratings are not that.

`rated_solved` is a separate column and not a detail. A third of the problemset
has no rating, and one of the two users checked had topics where the mean rested
on one or two problems. A mean over 2 and a mean over 393 must not look alike in
a chart.

### What the chart is allowed to claim

Not skill. The per-topic means cannot even be compared with each other as they
stand, because tree problems are rated higher than implementation problems for
everyone — a higher mean in trees may be a fact about trees rather than about
the user. Asking how far up a topic's own difficulty range somebody has climbed,
relative to people like them, is exactly what model.py is for at v0.6.

So v0.4's chart describes practice and says so, and §7.1 now records that the
wording changes at v0.6. Writing "you are weak at dp" from these numbers would
be the project claiming the thing it exists to measure, three milestones before
it has measured it.

### ADR 0004 made literally true

That ADR says one gatekeeping function enforces the completeness rule "rather
than remembered in five". It was a sentence inside `get_submissions`, and the
two new queries would have been the second and third place to remember it. It
is now `has_complete_data()`, which all three call. The rule it protects is not
"some rows are missing" but "some rows are missing and nothing says so", and it
only takes one reader that forgot to ask.

Both new functions return None for a user who was never synced or whose sync did
not finish, the same three-case contract `get_submissions` already had.

### Counted

115 checks, 14 new. The most valuable one is that the tags come from the
canonical copy: every other check here would still pass with that rule broken,
and the bug is invisible — a number wrong by one topic, on the page whose whole
job is to say which topics you are good at.

### Next

The chart itself, and the rating-only baseline with the problemset fetch that
feeds it.

---

## 2026-09-15 — The topic breakdown, on the page

`/results/<handle>` now opens with the breakdown and the submissions table below
it, because the table is a log and the breakdown is a shape.

### It is a table, not an SVG

ADR 0001 said "server-rendered SVG for the topic-breakdown chart", and §7 said
"the topic breakdown is the one thing a template cannot give us". The second
sentence is just wrong — a proportional fill is one `linear-gradient` with two
stops at the same position — and the first turned out to be the less important
half of its own decision.

What that ADR actually argued was against a chart library: no runtime
dependency, no canvas, Jinja already has the data, it has to survive with no
JavaScript and appear in a screenshot. A table satisfies every one of those. So
the rule against chart libraries stands and the SVG half is narrowed to charts
whose geometry is not rectangles — the calibration plot §9 wants will be SVG,
hand-written, still with no library.

Three things the table does better, and none of them are close. A screen reader
reads thirty-nine rows of numbers with no ARIA written for it. It reflows —
checked at 320, 375 and 1085 pixels. And it is literally the markup ADR 0008
describes a React island mounting onto: "a table is drawn by Jinja first and the
component takes it over."

ADR 0001 amended, §7 corrected.

### The bar's shape was decided by a failure

First version: the bar had a column of its own, an 8px track with a fill inside
it. Fine on a laptop. At 375px the track measured **2 pixels**.

The arithmetic is not subtle. The label wants 125px, `948/964` wants 71, and
`1776 (926 rated)` wants 141 because it was told not to wrap — 337 of the 343
a phone has. The bar column was the flexible one, so it got what was left,
which was nothing. Adding a minimum would have pushed the page into a sideways
scroll under a chart whose entire point is a horizontal comparison.

So the bar stopped being a column and became the row's own background, a
gradient with a hard stop at the percentage. A background cannot be squeezed by
its neighbours. That is not a fix, it is the failure being made impossible, and
it collapses two layouts into one mechanism that works at every width. The
narrow-screen rules that remain are two lines: let the rating cell break at its
own space, and drop the column gutters one step to `--s1`.

Verified at 320px, the narrowest phone worth worrying about: no sideways
scroll, the longest bar spans all 288 available pixels.

### A floor, and why it is honest

One solve against a best of 948 is 0.1% of the row — a pixel, which reads as a
rendering fault. But "you have solved one" and "you have never solved one" is
exactly the distinction this chart exists to draw, so the width has a floor of
1%, and a topic with nothing solved still gets a true zero and no bar at all.
Exaggerating 0.1% to 1% is the more truthful rendering, not the less: the exact
figure is in the next column, and the bar's job is shape.

### No green anywhere in it

Thirty-nine accent-coloured bars would turn the accent into decoration, and ADR
0006 spends it on one meaning — this is good, or this is where you act. The
bars are `--muted` on the canvas, and the accent is being saved for the
recommendations.

That is the single most tempting edit anybody will ever make to this
stylesheet, so it has a check: any rule whose selector names a chart element and
reaches for `--accent` fails it.

### What the page is allowed to claim

Under the heading, one line: *What you have practised. Not yet how good you are
at it.* Under the chart, the two things that look like mistakes and are not —
the Solved column adds to more than the problems solved, because a problem
carries about three tags; and some solved problems have no tags at all, so no
row can account for them. tourist has 162 of those.

The footnote also says the per-topic averages are not comparable between rows
yet. Writing "you are weak at dp" from these numbers would be the project
claiming the thing it exists to measure, three milestones early.

### Smaller

The header said `v0.2` while v0.3 was finished. Fixed. A stale version number
on a live page is the same class of tell as an unhandled error.

### Counted

127 checks, 12 new. The two that earn their place are the bar widths — a chart
that is wrong is worse than no chart, because it is wrong confidently — and the
accent rule.

### Next

The rating-only baseline recommender, with the problemset fetch at startup that
ADR 0010 says it needs, and which the chart also wants before it can say "you
have never attempted flows".

---

## 2026-09-17 — The rating-only baseline, and the question it could not avoid

The results page opens with five recommendations now. Getting there meant
measuring what the baseline should be before writing it, and the measurement
changed the plan twice.

### Elo's formula is not a baseline for this data

The obvious baseline was Elo's own curve, `1 / (1 + 10^(-gap/400))`, since that
is how Codeforces ratings are built. Checked against 1,578,181 first attempts —
one per (user, canonical problem), with the rating each user had *at the time*
from `rating_changes`:

| user − problem | first try accepted | Elo says |
|---|---|---|
| ≤ −800 | 37% | 1% |
| −200..−1 | 50% | 36% |
| +400..+599 | 72% | 95% |

Several times too steep. People attempt hard problems when they already have a
good chance — the selection effect §8 assumption 4 predicted, now with a number.
A baseline that says 1% where the truth is 37% would lose to anything, and §9's
"beats the baseline" would then be about calibration, not topics.

So the baseline is fitted: a logistic curve in the rating gap, two parameters,
maximum likelihood by Newton's method written out in `model.py`. `a = 0.2550`,
`b = 0.1215`. Fitted on counts per distinct gap rather than 1.5 million rows,
which gives the identical answer — ratings are integers and problem ratings are
multiples of 100, so there are only a few thousand distinct gaps and the counts
are everything logistic regression uses.

The check that matters most on it feeds the fit expected counts from a curve
chosen in advance and asserts that curve comes back out to six decimal places. A
fitting routine only ever run on real data can be wrong forever, because nobody
knows what the right answer was.

### A bug that looked like a finding

The first run of the measurement had "first try" and "eventually" identical in
every row. That is not a property of competitive programmers; it is SQLite. The
query leaned on the rule that a plain column in a `MIN()` query comes from the
row holding the minimum — a rule that only holds when there is exactly *one*
min or max in the query. There were two, so the "first verdict" came from an
arbitrary row, which happened to be the accepted one.

The tell was that the numbers were too tidy. Real data does not agree with
itself to the percent in nine rows out of nine. Rewritten with `ROW_NUMBER()`,
which says what it means and relies on no rule. Two days ago this same trick was
kept out of `_rebuild_aliases` on the grounds that most readers would have to
look it up. It turns out the writer did too.

### The question that arrived two milestones early

§12 scheduled "what counts as solved?" for v0.5. The recommender cannot pick a
problem without it:

- **Eventually accepted** runs from 82% to 99% across 1,600 rating points.
  People keep going until the problem falls, so the curve barely moves. 70% is
  not on it; the fit puts 70% at problems 1,318 points *above* the user, far
  outside anything measured.
- **First submission accepted** runs from 37% to 83%, and puts 70% at problems
  about 490 points *below* the user.

Which also means §1's 70% points the opposite way from the usual advice to
practise a little above your rating, which this curve puts near 50%. §8 calls
70% a guess not established for competitive programming, and this is the first
thing measured that bears on it.

That decision belongs to the author and was not taken silently. The recommender
runs on "first try" with the target unchanged, the page says in words exactly
what its percentage means, and ADR 0012 and §12 record both as provisional.

Also noted: log losses cannot be compared across the two events. "Eventually"
scores 0.207 and "first try" 0.639, and the smaller number means nothing — an
event that happens 94% of the time is easy to predict. Written into §9 so the
harness never compares them.

### A trap written down before anyone falls in it

`baseline.json` is fitted on all of `dataset.db`, and the page should use
exactly that. But the v0.5 harness must not: whatever it holds back for testing
is inside the data this file was fitted on, so scoring the test set with it
gives the baseline a look at the answers, and nothing would warn anyone. The
harness refits on its training portion. It is in ADR 0012 and §9 now, because
by v0.5 the reason would be forgotten and the file would look like the obvious
thing to reuse.

### The problemset reaches the server

ADR 0010 found that nothing but `collect.py` ever fetched the problemset. The web
app now does, in a background thread when it starts — started by `serve.py` and
by `python web.py`, never by importing the module, because every check imports
it and none of them may reach Codeforces. The debug reloader runs `web.py`
twice, so the fetch waits for the child that actually serves; otherwise every
save during development would spend two requests. The results page says "still
loading" until the problemset arrives rather than guessing from an empty pool,
because an empty pool also means somebody has solved everything.

### On the page

Five problems, the rating of each, and the chance — in the accent colour, the
first thing on the results page to use it outside an OK verdict, because it is
the one place anybody is being asked to act. One sentence says what the number
is, and that everybody at the visitor's rating is shown the same five, which is
precisely what the baseline is and what the model exists to fix. An unrated
visitor is told why there is nothing, rather than shown an empty table.

Two things caught in the browser: the centre rating printed as `2800.0`, because
`round(x, -2)` returns a float; and the sentence said "at your rating — around
2800", which reads as if 2800 were the visitor's own rating. Both fixed, the
first with a check.

### Counted

147 checks, 20 new. The staleness check refits the whole baseline from
`dataset.db` and compares it with the committed file, the same way the React
bundle will be guarded.

### Next

The author's decision on the event and the target. Then React takes over the
topic chart, which is where ADR 0008 said it would start.

---

## 2026-09-18 — How wrong the baseline is, and in which directions

Measured to answer two questions: how far the baseline's probabilities are from
what really happens, and what a better model would have to know. Nothing in the
code changed.

### What a log loss number means

| predictor | log loss |
|---|---|
| know nothing — always say 58.9%, the overall first-try rate | 0.6773 |
| Elo's formula, unfitted | 0.9135 |
| the fitted baseline | 0.6392 |

Elo is worse than knowing nothing. Log loss punishes confidence that turns out
wrong far harder than it rewards confidence that turns out right, and Elo says
1% about attempts that succeed 37% of the time. That is ADR 0012's argument in
one number.

The more sobering line is the gap between the first and third rows: knowing the
rating gap takes log loss down by 5.6%. Most of what decides a first attempt is
not in the rating. That is the headroom the v0.6 model has, and it also says
what a realistic win looks like — a few hundredths, not a halving.

### In-sample flatters it, and time is why

Calibration — group attempts by what the baseline predicted, compare with what
happened — measured on the data it was fitted to: an average gap of 2.0
percentage points.

Then fitted on attempts before 2025 only, and scored on the 1,004,413 from 2025
on, which it never saw: 3.4 points, and every band had the same sign. The model
under-predicted everything after its cutoff, by as much as 11.9 points on the
hardest problems. By year of attempt the error drifts steadily, from 6 to 9
points too optimistic in 2016–2018 to 3 points too pessimistic in 2026.

This is illustration, not §9's protocol — the cutoff was picked for the
demonstration. But it is evidence for §12's split question: a random split would
have reported the flattering 2.0, because it mixes every year into both halves.
A split by time reports what happens to a model that is used after it was
fitted, which is the only way it will ever be used.

The likeliest cause is that a rating lags a skill that is changing. Someone
improving quickly solves above their rating until the next contest catches it
up, and the users in this dataset were drawn for being active now. The rating
system itself has also changed over the years — ADR 0009 already notes the
step-by-step scheme new accounts get today. Both are hypotheses. Knowledge
tracing (§11) exists for the first.

### The errors have structure

Mean prediction against real rate, split by things the baseline cannot see:

| | predicted | real | gap |
|---|---|---|---|
| in contest | 63.6% | 60.9% | −2.7 |
| in practice | 54.4% | 56.7% | +2.3 |
| users rated 1000–1199 | 54.0% | 57.9% | +3.9 |
| users rated 1800–1999 | 61.5% | 59.8% | −1.7 |
| constructive algorithms | 59.6% | 53.1% | **−6.5** |
| binary search | 53.5% | 49.8% | −3.7 |
| dp | 52.6% | 53.1% | +0.5 |

Random error would scatter around zero whichever way the attempts were grouped.
This does not: contest attempts fail more than their rating says, practice
attempts succeed more, and a constructive problem is six and a half points
harder to get right first time than its rating suggests — for everybody.

That last row is the first direct evidence for §3's claim that topics carry
information rating does not. It is a property of the topic, before anything is
known about a particular user's skill in it. The per-user part — that one
person is weak at constructive and another is not — is what the model has to
find next.

### Two kinds of wrong

Worth separating before anyone tries to "minimise the gap". Calibration error is
systematic: the baseline says 53% for a group that succeeds 50% of the time,
and that can be fixed. The other kind cannot: one attempt succeeds or it does
not, so even a perfect model saying 60% is "wrong" on four attempts in ten.
Log loss has a floor above zero, set by how unpredictable a single attempt
genuinely is, and nothing gets below it.

And the fit is already the best curve of its shape — that is what maximum
likelihood means. Doing better needs more information in, or a different shape,
not a better fit of this one.

---

## 2026-09-18 — The most accurate model the data allows

The instruction was: add information to the prediction, whatever it costs,
because everything the recommender does later stands on it. Two things were
settled before any of that, and one was corrected.

**Settled: first try, and 50%.** The recommender aims at problems whose first
submission is accepted half the time. Under the baseline that is about 200
points above the user's rating, where ordinary advice puts practice; such a
problem is solved *eventually* about 93% of the time; and an attempt at 50% is
the one that tells the model most about the person making it — in a Rasch model
an item's information is P(1 − P), largest at one half, the reason adaptive
exams work that way. 70% had meant problems 500 points below the user.

**Corrected: "perfect".** No model can know whether one particular submission
will pass; one attempt is a coin toss even to the true probabilities. What can
be had is the lowest log loss on data the model has never seen, and
probabilities that mean what they say. That is what was built towards.

### The order: the harness first

"More accurate" means nothing without something that can say a change made it
worse. So v0.5's harness came before v0.6's model, and ADR 0013 fixed the
protocol before any model was scored: first attempts per (user, problem); a
date split — train before 2025-07, validation to the end of 2025, test from
2026, looked at once; the baseline refitted on train; the user's own terms
refitted month by month from their past only, the way the website will; strata
weighted by population.

The leakage rules got checks rather than comments. Flip every result a user has
after some month, and every prediction before that month must not move by one
bit. It does not.

### The model

Logistic, additive, one term per kind of information, each switched on in turn
and kept only if validation log loss fell (ADR 0014 has every row):

| added | validation | gain |
|---|---|---|
| rating-only baseline | 0.6533 | |
| context: contest or practice | 0.6515 | 0.0018 |
| how hard the topic is | 0.6456 | 0.0059 |
| **how hard this particular problem is** | **0.6195** | **0.0261** |
| the user, beyond their rating | 0.6148 | 0.0046 |
| the user in each topic | 0.6147 | 0.0001 |
| recent history counting more | 0.6139 | 0.0008 |
| the gap's curve allowed to bend | 0.6126 | 0.0012 |
| **the user's rating level itself** | **0.6058** | **0.0069** |
| experience | 0.6049 | 0.0009 |
| position in the contest | 0.6044 | 0.0005 |
| a line in time | 0.6038 | 0.0005 |

Two rows carry most of it. A problem's own first-try record, measured from the
crowd, is worth more than everything else together — rating says how hard a
problem is to solve, the record says how treacherous it is to submit. And the
user's rating level, not only its distance from the problem's: at the same gap,
a 1100 gets it right first time more often than an 1800 does.

Calibration got worse through the first round, from 1.8 points to 3.0, and back
to **1.0** by the end of the second. The time trend fixed it: first attempts
succeed a little more often every year, and a model fitted on the past was
pessimistic about the future until it could see time. In the 45–55% band where
recommendations are chosen: said 45.0%, happened 45.0%; said 55.0%, happened
55.4%. A calibration layer on top made things worse and was left out.

### The row that matters most is the smallest

"The user in each topic" — §3's "fine at greedy, weak at trees" — is worth
+0.0001 added and +0.0002 taken back out. It stays, because it helps, but it is
nowhere near the story §3 tells. Topics matter as a property of the *topic*:
constructive algorithms is harder on a first try than its rating says, for
everybody.

The likeliest reason is the one §8's fourth assumption named before any of
this existed. People choose their own problems. Someone weak at trees attempts
the tree problems they can do, so their record in trees looks fine, and the
weakness is hidden in the choosing. A recommender that chooses *for* them is the
one situation where the signal could surface — so it is not dead, it is
unmeasurable from this data, and it should be measured again once
recommendations are being acted on.

§3 has been annotated with this, not rewritten. What the product can honestly
claim changed; what it is for did not.

### Three bugs in the fitting, all caught by checks built to catch them

**It never converged.** The first full run hit its 60-sweep ceiling on every
fit. An additive model has directions along which parameters trade a constant
without changing a prediction — every user's number up by 0.1, the intercept
down by 0.1 — so the loss is flat and coordinate steps crawl. Each has a closed-
form best point, so the fit now jumps there after every sweep: 6 sweeps instead
of 167 on the synthetic check, and a check recomputes the objective from the
parameters to prove the jumps move no prediction.

**Two directions were missed**, and the check found them: a topic's difficulty
could sit in the topic or be spread across every user's skill in it, or across
every problem carrying it. The topic's gradient sat at 0.06 until they were
added. It mattered beyond speed — a new problem or a new visitor only ever sees
the topic's number, so whatever of it was parked elsewhere, they never got.

**A check that was wrong.** With all the extra columns in, the level column's
gradient read 2.2e-2 and failed. Its curvature was about 8,000, so the parameter
was 3e-6 from its optimum — closer than the tolerance on anything else. The
check was measuring raw gradient where it should measure how far a Newton step
would still move the column. Fixed in the check, not the model.

### What the small runs got wrong

Every ladder was first run on 200 users, to check the code before spending an
hour. On those 200, topic difficulty made predictions *worse*, by 0.0037. On
all 4,000 it made them better by 0.0059 and turned out to be what a new problem
falls back on. A 200-user run exercises code and says nothing about models; the
09-15 entry learned the same thing about a mean taken from 56 users, and it was
true again.

Three regularisation grids put their best value on the edge of the grid, which
means the real best was outside it. Each was widened before the full run.

And the first ladder added each kind of information in a fixed order and kept
it regardless, so a part that only helps in company could not show it. An
ablation was added at the end — the full model with each part taken out — and
it is the table that decides what stays.

### The test

Configuration written into `evaluate.FINAL` and committed first (487c76a), so
the record shows it was chosen without the test set. Then 2026, once:

| | baseline | model |
|---|---|---|
| weighted total | 0.6535 | **0.5989** — 8.4% lower |
| 1000–1199 | 0.6684 | 0.6043 |
| 1200–1399 | 0.6540 | 0.6018 |
| 1400–1599 | 0.6416 | 0.5913 |
| 1600–1799 | 0.6328 | 0.5906 |
| 1800–1999 | 0.6225 | 0.5824 |
| calibration | 4.8 points | 1.6 points |

Every stratum. **§9's first criterion is met.** The model is still about two
points pessimistic in the middle of the range in 2026 — said 45.2%, 47.9%
happened — where the baseline said 45.6% and 51.0% happened.

### Shipping it

`topic_model.json`: the crowd's part, 10,996 problems and 39 topics by name,
244 KB, fitted on all 1,578,181 attempts. The website folds a visitor into it
from their own history, having built their inputs with the harness's own SQL
and derivations — a check compares the two on 25 real users, every field of
every attempt, because the day they differ the site runs a model nobody scored.

One thing was found only by thinking about who will actually visit. The model
learned from users whose rating at the time sat, 99.8% of it, between about 350
and 2370, and its level term is a straight line. At tourist's 3528 that line
would add −1.95 to the log-odds — a thousand points of extrapolation dressed as
a measurement. The shipped model holds the level to the range it saw, and the
page tells anyone outside it that their chances are an extrapolation. The time
line stops 183 days after the newest attempt, so if the monthly refits ever
stop, predictions stop drifting instead of walking off.

### What it cost

- **A third request per sync**, for the rating history. Without it a visitor's
  past would be judged at today's rating and anybody who has climbed would look
  weaker than they are. Ten visitors at once now wait a minute for the last,
  not forty seconds.
- **A monthly re-collection**, about four and a half unattended hours, then a
  refit and a commit. `collect.py` cannot do it yet — it skips users it has —
  so a refresh mode is owed before the first one.
- **About two hours of fitting** across the two ladders, the monthly-refit
  comparison and the test. Pure Python throughout: nothing installed.

### Next

`/how`, which now has a number to hold. `collect.py --refresh`. Then React
taking the chart over, which the reorder moved behind this.

---

## 2026-09-18 (evening) — What the user did lately, and a rating the profile hides

The brief, after the push: find any way at all to make the predictions more
accurate — read what has been published, try what has not been tried here —
and make the site faster wherever it can be.

### Faster pages, steadier picks

**A results page spent 42% of its time scoring problems**, one `predict()` call
per problem, 11,000 of them, on a host with a tenth of a CPU. Most of each
problem's logit does not depend on the visitor at all — context, the problem's
own difficulty, its topics, its position — so `PracticeScorer` works that part
out once per fitted model and adds each visitor's part in one tight loop.
79 ms to 32 ms locally for one real history, 64 ms for tourist's. It is a
second copy of the model's arithmetic, which this project otherwise avoids, so
a check scores every problem both ways, with every column switched on and both
guard rails in play, and fails on any difference.

**The five recommendations reshuffled** whenever the clock moved. For a typical
user 143 unsolved problems sit within half a point of 50%, and the model is
calibrated to about a point and a half — so "the five nearest" was choosing on
noise. Now every problem within 2.5 points of the target counts as equally
right, and the five are chosen among them on something that means something:
the newest first, then each one sharing the fewest topics with those already
picked. The first version picked whatever added the most *new* topics and so
always opened with the problem carrying the most tags — eleven, for one real
user. A long tag list says more about the labelling than the lesson.

### Reading first

What has been measured on data like this, and what of it applies:

- **DAS3H** (Choffin et al., EDM 2019): this model's exact shape — ability,
  item and skill difficulty — plus counts of recent attempts and successes per
  skill, in time windows. The most direct fit.
- **Gervet et al.** (JEDM 2020): logistic regression on such counts did best
  on datasets of moderate size or with very many attempts per learner; deep
  knowledge tracing on the largest, or where precise timing matters most.
  Ours has hundreds of attempts per user, and no deep learning stack.
- **Logistic knowledge tracing** (Pavlik et al.): a recency-weighted share of
  recent successes.
- **Knowledge tracing machines** (Vie & Kashima 2019): this model already is
  one, with the pairs that matter.
- **Debiasing for self-selection** (TSDR, 2026): real, and untestable here —
  the test set chooses its problems the same way the training set does.

### A screen before a fit

A full fit with new columns takes a quarter of an hour, so candidates were
screened first: stack them on the current model's validation predictions, fit
on 2025-07..09, score on 2025-10..12. It answers "is there information here the
model lacks?" in minutes. Gains in log loss:

| candidate | gain |
|---|---|
| overall recent form, 1 hour to 30 days | +0.0023 |
| practice in the problem's topics, 1 hour to 30 days | +0.0016 |
| practice in the problem's topics, all time | +0.0012 |
| recency-weighted success share | +0.0012 |
| a new account's hidden rating (below) | +0.0012 |
| rating dynamics: peak minus current, recent changes | +0.0011 |
| previous attempt's outcome | +0.0007 |
| level × topic | +0.0006 |
| all-time successes | +0.0004 |
| time since the previous attempt | +0.0003 |
| the problem's age at the attempt | +0.0002 |
| having been in the problem's contest | +0.0000 |

### The rating on the profile is not the rating

The screen's second round asked what the rating itself might be hiding, and
Codeforces' own rules answered. Since May 2020 a new account is computed from
1400 but shown 0, and what is shown gets 500, 350, 250, 150, 100 and 50 added
after its first six rated contests. After one contest the profile says 900
less than the rating Codeforces works with. The model read the profile.

| contests so far | hidden | model said | happened |
|---|---|---|---|
| 1 | 900 | 46.3% | 56.7% |
| 2 | 550 | 51.1% | 59.8% |
| 3 | 300 | 55.2% | 58.4% |
| 4 | 150 | 58.1% | 60.3% |
| 5 | 50 | 58.8% | 57.7% |

The error shrinks exactly as the hidden amount does, and 12% of all attempts
in the dataset are by accounts still inside their first six contests.

**The first rule for spotting a new account was wrong.** It took "first rating
change starts from 0" to mean the new system. All 4,000 accounts start from 0
in the API — the ones from before 2020 jump straight to about 1400 after their
first contest, the new ones to about 400. Looking at the first contests of
2020 in order put the switch between contest 1355 (16 May) and contest 1358
(26 May), so the rule is by date.

### The full model

Validation, frozen at its start:

| | log loss |
|---|---|
| round two (ADR 0014) | 0.6038 |
| + the computed rating alone | 0.6031 |
| + practice history | 0.6012 |
| + practice history + computed rating | **0.6010** |
| + practice history + hidden amount as learned columns | 0.6008 |
| + that + rating dynamics | 0.6008 |

History is the prize: 0.0026, every stratum better, a quarter as much again as
all of round two's columns. Refitted monthly, as the product runs, the whole
of round three scores 0.5980 on validation against round two's 0.6007. On top of it the rating's contribution is small,
because a newcomer's rapid improvement already shows in how much they are
winning lately.

**Is the history too fresh to be fair?** Every attempt in the evaluation has
its history counted up to the second before it. The website counts up to the
moment the page is opened, and the attempt comes minutes or days later. So
the whole model was refitted twice more with the history counted as of an
hour, then a day, before each attempt: 0.6007 and 0.6015, against 0.6010 fresh
and 0.6031 without. An hour costs nothing — slightly better, within noise — and
a day keeps three quarters of the gain. The number was not flattered by the
freshness.

**The computed rating was kept over the learned columns** despite 0.0002. That
difference is below what validation can resolve, and the learned version would
be learning partly from how the sample was drawn: everyone in it reached
1000–1999 by September 2026, so its new accounts are the ones that succeeded.
A real newcomer is not preselected to succeed. Adding back what Codeforces hid
is arithmetic that is true of every account. The results page now says so when
it applies — "Codeforces shows you 700 but computes with 1250" — because
otherwise a newcomer sees problems picked for a rating they have never seen.

### Tried and taken out

With history on, a fit needs 33 sweeps instead of 5 to 13. The guess was that
the history columns and each user's own number, both saying how strong a user
is, were undoing each other's steps, so they were stepped together — an exact
Newton step for the global columns and every user's b at once, cheap because
each attempt has one user. Built, checked, measured: still short of
converging after 27 sweeps, against 33 for the plain step to finish. The slow
direction is somewhere else — most likely the topic columns against each
user's topic numbers — and seventy lines that would save a tenth of a fit
at best were deleted.

### Smaller things

- **A sync is two requests again.** `user.info` was fetched for the handle's
  spelling and the current rating, and both were already in the other two
  answers. Two seconds off every sync; the tenth visitor in a queue waits
  40 seconds, not 60.
- **`collect.py refresh`** fetches every collected user again, oldest first,
  resumable, drawing nobody new: the monthly refit can now actually happen.
  A collected user whose handle has gone keeps their rows and their place.
- **The laptop went to sleep for three and a half hours** in the middle of the
  full-model runs. Two of them report 13,500 seconds for work that takes 800.
  Long runs need sleep switched off.

### The test, a second time

Round three was committed in `evaluate.FINAL` (fb5a987) before the test set
was scored for it — on the terms of ADR 0013's amendment: the number is
reported whatever it is, and decides nothing. Nine monthly refits, from 37
sweeps for the first (cold) to 6–12 for the rest, about 75 minutes:

| | baseline | round two | round three |
|---|---|---|---|
| weighted total | 0.6535 | 0.5989 | **0.5934** |
| 1000–1199 | 0.6684 | 0.6043 | 0.5992 |
| 1200–1399 | 0.6540 | 0.6018 | 0.5956 |
| 1400–1599 | 0.6416 | 0.5913 | 0.5855 |
| 1600–1799 | 0.6328 | 0.5906 | 0.5868 |
| 1800–1999 | 0.6225 | 0.5824 | 0.5766 |
| calibration | 4.8 pt | 1.6 pt | 1.5 pt |

9.2% below the baseline now, against 8.4%, in every stratum. The gain on the
test year is twice the gain on validation (0.0055 against 0.0027), which fits
where it comes from: the newer the attempt, the more of it is made by new
accounts and by people in the middle of a burst of practice. The model is
still about two points pessimistic in 2026 — said 45.2%, happened 47.5% —
which is what ADR 0015 expects of a sample drawn on its future rating.

This test set is now spent. The next model is judged on what the October
refresh brings: months no model has seen.

### Next

- The first `collect.py refresh` and refit in October — and with it a fresh
  test window.
- What to do for a visitor with no rating at all, now that Codeforces' own
  answer is known — it computes a new account from 1400, and the 4.6% of
  attempts made before a first rated contest can say whether that works.
- `/how`, which now has a number to hold.

---

## 2026-09-19 — Round four: five more ideas, none of them better

Asked whether anything more could be had, by any method, as long as the
website did not get slower. Read first — item response theory, knowledge
tracing benchmarks, Elo systems with adaptive update sizes, multidimensional
models — then tested the five candidates that would cost the site at most a
multiply per problem. Validation, frozen, against round three's 0.6010:

| candidate | validation | |
|---|---|---|
| each problem its own slope on the rating gap (2PL), penalty 100 | 0.6009 | within noise |
| the same, penalty 30 | 0.6015 | worse: it fits noise |
| topic difficulty depending on the level | 0.6016 | worse |
| the fold-in's half-life 365 days instead of 180 | 0.6010 | no change |
| half of the users in training | 0.6017 | what 2,000 more users were worth |

**2PL** is the textbook step up from this model's shape: a problem that
separates strong and weak users sharply gets a steep slope, a trap that
catches everybody a flat one. The slopes do differ — the middle 90% run from
−0.09 to +0.08 around 0.10 — but knowing them predicts nothing better. The
research summary matches: over a model that already has per-problem
difficulty, per-item discrimination often does not pay.

**Level × topic** was the screen's best remaining candidate at +0.0006 and is
worse in the full model. The screen fitted its weights on the first half of
validation and scored the second; fitted on the training years, the pattern
does not carry forward. A screen says information exists *somewhere near the
validation period*; only the full model says whether it can be learned from
the past. That difference was always there, and this is the first time it
decided something.

**Half the users** costs 0.0007. Doubling the dataset again would be worth
less than that, for four and a half hours of collection and double the
monthly refresh. The model is not short of data.

Every round has been worth less than the one before — 0.039, 0.010, 0.003 for
the monthly refit, 0.003 for round three, nothing for round four — and the
last five ideas moved the number by less than it moves between two random
halves of a month. With this data and this kind of model, the prediction is
about as good as it gets. What would move it is new information: the fresh
sample and the October window for the pessimism, and above all what people do
with problems the site chose for them — the one setting in which a weakness in
a topic can show, because the user did not pick the problem.

Nothing from this round ships; the code stayed in the experiment.

---

## 2026-09-19 — `/how`, and a landing page that had stopped telling the truth

**The landing page was wrong on the live site for two days.** Written at v0.2,
it said the site would *eventually* pick problems at a 70% chance, and then, in
bold: "Right now it does none of that." Both became false on 09-17, when the
recommendations went live, and nothing checked the pitch against the product.
Now it says what the site does and what it can back up, and links to where
that is shown. The version beside the name still said v0.3, and the button
still said "Show my submissions". A check now fails if the landing page claims
the site does nothing, or mentions 70%.

**`/how`** is §4.1's page: what the percentage means, what the model knows
about a problem and about a visitor, §9's number by rating band, and a
calibration table — *when it said 50%, what happened*. It ends with what the
model cannot know, including that it does not claim anybody is weak at a
topic, and why. It is on the quiet surface: prose at the measure, tables for
numbers, no new token.

Two decisions in it:

- **The numbers live in one place in the code**, `web.EVALUATION`, and a check
  compares them with spec §9. The page and the spec making different claims
  about the one number the project exists to publish would be worse than
  either being missing.
- **An honest zero point.** Log loss has no natural scale for a reader, so the
  page gives two: guessing 50% every time scores 0.693, and always guessing
  the usual success rate 0.672. Measured from the second, rating alone gets
  0.019 below it and the model 0.079 — "about four times as far" is a claim a
  reader can check with a subtraction.

Two layout fixes found only by looking: a two-column table of numbers at full
width read as two columns a page apart, so it is now as wide as its contents;
and a header that does not wrap made the first table 9px wider than a 375px
phone, fixed by shortening "Rating at the time" to "Rating band".

v0.6 is done. Next is v0.7.
