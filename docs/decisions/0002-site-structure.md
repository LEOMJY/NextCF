# 0002 — Site structure: five pages, handle input in the hero

**Date:** 2026-08-14
**Status:** accepted

## Context

§4's architecture diagram had no landing page at all — it went straight from
"browser" to a handle being entered. But §7.1 had just established that the
landing page is a marketing surface with a different job from the tool, and §9
requires 20 people to return for a second visit.

Those two facts pull in opposite directions. A landing page good enough to
convince a stranger is exactly the thing a returning user wants to skip.

The initial sketch was: one landing page holding the pitch, how it works,
privacy, and per-version release notes, with a link to skip into the tool.

## Decision

**Five URLs**, listed in §4.1: `/`, `/progress/<job>`, `/results/<handle>`,
`/how`, `/privacy`.

**The handle input sits in the hero of `/`**, not behind a "get started" link.
One page serves both audiences: a returning visitor types immediately and never
scrolls, a first-time visitor scrolls past it for the argument. Nothing on the
page is compulsory reading.

**The pitch, how-it-works, and privacy are separate pages, not one scroll.**

**`/how` is a v1.0 requirement, not an appendix.** §3 says measurement is the
only differentiator; the §9 number needs a permanent home on the site rather
than living only in a blog post that scrolls away.

**No changelog page.** Added to §5.

## Alternatives considered

**Pure visual statement in the hero, with a skip link to the tool.** This was
the original sketch. Rejected: it charges every returning visitor a click on
every visit, and §9 is measured on returning visitors specifically. The pitch is
read once; the input is used every time.

**Everything on one long landing page** — pitch, mechanism, privacy, release
notes. Rejected. A page that is both a sales pitch and a privacy policy is
neither. Separate pages also mean the pitch can be short, which is the main
thing that makes a pitch work.

**A changelog page.** Rejected for v1.0. Nobody with 50 users reads release
notes. It reads as professional while being a way to feel productive without
shipping. A footer line is enough if it is wanted at all.

**`/how` deferred to post-v1.0.** Rejected. It is the differentiator; hiding it
would be hiding the only reason to prefer this over sorting the problemset by
rating.

## Consequences

- The hero has to carry a strong visual statement *and* a form field at once.
  That is genuinely harder to compose than either alone, and it is the accepted
  cost of the decision.
- `/how` cannot be written before v0.6, because the number it exists to report
  does not exist until the model is scored. Scheduled there.
- `/privacy` lands at v0.7 with the other production concerns. If the site gets
  real traffic earlier than planned, this moves earlier — it is the one page
  that is not optional once strangers are using it.
- v0.1 now implies two pages rather than one, though both can be crude.
- Both surfaces share one token set, used loudly on `/` and quietly in the tool.
  If they ever drift into two different visual languages, that is the failure
  mode to watch for.
