"""Extract once; compare saved canonical artifacts without the source deck."""
import json

import pytest

from spice_canonical.canonical_netlist import from_file, main as extract
from netlist_comparison.cli import main


def test_extractor_to_comparator_with_named_external_cells(tmp_path, capsys):
    interfaces = tmp_path / 'pins.json'
    interfaces.write_text(json.dumps({'nmos_lvt': ['d', 'g', 's', 'b'], 'res_cell': ['p', 'n']}))
    artifacts = []
    for side, width in [('a', '1u'), ('b', '3u')]:
        source = tmp_path / f'{side}.sp'
        source.write_text('.include unavailable.inc\n.lib unavailable.lib TT\n'
                          '.subckt AMP I O SCALE=2\n'
                          f'XM O I 0 0 nmos_lvt W={width}\nXR O 0 res_cell R=1k\n.ends\n'
                          'Xamp input output AMP SCALE=3\n')
        target = tmp_path / f'{side}.canonical'
        assert extract([str(source), '--external-subcircuits', str(interfaces),
                        '--include-diagnostics', '--output', str(target)]) == 0
        source.unlink()
        artifacts.append(str(target))
    interfaces.unlink()
    capsys.readouterr()
    assert main(artifacts + ['--format', 'canonical', '--black-box-missing', '--matching-mode', 'regional']) == 0
    report = json.loads(capsys.readouterr().out)
    assert len(report['representative_pair_ids']) == 2
    assert report['a']['black_box_leaf_count'] == 2
    assert report['a']['coverage']['opaque'] == 0
    assert len(report['a']['diagnostics']) == 1
    assert any(p['raw_differences'] == [dict(field='parameters.W', a=['1u'], b=['3u'])]
               for p in report['pair_options'])
    assert main([artifacts[0], '--format', 'canonical', '--inspect']) == 0
    assert 'AMP' in capsys.readouterr().out
    assert main([artifacts[0], '--format', 'canonical', '--path-a', 'TOP/Xamp',
                 '--path-b', 'TOP/Xamp', '--black-box-missing']) == 0
    selected = json.loads(capsys.readouterr().out)
    assert selected['a']['selection']['defaults'] == [dict(name='SCALE', value='2')]


def test_bad_canonical_input_is_actionable_cli_error(tmp_path, capsys):
    bad = tmp_path / 'bad.canonical'
    bad.write_text('DEVICE_TABLE TOP\nwrong columns\n')
    with pytest.raises(SystemExit) as exc:
        main([str(bad), str(bad), '--format', 'canonical'])
    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert 'canonical line' in error and '--format canonical --inspect' in error
