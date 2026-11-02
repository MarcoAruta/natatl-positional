"""Strict deterministic CGSs; VITAMIN matrix text and a sparse JSON format."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property
import json
from math import prod
from pathlib import Path
import re
from types import MappingProxyType

from .errors import ModelError


def normalize_action(action):
    if not isinstance(action, str) or not action.strip():
        raise ModelError("Actions must be nonempty strings")
    action = action.strip()
    if any(c.isspace() or c in "|,*" for c in action):
        raise ModelError(f"Unsupported action name: {action!r}")
    return "IDLE" if action in {"I", "IDLE"} else action


def parse_cell(cell, agents):
    if cell in ("0", "", 0, None):
        return []
    if not isinstance(cell, str) or "*" in cell:
        raise ModelError("Wildcard/malformed transition cells are unsupported")
    result = []
    for part in cell.split(","):
        raw = part.strip()
        tokens = raw.split("|") if "|" in raw else ([raw] if agents == 1 else list(raw))
        if len(tokens) != agents:
            raise ModelError(f"Joint action {raw!r} has incorrect arity")
        result.append(tuple(normalize_action(x) for x in tokens))
    return result


@dataclass(frozen=True)
class Game:
    states: tuple[str, ...]
    propositions: tuple[str, ...]
    number_of_agents: int
    initial_state: str
    labels: dict
    transitions: dict
    enabled: dict = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        states = tuple(self.states)
        props = tuple(self.propositions)
        if (not states or any(not isinstance(s, str) or not s for s in states)
                or len(set(states)) != len(states)):
            raise ModelError("States must be unique nonempty strings")
        if self.initial_state not in states:
            raise ModelError("Unknown initial state")
        if type(self.number_of_agents) is not int or self.number_of_agents < 1:
            raise ModelError("Number_of_agents must be a positive integer")
        reserved = {"true", "false", "and", "or", "not", "implies", "until", "weakuntil"}
        if (len(set(props)) != len(props) or
                any(not isinstance(p, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", p)
                    or p == "T" or p.lower() in reserved for p in props)):
            raise ModelError("Invalid, reserved, or duplicate proposition name")
        if set(self.labels) != set(states) or set(self.transitions) != set(states):
            raise ModelError("Labels and transitions must describe exactly all states")
        labels, transitions, enabled = {}, {}, {}
        for state in states:
            label = frozenset(self.labels[state])
            if not label <= set(props):
                raise ModelError(f"Unknown proposition in label of {state}")
            labels[state] = label
            row = {}
            items = self.transitions[state]
            items = items.items() if hasattr(items, "items") else items
            for joint, target in items:
                if isinstance(joint, str) or len(joint) != self.number_of_agents:
                    raise ModelError(f"Incorrect joint-action arity at {state}")
                profile = tuple(normalize_action(a) for a in joint)
                if target not in states:
                    raise ModelError(f"Unknown transition destination: {target}")
                if profile in row and row[profile] != target:
                    raise ModelError(f"Nondeterministic joint action {profile} at {state}")
                row[profile] = target
            if not row:
                raise ModelError(f"Non-total CGS: no transitions at {state}")
            choices = tuple(frozenset(p[i] for p in row) for i in range(self.number_of_agents))
            if prod(map(len, choices)) != len(row):
                raise ModelError(f"Incomplete Cartesian joint-action table at {state}")
            transitions[state] = MappingProxyType(row)
            enabled[state] = choices
        object.__setattr__(self, "states", states)
        object.__setattr__(self, "propositions", props)
        object.__setattr__(self, "labels", MappingProxyType(labels))
        object.__setattr__(self, "transitions", MappingProxyType(transitions))
        object.__setattr__(self, "enabled", MappingProxyType(enabled))

    @cached_property
    def label_classes(self):
        grouped = {}
        for state in self.states:
            grouped.setdefault(self.labels[state], []).append(state)
        return tuple(tuple(group) for group in grouped.values())

    @cached_property
    def class_of(self):
        return MappingProxyType({s: i for i, group in enumerate(self.label_classes) for s in group})

    @property
    def valuation(self):
        return {p: {s for s in self.states if p in self.labels[s]} for p in self.propositions}

    def to_dict(self):
        return {"states": list(self.states), "propositions": list(self.propositions),
                "number_of_agents": self.number_of_agents, "initial_state": self.initial_state,
                "labels": {s: sorted(self.labels[s]) for s in self.states},
                "transitions": {s: [{"actions": list(a), "to": t}
                                    for a, t in self.transitions[s].items()] for s in self.states}}

    @classmethod
    def from_dict(cls, data):
        try:
            if not isinstance(data, dict):
                raise ModelError("A JSON CGS must be an object")
            if not isinstance(data["states"], list) or not isinstance(data["propositions"], list):
                raise ModelError("JSON states/propositions must be arrays")
            if not isinstance(data["labels"], dict) or not isinstance(data["transitions"], dict):
                raise ModelError("JSON labels/transitions must be objects indexed by state")
            if any(not isinstance(label, list) for label in data["labels"].values()):
                raise ModelError("Each JSON label must be an array of proposition names")
            for row in data["transitions"].values():
                if not isinstance(row, list) or any(not isinstance(e, dict) or
                        not isinstance(e.get("actions"), list) for e in row):
                    raise ModelError("JSON transition rows/actions must be arrays")
            return cls(tuple(data["states"]), tuple(data["propositions"]),
                       data["number_of_agents"], data["initial_state"], data["labels"],
                       {s: [(tuple(e["actions"]), e["to"]) for e in row]
                        for s, row in data["transitions"].items()})
        except (KeyError, TypeError) as exc:
            raise ModelError(f"Malformed JSON CGS: {exc}") from exc

    @classmethod
    def load(cls, path):
        text = Path(path).read_text(encoding="utf-8")
        if text.lstrip().startswith("{"):
            return cls.from_dict(json.loads(text))
        return cls.from_text(text)

    @classmethod
    def from_text(cls, text):
        headers = {"Transition", "Name_State", "Initial_State", "Atomic_propositions",
                   "Labelling", "Number_of_agents", "Agent_labels", "Unknown_Transition_by"}
        sections = {}
        current = None
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith(("#", "//")):
                continue
            if line in headers:
                if line in sections:
                    raise ModelError(f"Duplicate section: {line}")
                current = line
                sections[current] = []
            elif current is None:
                raise ModelError(f"Unknown CGS section or content: {line}")
            else:
                sections[current].append(line)
        required = headers - {"Agent_labels", "Unknown_Transition_by"}
        if not required <= sections.keys():
            raise ModelError(f"Missing CGS sections: {sorted(required-sections.keys())}")
        def words(header):
            return " ".join(sections[header]).split()
        states, props = words("Name_State"), words("Atomic_propositions")
        if len(words("Initial_State")) != 1 or len(words("Number_of_agents")) != 1:
            raise ModelError("Initial_State and Number_of_agents require one value")
        try:
            n = int(words("Number_of_agents")[0])
        except ValueError as exc:
            raise ModelError("Invalid Number_of_agents") from exc
        rows = [r.split() for r in sections["Transition"]]
        if len(rows) != len(states) or any(len(r) != len(states) for r in rows):
            raise ModelError("Invalid transition-matrix dimensions")
        labelling = [r.split() for r in sections["Labelling"]]
        if not props and not labelling:
            labelling = [[] for _ in states]
        if (len(labelling) != len(states) or any(len(r) != len(props) for r in labelling)
                or any(v not in {"0", "1"} for r in labelling for v in r)):
            raise ModelError("Labelling must be a states x propositions binary matrix")
        transitions = {s: [] for s in states}
        for i, s in enumerate(states):
            for j, target in enumerate(states):
                transitions[s].extend((p, target) for p in parse_cell(rows[i][j], n))
        labels = {s: frozenset(p for p, v in zip(props, labelling[i]) if v == "1")
                  for i, s in enumerate(states)}
        return cls(tuple(states), tuple(props), n, words("Initial_State")[0], labels, transitions)
