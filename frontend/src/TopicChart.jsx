// The topic chart: what the visitor has practised, each topic a way to choose
// its five -- ADR 0025.
//
// The same table templates/results.html draws (see web.topic_rows for how
// each bar's width is worked out), with the same classes, so the stylesheet
// draws both alike. Every name is a real link to that topic's page; the
// component only intercepts the click to swap the five in place, and a click
// it does not intercept -- a new tab -- still goes to the right address.

import { pageUrl } from './urls.js'

function TopicLink({ tag, current, urls, onChoose }) {
  return (
    <a
      href={pageUrl(urls, tag)}
      aria-current={tag === current ? 'page' : undefined}
      onClick={(event) => onChoose(event, tag)}
    >
      {tag}
    </a>
  )
}

export default function TopicChart({ topics, otherTopics, totals, current, urls, onChoose }) {
  if (!topics.length && !otherTopics.length) return null
  return (
    <section className="topics">
      <h2>Topics</h2>
      <p className="meta">
        What you have practised. Not yet how good you are at it. Choose a topic to see five
        problems in it.
      </p>

      {topics.length > 0 && (
        <>
          <table>
            <thead>
              <tr>
                <th>Topic</th>
                <th className="num">Solved</th>
                <th className="num">Avg rating</th>
              </tr>
            </thead>
            <tbody>
              {topics.map((t) => (
                // --bar is read by the gradient in style.css: the row's own
                // background is the bar, as in the template.
                <tr key={t.tag} style={{ '--bar': `${t.width}%` }}>
                  <th scope="row" className="topic-name">
                    <TopicLink tag={t.tag} current={current} urls={urls} onChoose={onChoose} />
                  </th>
                  <td className="num">
                    {t.solved}<span className="of">/{t.attempted}</span>
                  </td>
                  <td className="num">
                    {t.mean !== null ? (
                      <>
                        {t.mean}
                        {t.rated_solved !== t.solved && (
                          <span className="of"> ({t.rated_solved} rated)</span>
                        )}
                      </>
                    ) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {/* Folded, as in the template (review of 2026-09-28): the answer
              to a question most visitors never ask, one press away. */}
          <details className="footnote">
            <summary>Why Solved adds up to more than {totals.solved}</summary>
            <p>
              A problem carries about three tags and counts under each, so the Solved column adds
              to more than the {totals.solved} problems solved
              {totals.solved_untagged
                ? `, and ${totals.solved_untagged} solved ${totals.solved_untagged === 1 ? 'problem has' : 'problems have'} no tags at all and appear in no row`
                : ''}
              . Average rating covers the rated problems solved in each topic; topics differ in how
              hard their problems are for everybody, so the averages are not yet comparable between
              rows.
            </p>
          </details>
        </>
      )}

      {/* Folded too, and open when the topic on screen is one of these, so
          its link, marked as the current page, is not hidden. `open` is
          only the starting state: React leaves a fold the visitor opened or
          closed alone until `current` changes. */}
      {otherTopics.length > 0 && (
        <details className="meta other-topics" open={otherTopics.includes(current)}>
          <summary>Not practised yet: {otherTopics.length} topic{otherTopics.length > 1 ? 's' : ''}</summary>
          <p>
            {otherTopics.map((tag, i) => (
              <span key={tag}>
                <TopicLink tag={tag} current={current} urls={urls} onChoose={onChoose} />
                {i < otherTopics.length - 1 ? ', ' : ''}
              </span>
            ))}
          </p>
        </details>
      )}
    </section>
  )
}
