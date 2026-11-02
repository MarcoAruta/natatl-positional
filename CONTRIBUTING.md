# Contributing

Use Python 3.10 or later. No runtime or test dependencies are required.

```bash
python -m unittest discover -s tests -v
```

Keep changes focused and explain any semantic impact. Changes to guard cost,
first-match selection, global admissibility, coalition budgets, or handling of
unknown results need corresponding semantic validation. Preserve the original
game when evaluating nested strategic modalities.

Use a branch and a pull request for subsequent development. Include the test
command and its result in the pull request description. Preserve the inherited
license and provenance notices.

Benchmark changes should retain the previous recorded measurements. Write
new results to a separate output directory and record the environment:

```bash
python experiments/run_benchmarks.py --repeats 3 --output experiments/results/new-run
python experiments/run_distinct_labels.py --project . --output experiments/results/new-run/distinct_labels.json
```

The included pilot is small and deliberately structured. Avoid extrapolating
its timing percentages to general NatATL workloads.
