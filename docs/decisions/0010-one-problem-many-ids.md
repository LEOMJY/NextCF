# 0010 — One problem, many ids: an alias map built from stored rows

**Date:** 2026-09-15
**Status:** accepted

## Context

§12 has asked since 09-11 what to do about a problem that carries more than one
id. When a Div. 1 and a Div. 2 round run together they share problems, and each
shared problem gets an id in both contests. `problemset.problems` lists only one
of them; a Div. 2 contestant's submissions carry the other. The question was due
at v0.4, before the first recommendation ships.

Measured against the collected dataset on 2026-09-15:

| | |
|---|---|
| non-gym ids stored in `problems` | 13,208 |
| of those, not listed in the problemset | **1,807** |
| — with a contest id | 1,680 |
| — acmsguru | 127 |
| submissions to an unlisted id | 146,869 (3.8% of all) |
| distinct (user, problem) solves on one | 48,526 |
| users who touched at least one | 3,528 of 4,000 |

**The cost is larger than §12 described, and lands in a second place.** §12 named
one consequence: a recommender drawing from the problemset would offer users
problems they have already solved. There is another, and it hits the per-topic
breakdown rather than the recommendations.

**Codeforces tags the two copies differently.**

```
1292A  NEKO's Maze Game  1400  data structures, dsu, implementation    in the problemset
1293C  NEKO's Maze Game  1400  constructive algorithms, implementation     not listed
```

Three ids can disagree three ways. "Marcin and Training Camp", rated 1700, is
`1210B` in the problemset with two tags, `1229A` with three, and `1230D` with
four.

So the same problem is counted under different topics depending on which
division its solver was in. A Div. 2 contestant who solves it is recorded as
having done constructive algorithms; a Div. 1 contestant, as having done data
structures and dsu.

This is not a handful of problems. Of the 1,527 pairs the map ends up holding,
**1,142 — three in four — are tagged differently on the two sides**, and 34,856
solves in the dataset sit on the wrong side of one. It has a direction, too:
the listed copy is the lower contest id in 1,493 of the 1,527 pairs, which is
the Div. 1 half of a pair, so the misattributed solves are the Div. 2 ones, and
§2 says the audience is mostly Div. 2. Per-topic solve counts are v0.4's first
deliverable, which moves this from a recommendation problem to a measurement
problem.

One suspicion was checked and dismissed. `save_problemset` and `save_sync` share
one writer, which replaces a problem's tags every time it is seen, so a later
sync could in principle have overwritten good problemset tags with worse ones.
It did not: all 11,401 problemset problems are stored, and every one has tags
identical to the live problemset. The two copies genuinely differ at the source.

**The database could not answer the question at all.** Nothing in `problems`
records whether an id is in the problemset — the shared writer does not mark it.
The "11,401 are the problemset" figure in the 09-15 devlog entry came from
`collect.py`'s printed output, not from a query. Without that fact stored,
neither a mapping nor a recommendation pool can be built, and §9's number cannot
be recomputed from the file alone, which ADR 0007 requires.

### Two ways to build the mapping

Both use only rows already stored, which is what §6 promised when it said that
storing the id each submission actually used is what keeps this fixable.

**A — simultaneous contests, then name.** A `CONTESTANT` submission can only be
made while its contest is running, so the earliest such submission per contest
brackets when that contest ran. Contests whose first contestant submission falls
within twenty minutes of another's were run together; inside such a cluster,
problems sharing a name are the same problem. 325 clusters, 1,251 of 1,680
mapped — **74%**.

**B — name and rating, with exactly one candidate.** Group every stored non-gym
problem by (name, rating); if the group holds exactly one problemset problem,
every other id in it is an alias of it. 1,527 of 1,680 — **91%**.

| | |
|---|---|
| ids where both methods fire | 1,239 |
| of those, the two methods agree | **1,239 — all of them** |
| A ∪ B | 1,539 (92%) |
| left unmapped | 141 |
| — in a contest the problemset omits entirely | 134 |
| — in a contest the problemset does list | 7 |

B's failure mode is a false match: two unrelated problems sharing a name and a
rating. The base rate is low and measurable — of 11,044 (name, rating) pairs
inside the problemset, 56 are shared by more than one problem, the worst being
three problems called "Game" rated 800. B declines to guess whenever a group
holds more than one problemset problem, so those 56 produce no mapping rather
than a wrong one.

### What the mapping buys

3,360 of the 4,000 users have at least one solve that is invisible without it —
median 6 per affected user, mean 13, largest 362; 2,025 users have five or more.
Those are the problems that would otherwise be recommended to people who have
already solved them.

## Decision

**1. `problems.in_problemset`**, an integer column, 1 for an id the problemset
lists and 0 otherwise. Set by `save_problemset`; never cleared by `save_sync`.

**2. `problem_aliases`**, a table of (alias id → canonical id), where the
canonical id is always a problemset member. Built by a command, stored, not
recomputed on read.

**3. Method B builds it.** B alone, not A and not the union.

**4. Method A becomes a check, not production code.** It runs against the
dataset and asserts that A and B never disagree. A disagreement means the data
moved or a method is wrong, and it fails loudly instead of being discovered
inside §9's number.

**5. Per-topic counts read the canonical problem's tags.** An alias's own tags
stay stored and stop being counted.

**6. The recommendation pool is problemset members with a rating** — 11,102 of
the 11,401. Gym and acmsguru are outside it: `problemset.problems` returns no
acmsguru entries at all, and gym problems have no rating.

## Alternatives

**Do not map; exclude every unlisted id.** The cheapest answer, and it is what
the code does today by accident. Rejected on the measurement above: it discards
48,526 solves, and it leaves 3,360 of 4,000 users liable to be recommended a
problem they have already solved. It also does not fix the tag bias at all — a
Div. 2 solve counted under the wrong topic is not an unlisted-id problem. It is
counted, just under the wrong heading.

**Method A alone.** Rejected for less coverage (74% against 91%) at more code.
Its real value is that it is *independent* of B — it uses submission times and
contest structure where B uses names and ratings — which is exactly what makes
it a good check and a redundant recommender.

**A ∪ B.** 92% against 91%. One extra percentage point of coverage in exchange
for a second implementation carried in production forever. The 88 ids it adds
are not worth it, and every one of them stays visible in the check's output if
it ever turns out they are.

**Name matching alone.** 4,027 non-gym rows share a name with another row, more
than twice the 1,807 that are actually unlisted, so name alone over-matches
badly. §12 already warned this, naming seven different problems called
"Elections"; the measurement agrees with the warning.

**Compute the mapping on every read instead of storing it.** §6 says derived
data is not stored, and this is derived data. Rejected on two counts. The
derivation depends on the *whole* problems table, so it cannot be computed for
one visitor's page without scanning everything. And §9 has to be reproducible
from the file: a mapping recomputed against a problemset fetched later is a
different mapping.

**Fetch a mapping from Codeforces.** There is no endpoint for it. `contest.list`
would supply real contest start times instead of times inferred from
submissions, which would sharpen method A — but A is not the method being
shipped, and taking on an external dependency to improve a check is the wrong
trade.

## Consequences

- **A schema change.** `ALTER TABLE ... ADD COLUMN` rewrites no rows, so the
  680 MB dataset takes it without being rebuilt. Every existing row keeps the
  default of 0 until a problemset fetch marks the members — and all 11,401 of
  them are already stored, so the fetch marks rather than inserts.
- **`jobs.kind` keeps `"collect"` after all.** ADR 0007 left removing it for
  "the next schema change so one rebuild covers both". This was meant to be
  that change, and it is not, because the premise did not survive contact with
  the work: `ALTER TABLE ... ADD COLUMN` rewrites nothing, so there is no
  rebuild here to share. Removing a value from a CHECK still costs a table
  rebuild of its own — rename, recreate, copy, drop — for a value nothing
  writes. Doing it would mean either duplicating the table's definition in
  Python or performing string surgery on the definition SQLite stores, both to
  tidy something with no effect on behaviour. It waits for a change that
  rebuilds a table for a reason. The alternative — changing `schema.sql` and
  not migrating — was rejected outright: a new database would then disagree
  with every existing one, which is worse than either state alone.
- **`web.py` must fetch the problemset.** Nothing but `collect.py` ever called
  `save_problemset`, so `nextcf.db` on the server knows only the problems its
  visitors have submitted to. A recommender there would have had an empty
  candidate pool and could only have offered problems the visitor had already
  attempted. The free instance wipes the file on every spin-down (§7), so the
  fetch happens at startup, and it is one request.
- **The alias map has to exist on the server too.** It is derived from the
  problemset and the problems table, both of which the server will now have, so
  it is rebuilt there after the problemset fetch rather than shipped from the
  author's machine. This is a smaller version of §12's open question about
  moving what the model learned to the server, and it does not settle that one.
- **141 ids stay unmapped**, 134 of them in contests the problemset omits
  entirely — April Fools rounds, unrated rounds, contests since removed. Those
  are not recommendable under any scheme, so the practical remainder is 7.
- **The mapping is a snapshot, like the ratings beside it.** Codeforces can
  rename a problem or change a rating, and the map would then be built
  differently. It is rebuilt whenever the problemset is fetched.
- **Nothing is deleted.** Alias rows keep their own ids, tags and submissions.
  The map adds a way to read them together; it does not merge them. A merge
  could not be undone, and the per-copy tag difference is the evidence that the
  map is working.
