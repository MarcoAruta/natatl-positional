"""Small reproducible comparisons, not a publication-scale performance study."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from natatl_positional import Game, Limits, check
from natatl_positional.pos2nat import pos2nat
from natatl_positional.strategy import export_profile


def alternating_chain(n):
    states = tuple(f"s{i}" for i in range(n))
    labels = {s: ({"p"} if i % 2 else set()) | ({"goal"} if i == n-1 else set())
              for i, s in enumerate(states)}
    transitions = {}
    for i, state in enumerate(states):
        correct = "B" if i % 2 else "A"
        transitions[state] = {(a,): states[min(i+1, n-1)] if a == correct else state
                              for a in ("A", "B")}
    return Game(states, ("p", "goal"), 1, states[0], labels, transitions)


def redundant_vocabulary(n=16):
    states = tuple(f"s{i}" for i in range(n))
    props = tuple(f"x{i}" for i in range(9)) + ("goal",)
    labels = {s: ({"x0"} if i % 2 else set()) | ({"x1"} if (i//2) % 2 else set())
              for i, s in enumerate(states)}
    transitions = {s: {("A",): states[(i+1) % n], ("B",): s}
                   for i, s in enumerate(states)}
    return Game(states, props, 1, states[0], labels, transitions)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--output", type=Path, default=ROOT/"experiments/results")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    args.output.mkdir(parents=True, exist_ok=True)
    cases = [
        ("switch-k1", Game.load(ROOT/"examples/switch.txt"), "<{1},1>F goal", "first-match"),
        ("switch-k2", Game.load(ROOT/"examples/switch.txt"), "<{1},2>F goal", "first-match"),
        ("switch-k4", Game.load(ROOT/"examples/switch.txt"), "<{1},4>F goal", "first-match"),
        ("switch-k63", Game.load(ROOT/"examples/switch.txt"), "<{1},63>F goal", "first-match"),
        ("indistinguishable", Game.load(ROOT/"examples/indistinguishable.txt"), "<{1},4>F goal", "first-match"),
        ("opponent", Game.load(ROOT/"examples/opponent.txt"), "<{1},2>F goal", "first-match"),
        ("coalition", Game.load(ROOT/"examples/opponent.txt"), "<{1,2},2>F goal", "first-match"),
        ("operational", Game.load(ROOT/"examples/state_dependent_actions.txt"), "<{1},3>F goal", "first-match"),
        ("global", Game.load(ROOT/"examples/state_dependent_actions.txt"), "<{1},3>F goal", "global"),
        ("vitamin-nominal", Game.load(ROOT/"examples/vitamin_nominal.txt"), "<{1},3>F a", "first-match"),
        ("chain-8", alternating_chain(8), "<{1},2>F goal", "first-match"),
        ("chain-32", alternating_chain(32), "<{1},2>F goal", "first-match"),
        ("chain-128", alternating_chain(128), "<{1},2>F goal", "first-match"),
        ("redundant-10-atoms", redundant_vocabulary(), "<{1},4>F goal", "first-match"),
    ]
    variants = [("classic", "hybrid", True), ("positional", "pos2nat", True),
                ("positional", "exact", True), ("positional", "hybrid", True),
                ("positional", "hybrid", False)]
    records, full = [], []
    for name, game, formula, mode in cases:
        (args.output/(name+".model.json")).write_text(json.dumps(game.to_dict(), indent=2)+"\n")
        exact_statuses = set()
        for engine, compiler, cegar in variants:
            times, results = [], []
            for _ in range(args.repeats):
                started = time.perf_counter()
                result = check(game, formula, engine=engine, compiler=compiler,
                               appropriateness=mode, cegar=cegar,
                               limits=Limits(max_candidates=100000, timeout_seconds=args.timeout))
                times.append(time.perf_counter()-started)
                results.append(result)
            statuses = {r["status"] for r in results}
            if len(statuses) != 1:
                raise AssertionError("Non-deterministic status across repeats")
            result = results[-1]
            if compiler != "pos2nat" and result["status"] != "unknown":
                exact_statuses.add(result["status"])
            stats = result["statistics"]
            row = {"case": name, "states": len(game.states), "atoms": len(game.propositions),
                   "label_classes": len(game.label_classes), "appropriateness": mode,
                   "engine": engine, "compiler": compiler, "cegar": cegar,
                   "status": result["status"], "mean_seconds": statistics.mean(times),
                   "median_seconds": statistics.median(times),
                   "candidates": stats["candidates_examined"], "ctl_checks": stats["temporal_checks"],
                   "cegar_skips": stats["cegar_candidates_skipped"],
                   "raw_cost_min": stats["raw_cost_min"], "raw_cost_max": stats["raw_cost_max"],
                   "witness_cost": result.get("witness_complexity")}
            records.append(row)
            full.append(dict(case=name, variant=[engine, compiler, cegar], seconds=times,
                             result=result))
            print(f"{name:22} {engine:10}/{compiler:7} cegar={str(cegar):5} "
                  f"{result['status']:7} {row['median_seconds']:.6f}s", flush=True)
            if name == "switch-k2" and engine == "positional" and compiler == "hybrid" and cegar:
                (args.output/"example_witness.json").write_text(json.dumps(result, indent=2)+"\n")
        if len(exact_statuses) > 1:
            raise AssertionError(f"Exact backends disagree on {name}")
    with (args.output/"summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    report = {"environment": {"python": sys.version, "platform": platform.platform(),
                               "repeats": args.repeats, "timeout_seconds": args.timeout},
              "runs": full}
    (args.output/"results.json").write_text(json.dumps(report, indent=2)+"\n")
    (args.output/"environment.json").write_text(json.dumps(report["environment"], indent=2)+"\n")
    switch = Game.load(ROOT/"examples/switch.txt")
    policy = {s: tuple(a) for s, a in json.loads((ROOT/"examples/switch_policy.json").read_text()).items()}
    converted = pos2nat(switch, policy, (1,), 1, complete=True)
    raw = {"strategy": export_profile({1: converted.strategy}),
           "trace": list(converted.trace), "reachable_layers": converted.reachable_layers}
    (args.output/"example_pos2nat_conversion.json").write_text(json.dumps(raw, indent=2)+"\n")


if __name__ == "__main__":
    main()
