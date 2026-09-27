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
           plan: { id: 7, started_at: '2026-09-27T10:00:00Z', size: problems.length,
                   settled: 0, solved: 0, complete: false },
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
    expect(document.body.textContent).not.toContain('ticked the next time')
  })

  it('says where the next plan will aim once a press has moved the target', () => {
    drawn(recs(null, [problem('1A', 'One')], { target: 70, next_target: 65 }))
    expect(document.body.textContent).toContain('Your next five will aim at 65%.')
    expect(document.body.textContent).toContain('Aiming at 70%')
  })

  it('says nothing about the next plan while the target has not moved', () => {
    drawn(recs(null, [problem('1A', 'One')]))
    expect(document.body.textContent).not.toContain('Your next five')
  })
})
