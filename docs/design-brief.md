# NextCF — design brief for the next theme

**Status: the working brief, 2026-10-04 (second version).** Written at the
author's request before any design work on the theme that replaces the card
table (ADR 0029). The author answered its four open questions the same day
(§10); the next step is the two directions of §9. Once a direction is chosen from prototypes, it
gets its own ADR and this file becomes the record of what it was asked to
do.

The first version of this brief took gsap.com itself as the reference. The
author meant the sites in GSAP's **showcase**: the studio and portfolio
sites built with it. §4 is rewritten for those, and what follows from it
changed with it.

This is the prompt a designer is handed. It should be possible to build from
it without having read anything else.

---

## 1. The product, in one sentence

NextCF reads a Codeforces user's submission history and gives them five
problems to solve next, each with the chance that their first submission
will be accepted — aimed at about 50%, hard enough to teach something.

What is true and can be said (spec §9, `/how`):

- The chance comes from a model learned from 4,000 other users' first
  attempts (1.62 million of them), plus the visitor's own history.
- It predicts better than rating alone, measured twice: on a year it never
  saw (0.6535 → 0.5934 log loss), and on the two weeks after it went live
  (0.6199 → 0.5650).
- It is honest about its limits: about four points pessimistic around 50%.

What must never be claimed: which topics somebody is weak at (measured, and
it cannot tell); anything that reads as a ranking of people (spec §5); luck.
The five are chosen, not drawn.

## 2. Who arrives

A Codeforces user rated roughly 1000–1999, mostly a student, who has just
finished a contest or a practice session and wants to know what to do next.
They arrive from a Codeforces blog post or a friend's link, half of them on
a phone. They have seen a hundred developer-tool landing pages and trust
none of them. English is often their second language. A real share of them
are in mainland China, where font and script CDNs do not load.

They give the page about five seconds.

## 3. The one job of each page

| Page | Its one job |
|---|---|
| `/` | A stranger understands what the site does and types their handle |
| `/progress` | Somebody waiting knows it is working and how long is left |
| `/results` | Pick one of five problems and go and solve it |
| `/how` | A sceptic checks the claim and finds it holds |

## 4. The reference: the sites in GSAP's showcase

The author's reference. Four were looked at on 2026-10-04 (Unseen Studio,
Huy Phan, Revelatio Studio, Ravi Klaassens), along with the showcase's own
gallery of about forty, by opening the pages and reading what they are made
of, not from memory.

**What they have in common:**

- **Almost no colour.** Black and white, or one dark and one light. Three of
  the four have a pure black page with white type. Colour, where there is
  any, is one accent or the work being shown.
- **Type is the picture.** One grotesque typeface with a voice (Neue
  Montreal, Neue Haas Grotesk), set very large, and very small beside it.
  Nothing in between.
- **One living thing on the first screen.** A WebGL canvas or a video: at
  least three of the four draw on a canvas. The page is built around it.
- **Words are performed, not printed.** Lines rise from behind a mask,
  letters arrive one at a time, text scrambles and resolves.
- **The page is a film.** Smooth-scrolling libraries (two of the four load
  one), scenes that pin and play as they are scrolled, transitions between
  pages, a loader before anything shows.
- **A custom cursor.** One of the four hides the system's pointer and draws
  its own; things that follow the pointer are common.
- **Precision in the corners.** Index numbers (01 / 19), a live clock,
  small mono labels, registration marks. The detail says "made by someone
  who cares" before a word is read.
- **Very few words.** Unseen's whole first page is about a hundred. But
  one sentence does say what they are.

**What they are for, and why that matters.** Every one is a studio or a
portfolio. Its job is to impress another designer into making contact, and
making the visitor wait or work a little is part of the effect. NextCF's
first job is the opposite: a stranger knows what it does in five seconds.
The author asked for both, in the same message, and that is the brief:

> **Showcase craft, tool clarity.** The page should feel made like those
> sites, and be understood faster than any of them.

**What is taken from them:**

1. The near-monochrome canvas, with colour only where it means something.
2. One typeface with a voice, at two sizes: enormous and small.
3. One living object on the first screen that the page is built around.
4. Words that arrive: line and letter reveals, numbers that count and
   settle.
5. Scenes that play as they are scrolled to.
6. A response to the cursor and the finger on everything that can be
   pressed.
7. The corners: mono labels, real ids, live numbers, exact alignment.

**What is not taken, and why:**

- **A loader.** It spends the five seconds on nothing. The first screen is
  in the HTML and readable before any script runs.
- **Scroll that is taken over.** Smooth-scroll libraries replace the
  browser's own scrolling and feel wrong on a phone or a trackpad that is
  not the designer's. Scrolling stays the browser's; animation is tied to
  it.
- **A replaced cursor.** It hides the system's pointer, which some people
  cannot do without. Things may follow the cursor; nothing replaces it.
- **Being cryptic.** Scrambled text and unlabeled icons are part of the
  showcase's charm and the opposite of rule 1 below.
- **Weight.** Video, large images and 3D engines. See §7.
- **Weeks.** Spec §7.1 already says it: those sites are weeks of
  professional work with custom 3D, illustration and type. What can be had
  in one week is the first five items of the list above, done exactly. That
  is most of the impression.

## 5. What the site must be like

Each of these is written so it can be checked, not just agreed with.

### Clear at first sight

1. **The five-second test.** A Codeforces user who has never heard of the
   site looks at the first screen for five seconds, then says what it does
   and what they would do next. Both answers are right. Tested on real
   people, not judged.
2. **A literal headline.** It says what the visitor gets, in words they use
   themselves: problems, solve, next, chance. Nothing to decode. Eight words
   at most.
3. **The answer is on the first screen.** Not a description of the result:
   the result. Real problems with real chances, before scrolling, on a
   phone too.
4. **The field is on the first screen**, with one button whose label says
   what happens.

### The main thing stands out

5. **One focal object per screen.** On the first screen it is the living
   object of rule 13, and it is made of the product: the five problems and
   their chances. The headline and the field are arranged around it.
6. **Two sizes.** Enormous and small. The largest type is at least eight
   times the body text, as on the reference sites, and nothing is medium.
7. **Few words.** No section has more than 40 words of running text. What
   needs more lives on `/how`.
8. **Near-monochrome.** Two neutrals carry the interface. Saturated colour
   appears only on what means something: a rank colour is a rating, one
   accent is "act here".

### It reacts — and every reaction teaches

9. **Play before the handle.** A visitor can do something meaningful
   without typing anything, on the first screen.
10. **Every interaction shows how the product works.** After using it, the
    visitor knows something true about NextCF that they did not before.
    Candidates:
    - *Move your rating*: drag a rating from 800 to 2400 and the five
      re-pick themselves, from the real rating-only curve
      (`baseline.json`, two numbers, runs in the browser).
    - *Move the aim*: drag from "too hard" to "too easy" and watch the
      five get harder or easier. The site's own control, explained by
      holding it.
    - *Rating alone against the model*: one problem, two chances, for a
      real sample history.
    - *The calibration plot*: move along it and read "said 45%, 48%
      happened"; switch between the test year and the two weeks after
      launch.
11. **Everything pressable answers at once**, under 100 milliseconds, to
    hover, press, drag and focus. All of it works by touch; nothing
    depends on hover alone.
12. **Scenes, on the browser's own scroll.** History in, model, five out:
    three scenes that play as they are scrolled through and can be
    scrolled back. Scrolling is never taken over.

### Motion

13. **One living object** on the first screen, as the reference sites
    have, and it is the product working: numbers settling, problems
    arriving, the answer changing when the visitor moves something.
14. **Words arrive.** Headlines rise line by line from behind a mask;
    numbers count to their value. Once, on entry, never again on the same
    visit.
15. **Motion explains or confirms.** Where something came from, what
    changed, that a press was received. Anything that does neither goes.
16. **Fast and exact.** 150–400 milliseconds for a response, up to about a
    second for an entrance, one easing curve for the whole site. Transforms
    and opacity only, 60 frames a second on a mid-range phone.
17. **Still for those who ask.** With reduced motion set, everything is in
    its final place and nothing is missing.

### Identity

18. **Unmistakably Codeforces-native.** Rank colours, problem ids such as
    1850C, verdicts, the A–G letters of a contest. The corners of the page
    (rule 20) are filled with the product's real data, not decoration.
19. **A typeface with a voice** for display and reading, and a mono for
    data. Served from this site.
20. **The corners are finished.** Small mono labels, real ids, counts that
    are true, alignment to a grid that can be seen. This is where "made
    with care" is read.
21. **Not a template.** No gradient-text headline, no three-card feature
    row, no glass panels, no tilted dashboard mock-up, no emoji bullets.

### True

22. **Every number is real** and comes from the code or the model file.
    Sample data is real data from a real history and is labelled a sample.
23. **Bold, not louder than the evidence.** "Better than rating alone, and
    here is how it was checked", not "AI-powered".

### The tool pages

24. **The same world, quiet.** Same type, neutrals and corners as the
    landing page; no motion except to answer a press or show a change.
25. **The five come first**: on a 375 × 812 phone the first problem starts
    in the top half of the screen (spec §7.1, rule 13).
26. **Scannable.** Rating and chance for all five can be compared without
    reading a sentence.
27. **One press per answer**, on the page, with what it does said once.
    Nothing behind a menu (rule 5 of the spec's checklist).

## 6. The landing page, scene by scene

1. **First screen.** The headline arrives. The living object: five real
   problems and their chances for a sample history. The handle field and
   its button. One small line saying whose five these are. On a phone, all
   of it above the fold.
2. **Play.** One control the visitor can move, and the object answering.
3. **How.** History in, model, five out: three scenes, about 30 words each.
4. **Proof.** The calibration plot and the two measurements, one sentence
   each, linked to `/how`.
5. **Again.** The field, once more, alone on the screen.

## 7. What it must survive

Not preferences. A design that breaks one is not a candidate.

- **Complete without JavaScript.** Every word, the five sample problems and
  the form are in the HTML and laid out by the stylesheet. Script adds
  motion and play. (Most showcase sites are blank without it.)
- **The three layers** of spec §7.1 for anything heavy: the effect, a still
  of it, plain HTML under both; which one a device gets is decided as the
  page loads.
- **Nothing from another server.** Fonts and any library are served from
  this site.
- **375 pixels wide**, no sideways scroll, touch targets of 44 pixels. The
  first screen works on a phone as well as on a laptop, which few showcase
  sites manage.
- **4.5 to 1** for every text colour on every surface it sits on; visible
  keyboard focus; reduced motion honoured; the system cursor left alone.
- **Light.** Script and fonts for the landing page under about 150 KB
  compressed. No video. No image over 100 KB.
- **The pieces that exist.** Flask and Jinja for pages, one stylesheet of
  tokens, the React island on the results page. A theme changes tokens,
  templates and checks; it does not add a framework.
- **Spec §7.1's checklist**, all fourteen rules, before anything is shown.

## 8. What it is not

- Not a game of chance. Nothing like a lottery, a loot box or a slot
  machine. The pack of cards was close to that line.
- Not a leaderboard, not a profile to show off (spec §5).
- Not a portfolio. It may be made like one; it does not behave like one.
  Nothing makes the visitor wait, hunt or decode.
- Not a second design for the tool pages. One identity, two volumes.

## 9. What gets made, in what order

1. **Two directions, as working pages**, not pictures. Each has the full
   first screen with its living object, one interaction a visitor can
   really use, and the first screen of the results page, at desktop and
   phone width. They differ in their visual idea, not in their colours.
2. Each is checked against §5 and spec §7.1 before the author sees it, and
   says which rule it bends, if any.
3. **The five-second test** on two or three Codeforces users who are not
   the author, for the direction the author prefers.
4. The author chooses. Then, and only then: an ADR, the tokens, the
   templates, the checks, in that order.

A time limit, set before starting: **one week** from the choice of
direction to the landing page live. The last theme cost five redraws of one
page.

## 10. Decided by the author, 2026-10-04

The four questions this brief ended with, and the author's answers.

1. **The canvas: not pure black, and not a safe choice.** "Don't pure
   black. Be more creative." So the showcase's black-and-white is not
   taken as it stands. What is kept from it is the discipline: two
   neutrals carry the page and saturated colour means something (rule 8).
   What the two neutrals are is open, and is one of the things the two
   directions must differ in. A dark page that is not black, a light one,
   or a page whose ground is itself a strong colour are all candidates.
2. **GSAP: yes.** Served from this site: the core, ScrollTrigger for
   scenes tied to scrolling, SplitText for lines and letters that arrive.
   These two effects are what the author asked for by name.
3. **The living object: real 3D.** WebGL, not only elements and SVG. So
   spec §7.1's three layers apply in full: the effect, a still of it, and
   plain HTML under both, chosen as the page loads; the library loaded only
   by a device that will run it; a frame-rate check that steps down. The
   object is still the product (rule 13): what is drawn in 3D is the five
   problems and their chances, not an ornament beside them. The weight
   limit in §7 is for what every visitor downloads; the 3D library is on
   top of it, and only for devices that get layer 3.
4. **The cards: probably start again from nothing.** Said as "maybe". The
   directions are free of the card idea. Rank colours stay.

The characteristics in §5 stand as written, with rule 8 read as in point 1.
