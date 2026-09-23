"""Check the problems.id rule in schema.sql against real Codeforces data.

Read-only. Three public API calls, spaced past the documented one request
per two seconds.

Not part of tests/run.py: it talks to Codeforces, and it prints a report
rather than passing or failing. Run it by hand.
"""

import collections
import json
import re
import sys
import time
import urllib.parse
import urllib.request

API = "https://codeforces.com/api"


def get(method, **params):
    query = urllib.parse.urlencode(params)
    url = f"{API}/{method}" + (f"?{query}" if query else "")
    with urllib.request.urlopen(url, timeout=90) as resp:
        payload = json.loads(resp.read())
    if payload["status"] != "OK":
        sys.exit(f"API refused {method}: {payload.get('comment')}")
    return payload["result"]


def make_id(problem):
    """The rule as written in schema.sql."""
    if "contestId" in problem:
        return f"{problem['contestId']}{problem['index']}"
    return f"{problem.get('problemsetName')}{problem['index']}"


# ------------------------------------------------------------------ problemset
problems = get("problemset.problems")["problems"]
print(f"problemset.problems: {len(problems)} problems\n")

print(f"[1] missing contestId: {sum('contestId' not in p for p in problems)}")

LETTER_FIRST = re.compile(r"^[A-Z][A-Z0-9]*$")
odd = [p for p in problems if not LETTER_FIRST.match(p["index"])]
print(f"[2] index not starting with a capital letter: {len(odd)}")
for p in odd[:5]:
    print(f"      {p.get('contestId')!r} {p['index']!r} {p['name']}")
shapes = collections.Counter(
    re.sub(r"[A-Z]", "L", re.sub(r"[0-9]", "9", p["index"])) for p in problems
)
print(f"    index shapes (L = letter, 9 = digit): {dict(shapes.most_common())}")

ids = [make_id(p) for p in problems]
repeated = [i for i, n in collections.Counter(ids).items() if n > 1]
print(f"[3] ids produced more than once: {len(repeated)} {repeated[:5]}")

# Same problem under two contest ids: Div. 1 and Div. 2 rounds held together
# share problems. Heuristic, not proof: identical name, contest ids at most
# 2 apart, and identical rating and tags.
by_name = collections.defaultdict(list)
for p in problems:
    by_name[p["name"]].append(p)

pairs = [
    (g[i], g[j])
    for g in by_name.values()
    for i in range(len(g))
    for j in range(i + 1, len(g))
]
near = [(a, b) for a, b in pairs if abs(a["contestId"] - b["contestId"]) <= 2]
mirrors = [
    (a, b)
    for a, b in near
    if a.get("rating") == b.get("rating")
    and sorted(a.get("tags", [])) == sorted(b.get("tags", []))
]
far = len(pairs) - len(near)

print(f"[4] pairs of problems with identical names:   {len(pairs)}")
print(f"      contests far apart (unrelated, e.g. 'Game'): {far}")
print(f"      contests <= 2 ids apart:                     {len(near)}")
print(f"      ...and identical rating and tags:            {len(mirrors)}")
involved = {make_id(p) for pair in mirrors for p in pair}
print(
    f"    problems that are one half of a likely mirror: {len(involved)}"
    f" of {len(problems)} ({100 * len(involved) / len(problems):.1f}%)"
)
print("    most recent examples:")
for a, b in sorted(mirrors, key=lambda ab: -max(ab[0]["contestId"], ab[1]["contestId"]))[:6]:
    lo, hi = sorted((a, b), key=lambda p: p["contestId"])
    print(f"      {make_id(lo):>7} = {make_id(hi):<7} {lo['name']}  (rating {lo.get('rating')})")
maze = by_name.get("NEKO's Maze Game", [])
print(f"    'NEKO's Maze Game' appears as: {[make_id(p) for p in maze]}")

# -------------------------------------------------------------------- acmsguru
time.sleep(2.5)
guru = get("problemset.problems", problemsetName="acmsguru")["problems"]
print(f"\n[5] acmsguru problemset: {len(guru)} problems")
print(f"      with a contestId: {sum('contestId' in p for p in guru)}")
if guru:
    print(f"      keys on one problem: {sorted(guru[0].keys())}")
    print(f"      ids under the schema rule: {[make_id(p) for p in guru[:3]]}")

# ------------------------------------------------ what sync.py will actually see
time.sleep(2.5)
subs = get("user.status", handle="tourist")
print(f"\n[6] user.status tourist: {len(subs)} submissions")
print(f"      problem without contestId:     {sum('contestId' not in s['problem'] for s in subs)}")
print(f"      gym (contestId >= 100000):     {sum(s['problem'].get('contestId', 0) >= 100000 for s in subs)}")
print(f"      distinct problem ids:          {len({make_id(s['problem']) for s in subs})}")
print(f"      ids that are half of a mirror: {len({make_id(s['problem']) for s in subs} & involved)}")
