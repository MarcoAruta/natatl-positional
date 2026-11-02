"""Portable CLI; JSON output, no server/UI and no network calls."""
import argparse
import json
from pathlib import Path
import sys

from . import Game, Limits, check, verify_strategy
from .errors import InadmissibleStrategy
from .model import normalize_action
from .pos2nat import pos2nat, reachability_layers
from .strategy import compile_profile, export_profile, import_profile


def _parser():
    parser = argparse.ArgumentParser(prog="natatl-positional")
    commands = parser.add_subparsers(dest="command", required=True)
    check_parser = commands.add_parser("check", help="Model check a memoryless NatATL formula")
    check_parser.add_argument("model")
    check_parser.add_argument("--formula", required=True)
    check_parser.add_argument("--compiler", choices=["hybrid", "pos2nat", "exact"], default="hybrid")
    check_parser.add_argument("--engine", choices=["positional", "classic"], default="positional")
    check_parser.add_argument("--appropriateness", choices=["first-match", "global"], default="first-match")
    check_parser.add_argument("--all-states", action="store_true")
    check_parser.add_argument("--no-cegar", action="store_true")
    check_parser.add_argument("--trace", action="store_true")
    check_parser.add_argument("--max-candidates", type=int)
    check_parser.add_argument("--timeout", type=float)
    check_parser.add_argument("--max-guard-masks", type=int, default=100000)
    check_parser.add_argument("--max-dp-states", type=int, default=100000)
    convert = commands.add_parser("convert", help="Run GianMarco's POS2NAT with its detailed trace")
    convert.add_argument("model")
    convert.add_argument("--policy", required=True, help="JSON: state -> coalition action list")
    convert.add_argument("--coalition", required=True, help="1,2,... in policy-list order")
    convert.add_argument("--complete", action="store_true", help="Extend from G' to all original states")
    convert.add_argument("--appropriateness", choices=["first-match", "global"], default="first-match")
    verify = commands.add_parser("verify", help="Re-check a saved natural-strategy witness")
    verify.add_argument("model")
    verify.add_argument("--formula", required=True)
    verify.add_argument("--witness", required=True)
    verify.add_argument("--appropriateness", choices=["first-match", "global"], default="first-match")
    for sub in (check_parser, convert, verify):
        sub.add_argument("--output", help="Also save exactly this JSON result")
    return parser


def main(argv=None):
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            result = check(args.model, args.formula, compiler=args.compiler, engine=args.engine,
                           appropriateness=args.appropriateness, all_states=args.all_states,
                           cegar=not args.no_cegar, trace=args.trace,
                           limits=Limits(args.max_candidates, args.timeout,
                                         args.max_guard_masks, args.max_dp_states))
        elif args.command == "verify":
            game = Game.load(args.model)
            profile = import_profile(json.loads(Path(args.witness).read_text(encoding="utf-8")),
                                     game.propositions)
            result = verify_strategy(game, args.formula, profile,
                                     appropriateness=args.appropriateness)
        else:
            game = Game.load(args.model)
            coalition = tuple(int(x.strip()) for x in args.coalition.split(","))
            if (len(set(coalition)) != len(coalition)
                    or any(not 1 <= a <= game.number_of_agents for a in coalition)):
                raise ValueError("Invalid coalition")
            raw = json.loads(Path(args.policy).read_text(encoding="utf-8"))
            if set(raw) != set(game.states):
                raise ValueError("The positional JSON must specify every original state")
            if any(not isinstance(row, list) or len(row) != len(coalition) for row in raw.values()):
                raise ValueError("Each positional action list must follow --coalition order")
            policy = {s: tuple(normalize_action(a) for a in raw[s]) for s in game.states}
            layers = reachability_layers(game, policy, coalition)
            profile, traces, extended = {}, {}, ()
            for agent in coalition:
                converted = pos2nat(game, policy, coalition, agent,
                                   layers=layers, complete=args.complete)
                profile[agent] = converted.strategy
                traces[str(agent)] = list(converted.trace)
                extended = converted.extended_states
            try:
                selected = compile_profile(game, coalition, profile, args.appropriateness)
                admissible = True
            except InadmissibleStrategy:
                selected, admissible = None, False
            result = {"strategy": export_profile(profile, selected),
                      "reachable_layers": [list(layer) for layer in layers],
                      "extended_states": list(extended), "trace": traces,
                      "whole_model_admissible": admissible,
                      "appropriateness": args.appropriateness}
        serialized = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
        if args.output:
            path = Path(args.output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(serialized, encoding="utf-8")
        sys.stdout.write(serialized)
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        sys.stderr.write(json.dumps({"status": "error", "error": str(exc)}) + "\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
