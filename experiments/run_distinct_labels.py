"""Portable reproduction of the distinct-label counter-regime in the notes."""
from pathlib import Path
import argparse
import json
import platform
import statistics
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True,
                        help="Extracted standalone project, containing natatl_positional/")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--output", type=Path, default=Path("distinct_labels_rerun.json"))
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be positive")
    project = args.project.resolve()
    if not (project/"natatl_positional/__init__.py").is_file():
        parser.error("--project must contain the natatl_positional package directory")
    sys.path.insert(0, str(project))
    from natatl_positional import Game, check, Limits
    records = []
    for m in (4, 8, 12, 16):
        states = tuple(f"s{i}" for i in range(m))
        props = tuple(f"x{i}" for i in range((m-1).bit_length())) + ("goal",)
        labels = {s: {p for b, p in enumerate(props[:-1]) if i & (1 << b)}
                  | ({"goal"} if i == m-1 else set()) for i, s in enumerate(states)}
        transitions = {s: {("A",): s, ("B",): states[min(i+1, m-1)]}
                       for i, s in enumerate(states)}
        game = Game(states, props, 1, "s0", labels, transitions)
        for engine in ("classic", "positional"):
            runs, result = [], None
            for _ in range(args.repeats):
                start = time.perf_counter()
                result = check(game, "<{1},1>F goal", engine=engine, compiler="exact",
                               limits=Limits(timeout_seconds=args.timeout))
                runs.append(time.perf_counter()-start)
            record = {"label_classes": m, "engine": engine, "status": result["status"],
                      "median_seconds": statistics.median(runs),
                      "candidates": result["statistics"]["candidates_examined"],
                      "ctl_checks": result["statistics"]["temporal_checks"], "runs": runs}
            records.append(record)
            print(json.dumps(record), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(records, indent=2)+"\n", encoding="utf-8")
    environment = {"python": sys.version, "platform": platform.platform(),
                   "repeats": args.repeats, "timeout_seconds": args.timeout,
                   "project": str(project)}
    args.output.with_suffix(".environment.json").write_text(json.dumps(environment, indent=2)+"\n")


if __name__ == "__main__":
    main()
