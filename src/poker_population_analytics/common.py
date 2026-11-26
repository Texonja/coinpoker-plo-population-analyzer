"""Shared parsing primitives for CoinPoker PLO hand histories."""

from __future__ import annotations

from collections import Counter
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
import math
import re
from typing import Any, Dict, List, Optional


RANK_ORDER = "23456789TJQKA"
RANK_VALUE = {rank: value for value, rank in enumerate(RANK_ORDER, start=2)}
HEADER_RE = re.compile(r"CoinPoker Hand #(\d+): (.*?) \(([^)]+)\) ([0-9/]+ [0-9:]+) (\w+)")


def suited_ace(cards):
    suit_counts = Counter(card[1].lower() for card in cards)
    return any(card[0] == "A" and suit_counts[card[1].lower()] >= 2 for card in cards)


def straight_window(values):
    ranks = set(values)
    windows = [set(range(low, low + 5)) for low in range(2, 11)] + [{14, 2, 3, 4, 5}]
    return max(len(ranks & window) for window in windows)


def board_texture(cards):
    """Rank pairing, highest suit count and distinct ranks in one straight window."""
    ranks = Counter(c[0] for c in cards)
    groups = sorted(ranks.values(), reverse=True)
    pair_labels = {(3, 2): "full-house", (2, 2): "double-paired"}
    high_group = {4: "quads", 3: "trips", 2: "paired", 1: "unpaired"}
    pairing = pair_labels.get(tuple(groups[:2]), high_group[groups[0]])
    suits = max(Counter(c[1].lower() for c in cards).values())
    suit_label = {1: "rainbow", 2: "two-tone", 3: "monotone"}[suits] if len(cards) == 3 else f"{suits}-to-a-flush"
    return pairing, suit_label, f"{straight_window(RANK_VALUE[r] for r in ranks)}-in-window"


def split_hand_history(text: str) -> List[str]:
    """Split a text export into complete hand-history blocks."""
    normalized = text.replace("\ufeffCoinPoker Hand #", "CoinPoker Hand #").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return []
    return re.split(r"\n(?=CoinPoker Hand #)", normalized)


def unique_hand_blocks(blocks):
    """Count exact copies once. Withhold every version of an ambiguous hand ID."""
    first = {}
    conflicts = set()
    unkeyed = []
    extra = 0
    for block in blocks:
        key = re.match(r"CoinPoker Hand #(\d+):", block)
        if not key:
            unkeyed.append(block)
            continue
        hand_id = key[1]
        block = block.strip()
        if hand_id not in first:
            first[hand_id] = block
        else:
            extra += 1
            if first[hand_id] != block:
                conflicts.add(hand_id)
    unique = [b for key, b in first.items() if key not in conflicts] + unkeyed
    return unique, {"repeated_id_entries": extra, "conflicting_hand_ids": len(conflicts)}


def valid_cards(cards, expected):
    return (len(cards) == expected and len(set(c.lower() for c in cards)) == expected
            and all(re.fullmatch(r"[2-9TJQKA][cdhs]", c, re.I) for c in cards))


def save_run_manifest(outdir: Path, name: str, filters, optional_paths, managed_paths):
    """Retire unchanged optional files from this analyzer's previous successful run."""
    path = outdir / name
    previous = {}
    if path.is_file():
        try:
            previous = json.loads(path.read_text(encoding="utf-8")).get("optional_file_hashes", {})
        except (ValueError, AttributeError):
            pass
    current = {p.relative_to(outdir).as_posix(): sha256(p.read_bytes()).hexdigest() for p in optional_paths}
    for relative in managed_paths:
        old = outdir / relative
        if (isinstance(previous, dict) and relative in previous and relative not in current
                and old.resolve().is_relative_to(outdir.resolve()) and old.is_file()
                and sha256(old.read_bytes()).hexdigest() == previous[relative]):
            old.unlink()
    filters["optional_file_hashes"] = current
    payload = json.dumps(filters, indent=2, ensure_ascii=False)
    path.write_text(payload, encoding="utf-8")
    (outdir / "filters_applied.json").write_text(payload, encoding="utf-8")


def validate_cli_filters(parser, args):
    for value in (args.date_from, args.date_to):
        if value:
            try:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError
            except ValueError:
                parser.error("dates must be valid calendar dates in YYYY-MM-DD format")
    if args.date_from and args.date_to and args.date_from > args.date_to:
        parser.error("--date-from must be on or before --date-to")
    for value in (args.stake_filter, getattr(args, "compare_stakes", "")):
        if value and not all(re.fullmatch(r"PL[1-9]\d*", s.strip(), re.I) for s in value.split(",")):
            parser.error("stakes must be comma-separated PL labels, for example PL25,PL50")
    if getattr(args, "min_sample", 1) < 1 or getattr(args, "audit_sample_size", 0) < 0:
        parser.error("--min-sample must be positive and --audit-sample-size nonnegative")
    minimum = getattr(args, "min_stack_bb", 0)
    if not math.isfinite(minimum) or minimum < 0:
        parser.error("--min-stack-bb must be finite and nonnegative")


def parse_header(line: str) -> Optional[Dict[str, Any]]:
    """Parse stable game metadata from a CoinPoker hand header."""
    match = HEADER_RE.match(line.lstrip('\ufeff'))
    if not match:
        return None
    hand_id, description, stakes, date_time, timezone = match.groups()
    amounts = [float(value) for value in re.findall(r"([0-9]+(?:\.[0-9]+)?)", stakes)]
    small_blind = amounts[0] if len(amounts) > 0 else None
    big_blind = amounts[1] if len(amounts) > 1 else None
    third_amount = amounts[2] if len(amounts) > 2 else None
    if small_blind is None or big_blind is None or not 0 < small_blind <= big_blind:
        return None
    try:
        iso_date = date(*map(int, date_time.split()[0].split("/"))).isoformat()
    except (ValueError, TypeError):
        return None
    plo_match = re.search(r"PLO\s+(\d+)", description)
    plo_cards = int(plo_match.group(1)) if plo_match else None
    is_bombpot = "BombPot" in description
    return {
        "hand_id": hand_id,
        "desc": description,
        "stakes_str": stakes,
        "dt": date_time,
        "date": iso_date,
        "tz": timezone,
        "sb": small_blind,
        "bb": big_blind,
        "ante": None if is_bombpot else third_amount,
        "bomb_amount": third_amount if is_bombpot else None,
        "plo_cards": plo_cards,
        "is_bombpot": is_bombpot,
        "stake_label": f"PL{int(round(big_blind * 100))}" if big_blind else "UNKNOWN",
    }


def assign_positions(seats: Dict[int, str], button_seat: Optional[int]) -> Dict[str, str]:
    """Map player names to conventional positions for two to nine seats."""
    if not seats or button_seat not in seats:
        return {}
    seat_numbers = sorted(seats)
    button_index = seat_numbers.index(button_seat)
    order = [seat_numbers[(button_index + offset) % len(seat_numbers)] for offset in range(len(seat_numbers))]
    labels_by_count = {
        2: ["BTN/SB", "BB"],
        3: ["BTN", "SB", "BB"],
        4: ["BTN", "SB", "BB", "CO"],
        5: ["BTN", "SB", "BB", "UTG", "CO"],
        6: ["BTN", "SB", "BB", "UTG", "HJ", "CO"],
        7: ["BTN", "SB", "BB", "UTG", "UTG1", "HJ", "CO"],
        8: ["BTN", "SB", "BB", "UTG", "UTG1", "MP", "HJ", "CO"],
        9: ["BTN", "SB", "BB", "UTG", "UTG1", "MP1", "MP2", "HJ", "CO"],
    }
    labels = labels_by_count.get(len(order), ["BTN"] + [f"P{index}" for index in range(1, len(order))])
    return {seats[seat]: labels[index] for index, seat in enumerate(order)}

