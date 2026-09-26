from dataclasses import replace
import json

import pytest
from spice_canonical.canonical_netlist import from_text, from_canonical_text
from netlist_comparison import compare, compare_instances, Options
from netlist_comparison.cli import main


@pytest.mark.parametrize('mode', ['fixed', 'regional'])
def test_file_root_is_not_an_available_missing_cell_implementation(mode):
    data = from_text('X1 out TOP gain=1\nR1 out 0 1k\n')
    saved = from_canonical_text(data.render(include_diagnostics=True))
    assert data == saved
    r = compare(data, saved, top_a='TOP', top_b='TOP', options=Options(
        matching_mode=mode, black_box_missing=True))
    leaf = next(o for o in r['a']['objects'] if o['id'] == 'TOP/X1')
    assert leaf['opaque_reason'] is None
    assert leaf['black_box']['cell'] == 'TOP'
    assert len(r['representative_pair_ids']) == 2
    assert not any(p['raw_differences'] for p in r['pair_options'])
    with pytest.raises(ValueError, match='unresolved_definition'):
        compare_instances(saved, top='TOP', path_a='TOP/X1', path_b='TOP/X1')


def test_actual_definition_on_other_side_still_abstains():
    a = from_text('X1 out CELL gain=1\nR1 out 0 1k')
    b = from_text('.subckt CELL p\nRinside p 0 1k\n.ends\nX1 out CELL gain=1\nR1 out 0 1k')
    r = compare(a, b, top_a='TOP', top_b='TOP', options=Options(black_box_missing=True))
    assert next(o for o in r['a']['objects'] if o['id'] == 'TOP/X1')['opaque_reason'] == 'black_box_definition_available_on_one_side'


def test_valid_name_collision_requires_explicit_root_rename(tmp_path, capsys):
    data = from_text('.subckt TOP p\nRinside p 0 1k\n.ends\nX1 out TOP\n')
    saved = from_canonical_text(data.render())
    assert saved == data
    with pytest.raises(ValueError, match='Explicitly rename the file root'):
        compare(saved, saved, top_a='TOP', top_b='TOP')
    path = tmp_path / 'collision.canonical'; path.write_text(saved.render())
    with pytest.raises(SystemExit) as exc:
        main([str(path), str(path), '--format', 'canonical'])
    assert exc.value.code == 2
    assert 'valid canonical input' in capsys.readouterr().err
    # Explicit caller choice: labels/paths change, the declared implementation
    # and call target do not. Both file-root and definition selection then work.
    renamed = replace(saved, top=replace(saved.top, name='FILE_ROOT'))
    path.write_text(renamed.render())
    assert main([str(path), str(path), '--format', 'canonical']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['a']['objects'][0]['id'] == 'FILE_ROOT/X1/Rinside'
    r = compare(renamed, renamed, top_a='TOP', top_b='TOP')
    assert r['a']['objects'][0]['id'] == 'TOP/Rinside'
