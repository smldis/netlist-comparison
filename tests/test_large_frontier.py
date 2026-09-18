import importlib.util
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import linear_sum_assignment
from spice_canonical.canonical_netlist import from_text

from netlist_comparison import InputScope, Options, compare
from netlist_comparison.blackbox import reconcile
from netlist_comparison.expand import expand
from netlist_comparison.large_frontier import match
from netlist_comparison.pieces import connectivity_frontier
from netlist_comparison.regional import match_regional, net_alignment

spec = importlib.util.spec_from_file_location('large_control', Path(__file__).parents[1] / 'examples/evaluate_large_frontier.py')
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


def views(a, b=None, **kwargs):
    opts = Options(black_box_missing=True, **kwargs)
    va, vb = [expand(data, 'TOP', InputScope(), opts) for data in (a, a if b is None else b)]
    reconcile(va, vb)
    return va, vb


def test_connected_blackboxes_admit_without_existing_frontier():
    a, _ = control.fixture(144)
    b, _ = control.fixture(144, rename=True)
    va, vb = views(a, b)
    assert connectivity_frontier(va) is connectivity_frontier(vb) is None
    baseline, ev = match_regional(va, vb)
    assert not baseline and ev['compute_budget']['used'] == 0
    plans, ev = match_regional(va, vb, large_frontier_work_limit=50000)
    assert len(plans[-1]) == 144
    assert net_alignment(va, vb, plans[-1])[0] == 0
    assert ev['hypotheses'][-1]['unmatched_leaves'] == 0
    assert ev['method'] == 'regional_sparse_frontier_v8'
    search = ev['large_frontier_search']
    assert len(search['seed_pair_paths']) == search['consistent_seeds']
    assert not ev['alternatives_complete']
    assert not ev['names_used'] and not ev['attributes_used']


def test_changed_unequal_depth_four_to_five_has_a_local_edit_hint():
    a, la = control.fixture(600, hierarchical=True)
    b, lb = control.fixture(600, changed=True, hierarchical=True, rename=True, additions=150)
    report = compare(a, b, top_a='TOP', top_b='TOP', options=Options(
        matching_mode='regional', black_box_missing=True, large_frontier_work_limit=50000))
    assert report['algorithm'] == 'regional_sparse_frontier_v8'
    ev = report['partial_alignment']
    assert len(report['representative_pair_ids']) >= 590
    assert ev['hypotheses'][-1]['endpoint_disagreements'] <= 1
    changed = [p for p in report['pair_options'] if p['raw_differences']]
    assert [(p['a'], p['b']) for p in changed] == [(la[300], lb[300])]
    assert any(token.startswith(changed[0]['id'] + ':')
               for row in report['connectivity']['overlap']
               if row['a_partitioned_across_b'] or row['b_collects_multiple_a']
               for token in row['endpoint_tokens'])
    region = next(r for r in report['inspection_regions'] if la[300] in r['a'])
    assert region['b'] == [lb[300]] and not region['alternatives_complete']
    assert all(p['correspondence'] == 'tentative' for p in report['pair_options'])
    for side in ('a', 'b'):
        assert sum(report[side]['coverage'].values()) == report[side]['expanded_leaf_count']
        assert report[side]['coverage']['unresolved'] > 0
        assert report[side]['black_box_leaf_count'] == report[side]['expanded_leaf_count']
    assert ev['hypotheses'][-1]['unpaired_b']
    assert report['population_evidence']['groups'][0]['represented_surplus'] == 149


def test_symmetric_ring_abstains_and_retains_unresolved_class_not_identity():
    a = from_text('\n'.join(f'X{i} n{i} n{(i+1)%144} 0 Cell W={i}' for i in range(144)))
    va, vb = views(a)
    plans, ev = match(va, vb, work_limit=50000)
    assert not plans and ev['stop'] == 'no_consistent_seeds'
    assert len(ev['unresolved_label_classes']) == 1
    assert len(ev['unresolved_label_classes'][0]['a']) == 144
    assert ev['work_used'] == 0


def test_false_seed_incidence_is_quarantined_including_suppressed_dense_nets():
    # Sparse topology is individually distinguishable. The third dense terminal
    # is ignored by WL, so locally unique seeds propose incompatible net maps.
    rows = [f'X{i} n{i} n{i+1} bus{i%2} Cell' for i in range(144)]
    changed = rows.copy()
    changed[0] = changed[0].replace('bus0', 'bus1')
    va, vb = views(from_text('\n'.join(rows)), from_text('\n'.join(changed)))
    plans, ev = match(va, vb, work_limit=50000)
    assert ev['quarantined_proposals'] > 0
    assert ev['consistent_seeds'] < ev['seed_proposals']
    # Abstention is allowed; any retained core is incidence-consistent. A final
    # completion's discrepancy bound is independent of an assumed history.
    assert net_alignment(va, vb, plans[-1] if plans else [])[0] <= ev['completion_pairs']


def test_atomic_budget_keeps_scope_and_never_accepts_partial_round():
    a, _ = control.fixture(144)
    va, vb = views(a)
    none, ev = match(va, vb, work_limit=1)
    assert not none and ev['stop'] == 'seed_work_limit' and ev['work_used'] == 0
    chain = from_text('\n'.join(f'X{i} n{i} n{i+1} 0 Cell' for i in range(144)))
    va, vb = views(chain)
    _, initial = match(va, vb, work_limit=50000, rounds=0)
    plans, ev = match(va, vb, work_limit=initial['seed_proposals'] + 1)
    assert ev['stop'] == 'candidate_work_limit'
    assert len(plans[-1]) == ev['consistent_seeds']
    assert ev['work_used'] == ev['work_limit']
    report = compare(a, a, top_a='TOP', top_b='TOP', options=Options(
        matching_mode='regional', black_box_missing=True, large_frontier_work_limit=1, max_objects=140))
    assert not report['a']['expansion_complete']
    assert sum(report['a']['coverage'].values()) == report['a']['expanded_leaf_count']
    assert not report['representative_pair_ids']


def test_opaque_and_incompatible_cells_never_enter_large_map():
    a, _ = control.fixture(144)
    va, vb = views(a)
    # Keep original canonical data; mutate only these isolated expanded views.
    va.leaves[0].opaque = 'unknown'
    vb.leaves[1].black_box = dict(vb.leaves[1].black_box, cell='Different')
    plans, ev = match(va, vb, work_limit=50000)
    for i, j in plans[-1]:
        assert i != 0 and j != 1


@pytest.mark.parametrize('right_nets', [71, 144, 211])
def test_sparse_overlap_validation_matches_independent_dense_oracle(monkeypatch, right_nets):
    from collections import Counter
    rng = np.random.default_rng(29)
    a = from_text('\n'.join(f'X{i} n{i} n{(i+1)%144} Cell' for i in range(144)))
    b = from_text('\n'.join(f'X{i} n{i%right_nets} n{(i+1)%right_nets} Cell' for i in range(144)))
    va, vb = views(a, b)
    plan = list(enumerate(map(int, rng.permutation(144))))
    aa, bb = list(va.nets), list(vb.nets)
    index_a, index_b = {n:i for i,n in enumerate(aa)}, {n:i for i,n in enumerate(bb)}
    overlap = Counter((index_a[u], index_b[vb.leaves[j].nets[r]])
                      for i,j in plan for r,u in va.leaves[i].nets.items())
    matrix = np.zeros((len(aa),len(bb)), dtype=int)
    for (i,j), count in overlap.items(): matrix[i,j] = count
    rr, cc = linear_sum_assignment(matrix, maximize=True)
    expected = 288 - int(matrix[rr,cc].sum())
    import netlist_comparison.regional as regional
    import scipy.sparse.csgraph as csgraph
    sparse_assignment = csgraph.min_weight_full_bipartite_matching
    sparse_calls = []
    def counted(matrix):
        sparse_calls.append(matrix.nnz)
        assert matrix.nnz <= 3 * len(plan)
        return sparse_assignment(matrix)
    monkeypatch.setattr(csgraph, 'min_weight_full_bipartite_matching', counted)
    original = regional.linear_sum_assignment
    def bounded(matrix, **kwargs):
        assert matrix.size <= 4096
        return original(matrix, **kwargs)
    monkeypatch.setattr(regional, 'linear_sum_assignment', bounded)
    assert net_alignment(va, vb, plan)[0] == expected
    assert sparse_calls


@pytest.mark.parametrize('value', [-1, True, 1.5])
def test_option_validation(value):
    with pytest.raises(ValueError, match='nonnegative integer'):
        Options(matching_mode='regional', large_frontier_work_limit=value)
    with pytest.raises(ValueError, match='requires matching_mode'):
        Options(large_frontier_work_limit=1)


def test_residual_size_admission_failure_retains_partial_round_bounded_scope():
    text = '.subckt Tiny a b c\nXlast a b c Cell\n.ends\n'
    text += '\n'.join(f'X{i} n{i} n{i+1} 0 Cell' for i in range(300))
    text += '\nXwrap n300 n301 0 Tiny'
    va, vb = views(from_text(text))
    baseline, ev = match_regional(va, vb)
    assert not baseline and ev['stop'] == 'regional_size_budget'
    assert ev['factor_search']['stop'] == 'factor_not_applicable'
    assert not ev['connectivity_frontier_available']
    assert ev['compute_budget']['used'] == 0
    plans, ev = match_regional(va, vb, large_frontier_work_limit=50000)
    assert 100 < len(plans[-1]) < 301
    assert ev['large_frontier_search']['stop'] == 'round_limit'
    assert ev['hypotheses'][-1]['unpaired_a'] and ev['hypotheses'][-1]['unpaired_b']
    assert ev['hypotheses'][-1]['endpoint_disagreements'] == 0
