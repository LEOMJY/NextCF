# 0001 — Design promoted to an explicit v1.0 goal

**Date:** 2026-08-14
**Status:** accepted

## Context

§7 already said "looking credible matters — the launch screenshot is the pitch",
but design was scheduled as a single pass at v0.8 , on the assumption that
"design is not what this project demonstrates."

That is now judged too weak. The stated requirement is that the site must not
read as a high-school project. The incumbent, CF Recommender, is polished, and a
recommendation tool asks a stranger to trust a number — a site that looks
unfinished undermines the number before anyone reads it.

The initial instinct was that this needs "interactive things."

## Decision

Design is a v1.0 goal with a written budget, but the interactivity instinct is
rejected. See spec §7.1.

1. **Design tokens at v0.1, not v0.8.** Type scale, spacing scale, one neutral
   ramp plus one accent, one typeface — as CSS custom properties, with nothing
   permitted outside the scale. Retrofitting spacing and type across templates
   later is expensive; polish applied late is cheap.
2. **Own CSS, no framework.** Pico.css was the previous choice.
3. **Server-rendered SVG for the topic-breakdown chart.** No chart library.
4. **Three interactive elements only**, each justified by the product rather
   than by decoration: the topic-breakdown visualisation, the progress page, and
   the solve probability on each recommendation.
5. **Roughly 15 hours total**, taken from §9.

## Alternatives considered

**Keep Pico.css and layer on top.** Rejected. A classless framework gives a
floor with no effort, but also a recognisable look, and "does not read as
templated" is now the explicit goal. Layering custom design tokens over a
framework also produces specificity fights. Three pages is about 200 lines of
CSS; the framework saves less than it costs here.

**A chart library (Chart.js via CDN).** Rejected. It would work with no build
step, but it adds a runtime dependency and a canvas element for what is a bar
chart of at most ~30 topics. Jinja already has the data; emitting SVG from it
needs nothing new, degrades gracefully, and appears in a screenshot.

**Scroll animation, parallax, page transitions, animated counters.** Rejected
as actively counterproductive. Over-animation is a stronger amateur signal than
plainness. The polished reference points in this space are less interactive than
amateur sites, not more. Reconsidered at v1.5 where motion is the feature.

**React, re-examined.** Still rejected. SVG rendered from Jinja and a polling
progress page need no client framework.

**Leaving design at v0.8 as before.** Rejected as the thing that produced this
discussion.

## Consequences

- Roughly 15 hours comes out of the evaluation work in §9. This is a deliberate
  trade, and the tiebreak is written down: **if the budget overruns, design
  stops, not §9.**
- Nothing may use a spacing or type value outside the tokens. This is a real
  constraint on every template written from v0.1 onward, and it is the part most
  likely to be violated quietly.
- The topic-breakdown chart moves from "nice to have" to a v0.4 deliverable.
- Unhandled states — mistyped handle, empty history, API failure, job failure —
  become design surface rather than tracebacks. This is the single loudest
  amateur tell and is now explicitly v0.8 scope.
- The risk this introduces: design has no natural stopping point and is more
  enjoyable than debugging a likelihood function. §11 already flags exactly this
  failure mode for the pet system. The budget exists because the same trap
  applies here.
