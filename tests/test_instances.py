import json
import subprocess
from pathlib import Path

import pytest
from spice_canonical.canonical_netlist import from_text
from netlist_comparison import compare_instances, InputScope, Options


CELL = '''.subckt CELL A B U W=2u
R1 A mid W
C1 mid B 1p
.ends
X1 in out spare CELL W=3u
X2 other other spare2 CELL W={K*2}
'''


def run(text=CELL, **kwargs):
    return compare_instances(from_text(text), top='TOP', path_a=kwargs.pop('path_a', 'TOP/X1'),
                             path_b=kwargs.pop('path_b', 'TOP/X2'), **kwargs)


def test_bindings_overrides_aliases_are_context_not_internal_edits():
    result = run()
    a, b = result['boundary']['a'], result['boundary']['b']
    assert a['aliases'] == []
    assert b['aliases'] == [{'net': 'local:TOP:other', 'formals': ['A', 'B']}]
    assert a['pins'][2]['internally_unused'] is True
    assert result['a']['selection']['defaults'] == [{'name': 'W', 'value': '2u'}]
    assert result['b']['selection']['overrides'] == [{'name': 'W', 'value': '{K*2}'}]
    assert len(result['representative_pair_ids']) == 2
    assert all(not p['raw_differences'] for p in result['pair_options'])
    assert all(not r['a_partitioned_across_b'] for r in result['connectivity']['overlap'])
    r1 = next(o for o in result['b']['objects'] if o['id'].endswith('/R1'))
    assert r1['resolved_nets']['p'] == 'local:TOP:other'
    candidates = [p for h in result['boundary']['hypotheses'] for p in h['pin_candidates']]
    assert {(p['a'], p['b']) for p in candidates} == {('A', 'A'), ('B', 'B')}
    assert all(not p['outer_net_equal'] for p in candidates)
    json.dumps(result, allow_nan=False)


def test_renamed_permuted_ports_with_real_edit_and_added_unused_port():
    text = CELL.split('X1')[0] + '''.subckt SPECIAL Z Y EXTRA IDLE W=9u
Rnew Y mid W
Cnew mid Z 9p
.ends
X1 in out spare CELL W=3u
X2 out2 in2 extra idle SPECIAL W=4u
'''
    result = run(text)
    candidates = [p for h in result['boundary']['hypotheses'] for p in h['pin_candidates']]
    assert {(p['a'], p['b']) for p in candidates} == {('A', 'Y'), ('B', 'Z')}
    assert any(p['raw_differences'] for p in result['pair_options'])
    assert result['boundary']['formal_count_delta_b_minus_a'] == 1
    assert [p['formal'] for p in result['boundary']['b']['pins'] if p['internally_unused']] == ['EXTRA', 'IDLE']


def test_ancestor_resolution_globals_same_path_and_overlap():
    text = CELL.split('X1')[0] + '''.subckt WRAP P Q
Xdeep P Q VDD CELL
.ends
Xouter input 0 WRAP
'''
    result = run(text, path_a='top/xouter/xdeep', path_b='TOP/Xouter/Xdeep',
                 scope=InputScope(('0', 'VDD'), True))
    assert result['a']['selection']['path'] == 'TOP/Xouter/Xdeep'
    pins = result['boundary']['a']['pins']
    assert [p['resolved_parent_net'] for p in pins] == ['local:TOP:input', 'global:0', 'global:vdd']
    assert [p['global'] for p in pins] == [False, True, True]
    overlap = run(text, path_a='TOP/Xouter', path_b='TOP/Xouter/Xdeep')
    assert len(overlap['a']['objects']) == len(overlap['b']['objects']) == 2


def test_escaping_and_case_are_unambiguous():
    text = CELL.replace('X1 in', 'X/a% in')
    result = run(text, path_a='top/x%2Fa%25')
    assert result['a']['selection']['path'] == 'TOP/X%2Fa%25'
    for path in ('TOP/X/a%', 'TOP/X%QQ', 'TOP//X2', 'TOP', '/TOP/X2', 'WRONG/X2', 'TOP/no'):
        with pytest.raises(ValueError):
            run(text, path_a=path)
    with pytest.raises(ValueError, match='repeats device'):
        run(CELL + '\nx1 a b c CELL')
    with pytest.raises(ValueError, match='primitives'):
        run(path_a='TOP/X1/R1')


def test_unrelated_population_does_not_spend_selected_budget():
    text = CELL + '\n' + '\n'.join(f'Xearly{i} a b c CELL' for i in range(100))
    result = run(text, options=Options(max_objects=3))
    assert result['a']['expansion_complete']
    assert len(result['a']['objects']) == 2
    truncated = run(text, options=Options(max_objects=1))
    assert not truncated['a']['expansion_complete']
    assert truncated['a']['unresolved'][0]['reason'] == 'expansion_budget'
    assert all(p['internally_unused'] is None for p in truncated['boundary']['a']['pins'])


def test_opaque_selection_is_rejected_and_opaque_descendants_retained():
    with pytest.raises(ValueError, match='unresolved_definition'):
        run('X1 a b MISSING\nX2 a b MISSING')
    text = CELL.replace('R1 A mid W', 'Xbad A mid MISSING')
    result = run(text)
    assert result['a']['unresolved'][0]['reason'] == 'unresolved_definition'
    assert not result['boundary']['a']['scope_complete']


def test_internal_twins_and_symmetric_ports_keep_ambiguity():
    text = '''.subckt CELL A B
R1 A n 1k
R2 A n 2k
C1 n B 1p
.ends
X1 a b CELL
X2 c d CELL
'''
    result = run(text, options=Options(matching_mode='regional'))
    assert any(len(r['a']) > 1 for r in result['boundary']['internal_ambiguity']['inspection_regions'])
    # Two identical branches permit a swap of their boundary pins.
    text = '''.subckt CELL A B G
R1 A G 1k
C1 A G 1p
R2 B G 1k
C2 B G 1p
.ends
X1 a b 0 CELL
X2 c d 0 CELL
'''
    result = run(text, options=Options(matching_mode='regional'))
    mappings = {(p['a'], p['b']) for h in result['boundary']['hypotheses'] for p in h['pin_candidates']}
    assert {('A', 'A'), ('A', 'B'), ('B', 'A'), ('B', 'B')} <= mappings


def test_installed_cli(tmp_path):
    source = tmp_path / 'full.sp'
    source.write_text(CELL)
    executable = Path(__file__).resolve().parents[2] / '.venv/bin/netlist-compare'
    proc = subprocess.run([str(executable), str(source), '--top', 'TOP', '--path-a', 'TOP/X1',
                           '--path-b', 'TOP/X2'], check=True, text=True, capture_output=True)
    assert json.loads(proc.stdout)['a']['selection']['path'] == 'TOP/X1'


def test_deep_selection_uses_ancestor_bindings_but_subtree_depth_budget():
    text = '.subckt LEAF A B\nR1 A n 1k\nC1 n B 1p\n.ends\n'
    for i in range(8):
        target = 'LEAF' if i == 0 else f'W{i-1}'
        text += f'.subckt W{i} P Q\nXnext P Q {target}\n.ends\n'
    text += 'X1 source 0 W7\nX2 other 0 W7\n'
    suffix = '/Xnext' * 8
    result = run(text, path_a='TOP/X1' + suffix, path_b='TOP/X2' + suffix,
                 options=Options(max_objects=3, max_depth=1))
    assert len(result['a']['objects']) == 2
    assert result['a']['selection']['physical_bindings']['a'] == 'local:TOP:source'
    assert len(result['a']['selection']['ancestor_calls']) == 9
    truncated = run(text, options=Options(max_depth=1))
    assert truncated['a']['unresolved'][0]['reason'] == 'depth_budget'


def test_invalid_actual_call_binding_is_not_replaced_by_its_definition():
    from dataclasses import replace
    data = from_text(CELL)
    invalid = replace(data.top.devices[0], connections=data.top.devices[0].connections[:-1])
    data = replace(data, top=replace(data.top, devices=(invalid, data.top.devices[1])))
    with pytest.raises(ValueError, match='invalid_call_bindings'):
        compare_instances(data, top='TOP', path_a='TOP/X1', path_b='TOP/X2')


def test_declared_global_and_same_spelling_local_have_distinct_scope():
    text = CELL.replace('R1 A mid W', 'R1 A VDD W').replace('C1 mid B', 'C1 VDD B')
    local = run(text)
    global_ = run(text, scope=InputScope(('VDD',), True))
    assert local['a']['objects'][0]['resolved_nets']['p'] == 'local:TOP/X1:vdd'
    assert global_['a']['objects'][0]['resolved_nets']['p'] == 'global:vdd'
    assert global_['scope']['global_net_declarations_complete'] is True
