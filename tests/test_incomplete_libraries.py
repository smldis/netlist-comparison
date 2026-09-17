"""Available structure survives incomplete inputs without inventing internals."""
from dataclasses import replace

import pytest
from spice_canonical.canonical_netlist import from_file, from_text
from netlist_comparison import compare, compare_instances, Options


CELL = '''.subckt CELL I O G
M1 O I T G UnknownMOS W=1u
D1 T G UnknownDiode area=2
Q1 O I G UnknownBJT
R1 O G 1k
.ends
'''


def check_available(result, prefix_a, prefix_b):
    assert len(result['representative_pair_ids']) == 4
    assert any(p['a'] == prefix_a + '/M1' and p['b'] == prefix_b + '/M1'
               and any(d['field'] == 'parameters.W' for d in p['raw_differences'])
               for p in result['pair_options'])
    for side, prefix in (('a', prefix_a), ('b', prefix_b)):
        assert result[side]['coverage']['opaque'] == 1
        opaque = next(o for o in result[side]['objects'] if o['opaque_reason'])
        assert opaque['id'] == prefix + '/Xmissing'
        assert opaque['type'] == 'UnknownBlock'
        assert opaque['connections'] == [dict(pin='@1', net='I'), dict(pin='@2', net='O'), dict(pin='@3', net='G')]
        assert opaque['parameters'] == [dict(name='gain', value='{K*2}')]
        assert result[side]['unresolved'] == [dict(region=opaque['id'], reason='unresolved_definition', hidden_leaf_count=None)]
        assert not any(p[side] == opaque['id'] for p in result['pair_options'])
        mos = next(o for o in result[side]['objects'] if o['id'].endswith('/M1'))
        assert mos['type'] == 'mosfet'
        assert dict((p['name'], p['value']) for p in mos['parameters'])['model'] == 'UnknownMOS'
        assert {c['pin'] for c in mos['connections']} == {'d', 'g', 's', 'b'}


@pytest.mark.parametrize('mode', ['fixed', 'regional'])
def test_missing_include_models_and_subckt_leave_edited_sibling_comparable(tmp_path, mode):
    cell = CELL.replace('.ends', 'Xmissing I O G UnknownBlock gain={K*2}\n.ends')
    paths = [tmp_path / f'{side}.sp' for side in ('a', 'b')]
    for path, width in zip(paths, ('1u', '9u')):
        path.write_text('.include absent.inc\n' + cell.replace('W=1u', 'W=' + width) + 'Xknown input output 0 CELL\n')
    a, b = map(from_file, paths)
    result = compare(a, b, top_a='TOP', top_b='TOP', options=Options(matching_mode=mode))
    check_available(result, 'TOP/Xknown', 'TOP/Xknown')
    assert result['a']['diagnostics'][0]['source'] == str(paths[0])
    assert result['a']['diagnostics'][0]['line'] == 1
    assert 'included file was not found' in result['a']['diagnostics'][0]['message']


@pytest.mark.parametrize('mode', ['fixed', 'regional'])
def test_selected_known_calls_keep_opaque_descendants_and_input_diagnostic_scope(mode):
    cell = CELL.replace('.ends', 'Xmissing I O G UnknownBlock gain={K*2}\n.ends')
    data = from_text(cell + cell.replace('CELL', 'EDIT').replace('W=1u', 'W=9u') +
                     'Xleft in out 0 CELL\nXright next next 0 EDIT\nXoutside z q Elsewhere\n')
    result = compare_instances(data, top='TOP', path_a='TOP/Xleft', path_b='TOP/Xright', options=Options(matching_mode=mode))
    check_available(result, 'TOP/Xleft', 'TOP/Xright')
    assert not result['boundary']['a']['scope_complete']
    assert any('Elsewhere' in d['message'] for d in result['a']['diagnostics'])
    with pytest.raises(ValueError, match='unresolved_definition at TOP/Xleft/Xmissing'):
        compare_instances(data, top='TOP', path_a='TOP/Xleft/Xmissing', path_b='TOP/Xright')
    with pytest.raises(ValueError, match='unresolved_definition'):
        compare_instances(data, top='TOP', path_a='TOP/Xoutside/child', path_b='TOP/Xright')


@pytest.mark.parametrize('external', [False, True])
@pytest.mark.parametrize('opaque_count', [1, 70])
def test_opaque_components_do_not_poison_more_than_64_certified_components(tmp_path, external, opaque_count):
    from test_budgeted import repeated
    a, b = repeated()
    source = tmp_path / 'unknown.sp'
    source.write_text('\n'.join(f'Xunknown{k} in out Missing gain=3' for k in range(opaque_count)))
    unknown = from_file(source,
                        external_subcircuits={'Missing': ['A', 'B']} if external else None)
    a = replace(a, top=replace(a.top, devices=(*a.top.devices, *unknown.top.devices)))
    b = replace(b, top=replace(b.top, devices=(*b.top.devices, *unknown.top.devices)))
    # With external pins use separate connections so each component is bounded.
    # The external signature gives terminals, never an internal implementation.
    if external:
        def separate(data):
            return replace(data, top=replace(data.top, devices=tuple(
                replace(d, connections=tuple(replace(c, net=c.net + d.name) for c in d.connections))
                if d.name.startswith('Xunknown') else d for d in data.top.devices)))
        a, b = separate(a), separate(b)
    result = compare(a, b, top_a='TOP', top_b='TOP', options=Options(matching_mode='regional'))
    assert len(result['representative_pair_ids']) == 280
    assert {h['endpoint_disagreements'] for h in result['partial_alignment']['hypotheses']} == {1}
    assert all(h['unmatched_leaves'] == 2 * opaque_count for h in result['partial_alignment']['hypotheses'])
    for side in ('a', 'b'):
        assert result[side]['coverage']['opaque'] == opaque_count
        factors = result['partial_alignment']['component_permutation_factors']
        assert all('Xunknown' not in p for f in factors for row in f['components'] for p in row)
    assert sum(bool(p['raw_differences']) for p in result['pair_options']) == 1


def test_external_signature_preserves_connections_but_never_supplies_internals(tmp_path):
    source = tmp_path / 'external.sp'
    source.write_text(CELL + 'Xknown a b 0 CELL\nXmissing a b 0 Missing P=7')
    data = from_file(source,
                     external_subcircuits={'Missing': ['I', 'O', 'G']})
    for mode in ('fixed', 'regional'):
        result = compare(data, data, top_a='TOP', top_b='TOP', options=Options(matching_mode=mode))
        assert len(result['representative_pair_ids']) == 4
        opaque = next(o for o in result['a']['objects'] if o['opaque_reason'])
        assert opaque['connections'] == [dict(pin='I', net='a'), dict(pin='O', net='b'), dict(pin='G', net='0')]
        assert opaque['resolved_nets']['G'] == 'global:0'
        assert opaque['parameters'] == [dict(name='P', value='7')]
        assert result['a']['coverage']['opaque'] == 1


def test_malformed_represented_structure_remains_an_error():
    with pytest.raises(ValueError):
        from_text(CELL + 'Xbad a b CELL')
    data = from_text(CELL + 'Xok a b 0 CELL')
    duplicate = replace(data, subcircuits=(*data.subcircuits, data.subcircuits[0]))
    with pytest.raises(ValueError, match='duplicate circuit definition'):
        compare(duplicate, data, top_a='TOP', top_b='TOP')


def test_external_opaque_neighbour_keeps_known_remainder_comparable(tmp_path):
    from test_budgeted import repeated
    a, b = repeated()
    path = tmp_path / 'external.sp'
    path.write_text('Xmissing i0 o0 Missing gain=3')
    call = from_file(path, external_subcircuits={'Missing': ['A', 'B']}).top.devices[0]
    a = replace(a, top=replace(a.top, devices=(*a.top.devices, call)))
    b = replace(b, top=replace(b.top, devices=(*b.top.devices, call)))
    result = compare(a, b, top_a='TOP', top_b='TOP', options=Options(matching_mode='regional'))
    assert len(result['representative_pair_ids']) == 280
    assert result['a']['coverage']['opaque'] == 1
    assert any(p['b'] == 'TOP/X0/M1' and p['raw_differences'] for p in result['pair_options'])
    assert all('TOP/X0/M1' not in row for f in result['partial_alignment']['component_permutation_factors']
               if f['side'] == 'a' for row in f['components'])


@pytest.mark.parametrize('mode', ['fixed', 'regional'])
def test_missing_definition_on_one_side_is_unresolved_not_a_deletion(mode):
    a = from_text(CELL + 'Xknown a b 0 CELL\nXopaque p q Missing gain=2')
    b = from_text(CELL.replace('W=1u', 'W=9u') +
                  '.subckt Missing P Q\nLhidden P Q 1n\n.ends\n'
                  'Xknown a b 0 CELL\nXopaque p q Missing gain=2')
    result = compare(a, b, top_a='TOP', top_b='TOP', options=Options(matching_mode=mode))
    assert len(result['representative_pair_ids']) == 4
    row = next(d for d in result['a']['disposition'] if d['object'] == 'TOP/Xopaque')
    assert row['status'] == 'opaque'
    assert result['a']['coverage']['opaque'] == 1
    assert not any(p['b'] == 'TOP/Xopaque/Lhidden' for p in result['pair_options'])


@pytest.mark.parametrize('mode', ['fixed', 'regional'])
@pytest.mark.parametrize('selected', [False, True])
def test_ambiguous_bjt_never_supplies_incidence_but_known_siblings_survive(mode, selected):
    cell = CELL.replace('.ends', 'Qamb O I G substrate MaybeModel area={A*2}\n.ends')
    a = from_text(cell + 'Xleft in out 0 CELL')
    b = from_text(cell.replace('W=1u', 'W=9u') + 'Xleft in out 0 CELL')
    if selected:
        data = from_text(cell + cell.replace('CELL', 'EDIT').replace('W=1u', 'W=9u') +
                         'Xleft in out 0 CELL\nXright other next 0 EDIT')
        result = compare_instances(data, top='TOP', path_a='TOP/Xleft', path_b='TOP/Xright',
                                   options=Options(matching_mode=mode))
        assert not result['boundary']['a']['scope_complete']
    else:
        result = compare(a, b, top_a='TOP', top_b='TOP', options=Options(matching_mode=mode))
    assert len(result['representative_pair_ids']) == 4
    assert any(p['a'].endswith('/M1') and p['raw_differences'] for p in result['pair_options'])
    for side in ('a', 'b'):
        assert 'ambiguous BJT terminal/model boundary' in result[side]['diagnostics'][0]['message']
        bjt = next(o for o in result[side]['objects'] if o['id'].endswith('/Qamb'))
        assert bjt['parameters'] == [dict(name='raw', value='O I G substrate MaybeModel area={A*2}')]
        assert bjt['connections'] == [] and bjt['resolved_nets'] == {}
        assert bjt['opaque_reason'] == 'unrepresented_connectivity'
        assert result[side]['coverage']['opaque'] == 1
        assert not any(p[side] == bjt['id'] for p in result['pair_options'])


def test_ambiguous_bjt_does_not_poison_large_regional_factor_search():
    from test_budgeted import repeated
    a, b = repeated()
    unknown = from_text('Qamb c base e substrate MaybeModel area=2').top.devices[0]
    a = replace(a, top=replace(a.top, devices=(*a.top.devices, unknown)))
    b = replace(b, top=replace(b.top, devices=(*b.top.devices, unknown)))
    result = compare(a, b, top_a='TOP', top_b='TOP', options=Options(matching_mode='regional'))
    assert len(result['representative_pair_ids']) == 280
    assert result['a']['coverage']['opaque'] == 1
    assert all(h['unmatched_leaves'] == 2 for h in result['partial_alignment']['hypotheses'])
    assert all('TOP/Qamb' not in row for f in result['partial_alignment']['component_permutation_factors']
               for row in f['components'])
