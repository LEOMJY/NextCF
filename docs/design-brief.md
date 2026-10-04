# NextCF — design brief for the next theme

**Status: draft, 2026-10-04.** Written at the author's request before any
design work on the theme that replaces the card table (ADR 0029). Nothing in
here is decided until the author says so; the open decisions are listed at
the end. Once a direction is chosen from prototypes, it gets its own ADR and
this file becomes the record of what it was asked to do.

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

## 4. The reference: gsap.com

The author's reference, looked at on 2026-10-04. What it does:

- **Two words say what it is.** "Animate Anything", about 200 pixels tall.
  The one line under it says who it is for.
- **The page is the product.** GSAP animates things, so every section of
  the page is an animation you can watch or play with. Nothing is described
  that could be shown.
- **Colour lives in the objects, not in the interface.** The background is
  near-black (`rgb(14,16,15)`), the text is cream, buttons are a cream
  outline or a cream fill. Every saturated colour is on a shape that moves.
- **One thing per screen.** Each section has one large object and a few
  words. It is 9,000 pixels long and never crowded.
- **It reacts.** To the cursor, to scrolling, to hovering. The visitor is
  doing something every few seconds, not reading.

**What transfers, and what does not.** GSAP's product is motion, so motion
is its demonstration. NextCF's product is a prediction. Copying the surface
— floating shapes, letters flying in — would be decoration, which this
project's own checklist forbids (spec §7.1, rule 4). The lesson that
transfers is the principle: **show the product working instead of describing
it, and let the visitor play with it before asking for anything.** For
NextCF that means the page makes predictions in front of the visitor, and
the visitor can change the inputs and watch the answer move.

One more difference. GSAP's page can leave content invisible until it
scrolls into view; captured without scrolling, most of it is blank. NextCF's
cannot: it has to be complete with scripting off (§9 below).

## 5. What the site must be like

Each of these is written so it can be checked, not just agreed with.

### Clear at first sight

1. **The five-second test.** A Codeforces user who has never heard of the
   site looks at the first screen for five seconds, then says what it does
   and what they would do next. Both answers are right. This is tested on
   real people, not judged.
2. **A literal headline.** It says what the visitor gets, in words they use
   themselves: problems, solve, next, chance. No metaphor that has to be
   decoded first. Eight words at most.
3. **The answer is on the first screen.** Not a description of the result:
   the result. Five real problems with real chances, visible before
   scrolling, on a phone too.
4. **The field is on the first screen**, next to the answer, with one
   button whose label says what happens.

### The main thing stands out

5. **One focal object per screen.** On the first screen it is the five
   problems. Everything else — headline, field — is arranged around it and
   is clearly smaller or quieter.
6. **Scale does the work.** One element is very large, most are small.
   Nothing is medium. The largest type on the page is at least six times
   the size of the body text.
7. **Few words.** No section has more than 40 words of running text. What
   needs more lives on `/how`.
8. **Colour is spent on the main thing.** The interface itself is two
   neutrals. Saturated colour appears only on what the visitor should look
   at or touch.

### It reacts — and every reaction teaches

9. **Play before the handle.** A visitor can do something meaningful
   without typing anything: move a control and watch five problems change.
   The first interaction is available within the first screen.
10. **Every interaction shows how the product works.** Not decoration. The
    test for each one: after using it, the visitor knows something true
    about NextCF that they did not know before. Candidates:
    - *Move your rating*: drag a rating from 800 to 2400 and the five
      re-pick themselves, from the real rating-only curve
      (`baseline.json`, two numbers, runs in the browser).
    - *Move the aim*: drag from "too hard" to "too easy" and watch the
      five get harder or easier. This is the site's own difficulty control,
      explained by letting someone hold it.
    - *Rating alone against the model*: the same problem, two chances side
      by side, for a real sample history.
    - *The calibration plot*: hover a point and read "said 45%, 48%
      happened"; switch between the test year and the two weeks after
      launch.
11. **It answers the cursor and the finger.** Hover, press, drag and focus
    each have a visible, immediate response, under 100 milliseconds. Every
    interaction works by touch; nothing depends on hover alone.
12. **Scrolling tells the story once.** History in, model, five out: three
    beats, each a picture that assembles as it is scrolled to. The page is
    never hijacked: scrolling always scrolls.

### Motion

13. **One signature moment**, the thing somebody describes an hour later.
    It happens on the first screen and it is the product doing its job (the
    five arriving), not an ornament.
14. **Motion explains or confirms.** It shows where something came from,
    what changed, or that a press was received. Anything that does neither
    is removed.
15. **Fast and physical.** 150–400 milliseconds for responses, eased out.
    Transforms and opacity only, 60 frames a second on a mid-range phone.
16. **Still for those who ask.** With reduced motion set, everything is in
    its final place and nothing moves; nothing is lost.

### Identity

17. **Unmistakably Codeforces-native.** Rank colours, problem ids such as
    1850C, verdicts, the A–G letters of a contest. Somebody from that world
    recognises their own things; a generic SaaS page could not have them.
18. **Not a template.** No gradient-text headline, no three-card feature
    row, no glass panels, no dashboard mock-up tilted in 3D, no emoji
    bullets.
19. **A typeface with a voice** for the display, a quiet one for reading,
    a mono for data. Three roles, one job each.
20. **Dark, but not dim.** If the canvas is dark it is carried by large
    areas of saturated colour and very large type, so it reads as lively,
    not as a terminal. (The author rejected black as "too dim, too serious"
    on 2026-09-29, and gsap.com is near-black: see the open decisions.)

### True

21. **Every number is real** and comes from the code or the model file.
    Sample data is real data from a real history and is labelled a sample.
22. **Bold, not louder than the evidence.** The claim is "better than
    rating alone, and here is how we checked", not "AI-powered".

### The tool pages

23. **The same world, quiet.** Same type, colour and shapes as the landing
    page; no motion except to answer a press or show a change.
24. **The five come first**: on a 375 × 812 phone the first problem starts
    in the top half of the screen (spec §7.1, rule 13).
25. **Scannable.** Rating and chance for all five can be compared without
    reading a sentence.
26. **One press per answer**, on the page, with what it does said once.
    Nothing behind a menu (rule 5).

## 6. The landing page, beat by beat

1. **First screen.** Headline; the five problems for a sample history,
   arriving; the handle field and its button; one line saying whose five
   these are. On a phone, all of that above the fold.
2. **Play.** One control the visitor can move, and the five changing with
   it.
3. **How.** History in, model, five out: three pictures, about 30 words
   each.
4. **Proof.** The calibration plot and the two measurements, each one
   sentence, linked to `/how`.
5. **Again.** The field, once more, with nothing else on the screen.

## 7. What it must survive

These are not preferences. A design that breaks one is not a candidate.

- **Complete without JavaScript.** Every word, the five sample problems and
  the form are in the HTML and laid out by the stylesheet. Script only adds
  motion and play.
- **Nothing from another server.** Fonts and any library are served from
  this site (mainland China; spec §7.1).
- **375 pixels wide**, no sideways scroll, touch targets of 44 pixels.
- **4.5 to 1** for every text colour on every surface it sits on; visible
  keyboard focus; reduced motion honoured.
- **Light enough.** The first screen is readable before any script has
  run. Script and fonts for the landing page stay under about 150 KB
  compressed.
- **The pieces that exist.** Flask and Jinja for pages, one stylesheet of
  tokens, the React island on the results page. A new theme changes the
  tokens, the templates and their checks; it does not add a framework.
- **Spec §7.1's checklist**, all fourteen rules, before anything is shown.

## 8. What it is not

- Not a game of chance. Nothing that looks like a lottery, a loot box or a
  slot machine. The pack of cards was close to that line.
- Not a leaderboard, not a profile to show off (spec §5).
- Not decorated. No shape floats, spins or follows the cursor unless it is
  information.
- Not a second design for the tool pages. One identity, two volumes.

## 9. What gets made, in what order

1. **Two directions, as working pages**, not pictures. Each has the full
   first screen, one interaction a visitor can really use, and the first
   screen of the results page, at desktop and phone width. They differ in
   their visual idea, not in their colours.
2. Each is checked against §5 and spec §7.1 before the author sees it, and
   says which rule it bends, if any.
3. **The five-second test** on two or three Codeforces users who are not
   the author, for the direction the author prefers.
4. The author chooses. Then, and only then: an ADR, the tokens, the
   templates, the checks, in that order.

A time limit, set before starting: **one week** from the choice of direction
to the landing page live. The last theme cost five redraws of one page.

## 10. For the author to decide before any drawing

1. **The canvas.** Near-black as on gsap.com, the navy that was kept on
   09-29, or light. Black was rejected once as dim; gsap.com is black and
   is not dim, because of how much colour and scale sits on it. Which is
   wanted?
2. **The animation library.** Scroll-driven storytelling and drag are
   possible by hand in small amounts. Past that, GSAP itself is the
   standard tool; it has been free since 2025, and would be served from
   this site (about 40 KB compressed for the core and the scroll plugin).
   It is a new dependency, so it is the author's call.
3. **The cards.** Start again from nothing, or keep the idea that a problem
   is a card? Rank colours stay either way: they are Codeforces's own.
