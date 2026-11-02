from itertools import product
from pathlib import Path
import random
import unittest

from natatl_positional import Game, check
from natatl_positional.refinement import learn_nogood
from natatl_positional.search import positional_policies
from natatl_positional.temporal import prune, universal_temporal_states, counterexample
from tests.helpers import game, one_agent, oracle_temporal, oracle_winners


ROOT = Path(__file__).resolve().parents[1]


class RefinementAndBroaderInputs(unittest.TestCase):
    def test_every_learned_nogood_preserves_a_violating_path(self):
        # All policies in this game, all starts, both operands varied. A learned
        # constraint is checked against every alternative matching policy using
        # independent reachability/cycle semantics (not the production fixpoint).
        g = one_agent([(1, 2), (2, 0), (2, 1)], [set(), {"p"}, {"q"}], ("p", "q"))
        policies = list(positional_policies(g, (1,)))
        for signature, policy in policies:
            graph = prune(g, policy, (1,))
            for op in ("X", "F", "G", "U", "W"):
                left = g.valuation["p"]
                right = g.valuation["q"] if op in {"U", "W"} else None
                winning = universal_temporal_states(graph, op, left, right)
                for start in set(g.states)-winning:
                    cert = counterexample(graph, start, op, left, right, winning)
                    constraint, enriched = learn_nogood(g, policy, (1,), cert)
                    self.assertEqual(len(enriched["joint_actions"]), len(cert["path"])-1)
                    for other_signature, other_policy in policies:
                        if constraint.matches(other_signature):
                            other_graph = prune(g, other_policy, (1,))
                            self.assertFalse(oracle_temporal(other_graph, start, op, left, right))

    def test_cegar_is_observationally_equivalent(self):
        model = ROOT/"examples/switch.txt"
        with_cegar = check(model, "<{1},2>F goal", all_states=True)
        without = check(model, "<{1},2>F goal", all_states=True, cegar=False)
        self.assertEqual(with_cegar["satisfying_states"], without["satisfying_states"])
        self.assertGreater(with_cegar["statistics"]["cegar_candidates_skipped"], 0)
        self.assertLess(with_cegar["statistics"]["temporal_checks"], without["statistics"]["temporal_checks"])

    def test_random_nonconstant_protocols_against_syntax_oracle(self):
        rng = random.Random(24019)
        comparisons = 0
        for _ in range(24):
            rows, labels = [], []
            for i in range(3):
                actions = ("A",) if rng.random() < .2 else ("B",) if rng.random() < .2 else ("A", "B")
                rows.append({(a,): f"s{rng.randrange(3)}" for a in actions})
                labels.append({p for p in ("p", "q") if rng.random() < .5})
            g = game(rows, labels, ("p", "q"))
            for mode in ("first-match", "global"):
                for op in ("F", "U", "W"):
                    left = g.valuation["p"]
                    right = g.valuation["q"] if op in {"U", "W"} else None
                    formula = f"<{{1}},4>(p {op} q)" if right is not None else "<{1},4>F p"
                    expected = oracle_winners(g, 4, op, left, right, mode)
                    result = check(g, formula, appropriateness=mode, all_states=True)
                    self.assertTrue(result["query_complete"])
                    self.assertEqual(set(result["satisfying_states"]), expected)
                    comparisons += 1
        self.assertEqual(comparisons, 144)

    def test_random_multiagent_against_classic_generator(self):
        rng = random.Random(11)
        comparisons = 0
        for _ in range(12):
            rows = [{joint: f"s{rng.randrange(3)}" for joint in product(("A", "B"), repeat=2)}
                    for _ in range(3)]
            labels = [{p for p in ("p", "q") if rng.random() < .5} for _ in range(3)]
            g = game(rows, labels, ("p", "q"), agents=2)
            for coalition, bound in (("1", 2), ("2", 3), ("1,2", 3)):
                for op in ("X", "F", "G", "U", "W"):
                    formula = (f"<{{{coalition}}},{bound}>(p {op} q)" if op in {"U", "W"}
                               else f"<{{{coalition}}},{bound}>{op} p")
                    a = check(g, formula, all_states=True, compiler="exact")
                    b = check(g, formula, all_states=True, engine="classic")
                    self.assertTrue(a["query_complete"] and b["query_complete"])
                    self.assertEqual(a["satisfying_states"], b["satisfying_states"])
                    comparisons += 1
        self.assertEqual(comparisons, 180)

    def test_supplied_deterministic_vitamin_models(self):
        for filename in ("vitamin_two_states.txt", "vitamin_nominal.txt"):
            g = Game.load(ROOT/"examples"/filename)
            for bound in (1, 2, 3):
                formula = f"<{{1}},{bound}>F a"
                new = check(g, formula, all_states=True)
                classic = check(g, formula, engine="classic", all_states=True)
                self.assertEqual(new["satisfying_states"], classic["satisfying_states"])
