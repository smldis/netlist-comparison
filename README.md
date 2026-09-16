# Netlist Comparison

A Python prototype that proposes counterparts between canonical analog netlists
and reports raw differences **conditional on those pairings**. It preserves
hierarchy locations, shared definitions, alternatives and unresolved regions.
Output is structured JSON; names are labels, not inferred circuit functions.

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
git -C spice-canonical checkout dcf9dfb4e85f4d87fac5fa8e9f410c20759188ed
git clone https://github.com/smldis/netlist-comparison.git
cd netlist-comparison
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ../spice-canonical -e . pytest
python -m pytest -q tests
netlist-compare examples/before.sp examples/after.sp --top-a TOP --top-b TOP \
  --output comparison.json
```

The pinned canonical revision adds the reviewed ambiguous-BJT correction; its PR
is separate from this package. Older canonical revisions can supply guessed BJT
terminals and will fail those regression tests. NumPy and SciPy are declared
runtime dependencies. No simulator or private netlist is required for the tests.
The full ASS validation passed 196 canonical, comparator and integration tests.

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
[iteration4 evidence](../research-observatory/runs/20260916-comparison-context/iteration4/report.md).

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

[Budgeted iteration evidence](../research-observatory/runs/20260916-budgeted-comparison/implementation/report.md)
records timings, resource guards, failed development controls and remaining limits.

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
