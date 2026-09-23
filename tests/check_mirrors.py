"""Does a Div. 2 history reference problems the problemset lists under a
different id? Read-only; three API calls, spaced past the rate limit.

Not part of tests/run.py: it talks to Codeforces, and it prints a report
rather than passing or failing. Run it by hand.
"""

import collections
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://codeforces.com/api"


def get(method, **params):
    query = urllib.parse.urlencode(params)
    url = f"{API}/{method}" + (f"?{query}" if query else "")
    try:
        with urllib.request.urlopen(url, timeout=90) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        # Codeforces explains a 400 in the response body -- same lesson as
        # api_client.py. Without this all you ever see is "Bad Request".
        payload = json.loads(exc.read())
    if payload["status"] != "OK":
        sys.exit(f"API refused {method} {params}: {payload.get('comment')}")
    return payload["result"]


def make_id(p):
    if "contestId" in p:
        return f"{p['contestId']}{p['index']}"
    return f"{p.get('problemsetName')}{p['index']}"


problems = get("problemset.problems")["problems"]
listed = {make_id(p) for p in problems}
by_name = collections.defaultdict(list)
for p in problems:
    by_name[p["name"]].append(make_id(p))

# [A] The mechanism, on one round. The problemset lists "NEKO's Maze Game"
# only as 1292A; ask contest 1293 what it calls its own problems.
time.sleep(2.5)
# Codeforces serves non-gym standings to anonymous callers only with no
# paging parameters at all -- the whole table or nothing.
standings = get("contest.standings", contestId=1293)
print(f"[A] contest 1293: {standings['contest']['name']}")
for p in standings["problems"]:
    pid = make_id(p)
    if pid in listed:
        status = "listed in problemset"
    else:
        status = f"NOT in problemset -- listed there as {[x for x in by_name.get(p['name'], []) if x != pid]}"
    print(f"      {pid:<6} {p['name']:<30} {status}")

# [B] The scale, on one real Div. 2 participant's whole history: someone in
# the top tenth, so an active account with a long history. Handle not printed.
rows = standings["rows"]
handle = rows[len(rows) // 10]["party"]["members"][0]["handle"]
time.sleep(2.5)
subs = get("user.status", handle=handle)

names = {}
solved = set()
for s in subs:
    p = s["problem"]
    cid = p.get("contestId")
    if cid is None or cid >= 100000:
        continue  # acmsguru or gym: never in the main problemset anyway
    pid = make_id(p)
    names[pid] = p["name"]
    if s.get("verdict") == "OK":
        solved.add(pid)

unlisted = {pid for pid in names if pid not in listed}
listed_elsewhere = {pid for pid in unlisted if by_name.get(names[pid])}

print(f"\n[B] one Div. 2 participant of contest 1293, full history ({len(subs)} submissions)")
print(f"      distinct non-gym problem ids:              {len(names)}")
print(f"      ids not in problemset.problems:            {len(unlisted)}")
print(f"      ...where the problemset has that name:     {len(listed_elsewhere)}")
print(f"      solved problems stored under unlisted ids: {len(solved & unlisted)} of {len(solved)}")
for pid in sorted(listed_elsewhere)[:6]:
    print(f"      {pid:<6} {names[pid]:<30} problemset: {by_name[names[pid]]}")
