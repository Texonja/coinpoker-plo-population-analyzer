"""Rebuild the public evidence ledger from the pinned Leak Finder demo export."""
import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from poker_population_analytics import population as pool

STAB = "BET_IP_VS_MISSED_FLOP_CB"
RESPONSE = "OOP_RESPONSE_VS_IP_FLOP_STAB_AFTER_MISSED_CB"
COMMIT = "16d505268c4229ac77bce764a97d499dbf9dd8cd"
SOURCE = f"https://github.com/Texonja/plo-hero-leak-finder/blob/{COMMIT}/demo/CoinPoker-HeroDemo.txt"
DIGEST = "9cfc4ce9b46d7b9d8760293dc02fb87ac1c4e7f1ba421566808070b6ed648295"
LEDGER = ROOT / "docs/demo/pl50_replay.json"
HERO = "HeroDemo"
EXCLUDED = "9000009970"


def build(path):
    source = path.read_text(encoding="utf-8")
    if hashlib.sha256(source.encode()).hexdigest() != DIGEST:
        raise ValueError("Expected the pinned CoinPoker-HeroDemo.txt export (LF-normalized SHA-256).")
    lines = source.splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("CoinPoker Hand #")]
    args = pool.build_parser().parse_args(["--input", str(path), "--hero", HERO, "--stake-filter", "PL50"])
    hands = []
    antes = Counter()
    settlements = Counter()
    for start, end in zip(starts, starts[1:] + [len(lines)]):
        hand = pool.parse_hand("\n".join(lines[start:end]), HERO)
        if hand is None:
            raise ValueError(f"Unparsed demo hand at line {start+1}")
        if not pool.pass_filters(hand, args):
            continue
        if hand.meta["unknown_action_lines"]:
            raise ValueError(f"Unknown action in {hand.hand_id}")
        antes[hand.meta["ante"] or 0] += 1
        settlements[hand.meta["settlement_status"]] += 1
        decisions = [r for r in pool.extract_required_pool_records(hand, args)
                     if r["spot_id"] in (STAB, RESPONSE) and hand.pot_type in ("srp", "3bet")]
        if not decisions and hand.hand_id != EXCLUDED:
            continue
        if decisions and hand.meta["settlement_status"] != "reconciled":
            raise ValueError(f"Check the source pot and awards in scored hand {hand.hand_id}")
        events = hand.events["FLOP"]
        trace = []
        for event in events:
            trace.append(dict(line=start + event.source_line, position=hand.positions[event.player],
                              hero=event.player == HERO, action=event.action,
                              text=event.raw_line.partition(": ")[2], pot_before=round(event.pot_before, 2)))
        scored = []
        for row in decisions:
            index = 1 if row["spot_id"] == STAB else 2
            action = row["action"].replace("raise_or_allin", "raise")
            if trace[index]["action"] != action or trace[index]["hero"]:
                raise ValueError(f"Source and classified action disagree in {hand.hand_id}")
            scored.append(dict(node=row["spot_id"], action=action, line=trace[index]["line"]))
        hands.append(dict(id=hand.hand_id, first_line=start + 1, last_line=trace[-1]["line"],
                          pot=hand.pot_type, pfa=hand.positions[hand.last_preflop_raiser],
                          board=hand.boards["FLOP"], trace=trace, decisions=scored))
    return dict(source=SOURCE, sha256_lf=DIGEST, raw_hands=len(starts), pl50_hands=sum(antes.values()),
                by_ante={f"{k:.2f}": v for k, v in sorted(antes.items())}, settlement_counts=dict(settlements), hands=hands)


def check_reference_cases(path):
    """Compare line, actor and action against the Leak Finder's independently labeled cases."""
    packed = path.read_bytes()
    if hashlib.sha256(packed).hexdigest() != "400612b6416d0d71efd423add78dbdb8f71fbf64bf33d8c6b26229bc378daac0":
        raise ValueError("Expected the pinned source-audit.json.gz reference pack.")
    verbs = {"check": "checks", "bet": "bets"}
    results = Counter()
    for case in json.loads(gzip.decompress(packed)):
        if case["room"] != "CoinPoker" or case["node"] != STAB:
            continue
        hero = re.search(r"^Dealt to (.+?) \[", case["raw"], re.M).group(1)
        args = pool.build_parser().parse_args(["--input", "reference", "--hero", hero, "--include-hero", "--debug-players"])
        hand = pool.parse_hand(case["raw"], hero)
        decisions = [r for r in pool.extract_required_pool_records(hand, args) if r["spot_id"] == STAB]
        actual = [[f"Line {hand.events['FLOP'][1].source_line}", r["actor"], verbs[r["action"]]] for r in decisions]
        if actual != case["expected"]:
            raise ValueError(f"Decision mismatch in reference hand {case['number']}")
        results[actual[0][2] if actual else "excluded"] += 1
    print(f"{sum(results.values())} independent CoinPoker IP-stab cases passed: {dict(results)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("export", type=Path)
    parser.add_argument("--check", action="store_true", help="Compare with the committed evidence without writing.")
    parser.add_argument("--reference-cases", type=Path, help="Also verify the pinned source-audit.json.gz pack.")
    args = parser.parse_args()
    ledger = build(args.export)
    if args.reference_cases:
        check_reference_cases(args.reference_cases)
    if args.check:
        if ledger != json.loads(LEDGER.read_text(encoding="utf-8")):
            parser.exit(1, "The public evidence differs from the replay.\n")
    else:
        LEDGER.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{ledger['pl50_hands']} eligible PL50 hands. Featured decisions by pot type:")
    print(Counter((h["pot"], d["node"], d["action"]) for h in ledger["hands"] for d in h["decisions"]))


if __name__ == "__main__":
    main()
