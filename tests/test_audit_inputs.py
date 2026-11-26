from contextlib import redirect_stdout, redirect_stderr
import csv
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from poker_population_analytics import fourbet, population as pool
from test_fourbet import fourbet_args
from test_population import FIXTURE


class InputAuditTests(unittest.TestCase):
    def setUp(self):
        self.first, self.second, *_ = pool.split_hand_history(FIXTURE.read_text(encoding="utf-8"))
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "hands.txt"
        self.out = self.root / "reports"

    def write(self, *blocks):
        self.source.write_text("\r\n".join(b.strip() for b in blocks), encoding="utf-8-sig")

    def run_both(self, *options):
        args = ["--input", str(self.source), "--outdir", str(self.out), "--no-charts", *options]
        with redirect_stdout(io.StringIO()):
            pool.main(args)
            fourbet.main(args)
        return tuple(
            json.loads((self.out / name).read_text(encoding="utf-8"))
            for name in ("pool_filters.json", "fourbet_filters.json")
        )

    def test_overlapping_exports_and_contradictory_duplicates(self):
        self.write(self.first, "\ufeff" + self.first, self.second)
        pool_stats, four_stats = self.run_both()
        self.assertEqual(
            (
                pool_stats["raw_hands_before_filters"],
                pool_stats["repeated_id_entries"],
                pool_stats["hands_analyzed_after_filters"],
                four_stats["stack_filtered_4bets"],
            ),
            (3, 1, 2, 1),
        )
        edited = self.first.replace("PlayerGamma: RETURN ₮8.00", "PlayerGamma: RETURN ₮7.99")
        for blocks in [(self.first, edited), (edited, self.first)]:
            self.write(*blocks, self.second)
            pool_stats, four_stats = self.run_both()
            self.assertEqual(
                (
                    pool_stats["conflicting_hand_ids"],
                    pool_stats["hands_analyzed_after_filters"],
                    four_stats["conflicting_hand_ids"],
                    four_stats["stack_filtered_4bets"],
                ),
                (1, 1, 1, 0),
            )

    def test_empty_stake_is_a_readable_report_in_both_pipelines(self):
        self.write(self.first)
        p, f = self.run_both("--stake-filter", "PL100")
        self.assertEqual((p["pool_spot_records"], f["stack_filtered_4bets"]), (0, 0))
        for filename, header in [
            ("pool_summary.csv", "opportunities"),
            ("fourbet_summary.csv", "known_4bettor_hands"),
            ("pool_spots.csv", "actor_position"),
            ("fourbet_known_cards.csv", "cards"),
        ]:
            with (self.out / filename).open(encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                self.assertIn(header, reader.fieldnames)
                self.assertEqual(list(reader), [])

    def test_bad_hand_does_not_stop_remaining_export(self):
        broken = self.first.replace("₮0.75 to ₮1.25", "₮0.75 to ₮1..25")
        self.write(broken, self.second)
        p, f = self.run_both()
        self.assertEqual(
            (p["hands_analyzed_after_filters"], p["parse_errors"], sum(f["parse_errors"].values())), (1, 1, 1)
        )
        for date_range in [("2026-01-10", "2026-01-10", 1), ("2026-01-11", "2026-01-31", 0)]:
            start, end, count = date_range
            self.write(self.first.replace("2026/01/10", "2026/1/10"))
            p, f = self.run_both("--date-from", start, "--date-to", end)
            self.assertEqual((p["hands_analyzed_after_filters"], f["stack_filtered_4bets"]), (count, count))

    def test_rerun_retires_only_unchanged_generated_audits(self):
        self.write(self.first, self.second)
        args = ["--input", str(self.source), "--outdir", str(self.out), "--no-charts"]
        with redirect_stdout(io.StringIO()):
            pool.main([*args, "--audit-flop-cbet"])
            annotated = self.out / "audit_fold_to_flop_cbet_included_sample.csv"
            annotated.write_text("my annotations", encoding="utf-8")
            pool.main(args)
        self.assertFalse((self.out / "audit_fold_to_flop_cbet.csv").exists())
        self.assertTrue(annotated.is_file())
        self.assertEqual(annotated.read_text(encoding="utf-8"), "my annotations")

    def test_different_hero_is_an_exclusion(self):
        self.write(self.first)
        p, f = self.run_both("--hero", "AnotherAlias")
        self.assertEqual((p["hands_without_hero"], p["parse_errors"], p["pool_spot_records"]), (1, 0, 0))
        self.assertEqual((f["stack_filtered_4bets"], f["parse_errors"]), (0, {}))

    def test_compare_stakes_honors_the_chart_switch(self):
        self.write(self.second)
        args = [
            "--input",
            str(self.source),
            "--outdir",
            str(self.out),
            "--compare-stakes",
            "pl50,PL25,PL50",
            "--no-charts",
        ]
        with patch.object(pool, "import_headless_pyplot") as plot, redirect_stdout(io.StringIO()):
            pool.main(args)
        plot.assert_not_called()
        self.assertTrue((self.out / "stake_comparison.csv").is_file())
        self.assertTrue((self.out / "PL50/pool_dashboard.html").is_file())
        self.assertFalse((self.out / "charts/stake_comparison.png").exists())

    def test_rejects_invalid_filter_inputs_before_creating_output(self):
        self.write(self.first)
        for module, extra in [
            (pool, ["--date-from", "2026-02-30"]),
            (fourbet, ["--min-stack-bb", "nan"]),
            (pool, ["--compare-stakes", "PL25,bad"]),
            (pool, ["--min-sample", "0"]),
            (fourbet, ["--date-from", "2026-02-01", "--date-to", "2026-01-01"]),
        ]:
            with self.subTest(extra=extra), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                module.main(["--input", str(self.source), "--outdir", str(self.out), *extra])
        self.assertFalse(self.out.exists())

    def test_hero_dealt_only_and_conflicting_reveals(self):
        block = self.first.replace("Hero", "Someone").replace("PlayerGamma", "Hero")
        block = block.replace("Dealt to Hero\n", "Dealt to Hero [Ac As 2h 5h]\n")
        block = "\n".join(line for line in block.splitlines() if "shows [" not in line and "showed [" not in line)
        _, included = fourbet.analyze_hand(block, fourbet_args(include_hero=True))
        self.assertEqual((len(included), included[0]["is_aaxx"]), (1, True))
        self.assertEqual(fourbet.analyze_hand(block, fourbet_args())[1], [])
        for extra in ["Hero: shows [9c 9d 2s 2d]", "Board [Ac 3c Qd]", "Someone: shows [As 8c 5d 6d]"]:
            with self.subTest(extra=extra):
                _, rows = fourbet.analyze_hand(block + "\n" + extra, fourbet_args(include_hero=True))
                self.assertFalse(rows[0]["known_cards"])
        self.assertEqual(fourbet.extract_known_cards(["Hero: shows [Ac As 2h 5h junk]"], {"Hero"}), {})

    def test_five_card_filter_and_complete_reveal(self):
        five = self.first.replace("PLO 4", "PLO 5").replace("9c 8c 7d 6d", "9c 8c 7d 6d 4h")
        five = five.replace("As Ah Kd Qd", "Ks Kh 8d Ad Ac")
        self.write(five)
        p, f = self.run_both()
        self.assertEqual((p["hands_analyzed_after_filters"], f["stack_filtered_4bets"]), (0, 0))
        p, f = self.run_both("--game-filter", "plo5")
        self.assertEqual((p["hands_analyzed_after_filters"], f["known_4bettor_hands"]), (1, 1))
        with (self.out / "fourbet_known_cards.csv").open() as stream:
            (row,) = csv.DictReader(stream)
        self.assertEqual((row["card_count"], row["is_aaxx"]), ("5", "True"))

    def test_fourbet_allin_call_versus_raise_and_stack_boundary(self):
        for action, count in [("ALLIN ₮2.75", 0), ("ALLIN ₮1.75", 0), ("ALLIN ₮10.75", 1)]:
            block = self.first.replace("raises ₮8.00 to ₮12.00", action)
            if count == 0:
                block = block.partition("PlayerEpsilon: folds\nPlayerGamma: RETURN")[0]
            error, rows = fourbet.analyze_hand(block, fourbet_args())
            self.assertIsNone(error)
            self.assertEqual(len(rows), count)
        for chips, expected in [("30.00", 1), ("29.99", 0)]:
            b = self.first.replace("PlayerGamma (₮80.00", f"PlayerGamma (₮{chips}")
            self.assertEqual(len(fourbet.analyze_hand(b, fourbet_args(min_stack_bb=60))[1]), expected)

    def test_partial_benchmark_and_exact_rate(self):
        spot = "BET_IP_VS_MISSED_FLOP_CB"
        config = self.root / "custom.json"
        config.write_text(json.dumps({spot: {"low": 40}}), encoding="utf-8-sig")
        settings = pool.load_benchmarks(str(config))
        self.assertEqual(settings[spot]["metric"], "bet_pct")
        self.assertEqual(settings[spot]["high"], pool.DEFAULT_BENCHMARKS[spot]["high"])
        row = dict(spot_id=spot, opportunities=1001, raw_action_counts='{"bet":400,"check":601}', bet_pct=40.0)
        self.assertEqual(pool.benchmark_flag(row, settings, 1)[0], "LOW")
        config.write_text(json.dumps({spot: {"low": 80, "high": 50}}), encoding="utf-8")
        with self.assertRaises(ValueError):
            pool.load_benchmarks(str(config))
