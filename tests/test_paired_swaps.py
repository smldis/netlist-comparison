from dataclasses import replace

import numpy as np
import pytest
from scipy.optimize import linear_sum_assignment
from spice_canonical.canonical_netlist import from_text

from netlist_comparison import InputScope, Options, compare
from netlist_comparison.blackbox import compatible, reconcile
from netlist_comparison.expand import expand
from netlist_comparison.swaps import challenge


def views(left, right=None):
    opts = Options(black_box_missing=True)
    a, b = [expand(from_text(t), 'TOP', InputScope(), opts)
            for t in (left, left if right is None else right)]
    reconcile(a, b)
    return a, b


def independent_error(a, b, plan):
    aa, bb = {}, {}; total = 0
    for i, j in plan:
        x = {r.casefold(): n for r, n in a.leaves[i].nets.items()}
        y = {r.casefold(): n for r, n in b.leaves[j].nets.items()}
        total += len(x.keys() | y.keys())
        for role in x.keys() & y.keys():
            aa.setdefault(x[role], set()).add((i, role))
            bb.setdefault(y[role], set()).add((i, role))
    matrix = np.array([[len(x & y) for y in bb.values()] for x in aa.values()])
    if not matrix.size:
        return total
    rr, cc = linear_sum_assignment(matrix, maximize=True)
    return total - int(matrix[rr, cc].sum())


def check_maps(a, b, plans, baseline):
    for plan in plans:
        assert len(plan) == len(dict(plan)) == len({j for _, j in plan})
        assert all(compatible(a.leaves[i], b.leaves[j]) for i, j in plan)
        assert {i for i, _ in plan} == {i for i, _ in baseline}
        assert {j for _, j in plan} == {j for _, j in baseline}


def test_all_paired_strict_local_minimum_crosses_a_worse_swap():
    # Every individual transposition worsens this map. Reaching zero requires
    # keeping a worse intermediate hypothesis, even though no leaf is omitted.
    a, b = views('X0 n5 n4 n3 Cell\nX1 n2 n0 n5 Cell\nX2 n1 n4 n3 Cell\n'
                 'X3 n0 n5 n3 Cell\nX4 n4 n3 n1 Cell\nX5 n5 n2 n0 Cell')
    permutation = [0, 3, 2, 5, 4, 1]
    initial = list(enumerate(permutation))
    assert independent_error(a, b, initial) == 3
    for i in range(6):
        for k in range(i):
            p = permutation.copy(); p[i], p[k] = p[k], p[i]
            assert independent_error(a, b, list(enumerate(p))) > 3
    plans, evidence = challenge(a, b, [initial], work_limit=512)
    check_maps(a, b, plans, initial)
    assert all(independent_error(a, b, p) == 0 for p in plans)
    trajectory = evidence['selected_score_trajectory']
    assert trajectory[0] == 3 and trajectory[1] > 3 and trajectory[-1] == 0
    assert not evidence['names_used'] and not evidence['attributes_used']


def test_body_supply_and_missing_roles_remain_in_final_objective():
    a, b = views('.model N NMOS\nM1 a g s 0 N\nM2 b g s 0 N\nM3 c h s 0 N',
                 '.model N NMOS\nM1 p q t 0 N\nM2 r q t vcc N\nM3 u v t 0 N')
    initial = [(0, 0), (1, 1), (2, 2)]
    plans, evidence = challenge(a, b, [initial], work_limit=32)
    check_maps(a, b, plans, initial)
    assert independent_error(a, b, initial) == 1
    assert evidence['best_endpoint_disagreements'] == 1
    assert all(independent_error(a, b, p) == 1 for p in plans)
    # Missing role evidence also counts: the broad native domain does not make
    # a resistor/MOS swap a complete terminal match.
    a, b = views('R1 a 0 1k\n.model N NMOS\nM1 a g 0 0 N')
    initial = [(0, 1), (1, 0)]
    plans, evidence = challenge(a, b, [initial], work_limit=16)
    assert evidence['baseline_endpoint_disagreements'] > 0
    assert independent_error(a, b, plans[-1]) == 0


def test_score_budget_counts_seeds_and_retains_incumbent(monkeypatch):
    import netlist_comparison.regional as regional
    a, b = views('X1 a b c Cell\nX2 b c d Cell\nX3 c d a Cell')
    initial = [(0, 2), (1, 1), (2, 0)]
    original = regional.net_alignment; calls = []
    def counted(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(regional, 'net_alignment', counted)
    plans, evidence = challenge(a, b, [initial], work_limit=1)
    assert plans == [initial]
    assert len(calls) == evidence['work_used'] == 1
    assert evidence['stop'] == 'work_limit'
    calls.clear()
    plans, evidence = challenge(a, b, [initial], work_limit=0)
    assert plans == [initial] and not calls and evidence['stop'] == 'disabled'


def test_hard_external_domains_and_opacity_never_enter_a_swap():
    a, b = views('X1 a b Cell\nX2 b c Cell\nX3 c a Different\nXbad a b c Missing',
                 'Xone p q Cell\nXtwo q r Cell\nXother r p Different\nXbad p q Missing')
    ai = {l.path: i for i, l in enumerate(a.leaves)}
    bi = {l.path: i for i, l in enumerate(b.leaves)}
    initial = [(ai['TOP/X1'], bi['TOP/Xtwo']), (ai['TOP/X2'], bi['TOP/Xone']),
               (ai['TOP/X3'], bi['TOP/Xother'])]
    plans, evidence = challenge(a, b, [initial], work_limit=32)
    check_maps(a, b, plans, initial)
    assert all(dict(p)[ai['TOP/X3']] == bi['TOP/Xother'] for p in plans)
    assert a.leaves[ai['TOP/Xbad']].opaque and b.leaves[bi['TOP/Xbad']].opaque
    assert evidence['work_used'] <= 2


def test_raw_fields_and_path_labels_do_not_rank_swap_search():
    a, b = views('X0 a b c Cell W=1u\nX1 b c d Cell W=2u\nX2 c d e Cell W=3u')
    initial = [[(0, 2), (1, 1), (2, 0)]]
    plans, evidence = challenge(a, b, initial, work_limit=32)
    for i, leaf in enumerate(b.leaves):
        leaf.path = f'unrelated/{17-i}'
        leaf.device = replace(leaf.device, name=f'misleading{i}', parameters=a.leaves[2-i].device.parameters)
    changed, other = challenge(a, b, initial, work_limit=32)
    assert changed == plans
    assert other['best_score'] == evidence['best_score']


def test_api_defaults_symmetry_empty_frontier_and_option_validation():
    with pytest.raises(ValueError, match='requires matching_mode'):
        Options(swap_work_limit=1)
    for invalid in (-1, True, 1.5):
        with pytest.raises(ValueError, match='nonnegative integer'):
            Options(matching_mode='regional', swap_work_limit=invalid)
    circuit = from_text('X1 a 0 RC\nX2 a 0 RC')
    base = compare(circuit, circuit, top_a='TOP', top_b='TOP', options=Options(
        matching_mode='regional', black_box_missing=True))
    new = compare(circuit, circuit, top_a='TOP', top_b='TOP', options=Options(
        matching_mode='regional', black_box_missing=True, swap_work_limit=32))
    assert 'swap_search' not in base['partial_alignment']
    assert new['a']['coverage']['ambiguous'] == 2
    assert new['inspection_regions'] == base['inspection_regions']
    assert new['partial_alignment']['swap_search']['best_endpoint_disagreements'] == 0
    flat = from_text('\n'.join(f'X{k} n{k} n{k+1} 0 Cell' for k in range(129)))
    result = compare(flat, flat, top_a='TOP', top_b='TOP', options=Options(
        matching_mode='regional', black_box_missing=True, swap_work_limit=32))
    assert not result['representative_pair_ids']
    assert result['partial_alignment']['swap_search']['stop'] == 'no_populated_incumbent'


def test_fresh_full_coverage_edit_and_permutation_with_independent_score():
    left = 'X1 a b 0 Cell\nX2 b c 0 Cell\nX3 c d 0 Cell\nX4 d e 0 Cell\nX5 e f 0 Cell'
    # Fresh reverse ordering/renaming plus one body-like third-terminal edit.
    right = 'Xaa n5 n6 0 Cell\nXbb n4 n5 0 Cell\nXcc n3 n4 altered Cell\nXdd n2 n3 0 Cell\nXee n1 n2 0 Cell'
    a, b = views(left, right)
    initial = [(i, i) for i in range(5)]
    plans, evidence = challenge(a, b, [initial], work_limit=256)
    check_maps(a, b, plans, initial)
    assert evidence['baseline_endpoint_disagreements'] > 1
    assert all(independent_error(a, b, p) == 1 for p in plans)
    assert evidence['best_endpoint_disagreements'] == 1
    baseline = dict(evidence['baseline_pairs'])
    indices = [{l.path: i for i, l in enumerate(v.leaves)} for v in (a, b)]
    for witness in evidence['witnesses']:
        mapping = baseline.copy()
        for x, y in witness['removed_pairs']:
            assert mapping.pop(x) == y
        mapping.update(witness['added_pairs'])
        reconstructed = [(indices[0][x], indices[1][y]) for x, y in mapping.items()]
        assert independent_error(a, b, reconstructed) == witness['score']


@pytest.mark.parametrize('correct_prefix,expected', [(0, 66), (6, 51)])
def test_proposal_stream_retains_old_top32_without_duplicate_pairs(monkeypatch, correct_prefix, expected):
    import netlist_comparison.regional as regional
    import netlist_comparison.swaps as swaps
    from collections.abc import Iterator
    a, b = views('\n'.join(f'X{k:02} a{k} b{k} Cell' for k in range(12)))
    initial = list(enumerate(range(12)))
    # Isolate proposal admission: all pairs, or only the last six, disagree.
    netmap = {n: n for leaf in a.leaves[:correct_prefix] for n in leaf.nets.values()}
    monkeypatch.setattr(regional, 'net_alignment', lambda *args: (1, netmap))
    original = swaps.nsmallest
    calls = []
    def inspect_stream(n, iterable):
        assert isinstance(iterable, Iterator)
        candidates = list(iterable)  # Small test oracle only; production streams.
        assert len(candidates) == expected
        assert len({row[2] for row in candidates}) == expected
        chosen = original(n, iter(candidates))
        assert chosen == sorted(candidates)[:32]
        calls.append(1)
        return chosen
    monkeypatch.setattr(swaps, 'nsmallest', inspect_stream)
    _, evidence = challenge(a, b, [initial], work_limit=2)
    assert calls == [1]
    assert evidence['proposal_comparisons'] == evidence['proposal_candidates_ranked'] == expected
    assert evidence['work_used'] == 2 and evidence['proposals_pruned']


def test_imported_seed_omissions_are_distinct_from_swap_inventory_changes():
    a, b = views('X1 a 0 RC\nX2 a 0 RC', 'X1 z 0 RC\nX2 z 0 RC\nX3 z 0 RC')
    plans, evidence = challenge(a, b, [[(0, 0), (1, 2)], [(0, 0), (1, 1)]], work_limit=8)
    witness = evidence['witnesses'][0]
    assert witness['seed_index'] == 1 and witness['score_trajectory'] == [0.6]
    reconstructed = dict(evidence['baseline_pairs'])
    for x, y in witness['removed_pairs']:
        assert reconstructed.pop(x) == y
    reconstructed.update(witness['added_pairs'])
    assert reconstructed == dict(evidence['seed_pairs'][witness['seed_index']])
    assert set(reconstructed.values()) != {y for x, y in evidence['baseline_pairs']}
    assert evidence['matched_sets_preserved_per_move']
