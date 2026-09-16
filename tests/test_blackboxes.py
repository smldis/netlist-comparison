"""Small missing-library controls; scale remains covered by existing tests."""
from dataclasses import asdict, replace

import pytest
from spice_canonical.canonical_netlist import from_file, from_text
from netlist_comparison import Options, compare, compare_instances


SOURCE = '''X1 out in 0 0 missing_nmos W=1u L=100n
X2 out bias vdd vdd missing_pmos W=2u L=100n
R1 out 0 1k
'''
MODES = ['fixed', 'regional', 'partial_qap', 'anchor_growth']


def run(a, b, mode='fixed', **kwargs):
    return compare(from_text(a), from_text(b), top_a='TOP', top_b='TOP',
                   options=Options(matching_mode=mode, black_box_missing=True, **kwargs))


@pytest.mark.parametrize('mode', MODES)
def test_overrides_and_unchanged_missing_cells_beside_known_device(mode):
    a = from_text(SOURCE)
    original = asdict(a)
    r = compare(a, from_text(SOURCE.replace('W=1u', 'W=3u')), top_a='TOP', top_b='TOP',
                options=Options(matching_mode=mode, black_box_missing=True))
    assert asdict(a) == original
    assert len(r['representative_pair_ids']) == 3
    changed = [p for p in r['pair_options'] if p['raw_differences']]
    assert len(changed) == 1
    assert changed[0]['a'] == changed[0]['b'] == 'TOP/X1'
    assert changed[0]['raw_differences'] == [dict(field='parameters.W', a=['1u'], b=['3u'])]
    for side in ('a', 'b'):
        assert r[side]['coverage']['opaque'] == 0
        assert r[side]['black_box_leaf_count'] == 2
        obj = next(x for x in r[side]['objects'] if x['id'] == 'TOP/X1')
        assert [x['pin'] for x in obj['connections']] == ['@1', '@2', '@3', '@4']
        assert obj['black_box']['internals'] == 'unavailable'
        assert len(r[side]['diagnostics']) == 2
        assert {x['reason'] for x in r[side]['unresolved']} == {'black_box_internals_unavailable'}
    assert 'stable pin order/names' in r['scope']['black_box_assumption']


@pytest.mark.parametrize('mode', ['fixed', 'regional'])
def test_net_renaming_is_not_override_noise_but_rewiring_is_visible(mode):
    renamed = SOURCE.replace('out', 'renamed').replace('X1', 'Xrenamed')
    same = run(SOURCE, renamed, mode)
    assert len(same['representative_pair_ids']) == 3
    assert not any(p['raw_differences'] for p in same['pair_options'])
    assert not any(x['a_partitioned_across_b'] or x['b_collects_multiple_a']
                   for x in same['connectivity']['overlap'])
    edited = run(SOURCE, SOURCE.replace('X1 out in 0 0', 'X1 out out 0 0'), mode)
    assert len(edited['representative_pair_ids']) == 3
    assert any(x['a_partitioned_across_b'] or x['b_collects_multiple_a']
               for x in edited['connectivity']['overlap'])
    assert not any(p['raw_differences'] for p in edited['pair_options'])


@pytest.mark.parametrize('mode', MODES)
def test_incompatible_arity_and_cell_identity_never_pair(mode):
    r = run(SOURCE, SOURCE.replace('X1 out in 0 0', 'X1 out in 0'), mode)
    for side in ('a', 'b'):
        assert next(x for x in r[side]['objects'] if x['id'] == 'TOP/X1')['opaque_reason'] == 'incompatible_black_box_interfaces'
    assert not any(p['a'] == 'TOP/X1' or p['b'] == 'TOP/X1' for p in r['pair_options'])
    changed_cell = run(SOURCE, SOURCE.replace('missing_nmos', 'other_cell'), mode)
    assert not any(p['a'] == 'TOP/X1' or p['b'] == 'TOP/X1' for p in changed_cell['pair_options'])


def test_default_and_malformed_evidence_remain_opaque():
    r = compare(from_text(SOURCE), from_text(SOURCE), top_a='TOP', top_b='TOP')
    assert r['a']['coverage']['opaque'] == 2
    malformed = SOURCE + 'Qbad c b e substrate MissingBJT\n'
    r = run(malformed, malformed)
    assert r['a']['coverage']['opaque'] == 1
    assert next(x for x in r['a']['objects'] if x['id'] == 'TOP/Qbad')['black_box'] is None
    defined = '.subckt missing_nmos d g s b\nRinside d s 1k\n.ends\n'
    r = run(SOURCE, defined + SOURCE)
    assert next(x for x in r['a']['objects'] if x['id'] == 'TOP/X1')['opaque_reason'] == 'black_box_definition_available_on_one_side'
    assert not any(p['a'] == 'TOP/X1' for p in r['pair_options'])


def test_named_external_interfaces_and_frozen_context(tmp_path):
    path = tmp_path / 'external.sp'
    path.write_text(SOURCE)
    a = from_file(path, external_subcircuits={'missing_nmos': ['D', 'G', 'S', 'B']})
    path.write_text(SOURCE.replace('W=1u', 'W=3u'))
    b = from_file(path, external_subcircuits={'missing_nmos': ['D', 'G', 'S', 'B']})
    r = compare(a, b, top_a='TOP', top_b='TOP',
                options=Options(black_box_missing=True, context_mode='frozen_neighbors'))
    assert len(r['representative_pair_ids']) == 3
    assert any(p['a'] == 'TOP/X1' and p['raw_differences'] for p in r['pair_options'])
    assert next(x for x in r['a']['objects'] if x['id'] == 'TOP/X1')['black_box']['pin_basis'] == 'named'
    reordered = replace(a, top=replace(a.top, devices=tuple(
        replace(d, connections=tuple(reversed(d.connections))) for d in a.top.devices)))
    same = compare(a, reordered, top_a='TOP', top_b='TOP', options=Options(black_box_missing=True))
    assert len(same['representative_pair_ids']) == 3
    assert not any(x['a_partitioned_across_b'] or x['b_collects_multiple_a']
                   for x in same['connectivity']['overlap'])
    swapped = from_file(path, external_subcircuits={'missing_nmos': ['G', 'D', 'S', 'B']})
    edited = compare(a, swapped, top_a='TOP', top_b='TOP', options=Options(black_box_missing=True))
    assert len(edited['representative_pair_ids']) == 3
    assert any(x['a_partitioned_across_b'] or x['b_collects_multiple_a']
               for x in edited['connectivity']['overlap'])


def test_selected_known_blocks_keep_missing_descendants_comparable():
    source = '.subckt AMP I O\n' + SOURCE.replace('in', 'I').replace('out', 'O') + '.ends\n'
    data = from_text(source + source.replace('AMP', 'EDIT').replace('W=1u', 'W=3u') +
                     'Xleft i o AMP\nXright j k EDIT\n')
    r = compare_instances(data, top='TOP', path_a='TOP/Xleft', path_b='TOP/Xright',
                          options=Options(black_box_missing=True))
    assert len(r['representative_pair_ids']) == 3
    assert not r['boundary']['a']['scope_complete']
    with pytest.raises(ValueError, match='unresolved_definition'):
        compare_instances(data, top='TOP', path_a='TOP/Xleft/X1', path_b='TOP/Xright/X1',
                          options=Options(black_box_missing=True))


def test_cli_explains_opt_in_and_shows_override(tmp_path, capsys):
    from netlist_comparison.cli import main
    a, b = tmp_path / 'a.sp', tmp_path / 'b.sp'
    a.write_text(SOURCE)
    b.write_text(SOURCE.replace('W=1u', 'W=3u'))
    assert main([str(a), str(b), '--black-box-missing', '--text']) == 0
    out = capsys.readouterr().out
    assert 'Black-box assumption:' in out
    assert 'Black-box leaves with comparable terminals: 2' in out
    assert 'parameters.W' in out


def test_original_library_identity_survives_type_normalization():
    from spice_canonical.canonical_netlist import normalize_device_types
    a = normalize_device_types(from_text(SOURCE), {'missing_nmos': 'generic'})
    b = normalize_device_types(from_text(SOURCE.replace('missing_nmos', 'different_cell')),
                               {'different_cell': 'generic'})
    r = compare(a, b, top_a='TOP', top_b='TOP', options=Options(black_box_missing=True))
    assert not any(p['a'] == 'TOP/X1' or p['b'] == 'TOP/X1' for p in r['pair_options'])


def test_ambiguous_retained_net_tokens_are_not_split_into_invented_pins():
    source = 'X1 "two words" out missing\nR1 out 0 1k\n'
    r = run(source, source)
    assert r['a']['coverage']['opaque'] == 1
    assert next(x for x in r['a']['objects'] if x['id'] == 'TOP/X1')['connections'] == []


def test_isolated_cell_support_is_an_assumption_not_a_neighbour_witness():
    r = run('X1 a b Missing W=1u', 'Xchanged a b Missing W=3u')
    assert len(r['representative_pair_ids']) == 1
    pair = r['pair_options'][0]
    assert pair['evidence']['black_box_interface_assumed']
    assert not pair['evidence']['external_neighbors_on_both_sides']
    assert pair['raw_differences'] == [dict(field='parameters.W', a=['1u'], b=['3u'])]
