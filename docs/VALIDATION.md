# Validation and measurements

The bundled test run passed **39 unittest test methods**, with no failures.
`experiments/results/tests.txt` contains the full run. The tests include:

- 1,920 state-set comparisons over all 64 combinations of two-state deterministic binary-action games and one-proposition labellings, budgets 1–3, five temporal operators, and two search engines. The oracle uses independent syntax enumeration and cycle/reachability semantics.
- 144 additional comparisons with the independent oracle on seeded three-state games with nonconstant action protocols, two propositions, and both appropriateness modes.
- 180 comparisons on seeded two-agent games between the new exact positional engine and the supplied classic generator.
- Six comparisons on the two deterministic fixtures copied from the supplied VITAMIN archive.
- Direct checks of every learned counterexample constraint against all alternative matching policies of a small game; raw POS2NAT updates and expanded cost; witness export/reload and verification; nested modalities; budget-before-pruning; resource exhaustion and negation.

The tests provide executable evidence on these inputs. They are not a mechanized proof for arbitrary games.

## Executed benchmarks

The benchmark runner executed **14 cases × 5 variants × 3 repetitions = 210 checks**. All completed exact/classic/hybrid variants agreed on the Boolean decisions. The literal POS2NAT variant intentionally reports unknown when its nonminimum representation exceeds the bound.

Runtime includes checking and compilation, excludes loading the model from disk, and uses a fresh checker for each repetition. The classic generator and new engine share admissibility and universal CTL evaluation. `hybrid` starts with the literal POS2NAT construction; `exact` directly performs bounded minimum implementation.

Selected **median wall times in milliseconds** from the executed run:

| Case | Classic | Positional exact | Positional hybrid | Exact Boolean answer |
|---|---:|---:|---:|---|
| switch-k2 | 0.393 | 0.290 | 0.438 | true |
| indistinguishable | 2.894 | 0.250 | 0.370 | false |
| global | 10.151 | 0.231 | 0.409 | false |
| chain-128 | 3.681 | 3.175 | 9.505 | true |
| redundant-10-atoms | 983.494 | 0.776 | 4.081 | false |

These small examples do not establish a general speedup. The redundant-vocabulary example deliberately contains ten declared atoms but only four observed valuations, and favours semantic quotienting. Conversely, on the simple chain the literal conversion in hybrid adds overhead. Submillisecond timings are sensitive to machine load and should not be treated as stable performance ratios.

On `switch-k2`, the raw whole-model conversion costs **63** and is rejected before any CTL call. Exact/hybrid return `p -> B; T -> A`, of cost **2**. On `switch-k63`, literal POS2NAT itself returns a valid winning witness of cost 63. Thus the project can reproduce both the literal construction and the need for minimization at small budgets.

Full results: `experiments/results/summary.csv`, `results.json`, `environment.json`, `benchmark_run.txt`. The generated benchmark models, a winning witness, and the detailed raw conversion are stored alongside them.

Reproduce with:

```bash
python -m unittest discover -s tests -v
python experiments/run_benchmarks.py --repeats 3
python -m natatl_positional verify examples/switch.txt --formula "<{1},2>F goal" --witness experiments/results/example_witness.json
```
