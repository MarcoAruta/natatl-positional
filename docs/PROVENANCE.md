# Sources and provenance

The standalone implementation was prepared from the two files supplied in this
conversation and GianMarco Parretti's algorithmic notes quoted by Marco Aruta.
No external service, LLM inference API, or VITAMIN web interface is needed to run it.

## Supplied source archive

`vitamin-model-checker-feat-natatl-memoryless-recall.zip`

SHA-256: `39dc27e9dad6f9979c479c16b1cb4cfdf1107abc1f86189638da17945f184571`

The implementation contract was taken from:

- `docs/NatATL/SEMANTIC_CONTRACT.md`;
- `model_checker/algorithms/explicit/NatATL/Memoryless/modal_backend.py`;
- `model_checker/algorithms/explicit/NatATL/Memoryless/pruning.py`;
- `model_checker/algorithms/explicit/NatATL/strategy_complexity.py`;
- `model_checker/parsers/game_structures/cgs/semantic_snapshot.py`;
- `model_checker/parsers/game_structures/cgs/cgs_actions.py`.

`natatl_positional/_classic_generation.py` is an unchanged copy of
`model_checker/algorithms/explicit/NatATL/Memoryless/lazy_generation.py` in that
archive. It provides the optional classic comparator. The universal temporal
fixpoint equations and model-validation conventions follow the supplied
implementation, with a dependency-free adapter and parser.

`examples/vitamin_two_states.txt` and `examples/vitamin_nominal.txt` are copied
from the deterministic NatATL fixtures in the supplied archive. They are used
as fixtures, including for the memoryless semantics even where the original
fixture filename mentions Recall. The new project implements no Recall backend.

The source archive's `LICENSE` is preserved verbatim. Copyright (c) 2026
VITAMIN-organization. This derivative is supplied with its complete source
under the same source-available non-commercial research/education license.
This project does not replace or revise that license.

## Supplied reference

Wojciech Jamroga, Vadim Malvone, Aniello Murano, *Natural Strategic Ability*,
2019 preprint supplied as `Natural Strategic Ability(1).pdf`.

SHA-256: `ae7328565a5dbec91f13711f776da378f27f4181355d3a2026b3f486a9a1ac51`

Relevant content: §4.1 (ordered guarded actions, fallback, appropriateness and
sum-of-guard-symbols cost; footnote 3 for the operational variant), §4.2
(bounded strategic modality), §5.1 (strategy enumeration, pruning and universal
CTL verification, with bottom-up evaluation of nested modalities).

The positional conversion is attributed to GianMarco's notes, not to that
paper. The exact compiler, label-class enumeration, resource-aware result
handling and concrete counterexample constraints are implementation components
described separately in `IMPLEMENTATION.md`.
