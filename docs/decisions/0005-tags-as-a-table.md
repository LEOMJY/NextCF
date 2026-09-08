# 0005 — Problem tags get their own table

**Date:** 2026-09-07
**Status:** accepted

## Context

§6 listed four tables and stored a problem's tags as `tags text — comma
separated for now`. The "for now" was doing real work in that sentence: a
column holding a list rather than a single value is the first thing relational
design tells you not to do, and the sentence knew it.

The consequences of the comma string are concrete. The column cannot be
indexed, so every topic query scans the table. Matching is substring matching,
so a search for `string` also matches `string suffix structures`. Both are
avoidable with delimiters and care, and neither is the real argument.

The real argument is that **topics are the axis the entire product works
along**. §1 promises a per-topic breakdown and calls it useful on its own. §3
says the differentiator is knowing you are fine at greedy and weak at trees.
`model.py` at v0.6 has "every submission by this user on problems tagged X" as
its central query. Making the central query of the model a string-matching
exercise is the actual cost, not the microseconds.

## Decision

A fifth table, `problem_tags`, one row per (problem, tag) pair. Roughly 10,000
problems at about three tags each is on the order of 30,000 rows, indexed on
both columns. `problems.tags` is removed.

## Alternatives

**Keep the comma-separated column until the model needs otherwise.** This was
the position §6 already held, and it is defensible, because the migration is
unusually cheap: every tag string is already stored, so building the table
later is one script over rows already on disk — no re-fetch of the API, no data
loss, no risk of getting it wrong. The bill for deferring is rewriting the
queries in `model.py` and `evaluate.py`, not repairing data.

Rejected on the grounds that the cost of doing it now is one `CREATE TABLE` and
an insert loop, in the same week the schema is being written for the first
time, whereas the cost of doing it later falls in the same week the first real
model is being fitted — which is a much worse week to be rewriting queries.

**Store tags as JSON in the column** and use SQLite's JSON functions. Rejected:
it is the same shape of problem with more syntax, and it makes the schema
depend on a SQLite feature for something a table does plainly.

## Consequences

- §6 now describes five tables, not four. The sentence "everything else is
  computed on demand, not stored, so there is only one copy of the truth" is
  unchanged and is in fact better served: a tag is now stored once as a value
  rather than embedded in a string.
- Reading a problem with its tags is now a join. That is the normal cost of
  normalising, and it is one query.
- Tag counts per user — the input to the topic breakdown chart at v0.4 — become
  a `GROUP BY` rather than parsing strings in Python. That chart is the highest
  return item in §7.1, so the query behind it being clean is worth something.
- Codeforces tags are free text and change over time. A sync that re-fetches a
  problem must replace that problem's tag rows rather than adding to them, or
  renamed tags accumulate forever.
