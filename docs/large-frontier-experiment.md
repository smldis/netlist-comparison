# Bounded sparse admission experiment — 2026-09-18

Implemented an **opt-in** vertical slice, `large_frontier_work_limit` (CLI:
`--large-frontier-work-limit 50000`, regional only, default zero). All data below
are newly generated public synthetic controls. No private input was read. The
7,037/8,371 counts deliberately mirror the reported scale, not its topology.

## Evidence behind the change

`factor_match` rejects a single inseparable component; `connectivity_frontier`
rejects oversized connected cores. The hierarchy path then returns either
`no_populated_frontier` or `regional_size_budget` (over 256 residual leaves or
64 regions), without spending regional work. Raising that counter cannot alter
admission. A connected 301-leaf chain with one small authored block reproduces
all three reported diagnostics: `regional_size_budget`, `factor_not_applicable`,
no connectivity frontier, work zero. The new path retains a partial map there.

Existing role-WL/anchor growth can retrieve useful counterparts without any such
frontier. Reusing its *proposal evidence*, with full-incidence conflict abstention
and a separate final completion, yielded a coherent small admission method.
This is not a new decomposition or a general alignment optimizer.

## Method and bounds

1. Compute existing depth-three typed role-WL labels. A label singleton on both
   sides with sparse neighbour incidence proposes a tentative seed. Names, raw
   values and authored hierarchy do not score candidates. Type, roles and external
   cell/interface must agree; opaque leaves are excluded.
2. Check the complete seed batch's terminal map, including globals/dense nets.
   Reject every proposal touching a nonfunctional/noninjective net relation.
   This establishes incidence consistency of the retained partial map, **not
   identity of its leaves**. Insufficient seed budget admits no seed prefix.
3. In at most 64 rounds, index unpaired leaves by compatible domain, role and
   currently mapped sparse net. Nets above 32 endpoints and explicit globals do
   not generate candidates. Retain mutual unique support winners, then reject
   their net conflicts as a batch. Incomplete budgeted rounds are discarded.
4. One final pass admits mutual unique proposals with two distinct supported
   sparse nets and at most one unsupported terminal. These proposals never grow
   the core. Under the core net map, each adds at most one endpoint discrepancy;
   full original role incidence supplies the reported maximum-overlap score.

The new path runs only after no populated regional hypothesis survives and at
least one view exceeds 128 leaves. Its separate counter charges singleton seed
checks and candidate scores, including discarded candidate work. It does not
bound preprocessing, whole API time or memory. Existing higher-omission-cost
completion is skipped for this path so its unsupported proposals cannot propagate;
separately requested omission/swap searches remain separate experiments.

For N leaves, E terminal incidences, budget B, max arity P, degree cap D=32 and
R<=64 rounds, proposal storage is O(N+E+B), not O(Na*Nb). Each round traverses
incidence and at most D candidates per query terminal; scoring costs O(BP),
with sorting overhead and O(R E D) retrieval before sorting. Fixed-depth WL adds
signature sorting/hashing. This does not make native validation time linear.
Large overlap components now use sparse optional weighted bipartite assignment
with one dummy per A net; weights preserve the existing exact maximum-overlap
objective. Dense blocks are limited to 4,096 cells. Net-map tie representatives
can differ from the old dense solver. Independent dense-oracle tests cover square
and rectangular large blocks and enforce sparse storage. Legacy reference
retrieval, presentation and user-requested other searches retain their own limits.

## Public measurements

Times are single full `compare` API wall-time samples, excluding parsing and the
external evaluation oracle; not latency guarantees. All pairs below are tentative.
“Error” counts conditional paired-terminal discrepancies, excluding unpaired leaves
and hidden cell internals. A zero-pair baseline has no meaningful error verdict.

| Control | Existing regional pairs | Anchor pairs / error / seconds | Sparse pairs / error / seconds | Sparse unpaired A/B |
|---|---:|---:|---:|---:|
| Connected chain, 129 unchanged | 0 | 129 / 0 / 0.089 | 129 / 0 / 0.086 | 0 / 0 |
| Connected branched 144, independently renamed | 0 | 144 / 0 / 0.095 | 144 / 0 / 0.092 | 0 / 0 |
| Depth 4→5, 2,000→2,499, renamed/regrouped/edited | 0 | 1,999 / 1 / 1.830 | 1,998 / 1 / 1.767 | 2 / 501 |
| Depth 4→5, 7,037→8,371, renamed/regrouped/edited | 0 | 7,036 / 1 / 6.761 | 7,035 / 1 / 7.853 | 2 / 1,336 |
| Uniform chain, 5,000 unchanged | 0 | 134 / 0 / 4.236 | 134 / 0 / 4.319 | 4,866 / 4,866 |
| Symmetric ring, 144 | 0 | 0 / — / 0.087 | 0 / — / 0.063 | 144 / 144 |
| Chain 144, one dense-bus terminal changed | 0 | 134 / 1 / 0.106 | 0 / — / 0.067 | 144 / 144 |

The two large edited controls remove one leaf, add 500/1,335, rewire one terminal
and change its raw W override; all represented leaves are external `Cell` calls.
Independent instance/net renaming, declaration reordering and changed bank
allocation preserve a generator ledger used **only by evaluation**. Sparse and
anchor maps have zero historical disagreements on these controls; that is not
proof that other histories are impossible. Both expose exactly one raw-changed
pair, with the edited path on both sides and a singleton *conditional* inspection
region. The 600→749 regression also checks that this leaf participates in the
reported wiring partition evidence. Remaining objects stay explicitly unresolved;
materialized population surplus is reported separately from exact deletion identity.

The 7,037 case uses 7,050 sparse work units: 7,032 core pairs and three completion
pairs. Existing regional takes 4.612 seconds with work zero. The new partial map
covers 99.97% of A and 84.04% of B. The omission of one extra surviving leaf is a
real cost relative to anchor growth, not a successful deletion localization.
The long chain reaches the round limit despite only 136 work units: insufficient
structural distinction, not candidate-budget exhaustion, limits coverage.
The dense-bus edit quarantines all six seeds. This catches incompatible incidence
but loses all localization; it does **not** demonstrate superior false-anchor recovery.

## Reproduction and checks

From a checkout with its declared dependencies installed:

```bash
python examples/evaluate_large_frontier.py --leaves 144
python examples/evaluate_large_frontier.py --leaves 2000 --hierarchical --changed --additions 500
python examples/evaluate_large_frontier.py --leaves 7037 --hierarchical --changed --additions 1335
python -m pytest -q tests
```

`tests/test_large_frontier.py` covers missing and oversized regional frontiers,
changed unequal populated hierarchy, conditional raw/wiring localization, symmetry,
dense-net seed conflicts, atomic budget exhaustion, incomplete expansion, opaque
and incompatible objects, and independent incidence validation. CLI tests exercise
the flag, forwarding, default and mode restriction. Chain/ring rows use
`X{i} n{i} n{i+1} 0 Cell` (ring wraps the next index modulo N); the dense conflict
uses alternating `bus{i%2}` instead of ground and changes X0 from bus0 to bus1.
The full regression run passed **194 tests in 17.90 seconds** using the author's
existing environment; final focused checks also cover the retained seed-path
evidence. No dependency installation,
commit, push or publication was performed.

## Decision, uncertainty and next question

Retain this as an explicit opt-in experiment. The strongest finding is that sparse
partial admission can supply useful raw/wiring inspection paths at the reported
scale without a decomposition or dense leaf matrix. It has **not** outperformed
anchor growth in these controls and inherits the central risk of unproved local
anchor identity. A consistent wrong seed can survive; repeated classes, ties,
large redesigns and distant propagation remain unresolved. The synthetic random
chords deliberately create strong local distinction and are an external-validity
limit. Public real-input quality is unmeasured; no private validation is implied.

No implementation blocker remains. The next discriminating question is whether a
public connected graph with weak local distinction and misleading unique motifs
can retain edit localization after rejecting conflicting anchors, without the
all-or-nothing failure seen on the dense-bus control. That evidence should decide
whether revisable local hypotheses are warranted, rather than raising this path's
budgets or replacing the existing defaults.
