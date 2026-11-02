"""GianMarco Parretti's LEFT_WRITE/POS2NAT construction.

V(q) is the complete propositional valuation (positive AND negative literals).
Under this convention SAT(V(q) AND NOT psi) is equivalent to checking whether
that valuation has already been seen. The formula itself is retained verbatim.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from .errors import InadmissibleStrategy
from .guards import TRUE, FALSE, conjunction, neg, disjunction, valuation_guard
from .strategy import NaturalStrategy, Rule, left_write


def projected_targets(game, policy, coalition, state):
    """Implicit projection only; do not allocate a pruned transition system."""
    selected = policy[state]
    return {target for joint, target in game.transitions[state].items()
            if all(joint[a-1] == action for a, action in zip(coalition, selected))}


def reachability_layers(game, policy, coalition, initial_state=None):
    initial = initial_state or game.initial_state
    if initial not in game.states:
        raise ValueError("Unknown marking root")
    depth = {initial: 0}
    queue = deque([initial])
    layers = []
    order = {s: i for i, s in enumerate(game.states)}
    while queue:
        state = queue.popleft()
        level = depth[state]
        if level == len(layers):
            layers.append([])
        layers[level].append(state)
        for target in sorted(projected_targets(game, policy, coalition, state), key=order.get):
            if target not in depth:
                depth[target] = level + 1
                queue.append(target)
    return tuple(tuple(layer) for layer in layers)


@dataclass(frozen=True)
class Conversion:
    strategy: NaturalStrategy
    trace: tuple[dict, ...]
    reachable_layers: tuple[tuple[str, ...], ...]
    extended_states: tuple[str, ...]


def pos2nat(game, policy, coalition, agent, *, layers=None, complete=False,
            default_action=None, record_trace=True):
    """Translate one component of a positional coalition policy.

    With complete=False this is the algorithm in the notes, over reachable G'.
    With complete=True, continue the same updates on states outside G' to obtain
    a strategy on the whole original game. No earlier rule is simplified.
    """
    coalition = tuple(coalition)
    if agent not in coalition:
        raise ValueError("Agent is not in the coalition")
    position = coalition.index(agent)
    if layers is None:
        layers = reachability_layers(game, policy, coalition)
    ordered = [(s, i) for i, layer in enumerate(layers) for s in layer]
    reached = {s for s, _ in ordered}
    extra = tuple(s for s in game.states if s not in reached) if complete else ()
    ordered.extend((s, None) for s in extra)
    assigned_actions = {}
    for state, _ in ordered:
        label = game.labels[state]
        action = policy[state][position]
        if label in assigned_actions and assigned_actions[label] != action:
            raise InadmissibleStrategy("Equal labels prescribe different actions")
        if action not in game.enabled[state][agent-1]:
            raise InadmissibleStrategy("Positional policy selects a disabled action")
        assigned_actions[label] = action
    actions = set().union(*(game.enabled[s][agent-1] for s in game.states))
    if default_action is None:
        default_action = "IDLE" if "IDLE" in actions else sorted(actions)[0]
    if default_action not in actions:
        raise InadmissibleStrategy("The default action is not in the agent's alphabet")
    strategy = NaturalStrategy((Rule(TRUE, default_action),))
    psi = FALSE
    seen = set()
    trace = []
    for state, level in ordered:
        v = valuation_guard(game.propositions, game.labels[state])
        f = conjunction(v, neg(psi))
        already_assigned = game.labels[state] in seen
        if already_assigned:
            strategy = left_write(strategy, v, policy[state][position])
        else:
            strategy = left_write(strategy, f, policy[state][position])
            psi = disjunction(psi, f)
            seen.add(game.labels[state])
        if record_trace:
            trace.append({"state": state, "marking": level,
                          "phase": "extension" if level is None else "reachable",
                          "branch": "overwrite" if already_assigned else "uncovered",
                          "guard_cost": (v if already_assigned else f).cost,
                          "strategy_cost": strategy.cost, "coverage_cost": psi.cost})
    return Conversion(strategy, tuple(trace), tuple(layers), extra)
