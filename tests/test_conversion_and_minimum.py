import unittest

from natatl_positional import InadmissibleStrategy, pos2nat, left_write, NaturalStrategy, Rule
from natatl_positional.guards import TRUE, atom
from natatl_positional.minimize import GuardTable, minimum_implementation
from natatl_positional.strategy import compile_profile, export_profile, import_profile
from tests.helpers import game, one_agent


class ConversionAndMinimum(unittest.TestCase):
    def setUp(self):
        self.game = one_agent([(1, 0), (1, 1)], [set(), {"p"}])
        self.policy = {"s0": ("A",), "s1": ("B",)}

    def test_left_write_prepends(self):
        base = NaturalStrategy((Rule(TRUE, "A"),))
        updated = left_write(base, atom("p"), "B")
        self.assertEqual(updated.action(frozenset({"p"})), "B")
        self.assertEqual(base.action(frozenset({"p"})), "A")

    def test_literal_algorithm_and_cost(self):
        c = pos2nat(self.game, self.policy, (1,), 1, complete=True)
        self.assertEqual(c.reachable_layers, (("s0",), ("s1",)))
        self.assertEqual([step["branch"] for step in c.trace], ["uncovered", "uncovered"])
        # V(s0)=!p, f0=(!p && !false) costs 5; psi0 costs 7.
        # f1=(p && !psi0) costs 10; default T costs 1.
        self.assertEqual(c.strategy.cost, 16)
        self.assertEqual(compile_profile(self.game, (1,), {1: c.strategy}), self.policy)

    def test_repeated_label_takes_overwrite_branch(self):
        g = one_agent([(1, 0), (2, 2), (2, 2)], [set(), {"p"}, {"p"}])
        policy = {"s0": ("A",), "s1": ("B",), "s2": ("B",)}
        c = pos2nat(g, policy, (1,), 1, complete=True)
        self.assertEqual(c.trace[-1]["branch"], "overwrite")
        self.assertEqual(c.strategy.cost, 17)
        self.assertEqual(compile_profile(g, (1,), {1: c.strategy}), policy)

    def test_conflicting_equal_labels_rejected(self):
        g = one_agent([(1, 0), (1, 1)], [set(), set()])
        with self.assertRaises(InadmissibleStrategy):
            pos2nat(g, self.policy, (1,), 1, complete=True)

    def test_whole_model_extension(self):
        g = one_agent([(0, 0), (1, 1)], [set(), {"p"}])
        c = pos2nat(g, self.policy, (1,), 1, complete=True)
        self.assertEqual(c.extended_states, ("s1",))
        self.assertEqual(compile_profile(g, (1,), {1: c.strategy}), self.policy)
        self.assertEqual(c.trace[-1]["phase"], "extension")

    def test_minimum_is_an_ordered_list(self):
        s = minimum_implementation(self.game, 1, ("A", "B"), 2)
        self.assertIsNotNone(s)
        self.assertEqual(s.cost, 2)
        self.assertEqual(s.rules[0].guard.text(), "p")
        self.assertEqual(s.rules[-1].guard.text(), "T")
        self.assertIsNone(minimum_implementation(self.game, 1, ("A", "B"), 1))
        self.assertEqual(minimum_implementation(self.game, 1, ("A", "A"), 1).cost, 1)

    def test_omitted_valuations_are_dont_cares(self):
        g = one_agent([(1, 0), (1, 1)], [set(), {"x", "y"}], ("x", "y"))
        strategy = minimum_implementation(g, 1, ("A", "B"), 2)
        self.assertEqual(strategy.cost, 2)
        self.assertIn(strategy.rules[0].guard.text(), {"x", "y"})

    def test_guard_table_shortest_costs(self):
        g = one_agent([(0, 0)]*4, [set(), {"x"}, {"y"}, {"x", "y"}], ("x", "y"))
        table = GuardTable(g)
        table.ensure(8)
        self.assertEqual(table.best[0b1000].cost, 3)  # x && y
        self.assertEqual(table.best[0b0110].cost, 8)  # (x||y) && !(x&&y)

    def test_witness_roundtrip(self):
        raw = pos2nat(self.game, self.policy, (1,), 1, complete=True).strategy
        data = export_profile({1: raw})
        restored = import_profile(data, self.game.propositions)
        self.assertEqual(restored[1].cost, raw.cost)
        self.assertEqual(compile_profile(self.game, (1,), restored), self.policy)

    def test_first_match_and_global(self):
        g = game([{("A",): "s0"}, {("B",): "s1"}], [{"p"}, set()])
        strategy = minimum_implementation(g, 1, ("A", "B"), 2)
        self.assertEqual(strategy.cost, 2)
        compile_profile(g, (1,), {1: strategy}, "first-match")
        with self.assertRaises(InadmissibleStrategy):
            compile_profile(g, (1,), {1: strategy}, "global")
        self.assertIsNone(minimum_implementation(g, 1, ("A", "B"), 20,
                                                appropriateness="global"))
