# NatATL Positional

**Positional guess-and-check and POS2NAT for bounded memoryless natural strategies.**

Research prototype for the project of Marco Aruta and GianMarco Parretti.
Python 3.10+; no external runtime or test dependencies; CLI and Python API.

## Quick start

Run from the repository root; installation is optional:

```bash
python -m natatl_positional check examples/switch.txt --formula "<{1},2>F goal" --output witness.json
python -m natatl_positional verify examples/switch.txt --formula "<{1},2>F goal" --witness witness.json
```

The example returns `true` with `p -> B; T -> A`, of total cost 2.

## Algorithms

| Mode | Behavior |
|---|---|
| `--compiler pos2nat` | Literal forward construction using LEFT_WRITE, without Boolean simplification |
| `--compiler exact` | Minimum ordered-rule representation within budget on the model's observed labels |
| `--compiler hybrid` | Try POS2NAT, then exact compilation if needed; current default |
| `--engine classic` | Supplied cost-ordered natural-strategy generator, used as a comparator |

POS2NAT is in [pos2nat.py](natatl_positional/pos2nat.py); LEFT_WRITE is in
[strategy.py](natatl_positional/strategy.py). Inspect every conversion step:

```bash
python -m natatl_positional convert examples/switch.txt --coalition 1 --policy examples/switch_policy.json --complete
```

POS2NAT is not a minimizer. Its representation may exceed the bound although
a cheaper implementation exists. The literal search then preserves `unknown`
instead of incorrectly reporting a negative answer.

## Semantic contract

- Total deterministic CGSs, in VITAMIN matrix text or sparse JSON.
- Propositional guards, ordered first-match execution, explicit final `T` rule.
- Guard-symbol cost, including the final rule, summed across coalition members.
- Default first-match admissibility; optional stronger `--appropriateness global`.
- Admissibility on the entire original model; all compatible opponent moves remain.
- The budget is checked before materializing the pruned CTL graph. POS2NAT
  still queries compatible transitions implicitly for its BFS marking.
- Universal `X`, `F`, `G`, `U`, `W`; nested quantifiers use the original game.
- Explicit `true`, `false`, and `unknown` results, including under negation.

Use `--all-states`, `--trace`, or `--no-cegar` to control state-set evaluation,
diagnostics, and counterexample-guided filtering. Current constraints filter
generated policies; they do not yet prune partial assignments during generation.

## Validation and experiments

```bash
python -m unittest discover -s tests -v
python experiments/run_benchmarks.py --repeats 3 --output experiments/results/new-run
python experiments/run_distinct_labels.py --project . --output experiments/results/new-run/distinct_labels.json
```

Recorded validation passes 39 test methods, including independent small-game
oracles. The main pilot contains 210 runs; an additional 24-run distinct-label
experiment exposes a regime where positional enumeration is substantially worse.
These preliminary structured examples do not establish a general speedup.

## Project structure

| Directory | Contents |
|---|---|
| [natatl_positional/](natatl_positional) | Games, guards, conversion, synthesis, temporal checking, CLI |
| [examples/](examples) | Small games and positional policies |
| [tests/](tests) | Semantic tests, independent oracles and witness verification |
| [experiments/](experiments) | Reproduction scripts and recorded measurements |
| [docs/](docs) | Implementation, provenance, validation and Italian guide |

Read the [implementation notes](docs/IMPLEMENTATION.md),
[validation report](docs/VALIDATION.md), [Italian guide](docs/README_it.md),
and [contribution workflow](CONTRIBUTING.md).

## License and provenance

This derivative retains the supplied VITAMIN **source-available non-commercial
research/education license**. See [LICENSE](LICENSE) and [provenance](docs/PROVENANCE.md).

Reference: W. Jamroga, V. Malvone, A. Murano, *Natural Strategic Ability*,
Artificial Intelligence 277, 103170, 2019. POS2NAT follows GianMarco Parretti's
project notes; the exact compiler and adaptations are documented separately.
