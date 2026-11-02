"""Universal CTL X/F/G/U/W on a total pruned outcome graph.

Fixpoint equations follow the existing NatATL modal_backend.py. Operands are
state truth sets computed in the original CGS; nested quantifiers are not
re-evaluated in the pruned graph.
"""
from collections import deque


def prune(game, policy, coalition):
    successors = {s: {t for joint, t in game.transitions[s].items()
                      if all(joint[a-1] == chosen
                             for a, chosen in zip(coalition, policy[s]))}
                  for s in game.states}
    if any(not row for row in successors.values()):
        raise ValueError("Non-total projection: illegal positional policy")
    return successors


def universal_temporal_states(successors, op, left, right=None):
    states = set(successors)
    if not states or any(not ts or not ts <= states for ts in successors.values()):
        raise ValueError("Temporal evaluation requires a total finite graph")
    left = set(left)
    right = None if right is None else set(right)
    if not left <= states or (right is not None and not right <= states):
        raise ValueError("Unknown temporal operand state")
    def ax(target):
        return {s for s, targets in successors.items() if targets <= target}
    if op == "X" and right is None:
        return ax(left)
    if op not in {"F", "G", "U", "W"} or ((op in {"U", "W"}) != (right is not None)):
        raise ValueError("Invalid temporal operator or arity")
    if op == "F":
        target, invariant, least = left, states, True
    elif op == "G":
        target, invariant, least = set(), left, False
    else:
        target, invariant, least = right, left, op == "U"
    current = set() if least else states
    while True:
        updated = target | (invariant & ax(current))
        if updated == current:
            return updated
        current = updated


def counterexample(successors, start, op, left, right, winning):
    """Finite violating prefix or infinite lasso (including the closing edge).

    The certificate is a witness of failure of a fixed universal objective,
    not a SAT unsatisfiability certificate.
    """
    if start in winning:
        raise ValueError("No counterexample at a winning state")
    if op == "X":
        target = min(t for t in successors[start] if t not in left)
        return {"path": [start, target], "loop_start": None}
    if op in {"G", "W"}:
        queue = deque([start])
        parent = {start: None}
        end = None
        while queue:
            state = queue.popleft()
            if state not in left and (op == "G" or state not in right):
                end = state
                break
            if op == "W" and state in right:
                continue
            for target in sorted(successors[state]):
                if target not in parent:
                    parent[target] = state
                    queue.append(target)
        if end is None:
            raise AssertionError("Missing finite counterexample")
        path = []
        while end is not None:
            path.append(end)
            end = parent[end]
        return {"path": path[::-1], "loop_start": None}
    # AF and AU can fail on an infinite path. For AU there may instead be a
    # finite failure of the left operand before the right operand holds.
    path, seen, state = [], {}, start
    while state not in seen:
        seen[state] = len(path)
        path.append(state)
        if op == "U" and state not in left and state not in right:
            return {"path": path, "loop_start": None}
        candidates = successors[state] - winning
        if not candidates:
            raise AssertionError("Missing losing successor")
        state = min(candidates)
    loop_start = seen[state]
    path.append(state)
    return {"path": path, "loop_start": loop_start}
