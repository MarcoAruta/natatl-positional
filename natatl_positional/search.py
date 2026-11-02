"""Positional guess -> natural implementation -> budget -> pruning -> CTL.

The optional classic engine is the supplied lazy NatATL generator, isolated
from the VITAMIN UI. It is a comparator, not the new default search space.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from math import prod

from .errors import InadmissibleStrategy, ResourceLimit
from .guards import parse_guard
from .limits import RunBudget
from .minimize import GuardTable, minimum_implementation
from .pos2nat import pos2nat, reachability_layers
from .refinement import learn_nogood
from .strategy import NaturalStrategy, Rule, compile_profile, profile_cost
from .temporal import prune, universal_temporal_states, counterexample


@dataclass
class ModalResult:
    lower: set[str] = field(default_factory=set)
    upper: set[str] = field(default_factory=set)
    witnesses: dict = field(default_factory=dict)
    statistics: dict = field(default_factory=dict)
    counterexamples: list = field(default_factory=list)
    events: list = field(default_factory=list)
    reasons: list = field(default_factory=list)


def policy_space(game, coalition):
    dimensions = []
    for group in game.label_classes:
        for agent in coalition:
            common = set.intersection(*(set(game.enabled[s][agent-1]) for s in group))
            dimensions.append(tuple(sorted(common, key=lambda a: (a != "IDLE", a))))
    return tuple(dimensions)


def positional_policies(game, coalition, dimensions=None):
    dimensions = policy_space(game, coalition) if dimensions is None else dimensions
    width = len(coalition)
    for assignment in product(*dimensions):
        signature = tuple(tuple(assignment[i*width:(i+1)*width])
                          for i in range(len(game.label_classes)))
        policy = {s: signature[game.class_of[s]] for s in game.states}
        yield signature, policy


def search_modality(game, coalition, bound, op, left_lower, left_upper,
                    right_lower=None, right_upper=None, *, wanted=None,
                    compiler="hybrid", engine="positional", appropriateness="first-match",
                    cegar=True, budget=None, guard_table=None, trace=False):
    """Return definite and possible truth sets, preserving incomplete decisions."""
    if compiler not in {"pos2nat", "exact", "hybrid"}:
        raise ValueError("compiler must be pos2nat, exact, or hybrid")
    if engine not in {"positional", "classic"}:
        raise ValueError("engine must be positional or classic")
    if appropriateness not in {"first-match", "global"}:
        raise ValueError("Unknown appropriateness mode")
    coalition = tuple(coalition)
    if (len(set(coalition)) != len(coalition)
            or any(type(a) is not int or not 1 <= a <= game.number_of_agents for a in coalition)
            or type(bound) is not int or bound < 0):
        raise ValueError("Invalid coalition or strategy bound")
    universe = set(game.states)
    wanted = universe if wanted is None else set(wanted)
    if not wanted <= universe:
        raise ValueError("Unknown requested state")
    result = ModalResult()
    stats = result.statistics
    stats.update(candidates_examined=0, duplicate_policies_skipped=0,
                 cegar_candidates_skipped=0, pos2nat_conversions=0,
                 exact_compilations=0, cost_rejections=0,
                 raw_budget_failures=0,
                 unresolved_rejections=0, pruned_models=0, temporal_checks=0,
                 nogoods_learned=0, raw_cost_min=None, raw_cost_max=None,
                 enumeration_exhausted=False)
    budget = budget or RunBudget()
    table = guard_table or GuardTable(game, budget)
    nogoods = {s: set() for s in wanted}
    dimensions = policy_space(game, coalition)
    stats["label_classes"] = len(game.label_classes)
    stats["positional_space_size"] = prod(len(d) for d in dimensions)
    stats["unquotiented_positional_space_size"] = prod(
        len(game.enabled[s][a-1]) for s in game.states for a in coalition)
    if bound < len(coalition):
        stats["enumeration_exhausted"] = True
        result.reasons.append("Budget is below the mandatory fallback cost")
        return result
    if appropriateness == "global" and any(
        not set.intersection(*(set(game.enabled[s][a-1]) for s in game.states))
        for a in coalition
    ):
        stats["enumeration_exhausted"] = True
        result.reasons.append("No globally enabled action for a mandatory T fallback")
        return result

    def event(stage, **details):
        if trace and len(result.events) < 2000:
            result.events.append(dict(candidate=stats["candidates_examined"], stage=stage, **details))

    def exact_profile(signature):
        stats["exact_compilations"] += 1
        profile = {}
        individual_bound = bound-len(coalition)+1
        for index, agent in enumerate(coalition):
            actions = tuple(row[index] for row in signature)
            strategy = minimum_implementation(
                game, agent, actions, individual_bound,
                appropriateness=appropriateness, table=table, budget=budget)
            if strategy is None:
                return None
            profile[agent] = strategy
        return profile if profile_cost(profile) <= bound else None

    def unresolved(states, reason):
        result.upper.update(states)
        stats["unresolved_rejections"] += 1
        if reason not in result.reasons:
            result.reasons.append(reason)

    def consider(signature, policy, supplied=None):
        pending = wanted-result.lower
        blocked = {s for s in pending if any(n.matches(signature) for n in nogoods[s])}
        if cegar and pending and blocked == pending:
            stats["cegar_candidates_skipped"] += 1
            event("counterexample_constraint")
            return
        profile = supplied
        route = "classic" if supplied is not None else compiler
        if profile is None and compiler in {"pos2nat", "hybrid"}:
            # G' is consulted implicitly for marking. No pruned CTL graph is
            # allocated here. Whole-model extension follows the reachable part.
            layers = reachability_layers(game, policy, coalition)
            profile = {}
            for agent in coalition:
                converted = pos2nat(game, policy, coalition, agent, layers=layers,
                                   complete=True, record_trace=trace)
                profile[agent] = converted.strategy
                stats["pos2nat_conversions"] += 1
            cost = profile_cost(profile)
            stats["raw_cost_min"] = cost if stats["raw_cost_min"] is None else min(cost, stats["raw_cost_min"])
            stats["raw_cost_max"] = cost if stats["raw_cost_max"] is None else max(cost, stats["raw_cost_max"])
            event("pos2nat", cost=cost,
                  reachable_layers=[list(layer) for layer in layers])
            raw_legal = False
            if cost <= bound:
                try:
                    selected = compile_profile(game, coalition, profile, appropriateness)
                    if selected != policy:
                        raise AssertionError("POS2NAT failed its implementation invariant")
                    raw_legal = True
                except InadmissibleStrategy:
                    pass
            else:
                stats["raw_budget_failures"] += 1
            if cost > bound or not raw_legal:
                if compiler == "pos2nat":
                    stats["cost_rejections"] += int(cost > bound)
                    unresolved(pending-blocked,
                               "Raw POS2NAT is not a minimum-cost implementation")
                    event("unresolved_rejection", cost=cost)
                    return
                profile = None
                route = "exact-fallback"
        if profile is None:
            profile = exact_profile(signature)
            if profile is None:
                stats["cost_rejections"] += 1
                event("no_implementation_within_budget")
                return
        cost = profile_cost(profile)
        if cost > bound:
            raise AssertionError("An over-budget strategy reached pruning")
        selected = compile_profile(game, coalition, profile, appropriateness)
        if selected != policy:
            raise AssertionError("Natural implementation disagrees with positional policy")
        event("admissible", cost=cost, compiler=route)
        budget.check_time()
        graph = prune(game, selected, coalition)
        stats["pruned_models"] += 1
        event("pruning", cost=cost)
        low = universal_temporal_states(graph, op, left_lower, right_lower)
        if left_lower == left_upper and right_lower == right_upper:
            high = low
        else:
            high = universal_temporal_states(graph, op, left_upper, right_upper)
        stats["temporal_checks"] += 1
        event("ctl", cost=cost, winning=sorted(low & wanted))
        for state in (low & wanted)-result.lower:
            result.witnesses[state] = profile
        result.lower.update(low & wanted)
        result.upper.update(high & wanted)
        if cegar:
            for state in sorted(wanted-high):
                if stats["nogoods_learned"] >= 10000:
                    break  # forgetting refinements affects performance only
                certificate = counterexample(graph, state, op, left_upper, right_upper, high)
                nogood, certificate = learn_nogood(game, selected, coalition, certificate)
                if nogood not in nogoods[state]:
                    nogoods[state].add(nogood)
                    stats["nogoods_learned"] += 1
                    if len(result.counterexamples) < 50:
                        result.counterexamples.append(dict(start=state, **certificate))

    try:
        if engine == "positional":
            for signature, policy in positional_policies(game, coalition, dimensions):
                budget.next_candidate()
                stats["candidates_examined"] += 1
                event("guess")
                consider(signature, policy)
                if wanted <= result.lower:
                    break
            else:
                stats["enumeration_exhausted"] = True
        else:
            from ._classic_generation import collective_strategies
            actions = {a: sorted(set().union(*(game.enabled[s][a-1] for s in game.states)))
                       for a in coalition}
            seen = set()
            for item in collective_strategies(
                coalition, actions, game.propositions, bound
            ):
                budget.next_candidate()
                stats["candidates_examined"] += 1
                profile = {a: NaturalStrategy(tuple(Rule(parse_guard(g, game.propositions), action)
                           for g, action in individual["condition_action_pairs"]))
                           for a, individual in zip(coalition, item)}
                try:
                    policy = compile_profile(game, coalition, profile, appropriateness)
                except InadmissibleStrategy:
                    continue
                signature = tuple(policy[group[0]] for group in game.label_classes)
                if signature in seen:
                    stats["duplicate_policies_skipped"] += 1
                    continue
                seen.add(signature)
                consider(signature, policy, supplied=profile)
                if wanted <= result.lower:
                    break
            else:
                stats["enumeration_exhausted"] = True
    except ResourceLimit as exc:
        result.upper.update(wanted)
        result.reasons.append(str(exc))
    stats["guard_masks"] = len(table.best)
    stats["guard_cost_complete_through"] = table.complete_through
    return result
