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
