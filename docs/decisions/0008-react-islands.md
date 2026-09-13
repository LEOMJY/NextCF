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
