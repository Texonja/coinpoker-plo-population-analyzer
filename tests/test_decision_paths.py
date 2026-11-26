"""Expected records for complete flop–turn–river paths and deliberately broken histories."""

from collections import Counter
from itertools import product
import unittest

from poker_population_analytics import population as pool
from test_flop_cbet_logic import heads_up_hand
from test_population import population_args

CBET = "FOLD_TO_FLOP_CBET"
FLOP_STAB = "BET_IP_VS_MISSED_FLOP_CB"
FLOP_REPLY = "OOP_RESPONSE_VS_IP_FLOP_STAB_AFTER_MISSED_CB"
BARREL = "PFA_TURN_BARREL_AFTER_FLOP_CBET_CALLED"
TURN_REPLY = "FOLD_TO_TURN_BARREL_AFTER_FLOP_CALL"
RIVER_REPLY = "FOLD_TO_RIVER_BARREL_AFTER_FLOP_TURN_CALL"
TURN_STAB = "BET_IP_VS_MISSED_TURN_CB"
TURN_STAB_REPLY = "OOP_RESPONSE_VS_IP_TURN_STAB_AFTER_MISSED_CB"
PROBE = "TURN_PROBE_AFTER_FLOP_CHECKBACK"
PROBE_REPLY = "FOLD_TO_TURN_PROBE"


def history(ip_pfa, flop, turn="", river=""):
    block = heads_up_hand(178, pfa_ip=ip_pfa).partition("*** FLOP")[0]
    order = ("Hero", "Aggressor") if ip_pfa else ("Aggressor", "Hero")
    verbs = {"x": "checks", "b": "bets ₮1", "f": "folds", "c": "calls ₮1", "r": "raises ₮2 to ₮3", "C": "calls ₮2"}
    for label, board, actions in (
        ("FLOP", "[Ks 7h 2c]", flop),
        ("TURN", "[Ks 7h 2c] [8s]", turn),
        ("RIVER", "[Ks 7h 2c 8s] [6c]", river),
    ):
        if actions:
            block += f"*** {label} *** {board}\n"
            block += "".join(f"{order[i % 2]}: {verbs[a]}\n" for i, a in enumerate(actions))
    return block


def records(text, include_hero=True):
    hand = pool.parse_hand(text)
    return pool.extract_required_pool_records(hand, population_args(include_hero=include_hero, debug_players=True))


class DecisionPathTests(unittest.TestCase):
    def assert_nodes(self, text, expected):
        result = records(text)
        self.assertEqual(Counter((r["spot_id"], r["action"]) for r in result), Counter(expected))
        self.assertTrue(all(r["actor_ip_oop"] in {"IP", "OOP"} for r in result))
        self.assertEqual([r for r in result if r["actor"] != "Hero"], records(text, False))

    def test_three_barrels_both_positions_and_river_responses(self):
        for ip, (verb, response) in product((True, False), (("f", "fold"), ("c", "call"), ("r", "raise_or_allin"))):
            with self.subTest(ip=ip, response=response):
                first = "x" if ip else ""
                seq = first + "bc"
                self.assert_nodes(
                    history(ip, seq, seq, first + "b" + verb),
                    [(CBET, "call"), (BARREL, "bet"), (TURN_REPLY, "call"), (RIVER_REPLY, response)],
                )

    def test_turn_stab_and_checkraise_two_actors_three_nodes(self):
        self.assert_nodes(
            history(False, "bc", "xbrf"),
            [
                (CBET, "call"),
                (BARREL, "check"),
                (TURN_STAB, "bet"),
                (TURN_STAB_REPLY, "raise_or_allin"),
                ("FOLD_TO_TURN_CHECK_RAISE", "fold"),
            ],
        )
        self.assert_nodes(
            history(False, "xbrC"),
            [(FLOP_STAB, "bet"), (FLOP_REPLY, "raise_or_allin"), ("FOLD_TO_FLOP_CHECK_RAISE", "call")],
        )

    def test_delayed_bets_and_probe_have_different_initiators(self):
        self.assert_nodes(
            history(False, "xx", "bc"),
            [(FLOP_STAB, "check"), ("DELAYED_CBET_OOP", "bet"), ("FOLD_TO_DELAYED_CBET_IP", "call")],
        )
        self.assert_nodes(
            history(True, "xx", "xbc"),
            [(PROBE, "check"), ("DELAYED_CBET_IP", "bet"), ("FOLD_TO_DELAYED_CBET_OOP", "call")],
        )
        self.assert_nodes(history(True, "xx", "bf"), [(PROBE, "bet"), (PROBE_REPLY, "fold")])
        self.assert_nodes(history(True, "xbc", "bf"), [(CBET, "call")])

    def test_malformed_and_partial_rounds_keep_valid_prior_decisions(self):
        good = history(False, "bc", "bf")
        for old, new in [
            ("Aggressor: bets ₮1\nHero: folds", "Hero: bets ₮1\nAggressor: calls ₮1"),
            ("Hero: folds", "Hero: checks"),
            ("Hero: folds", "Hero: calls ₮3"),
            ("Hero: folds", "Hero: folds\nHero: folds"),
        ]:
            with self.subTest(new=new):
                self.assert_nodes(good.replace(old, new), [(CBET, "call")])
        self.assert_nodes(history(False, "xb"), [(FLOP_STAB, "bet")])
        self.assert_nodes(history(False, "xb", "bc"), [(FLOP_STAB, "bet")])
        self.assert_nodes(history(False, "b"), [])

    def test_allin_and_runout_do_not_create_check_opportunities(self):
        hand = history(False, "bc", "xx").replace("Aggressor: bets ₮1", "Aggressor: ALLIN ₮1")
        self.assert_nodes(hand, [(CBET, "call")])
        hand = history(False, "bc").replace("Hero: calls ₮1\n", "Hero: ALLIN ₮1\n")
        self.assert_nodes(hand, [(CBET, "call")])

    def test_498_legal_paths_preserve_opportunities_and_action_domains(self):
        endings = ["bf", "xbf", "brf", "xbrf"]
        continues = ["xx", "bc", "xbc", "brC", "xbrC"]
        paths = [(f, "", "") for f in endings]
        paths += [(f, t, "") for f in continues for t in endings]
        paths += [(f, t, r) for f, t, r in product(continues, continues, endings + continues)]
        covered = set()
        for ip, (flop, turn, river) in product((False, True), paths):
            with self.subTest(ip=ip, flop=flop, turn=turn, river=river):
                rows = records(history(ip, flop, turn, river))
                spots = {r["spot_id"]: r for r in rows}
                self.assertEqual(len(rows), len(spots))
                covered.update(spots)
                for r in rows:
                    domain = (
                        {"bet", "check"}
                        if pool.DEFAULT_BENCHMARKS[r["spot_id"]]["metric"] == "bet_pct"
                        else {"fold", "call", "raise_or_allin"}
                    )
                    self.assertIn(r["action"], domain)
                    self.assertIn(r["actor_ip_oop"], {"IP", "OOP"})
                pfa_bet = "xb" if ip else "b"
                self.assertEqual(CBET in spots, flop.startswith(pfa_bet))
                self.assertEqual(FLOP_STAB in spots, not ip and flop.startswith("x"))
                self.assertEqual(FLOP_REPLY in spots, not ip and flop.startswith("xb"))
                self.assertEqual(PROBE in spots, ip and flop == "xx")
                self.assertEqual(PROBE_REPLY in spots, ip and flop == "xx" and turn.startswith("b"))
                self.assertEqual(TURN_STAB in spots, not ip and flop == "bc" and turn.startswith("x"))
                self.assertEqual(TURN_STAB_REPLY in spots, not ip and flop == "bc" and turn.startswith("xb"))
                called = pfa_bet + "c"
                self.assertEqual(BARREL in spots, flop == called and (not ip or turn.startswith("x")))
                self.assertEqual(TURN_REPLY in spots, flop == called and turn.startswith(pfa_bet))
                self.assertEqual(RIVER_REPLY in spots, flop == turn == called and river.startswith(pfa_bet))
                self.assertEqual("FOLD_TO_FLOP_CHECK_RAISE" in spots, flop.startswith("xbr"))
                self.assertEqual("FOLD_TO_TURN_CHECK_RAISE" in spots, turn.startswith("xbr"))
                role, other = ("IP", "OOP") if ip else ("OOP", "IP")
                self.assertEqual("DELAYED_CBET_" + role in spots, flop == "xx" and (not ip or turn.startswith("x")))
                self.assertEqual("FOLD_TO_DELAYED_CBET_" + other in spots, flop == "xx" and turn.startswith(pfa_bet))
        self.assertEqual(len(paths) * 2, 498)
        self.assertEqual(covered, set(pool.DEFAULT_BENCHMARKS))

    def test_invalid_boards_are_rejected_individually(self):
        good = history(False, "bc", "bf")
        for before, after in [
            ("[Ks 7h 2c]", "[Zz 7h 2c]"),
            ("[Ks 7h 2c]", "[Ks Ks 2c]"),
            ("[Ks 7h 2c]", "[Ks 7h]"),
            ("[Ks 7h 2c] [8s]", "[Kh 7h 2c] [8s]"),
            ("[Ks 7h 2c]", "[As 7h 2c]"),
        ]:
            with self.subTest(after=after):
                self.assertIsNone(pool.parse_hand(good.replace(before, after)))
