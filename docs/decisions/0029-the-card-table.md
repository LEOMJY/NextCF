# 0029 — Design direction: the card table

**Date:** 2026-09-29
**Status:** accepted as the **current** direction: built, live, and the
site's design system in place of ADR 0006 (terminal). **Not settled as the
final one.** On 2026-09-30 the author said the theme is not decided yet, so
spec §12's question stays open. The next test of it is the results page
drawn in it (see Consequences).

## Context

ADR 0006 chose "terminal" on 2026-09-12 as a working direction, and spec §12
left the final one to v0.8. By then two rounds of landing directions had been
built (2026-09-13), and a third on 2026-09-28: five directions drawn side by
side at desktop and phone width.

- **A · The ladder.** Rank colours, Swiss print, light.
- **B · Balloons.** The plan as five ICPC balloons, soft, light.
- **C · Rank balloons.** Both ideas together, dark.
- **D · Your own contest.** The plan as a one-row scoreboard, light.
- **E · The forecast.** A weather forecast graded on calibration, a
  deep blue page.

The author's verdict on all five: not creative, and a site nobody would be
drawn to at first look. The question was then asked the other way round:
what does a site this audience would stop for look like? The answer tried
was one the audience already plays with. Codeforces rank colours are a
rarity scale, like the colours on game cards, and a plan is five problems
dealt at once, like a pack. So:

- a problem is a **card**, framed in the rank colour of its rating;
- a plan is a **pack** of five, and looking a handle up is opening one;
- the landing page is a **card table**.

A working prototype was built with the real site's copy and a real plan. The author: "my favourite version". Black as the table
was "too dim, too serious, too computer-science". Six table colours were then
tried on the same page: navy, felt green, grape, tomato, sunny yellow and sky
blue, each with its text colours checked at 4.5 to 1 or more. The author
kept navy.

## Decision

**The card table**, as `static/style.css` and `templates/index.html`.

**The landing page** is the card table:

1. **The hero** is the headline "Open your next five.", one sentence, the
   handle field and a button reading "Open pack". Beside it, or under it on
   a phone, is a **sample pack**: five cards fanned in a hand. They are the
   first plan a real history rated 1491 was dealt on this site, on
   2026-09-27, with the chances the model gave then (`web.SAMPLE_PACK`). The
   handle is not shown: it is a person's, and the page is not about them.
   The caption says "Sample pack". The cards are drawn by the server, so the
   fan is there without JavaScript.
2. **Motion, on this page only.** The hand is dealt from a stack when the page
   opens. A card leans toward a mouse and its foil catches the light (not on
   a touch screen). Sending the form packs the five away: the hand closes,
   turns face down, goes into a pack with the typed handle on it, and the
   pack tears. That takes about 1.5 seconds, and then the form is sent as
   before. No card comes out of the pack here: the visitor's own five are on
   the page it leads to, and the sample is never presented as theirs.
   "Continue as" is a plain link and opens no pack. Somebody whose system
   asks for reduced motion gets none of this.
3. **Three sections after the hero**, each answering one question about the
   pack. *How a pack is made*: three steps, with the model's real training
   numbers and the sample's own aim and five chances on the line from the
   hardest target to the easiest. *A forecast you can check*: the calibration
   from `web.EVALUATION`, drawn as ten dots. *Rarity is just rating*: the
   seven bands. Every number is computed from the constants the rest of the
   site uses (`web.landing`).

**The tokens:**

```
type     Unbounded (display) · Onest (reading) · IBM Plex Mono (data)
         six sizes: 13 / 16 / 18 / 25 / clamp(28, 3.6vw, 44) / clamp(44, 6.2vw, 80)
space    five steps: 8 / 16 / 32 / 64 / 96
colour   table #172543, panels #1e2e52 and #2a3d68
         ink #f2f0ea, soft #d6dbe6, muted #aeb6c8
         gold #ffc83d    = act here, and the forecast
         green #7fdb88   = accepted
         warn #ffb4a6    = something went wrong
         cards #f8f4ea with ink #171b26
         seven rank colours: a frame colour, and a darker one for text on a card
radius   4 / 10 / 16
shadow   one: a card lifted off the table
motion   one curve, on the landing page only
```

Inside a card, sizes are fractions of the card's width, so the whole hand
shrinks as one picture on a phone. That is the one place the scale is not
used, and the stylesheet says so.

**The other pages** keep their layout and take the new tokens. The results
page drawn as flat cards is a later step, not part of this decision.

**The fonts are self-hosted**, as ADR 0006's amendment settled. Both new
families are variable fonts (one file holds every weight). Unbounded is Latin
only (50.9 KB), because it draws headings, buttons and numbers, never a
problem's title. Onest is Latin (33.8 KB) plus Cyrillic (15.9 KB), because it
draws titles. Each family's SIL Open Font License sits beside its files. The
two Latin files are preloaded by every page. The mono stays IBM Plex Mono,
already served, rather than downloading a new one.

## Alternatives

**A to E** (above). Each carried one idea from Codeforces, and none of them
made the site something to look at. The card table keeps the one the author
preferred from the start, the rank colours, and gives them a job: a rarity.

**Keeping terminal.** It was legible, and it looked like a developer tool. It
is the look the author called boring.

**Other table colours.** Felt green is the most literal card table. Grape,
tomato, sunny yellow and sky blue are louder, and the two light ones would
have needed a darker set of rank colours throughout. Navy was the author's
choice.

**JetBrains Mono** for data, as the prototype used. Plex Mono was already on
the server in four alphabets; a second mono would be about 60 KB for a
difference nobody would see at 13 pixels.

**The pack on "Continue as" as well.** A returning visitor would pay 1.5
seconds on every visit for an animation they had seen. It stays on the form,
where it plays once per lookup.

**Cards coming out of the pack on the landing page.** The prototype did this
with the sample cards. On the real site it would present the sample as the
visitor's own five, which is false.

## Consequences

- **The one accent is two colours.** ADR 0006's green meant both "good" and
  "act here". The rank colours make colour mean a rating band, and pupil is
  green, so the review of 2026-09-28 found the two could not share one
  green. Now gold means acting and the forecast, and a lighter green means
  accepted, as Codeforces uses it. Pupil's frame is still a green of its
  own; the two never share a surface, since frames are on cards and
  accepted verdicts are text on the tool pages. `check_model` holds each
  colour to its list of selectors.
- **Every lookup from the form takes about 1.5 seconds longer.** The form
  is sent when the pack tears, or after 2 seconds whatever happens: a
  browser pauses animations in a tab nobody is looking at, and found
  2026-09-29, the form would otherwise have waited. A second press is
  swallowed. Coming back with the Back button stops the timer, which would
  otherwise send the form a second time.
- **About 100 KB more on a first visit**, the two Latin files, preloaded.
  Cyrillic is downloaded only by a page with a Russian title on it.
- **The sample is fixed.** Its chances are what the model said on
  2026-09-27, and a monthly refit does not move them. The page says it is a
  sample from a real history, which stays true.
- **Readable by rule, not by eye.** Every text token is at least 4.5 to 1
  on every surface it is drawn on (the table, both panels, a card), checked
  by `tests/check_landing.py` rather than by looking. Muted on the table is
  7.5 to 1. The palest rank text, pupil's, is 4.71 to 1 on a card.
- **Measured at 375 × 812:** the field's top is at 335 pixels and the
  button's bottom at 458, or 602 with "Continue as" above them. The whole
  hand is on the first screen, ending at 781. **At 1280 × 800:** field and
  hand side by side, both above 480.
- The version label in the header still says v0.7. That is a separate item.
