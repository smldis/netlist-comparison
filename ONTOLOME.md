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
Prototype maturity is unchanged. The [iteration4 report](../research-observatory/runs/20260916-comparison-context/iteration4/report.md)
records preserved failures, before/after results, honest fallback and the next
boundary test; [iteration3](../research-observatory/runs/20260916-comparison-context/iteration3/report.md)
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
