"""Ordered rules, global/first-match admissibility, and portable witnesses."""
from __future__ import annotations

from dataclasses import dataclass

from .errors import InadmissibleStrategy, ResourceLimit
from .guards import Guard, export_dag, import_dag, parse_guard
from .model import normalize_action


@dataclass(frozen=True)
class Rule:
    guard: Guard
    action: str


@dataclass(frozen=True)
class NaturalStrategy:
    rules: tuple[Rule, ...]

    @property
    def cost(self):
        return sum(r.guard.cost for r in self.rules)

    def action(self, label, memo=None):
        for rule in self.rules:
            if rule.guard.evaluate(label, memo):
                return rule.action
        raise InadmissibleStrategy("Strategy has no matching rule")


def left_write(strategy, guard, action):
    """LEFT_WRITE(s, f, a) = [(f, a)] + s. Prepending is essential."""
    return NaturalStrategy((Rule(guard, normalize_action(action)),) + strategy.rules)


def profile_cost(profile):
    return sum(s.cost for s in profile.values())


def compile_profile(game, coalition, profile, appropriateness="first-match"):
    """Validate in the ORIGINAL game, including unreachable states."""
    if appropriateness not in {"first-match", "global"}:
        raise ValueError("Unknown appropriateness mode")
    if set(profile) != set(coalition):
        raise InadmissibleStrategy("Exactly one strategy per coalition agent is required")
    selected = {s: [] for s in game.states}
    for agent in coalition:
        if type(agent) is not int or not 1 <= agent <= game.number_of_agents:
            raise InadmissibleStrategy("Invalid coalition agent")
        strategy = profile[agent]
        if not strategy.rules or strategy.rules[-1].guard.op != "true":
            raise InadmissibleStrategy("The last rule must be an explicit (T, action)")
        all_actions = set().union(*(game.enabled[s][agent-1] for s in game.states))
        visited = set()
        todo = [r.guard for r in strategy.rules]
        while todo:
            node = todo.pop()
            if node in visited:
                continue
            visited.add(node)
            if node.op == "atom" and node.name not in game.propositions:
                raise InadmissibleStrategy(f"Unknown guard atom: {node.name}")
            todo.extend(node.args)
        for rule in strategy.rules:
            if normalize_action(rule.action) not in all_actions:
                raise InadmissibleStrategy(f"Undeclared action for agent {agent}: {rule.action}")
        for group in game.label_classes:
            label = game.labels[group[0]]
            memo = {}
            chosen = None
            for rule in strategy.rules:
                matches = rule.guard.evaluate(label, memo)
                action = normalize_action(rule.action)
                if matches and (appropriateness == "global" or chosen is None):
                    if any(action not in game.enabled[s][agent-1] for s in group):
                        raise InadmissibleStrategy(
                            f"Action {action!r} of agent {agent} is disabled at some "
                            f"state with label {sorted(label)} ({appropriateness})")
                if matches and chosen is None:
                    chosen = action
            if chosen is None:
                raise InadmissibleStrategy("Incomplete strategy")
            for state in group:
                selected[state].append(chosen)
    return {s: tuple(actions) for s, actions in selected.items()}


def export_profile(profile, selected=None):
    roots = [rule.guard for strategy in profile.values() for rule in strategy.rules]
    nodes, references = export_dag(roots)
    reference = iter(references)
    agents = {}
    for agent, strategy in profile.items():
        rules = []
        for rule in strategy.rules:
            try:
                text = rule.guard.text()
            except ResourceLimit:
                text = None
            rules.append({"guard": text, "guard_node": next(reference),
                          "action": rule.action, "cost": rule.guard.cost})
        agents[str(agent)] = {"cost": strategy.cost, "rules": rules}
    result = {"cost": profile_cost(profile), "agents": agents, "guard_dag": nodes}
    if selected is not None:
        result["selected_actions"] = {s: list(a) for s, a in selected.items()}
    return result


def import_profile(data, propositions):
    """Accept an exported witness, a checker result, or {agent: [[guard, action]]}."""
    if "winning_strategy" in data:
        data = data["winning_strategy"]
    elif "strategy" in data:
        data = data["strategy"]
    if not isinstance(data, dict):
        raise InadmissibleStrategy("No winning strategy in the supplied JSON")
    if "guard_dag" in data:
        nodes = import_dag(data["guard_dag"])
        result = {}
        for agent, item in data["agents"].items():
            rules = []
            for rule in item["rules"]:
                index = rule["guard_node"]
                if type(index) is not int or not 0 <= index < len(nodes):
                    raise InadmissibleStrategy("Unknown guard DAG node")
                rules.append(Rule(nodes[index], normalize_action(rule["action"])))
            result[int(agent)] = NaturalStrategy(tuple(rules))
        return result
    return {int(agent): NaturalStrategy(tuple(
                Rule(parse_guard(g, propositions), normalize_action(a)) for g, a in rules))
            for agent, rules in data.items()}
