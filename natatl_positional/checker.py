"""Compositional state-set semantics with sound propagation of UNKNOWN."""
from __future__ import annotations

from dataclasses import dataclass
import time

from .errors import FormulaError
from .formulas import parse_formula
from .limits import Limits, RunBudget
from .minimize import GuardTable
from .model import Game
from .search import search_modality
from .strategy import compile_profile, export_profile, profile_cost
from .temporal import prune, universal_temporal_states


@dataclass(frozen=True)
class Truth:
    lower: frozenset[str]
    upper: frozenset[str]

    def at(self, state):
        return True if state in self.lower else (False if state not in self.upper else None)


class Checker:
    def __init__(self, game, *, compiler="hybrid", engine="positional",
                 appropriateness="first-match", cegar=True, limits=None, trace=False):
        self.game = game
        self.compiler = compiler
        self.engine = engine
        self.appropriateness = appropriateness
        self.cegar = cegar
        self.trace = trace
        self.budget = RunBudget(limits)
        self.table = GuardTable(game, self.budget)
        self.universe = frozenset(game.states)
        self.memo = {}
        self.modal_results = {}

    def evaluate(self, node, wanted=None):
        full = wanted is None or set(wanted) == set(self.universe)
        if full and node in self.memo:
            return self.memo[node]
        op = node.op
        if op in {"atom", "true", "false"}:
            value = (self.universe if op == "true" else frozenset() if op == "false"
                     else frozenset(s for s in self.game.states if node.name in self.game.labels[s]))
            result = Truth(value, value)
        elif op == "not":
            child = self.evaluate(node.children[0])
            result = Truth(self.universe-child.upper, self.universe-child.lower)
        elif op in {"and", "or", "implies"}:
            a, b = (self.evaluate(child) for child in node.children)
            if op == "and":
                result = Truth(a.lower & b.lower, a.upper & b.upper)
            elif op == "or":
                result = Truth(a.lower | b.lower, a.upper | b.upper)
            else:
                result = Truth((self.universe-a.upper) | b.lower,
                               (self.universe-a.lower) | b.upper)
        else:
            # Always evaluate nested operands in the ORIGINAL game, and with
            # their own coalition/budget, never in a candidate's pruned graph.
            a = self.evaluate(node.children[0])
            b = self.evaluate(node.children[1]) if len(node.children) == 2 else None
            modal = search_modality(
                self.game, node.coalition, node.bound, op, set(a.lower), set(a.upper),
                None if b is None else set(b.lower), None if b is None else set(b.upper),
                wanted=wanted, compiler=self.compiler, engine=self.engine,
                appropriateness=self.appropriateness, cegar=self.cegar,
                budget=self.budget, guard_table=self.table, trace=self.trace)
            self.modal_results[node] = modal
            lower, upper = frozenset(modal.lower), frozenset(modal.upper)
            if not full:
                upper |= self.universe-frozenset(wanted)
            result = Truth(lower, upper)
        if full:
            self.memo[node] = result
        return result

    def check(self, formula, *, all_states=False):
        root = parse_formula(formula, self.game.number_of_agents, self.game.propositions)
        is_modal = root.op in {"X", "F", "G", "U", "W"}
        wanted = set(self.game.states) if all_states else {self.game.initial_state}
        truth = self.evaluate(root, wanted=None if all_states or not is_modal else wanted)
        decision = truth.at(self.game.initial_state)
        result = {
            "status": "true" if decision is True else "false" if decision is False else "unknown",
            "satisfied": decision,
            "formula": root.text(), "initial_state": self.game.initial_state,
            "engine": self.engine, "compiler": self.compiler,
            "appropriateness": self.appropriateness,
            "queried_states": sorted(wanted),
            "definitely_satisfying_states": sorted(truth.lower & wanted),
            "definitely_failing_states": sorted(wanted-truth.upper),
            "unknown_states": sorted((truth.upper-truth.lower) & wanted),
            "query_complete": not bool((truth.upper-truth.lower) & wanted),
            "state_set_complete": truth.lower == truth.upper,
            "winning_strategy": None,
            "modalities": [],
        }
        if truth.lower == truth.upper:
            result["satisfying_states"] = sorted(truth.lower)
        if is_modal:
            result["complexity_bound"] = root.bound
            modal = self.modal_results[root]
            if decision is True:
                profile = modal.witnesses[self.game.initial_state]
                selected = compile_profile(self.game, root.coalition, profile, self.appropriateness)
                result["winning_strategy"] = export_profile(profile, selected)
                result["witness_complexity"] = profile_cost(profile)
            result["statistics"] = modal.statistics
            if self.trace:
                result["trace"] = modal.events
            result["counterexamples"] = modal.counterexamples
        for node, modal in self.modal_results.items():
            result["modalities"].append({
                "formula": node.text(), "coalition": list(node.coalition), "bound": node.bound,
                "definite_winners": sorted(modal.lower),
                "possible_winners": sorted(modal.upper),
                "statistics": modal.statistics, "notes": modal.reasons,
            })
        result["elapsed_seconds"] = time.monotonic()-self.budget.started
        return result


def check(game_or_path, formula, *, all_states=False, **options):
    game = game_or_path if isinstance(game_or_path, Game) else Game.load(game_or_path)
    return Checker(game, **options).check(formula, all_states=all_states)


def verify_strategy(game, formula, profile, *, appropriateness="first-match"):
    """Check an externally supplied witness independently of positional search.

    Nested operands use the exact bounded backend. Incomplete nested results
    cannot certify a supplied strategy and yield status unknown.
    """
    if not isinstance(game, Game):
        game = Game.load(game)
    root = parse_formula(formula, game.number_of_agents, game.propositions)
    if root.op not in {"X", "F", "G", "U", "W"}:
        raise FormulaError("Witness verification requires a top-level strategic modality")
    selected = compile_profile(game, root.coalition, profile, appropriateness)
    cost = profile_cost(profile)
    if cost > root.bound:
        return {"status": "false", "verified": False, "cost": cost,
                "reason": "Witness exceeds the complexity bound"}
    checker = Checker(game, compiler="exact", appropriateness=appropriateness)
    a = checker.evaluate(root.children[0])
    b = checker.evaluate(root.children[1]) if len(root.children) == 2 else None
    graph = prune(game, selected, root.coalition)
    lower = universal_temporal_states(graph, root.op, set(a.lower), None if b is None else set(b.lower))
    upper = universal_temporal_states(graph, root.op, set(a.upper), None if b is None else set(b.upper))
    initial = game.initial_state
    verified = True if initial in lower else False if initial not in upper else None
    return {"status": "true" if verified is True else "false" if verified is False else "unknown",
            "verified": verified, "cost": cost,
            "satisfying_states": sorted(lower) if lower == upper else None}
