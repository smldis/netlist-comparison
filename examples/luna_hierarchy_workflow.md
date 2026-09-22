# Local automatic hierarchy trial

This optional workflow combines two bounded sources of `operator_scoped`
comparison windows:

1. every shared relative hierarchy path within the leaf cap, enumerated without
   ranking or agent judgment;
2. optional rename, move, split, and merge relations proposed by a local Luna
   medium agent from unmatched hierarchy frontiers.

Both are supplied comparison scopes. Relative path equality and Luna proposals
do not establish correspondence, edit history, unchanged behavior, or electrical
equivalence. Each complete result retains the ordinary anonymous graph, admission
record, exact proof, evidence lanes, support charges, and abstentions.

The agent may inspect complete sensitive inputs and results inside an authorized
local environment. The compact hierarchy files reduce initial reading cost; they
are not privacy filters. The trial config contains absolute input paths and all
artifacts contain design-derived data. Keep the directory local unless reviewed
for disclosure.

## Prepare

Run from a clone with `netlist-comparison` and its normal dependencies installed.
For two instances in one canonical file:

```sh
TRIAL=/absolute/private/path/automatic-hierarchy-trial
python examples/luna_hierarchy_trial.py prepare \
  --input-a /absolute/path/netlist.canonical --top-a TOP \
  --root-a TOP/XI0 --root-b TOP/XI1 --output "$TRIAL"
```

For two revisions:

```sh
python examples/luna_hierarchy_trial.py prepare \
  --input-a /absolute/path/before.canonical \
  --input-b /absolute/path/after.canonical \
  --top-a TOP --top-b TOP --globals-complete --omit-parameters \
  --output "$TRIAL"
```

`--globals-complete` says the declared list of global nets is complete. Ground
`0` is always included, matching the comparator CLI. Thus the command above is
the exact form for inputs with no global nets beyond ground. When other globals
exist, repeat `--global-net`, for example
`--global-net VDD --global-net VSS --globals-complete`. Omit
`--globals-complete` if the declaration is incomplete or unknown. The scope is
recorded in `trial-config.json`, used during preparation, and supplied unchanged
to both sides of the comparison batch.
This example is the architecture-first variant: `--omit-parameters` suppresses
the parameter-evidence lane. Remove that flag when parameter-class evidence is
wanted.

Optional roots restrict either revision to a selected instance. Preparation
hashes the canonical files and writes:

- `hierarchy-only-input.json`, with authored paths and case-insensitive relative
  keys beneath each selected root;
- `stable-windows.json`, containing every shared relative path with 1–64 leaves
  per side, in deterministic order;
- `unmatched-branch-input.json`, containing the first unmatched frontiers, their
  shared-parent context, and eligible descendants;
- `trial-config.json`, `input.sha256`, and a directly executable `LUNA_TASK.md`.

The default hard bound is 256 total windows. Preparation refuses a larger stable
set instead of truncating it. Shared paths outside the leaf cap remain recorded
as excluded; net, counterpart, retained-path, and proof admission remain decisions
of the comparator and therefore remain visible as result statuses.

This workflow explicitly uses the experimentally exercised 64-leaf, 96-net,
16-counterpart, 200-retained-path, and 100-presentation-path values. These are
workflow values, not package defaults or general performance claims. All values
are recorded in the config and can be changed explicitly during preparation.
The parameter choice is recorded and reused by `run`.

## Optional local Luna pass

Start a Luna medium agent in the authorized environment, give it the trial
directory, and ask it to follow `LUNA_TASK.md`. It may inspect the complete
canonical inputs locally. It writes `proposals.json`, `luna-report.md`, and,
after the batch, `luna-assessment.md`. Its short first page leads with readable
schematic locations and supported differences, including represented
additions/removals, cell populations, and pin/interface changes when available.
It separates those observations from tentative rename, move, split or merge
interpretations. Unmatched A-only/B-only branches are candidates, not proof of
historical removal/addition; positional `@N` terminals are not named pins.
No-card proposals and abstentions belong after supported findings. The agent
checks each evidence kind present in the card-bearing set before choosing its
first-page examples; a terminal residual can identify affected terminal roles
without proving which individual device was edited.
The generated task names the exact `sides.a.*` and `sides.b.*` frontier and
eligible-path arrays, records their counts, and requires Luna to confirm both
sides before returning no proposals. Its literal validate/run commands set a
quoted `PYTHONPATH` containing only the currently imported `netlist_comparison`
and `spice_canonical` source roots, so a source checkout remains runnable from a
clean shell without copying unrelated environment entries.

The validator accepts zero to 50 general 1:1, 1:n, or n:1 proposals. An empty
list is the correct answer when Luna finds no defensible unmatched relationship.
Every proposed path
must come from the handoff's unmatched eligible set, every same-side union must
be non-overlapping, and leaf totals must be exact and within the cap. Shared
relative paths and quiet controls are rejected because the deterministic pass
already owns stable hierarchy.

Validate manually when needed:

```sh
python examples/luna_hierarchy_trial.py validate "$TRIAL"
```

## Run one batch

After the optional Luna pass, one command loads the canonical inputs once and
runs deterministic windows first, followed by validated Luna proposals:

```sh
python examples/luna_hierarchy_trial.py run "$TRIAL"
```

If `proposals.json` is absent, this runs deterministic windows alone. The command
uses one explicit `compare_operator_scoped_batch` call, whose reuse is limited to
input identities and complete full-top exterior incidence. Every window still
receives a new selection, anonymous graph, proof, and report.

Complete reports are saved under `results/stable/` and `results/luna/`.
`trial-summary.json` is a compact index with exact statuses, card lanes, charges,
supplied A/B paths, report paths, and report hashes. This keeps both deterministic
and Luna locations navigable without opening each full report. The directory is
still sensitive local data. `batch-receipt.json` records the ordered IDs,
reuse key, input identities, and resource envelope without duplicating evidence.
Writes are atomic, and an existing result is not replaced unless `run --replace`
is explicit.

The input byte hashes are checked before execution. Every returned supplied scope
and every saved local extension is validated before writing. An outer deadline,
memory stop, worker failure, or serialization stop writes an incomplete summary
and receipt with zero inferred per-window outcomes. The current batch API returns
only after the whole batch completes, so no partial reports survive such a stop.

A certified result with no cards means only “no selected cards under this supplied
window and represented evidence.” It is not an unchanged or equivalence verdict.
Read the complete result for abstentions, omitted lanes, proof status, and support
charges. The Python batch API parses canonical files in the caller before its
bounded worker; the receipt's worker limits do not include that parsing time.
