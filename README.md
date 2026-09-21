# Netlist Comparison

Missing library cells can be compared explicitly as black boxes:

```bash
netlist-compare before.sp after.sp --black-box-missing --matching-mode regional --output result.json
```

This assumes unchanged hidden implementations, stable cell references and stable
terminal order. It compares connections and raw instance overrides without the
library definitions. Positional terminals are labelled `@1`, `@2`, etc.; these
are positions, not inferred pin names. Mismatched interfaces stay unresolved.
Internals remain unavailable and original extraction diagnostics remain visible.
The default still leaves undefined calls opaque. See the guide for scope/limits.

A Python prototype that proposes counterparts between canonical analog netlists
and reports raw differences **conditional on those pairings**. It preserves
hierarchy locations, shared definitions, alternatives and unresolved regions.
Output is structured JSON; names are labels, not inferred circuit functions.

## Start without reading a manual

Run `netlist-compare` for a quick-start guide, `netlist-compare --guide` for the
operator mini-guide, or `netlist-compare --help` for organized options and
parser-derived defaults. `netlist-compare view RESULT --help` documents the
saved-report filters. CLI help is maintained with behavior: each exposed option
or matching choice needs its purpose, default/choices, incompatibilities and
limits in help plus an entry-point check; this README explains the deeper contract
instead of duplicating a hand-maintained option list.

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

### Inspect a saved result

```bash
netlist-compare view result.json --under-a TOP/XOLD --category raw --text
netlist-compare view result.json --under-b TOP/XMOVED --category wiring --output focused.view.json
netlist-compare view result.json --omit-parameters --group-depth 2 --text
netlist-compare view result.json --parameter W --group-depth 1 --json
```

`view` reads complete saved comparison JSON (`.json` or `.json.gz`) without
loading netlists or matching. Terminal output is a bounded text preview;
redirected output or `--json` emits complete derived JSON. `--text` forces a
preview. `--output` saves derived JSON and cannot name or alias the source.
`--limit` affects text only. Invalid reports, paths and filters exit 2.

Repeat `--under-a PATH` and `--under-b PATH` for exact, case-insensitive
subtrees using percent-escaped catalog paths. A pair is selected if either
side lies under a requested path; moved counterparts remain visible. Repeat
`--category raw|wiring|unpaired` to select findings (default: all). `raw`
covers representative leaf-pair raw fields. `--parameter NAME` selects only
`parameters.NAME` and requires `raw`; it does not mean all parameter changes.
Definition defaults and call overrides remain unfiltered in `context.hierarchy`.
Expressions are not evaluated.

For an architecture-first inspection, `--omit-parameters` hides parameter-only
leaf findings while retaining type changes and exact canonical model/type and
connectivity-reference fields. It is mutually exclusive with `--parameter`.
Python: `project_saved_report(report, omit_parameters=True, group_depth=2)`.
With the default categories, wiring, conditional endpoint witnesses (when saved),
unpaired objects and source limitations remain visible. Hidden counts are explicit;
all original parameter/default/override values remain in the full JSON context.
This filter does not improve matching or identify redesign/split/merge events.

`--group-depth N` collapses text to finding counts by occurrence at depth N
relative to each selected comparison root, including selected-instance roots.
A shallow branch uses its closest available ancestor. JSON still retains all
selected leaf rows. Group counts show scoped representative pairs, shown raw
changed pairs, shown unpaired objects per side, and shown wiring partition rows
touching that group. A wiring row can touch several groups, so those counts do
not sum to independent wiring edits. With `--omit-parameters`, text also shows
conditional membership groups without leaf findings, preserving hierarchy-only
inspection routes. Otherwise text omits groups with no selected findings;
JSON retains those groups as context. Category total/shown/
hidden counts refer to raw edited pairs, wiring partition rows, and unpaired/
unresolved/opaque object rows. These are different record kinds, not independent
design edits. A selected wiring row retains every endpoint token, including
ones across the selected scope. Raw net labels alone are not wiring evidence.

Derived JSON has a distinct `kind`, a reproducible report-content SHA-256,
source artifact SHA-256 when saved bytes are available, and input identity,
filters, counts, findings, hierarchy groups, source scope, and full coupling
context. Pair options, groups, alternatives, component factors, hierarchy,
boundary pins, diagnostics, unresolved regions, coverage, opacity and black-box
assumptions remain where present. It can be large because ambiguity cannot be
trimmed into apparent certainty. It cannot replace a full comparison report.
Empty findings mean only none selected. Unpaired or opaque objects are not
proven additions or deletions; filtering cannot recover unexplored candidates.
Text wiring rows show A/B instance paths and terminal roles for bounded
endpoint previews, including roles containing colons.

## Extract once with SPICE Canonical

Pin mapping and library boundaries belong to the extractor:

```bash
spice-canonical before.sp --external-subcircuits pins.json --output before.canonical
spice-canonical after.sp --external-subcircuits pins.json --output after.canonical
netlist-compare before.canonical after.canonical --format canonical --black-box-missing --matching-mode regional --output result.json
```

`pins.json` maps actual cell names to pin names in call order, for example
`{"nmos_lvt": ["d", "g", "s", "b"], "res_cell": ["p", "n"]}`.
Without a mapping, canonical preserves positional terminals. Both artifacts use
SPICE Canonical's custom table syntax, not JSON. The comparator delegates loading
to `spice_canonical.canonical_netlist.from_canonical_file`; original SPICE files
and libraries need not be available. `--inspect` and two-instance comparison also
accept `--format canonical`. Extraction warnings, defaults, overrides and explicit
black-box interfaces survive. This requires the canonical-text reader revision of
`spice-canonical`; the earlier pinned BJT-only revision does not provide it.
The matching algorithms and their regional admission limits are unchanged.

## Development history

Public repository: [smldis/netlist-comparison](https://github.com/smldis/netlist-comparison).

This package has an independent Git repository. The initial `main` baseline
records the reviewed prototype on 2026-09-16, including budgeted regional matching,
instance/pin comparison and incomplete-library handling. Subsequent experiments
use topic branches and focused, tested commits. Research reports remain in the
sibling observatory; `spice-canonical` retains its own history. It is composed into
ASS as a Git submodule. Some research links require the surrounding ASS workspace;
the package source, tests, examples and usage documentation are included here.

## Run from ASS

```bash
uv sync --group dev
.venv/bin/netlist-compare \
  netlist-comparison/examples/before.sp \
  netlist-comparison/examples/after.sp \
  --top-a TOP --top-b TOP \
  --output /tmp/netlist-comparison.json
```

## Standalone checkout

Use sibling checkouts to reproduce the reviewed dependency state:

```bash
git clone https://github.com/smldis/spice-canonical.git
git -C spice-canonical checkout 7452879264d4b1b5d86b5a12734a4b7fa413e02c
git clone https://github.com/smldis/netlist-comparison.git
cd netlist-comparison
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ../spice-canonical -e . pytest
python -m pytest -q tests
netlist-compare examples/before.sp examples/after.sp --top-a TOP --top-b TOP \
  --output comparison.json
```

Replace the checkout placeholder with the commit that publishes the canonical-text
reader and explicit black-box boundaries before using these instructions. The
earlier [canonical PR #2](https://github.com/smldis/spice-canonical/pull/2)
introduced the ambiguous-BJT correction, but does not include this reader. Both
repositories currently declare prototype version `0.1.0`, so a version-only
dependency constraint does not identify the compatible revision. NumPy and SciPy
are declared runtime dependencies. No simulator or private netlist is required
for the tests. Root review of the composed ASS source passed 342 tests; this is
not workplace validation.

License: [Apache-2.0](LICENSE), matching the other ASS components.

## Python API

```python
from spice_canonical.canonical_netlist import from_file
from netlist_comparison import compare, InputScope

report = compare(
    from_file("before.sp"), from_file("after.sp"),
    top_a="TOP", top_b="TOP",
    scope_a=InputScope(global_nets=("0", "VDD")),
    scope_b=InputScope(global_nets=("0", "VDD")),
)
# Each pair's raw_differences is true only under that candidate pairing.
for pair in report["pair_options"]:
    if pair["raw_differences"]:
        print(pair["a"], pair["b"], pair["raw_differences"])
```

## What exists, and what remains uncertain

- Fixed structural features, global tiled search, compact repeated classes,
  restricted optional assignment, and bounded alternative checks.
- Conditional raw parameter/type/terminal comparisons, net overlap tables,
  occurrence membership, defaults and call overrides.
- Explicit expansion/search/assignment limits and per-object coverage.
- Runnable rename/move/edit example and reproducible synthetic scale evaluation.

The 2,067-leaf synthetic depth-4→5 example screens quickly, but leaves most
repeated devices unresolved. Its edited device has a unique new-value profile;
the possible old counterpart region remains broad. The public 376-leaf example
also leaves substantial ambiguity. **This is an executable baseline, not an
established solution for complex analog revisions.** No electrical equivalence,
impact, historical move event or unique identity is claimed.

Two opt-in experiments now exist: `--context-mode frozen_neighbors` and
`--matching-mode anchor_growth`. Growth locates the edited leaf on the known
2,067-device fixture, but a held-out bridge removal produces
110 historical disagreements; these are not proof of structural error or unique
edit history. **Neither replaces the v1 default.**
The comparison includes a names-unchanged TIA control where path/name matching
remains strongest; see the second experiment in the evaluation below.

[Usage, result contract and limits](docs/index.md) ·
[Measured evaluation and next experiment](docs/evaluation.md) ·
[Ontology](ONTOLOME.md)

## Regional graph and split/merge experiment

`--matching-mode regional` / `Options(matching_mode="regional")` compares authored
hierarchy and connectivity-derived pieces. It supports useful correspondence
across actual primitive splitting/merging, retaining original paths, coupled
alternatives and conditional many-to-many membership. Full terminal incidence
ranks the candidates. The fixed-feature matcher remains the default.

One-sided and independently salted block/pin/net rename controls preserve useful
hints; tied search alternatives can still depend on traversal order. Exact terminal
twins retain ambiguity while raw fields choose a less distracting representative.
This does not establish unique history or electrical equivalence.

Positive evidence includes thousands of leaves at depth4–5, branches/cycles,
unequal interfaces, arbitrary allocations across new sibling blocks and merged
blocks. Passive-only, dense and oversized components remain limitations. See
[the result contract](docs/index.md#regional-graph-checkpoint) and
iteration4 evidence (local research checkout: `research-observatory/runs/20260916-comparison-context/iteration4/report.md`).

## Budgeted incidence and repeated components

Regional mode now repairs small candidates by searching partial net maps with
optional leaf assignments. Large views can factor repeated components after
cutting global/dense nets and certifying **all** typed terminal incidence with
those boundary nets fixed. Original paths and body/supply checks remain intact.
The previous frontier search remains the fallback; fixed matching is unchanged.

The measured passive join/split improves from 8 to 2 endpoint disagreements;
2,000/5,000/10,000-leaf repeated-cell controls produce complete maps with one
endpoint disagreement. Independent renames and a fresh mutation retain this
quality. Repeated-cell hints deliberately span 200/500/1,000 interchangeable
cells; a selected representative is not unique identity.

`Options(matching_mode="regional", regional_work_limit=50_000)` and
`--regional-work-limit` bound new net-map candidate assignments/component
certificates. Exhaustion preserves feasible incumbent/partial evidence. This is
**not** a whole-comparison time or RAM limit: legacy search, expansion, reporting
and native calls are outside this counter. Use external process limits for those.
`partial_alignment.coverage_tradeoffs` separately exposes supported completions
that the normal omission cost disfavors; they are not primary hypotheses.

Budgeted iteration evidence (local research checkout: `research-observatory/runs/20260916-budgeted-comparison/implementation/report.md`)
records timings, resource guards, failed development controls and remaining limits.

## Reduce certified permutation noise

To reduce raw-change noise from arbitrary **certified whole-component**
permutations, try the opt-in regional presentation experiment:

```bash
netlist-compare before.canonical after.canonical --format canonical \
  --black-box-missing --matching-mode regional \
  --component-presentation minimum_raw --output result.json
```

`Options(matching_mode="regional", component_presentation="minimum_raw")` uses
raw type/parameter lists to reduce changed leaf rows within existing structural
factors. It preserves all factors, matched sets and terminal incidence. This is
a less noisy representative, not a unique counterpart or an edit-history claim.
The full report retains raw-profile population imbalances and a conditional
endpoint inspection witness with paths on both sides. Two bounded factor sweeps
do not guarantee a joint optimum. Default behavior stays unchanged.

On the known 240-leaf external-cell edit, raw-change rows fall from 31 to 1
while the one endpoint discrepancy remains; structural old-side ambiguity still
spans 20 leaves. The public TIA self-comparison still has four noisy raw rows,
and the connected 144-leaf admission failure still has no pairs. See
[the experiment contract](docs/index.md#certified-component-presentation) and
bounded evaluation (local research checkout: `research-observatory/runs/20260916-practical-comparison/implementation/report.md`).

## Compare two actual block calls

```python
from netlist_comparison import compare_instances, Options, InputScope
report = compare_instances(
    from_file("full.sp"), top="TOP", path_a="TOP/X1", path_b="TOP/X2",
    options=Options(), scope=InputScope(global_nets=("0", "VDD")),
)
```

```bash
.venv/bin/netlist-compare full.sp --top TOP --path-a TOP/X1 --path-b TOP/X2 \
  --global-net VDD --output /tmp/instances.json
```

Paths include the top and actual calls. Lookup is case insensitive; output retains
original spelling. Percent-escape each segment (`X/a%` → `X%2Fa%25`); malformed,
missing, ambiguous, recursive or invalid ancestor calls raise `ValueError` (CLI
exit 2). Primitive selections are explicitly unsupported. Same-path and overlapping
selections work independently, without asserting identity.

Only ancestors and the selected subtrees are expanded. `max_objects` applies per
selected subtree; `max_depth` is relative to its root. The full input is still
validated and hashed. Opaque descendants and exhausted budgets remain visible.

`a.selection` / `b.selection` retain physical paths, target definition, ancestor
bindings, raw overrides and defaults. Object `resolved_nets` and occurrence
`bindings` are physical; `internal_nets` / `internal_bindings` retain distinct
formal ports for matching. Pair terminal `net_a/b` and `connectivity` describe
that internal view; `physical_net_a/b` give actual attachments. External shorts
therefore do not become internal rewiring claims.

`boundary` contains all formal pins, raw/resolved parent bindings, globals,
unused/unknown-use status, aliases, raw missing/added declaration labels and
outer-net equality groups. Conditional pin candidates reference the retained
leaf hypotheses and endpoint evidence. A label change is not a proven port
addition/removal. Unsupported and unused pins stay unresolved. Alternatives within
a group are coupled; fixed-mode groups are independent factors, not an enumerated
joint pin bijection. Incidence conflicts are reported within each factor; combining
factors requires checking their shared pin constraints. Symmetry/twin inspection
regions remain attached; no exhaustive pin mapping or numeric parameter equivalence
is claimed. Default matching remains `fixed`; `regional` is opt-in.

## Challenge selected omissions

```bash
netlist-compare before.canonical after.canonical --format canonical \
  --black-box-missing --matching-mode regional --omission-work-limit 512 \
  --output result.json
netlist-compare view result.json --category unpaired --text
```

Python: `Options(matching_mode="regional", omission_work_limit=512)`. Zero
(the default) disables this additional search. An omitted supported leaf can
claim a compatible **occupied** counterpart across hierarchy, releasing its old
partner for another exchange. A width-12 beam takes at most three steps, ranks
complete injective maps by full terminal incidence plus 0.6 per omitted leaf,
and can traverse worse intermediate states. It adopts improvements and retains
up to 32 best-score alternatives, preferring different omission identities.
Cell identity/interface constraints remain hard; names and raw values do not rank
search. Existing certified/twin presentation may subsequently choose a raw-aware
representative without changing incidence or omitted sets.

`partial_alignment.omission_search` records termination, scored work, pruning,
conditional participation-versus-omission margins and coupled path exchanges.
`baseline_pairs` plus each witness's removed/added pairs reconstruct its complete
map. Baseline-score ties and best sampled participation witnesses are diagnostic;
they may be worse than a newly improved primary hypothesis. They are not silently
promoted into primary alternatives. Margins concern sampled maps only.

The budget counts full-map scores, including admitted seeds. Runtime scales with
represented incidence and candidate competition; memory can scale with budget
times paired inventory. It does **not** cap whole-call runtime/RAM. No populated
incumbent, no supported omission, or more than 64 supported omissions causes
explicit abstention. Depth, beam, seed/output truncation and iteration order limit
coverage. Full-coverage permutations and deletion moves are outside this search;
no global optimum, exhaustive search or calibrated probability is claimed.

Regional reports also include `population_evidence` without enabling search:
counts in hard-compatible represented domains, joint surplus and selected omission
counts. Native primitives share one domain (native type changes remain allowed);
external domains require the same cell/interface. Opaque objects are excluded
and counted separately. Incomplete expansion limits counts to materialized scope.
An unchanged unmatched 129-leaf graph has no population surplus. Two identical
external occurrences versus three have surplus one even when every occurrence
has a possible counterpart. Neither identifies an exact historical new instance.

Saved `--category unpaired` views show population groups and exchange evidence
**for the whole comparison scope**, explicitly unfiltered even with subtree
selectors. Per-object unpaired counts keep their existing meaning; population
counts are separate and survive when every per-object disposition is ambiguous.
Other category selections retain this evidence in unfiltered JSON context.

## Refine already paired counterparts

Use `--matching-mode regional --swap-work-limit 512` to try bounded swaps among
already paired objects, including fully paired compatible classes. It runs after
optional omission search. Python: `Options(matching_mode="regional",
swap_work_limit=512)`. Zero disables it; default matching remains unchanged.

Full represented terminal incidence ranks complete maps. Swaps preserve each
incoming seed's matched objects; external cell/interface compatibility remains
hard. Different seeds can already omit different objects. The score budget is
not a time/RAM cap. Branch/beam/depth limits and traversal order can miss better
maps: the renamed public control improves from 10 to 6 discrepancies after
omission search, while a feasible 2 remains missed. See `--guide` for choosing
between omission search, swaps, certified presentation and saved-view filtering.

JSON retains `partial_alignment.swap_search` and reconstructible witnesses.
`view --category wiring --text` shows swap evidence for the whole comparison scope
even with subtree filters; leaf/wiring selections remain separately scoped.
Names and raw values do not rank swap search; existing certified presentation
may subsequently choose an incidence-preserving representative.

## Experimental operator-supplied comparison windows

When you already know which blocks correspond, opt into `operator_scoped` to
inspect their represented content and connectivity. This is a local inspection
contract: your paths supply the correspondence, and never count as discovered
identity. Existing matching defaults are unchanged.

```sh
netlist-compare full.canonical --format canonical --top TOP \
  --path-a TOP/XOLD --path-b TOP/XNEW \
  --black-box-missing --matching-mode operator_scoped \
  --operator-seconds 180 --operator-memory-mib 3072 --output local.json --text

netlist-compare before.canonical after.canonical --format canonical \
  --top-a TOP --top-b TOP --path-a TOP/XOLD --path-b TOP/XNEW \
  --black-box-missing --matching-mode operator_scoped --output local.json --text

netlist-compare view local.json --category local --omit-parameters --text
```

For two files, omit paths to compare their entire selected tops. Repeat per-side
`--path-a`/`--path-b` flags to explicitly compose split/merged regions. All
selected leaves and scope addresses count against the budget; filtering a saved
card does not discard its opposite-side context or support charges.

Cards show conditional architecture, literal parameter populations and separate
exterior context. They do not claim unique identity, recovered edits, unchanged
circuit behavior or electrical equivalence. The primary matcher cannot see leaf
names, hierarchy paths or net spellings. Cell labels, named terminal roles and
positional `@N` roles retain their different literal meanings. Unknown cell-label
semantics cannot distinguish replacement from relabeling. Unequal black-box
interface widths remain literal inventory evidence with no cross-width pairing;
unrelated supported content can still be analyzed. Case-folding terminal-role collisions are rejected. Explicit black-box instance
overrides are retained, including names such as `model`, `source_type` and `raw`.
`--omit-parameters` hides the parameter-detail lane, retaining its facts in JSON.

The admitted region has at most 64 leaves and 64 nets per side, 16 compatible
counterparts per endpoint, 12 cards and 100 distinct side-qualified member,
scope and support paths. Oversized/opaque/incomplete regions are visibly
uncertified. Local terminal evidence requires certified weighted, maximum-
coverage `K` and `K-1` results. Literal inventory facts may still be available
when correspondence cannot be certified. Local hypotheses stay in
`operator_scoped.windows`; global `representative_pair_ids` remain empty.

Execution currently requires Linux/POSIX fork and `/proc`. The configurable
worker deadline defaults to 60 seconds, RSS watchdog to 3072 MiB, and individual
solver attempts to at most 10 seconds. The parent samples worker RSS every
20 ms and kills an over-budget worker: this is a sampled watchdog, not an
allocation-time memory ceiling. CLI input loading and worker result encoding
are inside the deadline; final stdout/disk serialization and writes are outside.
For the Python API, caller-side canonical parsing is also outside the deadline.
Timeout yields an incomplete report, never certified quiet. The worker uses one
CPU; the solver receives one thread. Multithreaded embedding of the fork-based
API has not been validated.

See [the detailed local contract](docs/index.md#operator-supplied-local-windows)
for the objective, certificates, API, output limits and remaining gaps.
