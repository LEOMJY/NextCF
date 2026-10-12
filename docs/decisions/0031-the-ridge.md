# 0031 — Design direction: the ridge

**Date:** 2026-10-11
**Status:** accepted, and **being built**. The card table (ADR 0029) is what
the live site shows until these templates replace it, and is superseded on
that day. The brief set one week from the choice to the landing page live:
**2026-10-18**. **Amended the same evening** (below): the arrangement of
the first screen and of the three steps, and the tool pages' pale ground,
which is withdrawn.

## Context

ADR 0029's card table was the current direction, never the settled one. On
2026-09-30 five mock-ups of the results page in it were drawn and the author
liked none. On 2026-10-04 the author decided the theme is replaced before
the public release, and named a reference: the sites in GSAP's showcase.

`docs/design-brief.md` was written before anything was drawn: 27
characteristics that can be checked, summed up as *showcase craft, tool
clarity*. The author answered its four questions the same day. The ground
is not pure black, "be more creative". GSAP is used, for lines that arrive
and scenes tied to scrolling. The first screen's living object is real 3D.
The cards probably go.

Two directions were then built as working pages (devlog, 2026-10-04): each
a landing first screen with its 3D object and one control that works, and
the first screen of the results page, at 1440 and 375 pixels.

- **A, the ridge.** A yellow ground and ink type. The lower half of the
  first screen is a field: every rated problem as a dot. A ridge rises
  where rating alone puts a 50% chance.
- **B, the stair.** An ultramarine ground and bone type. One white flight
  of 28 steps, a hundred points of rating each, edged in the rank colours.

Both were checked against the brief's §5 and spec §7.1's fourteen rules
before the author saw them, and shown with the list of rules each bends.

On 2026-10-11 the author preferred A, named two faults in it, and chose it.

## Decision

**The ridge**, as `static/style.css` and the templates.

**The landing page:**

1. **The first screen.** The headline "Five problems to solve next", in two
   lines. One sentence. The handle field and a button reading "Find my
   five". The five problems of a real sample history (`web.SAMPLE_PACK`) as
   a list: id, name, rating and chance. Under all of it, the field.
2. **The field** is the living object, and it is the product: every rated
   problem that can be recommended, one dot each (10,781 on 2026-10-04).
   Across is its rating, spread inside the hundred it is rounded to. Back
   is its contest, newest in front. A ridge rises where the rating-only
   curve (`baseline.json`) puts the chance within `model.BAND` of 50%. The
   five stand on their own dots as poles with flags.
3. **The control is the axis.** The field's front edge is the rating axis,
   banded in the rank colours, and the visitor's own rating is a pole and a
   flag on it, drawn like the five's. Moving it re-picks the five in the
   browser, by `model.recommend()`'s rule: nearest the target, newest
   contest first. Rating alone gives everybody at one rating the same five,
   all at one rating; the sample, from the full model, runs from 800 to
   1700. So moving the rating closes five scattered flags up onto one
   pole, and the caption says "Rating alone at N: everybody gets these
   five." That is spec §3's argument, held in the hand.
4. **Motion, on this page only.** The headline's lines rise from behind a
   mask and the chances count to their values, once per visit. The field
   arrives front to back, the ridge rises out of it, the five stand up. As
   the first screen is scrolled away the field stands up with it, and lies
   back down when it is scrolled back. Somebody whose system asks for
   reduced motion gets none of this.
5. **After the first screen:** how the five are made, in three statements,
   and the proof: the two measurements, linked to `/how`.

**The tool pages** are the same world with the two colours' jobs swapped.
On the landing page yellow is the ground and "act here" is ink. On the
results and progress pages the ground is a pale tint of the same yellow,
and yellow is the accent: the top bar, the main button, and a highlighter's
stroke under each chance that still asks for a press. The author chose this
over a yellow ground everywhere, with both built side by side: a page used
daily, often at night, should not be the loud one, and rank colours and the
green of "accepted" are weakest on full yellow (orange 1.5 to 1, cyan 1.9,
green 3.3).

**The tokens:**

```
type     Sofia Sans Extra Condensed 800 (display: headline, numerals,
         buttons, the name). Sentence case; no capitals anywhere.
         Sofia Sans 400 / 600 (reading) · IBM Plex Mono 400 / 600 (data)
space    five steps, kept: 8 / 16 / 32 / 64 / 96
colour   yellow #f5cd1e · ink #15130c · pale #fbf5d6
         secondary text: #4a4108 on yellow, #57501f on pale
         landing   ground yellow, "act here" = ink
         tool      ground pale,   "act here" = yellow
         seven rank colours, Codeforces' own values: always a mark with
         an ink edge, never the colour of text
         green = accepted and warn = wrong: set with the stylesheet, each
         at 4.5 to 1 or more on pale
radius   none
shadow   none
motion   one curve; the landing page only
```

**The headline is sentence case.** The first version set it in heavy
capitals and the author found it hard to read. Capitals are all one height,
so a word loses its outline, and at 180 pixels in a narrow face the letters
closed into a wall. Three treatments were built behind a switch and the
author chose sentence case in the same face, one weight lighter.

**What is served, all of it from this site** (spec §7.1):

```
static/vendor/   gsap.min.js            72 KB   28 KB compressed
                 ScrollTrigger.min.js   44 KB   18 KB
                 SplitText.min.js        7 KB    3 KB
                 three.module.min.js   671 KB  167 KB   layer 3 only
static/fonts/    Sofia Sans Extra Condensed 800, Latin      15.8 KB
                 Sofia Sans 400 and 600, Latin              14.9, 16.1 KB
                 Sofia Sans 400 and 600, Cyrillic            9.5, 10.0 KB
```

`static/vendor/SOURCES.txt` records each library file's address and
fingerprint; the bytes were compared with what cdnjs publishes for them.
The fonts are single weights rather than variable files, which is why they
are small: the two display weights first asked for came to 40 KB as one
variable file, and one weight is 16. The display face is Latin only, as
Unbounded was: it never draws a problem's title. What every visitor
downloads is about 82 KB of fonts and 50 KB of GSAP, 132 KB, inside the
brief's 150.

**"I solved it" is still not a button.** Looking at the results page, the
author asked where to press "solved" and "couldn't solve". ADR 0026 stands:
solved is read from the synced history, never stored. But the question
found a real gap. A history counts as fresh for ten minutes
(`FRESH_FOR_SECONDS`), so somebody who solves a problem in eight and comes
back sees no tick, and the button that would fix it was at the foot of the
page, named for what the system does: "Update from Codeforces". It moves to
directly under the five and is named for what the visitor wants: "Check
what I solved". "Couldn't solve" already exists as "too hard".

## Amendment, the same evening: one path, steps, and no pale page

The author looked at the pages again and named three faults. Each was a
fault of arrangement, and they had one cause: things had been set in
columns rather than next to what they belong to.

**The first screen had three islands.** The sentence, the handle field and
the five sat in a narrow column at the far right, a screen's width from the
headline they explain: "isolated, put on the edge". The handle field is the
page's one job and was its smallest part. Now there is one reading path
down one left edge: the headline; directly under it the field, at 64
pixels tall the largest thing after the headline, with the sentence beside
it; then the five across the whole page as five columns, the chance the
largest thing in each; then the field of dots. Each column's rule runs on
down as a line to that problem's own dot, so the list is the field's
labels and not a second copy of them. When the rating is moved, the five
lines swing to meet at one dot. On a narrow screen the five are a list
under the field and each dot carries a small flag, as before.

**The three steps did not read as steps.** Three titles ran down the left
and their sentences sat far to the right, with nothing to say they are a
sequence. Now each step has its number, its title and its sentence
together, in three columns in the order they happen, on one rule that the
scroll itself draws from left to right. Each shows what it works on in its
own material: a row of verdicts, the count of first attempts, the line
from 30% to 65% with the aim on it.

**The pale results page is withdrawn.** Chosen at midday, seen whole in the
evening: "I don't like it." Asked which of four things, the author picked
two: nothing leads and it is too empty; and the pale ground itself. Asked
what a results page should be like, the answer was the showcase again:
different from other sites of its kind, something that catches, and clear.
So the results page is the landing page's world at full strength. The
handle is as large as the landing headline. Each of the five is one line
across the page: its chance and its name both in the display face, id and
rating small under the name, and "too hard / too easy / skip" as one
joined control at the end. A whole line turns ink when pointed at, and is
the link to its problem. Under the five is the landing page's rating line,
drawn without script, with the visitor and their five standing on it. The
five arrive once per visit: lines rise, chances count up, poles stand.

This overrides the tokens above: **one ground, yellow, on every page, and
"act here" is ink.** It also relaxes spec §7.1's rule 12 (calm) for the
results page, by the author's choice. Rules 13 and 14 hold and were
measured: on a 375 by 812 phone the first problem starts at 159 pixels and
all five begin on the first screen.

What this gives back: the two doubts about full yellow on a page used
daily still stand, and were said. Rank colours and green are weakest on
it, and it is not calm. The author has heard both and chose the page that
catches.

Problem names are now set in the display face, which is served in Latin
only. A Russian title would fall back to another face, so the display
face's Cyrillic file (9.8 KB, same source) is needed before release.

## Alternatives

**B, the stair.** A rank colour always sat on bone there, so none was ever
hard to tell, and the step a rating stands on is a strong picture. On a
phone the flight was small and the numbers on its risers unreadable. The
author preferred A.

**Capitals for the headline**, as first drawn, or the same capitals made
lighter and opened up, or sentence case in the family's wider cut. All
three were built. The author chose sentence case in the condensed face.

**Yellow as the ground of every page.** One ground for the whole site is
the most recognisable. Built, compared, and not chosen, for the reasons
above.

**A button the visitor presses to say "solved".** It answers at once, and
it can disagree with the history, which is the truth and is one request
away. It would also need a stored state ADR 0026 deliberately does not
have, and it would teach the model nothing: the model learns from
submissions.

**JetBrains Mono** for data, as the prototype used. ADR 0029 turned it
down for a reason that still holds: IBM Plex Mono is already served, in
four alphabets, and at 13 pixels nobody would see the difference.

**Drawing the field without a 3D library.** The field is points and lines,
and could be written directly against the browser's WebGL with no library
at all, saving 167 KB for every device that gets layer 3. Not taken now:
the prototype works on three.js and the week is short. The brief already
accepts the cost, since the library is fetched only by a device that will
run it and only after the page is on screen. Worth reopening if layer 3
measures slow to arrive on a phone.

## Consequences

- **It is a change of layout, not only of tokens**, which spec §7.1 names as
  the expensive kind: every template, the stylesheet, and each check that
  looks for the card table's elements. Unbounded and Onest leave
  `static/fonts/` with the card table.
- **Spec §7.1's checklist keeps its rules and loses its examples.** Rule 4's
  "gold is act here" becomes the accent above. Rule 8's card games and rule
  9's pack opening described the card table; the ridge's memorable moment
  is the five closing up when the rating is moved.
- **Rules bent, knowingly.** The brief's rule 6 asks for type eight times
  the body size: 11 times at 1440 pixels, 4.5 at 375, where five words in
  two lines cannot be larger. The chance numerals are a third size, where
  the rule wants two. A row of the five has four text styles, where spec
  rule 3 allows three. On a 375 by 812 phone the fifth row of the list ends
  8 pixels below the first screen; the flags in the field carry every id
  and chance above it.
- **Not done yet, and owed before release:** the five-second test on two
  or three Codeforces users, which the brief put before the choice and the
  author made the choice first; layer 2, the still image a device gets when
  it cannot run the field; the check of frame rate that steps down; the
  progress page and the error states in the new theme.
- **After the theme is live:** the results page asks Codeforces by itself
  when the visitor comes back to its tab, so most people never press the
  button. That changes when a sync starts, so it amends ADR 0018 and gets
  its own checks; it is not part of this week.
