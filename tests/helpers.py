from itertools import product
from natatl_positional import Game


def game(rows, labels, props=("p",), agents=1, initial="s0"):
    states = tuple(f"s{i}" for i in range(len(rows)))
    return Game(states, tuple(props), agents, initial,
                {s: frozenset(labels[i]) for i, s in enumerate(states)},
                {s: rows[i] for i, s in enumerate(states)})


def one_agent(targets, labels, props=("p",)):
    return game([{("A",): f"s{row[0]}", ("B",): f"s{row[1]}"} for row in targets],
                labels, props)


def oracle_guards(cost, props):
    # Independent syntax and evaluator: no production parser, GuardTable,
    # POS2NAT, policy enumeration, or CTL fixpoint is called here.
    if cost == 1:
        return [("atom", p) for p in props]
    values = [("not", g) for g in oracle_guards(cost-1, props)]
    for lc in range(1, cost-1):
        rc = cost-lc-1
        for a in oracle_guards(lc, props):
            for b in oracle_guards(rc, props):
                values.extend([("and", a, b), ("or", a, b)])
    return values


def oracle_value(g, label):
    if g[0] == "true":
        return True
    if g[0] == "atom":
        return g[1] in label
    if g[0] == "not":
        return not oracle_value(g[1], label)
    if g[0] == "and":
        return oracle_value(g[1], label) and oracle_value(g[2], label)
    return oracle_value(g[1], label) or oracle_value(g[2], label)


def oracle_lists(cost, actions, props):
    if cost == 1:
        return [((("true",), a),) for a in actions]
    values = []
    for first_cost in range(1, cost):
        for guard in oracle_guards(first_cost, props):
            for action in actions:
                for tail in oracle_lists(cost-first_cost, actions, props):
                    values.append(((guard, action),) + tail)
    return values


def closure(graph, start, permitted=None):
    pending, seen = [start], set()
    while pending:
        state = pending.pop()
        if state in seen or (permitted is not None and state not in permitted):
            continue
        seen.add(state)
        pending.extend(graph[state])
    return seen


def has_cycle(graph, allowed):
    grey, black = set(), set()
    def visit(state):
        if state in grey:
            return True
        if state in black:
            return False
        grey.add(state)
        if any(t in allowed and visit(t) for t in graph[state]):
            return True
        grey.remove(state)
        black.add(state)
        return False
    return any(visit(s) for s in allowed if s not in black)


def oracle_temporal(graph, start, op, left, right=None):
    states = set(graph)
    if op == "X":
        return graph[start] <= left
    if op == "G":
        return closure(graph, start) <= left
    if op == "F":
        avoiding = closure(graph, start, states-left)
        return not has_cycle(graph, avoiding)
    avoiding = closure(graph, start, states-right)
    if not avoiding <= left:
        return False
    return op == "W" or not has_cycle(graph, avoiding)


def oracle_winners(model, bound, op, left, right=None, mode="first-match"):
    actions = sorted(set().union(*(model.enabled[s][0] for s in model.states)))
    winners = set()
    for cost in range(1, bound+1):
        for rules in oracle_lists(cost, actions, model.propositions):
            selected, valid = {}, True
            for state in model.states:
                matching = [(g, a) for g, a in rules if oracle_value(g, model.labels[state])]
                chosen = matching[0][1]
                required = [a for _, a in matching] if mode == "global" else [chosen]
                if any(a not in model.enabled[state][0] for a in required):
                    valid = False
                    break
                selected[state] = chosen
            if not valid:
                continue
            graph = {s: {t for a, t in model.transitions[s].items() if a[0] == selected[s]}
                     for s in model.states}
            winners.update(s for s in model.states if oracle_temporal(graph, s, op, left, right))
    return winners
