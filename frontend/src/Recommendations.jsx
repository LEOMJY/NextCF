// The recommendations section: the five, and every sentence around them.
//
// The same section templates/results.html draws, in the same words and with
// the same classes, from the same data (web.recommendation_view). ADR 0025
// accepts that there are two renderings -- the template's, which every
// visitor gets first, and this one, after a topic is chosen -- so this file
// follows the template branch for branch, and the tests check the sentences
// that carry meaning. When one changes, the other has to.

const nbsp = ' '

// One problem's row: the link, the "less evidence" note on a filled row,
// the two verdict buttons as a real form, the rating and the chance.
function ProblemRow({ problem, topic, urls }) {
  return (
    <tr>
      <td>
        <a href={problem.url}>{problem.name}</a>
        {problem.thin && (
          <span className="thin-note">
            few people near your rating have tried this one, so its chance rests on less evidence
          </span>
        )}
        {/* A form and a POST, exactly as the template's: pressing reloads the
            page on the same list, which is what the server redirects to. */}
        <form className="verdict-form" method="post" action={urls.feedback}>
          <input type="hidden" name="problem" value={problem.id} />
          {topic && <input type="hidden" name="topic" value={topic} />}
          <button type="submit" name="verdict" value="too_hard">too hard</button>
          <button type="submit" name="verdict" value="too_easy">too easy</button>
        </form>
      </td>
      <td className="num rating">{problem.rating}</td>
      <td className="num chance">{problem.percent}%</td>
    </tr>
  )
}

// The sentence that says what the number is, and the notes under it.
function Notes({ recs, urls }) {
  const where = recs.topic ? `in ${recs.topic}` : 'on Codeforces'
  return (
    <>
      {recs.source === 'topic' ? (
        <>
          <p className="meta">
            Chosen for you: the chance your first submission is accepted, worked
            out from your own history, how 4,000 other users actually did on
            each problem, and how hard its topics are. Aiming at {recs.target}%.{' '}
            <a href={urls.how}>How this works</a>
          </p>
          {recs.topic && (
            <p className="footnote">
              {recs.own_target
                ? <>This is {recs.topic}’s own target: “too hard” and “too easy” here move it, and nothing else.</>
                : <>The same as your overall target, until you press “too hard” or “too easy” here: then {recs.topic} keeps a target of its own.</>}
            </p>
          )}
          {recs.extrapolated && !recs.looked_up_at && (
            <p className="footnote">
              Your rating is outside the range the model learned from, so these
              chances are an extrapolation and less reliable than they look.
            </p>
          )}
          {recs.unrated && (
            <p className="footnote">
              You have no rating yet, so these chances start from {recs.computed}{nbsp}— the
              starting point that predicted best for people who had not yet entered a rated
              contest{nbsp}— and move with how your own practice has gone. They are less
              certain than a rated account’s.
            </p>
          )}
          {recs.hidden && (
            <p className="footnote">
              Codeforces shows you {recs.shown} but computes with {recs.computed}: for a new
              account’s first six rated contests it holds part of the rating back and returns
              it contest by contest. These chances use {recs.computed}.
            </p>
          )}
        </>
      ) : (
        <p className="meta">
          Problems rated around {recs.centre}, where{' '}
          {recs.event === 'first_try'
            ? <>a first submission from somebody at your rating is accepted about {recs.target}% of the time.</>
            : <>somebody at your rating solves them in the end about {recs.target}% of the time.</>}{' '}
          Rating only, so everybody at your rating is shown these five.
        </p>
      )}

      {recs.looked_up_at && (
        <p className="footnote">
          Your rating is outside what the 4,000 users behind these numbers were rated, so
          problems are chosen from ones people rated around {recs.looked_up_at} have actually
          tried{recs.extrapolated ? ', and the chances are an extrapolation, less reliable than they look' : ''}.
        </p>
      )}
      {recs.unguarded && (
        <p className="footnote">
          You have solved most of what people near your rating have tried, so these include
          problems few of them attempted. The chances on those rest on less evidence.
        </p>
      )}

      {recs.reach === 'easiest' ? (
        <p className="footnote">
          Nothing left {where} is as easy as {recs.target}% for you: these are the easiest
          problems there are, so “too hard” can hide one but cannot find anything easier.
        </p>
      ) : recs.reach === 'hardest' ? (
        <p className="footnote">
          Nothing left {where} is as hard as {recs.target}% for you: these are the hardest
          problems there are, so “too easy” can hide one but cannot find anything harder.
        </p>
      ) : recs.at_end === 'easiest' ? (
        <p className="footnote">
          {recs.target}% is as easy as the target goes. “Too hard” still hides a problem, and
          no longer moves the target.
        </p>
      ) : recs.at_end === 'hardest' ? (
        <p className="footnote">
          {recs.target}% is as hard as the target goes. “Too easy” still hides a problem, and
          no longer moves the target.
        </p>
      ) : null}
      {recs.scattered && (
        <p className="footnote">
          Few problems {recs.topic ? `in ${recs.topic}` : 'left'} come near {recs.target}% for
          you, so some of these are well off it: the chance on each says how far.
        </p>
      )}
    </>
  )
}

// Why there is no list, in the state's own words.
function Empty({ recs, dismissed, urls, onChoose, handle }) {
  if (recs.state === 'unrated') {
    return (
      <p className="meta">
        Codeforces has no rating for {handle} yet, and the rating-only recommender in use right
        now needs one, so there is nothing to base a recommendation on until one exists.
      </p>
    )
  }
  if (recs.state === 'not_ready') {
    return <p className="meta">The problem list is still loading. Reload in a few seconds.</p>
  }
  if (recs.topic) {
    return (
      <p className="meta">
        Nothing left to recommend in {recs.topic}: every rated problem tagged it is one you have
        solved{dismissed ? ' or hidden' : ''}.{' '}
        <a href={urls.results} onClick={(event) => onChoose(event, null)}>All topics</a>
      </p>
    )
  }
  if (dismissed) {
    return (
      <p className="meta">
        Every rated problem left for you is one you have hidden. Put some back to see
        recommendations again.
      </p>
    )
  }
  return (
    <p className="meta">
      You have solved every rated problem on Codeforces. There is nothing left to recommend.
    </p>
  )
}

export default function Recommendations({ handle, recs, dismissed, dismissalsKept, urls, busy, heading, onChoose }) {
  return (
    // aria-busy tells assistive technology the section is being replaced, so
    // it waits for the new list rather than reading a half-changed one.
    <section className="recs" aria-busy={busy}>
      <h2 ref={heading} tabIndex={-1}>Next{recs.topic ? ` in ${recs.topic}` : ''}</h2>

      {recs.topic && (
        <p className="meta topic-scope">
          Only problems tagged <strong>{recs.topic}</strong>.{' '}
          <a href={urls.results} onClick={(event) => onChoose(event, null)}>All topics</a>
        </p>
      )}

      {recs.state === 'ok' ? (
        <>
          <Notes recs={recs} urls={urls} />
          <table className="rec-table">
            <thead>
              <tr>
                <th>Problem</th>
                <th className="num">Rating</th>
                <th className="num">Chance</th>
              </tr>
            </thead>
            <tbody>
              {recs.problems.map((problem) => (
                <ProblemRow key={problem.id} problem={problem} topic={recs.topic} urls={urls} />
              ))}
            </tbody>
          </table>
        </>
      ) : (
        <Empty recs={recs} dismissed={dismissed} urls={urls} onChoose={onChoose} handle={handle} />
      )}

      {dismissed > 0 && (
        <>
          <form className="restore" method="post" action={urls.restore}>
            {recs.topic && <input type="hidden" name="topic" value={recs.topic} />}
            <button type="submit">
              Put back the {dismissed} problem{dismissed > 1 ? 's' : ''} I hid
            </button>
          </form>
          {dismissed >= dismissalsKept && (
            <p className="footnote">
              Only the latest {dismissalsKept} stay hidden: hiding another brings back the one
              you hid longest ago.
            </p>
          )}
        </>
      )}
    </section>
  )
}
