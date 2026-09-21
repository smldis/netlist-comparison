from spice_canonical.canonical_netlist import from_text
from netlist_comparison import Options, compare_instances, compare
from netlist_comparison import scoped_core as core
from netlist_comparison.operator_scoped import validate_saved_extension
import copy
import json
import time
from dataclasses import replace
import pytest


def compare_text(a,b=None,**kwargs):
    return compare(from_text(a),from_text(a if b is None else b),top_a='TOP',top_b='TOP',
                   options=Options(matching_mode='operator_scoped',**kwargs))


def graph(a, b=None):
    def side(rows):
        return {'objects':[{'cell':cell,'pin_basis':'positional','parameters':[],
                           'nets':{'@1':u,'@2':v}} for cell,u,v in rows],
                'net_count':1+max((n for _,u,v in rows for n in (u,v)),default=-1)}
    return {'a':side(a),'b':side(a if b is None else b)}


SCOPES='''.subckt OLD a b
R1 a mid 1k
C1 mid b 1p
.ends
.subckt NEW a b
Rrenamed a mid 2k
Crenamed mid b 1p
.ends
Xold in out OLD
Xnew other otherout NEW
'''


def test_selected_same_input_changed_parameter_and_certified_quiet():
    data=from_text(SCOPES);opts=Options(matching_mode='operator_scoped')
    quiet=compare_instances(data,top='TOP',path_a='TOP/Xold',path_b='TOP/Xold',options=opts)
    assert quiet['operator_scoped']['certified_internal'] and quiet['operator_scoped']['cards']==[]
    result=compare_instances(data,top='TOP',path_a='TOP/Xold',path_b='TOP/Xnew',options=opts)
    assert result['operator_scoped']['certified_internal']
    assert result['representative_pair_ids']==result['pair_options']==[]
    assert [c['lane'] for c in result['operator_scoped']['cards']]==['parameter_detail']
    assert result['operator_scoped']['charged_count']==6


def test_exact_milp_weighted_and_alternative_optimum():
    g=graph([('r',0,1),('r',0,1)])
    q=core.solve_milp(g,2,3);other=core.solve_milp(g,2,3,forbidden=q['pairs'])
    assert q['status']==other['status']=='optimal'
    assert q['error']==other['error']==0 and q['pairs']!=other['pairs']
    changed=graph([('r',0,1),('r',1,2)],[('r',0,1),('r',0,1)])
    full=core.solve_milp(changed,2,3);weighted=core.solve_milp(changed,None,3)
    assert full['error']==2 and weighted['weighted_cost']==6
    assert full['status']==weighted['status']=='optimal'


def test_zero_and_one_coverage_and_cold_cache():
    for g,k in ((graph([('r',0,1)],[('c',0,1)]),0),(graph([('r',0,1)]),1)):
        q=core.Executor(g,time.monotonic()+3).run()
        assert q['certified'] and q['K']==k
        assert q['weighted']['weighted_cost']==(6 if k==0 else 0)
        assert core.Executor(g,time.monotonic()+3).cache=={}


def test_anonymous_order_transfer_and_corruption():
    g=graph([('r',0,1),('c',1,2),('r',2,3)])
    original=core.Executor(g,time.monotonic()+3).run()
    for seed in (101,202,987):
        h,maps=core.permute(g,seed)
        q=core.Executor(h,time.monotonic()+3).run()['maximum_coverage']
        out=core.transfer(g,h,maps,q)
        assert out['error']==original['maximum_coverage']['error']==0
        bad=copy.deepcopy(h);bad['a']['objects'][0]['cell']='corrupted'
        with pytest.raises(ValueError,match='bijection'):core.transfer(g,bad,maps,q)


def test_incomplete_identity_uses_generic_next_order(monkeypatch):
    g=graph([('r',0,1),('r',1,2)],[('r',0,1),('r',0,1)])
    solve=core.solve_milp;calls=[]
    monkeypatch.setattr(core,'capacity_bound',lambda *_:{'kind':'test_unattainable','lower_bound':-1})
    def controlled(g,k,seconds):
        calls.append(k)
        if len(calls)==1:return {'status':'incomplete','proof':'test_incomplete'}
        return solve(g,k,seconds)
    monkeypatch.setattr(core,'solve_milp',controlled)
    executor=core.Executor(g,time.monotonic()+5);q=executor.search(2)
    assert q['status']=='optimal' and q['error']==2
    assert [a['ordering'] for a in executor.attempts]==[None,101]
    core.validate_witness(g,q,2)


def test_positional_black_boxes_name_blind_and_inventory():
    result=compare_text('Xone a b missing W=1u\n','Xrenamed x y MISSING W=2u\n',black_box_missing=True)
    extension=result['operator_scoped'];window=extension['windows'][0]
    assert extension['certified_internal']
    assert [c['lane'] for c in extension['cards']]==['parameter_detail']
    for side in window['anonymous_input'].values():
        assert set(side['objects'][0])=={'cell','pin_basis','parameters','nets'}
        assert side['objects'][0]['pin_basis']=='positional'
        assert set(side['objects'][0]['nets'])=={'@1','@2'}
    assert 'Xone' not in json.dumps(window['anonymous_input'])
    inventory=compare_text('Xone a b oldcell\n','Xnew x y newcell\n',black_box_missing=True)
    assert inventory['operator_scoped']['windows'][0]['hypotheses']['K']==0
    assert inventory['operator_scoped']['cards'][0]['identity_claim'] is False


def test_case_normalization_and_collision():
    data=from_text('Rone a b 1k\n');circuit=data.top;device=circuit.devices[0]
    changed=replace(device,connections=tuple(replace(c,pin=c.pin.upper()) for c in device.connections))
    other=replace(data,top=replace(circuit,devices=(changed,)))
    result=compare(data,other,top_a='TOP',top_b='TOP',options=Options(matching_mode='operator_scoped'))
    assert result['operator_scoped']['certified_internal'] and not result['operator_scoped']['cards']
    bad=replace(device,connections=(replace(device.connections[0],pin='D'),replace(device.connections[1],pin='d')))
    other=replace(data,top=replace(circuit,devices=(bad,)))
    with pytest.raises(ValueError,match='collision'):
        compare(data,other,top_a='TOP',top_b='TOP',options=Options(matching_mode='operator_scoped'))


def test_scope_and_counterpart_budget_abstain():
    repeated=''.join(f'R{i} a b 1k\n' for i in range(17))
    result=compare_text(repeated)['operator_scoped']
    assert result['status']=='counterpart_budget_abstention' and not result['certified_internal']
    large=''.join(f'R{i} a b 1k\n' for i in range(50))
    assert compare_text(large)['operator_scoped']['status']=='scope_path_budget_abstention'


def test_exterior_separated_and_each_crossing_net_witness_required():
    data=from_text('.subckt BLOCK a b\nR1 a b 1k\n.ends\nXone a b BLOCK\nXtwo c d BLOCK\nRoutside a e 2k\nCoutside b f 1p\n')
    result=compare_instances(data,top='TOP',path_a='TOP/Xone',path_b='TOP/Xtwo',options=Options(matching_mode='operator_scoped'))
    ext=result['operator_scoped'];assert ext['certified_internal']
    assert [c['lane'] for c in ext['cards']]==['environment']
    validate_saved_extension(ext)
    bad=copy.deepcopy(ext);bad['windows'][0]['exterior']['a']['witness_paths'].pop()
    with pytest.raises(ValueError,match='missing exterior witness'):validate_saved_extension(bad)
    bad=copy.deepcopy(ext);bad['cards'][0]['charged_paths']['a'].pop()
    with pytest.raises(ValueError,match='charge'):validate_saved_extension(bad)


def test_two_file_paths_and_composed_split():
    a=from_text('.subckt WHOLE a b\nR1 a mid 1k\nC1 mid b 1p\n.ends\nXold a b WHOLE\n')
    b=from_text('.subckt PART1 a b\nRrenamed a b 1k\n.ends\n.subckt PART2 a b\nCrenamed a b 1p\n.ends\nXleft a bridge PART1\nXright bridge b PART2\n')
    result=compare(a,b,top_a='TOP',top_b='TOP',paths_a=('TOP/Xold',),paths_b=('TOP/Xleft','TOP/Xright'),options=Options(matching_mode='operator_scoped'))
    ext=result['operator_scoped']
    assert ext['certified_internal'] and not ext['cards']
    assert ext['windows'][0]['full_member_scope_charge']==7 and not result['representative_pair_ids']


def test_deadline_is_incomplete_and_configured_minutes_retained(monkeypatch):
    from netlist_comparison import operator_scoped
    original=operator_scoped._execute
    def slow(request):time.sleep(.2);return original(request)
    monkeypatch.setattr(operator_scoped,'_execute',slow)
    stopped=compare_text('R1 a b 1k\n',operator_time_limit=.03)['operator_scoped']
    assert stopped['status']=='deadline_exhausted' and not stopped['certified_internal'] and not stopped['cards']
    monkeypatch.setattr(operator_scoped,'_execute',original)
    real=operator_scoped.Executor
    class CheckDeadline(real):
        def __init__(self,graph,deadline,query_seconds=10):
            assert deadline-time.monotonic()>100
            super().__init__(graph,deadline,query_seconds)
    monkeypatch.setattr(operator_scoped,'Executor',CheckDeadline)
    result=compare_text('R1 a b 1k\n',operator_time_limit=120)['operator_scoped']
    assert result['certified_internal'] and result['resources']['configured_seconds']==120


def test_canonical_cli_and_saved_local_views(tmp_path,capsys):
    from netlist_comparison.cli import main
    from netlist_comparison import project_saved_report
    source=tmp_path/'input.canonical';source.write_text(from_text(SCOPES).render())
    output=tmp_path/'result.json'
    args=[str(source),'--format','canonical','--matching-mode','operator_scoped','--top','TOP',
          '--path-a','TOP/Xold','--path-b','TOP/Xnew','--output',str(output),'--json']
    assert main(args)==0
    saved=json.loads(output.read_text());assert saved['operator_scoped']['certified_internal']
    capsys.readouterr()
    view=project_saved_report(saved,categories=['local'],under_a=['TOP/Xold/R1'])
    assert len(view['findings']['local_cards'])==1
    assert view['findings']['local_cards'][0]['charged_count']==6
    assert view['context']['operator_scoped']['windows'][0]['members']['b']
    assert not project_saved_report(saved,omit_parameters=True)['findings']['local_cards']
    assert main(['view',str(output),'--category','local','--text'])==0
    assert 'parameter' in capsys.readouterr().out
    assert main([str(source),str(source),'--format','canonical','--top-a','TOP','--top-b','TOP',
                 '--path-a','TOP/Xold','--path-b','TOP/Xnew','--matching-mode','operator_scoped','--json'])==0
    assert json.loads(capsys.readouterr().out)['operator_scoped']['certified_internal']
    bad=copy.deepcopy(saved);bad['operator_scoped']['windows'][0]['hypotheses']['maximum_coverage']['error']=99
    with pytest.raises(ValueError,match='witness'):project_saved_report(bad)
    with pytest.raises(SystemExit) as exc:main(['--help'])
    assert exc.value.code==0
    helptext=capsys.readouterr().out
    assert 'operator_scoped' in helptext and '--operator-memory-mib' in helptext


def test_named_blackbox_roles_fold_consistently_and_metadata_is_whitelisted():
    from netlist_comparison.expand import expand
    from netlist_comparison.model import InputScope
    from netlist_comparison.operator_scoped import encode
    data=from_text('Xone a b missing\n');device=data.top.devices[0]
    named=replace(device,black_box=replace(device.black_box,pin_basis='named'),
                  connections=tuple(replace(c,pin=r) for c,r in zip(device.connections,('Drain','Gate'))))
    a=replace(data,top=replace(data.top,devices=(named,)))
    lower=replace(named,connections=tuple(replace(c,pin=c.pin.lower()) for c in named.connections))
    b=replace(data,top=replace(data.top,devices=(lower,)))
    opts=Options(matching_mode='operator_scoped',black_box_missing=True)
    result=compare(a,b,top_a='TOP',top_b='TOP',options=opts)['operator_scoped']
    assert result['certified_internal'] and not result['cards']
    view=expand(a,'TOP',InputScope(),opts);before=encode({'a':view})[0]
    view.leaves[0].black_box.update(secret_identity='never_a_feature',source_path='also_not_a_feature')
    after=encode({'a':view})[0]
    assert before==after and 'never_a_feature' not in json.dumps(after)


def test_parameter_omission_retains_facts_and_weighted_corruption_rejected():
    result=compare_text('R1 a b 1k\n','R9 a b 2k\n',operator_parameters=False)['operator_scoped']
    assert result['certified_internal'] and not result['cards']
    assert result['windows'][0]['parameter_evidence'] and not result['parameter_detail_enabled']
    bad=copy.deepcopy(result);bad['windows'][0]['hypotheses']['weighted']['certificate']['full_cost']=10
    with pytest.raises(ValueError,match='weighted cardinality'):validate_saved_extension(bad)


def test_rewire_card_carries_coverage_sensitivity_and_no_identity():
    result=compare_text('R1 a b 1k\nR2 b c 1k\n','R9 x y 1k\nR8 x y 1k\n')['operator_scoped']
    assert result['certified_internal']
    window=result['windows'][0]
    assert window['coverage_sensitivity']['error_at_K']==2
    assert window['coverage_sensitivity']['error_at_K_minus_1']==0
    assert result['cards'][0]['evidence'][0]['kind']=='necessary_internal_terminal_residual'
    assert not result['cards'][0]['uniqueness_claim']
    validate_saved_extension(result)


def test_memory_stop_and_corrupted_optimality_bound(monkeypatch):
    from netlist_comparison import scoped_runtime
    monkeypatch.setattr(scoped_runtime,'_memory',lambda pid:10**9)
    stopped=compare_text('R1 a b 1k\n')['operator_scoped']
    assert stopped['status']=='memory_budget_exhausted' and not stopped['certified_internal']
    monkeypatch.undo()
    result=compare_text('R1 a b 1k\n')['operator_scoped']
    result['windows'][0]['hypotheses']['weighted']['lower_bound']=-1
    with pytest.raises(ValueError,match='optimality bound'):validate_saved_extension(result)


@pytest.mark.parametrize('tamper', ['extension_certification','extension_status','proof_certification',
    'lane','fabricated_evidence','focus','meaning','window_and_card_evidence','card_removed','channel','alternatives'])
def test_saved_card_semantics_and_certification_are_reconstructed(tamper):
    from netlist_comparison import project_saved_report
    report=compare_text('R1 a b 1k\n','R9 a b 2k\n')
    ext=report['operator_scoped'];card=ext['cards'][0];window=ext['windows'][0]
    if tamper=='extension_certification':ext['certified_internal']=False
    elif tamper=='extension_status':ext['status']='proof_budget_abstention'
    elif tamper=='proof_certification':window['hypotheses']['certified']=False
    elif tamper=='lane':card['lane']='architecture'
    elif tamper=='fabricated_evidence':card['evidence']=[{'kind':'necessary_internal_terminal_residual','value':99}]
    elif tamper=='focus':card['focus_paths']['a']=window['supplied_scopes']['a']
    elif tamper=='meaning':card['evidence'][0]['meaning']='Confirmed identity and edit.'
    elif tamper=='window_and_card_evidence':window['parameter_evidence'][0]['a']={'fabricated':12}
    elif tamper=='card_removed':ext['cards']=[];window['cards']=[];ext['charged_count']=0;ext['charged_paths']={'a':[],'b':[]}
    elif tamper=='channel':card['channel']='environment'
    elif tamper=='alternatives':window['alternatives']=card['alternatives']='Unique confirmed edit.'
    with pytest.raises(ValueError):project_saved_report(report)


def test_saved_architecture_and_environment_semantics_reconstruct():
    for report in (compare_text('R1 a b 1k\n','C9 a b 1p\n'),
                   compare_text('R1 a b 1k\nR2 b c 1k\n','R9 a b 1k\nR8 a b 1k\n')):
        ext=report['operator_scoped'];validate_saved_extension(ext)
        ext['windows'][0]['evidence'][0]['focus']['a']=[]
        with pytest.raises(ValueError,match='evidence/focus'):validate_saved_extension(ext)
    data=from_text('.subckt B a b\nR1 a b 1k\n.ends\nXone a b B\nXtwo c d B\nRoutside a e 2k\n')
    report=compare_instances(data,top='TOP',path_a='TOP/Xone',path_b='TOP/Xtwo',options=Options(matching_mode='operator_scoped'))
    ext=report['operator_scoped'];validate_saved_extension(ext)
    ext['cards'][0]['evidence'][0]['a']=99
    with pytest.raises(ValueError,match='card lane/evidence'):validate_saved_extension(ext)


def test_interface_width_residual_preserves_unrelated_parameter_evidence():
    report=compare_text('Xone a b missing\nRone c d 1k\n','Xnew x y z missing\nRnew u v 2k\n',black_box_missing=True)
    ext=report['operator_scoped'];window=ext['windows'][0]
    assert ext['certified_internal']
    assert [c['lane'] for c in ext['cards']]==['architecture','parameter_detail']
    assert window['hypotheses']['K']==1
    assert window['interface_limitations']['a'] and window['interface_limitations']['b']
    assert not window['admission']['opaque_paths']['a']
    q=window['hypotheses']['maximum_coverage']
    assert all(window['anonymous_input']['a']['objects'][a]['cell'].startswith('primitive:') for a,b in q['pairs'])
    assert window['evidence'][0]['kind']=='literal_inventory_or_interface_residual'
    assert window['parameter_evidence'][0]['kind']=='parameter_multiset_residual'
    validate_saved_extension(ext)


@pytest.mark.parametrize('paths', [('top/xone',),('TOP/%58one',),('TOP/Xone','top/xone','TOP/%58one')])
def test_scope_aliases_deduplicate_before_physical_composition(paths):
    data=from_text('.subckt CELL a b\nR1 a b 1k\n.ends\nXone short short CELL\n')
    opts=Options(matching_mode='operator_scoped')
    original=compare(data,data,top_a='TOP',top_b='TOP',paths_a=('TOP/Xone',),paths_b=('TOP/Xone',),options=opts)['operator_scoped']
    aliased=compare(data,data,top_a='TOP',top_b='TOP',paths_a=paths,paths_b=('TOP/Xone',),options=opts)['operator_scoped']
    assert original['certified_internal'] and aliased['certified_internal']
    assert original['cards']==aliased['cards']==[]
    for key in ('anonymous_input','full_member_scope_charge','members','supplied_scopes','evidence','parameter_evidence'):
        assert original['windows'][0][key]==aliased['windows'][0][key]
    assert aliased['windows'][0]['anonymous_input']['a']['net_count']==2
    validate_saved_extension(aliased)


@pytest.mark.parametrize('name',['model','source_type','raw','unresolved_nets'])
def test_explicit_blackbox_override_names_are_not_filtered_as_metadata(name):
    from spice_canonical.canonical_netlist import Parameter
    data=from_text('Xone a b missing\n');device=data.top.devices[0]
    assert device.black_box is not None
    aa=replace(device,parameters=(Parameter(name,'old'),));bb=replace(device,parameters=(Parameter(name,'new'),))
    a=replace(data,top=replace(data.top,devices=(aa,)));b=replace(data,top=replace(data.top,devices=(bb,)))
    ext=compare(a,b,top_a='TOP',top_b='TOP',options=Options(matching_mode='operator_scoped',black_box_missing=True))['operator_scoped']
    assert ext['certified_internal']
    assert [c['lane'] for c in ext['cards']]==['parameter_detail']
    window=ext['windows'][0]
    assert window['anonymous_input']['a']['objects'][0]['parameters']==[{'name':name,'value':'old'}]
    assert window['anonymous_input']['b']['objects'][0]['parameters']==[{'name':name,'value':'new'}]
    validate_saved_extension(ext)


@pytest.mark.parametrize('number',[float('nan'),float('inf'),-float('inf')])
@pytest.mark.parametrize('query',['weighted','maximum_coverage','one_pair_less'])
def test_direct_saved_validator_rejects_nonfinite_optimality_bounds(number,query):
    ext=compare_text('R1 a b 1k\n')['operator_scoped']
    ext['windows'][0]['hypotheses'][query]['lower_bound']=number
    with pytest.raises(ValueError,match='non-finite'):validate_saved_extension(ext)


@pytest.mark.parametrize('field',['coverage','error','weighted_cost','certificate'])
def test_direct_saved_validator_rejects_nonfinite_objectives_and_certificates(field):
    ext=compare_text('R1 a b 1k\n')['operator_scoped'];q=ext['windows'][0]['hypotheses']['weighted']
    if field=='certificate':q[field]['full_cost']=float('nan')
    else:q[field]=float('nan')
    with pytest.raises(ValueError,match='non-finite'):validate_saved_extension(ext)


def test_separate_budgets_certify_but_omit_over_budget_presentation():
    result=compare_text('R1 a b 1k\nC1 b c 1p\n','R1 a b 2k\nC1 b c 1p\n',
                        operator_retained_paths=200,operator_presentation_paths=4)
    ext=result['operator_scoped'];w=ext['windows'][0]
    assert ext['certified_internal'] and not ext['cards']
    assert w['parameter_evidence'] and w['full_member_scope_charge']==6
    assert w['omitted']==[{'lane':'parameter_detail','reason':'full_support_path_budget'}]
    assert w['admission']['reasons']==[] and w['retention']['internal_within_budget']
    validate_saved_extension(ext)
    from netlist_comparison.terminal import operator_summary
    assert '/4 (maximum 12 cards)' in operator_summary(ext)
    for field in ('charged_paths','retained_paths','nets_per_side'):
        broken=copy.deepcopy(ext);broken['limits'][field]=False
        with pytest.raises(ValueError):validate_saved_extension(broken)
    broken=copy.deepcopy(ext);broken['limits']['charged_paths']=200
    with pytest.raises(ValueError,match='card'):validate_saved_extension(broken)
    broken=copy.deepcopy(ext);broken['windows'][0]['admission']['reasons']=['net_budget_abstention']
    with pytest.raises(ValueError,match='admission'):validate_saved_extension(broken)
    broken=copy.deepcopy(ext);broken['windows'][0]['retention']['internal_context_paths']=2
    with pytest.raises(ValueError):validate_saved_extension(broken)


def test_all_admission_failures_retained_without_truncation():
    ext=compare_text('R1 a b 1k\nR2 b c 1k\n',operator_max_leaves=1,operator_max_nets=1,
                     operator_max_counterparts=1,operator_retained_paths=3,operator_presentation_paths=3)['operator_scoped']
    w=ext['windows'][0]
    assert ext['status']=='scope_path_budget_abstention' and not ext['certified_internal']
    assert w['admission']['reasons']==['scope_path_budget_abstention','leaf_budget_abstention',
                                     'net_budget_abstention','counterpart_budget_abstention']
    assert len(w['anonymous_input']['a']['objects'])==2 and not w['hypotheses']
    validate_saved_extension(ext)


def test_old_defaults_and_legacy_saved_extension():
    from netlist_comparison.operator_scoped import LIMITS,limits_for
    assert limits_for(Options())=={**LIMITS,'retained_paths':100}
    ext=compare_text('R1 a b 1k\n')['operator_scoped']
    old=copy.deepcopy(ext);old['schema_version']=1;old['limits']=dict(LIMITS)
    for w in old['windows']:
        w.pop('retention');w['admission'].pop('observed');w['admission'].pop('reasons')
    validate_saved_extension(old)
    assert ext['certified_internal'] and not ext['cards']
    budget=compare_text('R1 a b 1k\n',operator_max_nets=1)['operator_scoped']
    assert budget['status']=='domain_budget_abstention' and not budget['certified_internal']
    validate_saved_extension(budget)


@pytest.mark.parametrize('field,value', [('operator_max_leaves',0),('operator_max_nets',True),
    ('operator_max_counterparts',1.5),('operator_retained_paths',-1),('operator_presentation_paths',101),
    ('operator_max_cards',0),('operator_query_seconds',float('nan')),('operator_query_seconds',float('inf'))])
def test_invalid_separate_budget_options(field,value):
    with pytest.raises(ValueError):Options(**{field:value})


def test_configured_query_cap_and_model_instrumentation(monkeypatch):
    g=graph([('r',0,1)],[('r',0,0)])
    original=core.solve_milp;calls=[]
    def recorded(graph,coverage,seconds,forbidden=None):
        calls.append(seconds);return original(graph,coverage,seconds,forbidden)
    monkeypatch.setattr(core,'solve_milp',recorded)
    executor=core.Executor(g,time.monotonic()+5,query_seconds=.4)
    proof=executor.search(None)
    assert proof['status']=='optimal' and calls and all(0<x<=.4 for x in calls)
    native=[a for a in executor.attempts if a['model']]
    assert native and native[0]['model']['variables']>0 and native[0]['assembly_seconds']>=0


def test_scaling_cli_help_and_json(tmp_path,capsys):
    from netlist_comparison.cli import main
    with pytest.raises(SystemExit) as done:main(['--help'])
    assert done.value.code==0
    helptext=capsys.readouterr().out
    for flag in ('--operator-nets','--operator-retained-paths','--operator-presentation-paths','--operator-query-seconds'):
        assert flag in helptext
    a=tmp_path/'a.sp';b=tmp_path/'b.sp'
    a.write_text('R1 a b 1k\n');b.write_text('R1 a b 2k\n')
    assert main([str(a),str(b),'--top-a','TOP','--top-b','TOP','--matching-mode','operator_scoped',
                 '--operator-nets','96','--operator-retained-paths','200','--operator-presentation-paths','2',
                 '--operator-query-seconds','5','--json'])==0
    result=json.loads(capsys.readouterr().out)
    assert result['operator_scoped']['limits']['nets_per_side']==96
    assert result['operator_scoped']['certified_internal'] and not result['operator_scoped']['cards']
    validate_saved_extension(result['operator_scoped'])


def test_explicit_batch_reuses_only_immutable_preparation_and_matches_cold_reports():
    from netlist_comparison import compare_operator_scoped_batch
    data=from_text('.subckt B a b\nR1 a m 1k\nC1 m b 1p\n.ends\n'
                   'Xone a b B\nXtwo c d B\nRoutside a e 2k\n')
    options=Options(matching_mode='operator_scoped')
    windows=[{'paths_a':('TOP/Xone',),'paths_b':('TOP/Xtwo',)},
             {'paths_a':('TOP/Xtwo',),'paths_b':('TOP/Xone',)}]
    batch=compare_operator_scoped_batch(data,data,top_a='TOP',top_b='TOP',windows=windows,
                                        options=options)
    assert batch['kind']=='operator_scoped_batch_v1' and not batch['resources']['incomplete']
    assert batch['reuse']['scope']=='this_batch_only' and batch['reuse']['window_count']==2
    assert 0<batch['resources']['serialized_result_bytes']<=batch['resources']['serialized_result_limit_bytes']
    for index,(window,actual) in enumerate(zip(windows,batch['results'])):
        cold=compare(data,data,top_a='TOP',top_b='TOP',options=options,**window)
        for report in (cold,actual):
            report['metrics']['seconds']={}
            report['operator_scoped']['resources']={}
        assert actual==cold
        validate_saved_extension(batch['results'][index]['operator_scoped'])


def test_batch_reuse_key_invalidates_with_input_scope_and_options():
    from netlist_comparison import compare_operator_scoped_batch
    from netlist_comparison.model import InputScope
    base=from_text('R1 a b 1k\n');changed=from_text('R1 a b 2k\n')
    windows=[{'paths_a':(),'paths_b':()}]
    def key(a=base,b=base,scope=InputScope(),options=Options(matching_mode='operator_scoped')):
        return compare_operator_scoped_batch(a,b,top_a='TOP',top_b='TOP',windows=windows,
                                             options=options,scope_a=scope,scope_b=scope)['reuse']['key_sha256']
    original=key()
    assert key(b=changed)!=original
    assert key(scope=InputScope(global_nets=('a',)))!=original
    assert key(options=Options(matching_mode='operator_scoped',operator_max_nets=65))!=original
    with pytest.raises(ValueError,match='contains only'):
        compare_operator_scoped_batch(base,base,top_a='TOP',top_b='TOP',windows=[{'paths_a':(),'label':'x'}])
