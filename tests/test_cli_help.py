"""The runnable help is an operator contract, not a second static option table."""
import argparse
from dataclasses import fields
import json

import pytest

import netlist_comparison.cli as cli
from netlist_comparison.cli import BUDGET_HELP, build_parser, main, view_parser
from netlist_comparison.model import Options


def rendered_help(call, capsys):
    with pytest.raises(SystemExit) as exc:
        call()
    assert exc.value.code == 0
    return capsys.readouterr().out


def test_main_help_and_guide_cover_operator_decisions(capsys):
    help_text = rendered_help(lambda: main(['--help']), capsys)
    guide = main(['--guide'])
    assert guide == 0
    guide_text = capsys.readouterr().out
    for text in (help_text, guide_text):
        assert '--inspect' in text and '--format' in text and '--path-a' in text
        assert '--black-box-missing' in text and '--matching-mode' in text
    for phrase in ('canonical', 'minimum_raw', 'surplus', 'zero pair rows',
                   'regional hard-admission failure', 'not a proved add/delete',
                   'swap-work-limit', 'Python-only'):
        assert phrase in guide_text


def test_view_help_explains_read_only_architecture_first_filters(capsys):
    text = rendered_help(lambda: main(['view', '--help']), capsys)
    normalized = ' '.join(text.split())
    assert 'no netlist loading or rematching' in normalized
    assert '--omit-parameters' in text and '--group-depth' in text
    assert 'Architecture-first' in text
    assert '--under-a TOP/X1 --under-b TOP/X2 --category wiring' in text
    assert '--parameter W --category raw' in text
    assert 'whole-comparison-scope evidence' in normalized


def test_every_cli_option_has_help_and_exposed_budget_defaults_follow_options():
    for parser in (build_parser(), view_parser()):
        for action in parser._actions:
            if action.option_strings:
                assert action.help and action.help is not argparse.SUPPRESS, action.option_strings
    option_fields = {field.name for field in fields(Options)}
    assert set(BUDGET_HELP) <= option_fields
    defaults = Options()
    for name in BUDGET_HELP:
        action = next(action for action in build_parser()._actions
                      if '--' + name.replace('_', '-') in action.option_strings)
        assert action.default == getattr(defaults, name)


def test_guide_examples_start_with_runnable_local_spice_files(tmp_path, capsys):
    before = tmp_path / 'before.sp'
    after = tmp_path / 'after.sp'
    before.write_text('R1 out 0 1k\n')
    after.write_text('R1 out 0 2k\n')
    assert main([str(before), '--inspect']) == 0
    assert 'TOP:' in capsys.readouterr().out
    assert main([str(before), str(after), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['scope']['top_a'] == 'TOP'


def test_swap_work_limit_is_forwarded_to_options(tmp_path, capsys, monkeypatch):
    before = tmp_path / 'before.sp'
    after = tmp_path / 'after.sp'
    before.write_text('R1 out 0 1k\n')
    after.write_text('R1 out 0 2k\n')
    actual_options = cli.Options
    captured = []

    def options(**kwargs):
        captured.append(kwargs)
        return actual_options(**kwargs)

    monkeypatch.setattr(cli, 'Options', options)
    assert main([str(before), str(after), '--matching-mode', 'regional',
                 '--swap-work-limit', '512', '--json']) == 0
    json.loads(capsys.readouterr().out)
    assert captured[-1]['swap_work_limit'] == 512


def test_large_frontier_option_runs_connected_control(tmp_path, capsys):
    source = tmp_path / 'chain.sp'
    source.write_text('\n'.join(f'X{i} n{i} n{i+1} 0 Cell' for i in range(129)))
    assert main([str(source), str(source), '--black-box-missing', '--matching-mode', 'regional',
                 '--large-frontier-work-limit', '50000', '--json']) == 0
    report = json.loads(capsys.readouterr().out)
    assert report['options']['large_frontier_work_limit'] == 50000
    assert len(report['representative_pair_ids']) == 129
    assert report['partial_alignment']['large_frontier_search']['work_used'] <= 50000
    with pytest.raises(SystemExit) as exc:
        main([str(source), str(source), '--large-frontier-work-limit', '1', '--json'])
    assert exc.value.code == 2
    assert 'requires matching_mode regional' in capsys.readouterr().err
