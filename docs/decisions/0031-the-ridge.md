# 0031 — Design direction: the ridge

**Date:** 2026-10-11
**Status:** accepted, and **being built**. The card table (ADR 0029) is what
the live site shows until these templates replace it, and is superseded on
that day. The brief set one week from the choice to the landing page live:
**2026-10-18**. **Amended the same evening** (below): the tool pages'
ground, the three steps and the results page's arrangement are open again,
and are being settled one change at a time.

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

## Amendment, the same evening: what is open again

The author looked at the pages again and named three faults: the sentence,
the handle field and the five sat in a narrow column at the far right,
"isolated, put on the edge"; the three steps did not read as steps; and the
results page, with nothing leading, too empty, and on a pale ground that
was itself wrong.

A redraw that answered all three at once was built the same night: the
five as five large columns joined to their dots by lines, numbered steps,
and a results page of five very large lines on full yellow. The author
rejected it outright, "even worse", and said why when asked: too full and
too loud, too many lines and boxes, like a table, and the display face ugly
once it was used everywhere.

**Decided:** go back to the version before that redraw and change one
thing at a time, each change shown and judged before the next.

**The first change was refused too.** The sentence, the handle field and
the five were moved from the far-right column to directly under the
headline, same blocks and same sizes. The author's answer: no, change
everything back. So the prototype is again exactly the version of the
screenshots, right-hand column and all, and nothing is changed in it until
the author says what to change.

**2026-10-12: the right-hand block is where the author put it.** After
several rounds of "a bit left", "down", "too far down", the prototype was
given an editor for dragging and scaling its blocks, and the author placed
the sentence, the handle field and the five by hand: a little higher and
closer together, no change of size. The layout rules now produce that
placement at any window size (devlog, 2026-10-12, later).

**Open again, so not to be built from the Decision above:**

- the ground of the tool pages. The pale one is withdrawn; the full yellow
  one was part of the rejected redraw, and on 2026-10-12 the author said
  plainly that the results page is not to be yellow. What replaces it is
  not chosen: white, light grey and dark are side by side on the
  prototype. The tokens' "tool" line is unsettled;
- how the three steps are shown as steps;
- what the results page leads with;
- where the display face is used besides the headline. Heavy and narrow,
  it reads as ugly when everything is set in it.

The first version of this amendment recorded the redraw as decided before
the author had seen it. That was the mistake to note: a redraw is an
attempt, and belongs in the devlog until it has a verdict.

## Amendment, 2026-10-12: the landing page as built

The landing page is written as real code: `templates/index.html`,
`static/ridge.js`, a section of `static/style.css`, and
`static/field.json`. Live since the evening of 2026-10-12. Building it
settled six things the Decision above left open or had wrong.

1. **The ridge is a second set of values, not a second stylesheet.** The
   tokens keep their names. The ridge's values for them are one `.ridge`
   block, and a page asks for it with `class="ridge"` on `<html>`. Only the
   landing page does. The tool pages keep the card table's values until
   their ground is decided, and then the block moves into `:root`. The
   alternative, a stylesheet of its own for the landing page, would have
   been two files to keep in step and a second set of names for the same
   things.
2. **The dots are a file made on the author's machine.**
   `collect.py field` writes `static/field.json` from the problemset in the
   dataset, and `collect.py refresh` does it every month by itself. The
   server cannot make it: its own database is empty after every restart
   (ADR 0017), which is exactly when a first visitor is looking at this
   page. The file holds what `db.recommendation_pool()` chooses from before
   a person is subtracted, so the field is the recommender's pool and its
   count is the number the page states.
3. **Layer 2 is drawn, not a picture.** Spec §7.1 says "a still image".
   Somebody who asks for less motion, has no WebGL or is saving data gets
   the same field drawn once on a 2D canvas, by the same camera arithmetic,
   with no library fetched. An image file would show last month's
   problemset and would not line up with the axis at every width. The two
   layers put the five's flags within half a pixel of each other.
4. **The frame rate is measured.** Over the first second of drawing: under
   28 frames a second (30, with room for a screen held to exactly 30), the
   field draws at one device pixel per pixel and fewer than half the dots,
   and is measured again; still under, it becomes the still.
5. **Nothing here touches the form.** The card table delayed the form a
   second and a half to play its pack. The ridge's script never reaches for
   it. The only thing held back before the page is drawn is the headline,
   for the moment before its lines rise, and for three seconds at most.
6. **The list lies in front of the field.** Found by looking at window
   sizes nobody had looked at: at 1366 by 768 the last of the five sat on
   the field's far edge, and a rating moved to the top of the slider stood
   five flags on a pole under the list and drew them across the problem
   names. The prototype had both. Now the ground takes only the room under
   the list, poles that stand under it end below it, and the list has the
   ground's colour behind it for the windows too short for either. In the
   author's window none of the three changes anything that can be seen.
   **Still wrong:** in a short window (1366 by 768, for one), a rating at
   the top of the slider puts most of the five flags behind the list. The other answer is a
   first screen taller than the window on short screens, which puts the
   axis below the fold; that is the author's to choose.

What every visitor to the landing page downloads, compressed: 50 KB of
GSAP, 14 of `ridge.js`, 10 of `field.json`, and 66 of fonts (the two Sofia
faces the first screen uses, and IBM Plex Mono's two weights). 140 KB
against the brief's 150. A device that draws layer 3 adds 167.

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
