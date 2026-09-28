// The topic chart and the five it filters, as one component -- ADR 0025.
//
// What this adds over the page Flask already drew: choosing a topic swaps the
// five without reloading, and the address bar follows, so reloading or
// sharing the page shows the same list. Everything else on the page is plain
// HTML the server wrote.
//
// Where the five come from: /results/<handle>/recommendations?topic=..., the
// same recommendation_view the page itself calls (web.py). The component never
// decides which problems to show; it only asks and draws.
//
// If asking fails -- offline, the server restarting -- it does what the link
// would have done without it: goes to that address. A visitor never ends up
// on a page that silently did nothing.

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import Recommendations from './Recommendations.jsx'
import TopicChart from './TopicChart.jsx'
import { dataUrl, pageUrl } from './urls.js'

export default function TopicIsland({
  initial,
  // Swappable so the tests can stand in for the network and for leaving the
  // page; the defaults are the real browser.
  fetchImpl = (...args) => window.fetch(...args),
  navigate = (url) => window.location.assign(url),
}) {
  const [recs, setRecs] = useState(initial.recs)
  const [dismissed, setDismissed] = useState(initial.dismissed)
  const [busy, setBusy] = useState(false)
  const heading = useRef(null)

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

  // A press reloads the page at an address naming its row or the list
  // (web.row_anchor, web.LIST_ANCHOR), and the browser scrolls there as the
  // page arrives. Then this component replaces the rows the browser scrolled
  // to with its own, and the place is lost: measured 2026-09-28 at phone
  // width, a row landed at the top and then jumped 970 pixels away. So on
  // the first draw -- a layout effect, before anything is painted -- go back
  // to it. Without JavaScript nothing is replaced and the browser's own
  // scroll stands.
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
