import json

import pytest
from spice_canonical.canonical_netlist import from_text
from netlist_comparison import Options, InputScope, compare, project_saved_report
from netlist_comparison.blackbox import compatible, reconcile
from netlist_comparison.expand import expand
from netlist_comparison.exchange import challenge
from netlist_comparison.regional import net_alignment
from netlist_comparison.cli import main, view_summary


def views(left, right):
    options = Options(black_box_missing=True)
    a, b = [expand(from_text(text), 'TOP', InputScope(), options) for text in (left, right)]
    reconcile(a, b)
    return a, b


def test_occupied_chain_crosses_renamed_reorganized_hierarchy():
    a, b = views('Xold a b 0 Cell\nXnext b c 0 Cell\nXend c d 0 Cell',
                 '.subckt Wrap p q r s\nXrenamed p q 0 Cell\nXtail r s 0 Cell\n.ends\n'
                 'Xnew u v w x Wrap\nXmiddle v w 0 Cell\nXextra z y 0 Cell')
    # Wrong incumbent uses the disconnected extra, and steals the last leaf's
    # intended occupied counterpart. A two-step alternating exchange repairs it.
    initial = [(0, 0), (1, 3), (2, 2)]
    initial_error = net_alignment(a, b, initial)[0]
    plans, evidence = challenge(a, b, [initial], work_limit=128)
    assert evidence['best_endpoint_disagreements'] < initial_error
    assert any(len(w['added_pairs']) >= 2 for w in evidence['witnesses'])
    assert evidence['challenges'][0]['occupied_candidates'] == 3
    for plan in plans:
        assert len(plan) == len({i for i,j in plan}) == len({j for i,j in plan}) == 3
        assert all(compatible(a.leaves[i], b.leaves[j]) for i,j in plan)
    # Reverse orientation must also challenge occupied candidates.
    reversed_plans, reverse = challenge(b, a, [[(j,i) for i,j in initial]], work_limit=128)
    assert reverse['best_score'] == evidence['best_score']
    assert reversed_plans


def test_symmetric_external_surplus_is_joint_and_saved_view_visible():
    a = from_text('X1 a 0 RC\nX2 a 0 RC')
    b = from_text('Xred z 0 RC\nXgreen z 0 RC\nXblue z 0 RC')
    report = compare(a, b, top_a='TOP', top_b='TOP',
                     options=Options(matching_mode='regional', black_box_missing=True, omission_work_limit=128))
    assert report['b']['coverage']['ambiguous'] == 3
    population = report['population_evidence']['groups']
    assert len(population) == 1 and population[0]['represented_surplus'] == 1
    assert population[0]['count_a'] == 2 and population[0]['count_b'] == 3
    pairs = {p['id']:p for p in report['pair_options']}
    omissions = {tuple(sorted(set(o['id'] for o in report['b']['objects']) -
                             {pairs[i]['b'] for i in h})) for h in report['groups'][0]['hypotheses']}
    assert len(omissions) == 3
    view = project_saved_report(report, categories=['unpaired'], under_b=['TOP/Xred'])
    assert view['counts']['by_category']['unpaired']['shown'] == 0
    assert view['findings']['population_groups'] == population
    text = view_summary(view, 4)
    assert 'represented surplus 1 jointly' in text
    assert 'whole comparison scope' in text
    assert 'conditional margin=0.0' in text


def test_budget_and_empty_frontier_do_not_establish_additions():
    a, b = views('X1 a b 0 Cell\nX2 b c 0 Cell', 'X1 u v 0 Cell\nX2 v w 0 Cell\nX3 w x 0 Cell')
    initial = [[(0,0),(1,1)]]
    plans, evidence = challenge(a, b, initial, work_limit=1)
    assert plans == initial
    assert evidence['work_used'] == 1 and evidence['stop'] == 'work_limit'
    assert evidence['challenges'][0]['best_participating_score'] is None
    flat = from_text('\n'.join(f'X{k} n{k} n{k+1} 0 Cell W=1u' for k in range(129)))
    report = compare(flat, flat, top_a='TOP', top_b='TOP', options=Options(
        matching_mode='regional', black_box_missing=True, omission_work_limit=128))
    assert not report['representative_pair_ids']
    assert report['partial_alignment']['stop'] == 'no_populated_frontier'
    assert report['partial_alignment']['omission_search']['stop'] == 'no_populated_incumbent'
    assert not report['population_evidence']['groups']


def test_incompatible_external_identity_and_interface_stay_opaque():
    a = from_text('X1 a b c 0 Cell\nX2 a 0 RC')
    b = from_text('X1 a b 0 Cell\nX2 a 0 RC\nX3 a 0 DifferentRC')
    report = compare(a, b, top_a='TOP', top_b='TOP', options=Options(
        matching_mode='regional', black_box_missing=True, omission_work_limit=128))
    assert report['a']['coverage']['opaque'] == report['b']['coverage']['opaque'] == 1
    assert all(p['a'] != 'TOP/X1' and p['b'] not in ('TOP/X1', 'TOP/X3') for p in report['pair_options'])
    assert report['population_evidence']['opaque_excluded_a'] == 1
    assert report['partial_alignment']['omission_search']['challenges'][0]['compatible_candidates'] == 0
    assert any(o.get('opaque_reason') == 'incompatible_black_box_interfaces' for o in report['a']['objects'])


def test_api_and_cli_switch_validation_and_saved_output(tmp_path, capsys):
    with pytest.raises(ValueError, match='requires matching_mode'):
        Options(omission_work_limit=1)
    for invalid in (-1, True, 1.5):
        with pytest.raises(ValueError, match='nonnegative integer'):
            Options(matching_mode='regional', omission_work_limit=invalid)
    a, b, out = [tmp_path / s for s in ('a.sp','b.sp','report.json')]
    a.write_text('X1 a 0 RC\nX2 a 0 RC')
    b.write_text(a.read_text() + '\nX3 a 0 RC')
    assert main([str(a), str(b), '--black-box-missing', '--matching-mode', 'regional',
                 '--omission-work-limit', '16', '--output', str(out), '--json']) == 0
    saved = json.loads(out.read_text())
    assert saved['partial_alignment']['omission_search']['work_used'] <= 16
    assert main(['view',str(out),'--category','unpaired','--text']) == 0
    assert 'represented surplus 1 jointly' in capsys.readouterr().out


def test_work_counter_includes_seeds_and_retention_prefers_omission_diversity(monkeypatch):
    import netlist_comparison.regional as regional
    a, b = views('X1 a 0 RC\nX2 a 0 RC', 'X1 z 0 RC\nX2 z 0 RC\nX3 z 0 RC')
    original = regional.net_alignment
    calls = []
    def counted(*args):
        calls.append(1)
        return original(*args)
    monkeypatch.setattr(regional, 'net_alignment', counted)
    plans, evidence = challenge(a, b, [[(0,0),(1,1)]], work_limit=4)
    assert len(calls) == evidence['work_used'] == 4
    assert evidence['baseline_tied_exchanges']
    assert {tuple(sorted({0,1,2} - {j for i,j in p})) for p in plans} == {(0,), (1,), (2,)}


def test_search_admission_and_population_do_not_count_hidden_internals():
    text = '\n'.join(f'X{k} a 0 RC' for k in range(67))
    a, b = views('Xold a 0 RC', text)
    _, search = challenge(a, b, [[(0,0)]], work_limit=32)
    assert search['stop'] == 'omission_admission_limit' and search['work_used'] == 0
    a, b = views('Xold a 0 RC', 'Xnew z 0 RC')
    _, search = challenge(a, b, [[(0,0)]], work_limit=32)
    assert search['stop'] == 'no_supported_omission' and search['work_used'] == 0


def test_terminal_deduplicates_shared_witness_budget_and_readable_domains():
    from copy import deepcopy
    from netlist_comparison.terminal import omission_summary
    def witness(name, score, selected=False):
        return dict(removed_pairs=[['A/'+name,'B/old']], added_pairs=[['A/'+name,'B/new']],
                    score=score, score_delta=score-3.6, selected=selected)
    improved=witness('improved',1.6,True)
    participation=witness('participation',2.6)
    alternative=witness('alternative',3.6)
    search=dict(stop='depth_limit', work_used=12, work_limit=20,baseline_score=3.6,best_score=1.6,
                witnesses=[alternative,improved],baseline_tied_exchanges=[participation,alternative],
                challenges=[dict(side='b',object='B/new',occupied_candidates=2,compatible_candidates=2,
                    best_participating_score=2.6,best_omitted_score=1.6,participation_margin=1.,
                    participating_witness=participation)])
    population=dict(groups=[dict(domain='["rc", "positional", ["@1", "@2"]]', count_a=2,count_b=3,
                    surplus_side='b',represented_surplus=1,selected_omissions_a=0,selected_omissions_b=1)])
    before=deepcopy((population,search))
    text='\n'.join(omission_summary(population,search,2))
    assert 'rc (positional, 2 pins)' in text and '["rc"' not in text
    assert text.count('release A/improved') == text.count('release A/participation') == 1
    assert 'release A/alternative' not in text
    assert text.index('release A/improved') < text.index('release A/participation')
    assert '1 distinct exchange witnesses omitted; see full JSON' in text
    assert 'Distinct coupled exchange witnesses: 3; showing 2.' in text
    assert (population,search)==before
