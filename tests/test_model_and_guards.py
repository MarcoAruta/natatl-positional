import json
from pathlib import Path
import unittest

from natatl_positional import Game, ModelError
from natatl_positional.errors import FormulaError
from natatl_positional.formulas import parse_formula
from natatl_positional.guards import parse_guard, export_dag, import_dag, valuation_guard
from natatl_positional.model import parse_cell


ROOT = Path(__file__).resolve().parents[1]


class ModelAndGuards(unittest.TestCase):
    def test_nominal_actions_and_arity(self):
        self.assertEqual(parse_cell("MOVE_FORWARD", 1), [("MOVE_FORWARD",)])
        self.assertEqual(parse_cell("AC,IDLE|BLOCK", 2), [("A", "C"), ("IDLE", "BLOCK")])
        self.assertEqual(parse_cell("II", 2), [("IDLE", "IDLE")])
        for cell, n in [("A", 2), ("ABC", 2), ("A|", 2), ("A,", 1), ("*", 1)]:
            with self.subTest(cell=cell), self.assertRaises(ModelError):
                parse_cell(cell, n)

    def test_json_roundtrip(self):
        original = Game.load(ROOT/"examples/opponent.txt")
        loaded = Game.from_dict(json.loads(json.dumps(original.to_dict())))
        self.assertEqual(original.to_dict(), loaded.to_dict())

    def test_malformed_json_shapes_are_model_errors(self):
        original = Game.load(ROOT/"examples/opponent.txt")
        for key, value in (("states", "start"), ("labels", []), ("transitions", [])):
            data = original.to_dict()
            data[key] = value
            with self.assertRaises(ModelError):
                Game.from_dict(data)
        data = original.to_dict()
        data["transitions"]["start"][0]["actions"] = "AB"
        with self.assertRaises(ModelError):
            Game.from_dict(data)

    def test_lowercase_t_is_an_atom(self):
        g = Game.from_dict({"states": ["s0"], "propositions": ["t"],
                            "number_of_agents": 1, "initial_state": "s0",
                            "labels": {"s0": ["t"]},
                            "transitions": {"s0": [{"actions": ["A"], "to": "s0"}]}})
        self.assertTrue(parse_guard("t", g.propositions).evaluate(g.labels["s0"]))

    def test_invalid_transitions_are_errors(self):
        g = Game.load(ROOT/"examples/opponent.txt")
        for mutate in ("missing", "nondeterministic", "deadlock", "unknown"):
            d = g.to_dict()
            if mutate == "missing":
                d["transitions"]["start"].pop()
            elif mutate == "nondeterministic":
                d["transitions"]["start"].append({"actions": ["GO", "ALLOW"], "to": "trap"})
            elif mutate == "deadlock":
                d["transitions"]["start"] = []
            else:
                d["labels"]["start"] = ["undeclared"]
            with self.subTest(mutate=mutate), self.assertRaises(ModelError):
                Game.from_dict(d)

    def test_binary_labels_and_duplicate_sections(self):
        text = (ROOT/"examples/switch.txt").read_text()
        for bad in (text.replace("0 1\n", "0 2\n"), text + "\nInitial_State\nstart\n"):
            with self.assertRaises(ModelError):
                Game.from_text(bad)

    def test_guard_cost_and_dag(self):
        g = parse_guard("(x && y) || !x", {"x", "y"})
        self.assertEqual(g.cost, 6)
        self.assertTrue(g.evaluate(frozenset()))
        self.assertFalse(g.evaluate(frozenset({"x"})))
        nodes, roots = export_dag([g])
        restored = import_dag(nodes)[roots[0]]
        self.assertEqual(restored.cost, 6)
        self.assertEqual(restored.text(), g.text())
        with self.assertRaises(FormulaError):
            import_dag([{"op": "not", "args": [0]}])

    def test_full_valuation_is_not_positive_subset(self):
        g = valuation_guard(("x", "y"), frozenset({"x"}))
        self.assertTrue(g.evaluate(frozenset({"x"})))
        self.assertFalse(g.evaluate(frozenset({"x", "y"})))
        self.assertEqual(g.cost, 4)

    def test_temporal_looking_atoms_are_boolean(self):
        for p in ("G", "E", "AF"):
            self.assertTrue(parse_guard(p, {p}).evaluate(frozenset({p})))
            self.assertEqual(parse_formula(f"<{{1}},2>F {p}", 1, {p}).children[0].name, p)

    def test_formula_surface_and_invalid_inputs(self):
        for formula in ("<{1},4>F goal", "<{1},4>Fgoal", "<{1},4>EVENTUALLY goal",
                        "<{1},4>GLOBALLY goal", "<{1},4>(p U goal)",
                        "<{1},4>(p W goal)", "<{},0>X goal",
                        "!<{1},2>F (<{1},1>X goal)"):
            with self.subTest(formula=formula):
                parse_formula(formula, 1, {"goal", "p"})
        for formula in ("<{1,1},2>F p", "<{2},1>F p", "<{1},-1>F p",
                        "<{1},2>F missing", "<{1},2>p U goal", "AF p"):
            with self.subTest(formula=formula), self.assertRaises(FormulaError):
                parse_formula(formula, 1, {"p", "goal"})
