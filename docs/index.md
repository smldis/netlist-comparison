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

Run `netlist-compare` for a quick-start guide, `netlist-compare --guide` for the
operator mini-guide, or `netlist-compare --help` for organized options,
parser-derived choices/defaults and copyable examples. `netlist-compare view
RESULT --help` is the discoverable reference for saved-result filters. The CLI
help is maintained with behavior: a new CLI option or exposed matching choice
must add its purpose, default/choices, incompatibilities and limits there, with
an entry-point test; prose here supplies deeper rationale rather than a second
option inventory.

```bash
netlist-compare design.sp --inspect
netlist-compare before.sp after.sp --output result.json
netlist-compare full.sp --path-a TOP/X1 --path-b TOP/X2
netlist-compare view result.json --under-a TOP/X1 --category raw --text
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

Saved reports can be projected without netlist loading or matching. Run
`netlist-compare view result.json --help` for path, category, parameter,
hierarchy grouping and display options. Exact, case-insensitive decoded A/B
subtrees retain counterparts outside the opposite focus. `--limit` bounds text
only. Group depth is relative to each selected comparison root; text collapses
to grouped finding counts while JSON keeps the selected rows. Derived JSON keeps
the report-content hash, saved artifact hash when available, input identity,
total/shown/hidden counts,
input scope, diagnostics, unresolved and black-box status, and coupled
alternatives. Raw findings cover leaf fields; definition defaults and call
overrides stay in unfiltered hierarchy context. Wiring rows are overlapping
endpoint-partition evidence, not independent rewiring events. A view is an
inspection artifact, never a replacement comparison report.

Grouped text omits groups without selected findings; the derived JSON retains
their context and all selected leaf details.

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
explicit tops can name canonical `TOP` or any declared subcircuit. Use `--format canonical` to load saved canonical tables through SPICE Canonical's
`from_canonical_file`; SPICE/Eldo remains the default. For example:

```bash
spice-canonical before.sp --external-subcircuits pins.json --output before.canonical
spice-canonical after.sp --external-subcircuits pins.json --output after.canonical
netlist-compare before.canonical after.canonical --format canonical --black-box-missing --output result.json
```

The custom table reader also serves `--inspect` and two-instance comparison. It
preserves extraction diagnostics and black-box markers without opening original
sources or includes. Invalid canonical structure is an input error. Pin mapping
remains extraction configuration, not comparator configuration.

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

### Missing library cells

Use `--black-box-missing` (Python: `Options(black_box_missing=True)`) when missing
library implementations can be assumed unchanged across the inputs. For example,
`X1 out in 0 cell W=1u` versus `X1 out in 0 cell W=3u` can report the raw `W`
override change even without a `.subckt cell` declaration. The option works with
all matching modes; `regional` is useful for repeated cells and hierarchy changes,
while the fixed matcher still leaves repeated feature classes unresolved.

The comparison uses the case-insensitive cell reference and a compatible
terminal interface as hard candidate constraints. Unnamed retained connections
become positions `@1`, `@2`, etc., assuming stable order; supplied named signatures
retain their names. Named connection list order is not identity: reordering
entries preserves incidence, while changing role-to-net assignments supplies
wiring-change evidence. Mixed named/positional signatures, inconsistent pin counts
or named role sets, and definitions available on only one side stay unresolved. A cell
reference rename is therefore outside this assumption and stays unpaired. Missing
calls present on only one side can still appear as unpaired, not proven additions.
Current canonical objects provide explicit `Device.black_box` metadata containing
original cell identity and pin basis, plus actual token-preserving connections.
Type normalization preserves this identity. Quoted positional tokens now retain
their exact boundaries. Older canonical objects still use the compatibility path:
`source_type` identifies normalized cells and ambiguous quoted/grouped tokens in
legacy `unresolved_nets` remain opaque rather than being guessed.

Only represented connections and raw overrides are compared. Legacy synthetic
`unresolved_nets` metadata is retained in black-box evidence and excluded from
override differences. Current extraction no longer packs nets into a parameter;
a net rename therefore does not become a parameter change. `scope.black_box_assumption`, each object's `black_box`, and per-side
`black_box_leaf_count` distinguish comparable boundaries from unavailable
internals. That count overlaps ordinary disposition counts; it is not another
disjoint coverage category. Hidden internals remain in `unresolved`, and original
parser diagnostics remain visible. Certificates concern boundary incidence only,
not hidden circuitry or electrical equivalence.

Known selected subcircuits may contain black-box descendants. Selecting an
undefined call itself as a subtree still rejects with `unresolved_definition`:
there is no available internal circuit to expand. Malformed calls, ambiguous
primitive syntax and expansion-budget exclusions are not promoted to black boxes.
Model bodies remain uninterpreted; syntax-defined primitive terminals remain
usable without model declarations. The unchanged-internals assumption remains
comparator-owned; canonical owns boundary representation and serialization.

### Report fields

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

Explicit canonical black-box metadata identifies external calls independently of
instance spelling. Other calls follow canonical's SPICE instance-prefix contract:
`X` names are calls; primitive model types alone do not imply calls. A normalized call uses
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
[API/CLI examples and field semantics](https://github.com/smldis/netlist-comparison#compare-two-actual-block-calls).
The existing two-input `compare` contract is unchanged. Selection does not create
or serialize synthetic netlists. Internal port incidence, physical outer-net
attachments, and conditional pin correspondence are distinct report layers.

## Comparing incomplete libraries

Both fixed and regional modes consume the available canonical structure. Missing
include diagnostics retain their original file/line/path. Unknown X definitions
remain opaque by default, with original occurrence paths, cell targets, positional
connections and raw overrides (legacy objects may use `parameters.unresolved_nets`).
`--black-box-missing` opts into their boundary comparison as described above. Supplied external signatures
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

## Certified component presentation

Experimental `--component-presentation minimum_raw` (Python:
`Options(matching_mode="regional", component_presentation="minimum_raw")`)
refines the representative only inside previously certified whole-component
permutations. It requires regional mode; the default is `existing`.
The objective counts paired leaves whose raw type or ordered parameter list
differs, not electrical importance, numeric parameter distance or historical edits.
No raw values seed structural correspondence or rank competing leaf hypotheses.

Each admitted coordinate solves an assignment of entire component vectors.
Equal raw vectors cancel first: Hamming distance obeys the triangle inequality,
so this preserves a minimum for that coordinate. At most 256 residual components
enter one assignment; larger residual factors are skipped whole. Two alternating
A/B sweeps accept strict improvements only. Each coordinate is optimal with the
others fixed, but the joint result need not be. Only fully paired components
participate; unmatched objects and partially paired components remain untouched.
The guard bounds these matrices, not whole-process time or RAM. This work is
separate from `regional_work_limit`; elapsed time and skipped factors are recorded.

`representative_selection.components` records before/after changed-pair counts
per retained hypothesis, accepted factor permutations (indices into the unchanged
`partial_alignment.component_permutation_factors`), guards and elapsed seconds.
Assignments exchange complete slot vectors, preserving matched object sets and
represented role incidence. Structural factors and inspection regions are retained;
equal raw values never resolve their ambiguity. Defaults, call overrides and hidden
internals are outside this leaf-presentation objective and retain their prior scope.

`representative_profile_imbalances` counts unequal raw-profile populations in
fully paired A-factor slots of the final representative. Each surplus lists **all**
paths carrying that profile; it does not select which occurrence historically
changed. The count is a lower bound on differing pairs within that slot and
partner population, not an independent edit count or a whole-design finding.
Balanced slot populations can still require changed pairs when slots must move
together. B-only factors and unmatched leaves are outside this inventory.

`representative_wiring_witness` retains one maximum-overlap net bijection and
its disagreeing endpoint paths/roles. It is conditional on the selected leaf map;
net-map ties are not enumerated and may move the displayed witness. The complete
partition tables remain authoritative raw evidence. Selected-instance witnesses
use the same internal formal-port view as matching; outer attachments remain in
`boundary` and the existing physical-net fields. This report is not an electrical
equivalence test, historical edit reconstruction or complete ambiguity solver.
Saved-result views preserve all these fields in `context.representative_selection`.

The known 240-leaf external-cell example improves from 31 to 1 raw-change rows,
with unchanged complete pairing, one endpoint disagreement and broad structural
ambiguity. A 5,000-leaf repeated-motif stress improves from 2,447 to 1; this is a
resource test, not representative analog validation. Public TIA controls expose
unchanged residual noise and rename sensitivity; connected admission failures
remain. The ASS research checkout retains the evaluation report at
`research-observatory/runs/20260916-practical-comparison/implementation/report.md`
(outside this package’s documentation tree).

## Parameter-optional saved views

Use `netlist-compare view result.json --omit-parameters --group-depth 2 --text`
or `project_saved_report(report, omit_parameters=True, group_depth=2)` to begin
with represented structure. This is a pure saved-report projection; it neither
rematches nor minimizes raw differences. `--parameter NAME` and
`--omit-parameters` are mutually exclusive. Keep the default categories to retain
raw type/reference, wiring and unpaired findings together; explicit `--category`
selectors still narrow the requested output.

The filter removes `parameters.*` raw differences, including `$order`, **except**
these exact canonical reference/raw-evidence names: `model`, `source_type`,
`control`, `inductor1`, `inductor2`, `raw`, `unresolved_nets`. Their storage in a
parameter list does not make them sizing information. `type` and any other
non-parameter raw fields remain. This is an explicit field policy, not inferred
functional importance: an omitted override could affect hidden architecture.
Changed external cell references that matching cannot pair remain unpaired, with
original cell identities in `source_scope.black_box_objects`; the view invents no
paired cell-change finding.

Mixed rows retain their surviving fields; parameter-only rows disappear from
`findings.raw_pairs`. `filters.omit_parameters` and
`counts.parameter_fields_suppressed_in_path_scope` record the choice and suppressed
field count. Existing raw pair/field total/shown/hidden counts remain relative to
the full source report. The full pair evidence, defaults and call overrides remain
unfiltered in `context`; defaults/overrides are explicitly not counted or displayed
as leaf findings. They are not evaluated. The source report is never mutated.

Source diagnostics, opaque/unresolved scope, black-box assumptions, alternatives,
and conditional hierarchy memberships remain. With `--omit-parameters` and
`--group-depth`, text includes groups even when they have no selected leaf findings;
this lets hierarchy-only relocation stay inspectable. Paths and membership counts
are not proof of split, merge, redesign or historical identity. Text `--limit`
remains a preview bound and reports omitted group counts.

If a full report contains a `representative_wiring_witness`, saved views now copy
its endpoint rows into `findings.endpoint_witnesses`, under the wiring category and
the same either-side path selection. `counts.endpoint_witnesses` records
full/shown/hidden rows; groups include their `endpoint_witnesses` count. Ungrouped
text displays both schematic paths and the role. Original net-map scope and ties
remain in context. These witnesses and partition rows overlap; their counts are
not additive edits. Old reports without this optional evidence produce no witness
rows, rather than rerunning a solver.

Example hierarchy-only inspection, without parameter rows:

```sh
netlist-compare view C_regroup-regional.json --under-a CTDSM_TOP/xi20 \
  --omit-parameters --group-depth 2 --text
```

On the public development case this retains `xi20 -> xi20` (26 paired leaves) and
`xi20 -> xi20/XRC` (10), despite zero raw/wiring findings. The independently renamed
combined ADC case still has 21 selected-map endpoint disagreements versus one in a
known authored map: parameter suppression does not repair that correspondence.

## File roots and declared subcircuits

The synthetic file root is a selectable comparison scope, not a declared
implementation of an X call. Expansion and black-box reconciliation now consult
only actual subcircuit declarations when deciding whether a cell is available.
A missing cell named `TOP` therefore remains a comparable black-box boundary when
the file root is named `TOP`; selecting its unavailable internals still rejects.

Canonical permits a file root and a declared subcircuit to share a name. The
comparator's current name-keyed catalogs cannot represent both without ambiguity;
comparison explicitly rejects this valid input and requests a file-root rename.
It does not silently choose either circuit or relabel paths. A caller can make
that choice before comparison without changing the declared subcircuit or calls:

```python
from dataclasses import replace
from spice_canonical.canonical_netlist import from_canonical_file

netlist = from_canonical_file("same-name.canonical")
netlist = replace(netlist, top=replace(netlist.top, name="FILE_ROOT"))
# Choose top_a/top_b="FILE_ROOT" for file contents, or "TOP" for SUBCKT TOP.
# netlist.render() saves this explicit naming choice for the CLI if desired.
```

Choose a file-root name absent from the declarations. File-root occurrence paths
then use the chosen name; source subcircuit/call names are unchanged. Actual
duplicate subcircuit definitions remain invalid. Namespace-qualified catalog IDs
would be a separate contract change, not a hidden consequence of `--top`.

## Occupied omission challenges and represented population

`Options(matching_mode="regional", omission_work_limit=512)` /
`--matching-mode regional --omission-work-limit 512` opt into an additional
omission-seeded beam. Default 0 disables it. This revises the former unused-only
completion boundary: an unused leaf can displace an occupied compatible partner,
then the released leaf can compete again across hierarchy. Adding an unused pair
is also allowed. Full role-incidence disagreement plus 0.6 per omitted leaf judges
every complete injective candidate; names, values and fixed retrieval distance
are not candidate admission rules. External identities/interfaces stay hard.

The score budget includes seeds. Fixed limits: width 12, depth 3, 64 supported
initial omissions, 32 best-score output hypotheses. Worse intermediate states can
survive the beam. Equal-score output prioritizes distinct omission sets. Better
scores replace worse primary hypotheses; ties preserve the previous representative
when retained. Exact twin/certified component presentation follows this search.
Full-map score cost depends on circuit size, and stored states cost up to
O(score budget × paired inventory); this is not a wall-time or RAM cap. No
populated seed is an admission limitation, not an additions finding.

`partial_alignment.omission_search` is the evidence contract:

- `stop`, `work_used`, `work_limit`, `rounds`, `beam_pruned`, `seeds_truncated`,
  `alternatives_truncated` and fixed limits disclose bounded coverage.
- `baseline_score`, `best_score` and endpoint counts describe this search before
  incidence-preserving presentation. `baseline_pairs` reconstructs the incumbent.
- `witnesses` contain coupled removed/added pairs for retained best-score maps.
  `baseline_tied_exchanges` preserve changed-omission baseline ties even if a
  later improvement supersedes them; `baseline_ties_truncated` bounds this list.
- Each initially omitted supported object's `challenges` record gives compatible
  and occupied candidate counts, best sampled participating/omitted scores and
  their difference (participation minus omission). Missing participation produces
  null, never infinite confidence. `participating_witness` reconstructs the best
  sampled forced-participation explanation. These diagnostic maps need not be
  primary alternatives. All deltas apply to `baseline_pairs` jointly.

Search considers omission-seeded additions/exchanges, not arbitrary full-coverage
swaps or deletion moves. Beam order, depth, retained alternatives and opaque scope
remain limitations. No exhaustive-search, history or calibrated-probability claim.

`population_evidence` is always included in regional reports. Unequal counts in
hard-compatible represented domains give a joint lower bound on selected-map
omissions, independently of individual ambiguity. Native primitives form one
domain because type changes are admissible; external domains use stable cell and
interface. Opaque leaves are excluded and separately counted; expansion status
qualifies the materialized inventory. Bounded path examples are inspection aids,
not an exact new-instance list. These are population observations, not edit events.

Saved projections keep population and search evidence in full context. Selecting
`unpaired` also exposes `findings.population_groups` and `findings.omission_search`,
with separate `counts.population_groups`. These carry **unfiltered whole-scope**
evidence even under path filters; per-object raw/wiring/unpaired counts retain
their previous semantics. The text preview labels this scope and shows coupled
path exchanges and conditional margins. Selecting other categories hides these
findings but retains their context. A symmetric 2→3 population can therefore
show zero unpaired object rows and still visibly report represented surplus one.

## Challenge already paired counterparts

`Options(matching_mode="regional", swap_work_limit=512)` /
`--matching-mode regional --swap-work-limit 512` enables a bounded swap stage
following regional alignment and optional omission search. Zero disables it;
existing defaults remain unchanged. This can challenge a wrong correspondence
inside a fully paired compatible class, which omission-seeded search cannot reach.

A width-12 best-first beam explores occupied-counterpart transpositions to depth
8. At least one swapped pair has a represented terminal discrepancy under the
current optimal net map; all compatible occupied counterparts compete for a
32-proposal shortlist per expansion. Conditional fixed-net-map mismatch orders
proposals, while freshly optimized **full represented terminal incidence plus
0.6 per omitted leaf** ranks every admitted complete map. Worse intermediate
states can survive. Native type changes remain admissible; external cell/interface
compatibility and injectivity remain hard. Names and raw parameters do not rank
this search. Every swap preserves both matched sets of its originating seed.
Different incoming alternatives may already have different matched sets.

`partial_alignment.swap_search` records counted full-map scores (including seeds),
cheap proposal comparisons separately, beam/branch/depth/output pruning, scores,
runtime and reconstructible path witnesses. `baseline_pairs` plus a witness's
removed/added pairs reconstruct its map; `seed_index` indexes `seed_pairs` and
identifies its originating incoming alternative. A difference in inventory
between seeds is not an inventory change caused by a swap. Score trajectories
start at that seed. Up to 32 equal best maps survive; the previous representative
survives ties when it remains best. All alternatives remain incomplete and
conditional. Earlier `omission_search` selection describes the preceding stage;
it need not describe the final representative after swaps. Existing twin/factor
presentation can subsequently choose an incidence-preserving representative.

Streaming top-32 proposal retention uses linear active-pair context and bounded
proposal storage, without a quadratic candidate list or deduplication set. Cheap
proposal enumeration can still take quadratic time, and evaluated maps/net maps
can consume memory proportional to budget times inventory. The score budget is
not a whole-call time/RAM bound. Missing incumbents abstain explicitly. Truncated
branches, finite beam/depth, discrepancy admission and traversal order can miss
better maps. No global QAP enumeration, exhaustive symmetry, calibrated confidence,
unique historical identity or optimality is claimed.

Observed on the validated renamed public mutation: 12 endpoint discrepancies
without omission search, 10 with omission512, 6 with omission512+swap512; 285 pairs
and both matched sets remain fixed during the swap stage. Swap-only512 also reaches
6. A 2,048-score swap probe still misses the known feasible two-discrepancy witness.
Public redesign stays at one after omission search; original combined stays at
two. A six-object all-paired control crosses 3→5→0; a fresh five-object full-coverage
edit/permutation improves 5→1. These are development controls, not representative
workplace accuracy or recovery of unique edit history. Connected129 still lacks
an admitted regional incumbent.

In saved views, the wiring category retains this whole-comparison search evidence
and displays bounded path witnesses. Subtree filters still select leaf findings;
search context remains explicitly unfiltered. Run `netlist-compare --guide`,
`--help`, and `view --help` for current workflows, controls and examples.

## Operator-supplied local windows

`Options(matching_mode="operator_scoped")` opts into local evidence for an
explicitly supplied region relationship. It does not rank or discover global
architectural changes. Existing fixed/regional modes and their evidence keep
their contracts. A region may be one available hierarchy occurrence, a supplied
union of occurrences, or the selected whole top in each of two canonical inputs.

```python
from netlist_comparison import Options, compare, compare_instances

options = Options(matching_mode="operator_scoped", black_box_missing=True,
                  operator_time_limit=180, operator_memory_mib=3072)
local = compare_instances(netlist, top="TOP", path_a="TOP/XOLD",
                          path_b="TOP/XNEW", options=options)
revision = compare(before, after, top_a="TOP", top_b="TOP",
                   paths_a=("TOP/XOLD",),
                   paths_b=("TOP/XLEFT", "TOP/XRIGHT"), options=options)
```

These functions return the existing complete report envelope with an explicit
`operator_scoped` extension. Global candidate groups and representative pair IDs
remain empty; local leaf/net maps are conditional hypotheses inside the window.
Source catalogs, scope provenance, anonymous solver inputs, proof statuses,
coverage sensitivity and indivisible charges remain available in full JSON.
`project_saved_report(..., categories=["local"])` and
`view RESULT --category local --text` select cards without rematching. Saved
views retain the full source window as context. Parameter-name filtering belongs
to legacy raw-pair views; local parameter evidence is a class multiset, not a
claimed per-leaf identity. Use `--omit-parameters` to hide that lane.

### Representation and objectives

The matcher receives only anonymous integer leaf/net indices, case-folded literal
cell/model classes, the named-versus-positional terminal basis, normalized roles,
incidence, and literal parameter values. Its structural metadata whitelist is
explicit: black-box cell and pin basis only. Source path, instance name,
definition name, other metadata and net spelling are addresses/output only.
This structural whitelist does not filter explicit canonical black-box instance
overrides: all of those parameters remain in the parameter-detail lane, including
names such as `model`, `source_type`, `raw` and `unresolved_nets`.
Roles normalize consistently throughout candidates, hints, witnesses and scores;
a normalization collision is an input error. Positional `@1`, `@2`, etc. never
become inferred semantic pin names. Parameters do not choose correspondence.
They form a separate equal-class, equal-population multiset comparison; values
and expressions are not evaluated. Explicit global declarations and ordinary
high-fanout incidence follow canonical expansion; no additional global net is
inferred or deleted.

The complete compatible leaf catalogue requires equal literal cell class, pin
basis and role set. Different represented interface widths remain inventory
residuals and cannot pair across widths; they do not suppress independent
supported parameter/connectivity evidence elsewhere in the supplied region. Binary variables select injective compatible leaf pairs and
an injective net map. Each matched leaf terminal contributes one mismatch when
its two nets are not paired. The weighted objective is
`5 * terminal_mismatches + 3 * (unmatched_A + unmatched_B)`. Separate queries
minimize mismatch at maximum compatible cardinality `K` and at `K-1`; `K=0`
has an explicit empty-witness certificate. All three results must be optimal
before a necessary terminal-residual card is emitted. Dropping one leaf pair may
remove a residual; the report retains that coverage sensitivity.

The implementation preserves this binary objective and acceptance prerequisites
using existing SciPy/HiGHS MILP. Anonymous topology refinement supplies only
candidate witnesses. A zero mismatch witness attains the nonnegative lower
bound. At full two-sided coverage, maximum injective net assignment over relaxed
class/role endpoint capacities yields a separately reconstructed mismatch lower
bound; attaining it certifies optimality. A partition into `K`, `K-1` and all
smaller cardinalities can certify the weighted optimum, otherwise it needs its
own solve. Solver results require an integer incidence witness, optimal solver
status and matching dual bound within `1e-6`; this trusts the native optimizer's
bound, not a formally verified proof trace.

A cold, deterministic anonymous index portfolio uses identity, then seeds 101
and 202 on incomplete queries. It never chooses by case identity or favorable
localization. Transfers validate the complete bijection, original incidence,
compatible catalogue and objective before acceptance. The first certified
witness is retained. Alternative optima remain explicitly unresolved; one
optimal witness cannot establish unique leaf, net or historical edit identity.
A terminal focus includes touched endpoints, partners and their compatible
classes. Repeated explanations may therefore enlarge the inspection region.
No results/cache are shared across API calls.

### Cards, scope and resource accounting

Architecture cards combine literal inventory/interface residuals, represented
population surplus and certified terminal residuals. Unknown label semantics
cannot distinguish relabeling from replacement. Parameter cards show literal
class population changes without inventing a per-leaf pairing. Card text gives
bounded schematic addresses and values; JSON retains the complete context.
Internal selected-occurrence nets preserve formal boundary separation. Scope spellings that resolve to the same canonical root are deduplicated before
composition, so case/percent-encoding aliases cannot create connections. Supplied
unions join physical connections shared by distinct pieces; their scope provenance keeps
those maps inspectable. Exterior evidence separately reconstructs physical nets
with outside represented endpoints. Its current scalar is the crossing-net
count: changed attachment identity at equal counts is **not detected**. Every
counted crossing net has an actual outside witness path. Full-top incomplete or
opaque expansion prevents an environment claim. Hidden black-box internals
remain unavailable, even when their interfaces are represented.

An admitted query has at most 64 leaves and 64 nets per side and at most 16
compatible counterparts per leaf. Presentation admits at most 12 cards and
100 distinct A+B paths, charging every selected leaf, every supplied scope
address, and exterior witnesses when used. Cards are indivisible: saved filters
retain their full charges. A quiet card list alone is not certification, nor an
unchanged verdict; inspect status, omitted lanes and retained evidence. Inventory
or parameter facts may be shown even when a bounded correspondence query cannot
be certified. No such incomplete query supplies necessary terminal evidence.

The default isolated worker allowance is 60 seconds/3072 MiB with one CPU and
at most 10 seconds per solve; configure `operator_time_limit` /
`--operator-seconds` for server-minute trials and `operator_memory_mib` /
`--operator-memory-mib` for RAM. Linux/POSIX fork and `/proc` are currently
required. The parent checks time and sampled worker RSS approximately every
20 ms, kills on exhaustion, and records an incomplete result. RSS sampling can
overshoot briefly and is not a hard allocation ceiling. Worker output is capped
at 32 MiB. CLI loading, expansion, matching and worker JSON encoding fall inside
the computation deadline. Final stdout/disk serialization and writes fall
outside; API input parsing done by the caller also falls outside. This is not an
end-to-end shell-command deadline. Fork embedding in a multithreaded caller is
not yet validated.

The implementation's control suite covers changed/quiet inputs, ambiguity,
alternative optima, positional/named black boxes, mixed-case role normalization
and rejection, cold ordering fallback, corrupted witnesses/charges, supplied
unions, exterior-only evidence, budgets, canonical CLI, JSON and saved views.
The mathematical model follows the studied supplied-region portfolio; replacing
its CP-SAT backend with SciPy/HiGHS has not reproduced its target-scale timing.
No automatic discovery, private-case accuracy, integration maturity or electrical
equivalence claim follows. The next useful evidence is an opt-in real canonical
scope trial with status, cards, elapsed time and charges retained.

Saved local views reconstruct proof/status consistency, inventory and parameter
multisets, terminal focus, coverage sensitivity and complete deterministic cards
from retained anonymous incidence and witnesses. Relabeling a lane, fabricating
card evidence, changing its focus/meaning or weakening its charges is rejected.
This checks internal consistency, not cryptographic authenticity of a wholly
rewritten report and its source inputs.
