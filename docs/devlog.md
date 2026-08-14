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

### Next

Still v0.1: virtual environment, install Flask, get a page to say hello.

Note: the first script does not need Flask or any third-party package.
`urllib.request` and `json` are both in the standard library, so step one can be
written and run today despite `pip` being broken — fetch one user's submissions
from `user.status` and print them.

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
personal defaults stated in the imperative are indistinguishable from
real constraints, and end up in the spec as if they were.

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
