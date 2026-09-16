# 0008 — React for the interactive parts, not the whole front end

**Date:** 2026-09-13
**Status:** accepted. Built at v0.4, before the topic-breakdown chart.

## Context

§7 rejected React at the start, on the grounds that the pages were a form, a
progress bar and a list. §12 reopened it on 2026-09-12, with three options and a
deadline of v0.4:

- **(a)** Jinja templates, the token stylesheet, and small plain JavaScript
  where something moves. No build step.
- **(b)** React components for the interactive parts, mounted into pages Flask
  still renders. Routes and templates stay; Node and a build step arrive.
- **(c)** React for the whole front end, Flask returning JSON only.

Two things changed since §7 was written. The results page is now expected to
carry pieces that change each other: tables of problems, the topic chart, a way
to move the target probability, and later the pet system in §11. And the
landing page may get a real-time 3D experiment (§12, balloons).

What React changes is how state in the browser is organised. It does not make a
page look better, and it does not replace the stylesheet.

## Decision

**(b).** React components, mounted into server-rendered pages, for the parts
that are interactive. Everything else stays as it is.

The line between the two is state shared in the browser. A table that is only
shown stays Jinja. One table with a sort button could be either. Several pieces
where one changes another — pick a topic in the chart, the table filters, the
probability control re-ranks both — are React.

**Real-time 3D, if any ships, is React Three Fiber** inside the same build.

## Alternatives

**(a), plain JavaScript.** Enough for everything built so far, and for a
single sortable table. It starts to tangle at the first set of linked pieces,
where every change has to be pushed by hand into every place that shows it, and
forgetting one is a bug that only appears in one combination of clicks. It was
also noted that moving from (a) to (b) later adds a build and a mount point
without rewriting templates or routes, so choosing (b) now buys the setup early
rather than avoiding a rewrite. The author accepted that: the planned
interactivity makes (b) likely anyway, and setting it up once, before the first
component, beats switching in the middle of building one.

**(c), React everywhere.** Every template and the web-flow checks rewritten,
for five pages that are mostly read. And a page rendered only in the browser
shows nothing when JavaScript fails, which breaks layer 1 of §7.1 unless
server-side rendering is added — a second system to run.

**three.js without React, for 3D.** The same renderer, so the same look: React
Three Fiber draws with three.js. Chosen against because inside (b) there is
already a React build to share, and its helper library has ready-made pieces
for exactly what §7.1's layer rule asks for — measuring the frame rate and
lowering the resolution when a device struggles. Plain three.js would have been
the choice under (a).

## Consequences

- **Node and npm on the development machine, and a build step.** Whether the
  host builds on deploy or the built file is committed is open in §12, due at
  v0.4.
- **Two languages to test.** The Python checks cannot see inside a React
  component; a JavaScript test tool is needed by v0.7 at the latest.
- **Layer 1 still holds.** Every component sits on HTML Flask has already
  rendered — a table is drawn by Jinja first and the component takes it over.
  If the bundle fails to load, the page still works, just without the
  interaction.
- **The bundle is served from this site**, like the fonts, for the same reason
  (§7.1).
- **React brings no styling system.** The tokens in `static/style.css` stay the
  only one. A component library or a utility-class framework such as Tailwind
  would be a separate decision, and would collide with the token file.
- **Pages without interactive parts load no React.** The landing form and the
  progress page stay as they are unless they need it.
- **Time.** Setting up the build and learning React come out of the same hours
  as §9, which is the trade §7.1 already names for design work.
- **Balloons are not decided by this.** It fixes how a real-time prototype
  would be written, not whether one ships (v0.8).

## Amendment — 2026-09-15: the Tailwind consequence was argued wrongly

The consequence above reads "a component library or a utility-class framework
such as Tailwind would be a separate decision, and would collide with the token
file." That sentence puts two different things in one bucket and gives a reason
that is only true of one of them.

**A component library** — shadcn/ui, Material — ships buttons, cards and
dialogs that already look like something. ADR 0001's argument against Pico.css
applies to it exactly: a recognisable look is a cost as well as a floor, and
§7.1's stated goal is that the site must not read as templated.

**Tailwind ships no appearance at all.** It is a set of small class names for
individual properties. ADR 0001's argument does not apply to it, and "would
collide with the token file" is too strong: Tailwind reads CSS custom properties
as its own configuration, so a single source of truth in `static/style.css` is
achievable rather than impossible.

**The decision does not change**, for two reasons that were not the ones given:

- **React is a small minority of this site's markup.** Five pages, one component
  at v0.4. The Jinja templates keep hand-written CSS either way, so adopting
  Tailwind would add a second way of writing styles rather than replacing the
  first. Two idioms in one codebase is worse than either idiom alone. Tailwind's
  real advantage — never naming a class again — arrives when components carry
  most of the markup, which is not this project.
- **§7.1's budget.** Learning a second styling system comes out of §9, and buys
  nothing there.

**When to reopen it:** if React comes to carry the majority of the markup. The
plausible cause is the pet system at v1.5 (§11), which would make the results
page mostly components. At that point the ratio flips and the trade is worth
recomputing. Recorded in §12 so it is a trigger rather than a thing that quietly
never happens.

**The build question this ADR left open is now answered** — see
`docs/decisions/0011-bundle-built-locally.md`.
