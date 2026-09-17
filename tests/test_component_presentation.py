"""Certified permutations reduce noise without upgrading evidence to identity."""
from dataclasses import replace
from itertools import permutations
import json

import pytest
from spice_canonical.canonical_netlist import from_text
from netlist_comparison import Options, InputScope, compare, project_saved_report
from netlist_comparison.component_presentation import _assignment, refine
from netlist_comparison.expand import expand
from netlist_comparison.regional import net_alignment
from netlist_comparison.cli import main


def decks():
    # Distinct slot topology, three raw profiles, all cells unavailable.
    rows = []
    for k in range(40):
        rows.extend([f'X{k}a o{k} i{k} t{k} 0 NF W={k % 3 + 1}u',
                     f'X{k}b t{k} i{k} 0 0 NF W=2u',
                     f'X{k}c o{k} 0 RC R={k % 4 + 1}k',
                     f'X{k}d t{k} 0 CC C=1p'])
    a = '\n'.join(rows)
    b = a.replace('X0a o0 i0 t0 0 NF W=1u', 'X0a o0 i0 t0 i0 NF W=9u')
    return a, b


def run(a, b, **kwargs):
    return compare(from_text(a), from_text(b), top_a='TOP', top_b='TOP',
                   options=Options(matching_mode='regional', black_box_missing=True, **kwargs))


def selected(report):
    return [p for p in report['pair_options'] if p['id'] in report['representative_pair_ids']]


def test_raw_noise_reduction_keeps_incidence_and_full_factor_ambiguity():
    a, b = decks()
    old = run(a, b); new = run(a, b, component_presentation='minimum_raw')
    assert sum(bool(p['raw_differences']) for p in selected(old)) > 1
    assert sum(bool(p['raw_differences']) for p in selected(new)) == 1
    assert len(selected(old)) == len(selected(new)) == 160
    assert old['partial_alignment'] == {**new['partial_alignment'], 'seconds': old['partial_alignment']['seconds']}
    for side in ('a', 'b'):
        assert {p[side] for p in selected(old)} == {p[side] for p in selected(new)}
        assert new[side]['coverage'] == old[side]['coverage']
    va, vb = [expand(from_text(s), 'TOP', InputScope(), Options(black_box_missing=True)) for s in (a, b)]
    ia = {l.path: i for i, l in enumerate(va.leaves)}; ib = {l.path: i for i, l in enumerate(vb.leaves)}
    assert net_alignment(va, vb, [(ia[p['a']], ib[p['b']]) for p in selected(new)])[0] == 1
    detail = new['representative_selection']['components']
    witness = detail['representative_wiring_witness']
    assert len(witness['endpoint_disagreements']) == 1
    assert witness['endpoint_disagreements'][0]['b'] == 'TOP/X0a'
    assert len({p['a'] for p in witness['net_pairs']}) == len({p['b'] for p in witness['net_pairs']}) == len(witness['net_pairs'])
    assert sum(r['minimum_differing_pairs_in_slot'] for r in detail['representative_profile_imbalances']) == 1
    assert any(p['b'] == 'TOP/X0a' for p in selected(new) if p['raw_differences'])
    view = project_saved_report(new, categories=['raw'])
    assert view['context']['representative_selection']['components'] == detail


def test_rename_and_equal_population_do_not_assert_hidden_swaps():
    a, _ = decks()
    # Reverse declarations and rename every instance and every non-ground net.
    data = from_text(a)
    devices = [replace(d, name='Xrenamed' + str(k), connections=tuple(
        replace(c, net='renamed_' + c.net if c.net != '0' else '0') for c in d.connections))
        for k, d in enumerate(data.top.devices)]
    other = replace(data, top=replace(data.top, devices=tuple(reversed(devices))))
    r = compare(data, other, top_a='TOP', top_b='TOP', options=Options(
        matching_mode='regional', black_box_missing=True, component_presentation='minimum_raw'))
    assert len(selected(r)) == 160
    assert not any(p['raw_differences'] for p in selected(r))
    assert not r['representative_selection']['components']['representative_profile_imbalances']
    assert r['a']['coverage']['ambiguous'] == 160
    assert not r['partial_alignment']['alternatives_complete']


def test_cancel_then_assignment_agrees_with_small_exhaustive_oracle():
    # Includes vectors with balanced per-slot populations but unavoidable paired
    # differences: independent slot permutations would incorrectly report zero.
    for left, right in [([(1, 1), (2, 2)], [(1, 2), (2, 1)]),
                        ([(1, 2), (1, 2), (3, 4), (5, 6)], [(5, 6), (1, 2), (3, 2), (1, 4)])]:
        score = lambda p: sum(x != y for i, j in enumerate(p) for x, y in zip(left[i], right[j]))
        chosen, _ = _assignment(left, right, 256)
        assert score([chosen[i] for i in range(len(left))]) == min(map(score, permutations(range(len(left)))))
    assert _assignment([(1,), (2,)], [(3,), (4,)], 1) == (None, 2)


def test_partial_and_budgeted_factors_preserve_unmatched_sets_and_report_limits():
    a, b = decks(); options = Options(matching_mode='regional', black_box_missing=True)
    va, vb = [expand(from_text(s), 'TOP', InputScope(), options) for s in (a, b)]
    from netlist_comparison.budgeted import factor_match, Work
    plans, ev = factor_match(va, vb, Work(50000))
    partial = [plans[0][1:]]
    result, info = refine(va, vb, partial, ev['component_permutation_factors'], residual_limit=0)
    assert {i for i, j in result[0]} == {i for i, j in partial[0]}
    assert {j for i, j in result[0]} == {j for i, j in partial[0]}
    assert info['hypotheses'][0]['partially_paired_factors']
    assert info['hypotheses'][0]['skipped_large_residual_factors']


def test_b_side_permutations_keep_incidence_and_do_not_mutate_input_plans():
    a, b = decks(); options = Options(matching_mode='regional', black_box_missing=True)
    va, vb = [expand(from_text(s), 'TOP', InputScope(), options) for s in (a, b)]
    from netlist_comparison.budgeted import factor_match, Work
    plans, ev = factor_match(va, vb, Work(50000))
    original = [list(p) for p in plans]
    result, info = refine(va, vb, plans, [f for f in ev['component_permutation_factors'] if f['side'] == 'b'])
    assert plans == original
    assert info['hypotheses'][0]['permutations']
    assert net_alignment(va, vb, result[0])[0] == net_alignment(va, vb, original[0])[0] == 1
    assert {i for i, j in result[0]} == {i for i, j in original[0]}
    assert {j for i, j in result[0]} == {j for i, j in original[0]}


def test_cli_and_saved_evidence(tmp_path, capsys):
    a, b = decks(); pa = tmp_path / 'a.sp'; pb = tmp_path / 'b.sp'; saved = tmp_path / 'report.json'
    pa.write_text(a); pb.write_text(b)
    assert main([str(pa), str(pb), '--matching-mode', 'regional', '--black-box-missing',
                 '--component-presentation', 'minimum_raw', '--output', str(saved), '--text', '--limit', '1']) == 0
    captured = capsys.readouterr(); text = captured.out + captured.err
    assert 'Certified component presentation:' in text and 'Endpoint example:' in text
    assert 'all structural alternatives retained' in text and 'TOP/X0a' in text
    assert json.loads(saved.read_text())['representative_selection']['components']['hypotheses']
    with pytest.raises(ValueError, match='requires matching_mode regional'):
        Options(component_presentation='minimum_raw')
