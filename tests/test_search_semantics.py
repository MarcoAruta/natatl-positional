import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from natatl_positional import (check, Game, Limits, ModelError, verify_strategy,
                               import_profile, InadmissibleStrategy)
from natatl_positional.guards import atom, TRUE
from natatl_positional.strategy import Rule, NaturalStrategy
from natatl_positional.temporal import prune
from tests.helpers import one_agent, game


ROOT = Path(__file__).resolve().parents[1]


class SearchSemantics(unittest.TestCase):
    def test_switch_budget_and_witness(self):
        model = ROOT/"examples/switch.txt"
        self.assertIs(check(model, "<{1},1>F goal")["satisfied"], False)
        result = check(model, "<{1},2>F goal")
        self.assertIs(result["satisfied"], True)
        self.assertEqual(result["witness_complexity"], 2)
        profile = import_profile(result, Game.load(model).propositions)
        self.assertTrue(verify_strategy(model, "<{1},2>F goal", profile)["verified"])

    def test_rejection_occurs_before_pruning(self):
        with patch("natatl_positional.search.prune", side_effect=AssertionError("must not prune")):
            result = check(ROOT/"examples/switch.txt", "<{1},2>F goal", compiler="pos2nat", trace=True)
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["statistics"]["temporal_checks"], 0)
        self.assertGreater(result["statistics"]["unresolved_rejections"], 0)
        for compiler in ("exact", "hybrid"):
            result = check(ROOT/"examples/switch.txt", "<{1},2>F goal", compiler=compiler, trace=True)
            for event in result["trace"]:
                if event["stage"] in {"pruning", "ctl"}:
                    self.assertLessEqual(event["cost"], 2)

    def test_raw_incompleteness_survives_negation(self):
        for formula in ("<{1},2>F goal", "!<{1},2>F goal",
                        "<{1},2>G (!<{1},2>F goal)"):
            result = check(ROOT/"examples/switch.txt", formula, compiler="pos2nat")
            self.assertEqual(result["status"], "unknown")
            self.assertIsNone(result["satisfied"])

    def test_raw_pos2nat_can_return_its_own_winning_witness(self):
        model = ROOT/"examples/switch.txt"
        result = check(model, "<{1},63>F goal", compiler="pos2nat")
        self.assertTrue(result["satisfied"])
        self.assertEqual(result["witness_complexity"], 63)
        profile = import_profile(result, Game.load(model).propositions)
        self.assertTrue(verify_strategy(model, "<{1},63>F goal", profile)["verified"])

    def test_all_opponent_moves_survive(self):
        model = ROOT/"examples/opponent.txt"
        self.assertFalse(check(model, "<{1},1>F goal")["satisfied"])
        self.assertTrue(check(model, "<{1,2},2>F goal")["satisfied"])
        g = Game.load(model)
        graph = prune(g, {s: ("GO",) for s in g.states}, (1,))
        self.assertEqual(graph["start"], {"goal", "trap"})
        self.assertFalse(check(model, "<{1},0>G safe")["satisfied"])
        self.assertTrue(check(model, "<{},0>G true")["satisfied"])

    def test_indistinguishable_states(self):
        result = check(ROOT/"examples/indistinguishable.txt", "<{1},4>F goal")
        self.assertFalse(result["satisfied"])
        self.assertEqual(result["statistics"]["label_classes"], 2)
        self.assertEqual(result["statistics"]["positional_space_size"], 4)
        self.assertEqual(result["statistics"]["unquotiented_positional_space_size"], 16)

    def test_global_and_operational_are_not_interchanged(self):
        model = ROOT/"examples/state_dependent_actions.txt"
        formula = "<{1},3>F goal"
        self.assertTrue(check(model, formula, appropriateness="first-match")["satisfied"])
        self.assertFalse(check(model, formula, appropriateness="global")["satisfied"])

    def test_nested_modalities_use_original_game(self):
        g = one_agent([(1, 2), (1, 1), (2, 2)], [set(), {"p"}, {"q"}], ("p", "q"))
        result = check(g, "(<{1},1>X p) && (<{1},1>X q)")
        self.assertTrue(result["satisfied"])
        self.assertEqual(len(result["modalities"]), 2)
        self.assertTrue(check(g, "<{1},1>X (<{1},1>F p)")["satisfied"])
        self.assertFalse(check(g, "!<{1},1>X p")["satisfied"])

    def test_initial_query_and_full_state_sets(self):
        initial = check(ROOT/"examples/switch.txt", "<{1},2>F goal")
        full = check(ROOT/"examples/switch.txt", "<{1},2>F goal", all_states=True)
        self.assertEqual(initial["satisfied"], full["satisfied"])
        self.assertTrue(full["state_set_complete"])
        self.assertEqual(full["satisfying_states"], ["goal", "middle", "start"])

    def test_resource_limits_preserve_unknown(self):
        model = ROOT/"examples/switch.txt"
        for compiler in ("exact", "hybrid"):
            for formula in ("<{1},2>F goal", "!<{1},2>F goal"):
                result = check(model, formula, compiler=compiler, limits=Limits(max_candidates=1))
                self.assertEqual(result["status"], "unknown")
        result = check(model, "<{1},2>F goal", compiler="exact",
                       limits=Limits(max_guard_masks=1))
        self.assertEqual(result["status"], "unknown")

    def test_malformed_input_is_not_a_negative_formula(self):
        with self.assertRaises(ModelError):
            Game.from_text("Transition\n0\nName_State\ns0\nInitial_State\ns0\n"
                           "Atomic_propositions\np\nLabelling\n1\nNumber_of_agents\n1")

    def test_undeclared_or_disabled_supplied_action_rejected(self):
        g = one_agent([(0, 0)], [set()])
        with self.assertRaises(InadmissibleStrategy):
            verify_strategy(g, "<{1},1>G true",
                            {1: NaturalStrategy((Rule(TRUE, "MISSING"),))})

    def test_cli_check_verify_and_convert(self):
        with tempfile.TemporaryDirectory() as tmp:
            result_file = Path(tmp)/"witness.json"
            commands = [
                ["check", "examples/switch.txt", "--formula", "<{1},2>F goal", "--output", str(result_file)],
                ["verify", "examples/switch.txt", "--formula", "<{1},2>F goal", "--witness", str(result_file)],
                ["convert", "examples/switch.txt", "--policy", "examples/switch_policy.json", "--coalition", "1", "--complete"],
            ]
            for command in commands:
                process = subprocess.run([sys.executable, "-m", "natatl_positional", *command],
                                         cwd=ROOT, capture_output=True, text=True, check=True)
                result = json.loads(process.stdout)
                self.assertTrue(result.get("whole_model_admissible", result.get("verified", result.get("satisfied"))))


class ExhaustiveTwoStateOracle(unittest.TestCase):
    def test_all_binary_deterministic_games(self):
        from itertools import product
        from tests.helpers import oracle_winners
        comparisons = 0
        for destinations in product(range(2), repeat=4):
            rows = [destinations[:2], destinations[2:]]
            for labels in product((frozenset(), frozenset({"p"})), repeat=2):
                g = one_agent(rows, labels)
                for bound in (1, 2, 3):
                    for op in ("X", "F", "G", "U", "W"):
                        left = set(g.states) if op in {"U", "W"} else g.valuation["p"]
                        right = g.valuation["p"] if op in {"U", "W"} else None
                        expected = oracle_winners(g, bound, op, left, right)
                        formula = f"<{{1}},{bound}>(true {op} p)" if right is not None else f"<{{1}},{bound}>{op} p"
                        for engine in ("positional", "classic"):
                            with self.subTest(destinations=destinations, labels=labels,
                                              k=bound, op=op, engine=engine):
                                result = check(g, formula, all_states=True, engine=engine,
                                               compiler="exact", cegar=True)
                                self.assertTrue(result["query_complete"])
                                self.assertEqual(set(result["satisfying_states"]), expected)
                                comparisons += 1
        self.assertEqual(comparisons, 1920)
