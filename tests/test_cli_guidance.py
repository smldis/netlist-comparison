"""Operator journeys: discover scope, compare, inspect uncertainty, recover errors."""
import json
import sys
from pathlib import Path

import pytest

from netlist_comparison.cli import main


EXAMPLES = Path(__file__).resolve().parents[1] / 'examples'


def examples():
    return [str(EXAMPLES / 'before.sp'), str(EXAMPLES / 'after.sp')]


def deck(tmp_path, text, name='design.sp'):
    path = tmp_path / name
    path.write_text(text)
    return str(path)


def test_startup_is_a_successful_quickstart(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert 'before.sp after.sp' in out and '--inspect' in out and '--path-a' in out
    assert 'Exit status' in out and '--help' in out


def test_help_explains_all_compute_controls(capsys):
    with pytest.raises(SystemExit) as exc:
        main(['--help'])
    assert exc.value.code == 0
    out = ' '.join(capsys.readouterr().out.split())
    assert 'NOT a time or RAM cap' in out
    assert 'default: 50000' in out
    assert '--format' in out and '--global-net' in out


def test_two_file_short_form_preserves_json_pipeline(capsys):
    assert main(examples()) == 0
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    assert report['scope']['top_a'] == 'TOP'
    assert report['options']['matching_mode'] == 'fixed'
    assert captured.err == ''


def test_terminal_summary_and_explicit_json(monkeypatch, capsys):
    monkeypatch.setattr(sys.stdout, 'isatty', lambda: True)
    main(examples())
    out = capsys.readouterr().out
    assert 'TOP/XOLD/XCH/M1' in out and "['6u']" in out
    assert 'does not establish equivalence' in out
    main(examples() + ['--json'])
    assert json.loads(capsys.readouterr().out)['schema_version'] == 1


def test_saved_full_report_and_readable_preview(tmp_path, capsys):
    output = tmp_path / 'report.json'
    main(examples() + ['--output', str(output), '--limit', '1'])
    captured = capsys.readouterr()
    assert captured.out == '' and 'Full JSON saved to:' in captured.err
    assert len(json.loads(output.read_text())['representative_pair_ids']) == 4
    main(examples() + ['--output', str(output), '--json'])
    captured = capsys.readouterr()
    assert not captured.out and not captured.err


def test_definition_only_file_selects_sole_definition(tmp_path, capsys):
    path = deck(tmp_path, '.subckt AMP A B\nR1 A B 1k\n.ends\n')
    main([path, path])
    assert json.loads(capsys.readouterr().out)['scope']['top_a'] == 'AMP'


def test_multiple_definitions_require_explicit_scope_and_inspect_recovers(tmp_path, capsys):
    path = deck(tmp_path, '.subckt AMP A B\nR1 A B 1k\n.ends\n.subckt BUF A B\nR2 A B 2k\n.ends\n')
    with pytest.raises(SystemExit) as exc:
        main([path, path])
    assert exc.value.code == 2
    error = capsys.readouterr().err
    assert '--top-a CIRCUIT' in error and 'AMP, BUF' in error
    main([path, '--inspect'])
    out = capsys.readouterr().out
    assert 'AMP: 1 devices' in out and '--inspect --top CIRCUIT' in out
    main([path, path, '--top-a', 'amp', '--top-b', 'BUF'])
    assert json.loads(capsys.readouterr().out)['scope']['top_a'] == 'AMP'


def test_discover_escaped_paths_then_compare_calls(tmp_path, capsys):
    path = deck(tmp_path, '.subckt CELL A B\nR1 A B 1k\n.ends\nX/a in 0 CELL\nXb out 0 CELL\n')
    main([path, '--inspect'])
    out = capsys.readouterr().out
    assert 'TOP/X%2Fa' in out and 'TOP/Xb' in out
    main([path, '--path-a', 'TOP/X%2Fa', '--path-b', 'TOP/Xb', '--text'])
    out = capsys.readouterr().out
    assert 'Instances: TOP/X%2Fa -> TOP/Xb' in out and 'Pin correspondence' in out


def test_incomplete_inputs_stay_visible_in_inspection_and_text(tmp_path, capsys):
    path = deck(tmp_path, '.include missing.inc\nR1 a 0 1k\nXmissing a 0 Absent\n')
    main([path, '--inspect'])
    out = capsys.readouterr().out
    assert 'unresolved_definition' in out and 'missing.inc' in out
    main([path, path, '--text'])
    out = capsys.readouterr().out
    assert 'opaque=1' in out and 'TOP/Xmissing' in out and 'missing.inc' in out


@pytest.mark.parametrize('extra,expected', [
    (['--top-a', 'NONEXISTENT'], 'Available circuits:'),
    (['--context-mode', 'frozen_neighbors', '--matching-mode', 'regional'], 'omit --context-mode'),
    (['--max-objects', '0'], 'at least 1'),
    (['--regional-work-limit', '-2'], 'at least 1'),
    (['--max-alternative-checks', '-1'], 'at least 0'),
    (['--limit', 'zero'], 'must be an integer'),
])
def test_errors_explain_recovery(extra, expected, capsys):
    with pytest.raises(SystemExit) as exc:
        main(examples() + extra)
    assert exc.value.code == 2
    assert expected in capsys.readouterr().err


def test_one_file_and_half_instance_selection_are_actionable(capsys):
    for args in ([examples()[0]], [examples()[0], '--path-a', 'TOP/XOLD']):
        with pytest.raises(SystemExit) as exc:
            main(args)
        assert exc.value.code == 2
        assert '--path-b' in capsys.readouterr().err


def test_output_cannot_replace_input(tmp_path, capsys):
    path = deck(tmp_path, 'R1 a 0 1k\n')
    before = Path(path).read_bytes()
    with pytest.raises(SystemExit) as exc:
        main([path, path, '--output', path])
    assert exc.value.code == 2
    assert 'different from the input' in capsys.readouterr().err
    assert Path(path).read_bytes() == before


def test_missing_file_and_output_directory_are_actionable(tmp_path, capsys):
    with pytest.raises(SystemExit):
        main([str(tmp_path/'missing.sp'), '--inspect'])
    assert 'Cannot read netlist file' in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(examples() + ['--output', str(tmp_path/'missing/report.json')])
    assert 'output directory exists' in capsys.readouterr().err


def test_inspection_bounds_are_explicit(tmp_path, capsys):
    path = deck(tmp_path, '.subckt C A B\nR1 A B 1k\n.ends\nXa a 0 C\nXb b 0 C\n')
    main([path, '--inspect', '--max-objects', '2', '--limit', '1'])
    out = capsys.readouterr().out
    assert 'within budget: False' in out and 'expansion_budget' in out
    assert 'more not displayed' in out
