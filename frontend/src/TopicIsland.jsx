// The topic chart and the five it filters, as one component -- ADR 0025.
//
// What this adds over the page Flask already drew: choosing a topic swaps the
// five without reloading, and the address bar follows, so reloading or
// sharing the page shows the same list; and since ADR 0030, "too hard", "too
// easy", "skip", "undo" and "put back" are sent without a reload too, and the
// server's answer -- the list's five -- is drawn in place. Everything else on
// the page is plain HTML the server wrote.
//
// And since 2026-10-15 the page checks Codeforces by itself when its tab is
// returned to (ADR 0018, amended): somebody who went to solve one of the five
// comes back to find it ticked, without a press and without a reload. See
// "THE PAGE'S OWN CHECK" below.
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
  // Time, swappable for the same reason: the tests decide when "now" is and
  // how long a wait takes, instead of sleeping.
  now = () => Date.now(),
  wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
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
  // The page's own check: whether one is under way (the note beside "Check
  // what I solved" says so), and when the last one ended -- or the page
  // arrived, which counts as one: what it shows was read moments ago.
  const [checking, setChecking] = useState(false)
  const inFlight = useRef(false)
  const lastCheck = useRef(now())
  // The list on screen, for code that runs later than the render that drew
  // it: a listener added once would otherwise only ever see the first list.
  const onScreen = useRef(recs)
  useEffect(() => { onScreen.current = recs }, [recs])
  // The network and the clock, for the same reason. The defaults above are
  // new functions on every render, and an effect that listed them would be
  // taken down and set up again on every render -- including the render
  // that "checking" itself causes, which ended the check it was showing.
  const tools = useRef({ fetchImpl, now, wait })
  useEffect(() => { tools.current = { fetchImpl, now, wait } })

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

  // THE PAGE'S OWN CHECK (ADR 0018, amended 2026-10-15). When the tab comes
  // back into view -- the visitor went to Codeforces and has returned -- ask
  // Codeforces for the history again, wait for it, and redraw the five in
  // place, so a problem solved meanwhile is ticked. All of these must hold:
  //
  //   - something on screen could still be ticked: a plan with a problem
  //     not yet solved. Five ticks already, nothing to look for;
  //   - the last check (or the page's arrival) was check_every seconds ago
  //     or more. The server keeps the same limit for the handle
  //     (web.AUTO_CHECK_SECONDS) and answers "started": false inside it;
  //   - no check is under way, and no sync was running when the page was
  //     drawn: then the line at the top of the page is watching that one.
  //
  // It is silent when anything goes wrong -- offline, Codeforces down, the
  // sync failing. The page still shows what it showed, which is still true,
  // and the next return tries again. Nothing moves the keyboard: the visitor
  // did not press anything.
  useEffect(() => {
    if (!initial.urls.resync || initial.syncing) return undefined
    let gone = false
    const every = (initial.check_every || 60) * 1000

    async function check() {
      const { fetchImpl: ask, wait: pause } = tools.current
      inFlight.current = true
      setChecking(true)
      try {
        const started = await ask(initial.urls.resync, {
          method: 'POST',
          headers: { Accept: 'application/json' },
        })
        if (!started.ok) return
        const begun = await started.json()
        if (!begun.status) return               // held back: checked in the last minute
        // Ask until the sync is over, as often as the server says, and at
        // most 60 times: a sync is seconds, and a queue of strangers' syncs
        // a minute or two. A page left asking for ever is a bug.
        let state = 'pending'
        let next = begun.poll_in
        for (let asked = 0; asked < 60 && !gone; asked += 1) {
          await pause(Math.max(1, next || 2) * 1000)
          const answer = await ask(begun.status, { headers: { Accept: 'application/json' } })
          if (!answer.ok) return
          const status = await answer.json()
          state = status.state
          next = status.poll_in
          if (state !== 'pending' && state !== 'running') break
        }
        if (state !== 'done' || gone) return
        // The list on screen now, which may not be the one the check began
        // on: a topic chosen meanwhile is the one to redraw.
        const before = onScreen.current
        const solvedBefore = new Set(
          before.state === 'ok' ? before.problems.filter((problem) => problem.solved).map((problem) => problem.id) : [],
        )
        const response = await ask(dataUrl(initial.urls, before.topic), {
          headers: { Accept: 'application/json' },
        })
        if (!response.ok) return
        const data = await response.json()
        if (gone) return
        setRecs(data.recs)
        setDismissed(data.dismissed)
        // Read out what changed, and only that: nothing when nothing did.
        const fresh = data.recs.state === 'ok'
          ? data.recs.problems.filter((problem) => problem.solved && !solvedBefore.has(problem.id))
          : []
        if (fresh.length) setSaid(`Solved since you last looked: ${fresh.map((problem) => problem.name).join(', ')}.`)
      } catch {
        // Silent, as above.
      } finally {
        inFlight.current = false
        lastCheck.current = tools.current.now()
        if (!gone) setChecking(false)
      }
    }

    function onReturn() {
      if (document.visibilityState !== 'visible') return
      const list = onScreen.current
      if (list.state !== 'ok' || !list.problems.some((problem) => !problem.solved)) return
      if (inFlight.current || tools.current.now() - lastCheck.current < every) return
      check()
    }

    document.addEventListener('visibilitychange', onReturn)
    return () => {
      gone = true
      document.removeEventListener('visibilitychange', onReturn)
    }
  }, [initial.urls, initial.syncing, initial.check_every])

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
        syncing={initial.syncing}
        checking={checking}
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
