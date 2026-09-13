"""Bulk collection of the dataset: 2000 Codeforces users, stratified by rating.

Runs on the author's machine, into dataset.db, and never on the server
(ADR 0007). Who is drawn, and why this way: ADR 0009.

Three commands, in the order they are used:

    .venv\\Scripts\\python.exe collect.py draw [--seed N] [--per-stratum N]
        Fetch the list of active rated users, shuffle each rating stratum with
        the seed, and store the whole order. Once per dataset -- a second draw
        is refused.

    .venv\\Scripts\\python.exe collect.py run
        Fetch the problemset, then collect users -- whole history and rating
        changes -- until every stratum has per_stratum of them. Stops cleanly
        on a network failure or Ctrl+C; run it again to carry on.

    .venv\\Scripts\\python.exe collect.py status
        How far it has got, per stratum.

Every request waits for a two-second turn (api_client), and each user takes
two requests, so a full run is a little over two hours. Do not run it while
using the local site: each program keeps its own pace, and together they go
twice as fast as Codeforces allows.
"""

import argparse
import os
import random
import secrets
import sys
import time
import urllib.error
from pathlib import Path

import api_client
import db

HERE = Path(__file__).resolve().parent

# The dataset lives in its own file, never nextcf.db (ADR 0007). Overridable
# from the environment the way db.py's NEXTCF_DB is, so a trial run can go to a
# throwaway file without touching the real dataset.
DATASET_PATH = Path(os.environ.get("NEXTCF_DATASET", HERE / "dataset.db"))

# ADR 0009: ratings 1000-1999 in five strata of 200, 400 users from each.
# These are the defaults for a new draw. Once drawn, the numbers stored in the
# samples table are what run() obeys, so changing these later cannot change a
# dataset already drawn.
RATING_MIN = 1000
RATING_MAX = 1999
STRATUM_WIDTH = 200
PER_STRATUM = 400
STRATA = list(range(RATING_MIN, RATING_MAX + 1, STRATUM_WIDTH))

SOURCE = "user.ratedList activeOnly=true includeRetired=false"


class SampleExists(Exception):
    """Raised by draw() when this dataset already has a sample."""


def stratum_of(rating):
    """The lower bound of the stratum `rating` falls in, or None if outside.

    1000-1199 -> 1000, 1200-1399 -> 1200, ... 1800-1999 -> 1800. Both ends are
    inclusive, which is exactly where an off-by-one would put 1999 nowhere or
    2000 somewhere.
    """
    if rating is None or not RATING_MIN <= rating <= RATING_MAX:
        return None
    return RATING_MIN + (rating - RATING_MIN) // STRATUM_WIDTH * STRATUM_WIDTH


# ------------------------------------------------------------------------ draw

def draw(path, rated_users, seed, per_stratum=PER_STRATUM, fetched_at=None):
    """Shuffle every stratum of `rated_users` with `seed` and store the order.

    `rated_users` is the list from api_client.fetch_rated_list(). Returns the
    new sample's id. Raises SampleExists if this database already has one.

    The draw is split from the fetch so the checks can hand it a list built by
    hand, and so its randomness can be tested without the network.
    """
    db.init_db(path)
    conn = db.connect(path)
    try:
        if db.get_sample(conn) is not None:
            raise SampleExists(
                f"{path} already has a sample. A second draw would change who is "
                "in the dataset; use a new file for a new sample."
            )

        pools = {stratum: [] for stratum in STRATA}
        for user in rated_users:
            stratum = stratum_of(user.get("rating"))
            if stratum is not None:
                pools[stratum].append((user["handle"], user["rating"]))

        # One random generator for the whole draw, seeded once, used on the
        # strata in a fixed order. Same seed, same list -> same order, every
        # time.
        #
        # Each pool is SORTED before it is shuffled. The API does not promise
        # to list users in the same order twice, and shuffling a list that
        # arrived in a different order gives a different result even with the
        # same seed. Sorting first makes the draw depend on who is in the list,
        # not on how the list was ordered.
        rng = random.Random(seed)
        candidates = []
        for stratum in STRATA:
            pool = sorted(pools[stratum], key=lambda user: (user[0].lower(), user[0]))
            rng.shuffle(pool)
            candidates.extend(
                (stratum, position, handle, rating)
                for position, (handle, rating) in enumerate(pool)
            )

        sample_id = db.save_draw(
            conn, seed, SOURCE, fetched_at or db.utc_now(),
            RATING_MIN, RATING_MAX, STRATUM_WIDTH, per_stratum, candidates,
        )

        print(f"sample {sample_id}: seed {seed}, {per_stratum} wanted per stratum")
        for stratum in STRATA:
            print(f"  {stratum}-{stratum + STRATUM_WIDTH - 1}  {len(pools[stratum]):>6} candidates")
        return sample_id
    finally:
        conn.close()


# ------------------------------------------------------------------------- run

def run(path=DATASET_PATH):
    """Collect until every stratum is full, or stop cleanly. Returns an exit code.

    0 -- finished: every stratum has per_stratum users, or has run out of
         candidates (which is reported).
    1 -- stopped by a failure worth a human look. Nothing is half-written, and
         running again carries on from the same place.
    2 -- nothing has been drawn yet.
    """
    db.init_db(path)
    conn = db.connect(path)
    try:
        sample = db.get_sample(conn)
        if sample is None:
            print(f"Nothing drawn yet in {path}. Run: collect.py draw")
            return 2

        # The strata come from the stored sample, not from the constants at
        # the top of this file -- see the comment there.
        strata = list(range(sample["rating_min"], sample["rating_max"] + 1, sample["stratum_width"]))
        wanted = sample["per_stratum"]

        # The problemset first: one request, and it also refreshes problem
        # ratings, which Codeforces assigns days after a contest.
        try:
            problems = api_client.fetch_problemset()["problems"]
        except (urllib.error.URLError, RuntimeError) as exc:
            return _stopped(f"could not fetch the problemset: {exc}")
        print(f"problemset: {db.save_problemset(conn, problems)} problems", flush=True)

        started = time.monotonic()
        collected_this_run = 0
        exhausted = set()

        # ROUND-ROBIN across the strata: one attempt per stratum per round,
        # rather than finishing 1000-1199 before starting 1200-1399. A run
        # stopped after an hour then leaves every stratum about equally full,
        # instead of a dataset of low-rated users only -- which would look
        # like a usable half-sample and be a biased one.
        while True:
            progressed = False
            counts = {row["stratum"]: row["collected"] for row in db.get_strata(conn, sample["id"])}

            for stratum in strata:
                if stratum in exhausted or counts.get(stratum, 0) >= wanted:
                    continue

                candidate = db.next_candidate(conn, sample["id"], stratum)
                if candidate is None:
                    exhausted.add(stratum)
                    print(f"  [{stratum}] ran out of candidates at {counts.get(stratum, 0)} of {wanted}", flush=True)
                    continue

                try:
                    outcome = _collect_one(conn, sample["id"], candidate)
                except (urllib.error.URLError, RuntimeError) as exc:
                    # URLError: the network, after api_client's retries.
                    # RuntimeError: TemporaryFailure after retries, or a refusal
                    # _collect_one could not recognise as "this handle is gone".
                    # Either way a person should look before anything is
                    # skipped for good.
                    return _stopped(f"{candidate['handle']}: {exc}")
                except Exception:
                    # A bug or data this code does not understand. Say who it
                    # was for, then let the traceback through -- skipping the
                    # user would hide the bug, and ADR 0004 means nothing of
                    # theirs was written.
                    print(f"\nUnexpected error while collecting {candidate['handle']}:", file=sys.stderr)
                    raise

                progressed = True
                if outcome is None:
                    print(f"  [{stratum}] {candidate['handle']}: unavailable, next in line takes the place", flush=True)
                    continue

                n_submissions, n_changes = outcome
                collected_this_run += 1
                counts[stratum] = counts.get(stratum, 0) + 1
                remaining = sum(max(0, wanted - counts.get(s, 0)) for s in strata if s not in exhausted)
                per_user = (time.monotonic() - started) / collected_this_run
                print(
                    f"  [{stratum}] {counts[stratum]:>3}/{wanted}  {candidate['handle']:<24}"
                    f" {n_submissions:>6,} submissions  {n_changes:>3} rating changes"
                    f"   about {_duration(remaining * per_user)} left",
                    flush=True,
                )

            if not progressed:
                break

        print()
        _print_status(conn, sample)
        if exhausted:
            print("Some strata ran out of candidates; see above.")
        return 0
    finally:
        conn.close()


def _collect_one(conn, sample_id, candidate):
    """Fetch and store one candidate. Two requests, one transaction.

    Returns (submissions stored, rating changes) when collected, or None when
    Codeforces says the handle does not exist -- recorded, so the next
    candidate in the stratum takes the place.
    """
    handle = candidate["handle"]
    try:
        submissions = api_client.fetch_submissions(handle)
        changes = api_client.fetch_rating_changes(handle)
    except api_client.TemporaryFailure:
        # Caught first, because it is also a RuntimeError and must not be
        # mistaken for the permanent kind below.
        raise
    except RuntimeError as exc:
        # Only "not found" is recorded as unavailable. Any other refusal -- an
        # HTML error page from a proxy, a 403 while Codeforces is blocking us
        # -- could mark every remaining candidate unavailable in a few minutes,
        # emptying the strata while looking like normal progress. So those are
        # re-raised, and run() stops for a person to look.
        if "not found" not in str(exc).lower():
            raise
        db.mark_unavailable(conn, sample_id, handle, str(exc))
        return None

    # cf_rating is the user's current rating: the last change, since
    # user.rating lists them oldest first. The rating from the draw is the
    # fallback for somebody whose history came back empty.
    rating = changes[-1]["newRating"] if changes else candidate["rating_when_drawn"]

    # History, rating changes and last_synced in ONE transaction (ADR 0004). A
    # stop at any point before this line leaves no trace of this user, and the
    # next run starts them again from the beginning.
    stored = db.save_sync(conn, handle, rating, submissions, rating_changes=changes)
    return stored, len(changes)


def _stopped(reason):
    print(f"\nStopped: {reason}")
    print("Nothing is half-written. Run `collect.py run` again to carry on from here.")
    return 1


def _duration(seconds):
    minutes = int(seconds // 60)
    return f"{minutes // 60}h{minutes % 60:02d}m" if minutes >= 60 else f"{minutes}m"


# ---------------------------------------------------------------------- status

def status(path=DATASET_PATH):
    db.init_db(path)
    conn = db.connect(path)
    try:
        sample = db.get_sample(conn)
        if sample is None:
            print(f"Nothing drawn yet in {path}.")
            return 2
        _print_status(conn, sample)
        return 0
    finally:
        conn.close()


def _print_status(conn, sample):
    print(
        f"sample {sample['id']}: seed {sample['seed']}, "
        f"list fetched {sample['source_fetched_at']}"
    )
    print(f"  {'stratum':<10} {'population':>10} {'collected':>10} {'unavailable':>12}")
    total = 0
    for row in db.get_strata(conn, sample["id"]):
        label = f"{row['stratum']}-{row['stratum'] + sample['stratum_width'] - 1}"
        print(
            f"  {label:<10} {row['population']:>10,} "
            f"{row['collected']:>5} / {row['wanted']:<3} {row['unavailable']:>9}"
        )
        total += row["collected"]
    print(f"  {total} users collected")


# ------------------------------------------------------------------------ main

def main(argv=None):
    parser = argparse.ArgumentParser(description="Collect the NextCF dataset (ADR 0009).")
    commands = parser.add_subparsers(dest="command", required=True)

    draw_cmd = commands.add_parser("draw", help="fetch the rated list and draw the sample")
    # No fixed default seed: a random one is chosen, printed and stored, which
    # is what repeating the draw needs. Pass --seed to choose it yourself.
    draw_cmd.add_argument("--seed", type=int, default=None)
    # 400 is ADR 0009's number. A smaller one is for a trial run into a
    # throwaway file (set NEXTCF_DATASET), and is stored with the sample either
    # way, so a trial can never be mistaken for the real thing.
    draw_cmd.add_argument("--per-stratum", type=int, default=PER_STRATUM)

    commands.add_parser("run", help="collect until every stratum is full")
    commands.add_parser("status", help="show progress per stratum")

    args = parser.parse_args(argv)
    print(f"dataset: {DATASET_PATH}")

    try:
        if args.command == "draw":
            # Refuse before the 15 MB download, not after it. draw() checks
            # again, which is the check that actually guarantees it.
            db.init_db(DATASET_PATH)
            conn = db.connect(DATASET_PATH)
            try:
                if db.get_sample(conn) is not None:
                    raise SampleExists(
                        f"{DATASET_PATH} already has a sample. A second draw would change "
                        "who is in the dataset; use a new file for a new sample."
                    )
            finally:
                conn.close()
            seed = args.seed if args.seed is not None else secrets.randbelow(2**31)
            print("fetching the rated list (about 15 MB)...", flush=True)
            users = api_client.fetch_rated_list()
            draw(DATASET_PATH, users, seed, args.per_stratum)
            return 0
        if args.command == "run":
            return run(DATASET_PATH)
        return status(DATASET_PATH)
    except SampleExists as exc:
        print(exc)
        return 1
    except KeyboardInterrupt:
        # Ctrl+C. The user being written, if any, rolled back with its
        # transaction (ADR 0004), so the next run starts them over.
        print("\nStopped by Ctrl+C. Nothing is half-written; run `collect.py run` again to carry on.")
        return 130


# Runs only when this file is executed directly, not when the checks import it.
if __name__ == "__main__":
    sys.exit(main())
