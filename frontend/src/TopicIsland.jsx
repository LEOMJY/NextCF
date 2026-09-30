// The topic chart and the five it filters, as one component -- ADR 0025.
//
// What this adds over the page Flask already drew: choosing a topic swaps the
// five without reloading, and the address bar follows, so reloading or
// sharing the page shows the same list; and since ADR 0030, "too hard", "too
// easy", "skip", "undo" and "put back" are sent without a reload too, and the
// server's answer -- the list's five -- is drawn in place. Everything else on
// the page is plain HTML the server wrote.
//
// Where the five come from: /results/<handle>/recommendations?topic=..., the
// same recommendation_view the page itself calls (web.py). The component never
// decides which problems to show; it only asks and draws.
//
// If asking fails -- offline, the server restarting -- it does what the link
// or the form would have done without it: goes to that address, or sends the
// form the ordinary way. A visitor never ends up on a page that silently did
// nothing.

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import Recommendations from './Recommendations.jsx'
import TopicChart from './TopicChart.jsx'
import { dataUrl, pageUrl } from './urls.js'

// What a press did, in the words the row itself now shows.
const SAID = { too_hard: 'marked too hard', too_easy: 'marked too easy', skip: 'skipped' }

// Send a form the ordinary way, reloading the page, with the button that
// was pressed: form.submit() leaves the button out, and a verdict is the
// button's own value. Not requestSubmit(), which would come back here.
function submitForm(form, pressed) {
  if (pressed && pressed.name) {
    const carried = document.createElement('input')
    carried.type = 'hidden'
    carried.name = pressed.name
    carried.value = pressed.value
    form.appendChild(carried)
  }
  form.submit()
}

export default function TopicIsland({
  initial,
  // Swappable so the tests can stand in for the network and for leaving the
  // page; the defaults are the real browser.
  fetchImpl = (...args) => window.fetch(...args),
  navigate = (url) => window.location.assign(url),
  submit = submitForm,
}) {
  const [recs, setRecs] = useState(initial.recs)
  const [dismissed, setDismissed] = useState(initial.dismissed)
  const [busy, setBusy] = useState(false)
  const [said, setSaid] = useState('')
  // How many presses have been drawn: what the focus effect below follows.
  // Not the five themselves -- an answer equal to what is on screen is not
  // a new state to React, and the keyboard still has to go somewhere.
  const [drawnPresses, setDrawnPresses] = useState(0)
  const heading = useRef(null)
  // A press on its way to the server. A second press meanwhile -- a
  // double-click -- is swallowed rather than sent twice.
  const pressing = useRef(false)
  // After a press is drawn, where the keyboard goes: a problem's id, '' for
  // the heading, null for nowhere.
  const focusNext = useRef(null)

  // Fetch one topic's five (null: the overall five) and draw them.
  // `push` is false when the browser's back or forward button asked, because
  // the address is already where it should be.
  const choose = useCallback(async (topic, { push = true } = {}) => {
    const address = pageUrl(initial.urls, topic)
    setBusy(true)
    try {
      const response = await fetchImpl(dataUrl(initial.urls, topic), {
        headers: { Accept: 'application/json' },
      })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      setRecs(data.recs)
      setDismissed(data.dismissed)
      if (push) window.history.pushState({ topic }, '', address)
      // Move focus to the list's heading, so a screen reader announces the
      // new list ("Next in dp") instead of staying on a link that no longer
      // describes what changed.
      heading.current?.focus()
    } catch {
      navigate(address)
    } finally {
      setBusy(false)
    }
  }, [fetchImpl, navigate, initial.urls])

  // A press without a reload (ADR 0030). The form is sent as it would be,
  // with the pressed button's value, asking for the five back as data
  // (web.wants_data); they are drawn in place, a screen reader is told what
  // changed, and the keyboard goes to the control that took the pressed
  // one's place. Anything but a list of five coming back -- an error page, a
  // redirect to a page, no answer -- and the form is sent the ordinary way,
  // which shows whatever the server has to say. Sending it twice is
  // harmless: the same answer about the same problem counts once
  // (db.record_feedback).
  const press = useCallback(async (event) => {
    const form = event.currentTarget
    const pressed = event.nativeEvent.submitter
    // A browser too old to say which button sent the form cannot send the
    // verdict either; it gets the ordinary form.
    if (!pressed && form.querySelector('button[name]')) return
    event.preventDefault()
    if (pressing.current) return
    pressing.current = true
    const body = new FormData(form)
    if (pressed && pressed.name) body.append(pressed.name, pressed.value)
    try {
      const response = await fetchImpl(form.getAttribute('action'), {
        method: 'POST',
        body,
        headers: { Accept: 'application/json' },
      })
      const type = response.headers?.get('Content-Type') || ''
      if (!response.ok || !type.includes('application/json')) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      const id = body.get('problem')
      const row = id && data.recs.state === 'ok' ? data.recs.problems.find((problem) => problem.id === id) : null
      setSaid(row
        ? `${row.name}: ${row.outcome ? SAID[row.outcome] : 'back in the plan'}.`
        : 'The problems you hid are back.')
      focusNext.current = row ? id : ''
      setRecs(data.recs)
      setDismissed(data.dismissed)
      setDrawnPresses((count) => count + 1)
    } catch {
      submit(form, pressed)
    } finally {
      pressing.current = false
    }
  }, [fetchImpl, submit])

  // Once a press is drawn: the row's first button -- "undo" on a row just
  // marked, "too hard" on a row just taken back -- or the heading, when the
  // pressed control has gone and nothing took its place ("put back").
  useEffect(() => {
    const id = focusNext.current
    if (id === null) return
    focusNext.current = null
    const control = id ? document.getElementById(`p-${id}`)?.querySelector('button') : null
    if (control) control.focus()
    else heading.current?.focus()
  }, [drawnPresses])

  // A press sent the ordinary way reloads the page at an address naming its
  // row or the list (web.row_anchor, web.LIST_ANCHOR), and the browser
  // scrolls there as the page arrives. Then this component replaces the
  // rows the browser scrolled to with its own, and the place is lost:
  // measured 2026-09-28 at phone width, a row landed at the top and then
  // jumped 970 pixels away. So on the first draw -- a layout effect, before
  // anything is painted -- go back to it. Without JavaScript nothing is
  // replaced and the browser's own scroll stands.
  useLayoutEffect(() => {
    const id = decodeURIComponent(window.location.hash.slice(1))
    const target = id ? document.getElementById(id) : null
    // scrollIntoView honours the rows' scroll-margin-top in style.css.
    if (target && target.scrollIntoView) target.scrollIntoView()
  }, [])

  // The back and forward buttons: the address changed, so draw its list.
  useEffect(() => {
    const onPop = () => {
      const topic = new URLSearchParams(window.location.search).get('topic')
      choose(topic, { push: false })
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [choose])

  // A click on any topic link. A click that means "open elsewhere" -- with
  // Ctrl, Cmd, Shift, or a middle button -- is left to the browser, which
  // opens the link's real address in a new tab.
  const onChoose = (event, topic) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return
    event.preventDefault()
    choose(topic)
  }

  return (
    <>
      <Recommendations
        handle={initial.handle}
        recs={recs}
        dismissed={dismissed}
        dismissalsKept={initial.dismissals_kept}
        urls={initial.urls}
        busy={busy}
        heading={heading}
        onChoose={onChoose}
        onPress={press}
        said={said}
      />
      <TopicChart
        topics={initial.topics}
        otherTopics={initial.other_topics}
        totals={initial.totals}
        current={recs.topic}
        urls={initial.urls}
        onChoose={onChoose}
      />
    </>
  )
}
