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
