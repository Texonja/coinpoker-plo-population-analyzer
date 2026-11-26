"""Compare the bundled analyzer with the pinned Leak Finder on its public CoinPoker demo."""

import argparse
from collections import Counter
from decimal import Decimal
import hashlib
from pathlib import Path
import re
import subprocess
import sys

from replay_pl50 import COMMIT, DIGEST, HERO
from poker_population_analytics import fourbet, population


def check(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("leak_finder", type=Path, help="Local checkout of the referenced Leak Finder revision.")
    root = parser.parse_args().leak_finder.resolve()
    revision = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    check(revision == COMMIT, f"Expected Leak Finder revision {COMMIT}")
    source = (root / "demo/CoinPoker-HeroDemo.txt").read_text(encoding="utf-8")
    check(hashlib.sha256(source.encode()).hexdigest() == DIGEST, "Unexpected demo fingerprint")
    sys.path.insert(0, str(root))
    from leakfinder.engine import METRICS, replay
    from leakfinder.importers import SCALE, coin

    shared = set(population.DEFAULT_BENCHMARKS).intersection(METRICS)
    flags = ["--input", "demo", "--hero", HERO, "--include-hero"]
    pool_args = population.build_parser().parse_args(flags + ["--debug-players"])
    four_args = fourbet.build_parser().parse_args(flags + ["--min-stack-bb", "0"])
    hands = events = decisions = fourbets = splash_events = 0
    for block in population.split_hand_history(source):
        h = population.parse_hand(block, HERO)
        check(h and population.pass_filters(h, pool_args), "Unexpected exclusion in the public demo")
        ref = coin(block)
        other, streets = replay(ref)
        hands += 1
        drops = [
            (i, int(Decimal(m[1]) * SCALE))
            for i, line in enumerate(block.splitlines(), 1)
            if (m := re.fullmatch(r"SPLASH dropped ₮([0-9]+(?:\.[0-9]+)?)", line))
        ]
        for street, reference_events in streets.items():
            actual = h.events[street.upper()]
            check(len(reference_events) == len(actual), f"{h.hand_id}: {street} length")
            for e, observed in zip(reference_events, actual):
                location = f"{h.hand_id} line {observed.source_line}"
                check(
                    (e.ref, e.player, e.action) == (f"Line {observed.source_line}", observed.player, observed.action),
                    location + " actor/action",
                )
                # The reference engine only adds player contributions to its pot.
                external = sum(amount for line, amount in drops if line < observed.source_line)
                check(round(observed.pot_before * SCALE) == e.pot + external, location + " pot")
                check(round(observed.amount * SCALE) == e.amount, location + " contribution")
                splash_events += bool(external)
                events += 1

        expected = Counter((d.node, d.event.player, d.event.action) for d in other if d.node in shared)
        records = population.extract_required_pool_records(h, pool_args)
        actual = Counter(
            (r["spot_id"], r["actor"], r["action"].replace("raise_or_allin", "raise"))
            for r in records
            if r["spot_id"] in shared
        )
        check(actual == expected, f"{h.hand_id}: decision differences {actual - expected}, {expected - actual}")
        decisions += sum(expected.values())

        raises = [e for e in streets["Preflop"] if e.action == "raise"]
        error, rows = fourbet.analyze_hand(block, four_args)
        check(not error and len(rows) == int(len(raises) >= 3), f"{h.hand_id}: four-bet presence")
        if rows:
            row = rows[0]
            actor = raises[2].player
            check(
                row["fourbettor"] == actor and round(row["fourbettor_start_stack"] * SCALE) == ref.stacks[actor],
                f"{h.hand_id}: four-bettor or stack",
            )
            check(set(row["cards"].split()) == set(ref.cards.get(actor, [])), f"{h.hand_id}: known holding")
            fourbets += 1

    print(
        f"{hands} hands, {events} betting actions, {decisions} decisions across {len(shared)} shared nodes, "
        f"{fourbets} four-bets. {splash_events} action pots included documented Splash money."
    )


if __name__ == "__main__":
    main()
