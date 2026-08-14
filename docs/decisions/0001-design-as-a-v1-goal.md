# 0001 — Design promoted to an explicit v1.0 goal

**Date:** 2026-08-14
**Status:** accepted, amended same day — see "Amendment" at the end

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

1. **Design tokens at v0.2**, as CSS custom properties in one file. The
   requirement is that a system exists and does not get broken; which system is
   a design decision belonging to the author.
2. **Own CSS, no framework.** Pico.css was the previous choice.
3. **Server-rendered SVG for the topic-breakdown chart.** No chart library.
4. **The landing page and the tool are judged differently.** The landing page is
   a marketing surface and expressive work belongs there. The progress and
   results pages are read under time pressure and stay calm.
5. **A fixed number of hours, taken from §9.** The mechanism is settled; the
   number is not yet set.

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

**Scroll animation, parallax, page transitions, animated counters — on the
progress and results pages.** Rejected, but not because motion is amateur. Those
pages are read under time pressure by someone who wants to leave for Codeforces;
motion there costs attention and returns nothing. On the landing page the same
techniques are in scope, limited by the hour budget rather than by a rule.

**React, re-examined.** Still rejected. SVG rendered from Jinja and a polling
progress page need no client framework.

**Leaving design at v0.8 as before.** Rejected as the thing that produced this
discussion.

## Consequences

- Roughly 15 hours comes out of the evaluation work in §9. This is a deliberate
  trade, and the tiebreak is written down: **if the budget overruns, design
  stops, not §9.**
- Nothing may use a spacing or type value outside the tokens. This is a real
  constraint on every template written from v0.2 onward, and it is the part most
  likely to be violated quietly.
- The topic-breakdown chart moves from "nice to have" to a v0.4 deliverable.
- Unhandled states — mistyped handle, empty history, API failure, job failure —
  become design surface rather than tracebacks. This is the single loudest
  amateur tell and is now explicitly v0.8 scope.
- The risk this introduces: design has no natural stopping point and is more
  enjoyable than debugging a likelihood function. §11 already flags exactly this
  failure mode for the pet system. The budget exists because the same trap
  applies here.

## Amendment — 2026-08-14, same day

The first version of this ADR over-specified in three places. Corrected:

**"Over-animation is a stronger amateur signal than plainness" — withdrawn.**
Stated as a general rule it is simply wrong. The GSAP showcase is full of
heavily animated sites that are excellent professional work. *Badly executed*
animation reads as amateur; animation does not. What replaced it is the
landing-page/tool distinction, which is the thing that actually applies to this
project.

**Exact token values — withdrawn.** The original specified a 4/8/16/24/48/96
spacing step and "exactly one accent colour". Those are one reasonable system
presented as if it were the only one, and the second is contradicted by good
sites that commit hard to two or three colours. The requirement is that a system
exists and holds; choosing it is the author's call.

**Tokens at v0.1 — moved to v0.2.** The stated reason for v0.1 was that
retrofitting spacing across templates is expensive. For three pages it is not.
v0.1 should answer one question only: does this thing run at all.

**The 15-hour figure — withdrawn.** It was invented, not estimated. Taking the
budget from §9 was affirmed by the author and stands; the number gets worked out
against the milestones before design starts.

The general lesson, worth more than any of the four: a mentor stating personal
defaults in the imperative is indistinguishable from a real constraint, and gets
written into the spec as one. Design decisions belong to the author. Engineering
consequences — that a system must not be broken once chosen, that budgets need a
source — are the part that is actually being advised on.
