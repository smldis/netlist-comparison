"""Architecture-oriented inspection is a projection, not better correspondence."""
import copy
import json
from pathlib import Path

import pytest
from spice_canonical.canonical_netlist import from_file, from_text
from netlist_comparison import compare, Options, project_saved_report
from netlist_comparison.cli import main


def example():
    folder = Path(__file__).resolve().parents[1] / 'examples'
    return compare(from_file(folder / 'before.sp'), from_file(folder / 'after.sp'), top_a='TOP', top_b='TOP')


def test_mixed_raw_pair_retains_exact_types_and_references_but_not_sizes():
    r = compare(from_text('.model A NMOS\nM1 out in 0 0 A W=1u\nR1 out 0 1k'),
                from_text('.model B PMOS\nM1 out in 0 0 B W=2u\nR1 out 0 1k'), top_a='TOP', top_b='TOP')
    original = copy.deepcopy(r)
    v = project_saved_report(r, omit_parameters=True)
    fields = {d['field'] for p in v['findings']['raw_pairs'] for d in p['raw_differences']}
    assert fields == {'type', 'parameters.model'}
    assert v['counts']['parameter_fields_suppressed_in_path_scope'] == 1
    assert v['counts']['raw_fields']['hidden'] == 1
    assert v['context']['pair_options'] == r['pair_options']
    assert r == original


def test_reference_metadata_and_unknown_nonparameter_fields_are_not_discarded():
    r = example(); p = r['pair_options'][0]
    retained = ['type', 'black_box.cell', 'future_structure', 'parameters.model',
                'parameters.source_type', 'parameters.control', 'parameters.inductor1',
                'parameters.inductor2', 'parameters.raw', 'parameters.unresolved_nets']
    p['raw_differences'] = [dict(field=f, a=['old'], b=['new']) for f in
                            retained + ['parameters.W', 'parameters.series', 'parameters.$order']]
    r['representative_pair_ids'] = [p['id']]
    # Connectivity tokens must still refer to representative pairs.
    r['connectivity']['overlap'] = []
    v = project_saved_report(r, omit_parameters=True)
    assert [d['field'] for d in v['findings']['raw_pairs'][0]['raw_differences']] == retained
    assert v['counts']['parameter_fields_suppressed_in_path_scope'] == 3


def test_parameter_only_rows_disappear_but_membership_defaults_and_overrides_survive(tmp_path, capsys):
    r = example(); before = copy.deepcopy(r)
    v = project_saved_report(r, omit_parameters=True, group_depth=3)
    assert not v['findings']['raw_pairs']
    assert v['counts']['by_category']['raw']['hidden'] > 0
    assert v['context']['hierarchy'] == r['hierarchy']
    assert any(g['a'] == 'TOP/XOLD/XCH' and g['b'] == 'TOP/XMOVED/XCORE/XNEW'
               for g in v['hierarchy_groups'])
    source = tmp_path / 'report.json'; source.write_text(json.dumps(r))
    main(['view', str(source), '--omit-parameters', '--group-depth', '3', '--text'])
    text = capsys.readouterr().out
    assert 'TOP/XOLD/XCH -> TOP/XMOVED/XCORE/XNEW' in text
    assert 'including groups without findings' in text
    assert 'Definition defaults and call overrides are not displayed' in text
    assert 'not a proven split/merge/redesign' in text
    assert r == before


def test_wiring_witnesses_and_unavailable_scope_survive_and_can_be_filtered(tmp_path, capsys):
    a = '.model N NMOS\nM1 out in 0 0 N W=1u\nR1 out 0 1k\nXunknown out 0 ABSENT\n'
    b = a.replace('W=1u', 'W=2u').replace('M1 out in 0 0', 'M1 out in 0 in')
    r = compare(from_text(a), from_text(b), top_a='TOP', top_b='TOP', options=Options(
        matching_mode='regional', component_presentation='minimum_raw'))
    ordinary = project_saved_report(r)
    v = project_saved_report(r, omit_parameters=True)
    assert v['findings']['wiring_partition_rows'] == ordinary['findings']['wiring_partition_rows']
    assert v['findings']['endpoint_witnesses'] == ordinary['findings']['endpoint_witnesses']
    assert v['findings']['endpoint_witnesses']
    assert v['source_scope'] == ordinary['source_scope']
    assert v['findings']['unpaired_objects'] == ordinary['findings']['unpaired_objects']
    assert v['source_scope']['opaque_objects']['a']
    assert not project_saved_report(r, omit_parameters=True, categories=['raw'])['findings']['endpoint_witnesses']
    assert not project_saved_report(r, omit_parameters=True, under_a=['TOP/Xunknown'])['findings']['endpoint_witnesses']
    path = tmp_path / 'report.json'; path.write_text(json.dumps(r))
    main(['view', str(path), '--omit-parameters', '--text'])
    text = capsys.readouterr().out
    assert 'Conditional endpoint witnesses' in text and 'TOP/M1 -> TOP/M1' in text
    assert 'parameters.W' not in text and 'opaque=1' in text


def test_changed_external_cell_stays_unpaired_with_original_identity():
    r = compare(from_text('X1 a b CELL_A W=1u'), from_text('X1 a b CELL_B W=2u'),
                top_a='TOP', top_b='TOP', options=Options(black_box_missing=True))
    v = project_saved_report(r, omit_parameters=True)
    assert v['findings']['unpaired_objects']['a'] and v['findings']['unpaired_objects']['b']
    assert v['source_scope']['black_box_objects']['a'][0]['black_box']['cell'] == 'CELL_A'
    assert v['source_scope']['black_box_objects']['b'][0]['black_box']['cell'] == 'CELL_B'


def test_option_errors_and_self_guiding_help(capsys):
    r = example()
    with pytest.raises(ValueError, match='cannot be combined'):
        project_saved_report(r, omit_parameters=True, parameter='W')
    with pytest.raises(ValueError, match='must be a boolean'):
        project_saved_report(r, omit_parameters=1)
    with pytest.raises(SystemExit) as exc:
        main(['view', '--help'])
    assert exc.value.code == 0
    text = ' '.join(capsys.readouterr().out.split())
    assert '--omit-parameters' in text and 'Does not rematch' in text
    assert 'model/source_type' in text and 'Defaults/overrides' in text
