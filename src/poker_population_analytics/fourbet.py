#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CoinPoker PLO Four-bet Showdown Analyzer

Finds preflop 4-bets made by non-Hero opponents, filters by starting stack in bb,
and checks known/shown 4-bettor hole cards to estimate how often the 4-bet was AAxx.

Default: PLO4 regular hands only, bombpots excluded, Hero excluded.

Usage after installation:
    plo-fourbet --input cash.txt --stake-filter PL50 --hero Hero --outdir fourbet_report

Notes:
- A 4-bet is defined as the third preflop raise in a hand:
    open raise = raise #1
    3-bet      = raise #2
    4-bet      = raise #3
- ALLIN actions are treated as raises only if they increase the current amount to call.
- "Known" means the 4-bettor's 4-card hand appears in the HH via shows/showed/mucks/mucked.
- This is population-only; anonymized IDs are not profiled individually.
"""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
import html
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from . import __version__
    from .common import RANK_VALUE, assign_positions, parse_header, split_hand_history, suited_ace, straight_window, unique_hand_blocks, valid_cards, validate_cli_filters, save_run_manifest
    from . import report_ui
except ImportError:  # Supports direct execution during local debugging.
    __version__ = "1.2.1"
    from common import RANK_VALUE, assign_positions, parse_header, split_hand_history, suited_ace, straight_window, unique_hand_blocks, valid_cards, validate_cli_filters, save_run_manifest
    import report_ui

SEAT_RE = re.compile(r"Seat (\d+): (.+?) \(₮([0-9]+(?:\.[0-9]+)?) in chips\)")
BUTTON_RE = re.compile(r"Seat #(\d+) is the button")
RAISE_RE = re.compile(r"^(.+?): raises ₮([0-9]+(?:\.[0-9]+)?) to ₮([0-9]+(?:\.[0-9]+)?)")
CALL_RE = re.compile(r"^(.+?): calls ₮([0-9]+(?:\.[0-9]+)?)")
ALLIN_RE = re.compile(r"^(.+?): ALLIN ₮([0-9]+(?:\.[0-9]+)?)")
POST_SB_RE = re.compile(r"^(.+?): posts small blind ₮([0-9]+(?:\.[0-9]+)?)")
POST_BB_RE = re.compile(r"^(.+?): posts big blind ₮([0-9]+(?:\.[0-9]+)?)")
POST_ANTE_RE = re.compile(r"^(.+?): posts ante ₮([0-9]+(?:\.[0-9]+)?)")
STRADDLE_RE = re.compile(r"^(.+?): STRADDLE ₮([0-9]+(?:\.[0-9]+)?)", re.I)
FOLD_RE = re.compile(r"^(.+?): folds")
STREET_RE = re.compile(r"^\*\*\* (?:FIRST |SECOND |THIRD )?(FLOP|TURN|RIVER) \*\*")

# Robust known-card patterns. CoinPoker exports can vary slightly between full action and summary lines.
KNOWN_CARD_PATTERNS = [
    re.compile(r"^Dealt to (.+?)\s+\[([^\]]+)\]"),
    re.compile(r"^(.+?):\s+shows\s+\[([^\]]+)\]", re.I),
    re.compile(r"^(.+?):\s+showed\s+\[([^\]]+)\]", re.I),
    re.compile(r"^(.+?):\s+mucks\s+\[([^\]]+)\]", re.I),
    re.compile(r"^(.+?):\s+mucked\s+\[([^\]]+)\]", re.I),
    re.compile(r"^Seat \d+:\s+(.+?)\s+showed\s+\[([^\]]+)\]", re.I),
    re.compile(r"^Seat \d+:\s+(.+?)\s+mucked\s+\[([^\]]+)\]", re.I),
]


def parse_cards(card_text: str) -> List[str]:
    return [token[0].upper() + token[1:].lower() for token in card_text.split()]


def classify_known_hand(cards: List[str]) -> Dict[str, Any]:
    ranks = [c[0].upper() for c in cards]
    suits = [c[1].lower() for c in cards]
    rank_counts = collections.Counter(ranks)
    suit_counts = collections.Counter(suits)
    vals = sorted([RANK_VALUE.get(r, 0) for r in ranks], reverse=True)
    uniq = sorted(set(vals))
    pairs = sum(1 for v in rank_counts.values() if v == 2)
    high = sum(1 for v in vals if v >= 11)
    broadway = sum(1 for v in vals if v >= 10)
    best_window = straight_window(uniq)
    double_suited = sum(1 for v in suit_counts.values() if v >= 2) >= 2
    if rank_counts.get("A", 0) >= 2:
        hand_class = "AAxx"
    elif rank_counts.get("K", 0) >= 2:
        hand_class = "KKxx"
    elif pairs >= 1:
        hand_class = "pair"
    elif best_window >= 4:
        hand_class = "rundown"
    elif broadway >= 3:
        hand_class = "broadway"
    elif suited_ace(cards):
        hand_class = "suited_ace"
    else:
        hand_class = "other"
    return {
        "cards": " ".join(cards),
        "card_count": len(cards),
        "is_aaxx": rank_counts.get("A", 0) >= 2,
        "hand_class": hand_class,
        "double_suited": double_suited,
        "suited_ace": suited_ace(cards),
        "pairs": pairs,
        "broadways": broadway,
        "high_cards": high,
        "connected_window": best_window,
    }


def extract_known_cards(lines: List[str], seat_names: set[str], expected_cards: int = 4) -> Dict[str, List[str]]:
    known: Dict[str, List[str]] = {}
    conflicts = set()
    board_cards = set()
    for line in lines:
        if STREET_RE.match(line) or line.startswith("Board ["):
            for group in re.findall(r"\[([^\]]+)\]", line):
                board_cards.update(parse_cards(group))
        for pat in KNOWN_CARD_PATTERNS:
            m = pat.match(line)
            if not m:
                continue
            player = m.group(1).strip()
            cards = parse_cards(m.group(2))
            if player in seat_names and valid_cards(cards, expected_cards):
                if player in known and set(known[player]) != set(cards):
                    conflicts.add(player)
                known[player] = cards
            break
    owners = collections.Counter(card for holding in known.values() for card in holding)
    return {p: cards for p, cards in known.items() if p not in conflicts
            and not any(c in board_cards or owners[c] > 1 for c in cards)}


def pass_filters(meta: Dict[str, Any], args: argparse.Namespace) -> bool:
    gf = args.game_filter.lower()
    if gf == "plo4":
        if meta.get("plo_cards") != 4:
            return False
        if meta.get("is_bombpot") and not args.include_bombpot:
            return False
    elif gf == "plo5":
        if meta.get("plo_cards") != 5:
            return False
        if meta.get("is_bombpot") and not args.include_bombpot:
            return False
    elif gf == "bombpot":
        if not meta.get("is_bombpot"):
            return False
    elif gf == "all":
        if meta.get("is_bombpot") and not args.include_bombpot:
            return False
    else:
        raise ValueError(f"Unknown game filter: {args.game_filter}")

    if meta.get("is_straddled") and not getattr(args, "include_straddles", False):
        return False

    if args.stake_filter:
        allowed = {x.strip().upper() for x in args.stake_filter.split(",") if x.strip()}
        if meta.get("stake_label", "").upper() not in allowed:
            return False

    date_part = meta["date"]
    if args.date_from and date_part < args.date_from:
        return False
    if args.date_to and date_part > args.date_to:
        return False
    return True


def analyze_hand(block: str, args: argparse.Namespace) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    lines = block.splitlines()
    if not lines:
        return "empty", []
    meta = parse_header(lines[0])
    if not meta:
        return "header", []
    meta["is_straddled"] = any(STRADDLE_RE.match(line) for line in lines)
    if not pass_filters(meta, args):
        return None, []

    seats: Dict[int, str] = {}
    stacks: Dict[str, float] = {}
    for line in lines:
        m = SEAT_RE.match(line)
        if m:
            seat = int(m.group(1))
            player = m.group(2)
            seats[seat] = player
            stacks[player] = float(m.group(3))
    if not seats:
        return "seats", []
    if args.hero and args.hero not in seats.values() and not args.allow_hands_without_hero:
        return None, []

    bb = float(meta.get("bb") or 0.0)
    if bb <= 0:
        return "bb", []
    button_match = BUTTON_RE.search(block)
    button_seat = int(button_match.group(1)) if button_match else None
    positions = assign_positions(seats, button_seat)
    known_cards = extract_known_cards(lines, set(seats.values()), meta.get("plo_cards") or 4)

    street_contrib: Dict[str, float] = collections.defaultdict(float)
    closed_players = set()
    current_to_call = 0.0
    raise_count = 0
    preflop_sequence: List[str] = []
    fourbet_rows: List[Dict[str, Any]] = []

    for line in lines[1:]:
        line = line.rstrip()
        if STREET_RE.match(line) or line.startswith(("*** SHOWDOWN", "*** SUMMARY")):
            break
        actor, sep, action = line.partition(": ")
        if not sep or actor not in stacks:
            if any(regex.fullmatch(line) for regex in (RAISE_RE, CALL_RE, ALLIN_RE, FOLD_RE)):
                return "unknown_preflop_actor", []
            continue
        post = POST_SB_RE.fullmatch(line) or POST_BB_RE.fullmatch(line) or STRADDLE_RE.fullmatch(line)
        if post:
            street_contrib[actor] += float(post[2])
            current_to_call = max(current_to_call, street_contrib[actor])
            continue
        if POST_ANTE_RE.fullmatch(line) or re.fullmatch(r"RETURN ₮[0-9]+(?:\.[0-9]+)?", action):
            continue
        if actor in closed_players:
            return "action_after_fold_or_allin", []
        if action == "folds":
            closed_players.add(actor)
            preflop_sequence.append(f"{actor}:fold")
            continue
        if action == "checks" and abs(street_contrib[actor] - current_to_call) < 1e-9:
            preflop_sequence.append(f"{actor}:check")
            continue
        call = CALL_RE.fullmatch(line)
        raise_to = RAISE_RE.fullmatch(line)
        all_in = ALLIN_RE.fullmatch(line)
        if not (call or raise_to or all_in):
            return "unrecognized_preflop_action", []
        target = float(raise_to[3]) if raise_to else street_contrib[actor] + float((call or all_in)[2])
        if target <= street_contrib[actor] or (call and target > current_to_call + 1e-9):
            return "invalid_preflop_amount", []
        if all_in:
            closed_players.add(actor)
        street_contrib[actor] = target
        if target <= current_to_call + 1e-9:
            if raise_to:
                return "invalid_raise_to", []
            label = "allin_call" if all_in else "call"
            preflop_sequence.append(f"{actor}:{label}_to_{target:.4g}")
            continue
        current_to_call = target
        raise_count += 1
        action_name = "open" if raise_count == 1 else f"{raise_count + 1}bet"
        if all_in:
            action_name += "_allin"
        preflop_sequence.append(f"{actor}:{action_name}_to_{target:.4g}")
        if raise_count == 3:
            row = build_fourbet_row(meta, actor, stacks, positions, bb, known_cards, action_name, target,
                                    args, "allin_raise" if all_in else "raise")
            if row:
                row["preflop_sequence"] = " | ".join(preflop_sequence)
                fourbet_rows.append(row)

    return None, fourbet_rows


def build_fourbet_row(
    meta: Dict[str, Any],
    player: str,
    stacks: Dict[str, float],
    positions: Dict[str, str],
    bb: float,
    known_cards: Dict[str, List[str]],
    action_name: str,
    total_to: float,
    args: argparse.Namespace,
    action_type: str,
) -> Optional[Dict[str, Any]]:
    if args.hero and not args.include_hero and player == args.hero:
        return None
    stack = float(stacks.get(player, 0.0))
    stack_bb = stack / bb if bb else 0.0
    if stack_bb < args.min_stack_bb:
        return None
    cards = known_cards.get(player, [])
    hand_info = classify_known_hand(cards) if cards else {
        "cards": "",
        "card_count": 0,
        "is_aaxx": "",
        "hand_class": "unknown",
        "double_suited": "",
        "suited_ace": "",
        "pairs": "",
        "broadways": "",
        "high_cards": "",
        "connected_window": "",
    }
    return {
        "hand_id": meta.get("hand_id", ""),
        "dt": meta.get("dt", ""),
        "stake_label": meta.get("stake_label", ""),
        "desc": meta.get("desc", ""),
        "bb": bb,
        "fourbettor": player,
        "fourbettor_position": positions.get(player, ""),
        "fourbettor_start_stack": round(stack, 4),
        "fourbettor_start_stack_bb": round(stack_bb, 1),
        "fourbet_action": action_name,
        "fourbet_action_type": action_type,
        "fourbet_total_to": round(total_to, 4),
        "fourbet_total_to_bb": round(total_to / bb, 2) if bb else "",
        "known_cards": bool(cards),
        **hand_info,
    }


SUMMARY_COLUMNS = ("stake_label fourbettor_position total_4bets_stack_filtered known_4bettor_hands known_rate_pct "
                   "known_AAxx AAxx_pct_of_known unknown_4bettor_hands").split()


def write_csv(rows: List[Dict[str, Any]], path: Path, empty_columns=()) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows and not empty_columns:
        path.write_text("", encoding="utf-8")
        return
    keys: List[str] = list(empty_columns) if not rows else []
    for row in rows:
        for k in row.keys():
            if k not in keys:
                keys.append(k)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def export_detail_row(row: Dict[str, Any], include_identifiers: bool = False) -> Dict[str, Any]:
    """Return a CSV-safe detail row with player identifiers removed by default."""
    exported = dict(row)
    if not include_identifiers:
        exported.pop("fourbettor", None)
        exported.pop("preflop_sequence", None)
    return exported


def pct_float_text(value: Any) -> float:
    try:
        if isinstance(value, str) and value.endswith("%"):
            value = value[:-1]
        return float(value)
    except Exception:
        return math.nan


def html_escape(x: Any) -> str:
    return html.escape(str(x))


def html_table(rows: List[Dict[str, Any]], cols: List[str], max_rows: int = 80) -> str:
    return report_ui.html_table(rows, cols, max_rows)


def make_hand_class_summary(known_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    c = collections.Counter(str(r.get("hand_class", "unknown")) for r in known_rows)
    total = sum(c.values())
    return [
        {"hand_class": cls, "count": n, "pct": pct(n, total)}
        for cls, n in c.most_common()
    ]


def import_headless_pyplot():
    return report_ui.chart_pyplot()


def generate_fourbet_charts(outdir: Path, summary_rows: List[Dict[str, Any]], known_rows: List[Dict[str, Any]]) -> List[str]:
    return plot_fourbet_summary(outdir, summary_rows, make_hand_class_summary(known_rows))


def plot_fourbet_summary(outdir: Path, summary_rows: List[Dict[str, Any]], classes: List[Dict[str, Any]]) -> List[str]:
    paths: List[str] = []
    try:
        plt = import_headless_pyplot()
    except Exception:
        return paths
    chart_dir = outdir / "charts"
    chart_dir.mkdir(parents=True, exist_ok=True)

    pos_rows = [r for r in summary_rows if r.get("fourbettor_position") != "ALL" and int(r.get("known_4bettor_hands") or 0) > 0]
    if pos_rows:
        pos_rows = sorted(pos_rows, key=lambda r: pct_float_text(r.get("AAxx_pct_of_known")), reverse=True)
        labels = [f"{r.get('stake_label')} · {r.get('fourbettor_position')} · n={r.get('known_4bettor_hands')}" for r in pos_rows]
        vals = [pct_float_text(r.get("AAxx_pct_of_known")) for r in pos_rows]
        fig, ax = plt.subplots(figsize=(9, max(4, 0.38 * len(pos_rows))))
        ax.barh(labels, vals)
        ax.invert_yaxis()
        ax.set_xlim(0, 100)
        ax.set_xlabel("AAxx among known 4-bets (%)")
        ax.set_title("AAxx share by 4-bettor position")
        ax.grid(axis="x", alpha=0.25)
        fig.tight_layout()
        path = chart_dir / "aaxx_by_position.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(str(path))

    if classes:
        labels = [str(r.get("hand_class")) for r in classes]
        vals = [int(r.get("count") or 0) for r in classes]
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(labels, vals)
        ax.set_ylabel("Known 4-bettor hands")
        ax.set_title("Known 4-bet hand-class composition")
        ax.tick_params(axis='x', rotation=35)
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        path = chart_dir / "hand_class_composition.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        paths.append(str(path))

    return paths


def generate_fourbet_dashboard(outdir: Path, summary_rows: List[Dict[str, Any]], rows: List[Dict[str, Any]], known_rows: List[Dict[str, Any]], chart_paths: List[str], args: argparse.Namespace) -> None:
    report_ui.fourbet_report(outdir, summary_rows, make_hand_class_summary(known_rows),
                            chart_paths, args.min_stack_bb, args.stake_filter, include_hero=args.include_hero)


def pct(num: int, den: int) -> str:
    return "" if den == 0 else f"{100.0 * num / den:.1f}%"


def summarize(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = collections.defaultdict(list)
    for r in rows:
        groups[(str(r.get("stake_label", "")), str(r.get("fourbettor_position", "")))].append(r)
    out: List[Dict[str, Any]] = []
    for (stake, pos), gr in sorted(groups.items()):
        known = [r for r in gr if r.get("known_cards")]
        aaxx = [r for r in known if r.get("is_aaxx") is True]
        out.append({
            "stake_label": stake,
            "fourbettor_position": pos,
            "total_4bets_stack_filtered": len(gr),
            "known_4bettor_hands": len(known),
            "known_rate_pct": pct(len(known), len(gr)),
            "known_AAxx": len(aaxx),
            "AAxx_pct_of_known": pct(len(aaxx), len(known)),
            "unknown_4bettor_hands": len(gr) - len(known),
        })
    # Add all-positions aggregate by stake.
    by_stake: Dict[str, List[Dict[str, Any]]] = collections.defaultdict(list)
    for r in rows:
        by_stake[str(r.get("stake_label", ""))].append(r)
    for stake, gr in sorted(by_stake.items()):
        known = [r for r in gr if r.get("known_cards")]
        aaxx = [r for r in known if r.get("is_aaxx") is True]
        out.insert(0, {
            "stake_label": stake,
            "fourbettor_position": "ALL",
            "total_4bets_stack_filtered": len(gr),
            "known_4bettor_hands": len(known),
            "known_rate_pct": pct(len(known), len(gr)),
            "known_AAxx": len(aaxx),
            "AAxx_pct_of_known": pct(len(aaxx), len(known)),
            "unknown_4bettor_hands": len(gr) - len(known),
        })
    return out


def make_md(summary_rows: List[Dict[str, Any]], rows: List[Dict[str, Any]], args: argparse.Namespace) -> str:
    md: List[str] = []
    known = [r for r in rows if r.get("known_cards")]
    aaxx = [r for r in known if r.get("is_aaxx") is True]
    md.append("# CoinPoker PLO 4-bet Showdown Analyzer")
    md.append("")
    md.append(f"Input file: `{Path(args.input).name}`")
    md.append(f"Game filter: **{args.game_filter}**, stake filter: **{args.stake_filter or 'all'}**, min stack: **{args.min_stack_bb:g}bb**, Hero included: **{args.include_hero}**")
    md.append("")
    md.append("## Headline")
    md.append("")
    md.append(f"- Stack-filtered 4-bets found: **{len(rows):,}**")
    md.append(f"- Known/shown 4-bettor hands: **{len(known):,}**")
    md.append(f"- AAxx among known 4-bettor hands: **{len(aaxx):,} / {len(known):,} ({pct(len(aaxx), len(known)) or 'n/a'})**")
    md.append("")
    md.append("## Summary")
    md.append("")
    cols = ["stake_label", "fourbettor_position", "total_4bets_stack_filtered", "known_4bettor_hands", "known_rate_pct", "known_AAxx", "AAxx_pct_of_known", "unknown_4bettor_hands"]
    md.append("| " + " | ".join(cols) + " |")
    md.append("| " + " | ".join(["---"] * len(cols)) + " |")
    for r in summary_rows:
        md.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    md.append("")
    md.append("## Important notes")
    md.append("")
    md.append("- This counts only known/shown 4-bettor cards for the AAxx percentage. Unknown 4-bettor hands are excluded from the AAxx denominator.")
    md.append("- ALLIN is counted as a 4-bet only when it increases the current preflop bet.")
    md.append("- Because CoinPoker uses anonymized IDs, this is population-only and not a player profile.")
    return "\n".join(md)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Analyze known/shown villain 4-bets for AAxx frequency")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument("--input", required=True, help="CoinPoker hand history txt file")
    p.add_argument("--hero", default="Hero", help="Hero screen name, default Hero")
    p.add_argument("--include-hero", action="store_true", help="Include Hero 4-bets too. Default excludes Hero.")
    p.add_argument("--allow-hands-without-hero", action="store_true", help="Analyze hands even if hero name is not present")
    p.add_argument("--outdir", default="fourbet_showdown_report", help="Output directory")
    p.add_argument("--min-stack-bb", type=float, default=60.0, help="Minimum starting stack in bb for the 4-bettor")
    p.add_argument("--game-filter", default="plo4", choices=["plo4", "plo5", "bombpot", "all"], help="Default PLO4 regular only")
    p.add_argument("--include-bombpot", action="store_true")
    p.add_argument("--include-straddles", action="store_true", help="Include straddled hands. Default excludes them")
    p.add_argument("--stake-filter", default="", help="Comma-separated stakes, e.g. PL25,PL50")
    p.add_argument("--date-from", default="", help="YYYY-MM-DD inclusive")
    p.add_argument("--date-to", default="", help="YYYY-MM-DD inclusive")
    p.add_argument("--no-charts", action="store_true", help="Skip PNG chart generation; the HTML dashboard is still written")
    p.add_argument("--include-identifiers", action="store_true", help="Include player IDs and named preflop sequences in granular CSV files. Off by default.")
    return p


def main(argv: Optional[List[str]] = None) -> None:
    p = build_parser()
    args = p.parse_args(argv)
    validate_cli_filters(p, args)

    input_path = Path(args.input)
    if not input_path.is_file():
        p.error(f"input file not found: {input_path}")
    text = input_path.read_text(encoding="utf-8", errors="replace")
    blocks = split_hand_history(text)
    rows: List[Dict[str, Any]] = []
    parse_errors = collections.Counter()
    unique, duplicate_counts = unique_hand_blocks(blocks)
    for block in unique:
        err, hand_rows = analyze_hand(block, args)
        if err:
            parse_errors[err] += 1
        rows.extend(hand_rows)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    known_rows = [r for r in rows if r.get("known_cards")]
    summary_rows = summarize(rows)
    exported_rows = [export_detail_row(row, args.include_identifiers) for row in rows]
    exported_known_rows = [export_detail_row(row, args.include_identifiers) for row in known_rows]
    detail_columns = ("hand_id dt stake_label desc bb fourbettor_position fourbettor_start_stack fourbettor_start_stack_bb "
                      "fourbet_action fourbet_action_type fourbet_total_to fourbet_total_to_bb known_cards cards card_count "
                      "is_aaxx hand_class double_suited suited_ace pairs broadways high_cards connected_window").split()
    if args.include_identifiers:
        detail_columns.extend(["fourbettor", "preflop_sequence"])
    write_csv(exported_rows, outdir / "fourbet_all.csv", detail_columns)
    write_csv(exported_known_rows, outdir / "fourbet_known_cards.csv", detail_columns)
    write_csv(summary_rows, outdir / "fourbet_summary.csv", SUMMARY_COLUMNS)
    filters = {
        "analyzer_version": __version__,
        "input": input_path.name,
        "hero": args.hero,
        "include_hero": args.include_hero,
        "include_identifiers": args.include_identifiers,
        "min_stack_bb": args.min_stack_bb,
        "game_filter": args.game_filter,
        "include_bombpot": args.include_bombpot,
        "include_straddles": args.include_straddles,
        "stake_filter": args.stake_filter or "all",
        "date_from": args.date_from or "none",
        "date_to": args.date_to or "none",
        "raw_hands": len(blocks),
        **duplicate_counts,
        "stack_filtered_4bets": len(rows),
        "known_4bettor_hands": len(known_rows),
        "parse_errors": dict(parse_errors),
    }
    md = make_md(summary_rows, rows, args)
    (outdir / "fourbet_report.md").write_text(md, encoding="utf-8")
    chart_paths: List[str] = []
    if not args.no_charts:
        chart_paths = generate_fourbet_charts(outdir, summary_rows, known_rows)
    generate_fourbet_dashboard(outdir, summary_rows, rows, known_rows, chart_paths, args)
    save_run_manifest(outdir, "fourbet_filters.json", filters, [Path(p) for p in chart_paths],
                      ("charts/aaxx_by_position.png", "charts/hand_class_composition.png"))

    known_aaxx = sum(1 for r in known_rows if r.get("is_aaxx") is True)
    print("Done.")
    print(f"Raw hands: {len(blocks):,}")
    print(f"Stack-filtered 4-bets: {len(rows):,}")
    print(f"Known/shown 4-bettor hands: {len(known_rows):,}")
    print(f"AAxx among known: {known_aaxx:,}/{len(known_rows):,} ({pct(known_aaxx, len(known_rows)) or 'n/a'})")
    print(f"Output: {outdir}")
    print("Open fourbet_dashboard.html, fourbet_report.md and fourbet_known_cards.csv.")


if __name__ == "__main__":
    main()
