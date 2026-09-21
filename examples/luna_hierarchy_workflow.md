# Local Luna hierarchy-window workflow

This optional workflow turns one canonical comparison into a compact hierarchy
handoff for a local Luna medium agent, validates the agent's proposed windows,
and runs `operator_scoped` on each accepted proposal. Luna proposes places to
inspect. Neither its proposal nor a comparator card establishes correspondence,
edit history, circuit behavior, or electrical equivalence.

The agent may inspect the complete inputs and results inside an authorized local
environment, including sensitive design data. The hierarchy manifest reduces
initial reading cost; it is not a privacy filter. The trial directory contains
absolute input paths and design-derived data, so keep the directory local unless
it has been reviewed for disclosure.

Run the workflow from a clone with `netlist-comparison` and its normal dependencies
installed. It adds no dependency beyond the package itself. For two instances in
one canonical file:

```sh
TRIAL=/absolute/private/path/luna-netlist-trial
python examples/luna_hierarchy_trial.py prepare \
  --input-a /absolute/path/netlist.canonical --top-a TOP \
  --root-a TOP/XI0 --root-b TOP/XI1 --output "$TRIAL"
```

For two revisions, supply `--input-a`, `--input-b`, `--top-a`, and `--top-b`.
The roots are optional in that form; supplying them restricts each hierarchy
manifest to the selected instance.

Preparation writes `hierarchy-only-input.json`, `input.sha256`,
`trial-config.json`, and `LUNA_TASK.md`. Start a Luna medium agent inside the
authorized local environment, give it the trial directory, and ask it to follow
`LUNA_TASK.md`. The generated task includes exact validation and run commands
for the Python interpreter and checkout that prepared the handoff. It asks Luna
to produce:

- `proposals.json`, containing tentative 1:1, 1:n, or n:1 windows;
- `luna-report.md`, explaining how those windows were selected;
- `luna-assessment.md`, interpreting the resulting comparator statuses without
  promoting a proposal to known identity.

The workflow accepts zero to ten quiet controls because a small design may not
provide five defensible controls. It validates input hashes, exact leaf counts,
the configured leaf cap, known paths, non-overlapping unions, safe unique IDs,
unique priorities, and the proposal schema before comparison. Run the generated
commands yourself if the agent stops after writing `proposals.json`:

```sh
python examples/luna_hierarchy_trial.py validate "$TRIAL"
python examples/luna_hierarchy_trial.py run "$TRIAL" \
  --seconds 180 --memory-mib 3072
```

Read `trial-summary.json` first. It records one exact status per proposed window,
with card lanes, charged-path count, time, and memory. Full evidence is under
`results/`. A certified window with no cards means only that represented local
incidence produced no selected card under the supplied relationship. It does not
prove equivalence or validate Luna's correspondence guess.

This pass is aimed at unmatched branches where rename, move, split, or merge may
have broken path equality. Deterministic enumeration is the ordinary source for
stable same-path scopes. Current `operator_scoped` admission and evidence limits
remain authoritative; proposal validation at the leaf cap does not guarantee that
a window will pass net, ambiguity, counterpart, or charged-path limits.

