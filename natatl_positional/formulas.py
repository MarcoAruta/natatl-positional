"""Dependency-free parser for propositional, perfect-information NatATL.

Unary: <{1,2},4>F phi. Binary: <{1},4>(phi U psi), similarly W.
State operands can contain nested strategic modalities. No CTL or regex guards
are silently accepted as state propositions.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from .errors import FormulaError


@dataclass(frozen=True)
class Formula:
    op: str
    children: tuple[Formula, ...] = ()
    name: str = ""
    coalition: tuple[int, ...] = ()
    bound: int = 0

    def text(self):
        if self.op == "atom":
            return self.name
        if self.op in {"true", "false"}:
            return self.op
        if self.op == "not":
            return f"!({self.children[0].text()})"
        if self.op in {"and", "or", "implies"}:
            symbol = {"and": "&&", "or": "||", "implies": "->"}[self.op]
            return f"({self.children[0].text()} {symbol} {self.children[1].text()})"
        prefix = "<{" + ",".join(map(str, self.coalition)) + "}," + str(self.bound) + ">"
        if len(self.children) == 1:
            return f"{prefix}{self.op} ({self.children[0].text()})"
        return f"{prefix}({self.children[0].text()} {self.op} {self.children[1].text()})"


_TOKEN = re.compile(
    r"\s*(<\s*\{[^}]*\}\s*,\s*[^>]*>|&&|\|\||->|[!()]|[A-Za-z_][A-Za-z_0-9]*)")
_MODAL = re.compile(r"<\s*\{\s*(\d*(?:\s*,\s*\d+)*)\s*\}\s*,\s*(\d+)\s*>")
_UNARY = {"X": "X", "NEXT": "X", "F": "F", "EVENTUALLY": "F",
          "G": "G", "GLOBALLY": "G", "ALWAYS": "G"}
_BINARY = {"U": "U", "UNTIL": "U", "W": "W", "WEAKUNTIL": "W"}


def parse_formula(text, number_of_agents, propositions):
    if not isinstance(text, str) or not text.strip():
        raise FormulaError("Formula is empty")
    # Preserve VITAMIN's common <{1},k>Fp spelling without splitting ordinary
    # proposition identifiers elsewhere.
    def separate(match):
        word = match[1]
        if word.upper() in _UNARY or word.upper() in _BINARY:
            return ">" + word
        return ">" + word[0] + " " + word[1:]
    text = re.sub(r">([FGX][A-Za-z_][A-Za-z_0-9]*)", separate, text.strip())
    tokens, position = [], 0
    while position < len(text):
        match = _TOKEN.match(text, position)
        if not match:
            raise FormulaError(f"Invalid formula near {text[position:]!r}")
        tokens.append(match.group(1))
        position = match.end()
    index = 0

    def peek():
        return tokens[index] if index < len(tokens) else None

    def take(options):
        nonlocal index
        if peek() in options:
            value = tokens[index]
            index += 1
            return value
        return None

    def primary():
        nonlocal index
        if take({"!", "NOT", "not"}):
            return Formula("not", (primary(),))
        if take({"("}):
            child = implication()
            if not take({")"}):
                raise FormulaError("Unclosed formula parentheses")
            return child
        token = peek()
        if token is None:
            raise FormulaError("Missing state formula")
        if token.startswith("<"):
            index += 1
            match = _MODAL.fullmatch(token)
            if not match:
                raise FormulaError("Use coalition syntax <{1,2},k> with k >= 0")
            agents = tuple(int(a.strip()) for a in match[1].split(",") if a.strip())
            if len(set(agents)) != len(agents) or any(not 1 <= a <= number_of_agents for a in agents):
                raise FormulaError("Invalid coalition agent(s)")
            bound = int(match[2])
            op = (peek() or "").upper()
            if op in _UNARY:
                index += 1
                return Formula(_UNARY[op], (primary(),), coalition=agents, bound=bound)
            if not take({"("}):
                raise FormulaError("Binary temporal operands require <{A},k>(phi U psi)")
            left = implication()
            op = (peek() or "").upper()
            if op not in _BINARY:
                raise FormulaError("Expected U or W inside strategic parentheses")
            index += 1
            right = implication()
            if not take({")"}):
                raise FormulaError("Unclosed strategic temporal operands")
            return Formula(_BINARY[op], (left, right), coalition=agents, bound=bound)
        index += 1
        if token in {"true", "T"}:
            return Formula("true")
        if token == "false":
            return Formula("false")
        if token not in propositions:
            raise FormulaError(f"Unknown atomic proposition: {token}")
        return Formula("atom", name=token)

    def boolean_and():
        result = primary()
        while take({"&&", "AND", "and"}):
            result = Formula("and", (result, primary()))
        return result

    def boolean_or():
        result = boolean_and()
        while take({"||", "OR", "or"}):
            result = Formula("or", (result, boolean_and()))
        return result

    def implication():
        result = boolean_or()
        if take({"->", "IMPLIES", "implies"}):
            result = Formula("implies", (result, implication()))
        return result

    try:
        root = implication()
    except RecursionError as exc:
        raise FormulaError("Formula nesting is too deep") from exc
    if index != len(tokens):
        raise FormulaError(f"Unexpected token: {tokens[index]}")
    return root
