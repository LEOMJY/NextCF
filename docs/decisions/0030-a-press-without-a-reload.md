# 0030 — A press without a reload

**Date:** 2026-09-29
**Status:** accepted

## Context

Every button on the five was a plain HTML form: "too hard", "too easy",
"skip", "undo", "put back". A press sent a POST, the server recorded it and
answered with a redirect back to the row (ADR 0021, 0028; the row's address
since 2026-09-28), and the browser loaded the whole results page again.
That is what works with scripting off, which spec §7.1's first layer asks
for. The author, using it: "it refreshes the whole page every time I press
too hard or too easy." A plan is answered five presses at a time, so each
press flashing the whole page is felt five times.

The results page already has a React island (ADR 0025). Choosing a topic
swaps the five without a reload, drawing what
`/results/<handle>/recommendations` returns. Most of what a press needs
already existed.

## Decision

The author chose to have **the server answer a press made by the page's
script with the five as data**:

1. **The three routes answer in two ways.** `feedback`, `undo` and `restore`
   record the press exactly as before. Then `web.wants_data` reads the
   request's `Accept` header, the line in every request that says what kind
   of answer the sender wants. A browser sending a form asks for HTML first
   and gets the redirect it always got. The island's `fetch` asks for
   `application/json` and gets the list's five in the same shape as
   `/recommendations`, from the same `recommendation_view` and recorded as
   shown the same way (`web.five_as_data`). A refusal (an unknown verdict, an
   unknown problem) stays the error page it was.
2. **The island sends the form itself.** `TopicIsland.jsx` catches the
   submit, sends the same fields plus the pressed button's value (a verdict
   is the button's own value, and a form's data leaves the button out), and
   draws the five that come back.
3. **The keyboard and the screen reader are told.** Focus goes to the
   control that took the pressed one's place: "undo" on a row just marked,
   "too hard" on a row just taken back, the list's heading after "put
   back". A status line inside the section, drawn empty by the template,
   says what changed ("Huge Pile: skipped.").
4. **Anything else, and the form goes the ordinary way.** If anything but
   the five comes back (an error page, a redirect, no answer at all), the
   island sends the form as a browser would, which reloads the page and
   shows whatever the server had to say. Sending it twice is harmless: the
   same answer about the same problem counts once (`db.record_feedback`),
   and undo and put back change nothing the second time. A second press
   while the first is on its way is swallowed.
5. **Ending a plan still reloads.** "Swap the five" and "next five" move the
   target, start the next plan and add to the history under the list: more
   of the page than the five changes.

## Alternatives

**The island sends the press, then asks `/recommendations` for the five
(two requests).** No server change at all. The author chose one request
instead of two.

**A field of our own ("js=1") instead of the Accept header.** It would work,
and it is one more thing for a hand-made POST to add or leave out. The
Accept header is already sent by every browser and says exactly this.

**JSON errors for a script's press.** Each refusal would need a second form
in the three routes and a message drawn by the island. Falling back to the
ordinary form shows the server's own error page, already written and
already checked, for a case a visitor meets only by hand-editing the page.

**Leaving it.** Five full reloads per plan.

## Consequences

- **A press is one request and no reload.** Measured in the browser: one
  POST each, answered 200 with JSON, the page's own state untouched, the
  plan's line updated ("1 of 5 done").
- **Two answers from one route**, so `check_plans` holds both. Script gets
  data; no header, a browser's own header or `*/*` gets the redirect; a
  refusal is a page either way.
- **The template and `Recommendations.jsx` still mirror each other**,
  including the new status line, which the template draws empty.
- **Without JavaScript nothing changed.** A press is the form and the
  redirect to its row, as before.
