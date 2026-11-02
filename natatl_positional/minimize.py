"""Exact bounded implementation on the valuations occurring in a fixed CGS.

First find a cheapest guard for each observed truth mask by increasing formula
cost. Then use dynamic programming over the remaining uncovered label classes.
The output is a decision LIST, not independently minimized per-action formulas.
"""
from __future__ import annotations

from functools import lru_cache

from .errors import ResourceLimit
from .guards import TRUE, FALSE, atom, neg, conjunction, disjunction
from .limits import RunBudget
from .strategy import NaturalStrategy, Rule


class GuardTable:
    def __init__(self, game, budget=None):
        self.game = game
        self.budget = budget or RunBudget()
        self.full_mask = (1 << len(game.label_classes)) - 1
        self.best = {}
        self.by_cost = {}
        self.complete_through = 0
        self.operations = 0

    def _add(self, cost, mask, guard):
        if mask in self.best:
            return
        maximum = self.budget.limits.max_guard_masks
        if maximum is not None and len(self.best) >= maximum:
            raise ResourceLimit("Guard-mask limit reached")
        self.best[mask] = guard
        self.by_cost.setdefault(cost, []).append((mask, guard))

    def _tick(self):
        self.operations += 1
        if self.operations % 256 == 0:
            self.budget.check_time()

    def ensure(self, bound):
        for cost in range(self.complete_through + 1, bound + 1):
            self.budget.check_time()
            self.by_cost.setdefault(cost, [])
            if cost == 1:
                self._add(1, self.full_mask, TRUE)
                self._add(1, 0, FALSE)
                for prop in self.game.propositions:
                    mask = sum(1 << i for i, group in enumerate(self.game.label_classes)
                               if prop in self.game.labels[group[0]])
                    self._add(1, mask, atom(prop))
            else:
                for mask, guard in self.by_cost.get(cost-1, []):
                    self._tick()
                    self._add(cost, self.full_mask ^ mask, neg(guard))
                for left_cost in range(1, (cost-1)//2 + 1):
                    right_cost = cost-1-left_cost
                    lefts = self.by_cost.get(left_cost, [])
                    rights = self.by_cost.get(right_cost, [])
                    for i, (lm, lg) in enumerate(lefts):
                        start = i if left_cost == right_cost else 0
                        for rm, rg in rights[start:]:
                            self._tick()
                            self._add(cost, lm & rm, conjunction(lg, rg))
                            self._add(cost, lm | rm, disjunction(lg, rg))
            self.complete_through = cost
            # Once every observed mask has a representative, no cheaper
            # representative can appear at a later (larger) cost.
            if len(self.best) == (1 << len(self.game.label_classes)):
                self.complete_through = max(bound, self.complete_through)
                break


def minimum_implementation(game, agent, target_actions, bound, *,
                           appropriateness="first-match", table=None, budget=None):
    """Minimum representation if its cost is <= bound; otherwise None.

    target_actions has one action per observed label class. A negative result is
    exact only after this function returns normally, never after ResourceLimit.
    """
    if appropriateness not in {"first-match", "global"}:
        raise ValueError("Unknown appropriateness mode")
    if len(target_actions) != len(game.label_classes):
        raise ValueError("One target action per label class is required")
    if bound < 1:
        return None
    budget = budget or (table.budget if table else RunBudget())
    table = table or GuardTable(game, budget)
    if table.game is not game:
        raise ValueError("Guard tables must not be shared between games")
    available = set().union(*(game.enabled[s][agent-1] for s in game.states))
    allowed, desired = {}, {}
    for action in sorted(available):
        allowed[action] = sum(1 << i for i, group in enumerate(game.label_classes)
                              if all(action in game.enabled[s][agent-1] for s in group))
        desired[action] = sum(1 << i for i, a in enumerate(target_actions) if a == action)
    for i, action in enumerate(target_actions):
        if not (allowed.get(action, 0) & (1 << i)):
            return None
    common = [a for a in sorted(available) if allowed[a] == table.full_mask]
    if appropriateness == "global" and not common:
        return None  # the mandatory T rule cannot be globally appropriate
    if len(set(target_actions)) == 1:
        action = target_actions[0]
        if appropriateness == "first-match" or action in common:
            return NaturalStrategy((Rule(TRUE, action),))
    table.ensure(max(0, bound-1))
    guards = sorted(table.best.items(), key=lambda item: (item[1].cost, -item[0].bit_count(), item[0]))
    calls = 0

    @lru_cache(None)
    def solve(remaining, cap):
        nonlocal calls
        calls += 1
        budget.check_time()
        maximum = budget.limits.max_dp_states
        if maximum is not None and calls > maximum:
            raise ResourceLimit("Decision-list DP limit reached")
        if cap < 1:
            return None
        # The terminal rule must be syntactically T, and contributes one.
        for action in sorted(available):
            if remaining & ~desired[action] == 0:
                if appropriateness == "first-match" or action in common:
                    return NaturalStrategy((Rule(TRUE, action),))
        best = None
        ceiling = cap + 1
        for mask, guard in guards:
            if guard.cost + 1 >= ceiling or guard.cost + 1 > cap:
                continue
            newly = remaining & mask
            if not newly:
                continue
            i = (newly & -newly).bit_length()-1
            action = target_actions[i]
            if newly & ~desired[action]:
                continue
            if appropriateness == "global" and mask & ~allowed[action]:
                continue
            tail_cap = min(cap-guard.cost, ceiling-guard.cost-1)
            tail = solve(remaining ^ newly, tail_cap)
            if tail is not None:
                candidate = NaturalStrategy((Rule(guard, action),) + tail.rules)
                if candidate.cost < ceiling:
                    best, ceiling = candidate, candidate.cost
        return best

    try:
        return solve(table.full_mask, bound)
    except RecursionError as exc:
        raise ResourceLimit("Decision-list DP recursion limit reached") from exc
