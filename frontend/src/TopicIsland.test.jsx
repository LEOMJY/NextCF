// Component tests for the topic chart (ADR 0025), run by Vitest in jsdom --
// a browser page simulated in Node. `npm test` in frontend/, and
// tests/run.py runs it too when frontend/node_modules exists.
//
// The network and page navigation are stand-ins passed in as props, so these
// check what the component does, not what a server happens to answer.

import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import TopicIsland from './TopicIsland.jsx'

afterEach(cleanup)

const urls = {
  results: '/results/somebody',
  recommendations: '/results/somebody/recommendations',
  feedback: '/results/somebody/feedback',
  restore: '/results/somebody/restore',
  undo: '/results/somebody/undo',
  plan: '/results/somebody/plan',
  how: '/how',
}

function problem(id, name, extra = {}) {
  return { id, name, rating: 1500, percent: 50, probability: 0.5, thin: false, guarded: true,
           solved: false, outcome: null,
           url: `https://codeforces.com/problemset/problem/${id}`, ...extra }
}

// A list as web.recommendation_view returns it: a plan (ADR 0026) with
// nothing done yet, aiming where the next one will, unless `extra` says not.
function recs(topic, problems, extra = {}) {
  const target = extra.target ?? 50
  return { state: 'ok', source: 'topic', topic, own_target: false, overall_target: 50,
           target, next_target: target, looked_up_at: null, unguarded: false, reach: null,
           at_end: null, extrapolated: false, unrated: false, hidden: false,
           plan: { id: 7, started_at: '2026-09-27T10:00:00Z', started_ago: 'just now',
                   size: problems.length, settled: 0, solved: 0, complete: false },
           problems, ...extra }
}

// Draw `list` as the page's own first list, without choosing anything.
function drawn(list) {
  return render(<TopicIsland initial={{ ...initial, recs: list }} fetchImpl={answering({})} navigate={vi.fn()} />)
}

const initial = {
  handle: 'somebody',
  recs: recs(null, [problem('1A', 'Overall One'), problem('2A', 'Overall Two')]),
  dismissed: 0,
  dismissals_kept: 50,
  topics: [{ tag: 'dp', solved: 3, attempted: 4, rated_solved: 3, mean: 1400, width: 100 },
           { tag: 'math', solved: 1, attempted: 1, rated_solved: 1, mean: 900, width: 33.3 }],
  other_topics: ['fft'],
  totals: { solved: 4, solved_untagged: 0 },
  urls,
}

// A fetch that answers every request with `body`, and records what it was asked.
function answering(body, ok = true) {
  return vi.fn(async () => ({ ok, status: ok ? 200 : 500, json: async () => body }))
}

describe('the topic chart', () => {
  it('draws what the page drew', () => {
    render(<TopicIsland initial={initial} fetchImpl={answering({})} navigate={vi.fn()} />)
    expect(screen.getByText('Overall One')).toBeTruthy()
    expect(screen.getByRole('heading', { name: 'Next' })).toBeTruthy()
    // Every topic is a real link, practised or not.
    expect(screen.getByRole('link', { name: 'dp' }).getAttribute('href')).toBe('/results/somebody?topic=dp')
    expect(screen.getByRole('link', { name: 'fft' }).getAttribute('href')).toBe('/results/somebody?topic=fft')
  })

  // Folded since the review of 2026-09-28; open when the topic on screen is
  // one of the unpractised ones, so the link marked as the current page shows.
  it('folds the unpractised topics, open only when one of them is on screen', async () => {
    const { container } = render(<TopicIsland initial={initial} fetchImpl={answering({ recs: recs('fft', [problem('7A', 'An FFT Problem')]), dismissed: 0 })} navigate={vi.fn()} />)
    const fold = container.querySelector('details.other-topics')
    expect(fold.querySelector('summary').textContent).toBe('Not practised yet: 1 topic')
    expect(fold.open).toBe(false)
    fireEvent.click(screen.getByRole('link', { name: 'fft' }))
    await screen.findByText('An FFT Problem')
    expect(container.querySelector('details.other-topics').open).toBe(true)
    expect(container.querySelector('details.footnote summary').textContent).toBe('Why Solved adds up to more than 4')
  })

  it('choosing a topic swaps the five in place, and the address follows', async () => {
    const fetchImpl = answering({ recs: recs('dp', [problem('9A', 'A DP Problem')]), dismissed: 0 })
    const push = vi.spyOn(window.history, 'pushState')
    render(<TopicIsland initial={initial} fetchImpl={fetchImpl} navigate={vi.fn()} />)

    fireEvent.click(screen.getByRole('link', { name: 'dp' }))

    await screen.findByText('A DP Problem')
    expect(fetchImpl).toHaveBeenCalledWith('/results/somebody/recommendations?topic=dp', expect.anything())
    expect(push).toHaveBeenCalledWith({ topic: 'dp' }, '', '/results/somebody?topic=dp')
    expect(screen.getByRole('heading', { name: 'Next in dp' })).toBeTruthy()
    expect(screen.queryByText('Overall One')).toBeNull()
    push.mockRestore()
  })

  it('marks the chosen topic', async () => {
    const fetchImpl = answering({ recs: recs('math', [problem('3A', 'Math One')]), dismissed: 0 })
    render(<TopicIsland initial={initial} fetchImpl={fetchImpl} navigate={vi.fn()} />)
    fireEvent.click(screen.getByRole('link', { name: 'math' }))
    await screen.findByText('Math One')
    expect(screen.getByRole('link', { name: 'math' }).getAttribute('aria-current')).toBe('page')
    expect(screen.getByRole('link', { name: 'dp' }).getAttribute('aria-current')).toBeNull()
  })

  it('a press on a topic list says which list it was made on', async () => {
    const fetchImpl = answering({ recs: recs('dp', [problem('9A', 'A DP Problem')]), dismissed: 0 })
    const { container } = render(<TopicIsland initial={initial} fetchImpl={fetchImpl} navigate={vi.fn()} />)
    fireEvent.click(screen.getByRole('link', { name: 'dp' }))
    await screen.findByText('A DP Problem')
    const form = container.querySelector('.verdict-form')
    expect(form.getAttribute('action')).toBe('/results/somebody/feedback')
    expect(form.querySelector('input[name="topic"]').value).toBe('dp')
  })

  it('if asking fails, it goes where the link goes', async () => {
    const navigate = vi.fn()
    render(<TopicIsland initial={initial} fetchImpl={answering({}, false)} navigate={navigate} />)
    fireEvent.click(screen.getByRole('link', { name: 'dp' }))
    await waitFor(() => expect(navigate).toHaveBeenCalledWith('/results/somebody?topic=dp'))
  })

  it('a click meant for a new tab is left to the browser', () => {
    const fetchImpl = answering({})
    render(<TopicIsland initial={initial} fetchImpl={fetchImpl} navigate={vi.fn()} />)
    fireEvent.click(screen.getByRole('link', { name: 'dp' }), { ctrlKey: true })
    expect(fetchImpl).not.toHaveBeenCalled()
  })

  it('only a filled row says it rests on less evidence', async () => {
    const small = recs('fft', [problem('5A', 'Guarded FFT'), problem('6A', 'Filled FFT', { thin: true })])
    render(<TopicIsland initial={initial} fetchImpl={answering({ recs: small, dismissed: 0 })} navigate={vi.fn()} />)
    fireEvent.click(screen.getByRole('link', { name: 'fft' }))
    await screen.findByText('Filled FFT')
    const notes = document.querySelectorAll('.thin-note')
    expect(notes.length).toBe(1)
    expect(notes[0].closest('td').textContent).toContain('Filled FFT')
  })

  it('"All topics" goes back to the overall five', async () => {
    const fetchImpl = vi.fn()
      .mockResolvedValueOnce({ ok: true, json: async () => ({ recs: recs('dp', [problem('9A', 'A DP Problem')]), dismissed: 0 }) })
      .mockResolvedValueOnce({ ok: true, json: async () => ({ recs: initial.recs, dismissed: 0 }) })
    render(<TopicIsland initial={initial} fetchImpl={fetchImpl} navigate={vi.fn()} />)
    fireEvent.click(screen.getByRole('link', { name: 'dp' }))
    await screen.findByText('A DP Problem')
    fireEvent.click(screen.getAllByRole('link', { name: 'All topics' })[0])
    await screen.findByText('Overall One')
    expect(fetchImpl).toHaveBeenLastCalledWith('/results/somebody/recommendations', expect.anything())
  })

  it('the back button draws the list its address names', async () => {
    const fetchImpl = answering({ recs: recs('math', [problem('3A', 'Math One')]), dismissed: 0 })
    render(<TopicIsland initial={initial} fetchImpl={fetchImpl} navigate={vi.fn()} />)
    window.history.replaceState({}, '', '/results/somebody?topic=math')
    fireEvent(window, new PopStateEvent('popstate'))
    await screen.findByText('Math One')
    expect(fetchImpl).toHaveBeenCalledWith('/results/somebody/recommendations?topic=math', expect.anything())
  })

  it('says so when a small topic cannot come near the target', async () => {
    const spread = recs('meet-in-the-middle', [problem('7A', 'Far One', { percent: 30 })], { scattered: true })
    render(<TopicIsland initial={initial} fetchImpl={answering({ recs: spread, dismissed: 0 })} navigate={vi.fn()} />)
    fireEvent.click(screen.getByRole('link', { name: 'fft' }))
    await screen.findByText('Far One')
    expect(document.body.textContent).toContain('Few problems in meet-in-the-middle come near 50% for you')
  })

  it("says whose target a topic's list is aiming at", async () => {
    const own = recs('dp', [problem('9A', 'A DP Problem')], { own_target: true, target: 55 })
    render(<TopicIsland initial={initial} fetchImpl={answering({ recs: own, dismissed: 0 })} navigate={vi.fn()} />)
    fireEvent.click(screen.getByRole('link', { name: 'dp' }))
    await screen.findByText('A DP Problem')
    expect(document.body.textContent).toContain('This is dp’s own target')
    expect(document.body.textContent).toContain('Aiming at 55%')
  })
})

describe('a practice plan', () => {
  it('a settled problem shows how, and only the rest keep their buttons', () => {
    const { container } = drawn(recs(null, [
      problem('1A', 'Solved One', { solved: true }),
      problem('2A', 'Pressed One', { outcome: 'too_hard' }),
      problem('3A', 'Open One'),
    ], { plan: { id: 7, started_at: '2026-09-27T10:00:00Z', size: 3, settled: 2, solved: 1, complete: false } }))
    const row = (name) => screen.getByText(name).closest('tr')
    expect(row('Solved One').textContent).toContain('✓ solved')
    expect(row('Pressed One').textContent).toContain('marked too hard')
    expect(row('Solved One').className).toBe('settled')
    expect(row('Open One').className).toBe('')
    // One form of verdict buttons: the open row's.
    expect(container.querySelectorAll('.verdict-form').length).toBe(1)
    expect(row('Open One').querySelector('.verdict-form')).toBeTruthy()
    expect(document.body.textContent).toContain('2 of 3 done, 1 solved')
  })

  it('swapping names the plan it ends, and the list it is on', () => {
    const { container } = drawn(recs('dp', [problem('9A', 'A DP Problem')]))
    const form = container.querySelector('.plan-next')
    expect(form.getAttribute('action')).toBe('/results/somebody/plan')
    expect(form.querySelector('input[name="plan"]').value).toBe('7')
    expect(form.querySelector('input[name="topic"]').value).toBe('dp')
    expect(screen.getByRole('button', { name: 'Swap the five' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Next five' })).toBeNull()
  })

  it('a finished plan offers the next five', () => {
    drawn(recs(null, [problem('1A', 'Done One', { solved: true })],
               { plan: { id: 8, started_at: '2026-09-27T10:00:00Z', size: 1, settled: 1, solved: 1, complete: true } }))
    expect(screen.getByRole('button', { name: 'Next five' }).className).toBe('primary')
    expect(document.body.textContent).toContain('1 of 1 done, 1 solved')
  })

  it('says where the next plan will aim once a press has moved the target', () => {
    drawn(recs(null, [problem('1A', 'One')], { target: 70, next_target: 65 }))
    expect(document.body.textContent).toContain('Your next five will aim at 65%.')
    expect(document.body.textContent).toContain('Aiming at 70%')
  })

  it('a marked row can take back its answer alone, and says which it was', () => {
    const { container } = drawn(recs(null, [
      problem('1A', 'Pressed One', { outcome: 'too_hard' }),
      problem('2A', 'Skipped One', { outcome: 'skip' }),
      problem('3A', 'Open One'),
    ]))
    const row = (name) => screen.getByText(name).closest('tr')
    const undo = row('Pressed One').querySelector('form')
    expect(undo.getAttribute('action')).toBe('/results/somebody/undo')
    expect(undo.querySelector('input[name="problem"]').value).toBe('1A')
    expect(row('Skipped One').textContent).toContain('skipped')
    expect(row('Open One').querySelector('button[value="skip"]')).toBeTruthy()
    expect(container.querySelectorAll('.verdict-form').length).toBe(1)
  })

  it('says when the plan began, in words', () => {
    drawn(recs(null, [problem('1A', 'One')]))
    expect(document.body.textContent).toContain('plan started just now')
  })

  it('says nothing about the next plan while the target has not moved', () => {
    drawn(recs(null, [problem('1A', 'One')]))
    expect(document.body.textContent).not.toContain('Your next five')
  })

  // A press reloads the page at an address naming the row, or the list
  // (web.row_anchor, web.LIST_ANCHOR). After a topic has been chosen the
  // component draws the list, so it carries the same ids as the template.
  it('carries the ids a press comes back to', () => {
    const { container } = drawn(recs('dp', [problem('9A', 'Open One'), problem('8B', 'Pressed One', { outcome: 'skip' })]))
    expect(container.querySelector('section.recs').id).toBe('next')
    expect(screen.getByText('Open One').closest('tr').id).toBe('p-9A')
    expect(screen.getByText('Pressed One').closest('tr').id).toBe('p-8B')
  })

  // The component replaces the rows the browser scrolled to on arrival, so
  // it scrolls back to the one the address names, once, when it first draws.
  it('goes back to the row the address names after replacing it', () => {
    const scrolled = []
    const original = Element.prototype.scrollIntoView
    Element.prototype.scrollIntoView = function () { scrolled.push(this.id) }
    window.history.replaceState(null, '', '/results/somebody#p-8B')
    try {
      drawn(recs(null, [problem('9A', 'Open One'), problem('8B', 'Pressed One', { outcome: 'skip' })]))
      expect(scrolled).toEqual(['p-8B'])
    } finally {
      Element.prototype.scrollIntoView = original
      window.history.replaceState(null, '', '/')
    }
  })

  // The review of 2026-09-28: one line above the five, and everything that
  // explains them under the table, in one group.
  it('says the target and the plan on one line above the table, and explains the numbers under it', () => {
    const { container } = drawn(recs(null, [problem('1A', 'One')], { target: 52 }))
    const status = container.querySelector('.recs-status')
    expect(status.textContent.replace(/\s+/g, ' ')).toContain('Aiming at 52% · 0 of 1 done, 0 solved · plan started just now')
    const table = container.querySelector('.rec-table')
    const notes = container.querySelector('.notes')
    // The status line comes before the table, the notes after it.
    expect(status.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(table.compareDocumentPosition(notes) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(notes.textContent).toContain('Rating is Codeforces’ own, the same for everybody. Chance is yours')
  })

  it("a topic that has no target of its own says it follows the overall one, not that they are equal", () => {
    drawn(recs('dp', [problem('9A', 'One')], { own_target: false, target: 55, overall_target: 52 }))
    expect(document.body.textContent).toContain('dp follows your overall target until a plan here ends')
    expect(document.body.textContent).not.toContain('The same as your overall target')
  })

  it('every button names its problem to a screen reader, the words shown first', () => {
    drawn(recs(null, [problem('1A', 'Open One'), problem('2A', 'Pressed One', { outcome: 'skip' })]))
    expect(screen.getByRole('button', { name: 'too hard: Open One' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'too easy: Open One' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'skip: Open One' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'undo: Pressed One' })).toBeTruthy()
  })

  it('offers "put back" only for hidden problems that have no undo on screen', () => {
    const list = recs(null, [problem('1A', 'Open One'), problem('2A', 'Pressed One', { outcome: 'skip' })])
    const { unmount } = render(<TopicIsland initial={{ ...initial, recs: list, dismissed: 1 }} fetchImpl={answering({})} navigate={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Put back/ })).toBeNull()
    unmount()
    const second = render(<TopicIsland initial={{ ...initial, recs: list, dismissed: 3 }} fetchImpl={answering({})} navigate={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Put back all 3 problems you hid' })).toBeTruthy()
    second.unmount()
    // Pressed, then solved: no undo on the row, and nothing to put back --
    // a solved problem is never offered again, hidden or not.
    const solved = recs(null, [problem('1A', 'Open One'), problem('2A', 'Solved One', { outcome: 'too_hard', solved: true })])
    render(<TopicIsland initial={{ ...initial, recs: solved, dismissed: 1 }} fetchImpl={answering({})} navigate={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Put back/ })).toBeNull()
  })

  it('scrolls nowhere when the address names nothing', () => {
    const scrolled = []
    const original = Element.prototype.scrollIntoView
    Element.prototype.scrollIntoView = function () { scrolled.push(this.id) }
    try {
      drawn(recs(null, [problem('9A', 'Open One')]))
      expect(scrolled).toEqual([])
    } finally {
      Element.prototype.scrollIntoView = original
    }
  })
})

// ADR 0030: the buttons on the five are sent without a reload, and the
// server's answer -- the list's five, as data -- is drawn in place.
describe('a press without a reload', () => {
  // A fetch that answers like web.five_as_data: JSON, with its type said.
  function answeringData(body) {
    return vi.fn(async () => ({
      ok: true, status: 200,
      headers: { get: (name) => (name.toLowerCase() === 'content-type' ? 'application/json' : null) },
      json: async () => body,
    }))
  }
  // Draw `list` with the network and the ordinary submission stood in for.
  function pressable(list, fetchImpl, { dismissed = 0 } = {}) {
    const submit = vi.fn()
    const view = render(<TopicIsland initial={{ ...initial, recs: list, dismissed }} fetchImpl={fetchImpl}
                                     navigate={vi.fn()} submit={submit} />)
    return { ...view, submit }
  }
  const sent = (fetchImpl) => {
    const [address, options] = fetchImpl.mock.calls[0]
    return { address, options, fields: Object.fromEntries(options.body.entries()) }
  }

  it('sends the press, with the button pressed, and draws the answer in place', async () => {
    const after = recs(null, [problem('1A', 'Open One', { outcome: 'too_hard' }), problem('2A', 'Other One')])
    const fetchImpl = answeringData({ recs: after, dismissed: 1 })
    const { submit } = pressable(recs(null, [problem('1A', 'Open One'), problem('2A', 'Other One')]), fetchImpl)

    fireEvent.click(screen.getByRole('button', { name: 'too hard: Open One' }))

    await screen.findByRole('button', { name: 'undo: Open One' })
    const { address, options, fields } = sent(fetchImpl)
    expect(address).toBe('/results/somebody/feedback')
    expect(options.method).toBe('POST')
    expect(options.headers.Accept).toBe('application/json')
    expect(fields).toEqual({ problem: '1A', verdict: 'too_hard' })
    expect(screen.getByText('Open One').closest('tr').textContent).toContain('marked too hard')
    expect(submit).not.toHaveBeenCalled()
  })

  it('tells a screen reader what changed, and puts the keyboard on the button that took its place', async () => {
    const after = recs(null, [problem('1A', 'Open One', { outcome: 'skip' })])
    const { container } = pressable(recs(null, [problem('1A', 'Open One')]), answeringData({ recs: after, dismissed: 1 }))
    fireEvent.click(screen.getByRole('button', { name: 'skip: Open One' }))
    await screen.findByRole('button', { name: 'undo: Open One' })
    expect(container.querySelector('.recs [role="status"]').textContent).toBe('Open One: skipped.')
    await waitFor(() => expect(document.activeElement.getAttribute('aria-label')).toBe('undo: Open One'))
  })

  it('undo takes the row back, and the keyboard lands on its first button', async () => {
    const after = recs(null, [problem('1A', 'Pressed One')])
    const fetchImpl = answeringData({ recs: after, dismissed: 0 })
    const { container } = pressable(recs(null, [problem('1A', 'Pressed One', { outcome: 'too_easy' })]), fetchImpl, { dismissed: 1 })
    fireEvent.click(screen.getByRole('button', { name: 'undo: Pressed One' }))
    await screen.findByRole('button', { name: 'too hard: Pressed One' })
    expect(sent(fetchImpl).address).toBe('/results/somebody/undo')
    expect(sent(fetchImpl).fields).toEqual({ problem: '1A' })
    expect(container.querySelector('.recs [role="status"]').textContent).toBe('Pressed One: back in the plan.')
    await waitFor(() => expect(document.activeElement.getAttribute('aria-label')).toBe('too hard: Pressed One'))
  })

  it('a press on a topic list names the list it was made on', async () => {
    const list = recs('dp', [problem('9A', 'A DP Problem')])
    const fetchImpl = answeringData({ recs: recs('dp', [problem('9A', 'A DP Problem', { outcome: 'too_easy' })]), dismissed: 1 })
    pressable(list, fetchImpl)
    fireEvent.click(screen.getByRole('button', { name: 'too easy: A DP Problem' }))
    await screen.findByRole('button', { name: 'undo: A DP Problem' })
    expect(sent(fetchImpl).fields).toEqual({ problem: '9A', topic: 'dp', verdict: 'too_easy' })
  })

  it('"put back" is sent the same way, and the keyboard goes to the heading when the button has gone', async () => {
    const list = recs(null, [problem('1A', 'Open One')])
    const fetchImpl = answeringData({ recs: list, dismissed: 0 })
    const { container } = pressable(list, fetchImpl, { dismissed: 3 })
    fireEvent.click(screen.getByRole('button', { name: 'Put back all 3 problems you hid' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: /Put back/ })).toBeNull())
    expect(sent(fetchImpl).address).toBe('/results/somebody/restore')
    expect(container.querySelector('.recs [role="status"]').textContent).toBe('The problems you hid are back.')
    await waitFor(() => expect(document.activeElement.textContent).toBe('Next'))
  })

  it('anything but the five coming back sends the form the ordinary way, with the button pressed', async () => {
    const page = vi.fn(async () => ({ ok: true, status: 200, headers: { get: () => 'text/html; charset=utf-8' }, json: async () => ({}) }))
    const { submit } = pressable(recs(null, [problem('1A', 'Open One')]), page)
    fireEvent.click(screen.getByRole('button', { name: 'too easy: Open One' }))
    await waitFor(() => expect(submit).toHaveBeenCalledTimes(1))
    const [form, pressed] = submit.mock.calls[0]
    expect(form.getAttribute('action')).toBe('/results/somebody/feedback')
    expect(pressed.value).toBe('too_easy')

    cleanup()
    const offline = vi.fn(async () => { throw new TypeError('Failed to fetch') })
    const second = pressable(recs(null, [problem('1A', 'Open One')]), offline)
    fireEvent.click(screen.getByRole('button', { name: 'skip: Open One' }))
    await waitFor(() => expect(second.submit).toHaveBeenCalledTimes(1))
  })

  it('the ordinary way carries the pressed button, which form.submit() would leave out', async () => {
    const page = vi.fn(async () => ({ ok: false, status: 500, headers: { get: () => 'text/html' }, json: async () => ({}) }))
    const original = HTMLFormElement.prototype.submit
    const submitted = []
    HTMLFormElement.prototype.submit = function () { submitted.push(this) }
    try {
      render(<TopicIsland initial={{ ...initial, recs: recs(null, [problem('1A', 'Open One')]) }} fetchImpl={page} navigate={vi.fn()} />)
      fireEvent.click(screen.getByRole('button', { name: 'too hard: Open One' }))
      await waitFor(() => expect(submitted.length).toBe(1))
      expect(submitted[0].querySelector('input[type="hidden"][name="verdict"]').value).toBe('too_hard')
    } finally {
      HTMLFormElement.prototype.submit = original
    }
  })

  it('a second press while the first is on its way is not sent', async () => {
    let answer
    const fetchImpl = vi.fn(() => new Promise((resolve) => { answer = resolve }))
    pressable(recs(null, [problem('1A', 'Open One'), problem('2A', 'Other One')]), fetchImpl)
    fireEvent.click(screen.getByRole('button', { name: 'too hard: Open One' }))
    fireEvent.click(screen.getByRole('button', { name: 'too hard: Other One' }))
    expect(fetchImpl).toHaveBeenCalledTimes(1)
    answer({ ok: false, status: 500, headers: { get: () => '' }, json: async () => ({}) })
  })

  it('ending the plan still reloads the page: it changes more than the five', () => {
    const fetchImpl = answeringData({})
    const { container } = pressable(recs(null, [problem('1A', 'Open One')]), fetchImpl)
    fireEvent.submit(container.querySelector('.plan-next'))
    expect(fetchImpl).not.toHaveBeenCalled()
  })
})
