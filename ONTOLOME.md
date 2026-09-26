# Netlist Comparison Ontology

## Purpose and scope

Help an engineer locate possible counterparts and differences in two schematics
through their canonical netlists. This unit owns occurrence expansion, heuristic
correspondence, conditional raw comparisons, and compact file-based results.
SPICE Canonical owns extraction; the original simulator inputs remain authoritative.

## Mode of being

**Development state:** `prototype`

This first slice tests whether fixed local structural features and optional
assignment can produce useful inspection regions without a propagation/repair
state machine. Thousands of instantiated devices and meaningful depth 4–5 remain
the target, not a demonstrated general capability. Synthetic resource checks do
not establish workplace accuracy or inspection benefit.

## Commitments

- Consume public canonical objects and preserve occurrence/definition separation,
  raw fields, terminal roles, defaults and explicit call overrides.
- Search across hierarchy. Repeated search features yield candidate classes,
  not identities. All assignments remain tentative and their alternatives coupled.
- Keep global scoping assumptions, missing semantic information, opaque regions,
  search truncation and assignment limits visible, including when nothing matched.
- Compare connectivity only conditional on an explicit endpoint correspondence;
  retain high-degree nets and body terminals in the report.
- Provide a Python API and headless CLI with complete JSON evidence and bounded,
  deterministic terminal previews. Compact data remains the primary artifact.
- Keep the CLI independently discoverable: parser help and the built-in operator
  mini-guide describe exposed choices, defaults, incompatibilities and limits;
  focused entry-point tests keep that presentation tied to runnable behavior.
  Regional omission and paired-swap score budgets are explicitly opt-in and do
  not turn bounded candidate exploration into a correspondence verdict.

## Boundaries and possibilities

No equivalence proof, electrical explanation, inferred circuit function, generated
prose, parameter evaluation or edit-history recovery. Initial hierarchy output is
membership with null event labels. Indexing, context reweighting and source-map
adapters are possible extensions only when evidence justifies them. Definition
sharing must not collapse physical occurrences or force one-to-one definitions.

## Child composition

No child units. The parent registers this independently installable package and
its explicit dependency on the public `spice_canonical.canonical_netlist` types.
The implementation is published in its own public Git repository and composed
into ASS as a submodule. Standalone checkout instructions identify the tested
canonical revision; research history remains in the observatory. Publication
does not change prototype maturity or extend the demonstrated accuracy domain.

## What the first execution taught us

The small moved-and-edited motif produces four tentative counterparts and retains
its raw width/default differences. The synthetic 2,067-leaf depth-4→5 composition
retains the generator's counterparts as class candidates, but most leaves remain
unresolved and the edited device's candidate region spans 704 leaves per side.
This is evidence against treating the initial features as sufficient for the
eventual inspection goal, despite inexpensive execution on that repeated input.

Repeated classes initially vetoed every proposal in their connected candidate
region. Isolating them and explicitly solving a restricted singleton domain
recovers some useful proposals without inventing repeated-copy identity. That
restriction is now an implementation commitment: its optimum is not a global
optimum with excluded alternatives restored. The fixed-feature default remains the reference. A representative complex
analog fixture remains an external-validity gap.

## Bounded relational experiment

Two opt-in experiments now test fixed neighbouring signatures and role-aware
WL-anchor growth adapted from IP-Matcher. Growth explicitly revises the blanket
exclusion of repeated feature-class members: earlier tentative correspondences
can distinguish individual leaves. Support flows only from earlier rounds, has
inspectable provenance, and remains conditional on its anchors. Physical device
multiplicity and reporting incidence are retained; search can suppress dense-net
influence without suppressing body/supply differences in the report.

Observed: growth yields 1,231 historical agreements and a useful edited-device
hint on the known 2,067-leaf hierarchy. On a held-out bridge removal with body
and device edits, seven locally unique anchors produce 110 historical disagreements. Root later
constructed a complete admissible alternative history containing those placements;
historical disagreement alone does not prove a graph mismatch. Uncertainty-labelled propagation alone does not make a narrow
inspection hint useful. All surviving historical counterparts remain in the
reference candidate graph, so the limiting assumption is anchor identity rather
than retrieval coverage. The new mode remains experimental; v1 is unchanged as
the default, and neither mode establishes general revision accuracy.

Possibility: jointly compare regional alignment hypotheses using preserved
terminal incidence and unmatched cost, allowing locally attractive anchors to
be rejected. This is a next experiment, not a new equivalence or history-recovery
commitment. Default changes must earn comparative evidence, including names
unchanged and true-symmetry controls.

## Regional correspondence checkpoint

A new opt-in chain-of-regions kernel enumerates coarse fragment orderings and
uses interface distances for local optional assignments. On the known cut/body
case, including independent renaming and reversal, two complete 2,066-pair
hypotheses each preserve incidence except one endpoint, expose the width edit,
and retain both old-side placements of the edited B device. A fresh gate/cut
mutation behaves similarly. This is narrower, useful ambiguity rather than a
claim to recover unique history. The general dense partial-QAP experiment remains
a weaker reference: local optimization is sensitive to permutation and names.

## Regional graph and interface revision

The chain-only restriction is superseded in the opt-in regional mode. A bounded
beam searches a coarse graph over a size-selected hierarchy frontier, allowing
unmatched regions, branching and cycles. Oversized wrappers are opened; direct
primitives outside the frontier remain residual objects. Multiple complete
hypotheses survive local optional assignment and full terminal-incidence ranking.
This is a new heuristic informed by the earlier experiments, not an implementation
of a published graph-matching algorithm. The fixed default remains unchanged.

Observed: the prior 2,114→2,113-leaf two-cut/cross-link/type/body failure now yields
2,113-pair alternatives with two endpoint disagreements, compact two-sided edit
hints and one unmatched old object. Frozen binary-tree, cycle/spoke and unequal
repeated-tree controls also produce useful hints. The unequal case preserves all
old incidence under an alternative alignment with one added region; it does not
recover the generator's remove-one/add-two history. This reinforces the distinction
between observable incidence/edit coverage and unknowable historical identity.

Root's formal-pin permutation audit falsified the initial assumption that slot
order was sufficiently harmless context: changing only declaration order created
avoidable unmatched leaves and 16–23 endpoint discrepancies. The adopted revision
removes indices from coarse relations and enumerates boundary-net bijections for
interfaces of at most six distinct nets. Larger interfaces use order-independent
distance multisets. Local assignments retain tied incidence-consistent alternatives;
full-graph scoring checks their external context. All six permutations recover the
46-leaf reduced example and the independently renamed/wrapped 2,067-leaf example
without endpoint disagreement. The earlier frozen failure remains preserved.

## Physical pieces across changing hierarchy

The independent occurrence frontier is now one candidate decomposition, not the
only correspondence boundary. `regional_multifrontier_v4` also builds physical
pieces from multi-terminal cores joined through sparse nets, attaching passive
leaves only when ownership is unambiguous. Both revisions can therefore recover
the same useful pieces after arbitrary primitive allocations into new sibling
blocks or unions of old blocks. Every original leaf/path survives; search pieces
are neither inferred circuit functions nor replacements for authored hierarchy.
Final role-incidence/unmatched cost chooses among complete frontier hypotheses.

Unequal boundary-net counts now provide partial interface context rather than a
pairing veto. Small sets use partial injections; larger ones use invariant distance
distributions. Conditional many-to-many authored membership is reported alongside
the complete supporting leaf hypotheses, without asserting historical split or
merge events. Small passive-only regional fallback uses structure alone; the
separate partial-QAP reference retains its historical weak-name alternative.

Observed: actual interleaved splitting, reverse merging and arbitrary cross-bank
regrouping recover thousands of leaves at populated depth4–5. One-sided and
independently salted definition/instance/formal-pin/internal-net renaming preserve
measured incidence and changed-device hints on the controls. Tied tree hypothesis
sets do change under renaming: no universal traversal-invariance claim is made.
A repeated ring exposed missing valid rotations; bounded composition of verified
whole-view structural symmetries recovers all 45 in that case. This closes the
observed generators only, not every possible symmetry in arbitrary inputs.

Root also exposed reporting noise inside exact same-type terminal twins. Raw
fields now select a representative only within these already established twin
classes, minimizing avoidable displayed changes while keeping the full structural
ambiguity in inspection regions. Matched sets and terminal incidence stay fixed;
real value edits still appear. Attribute-free coarse matching remains, while
attribute-free representative presentation is explicitly superseded. Matching raw
values establish neither unique identity nor absence of hidden swaps.

Limits of the retained v4 frontier path: 64 pieces, 128 leaves/piece, 256 residual objects; coarse/local truncation;
weaker context for large interfaces; a core-based decomposition that may fail on
passive-only, densely coupled or oversized cores. Arbitrary input regrouping is
not generally solved. Physical split/merge has positive evidence within this
supported domain, not merely for empty wrappers. Body/supply and all primitive
roles remain in final validation even when search suppresses particular nets.
Prototype maturity is unchanged. The iteration4 report (local research checkout: `research-observatory/runs/20260916-comparison-context/iteration4/report.md`)
records preserved failures, before/after results, honest fallback and the next
boundary test; iteration3 (local research checkout: `research-observatory/runs/20260916-comparison-context/iteration3/report.md`)
remains the historical graph/interface checkpoint.

## Actual occurrence boundaries

The public definition-root comparison is now joined by `compare_instances` over
one full input and two actual call paths. This revises the API boundary, not the
graph matcher: selected expansion supplies existing comparison views directly.
Ancestors resolve attachments without expanding unrelated siblings. Original
paths, target definitions, defaults and call overrides remain inspectable;
expressions remain unevaluated. Same-path and nested selections are independent
views. Primitive selection is explicitly excluded from this slice.

Experience: merging caller-shorted ports before matching confounds external
attachments with internal structure. The selected internal view therefore retains
distinct formal ports, with a separate mapping to physical nets. Boundary aliases,
external equality and conditional functional correspondence are separate outputs.
Pins without supported internal incidence retain unresolved identity, including
unused pins. Raw added/missing declaration labels do not prove functional port
addition/removal. Pin evidence remains factored by retained leaf hypotheses and
preserves their incomplete symmetry/twin ambiguity. This is an inspection contract,
not electrical equivalence or an exhaustive boundary assignment solver.


## Budgeted incidence and certified repeated components

The 64-region frontier is no longer a universal admission boundary. A new path
cuts explicit global/high-degree nets, certifies repeated components using exact
typed role incidence with a fixed shared boundary, and searches the edited
remainder directly over partial net maps. Optional leaf assignment bounds the
net beam; feasible incumbents are ranked by full original incidence. Small
whole-view failures can use the same repair. The fixed default and selected
instance internal/physical boundary contract are unchanged.

Observed: the passive 24-leaf join/split improves from eight to two endpoint
disagreements with no raw distractions, including independent renaming and a
fresh mutation. Repeated 2,000/5,000/10,000-leaf controls reach one disagreement
with complete pairing. Exact whole-component permutation factors expose their
large, real structural ambiguity without enumerating every map. Certification
uses no raw values or names; unique WL labels order a certificate but never prove
it. These results support factorization of this sparse repeated domain, not a
general arbitrary hierarchy/decomposition claim. The initial salted net-beam
failure also shows that a finite beam still depends on its variable ordering.

The objective itself can hide heavily edited objects: the dense 48-leaf control
admits a 45-pair score of 4.6 versus a complete map's score of eight. A separately
labelled coverage tradeoff exposes the latter and its paths; it does not silently
change the primary omission cost or assert unique identity. New search work is
publicly bounded with incumbent/partial retention. Its counter is not a promise
about whole-call time or memory. Large inseparable components, ambiguous component
certificates/boundaries, and truncated net beams remain open. Prototype maturity
and the need for representative workplace evidence are unchanged.

## Available structure beside opaque libraries

Observed: one undefined X call made regional factorization discard 5,000 otherwise
certifiable primitive leaves and hit the old 64-region fallback cutoff. The revised
factor boundary skips opaque components, retains their known neighbours for bounded
remainder search, and keeps opaque leaves in coverage and final unmatched counts.
Opacity is local evidence of unavailable internals, not a global veto of available
structure. This changes factor admission, not canonical representation, fixed-mode
matching, primitive terminal semantics or the unknown-block selection rejection.
Certificates still cover only represented incidence; opaque objects cannot certify
whole-design equivalence. Non-opaque certificate and known-remainder limits remain.

Missing primitive model bodies already leave syntax-defined terminals usable with
raw model identifiers and generic types. Extraction diagnostics remain at their original input scope. Ambiguous undeclared
BJT terminal/model splits now arrive as canonical unresolved raw evidence, using
the existing opaque path; no assumed terminals enter incidence or certification.
This supersedes the initial audit's acceptance of warning-only guessed BJT roles.
Component factors explicitly qualify their scope as represented terminal incidence;
unrepresented positional attachments and hidden internals are outside that claim.
Unknown semantics, missing files and intentionally opaque libraries are distinct.
These controls establish useful partial inspection on public synthetic inputs,
not broad dialect compatibility or simulated electrical equivalence. Prototype
maturity is unchanged.

## Missing-cell boundaries as explicit comparison objects

User experience showed that preserving known circuitry beside opaque calls is
insufficient when most leaves come from unavailable libraries. Opt-in
`black_box_missing` adopts a boundary-only comparison of explicit canonical
black-box interfaces: original cell identity, named or positional terminals and
raw instance overrides. Extraction now owns token boundaries and marker metadata;
the earlier joined-net interpretation survives only for legacy canonical objects.
This comparison assumption is consumer policy, not inferred formal names. Same cell reference and compatible
interface are hard correspondence constraints under an explicit assumption of
unchanged internals and stable terminal identity. Incompatible interfaces and
one-sided definitions abstain; malformed primitives and budgets remain opaque.

Available terminal incidence and unavailable internals are separate dimensions.
Black-box leaves participate in matching and component certificates, with the
latter limited to represented boundary incidence. Original diagnostics, hidden
internal scope, and positional provenance remain inspectable. Net renaming cannot
become a synthetic override change. Selected known blocks can contain such leaves;
direct selection of unavailable internals remains excluded. Existing repeated-class
and heuristic search limitations remain. Prototype maturity is unchanged.

## CLI discovery and presentation

User experience exposed a boundary gap: requiring code/docs to discover circuit
names, actual call paths and output semantics made the headless entry point hard
to use independently. The CLI now owns a built-in guide, bounded read-only
inspection, explicit recovery hints and readable terminal previews. This is
presentation of existing evidence, not inferred functional prose or a new matcher.
Populated file-level roots and sole definitions can be selected automatically;
ambiguous library scope requires a choice. Piped output stays JSON and callers can
force a format; saved output always retains full evidence. Diagnostics, opacity,
search limits and ambiguity remain visible in previews. Defaults/overrides and
coupled hierarchy/pin details still require the full report. The fixed default,
API contract and prototype maturity are unchanged.

## Saved-result inspection

Saved full reports now support a pure projection boundary and a `view` CLI.
This adopts the earlier inspection hypothesis without extending the matcher:
the view selects represented raw leaf fields, net-partition rows and unpaired
object dispositions by exact A/B subtree, optionally groups representative
pairs by occurrence depth, and keeps the source report immutable. Source
identity/hash, before/after record counts, scope, diagnostics, unresolved and
opaque evidence, black-box assumptions, and coupled pair/group/factor context
remain visible. The derived artifact has a distinct kind and cannot be read
as another full comparison. This boundary makes focused review useful while
preserving the evidence that a representative is tentative.

Experience from root review refined that boundary: endpoint tokens carry a
pair ID and a role that may contain colons; resolving from the first separator
preserves named-bus evidence. Group depth is relative to each selected root and
uses the closest available ancestor for shallow branches. Grouped text now
collapses leaf detail but JSON retains it, including full endpoint context.
Every projection records a canonical report-content hash even without saved
bytes; an exact artifact hash is separate. Returned data is detached from the
source report so later view edits cannot rewrite evidence in memory.

The report still lacks independent wiring-event identity and evaluated
parameter values. Definition defaults and call overrides remain as unfiltered
hierarchy context rather than counted as leaf raw findings. A view cannot
recover unexplored alternatives or establish equivalence from an empty
selection. This is an inspection capability in the existing prototype, not a
maturity change or a new claim about matching accuracy.

## Canonical file consumption

User experience exposed that a direct Python dependency was insufficient for a
reusable extraction workflow. `--format canonical` now delegates custom-table
loading to the owning canonical reader. Extraction configuration is not duplicated
here; saved diagnostics when present, defaults and explicit external interfaces enter the same
comparison API used by SPICE inputs. The canonical reader checks artifact structure;
comparison still decides what to assume about unavailable internals. This changes
the input boundary, not regional admission limits or prototype maturity.

## Whole-component representative experience

The external-cell trials exposed a distinction between structural ambiguity and
avoidable presentation noise: a certified permutation can explain one width edit
with 31 raw-change rows. The opt-in `component_presentation="minimum_raw"`
experiment extends raw-aware representative choice from terminal twins to whole
certified components. It uses bounded coordinate assignments, preserves matched
sets/incidence and every structural factor, and leaves the default unchanged.
Raw values choose a readable representative without establishing identities.

Population imbalances in paired component slots are separate raw facts conditional
on partner sets. A concise wiring witness is likewise conditional on one leaf/net
map; net-map ties can relocate it. This separation helps an operator use both
schematic paths without converting a selected permutation into an established edit.
Observed: 31 raw rows become one on the known 240-leaf external-cell edit, and
2,447 become one on a 5,000-leaf repeated resource stress, retaining the single
endpoint discrepancy. These are synthetic results. Public TIA self-comparison
still produces four noisy raw rows; rename sensitivity, connected admission and
broad structural ambiguity remain. This revises presentation inside certified
symmetries, not correspondence admission or prototype maturity. A general useful
analog-difference result remains unestablished.

## Architecture-first inspection and input namespaces

User experience adds a practical distinction: a redesign or reorganization may
need inspection before sizing details matter. The saved-view `omit_parameters`
option suppresses ordinary parameter differences while retaining raw type and
canonical reference fields, connectivity, conditional hierarchy membership and
unavailable scope. Parameter-list storage is not itself evidence that a field is
sizing: model/type and connectivity references remain. Defaults and call overrides
remain explicit unfiltered context, outside displayed leaf findings. Grouped text
retains membership even without leaf differences, and saved endpoint witnesses
can be viewed without parameter rows. No functional taxonomy or event inference
is adopted; this changes projection, not correspondence.

Observed: the public hierarchy-only case exposes 26 leaves remaining under xi20
and 10 paired into xi20/XRC. The renamed combined case still selects a 21-endpoint
alignment where an authored alignment has one discrepancy. Filtering its six
parameter rows leaves the 39 partition rows and 21 conditional witnesses intact;
this is an unresolved matching failure, not successful architecture localization.

Root integration review also showed that a synthetic file root was wrongly
counted as an available missing-cell implementation. Only declared subcircuits
now serve call lookup and availability checks. A file-root/subcircuit name
collision is valid canonical input but exceeds the current name-keyed report
catalog: comparison explicitly requires the caller to rename the file root,
without changing subcircuit identities or silently selecting a scope. General
namespace-qualified catalogs remain a possible later boundary revision. Prototype
maturity and the certified-only raw-minimization boundary are unchanged.

## Challenging selected omissions

Experience exposed a boundary error in unused-only regional completion: an omitted
leaf can have plausible counterparts that are all occupied. The adopted opt-in
`omission_work_limit` search reopens those assignments across hierarchy using an
omission-seeded beam. Full role incidence judges complete injective maps, including
worse intermediate steps; external identities/interfaces remain hard constraints.
Improving maps replace worse primary proposals. Best-score alternatives prioritize
different omission identities, while superseded baseline ties and forced-participation
witnesses remain separately labelled diagnostic evidence. Canonical extraction and
its cross-unit interface are unchanged; prototype maturity remains unchanged.

Population evidence is now a separate regional reporting commitment. Materialized
counts in hard-compatible domains can establish a joint surplus even when every
member has a possible counterpart. Opaque scope and incomplete expansion qualify
these counts. Search failure or an individual omission never becomes a historical
addition claim. Saved views preserve and explicitly label whole-scope population
and exchange context separately from filtered per-object dispositions.

Observed in the bounded public controls: redesign improves three endpoint
discrepancies to one with 285 pairs; combined remains at two. The equal-score
baseline omission exchange remains inspectable, but does not establish optimality.
The unchanged connected129 admission failure remains zero matched under regional
mode and has no population surplus. This supports reopening occupied competition,
not general correspondence accuracy. Fixed depth/beam, score/output budgets,
order sensitivity, missing full-coverage swaps and opaque scope remain explicit.
Conditional participation margins describe evaluated hypotheses, never probabilities.

## Paired discrepancy experiment

The regional prototype now separately tests occupied-counterpart swaps, explicitly
revising the search move boundary that required an omitted seed. A bounded beam
can use a worse intermediate map to improve fully paired compatible classes.
Matched sets remain fixed within each swap sequence; incoming seeds and conditional
alternatives remain distinct. Full represented incidence is the final objective;
external compatibility, injectivity and absence of name/raw-parameter search rank
remain commitments. Existing representative presentation is a separate operation.

The renamed public case improves from ten to six discrepancies after omission
search, while a known feasible two remains missed even at four times the swap
budget. A controlled strict local minimum resolves through an uphill step. This
supports the usefulness of the new move without establishing adequate basin
exploration or representative analog accuracy. Root review also exposed quadratic
proposal storage despite a small score budget; streaming bounded selection removes
that storage while preserving ordering, without imposing a new hard admission
limit. Score budgets still do not bound total runtime or memory. Prototype maturity
is unchanged. A next possibility is a small coupled structural proposal that can
cross the remaining basin more effectively than leaf transpositions alone.

## Supplied-region experimental contract

An opt-in `operator_scoped` mode now separates the operator's knowledge of a
region relationship from the comparator's evidence inside it. This revises the
assumption that useful local inspection must wait for automatic global discovery.
Supplied paths/top selections and unions are input knowledge, never recovered
correspondence. Existing modes remain unchanged.

The primary local model cannot see occurrence names, hierarchy paths or net
spellings. It uses explicit whitelisted literal cell/interface semantics and
original incidence, with case-consistent roles and collision rejection. A bounded
exact binary leaf/net model, attaining-bound certificates and a cold anonymous
ordering portfolio require weighted and K/K-1 optimality before necessary
terminal evidence. SciPy/HiGHS carries the same objective with existing package
dependencies; its target performance remains unmeasured. Alternative explanations
remain unresolved. Local witnesses never become global representative pairs.

Complete selected-member/scope/support charges bound conditional architecture,
parameter and separate exterior cards. Sampled Linux worker time/RSS watchdogs
make exhaustion observable; absence of cards is not a proof of unchanged design.
The current exterior scalar only detects crossing-net count changes. Unknown
label semantics, hidden internals, ambiguous exact explanations, budget overflow,
final output I/O and fork-based embedding limits remain explicit. Source catalogs
and saved views retain the paid context.

Observed package controls exercise exact/quiet/changed cases, alternative optima,
normalization, anonymous order fallback, corrupted evidence, exterior witnesses,
composed scopes and CLI/view behavior. This supports a runnable experimental
vertical slice, not private accuracy or maturity advancement. The next
architectural question is whether a knowledgeable operator can choose affordable
real canonical regions and receive useful conditional evidence with these limits.

Review exposed four boundaries that are now explicit in this local contract:
canonical root identity governs union deduplication; unequal represented
interfaces supply inventory residuals without suppressing unrelated content;
structural metadata filtering never drops explicit black-box instance overrides;
and saved cards are reconstructed from incidence/proofs rather than trusted as
independent assertions. Certification, lanes, focus, meaning and full charges
must agree with that reconstruction. These are consistency guarantees, not
authentication of an arbitrarily rewritten source report.

## Local automatic hierarchy trial

The repository carries an optional example workflow that deterministically
enumerates every affordable relative hierarchy path shared by two selected roots.
This revises the earlier Luna-first handoff: stable hierarchy requires no agent
ranking. Relative path equality remains supplied scope knowledge, never verified
identity. Every window retains its independent anonymous graph, proof, report and
abstentions while one explicit batch reuses immutable input preparation.

A local Luna agent is reserved for unmatched frontier branches where rename,
move, split or merge may have broken relative path equality. Its compact handoff
is a reading-cost aid, not a privacy boundary; the authorized local agent may
inspect complete sensitive inputs. Validation rejects shared paths and quiet
controls, binds proposals to the handoff hash, and checks exact leaf charges,
non-overlapping unions and general 1:1/1:n/n:1 structure. An agent proposal remains
a heuristic supplied scope and never becomes correspondence evidence.

The trial refuses more than its explicit total-window bound rather than ranking
or truncating. Canonical input hashes, atomic non-overwriting output, complete
per-window reports and an honest resource-stop receipt make one private run
inspectable. The workflow opts into the exercised 64-leaf/96-net/16-counterpart/
200-retained/100-presentation values without changing package defaults. Public
tests cover both input shapes, explicit complete global-net scope, optional
parameter omission, zero-proposal agent abstention, deterministic and unmatched
selection, mutation and overwrite guards, a real mixed batch, and resource
exhaustion without inferred quiet results. Compact summaries retain supplied
paths for local navigation. Private usefulness and naming stability remain
unmeasured; prototype maturity is unchanged.

The first public usability run exposed that a technically valid handoff can fail
at its human-agent seam: Luna searched for a top-level frontier array and the
generated commands relied on an inherited development `PYTHONPATH`. The task now
names all four side-qualified arrays, reports and requires confirmation of their
counts before abstention, and emits commands bound only to the two discovered
local package roots. Tests execute those commands with the ambient Python path
removed.

The workplace trial exposed a second seam: complete JSON and a flat window
summary can be hard for an engineer to read even when local cards exist. The
optional local agent task now asks for a schematic-facing assessment of supported
inventory, pin/interface and connectivity evidence, with candidate additions,
removals and hierarchy relations kept explicitly tentative. This is a human
interpretation layer over saved reports, not a new comparator proof or a claim
that generated prose is authoritative. The unresolved question is whether that
assessment actually helps the operator find and understand private changes.

## Experimental budget separation

The opt-in operator-scoped prototype now distinguishes solver leaf/net/counterpart
admission, retained evidence support and charged presentation. Old defaults remain
unchanged. A larger analyzed window may have a certified proof and no affordable
card; those outcomes are reported separately. Complete candidate classes and nets
remain intact, and all admission failures are visible. Raw catalogs/exterior
incidence remain audit context, with separate byte/resource limits.

This challenges the earlier coupling in which a presentation ceiling prevented
backend analysis. It does not establish that larger regions yield useful operator
locations: overlap grouping, complete support charging and private correspondence
remain separate questions. Phase/model/RSS diagnostics make that hypothesis
inspectable. Exact objectives, proof prerequisites and unresolved identity remain
unchanged; new capacity is not a new correspondence claim.

## Explicit sequential batch preparation

Repeated supplied-window scans exposed a boundary mismatch: immutable full-input
identity and full-top exterior incidence were being reconstructed for every
window even though their inputs, tops, scope and options were fixed. An explicit
batch API now owns that reuse inside one bounded worker. It has no process-global
state. Each window still constructs a fresh selected view, anonymous graph,
admission record, evidence lanes and exact proof, and yields an ordinary saved
report. The batch key includes canonical content identities, tops, scopes and all
options, so a changed basis starts new preparation rather than inheriting stale
incidence. This tests whether deterministic hierarchy scans can pay immutable
preparation once without weakening the local proof contract; representative
workplace performance remains an evidence question.
