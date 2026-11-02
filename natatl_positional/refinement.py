"""Sound, query-local counterexample-guided policy constraints."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Nogood:
    constraints: tuple[tuple[int, tuple[str, ...]], ...]

    def matches(self, signature):
        return all(signature[index] == actions for index, actions in self.constraints)


def learn_nogood(game, policy, coalition, certificate):
    path = certificate["path"]
    # Only source choices of ACTUAL certificate edges are constrained.
    # A finite bad endpoint does not require any action at that endpoint.
    constraints = {}
    joints = []
    for source, target in zip(path, path[1:]):
        constraints[game.class_of[source]] = policy[source]
        matching = [joint for joint, destination in game.transitions[source].items()
                    if destination == target and all(joint[a-1] == chosen
                       for a, chosen in zip(coalition, policy[source]))]
        if not matching:
            raise AssertionError("Counterexample contains an unprojected edge")
        joints.append(list(min(matching)))
    enriched = dict(certificate, joint_actions=joints)
    return Nogood(tuple(sorted(constraints.items()))), enriched
