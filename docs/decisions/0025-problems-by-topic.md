# 0025 — Problems by topic, with a target per topic, as the first React component

**Date:** 2026-09-26
**Status:** accepted. The scope change is made; the build follows.

## Context

Spec §11 had per-topic recommendations at v1.5: "pick a topic, get problems
in that topic near the target probability", with the page and small topics
named as the cost. The audit of 2026-09-26 made two findings it answers. The
38-row topic table on the results page was information nobody could act on.
And difficulty was the only thing a visitor could steer. The author moved it
into v0.8, changing the spec first, as §5 requires of anything added to v1.0.

Measured before designing: after ADR 0023's guard rail, the topics are very
uneven. For a visitor rated 1000, greedy and math keep over 1,000 candidates
each, trees 47, dsu 35, probabilities 6, fft 1, meet-in-the-middle 0. At
1500, fft keeps 7. A small topic will often have fewer than five problems
near the target.

## Decision

**A visitor chooses a topic; the page never recommends one.** The topic
list is every topic in the pool, with what the visitor has practised in it,
as the table already shows. Suggesting a topic ("you are weak at trees")
would be the claim ADR 0014 measured at +0.0002 and §3 refuses.

The author's three decisions, each made between measured alternatives:

**1. A small topic is filled to five, and the extra rows say so.** Problems
that pass the guard rail come first. If fewer than five pass, the rest are
filled from the topic's unguarded problems, and each of those rows is marked
as resting on less evidence. ADR 0023's rule still decides the order and is
visible where it gave way. It stands aside for the missing places only, not
for the whole list.

**2. Each topic has its own difficulty target.** "Too hard" pressed on a dp
list moves the dp target and nothing else. A topic nobody has pressed on
starts from the overall target. A new table, `topic_targets`, holds one row
per (handle, topic) once it is moved. The page says which target the list is
aiming at. Hiding a problem stays global: a problem hidden in one list is
hidden in all of them, because "not this one" is about the problem, not the
list it was seen in.

**3. The topic chart is the first React component**, as ADR 0008 planned for
exactly this ("pick a topic in the chart, the table filters"). Choosing a
topic swaps the five without reloading the page. ADR 0011's obligations
arrive with it: a Vite build on the author's machine; the bundle committed
and served from this site; the staleness check that fails when a component
changes and the bundle does not, in the same commit as the first bundle; and
Vitest for the component, the tool that amendment tied to the first
component.

The technical decisions that follow from those:

- **Layer 1 stays** (§7.1). Every topic is a real link, to
  `/results/<handle>?topic=<tag>`, rendered by Jinja, and it works with
  scripting off. The component takes over the same table and fetches the
  five for a topic from `/results/<handle>/recommendations?topic=<tag>`, as
  data. With the bundle missing or failing, the links still work.
- **The five come from the same function either way.** The page and the
  data endpoint both call the recommendation view, so a topic's five cannot
  differ depending on whether JavaScript ran.
- **`recommendations.topic`** records which list a problem was first shown
  in, NULL for the overall five, so §9's calibration can judge the two kinds
  of pick apart (ADR 0024). `guarded` is per row, because a topic list can
  mix both.
- **The address is shareable and safe to reload.** The topic is in the URL,
  so a link to a friend's dp list is that list.

## Alternatives

**Show only what passes the guard rail, and say how many** (recommended in
the discussion). This keeps ADR 0023 whole. The author preferred a list that
is always five long, with the thin rows marked.

**One target for everything** (recommended in the discussion). No new table,
and nothing more to explain. The author wants dp and greedy set
independently.

**Plain links, no React** (recommended in the discussion). No installation,
no build, and nothing new to test in a second language. The author chose to
build the component now. ADR 0008 always intended this chart to be one, and
the links remain underneath it either way.

**Suggesting a topic.** Refused. It is the one thing the data says this model
cannot do.

## Consequences

- **The first npm packages**, installed into the project only, with the
  author's explicit consent for the list: React to run it; Vite to build
  it; Vitest, with a browser-like environment and a testing library, to test
  it. `node_modules/` is not committed; the lockfile and the built bundle
  are.
- **Two renderings of the five**: Jinja's, which every visitor gets first,
  and the component's, after a topic is chosen. They are held together by
  the data both read, and by checks on both sides.
- **In a small topic, some of the five rest on less evidence**, and say so
  row by row. The recommendation record marks them unguarded, so the report
  can show whether they came true as often as the rest.
- **The visitor has more to understand**: the page must say which target a
  list is aiming at, and that a topic's target is separate from the overall
  one.
- **v0.8 is larger.** This comes out of the same weeks as the design pass
  and the disk before launch.

## Built — 2026-09-26, and what building it found

Everything above is built. The component is `frontend/src/` (three
components and a module of addresses). It is built into `static/app/app.js`,
229 KB and 72 KB compressed, almost all of it React. It is loaded only on the
results page, as a module script, after the page is drawn. Measured in a
browser: choosing a topic swaps the five with no reload, the address follows
it, the back button returns to the list it names, focus moves to the new
heading, and "too hard" on a topic's list comes back to that list with only
that topic's target moved.

Three things were wrong until the browser showed them, and each has a check:

- **The easier-version rule looked in the wrong place.** On a topic's list
  the pool is that topic's problems, and 1249C1 "Good Numbers (easy
  version)" is not tagged meet-in-the-middle while 1249C2 is. So on that list
  C1 was not in the pool, and C2 was offered though C1 was unsolved. The rule
  now looks at everything the visitor has not solved.
- **Past the band, the choice ignored the target.** When fewer than five
  problems sit within `model.BAND` of the target, `choose()` used to widen
  the band, up to "everything", and pick from it by topic and contest alone:
  a list aiming at 50% came out 15%, 51%, 29%, 50%, 73%, with nearer
  problems left out. Places the band cannot fill now go to the nearest
  problems. This affects the overall five too, for very strong visitors and
  nearly exhausted pools. It changes no prediction.
- **A list scattered around the target said nothing.** A small topic's five
  can straddle 50% at 30% and 63%, and neither of ADR 0023's walls describes
  that. The page now says so when any pick is more than twice the band from
  the target.

The small-topic fill, as decided: on the measured page the guard rail held
for all five on meet-in-the-middle at 1491, so nothing was filled. On the
checks' fake problemset, fft's two problems show with the one that did not
pass marked.

Checks: 18 in `tests/check_by_topic.py`; 11 component tests (Vitest, run by
`tests/check_components.py`); `tests/check_bundle.py` for the staleness
hash. Twenty mutations, each in a fresh copy of the repository (the Python
code, the component, and one "edited but not rebuilt"), all caught.
