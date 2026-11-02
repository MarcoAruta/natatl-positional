"""Propositional guards as DAGs with the cost of the EXPANDED formula tree.

Sharing subexpressions saves storage, not strategy cost. No simplification is
performed by the constructors. This is important for literal POS2NAT runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re

from .errors import FormulaError, ResourceLimit


@dataclass(frozen=True, eq=False)
class Guard:
    op: str
    args: tuple[Guard, ...] = ()
    name: str = ""
    cost: int = field(init=False)

    def __post_init__(self):
        arities = {"atom": 0, "true": 0, "false": 0,
                   "not": 1, "and": 2, "or": 2}
        if self.op not in arities or len(self.args) != arities[self.op]:
            raise ValueError("Invalid Boolean DAG node")
        object.__setattr__(self, "cost", 1 + sum(a.cost for a in self.args))

    def evaluate(self, label: frozenset[str], memo=None) -> bool:
        # Iterative evaluation: a long raw POS2NAT trace must not overflow the
        # Python call stack. Node identity is intentional (DAG, not tree).
        memo = {} if memo is None else memo
        todo = [(self, False)]
        while todo:
            node, ready = todo.pop()
            if node in memo:
                continue
            if not ready and node.args:
                todo.append((node, True))
                todo.extend((a, False) for a in node.args if a not in memo)
                continue
            if node.op == "atom":
                value = node.name in label
            elif node.op == "true":
                value = True
            elif node.op == "false":
                value = False
            elif node.op == "not":
                value = not memo[node.args[0]]
            elif node.op == "and":
                value = memo[node.args[0]] and memo[node.args[1]]
            else:
                value = memo[node.args[0]] or memo[node.args[1]]
            memo[node] = value
        return memo[self]

    def text(self, max_symbols: int = 10000) -> str:
        if self.cost > max_symbols:
            raise ResourceLimit("Expanded guard is too large to print; use its DAG")
        parts = []
        todo = [self]
        while todo:
            item = todo.pop()
            if isinstance(item, str):
                parts.append(item)
            elif item.op == "atom":
                parts.append(item.name)
            elif item.op in ("true", "false"):
                parts.append("T" if item.op == "true" else "false")
            elif item.op == "not":
                todo.extend([
                    ")", item.args[0], "!("
                ])
            else:
                todo.extend([
                    ")", item.args[1],
                    " && " if item.op == "and" else " || ",
                    item.args[0], "("
                ])
        return "".join(parts)


TRUE = Guard("true")
FALSE = Guard("false")


def atom(name):
    return Guard("atom", name=name)


def neg(g):
    return Guard("not", (g,))


def conjunction(a, b):
    return Guard("and", (a, b))


def disjunction(a, b):
    return Guard("or", (a, b))


def valuation_guard(propositions, label):
    """Full minterm: true at precisely this Boolean valuation, not at supersets."""
    terms = [atom(p) if p in label else neg(atom(p)) for p in propositions]
    if not terms:
        return TRUE
    result = terms[0]
    for term in terms[1:]:
        result = conjunction(result, term)
    return result


_TOKEN = re.compile(r"\s*(&&|\|\||!|\(|\)|[A-Za-z_][A-Za-z_0-9]*)")


def parse_guard(text: str, propositions) -> Guard:
    tokens = []
    position = 0
    text = text.strip()
    while position < len(text):
        match = _TOKEN.match(text, position)
        if not match:
            raise FormulaError(f"Invalid Boolean guard near {text[position:]!r}")
        tokens.append(match.group(1))
        position = match.end()
    index = 0
    vocabulary = set(propositions)

    def take(options):
        nonlocal index
        if index < len(tokens) and tokens[index] in options:
            token = tokens[index]
            index += 1
            return token
        return None

    def primary():
        nonlocal index
        if take({"!", "not", "NOT"}):
            return neg(primary())
        if take({"("}):
            value = boolean_or()
            if not take({")"}):
                raise FormulaError("Unclosed Boolean guard")
            return value
        if index == len(tokens):
            raise FormulaError("Missing Boolean guard operand")
        value = tokens[index]
        index += 1
        if value in {"T", "true"}:
            return TRUE
        if value == "false":
            return FALSE
        if value not in vocabulary:
            raise FormulaError(f"Unknown guard proposition: {value}")
        return atom(value)

    def boolean_and():
        result = primary()
        while take({"&&", "and", "AND"}):
            result = conjunction(result, primary())
        return result

    def boolean_or():
        result = boolean_and()
        while take({"||", "or", "OR"}):
            result = disjunction(result, boolean_and())
        return result

    result = boolean_or()
    if index != len(tokens):
        raise FormulaError(f"Unexpected guard token: {tokens[index]}")
    return result


def export_dag(roots):
    """Topological JSON DAG; each reference is to a previous node."""
    ids, nodes = {}, []
    for root in roots:
        todo = [(root, False)]
        while todo:
            node, ready = todo.pop()
            if node in ids:
                continue
            if not ready and node.args:
                todo.append((node, True))
                todo.extend((a, False) for a in reversed(node.args) if a not in ids)
                continue
            ids[node] = len(nodes)
            record = {"op": node.op}
            if node.op == "atom":
                record["name"] = node.name
            if node.args:
                record["args"] = [ids[a] for a in node.args]
            nodes.append(record)
    return nodes, [ids[r] for r in roots]


def import_dag(nodes):
    result = []
    for index, item in enumerate(nodes):
        references = item.get("args", [])
        if any(type(i) is not int or i < 0 or i >= index for i in references):
            raise FormulaError("Guard DAG is not topologically ordered")
        result.append(Guard(item["op"], tuple(result[i] for i in references),
                            item.get("name", "")))
    return result

