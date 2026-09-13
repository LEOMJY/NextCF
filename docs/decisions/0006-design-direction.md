# 0006 — Design direction: terminal

**Date:** 2026-09-12
**Status:** accepted as the working direction. Not necessarily final: the
final direction is revisited at v0.8 (spec §12).

## Context

§7.1 promotes design to a v1.0 goal with a stated target: the site must not
read as a student project. It also says which token system to use is a design
decision belonging to whoever is designing, and that the requirement is only
that **a system exists and is not broken** — as CSS custom properties in one
file.

Three complete directions were built as working HTML rather than described in
words. Each rendered both of the surfaces §7.1 distinguishes — the landing page
loud, the results page quiet — using the site's real copy and a real 8,574-row
history rather than placeholder text, because a design decision made against
lorem ipsum is a decision about lorem ipsum.

- **Editorial.** Serif display headline, warm off-white paper, one oxblood
  accent, hairline rules, no radius and no shadow.
- **Terminal.** One monospace family throughout, dark canvas, a single bright
  green accent, dense rows, 3px radius, no shadow.
- **Product.** Geometric display face over a neutral sans, white canvas, indigo
  accent, rounded cards, soft shadows.

## Decision

**Terminal**, as `static/style.css`, with the tokens as custom properties at
the top of that file:

```
type     IBM Plex Mono, five sizes: 13 / 16 / 20 / 25 / clamp(34, 5.2vw, 64)
space    five steps: 8 / 16 / 32 / 64 / 96
colour   canvas #0b0d10, ink #e8ecf1, muted #79838f, accent #7cf03d
radius   3px
shadow   none
```

The landing page uses those values at full volume — the display size appears
there and, once, on the progress count. The tool pages use the same values
quietly.

## Alternatives

**Editorial.** The cheapest of the three to execute well: no radius and no
shadow to get wrong, so it stands on type and space alone. It also suits a
project whose pitch is publishing a number nobody else has published.
Rejected because a serif headline reads as a publication, and the thing being
built is a tool people open in a hurry.

**Product.** The most conventionally professional, and the fastest to make look
finished. Rejected for the reason §7 already gives against a CSS framework: a
recognisable look is a cost as well as a floor. This is the look people
recognise, so it carries the highest risk of reading as templated — which is
the exact failure §7.1 exists to avoid.

## Consequences

- **Monospace for body text is unusual**, and slightly slower to read per word
  than a proportional face. Accepted deliberately: the audience reads code all
  day, and the main surface is a data table, which is what mono is good at.
- **The accent means one thing.** The moment a second saturated colour appears,
  the green stops reading as "this is good, or this is where you act". The only
  other colour in the system is `--warn`, and it appears on the error page.
- **Dark canvas only.** A light mode is a second design to maintain, and
  nobody has asked for one.
- **The typeface comes from a font CDN**, so a visitor who cannot reach it gets
  the fallback mono stack. The design survives that: it is the one place the
  system degrades instead of breaking. Self-hosting the two weights is the fix
  if it ever matters, and it may — a real share of Codeforces users are in
  places where that CDN is blocked.
  *Amended 2026-09-13: self-hosted.* The degradation above was milder than the
  real risk. The stylesheet link to Google Fonts blocks rendering, and
  GreatFire's tests from inside mainland China show that address interfered
  with intermittently, so the page itself could stall, not only the font.
  Both weights of IBM's "Latin1" subset (17,544 and 17,872 bytes, checked
  against IBM's repository) now live in `static/fonts/` with the SIL Open Font
  License beside them, and no page loads anything from another server. 51 of
  11,401 Codeforces problem names have a character outside that subset, mostly
  Russian titles, which the fallback mono drew in a visibly different face; the
  same day IBM's Cyrillic, Latin2 and Pi subsets were added, each downloaded
  only by a page that uses one of its characters. Only θ and ⟩ are in no Plex
  Mono file.
- **Every page now depends on one file.** Changing a token changes the whole
  site, which is the point, and also means a careless change is site-wide.
- §7.1's design budget, which it says comes out of §9, is still an unset
  number. This decision spent roughly half a session.
