# Netlist Comparison

Netlist Comparison proposes locations to inspect in two netlists. Its Python
API consumes current `spice_canonical.canonical_netlist.CanonicalNetlist` objects;
the CLI uses that package's file extractor. It returns JSON-compatible data.
It does not recover edit history, prove equivalence or infer electrical effects.

```{toctree}
:maxdepth: 1

Evaluation and limitations <evaluation>
```

## Start without reading a manual

Run `netlist-compare` for a quick-start guide, or `netlist-compare --help` for
examples, option explanations and defaults.

```bash
netlist-compare design.sp --inspect
netlist-compare before.sp after.sp --output result.json
netlist-compare full.sp --path-a TOP/X1 --path-b TOP/X2
```

Inspection lists circuit names, pins, actual block paths and input problems.
Comparison selects populated file-level `TOP`, or the sole definition when the
file level is empty. Multiple definitions require an explicit choice; the error
lists available names. Use `--top-a`/`--top-b` for two files or `--top` for two calls.

An attached terminal shows a readable preview with schematic paths, raw changes,
coverage, input diagnostics and uncertainty. Pipes retain full JSON; `--text` or
`--json` selects either form explicitly. `--output` always saves full JSON, with
an abbreviated preview on stderr when stdout is redirected (suppressed by `--json`).
`--limit N` controls displayed rows only. Text is a preview, not complete evidence:
defaults, call overrides, hierarchy and pin details remain in JSON. Matching
remains `fixed` by default; `--matching-mode regional` opts into the experimental
hierarchy/regrouping matcher. No interactive prompts are required.

Exit 0 means completion, possibly partial; exit 2 means invalid usage/input or I/O.
No equality/difference exit-code convention or new matching semantics is introduced.
`--inspect` expands under the same object/depth budgets as comparison, without
matching. Explicit top selection still accepts an empty root.

## Start with the example

From the ASS root, after `uv sync --group dev`:

```console
.venv/bin/netlist-compare netlist-comparison/examples/before.sp netlist-comparison/examples/after.sp --top-a TOP --top-b TOP --output /tmp/comparison.json
```

`python -m netlist_comparison` is the same CLI. Select `--format ngspice` for
ngspice syntax; the default is Eldo. Both files use the selected format. The
explicit tops can name canonical `TOP` or any declared subcircuit. Do not pass
rendered canonical tables as input: canonical has no parser for that format.

```python
from spice_canonical.canonical_netlist import from_file
from netlist_comparison import compare, InputScope, Options

a = from_file("a.sp")
b = from_file("b.sp")
report = compare(a, b, top_a="TOP", top_b="TOP",
                 options=Options(candidate_top_k=8),
                 scope_a=InputScope(global_nets=("0", "VDD")),
                 scope_b=InputScope(global_nets=("0", "VDD")))
```

Inputs are not modified. A reordered device/definition list gives the same
result except timings. The input digest identifies **retained canonical data**,
not the full deck, include tree or model library.

## Read the result

| Field | Meaning |
|---|---|
| `scope`, `options` | Input omissions, explicit scoping knowledge and experimental budgets/costs |
| `a`, `b` | Object, occurrence and definition catalogs; raw profiles; diagnostics; disjoint coverage accounting |
| `candidate_edges` | Possible **feature-class** counterparts, scores and assignment eligibility |
| `groups` | Candidate competition; restricted assignment domain; coupled hypotheses and excluded classes |
| `pair_options` | A/B object paths, evidence, raw field differences and terminal rows for each pairing |
| `representative_pair_ids` | One feasible tentative choice used for the following tables, not a verified mapping |
| `connectivity` | Net membership of paired terminal tokens, explicitly conditional on the representative choice |
| `hierarchy` | Conditional ancestor memberships, possible occurrence and definition counterparts; all event labels are null |
| `metrics` | Stage times, actual class-pair scores, retained edges and solver calls |

For a pair such as `TOP/XOLD/XCH/M1` →
`TOP/XMOVED/XCORE/XNEW/M8`, the example reports `parameters.W: ["W"] → ["6u"]`.
That is a raw expression difference under a tentative pairing, not an evaluated
width change. A missing parameter is `null`, distinct from a present value.
Duplicate assignments remain ordered lists; parameter-order changes are retained.
Defaults are compared separately from call overrides.
Terminal rows retain both raw local bindings and resolved net identifiers.
Resolved identifiers can differ because of an ancestor/net rename as well as a
binding edit; neither identifier inequality nor a raw net-label change alone
proves rewiring. The conditional net-partition table supplies the connectivity
evidence available in the represented scope.

Use `groups[].hypotheses` jointly: alternatives in one group must satisfy
one-to-one leaf correspondence. Mixing arbitrary rows can produce an invalid
many-to-one result. `alternatives_complete` remains false: checking selected
edges does not enumerate all near optima and retrieval may have omitted candidates.
`selected_edges_checked` describes checks within the **restricted** solver domain.
It does not include competition from repeated/excluded classes.

`tentative` means selected without an alternative found in the performed checks;
it is not calibrated confidence. `ambiguous` means alternative solutions were
found. `unpaired` means absent from this proposal, not a proved insertion/deletion.
Opaque devices and unsearched regions remain explicit. Per-side coverage counts
partition the materialized leaf catalog. Hidden leaf totals behind truncated or
opaque calls are unknown; they are not counted as known primitive totals.

Repeated classes contain raw-value profiles with member paths. Those profiles
can reveal a distinctive edited value without choosing which old repeated copy
corresponds to it. Class equality means equal search features, not automorphism.
Names, parameter values and functional labels do not determine these classes.

## Input scoping

Subcircuit bindings, occurrence-local nets and ground `0` are resolved. Extra
global nets must be supplied through `InputScope` or repeatable CLI
`--global-net`. `globals_complete=True` / `--globals-complete` is a caller
assertion, not something the extractor verifies. Without it, global declaration
completeness remains unknown. No alias inference is performed.

Canonical model bodies, global parameter semantics, some simulator directives,
source maps and nonterminal references are not available as complete comparison
semantics. For example, control-device names can be retained as raw parameters
without being resolved as graph edges. Canonical diagnostics are preserved even
when comparison can continue. No diagnostics does not imply complete input.

This adapter follows canonical's SPICE instance-prefix contract: `X` names are
calls; primitive model types alone do not imply calls. A normalized call uses
its retained `source_type` to find the original definition. Unknown definitions,
unrepresented connectivity, malformed call bindings, recursion and depth/size
limits produce opaque or unfinished regions. Duplicate definition/device/pin
identities raise an error. Primitive terminal roles pair by case-insensitive
name; no source/drain swapping. Formal pin names bind within each revision and
may differ across revisions without blocking expansion.

## Algorithm and actual bounds

1. Expand occurrence paths while keeping definitions/defaults and raw call data.
2. Compute fixed per-terminal presence, degree, same-device net sharing, and
   degree-weighted neighbouring primitive-kind histograms. Exclude self support.
   High-degree nets are downweighted for search and fully retained for reporting.
3. Group identical feature/type rows, then compute class-to-class costs in array
   tiles. Retain the union of each direction's top `k` classes plus cutoff-tie
   diagnostics. Names and raw parameter equality are not scoring inputs.
4. Require external-neighbour support and cost below leaving both sides unmatched.
   Isolate repeated, cutoff-tied or incompletely searched classes as unresolved.
   Propose optional assignments among the remaining singleton classes. A repeated
   class no longer blocks all singleton evidence in its connected region.
5. Re-solve after forbidding selected edges, within a global check budget. Build
   raw comparisons, terminal-token overlap and hierarchy membership tables.

The singleton restriction is an explicit heuristic: the optimum is for that
restricted cost graph, **not** for all candidate devices. Excluded alternatives
stay in the report. No match propagates into another node's feature or score.

| Option | Initial default | Limit or role |
|---|---:|---|
| `max_objects` | 20,000 | Materialized occurrences plus leaves per revision |
| `max_depth` | 32 | Maximum expanded occurrence depth, root=0 |
| `candidate_top_k` | 8 | Classes per direction; copies within a class remain referenced |
| `tile_size` | 128 | Maximum score tile side |
| `max_pair_scores` | 25,000,000 | Class comparisons; a tile that would exceed it is not evaluated |
| `max_component_nodes` | 256 | Singleton rows plus real columns admitted to one solve |
| `max_component_edges` | 4,096 | Singleton candidate edges admitted |
| `max_alternative_checks` | 16 | Additional solves across the entire comparison |
| `unmatched_cost` | 0.3 per side | Experimental abstention cost |
| `type_penalty` | 0.12 | Soft type-change cost |
| `ambiguity_tolerance` | 1e-9 | Numerical near-optimum tolerance, not accuracy calibration |

All these values are prototype settings. None is established as an accuracy or
performance target. The CLI exposes the most useful budgets; the Python API
exposes all of them. A positive size budget is not a wall-time deadline. SciPy's
native solver has no timeout parameter; this prototype admits small problems
and makes **no hard wall-time promise**. Use a process-level limit externally if
one is necessary.

The structure cost is the L1 distance between fixed feature vectors divided by
8, plus the configured type penalty for unequal types. This normalization is
part of the experimental scoring model; raw parameter/name agreement adds no
bonus. A pair must cost strictly less than twice `unmatched_cost` to be eligible.

For `n` expanded leaves, `E` incidences, feature width `f`, class counts `cA,cB`,
and depth `h`: feature storage is O(nf), screening is O(cA*cB*f) before top-k
selection overhead, retained class edges O(k*(cA+cB)), and tiles have bounded
size. In the worst case class counts equal device counts. Net overlap is O(E)
under the chosen pairing. Ancestor membership costs O(n*hA*hB). Solver workspace,
alternative solves, raw catalogs/profiles, sorting and output are additional.
Input validation and identity also scan retained definitions, including
unreachable definitions; expansion limits do not cap the supplied input's size.
The repeated stress case does not benchmark the worst-case all-distinct search.

## Extensions are evidence-driven

The current experiment supports extraction, bounded execution and conditional
reporting. It also exposes excessive ambiguity. The second experiment below compares frozen context and bounded anchor
growth against this baseline and path/name matching; its held-out failure keeps
both opt-in. Indexing is a later response to measured screening cost. Interactive
schematic source maps and move/regroup labels are not part of this first slice.

## Opt-in matching experiments

The fixed-feature algorithm above remains the default. Select exactly one:

```python
Options(context_mode="frozen_neighbors")
Options(matching_mode="anchor_growth", growth_rounds=64)
```

The corresponding CLI flags are `--context-mode frozen_neighbors` and
`--matching-mode anchor_growth`. Combining them is rejected. The frozen pass
adds degree-weighted differences between bags of neighbouring v1 signatures;
`context_evidence` records its recipe, original signatures, net aggregates and
self-exclusion. It uses no inferred pairs.

Anchor growth replaces the fixed-feature proposals while retaining its classes
and `candidate_edges` as **reference alternatives** (`candidate_basis` states
this). `reference_assignment_domain` describes the reference solve, not the
growth domain. Growth can pair individual members of repeated reference classes.
Each pair's evidence gives its WL anchor signature or earlier support pair IDs,
terminal tokens and round. `relational.joint_hypothesis` binds the complete
conditional proposal; dependencies can cross the presentation groups.
`inspection_regions` holds compact unresolved conditional shortlists under a
one-to-one constraint. Neither these shortlists nor representative pairs erase
broader reference alternatives. Region alternatives are not exhaustively solved.

Growth `cost` is zero for an exact anchor or one minus its support Dice, with
`cost_basis` explicit; it is not the v1 unary cost. Reports preserve raw fields,
unknown global scope, full net incidence, null hierarchy-event labels and
per-object accounting. The growth kernel never evaluates parameter expressions.

**Known failure:** a newly created boundary can supply false unique anchors and
misdirect growth. The held-out mutation produced 110 historical disagreements.
Growth also abstains where edits remove every anchor. It is an experimental
inspection aid, not a replacement default. See the second experiment in
[evaluation](evaluation.md) for positive evidence, failures and exact commands.

### Regional graph checkpoint

`Options(matching_mode="regional")` / `--matching-mode regional` selects
`regional_budgeted_v5` when the new incidence/factor path wins; the retained
frontier fallback reports `regional_multifrontier_v4`. Fixed v1 remains the default. The separate
`partial_qap` mode retains the older dense reference.

Two candidate decompositions compete using the same physical-leaf objective:

- Authored occurrences of at most 128 leaves, opening oversized wrappers.
- Hierarchy-independent pieces: multi-terminal cores joined on sparse nets,
  excluding globals, nets above 32 distinct leaves, and gate/body-only fanout;
  passives attach only to an unambiguous core. Unresolved bridges stay residual.

The second runs when the physical partitions differ. This permits real primitive
splitting/merging without collapsing instances or treating new boundaries as
identities. This fallback retains limits of 64 pieces and 256 residual leaves; search uses a 192-state
beam in both directions, up to 24 final placements per direction within 0.5 of
best coarse cost. Full role-labelled incidence ranks complete plans with
`endpoint_disagreement + 0.6 * unmatched_leaf_count`. These are heuristic costs,
not calibrated confidence or a globally minimum edit proof.

Local interface sets can differ in cardinality. Up to six nets, all injections
of the smaller set into the larger supply tentative distance context. Larger
sets use per-role distance distributions. No formal slot, block/pin/net name or
parameter value decides structural correspondence. The small passive-only regional
fallback uses structure-only partial QAP; its separate public reference mode still
has a weak-name start. Large unsupported shapes expose their stop and coverage.

Complete zero-disagreement hypotheses may generate whole-view symmetries, verified
against primitive types and every terminal incidence. Their bounded composition
adds supported alternatives (limit 64), without claiming discovery of every
symmetry. Partial maps and actual incidence disagreements cannot seed this step.

`partial_alignment` exposes frontiers, piece membership, trial budgets, complete
hypotheses, full endpoint error, unpaired objects and symmetry-closure limits.
`groups[].hypotheses` refers to complete coupled leaf assignments.
`inspection_regions` unions alternatives and exact terminal twins, explicitly
incompletely. `hierarchy.frontier_membership_hypotheses` gives compact conditional
many-to-many authored membership for the corresponding hypothesis index. These
are supported memberships, not historical split/merge event labels.

`representative_selection` records raw-field refinement confined to **exact
same-type, same-role/net twin classes**. Two bounded assignment sweeps strictly
reduce displayed field differences; matched object sets and incidence stay fixed.
The classes remain ambiguous even when a minimum-change representative is unique.
Real value edits remain visible; equal fields do not disprove hidden permutations.
Raw findings are conditional on each displayed pair; top-level connectivity uses
the representative. `reference_proposals` preserves original v1 output.

Pure passive repartitioning, inseparable cores above 128 leaves, dense coupling,
local ambiguity exceeding budgets and representative workplace accuracy remain
open. Positive split/merge and independent-rename measurements do not establish
arbitrary hierarchy invariance. See [evaluation](evaluation.md).

### Budgeted incidence and factor path

Before a large frontier search, global nets and nets above 32 leaves are cut into
components, retaining their full incidence as shared boundaries. Components up
to 64 leaves with distinct four-round structural labels get a canonical **exact**
type/role/incidence certificate. WL equality alone is never certification. A
role-profile boundary assignment must have no row tie; at most eight cut nets
are admitted. Exact repeated certificates cancel without a quadratic region
assignment. The remaining at-most-64-leaf/64-net problem uses partial injective
net maps and optional leaf assignment. Unknown nets give an optimistic search
bound; a 64-state beam ranks it, and full incidence scores feasible incumbents.
Primitive type is a soft search cost and final tie-break, never a raw-value hint.
The same search challenges nonzero small whole-view incumbents. Other shapes
retain the earlier multi-frontier behavior.

`partial_alignment.component_permutation_factors` records verified same-side
component permutations as equal-width path arrays: **whole rows permute, slots
move together**. `inspection_regions` includes their counterpart orbits, without
materializing their factorial joint hypotheses. These factors qualify both
`groups[].hypotheses` and boundary-pin evidence; enumerated representatives and
pins do not exhaust those permutations. Component certification requires unique
structural labels; internally symmetric components currently use the fallback.

`regional_work_limit` defaults to 50,000. `compute_budget` records the limit,
consumption, exhaustion and exact scope: net-map candidate assignments plus
component certificates in the new search. This counter excludes the existing
frontier search, expansion, reporting, diagnostics and native-call duration; it
is neither a wall deadline nor a hard/estimated RSS cap. Exhausted search keeps a
feasible incumbent or certified paired prefix and reports unpaired scope. Beam,
local size and certificate restrictions still limit quality even with more work.

The normal objective remains endpoint disagreements plus 0.6 per unmatched leaf.
A small `coverage_tradeoffs` list records optional completion of omitted leaves
with mapped endpoint support, using a diagnostic omission cost of 2 per side.
Each row includes its full path-pair map, extra pairs, original objective score,
endpoint disagreements and unmatched count. A strictly better completion becomes
the incumbent; a higher/equal-cost completion stays separate from primary pairs,
connectivity, inspection regions and boundary hypotheses. Thus omitted changed
objects have reviewable conditional locations without forcing complete pairing.

## Selected instances and boundary pins

`compare_instances(netlist, *, top, path_a, path_b, options=None, scope=None)`
compares two actual block calls in one full canonical input. See the
[API/CLI examples and field semantics](../README.md#compare-two-actual-block-calls).
The existing two-input `compare` contract is unchanged. Selection does not create
or serialize synthetic netlists. Internal port incidence, physical outer-net
attachments, and conditional pin correspondence are distinct report layers.

## Comparing incomplete libraries

Both fixed and regional modes consume the available canonical structure. Missing
include diagnostics retain their original file/line/path. Unknown X definitions
remain opaque objects with original occurrence paths, targets, raw positional nets
(`parameters.unresolved_nets`) and raw parameters. Supplied external signatures
retain named/raw/resolved connections but still provide no internals. These objects
have `coverage.opaque` / opaque dispositions and unresolved regions, with unknown
hidden leaf counts. They are not paired or labelled unchanged/deleted. Regional
hypothesis unmatched counts include them; those counts are not deletion claims.

Regional component factorization skips components containing opaque objects instead
of abandoning every certified sibling component. Their known neighbours may enter
the bounded remainder search. Opaque leaves remain in the full report but do not
consume its known-leaf remainder admission limit. Certificate failures unrelated
to opacity, oversized components and large known remainders retain existing fallback
limits. Component permutation certificates concern represented typed incidence,
not hidden library internals or whole-design equivalence. Factors explicitly label
this represented scope. Undefined-call positional attachments may themselves be
unrepresented; symmetry of represented incidence does not establish symmetry of
those attachments or a hidden library implementation.

Missing device model bodies do not erase syntax-defined MOS/diode roles: canonical
extraction supplies generic types and raw model identifiers/parameters, and those
leaves remain comparable. No polarity, model contents or electrical meaning is
inferred. Canonical now marks BJT terminal/model splits with undeclared models and
extra positional tokens unresolved, retaining raw tokens and a source diagnostic.
The comparator treats these as opaque `unrepresented_connectivity`, so guessed
terminals cannot enter correspondence or factor certification. Unambiguous
three-terminal BJTs remain usable without a model declaration. A missing library may therefore contain
unknown model semantics, unknown subcircuit internals, or both.

Selecting a known call compares its available descendants even if other descendants
or unrelated siblings are opaque. Direct selection of an unavailable call, or a path
through one, raises `ValueError` (`unresolved_definition`; CLI exit 2). Full-input
extraction diagnostics remain full-input diagnostics in each selected view; they are
not reassigned to the selected subtree. Missing root files and structural validation
errors still fail. Deliberately stopped includes and `.LIB` boundaries are not
reported as missing files by canonical extraction, and absent primitive model bodies
alone are not diagnosed. `expansion_complete` only means the object budget was not
exhausted; consult diagnostics, unresolved regions and coverage for incomplete scope.

Small mixed missing-library regression cases retain edited sibling comparisons in
both modes. Regional repeated-component controls retain 5,000 available pairs plus
explicit opacity. Fixed matching still has its existing repeated-class limitations;
missing-library support does not turn ambiguous repeated devices into unique pairs.
