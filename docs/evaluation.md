# Prototype evaluation

Run on 2026-09-16 Europe/Rome (2026-09-15 UTC), Python 3.11.16, NumPy 2.4.6,
SciPy 1.17.1. These are local observations, not calibrated quality or speed
promises. The package is a runnable baseline; useful large-design correspondence
is still an open result.

## What ran

- The owned test suite exercises canonical bindings, changed defaults and raw
  values, moved/renamed containers, body-net partition changes, ambiguity,
  opaque/recursive calls, and limits. See the package's `tests/`.
- `examples/evaluate.py` runs the four-device authored motif, a synthetic
  hierarchy, and optionally a local public netlist. The mutation ledger is held
  by the evaluator and is never passed to the matcher.
- Raw results are in `examples/evaluation.json`. The initial failure is retained
  in `examples/evaluation-before-class-isolation.json`.

From the ASS root:

```console
.venv/bin/python netlist-comparison/examples/evaluate.py --output /tmp/comparison-evaluation.json
```

The optional public check uses the already saved observatory input, without
downloading or copying the model into this package:

```console
.venv/bin/python netlist-comparison/examples/evaluate.py --output /tmp/comparison-evaluation.json --public-netlist research-observatory/runs/20260915-netlist-diff-sota/tia_output.net
```

The public file SHA-256 is
`142c6445f666fa1e28f56ebb9aafcae35418b48ce1cab17ef3454ff7b1c2c7d0`.
It contains existing vendor macromodel text; this check establishes neither
simulation validity nor redistribution rights. The package retains only metrics
and the digest, not a copy of the deck.

## Results and limitations

| Case | Leaves A/B; depth A/B | Result |
|---|---|---|
| Authored small move+edit | 4/4; 2/3 | Four tentative pairs; the width-expression edit and definition-default edit are retained under the correct generated pairing. |
| Synthetic repeated hierarchy | 2,067/2,067; 4/5 | All 2,067 ledger counterparts remain among retained eligible class candidates; only two leaf pairs proposed. 2,065 leaves per side remain unresolved. |
| Public TIA with one raw resistor edit | 376/376; 1/1 | 58 tentative pairs; 318 unresolved. The changed R112 is unresolved, so this run does not yield a paired raw-edit finding for it. |

The synthetic hierarchy contains 44 populated banks, each built from branching
analog motifs with devices at every original level, plus inter-bank resistors.
It is not merely thousands of empty wrappers. The revision renames/reorders
objects, specializes one leaf through copied ancestor definitions, and adds a
wrapper to relocate that specialized occurrence. The added wrapper itself is a
controlled hierarchy edit, not an extra claim of analog complexity.

Its 24 classes on each side require 576 scores instead of 2,067 squared
device-pair scores. The retained graph has 222 class edges. Local elapsed time
was approximately 0.7 seconds, with about 91 MiB peak process RSS across the
evaluation process including imports and the public check. This does not
establish dense-candidate or large-assignment performance: only one small
assignment component was solved in the synthetic case.

The new value `6u` identifies one revised occurrence in a raw profile, but the
old/new candidate group containing it still has 704 leaves on each side.
That is much too broad to claim the requested schematic-localization problem
solved. The two proposed synthetic pairs agree with the generator ledger;
most repeated objects have no verified unique historical identity. Path/name
matching finds zero equal paths after the systematic rename, but that weak
result does not establish that this report saves inspection time.

## Architectural lesson adopted during the prototype

Initially, a repeated class made its entire connected candidate component
unresolved. Both the public example and the synthetic example then had **zero**
leaf proposals. That policy let local ambiguity suppress unrelated evidence.

The prototype now solves a **restricted singleton domain** and explicitly lists
excluded repeated, cutoff-tied or unfinished classes. This recovers 58 public
and two synthetic proposals. It does not prove those proposals are correct or
globally optimal with the excluded alternatives restored. The report preserves
that distinction. No dynamic propagation or repair was added.

## Decision and next discriminating experiment

Keep this as the executable reference and output contract. The repeated-scale
result rejects treating fixed local features alone as an adequate solution for
the eventual target. It supports the implementation's boundedness and input
handling, not general correspondence or inspection usefulness.

The planned next step was an experimental single frozen-context pass,
comparing three variants: path/name, fixed-feature reference, and context extension. Use held-out
combinations of regrouping, changed terminals, insertion/removal, shared versus
specialized definitions, and misleading repeated copies. Measure candidate rank,
wrong pairing, unresolved-region size, changed-object localization, runtime and
memory. Keep symmetric admissible mappings distinct from the generator's edit
history. Reject the extension if extra matches merely spread wrong seeds or
fail to narrow inspection regions. The original section claimed no frozen-context result; the second experiment
below now records its outcome and the subsequently authorized stronger kernel.

A representative complete complex-analog depth-4–5 design is still needed for
external validity. No human inspection-time benefit or numeric acceptance target
has been established.

## Second experiment: frozen neighbours and bounded anchor growth

2026-09-16. The first context pass was measured before extending the algorithm.
It only raised stress proposals from 2 to 7. User steering then prioritized
algorithm engineering and authorized bounded relational refinement. The original
fixed-feature mode remains the default and the comparison reference.

The new `Options(matching_mode="anchor_growth")` / CLI
`--matching-mode anchor_growth` is an independent **adaptation** of IP-Matcher's
WL-anchor and binding-growth ideas (Algorithms 1 and 3), not its implementation
or a reproduction of its reported performance. It uses role-labelled structural
hashes at three device/net rounds, uniquely occurring equal hashes as tentative
anchors, and at most 64 synchronous growth rounds. Growth requires mutually
unique best terminal support from earlier tentative pairs (Dice ≥0.8). No pair
supports itself or another pair accepted in the same round. Candidate visits
are capped at 200,000, also bounded by `max_pair_scores`.

Unlike the paper's prime-product hashes, greedy queue pairing and IP covering,
this adaptation preserves terminal roles, physical multiplicity and unmatched
objects. Nets with over 32 distinct devices are suppressed **only in this
search view**; all incidence, including body terminals, remains in raw catalogs
and conditional connectivity reporting. No names, values or hierarchy gates
enter this kernel. Its thresholds are experimental settings.

| Case | Path/name | v1 | Frozen neighbours | Anchor growth |
|---|---:|---:|---:|---:|
| Known 2,067-leaf depth4→5, moved raw edit: pairs | 0 | 2 | 7 | 1,231 |
| Same case: edited-object hint/eligible set, opposite leaves | none | 396 | 308 | 1 paired hint |
| TIA unchanged names: pairs | 376 | 58 | 105 | 344 |
| TIA R112 inspection set | 1 paired hint | 17 | 15 | 2 unresolved |
| Held-out stress body+add/remove: pairs | 0 | 2 | 8 | 110 |
| Same held-out case: historical disagreements | 0 | 2 | 8 | 110 |
| Held-out moved motif + body edit: pairs | 0 | 4 | 4 | 0 |

The known stress growth pairs all agree with generator history; exact terminal
twins are allowed interchangeable identities in evaluation. Its edited raw
width is reported at the expected paired location. This is useful positive
synthetic evidence. The retained full reference competition region remains
704×704: a one-pair hint is **conditional**, not exhaustive elimination of
alternatives. TIA's path/name baseline is strongest; R112 remains structurally
ambiguous in growth.

**The held-out stress combination rejects default adoption.** Removing a bridge
creates a new boundary motif. Seven uniquely matching local hashes choose the
wrong historical region, then grow into 110 disagreements. The edited device
receives a wrong singleton hint and its raw edit is missed. Reference candidates
still contain all 2,066 surviving historical counterparts. This is an anchor
hypothesis failure, not loss in candidate retrieval. No post-result tuning was
performed. The small moved+body case supplies no anchors and growth abstains,
although v1/context locate the edit. Shared/specialized defaults and overrides
remain raw and separate; true parallel-copy ambiguity remains unresolved.

All four methods use the same canonical inputs. The path/name reference uses
exact full paths followed by globally unique remaining leaf names. Evaluation
identities never enter matchers. A separate recursive elaborator checks both
reported incidence partitions and transformed incidence outside declared edits.
Development/known challenges and five untouched mutation combinations are
explicitly separated; acceptance criteria were written before held-out execution.
These few cases do not calibrate general accuracy or establish human time saving.

The measured stress comparison took 0.51 s for v1, 0.74 s for context, and
2.03 s for growth including retained reference reporting. Growth used 38 anchors,
46 growth rounds including the final empty round, and 62,299 candidate visits.
Peak RSS for the sequential evaluation process was 133.3 MiB, including imports
and retained prior allocations; this is not per-method isolated peak memory.
Stress order, systematic rename and reversal preserved proposal sets. Full
reports under traversal reordering match after JSON normalization and excluding
timings. Initial diagnostics compared JSON arrays with Python tuples; that
measurement error is retained and corrected in the evidence.

Reproduce from ASS root (writes only the chosen output directory):

```console
.venv/bin/python netlist-comparison/examples/evaluate_matching.py --output-dir /tmp/comparison-second --public-netlist research-observatory/runs/20260915-netlist-diff-sota/tia_output.net
.venv/bin/python netlist-comparison/examples/diagnose_matching.py --reports /tmp/comparison-second --output /tmp/comparison-second/diagnostics.json
.venv/bin/python netlist-comparison/examples/summarize_matching.py /tmp/comparison-second
```

Saved summaries, full compressed JSON reports, freezes and criteria live in
`research-observatory/runs/20260916-comparison-context/` at the ASS root.
Candidate ranks in `comparison/derived.json` are within retained class edges,
not full pre-cutoff ranks. Stage sizes/times, containment, region sizes, false
extra raw findings and scope are retained alongside the counts.

**Next algorithmic question:** can competing regional anchor hypotheses be
scored jointly for total preserved terminal incidence and unmatched cost, so a
newly created boundary cannot displace an otherwise coherent surviving region?
This calls for revisable relational optimization, not another local threshold
or a claim that an equal WL hash establishes identity. The current kernels stay
opt-in as inspectable experiments.

## Regional graph and formal-interface correction (iteration 3)

The opt-in regional kernel now searches branching/cyclic coarse graphs, permits
unequal region counts, and opens oversized hierarchy wrappers. The fixed default,
frozen-context, growth and partial-QAP references remain unchanged. Historical
ledger disagreement alone is not structural error: the root audit constructed
admissible alternate histories, so this checkpoint measures full terminal
incidence, conditional raw findings and both-side inspection regions.

Root's independent formal-order control exposed a real representation bug in the
first graph version: unchanged incidence yielded missing matches or 16–23
endpoint disagreements on a 46-leaf reduction. The corrected
`regional_graph_beam_interface_v3` removes formal indices from coarse relations
and enumerates small interface bijections. All six slot permutations now yield
46/46 pairs and zero endpoint disagreements; the renamed, wrapped 2,067-leaf
controls also recover all pairs with zero disagreement. Symmetric interface
alternatives are retained, and large interfaces use weaker invariant multisets.

Frozen binary-tree, cycle/spoke and unequal-tree cases retain their results after
the correction: 1,455/1,367/1,268 pairs, 1/2/0 endpoint disagreements, singleton
changed-device hints on both sides, and no raw findings outside the specified
edits. These synthetic results expand the supported domain; they do not establish
arbitrary regrouping, exhaustive alternatives or workplace accuracy. The unequal
tree admits an alternate explanation preserving every old device and leaving one
new 46-leaf region plus a link unmatched, rather than its historical remove-one /
add-two ledger. All candidate assignments remain conditional.

The [iteration 3 report](../../research-observatory/runs/20260916-comparison-context/iteration3/report.md)
records the before/after sources, failed formal-order controls, comparative
measurements, budgets, commands, and the next discriminating experiment.

## Physical split/merge and rename audit (iteration4)

`regional_multifrontier_v4` compares the authored frontier with physical pieces
that can cross occurrence boundaries. Root's independently interleaved three-way
split improves from 2,020 pairs (edited target missed) to 2,067 pairs: zero terminal
disagreement for pure split/reverse merge, one for combined body/type editing.
Exact terminal-twin raw-field representative selection removes the manufactured
resistor-value findings, while retaining structural ambiguity and real edits.

Arbitrary allocations across seven new populated blocks at depth 5 recover 2,066
pairs with one body-endpoint discrepancy and exactly one unmatched object per side
for a simultaneous cut/add/type/width case. A 32-bank ladder merged in arbitrary
three-bank groups recovers all 1,518 pairs in both directions. A 45-bank ring initially
returned 38 admissible placements and omitted seven; the preserved follow-up uses
verified whole-view symmetry composition to recover all 45, each with 2,115 pairs
and zero incidence disagreement. This is bounded inference, not unique history.

One-sided and independently salted instance/definition/formal-pin/internal-net
renaming preserve measured incidence and edit hints on these controls. Tied tree
hypothesis sets change under renaming; their completeness is not established.
The old add-capacitor control retains an extra conditional value finding in one
alternative because unmatched-object identity is not refined by raw fields.

[Iteration4 evidence and exact commands](../../research-observatory/runs/20260916-comparison-context/iteration4/report.md)
include the frozen failure, follow-up, physical membership, raw findings, timings,
67 passing tests, unchanged primitive-role checks and explicit fallback limits.

## Budgeted incidence and component factors (2026-09-16)

The new `regional_budgeted_v5` path repairs the frozen passive join/split from
8 to 2 endpoint disagreements, with no raw distractions. Independently salted
inputs improve from 20 to 2; a fresh connection mutation and its salted version
also reach 2. The frozen 2,000-leaf failure improves from 15 to 1, and previously
rejected 5,000/10,000-leaf controls return complete maps with 1 disagreement.
Final matcher times were 1.15/2.89/6.13 seconds at about 103/135/187 MiB peak RSS.
Independent checking was measured separately. These are repeated synthetic
components, not demonstrated arbitrary large-graph capability.

Certified whole-component permutation factors preserve broad structural
ambiguity: the scale edit's old-side hint spans 200/500/1,000 interchangeable
cells. The dense 48-leaf case retains 45 pairs (1 endpoint disagreement, score
4.6); a separate complete inspection hypothesis has 8 disagreements and score 8.
Thus the unmatched scope is partly an objective tradeoff, not just retrieval loss.

All 88 owning/integration/composition tests pass. Selected large split/merge,
salted depth-5 scatter and the 45-alternative symmetric ring retain their prior
incidence/raw/hint results. [Full bounded implementation report](../../research-observatory/runs/20260916-budgeted-comparison/implementation/report.md)
contains frozen runtimes, guarded commands, budget stops and preserved failures.
