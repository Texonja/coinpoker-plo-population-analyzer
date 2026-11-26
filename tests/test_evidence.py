import csv
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from poker_population_analytics import common, fourbet, population
from test_flop_cbet_logic import heads_up_hand
from test_population import FIXTURE, population_args


class EvidenceTests(unittest.TestCase):
    def test_user_reported_offsuit_ace_in_both_classifiers(self):
        for cards, expected in [("Ah Kc 8c 3d", "other"), ("Ac Kh 8c 3d", "suited_ace")]:
            with self.subTest(cards=cards):
                self.assertEqual(population.classify_starting_hand(cards.split())["hand_class"], expected)
                holding = fourbet.classify_known_hand(cards.split())
                self.assertEqual(holding["hand_class"], expected)
                self.assertEqual(holding["suited_ace"], expected == "suited_ace")

    def test_aces_wheel_and_suited_ace(self):
        self.assertTrue(common.suited_ace(["As", "Ks", "8h", "2c"]))
        self.assertFalse(common.suited_ace(["Ad", "Ks", "8s", "2c"]))
        self.assertEqual(common.straight_window([14, 2, 3, 4]), 4)
        self.assertEqual(common.straight_window([13, 14, 2, 3]), 3)
        self.assertEqual(common.board_texture(["2s", "3h", "Ad"]), ("unpaired", "rainbow", "3-in-window"))
        self.assertEqual(common.board_texture(["As", "Ah", "5s"]), ("paired", "two-tone", "2-in-window"))
        self.assertTrue(fourbet.classify_known_hand(["2c", "4s", "5h", "Ac", "Ad"])["is_aaxx"])
        self.assertEqual(fourbet.extract_known_cards(["Dealt to Hero [As As 2c 3d]"], {"Hero"}), {})

    def test_synthetic_hand_settlement_and_mismatch(self):
        blocks = common.split_hand_history(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual([population.parse_hand(b).meta["settlement_status"] for b in blocks], ["reconciled"] * 4)
        bad = blocks[0].replace("Total pot ₮9.05", "Total pot ₮10.05")
        self.assertEqual(population.parse_hand(bad).meta["settlement_status"], "mismatch")

    def test_splash_is_dead_money_in_pot_not_a_player_contribution(self):
        raw = heads_up_hand(125, pfa_ip=False)
        base = population.parse_hand(raw)
        splash = population.parse_hand(raw.replace("*** HOLE CARDS ***", "SPLASH dropped ₮7\n*** HOLE CARDS ***"))
        self.assertEqual(splash.total_contributed, base.total_contributed)
        self.assertAlmostEqual(splash.events["FLOP"][0].pot_before, base.events["FLOP"][0].pot_before + 7)

    def test_unknown_action_excludes_hand_and_counts_line(self):
        raw = heads_up_hand(123, pfa_ip=True).replace("Hero: checks", "Hero: unrecognized move")
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.txt"
            path.write_text(raw, encoding="utf-8")
            output = Path(tmp) / "result"
            population.analyze_pool(path, output, population_args())
            result = json.loads((output / "filters_applied.json").read_text(encoding="utf-8"))
        self.assertEqual((result["hands_excluded_unknown_action"], result["unknown_action_lines"],
                          result["hands_analyzed_after_filters"]), (1, 1, 0))

    def test_cbet_audit_respects_actor_filter_and_order(self):
        text = heads_up_hand(124, pfa_ip=True)
        hand = population.parse_hand(text)
        row = population.make_flop_cbet_audit_row(hand, excluded_actor="Hero")
        self.assertTrue(row["structurally_eligible"])
        self.assertFalse(row["denominator_eligible"])
        self.assertEqual(row["reason_excluded"], "hero_actor_excluded")
        bad = text.replace("Hero: checks", "Hero: checks\nHero: checks")
        self.assertFalse(population.evaluate_flop_cbet(population.parse_hand(bad)).included)

    def test_board_counts_combine_by_stake_before_threshold(self):
        def sample(stake, hit, n):
            return dict(spot_id="spot", board_bucket="board", pot_type="srp", stake_label=stake,
                        raw_action_counts=json.dumps({"fold": hit, "call": n-hit}), opportunities=n)
        rows = [sample("PL25", 2, 8), sample("PL50", 1, 3), sample("PL50", 7, 9)]
        self.assertEqual(population.board_response_cells(rows, "spot", "fold_pct", 10),
                         {("PL50", "board", "srp"): (8, 12)})

    def test_public_snapshot_and_replay_counts(self):
        directory = Path(__file__).resolve().parents[1] / "docs/demo"
        with (directory / "pool_summary.csv").open(encoding="utf-8-sig") as src:
            summary = list(csv.DictReader(src))
        snapshot = json.loads((directory / "snapshot.json").read_text())
        self.assertEqual(sum(int(r["opportunities"]) for r in summary), snapshot["filters"]["pool_spot_records"])
        self.assertNotIn("PFA_RESPONSE_AFTER_TURN_GIVEUP", {r["spot_id"] for r in summary})
        for row in summary:
            counts = json.loads(row["raw_action_counts"])
            self.assertEqual(sum(counts.values()), int(row["opportunities"]))
            for metric in ("bet_pct", "check_pct", "fold_pct", "call_pct", "raise_pct", "no_response_pct"):
                self.assertEqual(round(population.exact_metric_value(row, metric), 1), float(row[metric]))
            self.assertEqual(population.benchmark_flag(row, population.DEFAULT_BENCHMARKS, 30)[0], row["benchmark_flag"])
        with (directory / "fourbet_summary.csv").open(encoding="utf-8") as src:
            four = list(csv.DictReader(src))
        for total in (row for row in four if row["fourbettor_position"] == "ALL"):
            positions = [r for r in four if r["stake_label"] == total["stake_label"] and r["fourbettor_position"] != "ALL"]
            for col in ("total_4bets_stack_filtered", "known_4bettor_hands", "known_AAxx", "unknown_4bettor_hands"):
                self.assertEqual(sum(int(r[col]) for r in positions), int(total[col]))
        ledger = json.loads((directory / "pl50_replay.json").read_text(encoding="utf-8"))
        self.assertEqual((ledger["raw_hands"], ledger["pl50_hands"]), (320, 116))
        landing = (directory.parent / "index.html").read_text(encoding="utf-8")
        self.assertIn("<strong>40.7%</strong>", landing)
        self.assertIn("847 opportunities in the historical sample", landing)
        scored = [d for h in ledger["hands"] for d in h["decisions"]]
        self.assertEqual((sum(bool(h["decisions"]) for h in ledger["hands"]), len(scored)), (9, 13))
        for h in ledger["hands"]:
            for d in h["decisions"]:
                event, = [e for e in h["trace"] if e["line"] == d["line"]]
                self.assertEqual(event["action"], d["action"])
                self.assertFalse(event["hero"])
