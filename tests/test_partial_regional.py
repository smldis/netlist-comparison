from dataclasses import replace
import importlib.util
from pathlib import Path

from spice_canonical.canonical_netlist import from_text
from netlist_comparison import compare,Options

HERE=Path(__file__).resolve().parents[1]/'examples'


def test_small_body_and_type_edits_need_no_exact_seeds():
    text=(HERE/'before.sp').read_text();a=from_text(text)
    for changed in (text.replace('M1 OUT IN T VSS','M1 OUT IN T IN'),
                    text.replace('.model N NMOS','.model N NMOS\n.model P PMOS').replace('M1 OUT IN T VSS N','M1 OUT IN T VSS P')):
        r=compare(a,from_text(changed),top_a='TOP',top_b='TOP',options=Options(matching_mode='regional'))
        assert len(r['representative_pair_ids'])==4
        region=next(x for x in r['inspection_regions'] if 'TOP/XOLD/XCH/M1' in x['a'])
        assert region['b']==['TOP/XOLD/XCH/M1']
        assert sum(r['a']['coverage'].values())==4
        assert any(p['raw_differences'] or any(t['raw_binding_differs'] for t in p['terminals']) for p in r['pair_options'])


def test_exact_twins_cannot_become_singletons_through_lap_tie_order():
    a=from_text('R1 a 0 1k\nR2 a 0 2k\nC1 a 0 1p')
    r=compare(a,a,top_a='TOP',top_b='TOP',options=Options(matching_mode='regional'))
    region=next(x for x in r['inspection_regions'] if 'TOP/R1' in x['a'])
    assert set(region['b'])=={'TOP/R1','TOP/R2'}
    assert r['a']['coverage']['ambiguous']==2


def test_chain_fragment_orders_are_coupled_and_names_do_not_rank_them():
    spec=importlib.util.spec_from_file_location('scale_fixture',HERE/'evaluate.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    a,b,ledger=module.stress_fixture(5)
    b=replace(b,top=replace(b.top,devices=tuple(d for d in b.top.devices if d.name!='RzLINK1')))
    r=compare(a,b,top_a='TOP',top_b='TOP_v2',options=Options(matching_mode='regional'))
    hypotheses=r['groups'][0]['hypotheses'];p={x['id']:x for x in r['pair_options']}
    assert len(hypotheses)==2
    for h in hypotheses:
        assert len(h)==233
        assert len({p[i]['a'] for i in h})==len({p[i]['b'] for i in h})==len(h)
    assert not r['partial_alignment']['names_used']
    edited='TOP/XB0/XL/XL/XL/M1'
    region=next(x for x in r['inspection_regions'] if edited in x['a'])
    assert len(region['b'])==2 and ledger[edited] in region['b']


def test_qap_size_budget_and_opaque_inputs_abstain_with_accounting():
    a=from_text('X1 a b MISSING')
    r=compare(a,a,top_a='TOP',top_b='TOP',options=Options(matching_mode='partial_qap'))
    assert not r['pair_options'] and r['a']['coverage']['opaque']==1
    a=from_text('R1 a 0 1k\nC1 a 0 1p')
    r=compare(a,a,top_a='TOP',top_b='TOP',options=Options(matching_mode='partial_qap',max_pair_scores=1))
    assert not r['pair_options'] and r['partial_alignment']['stop']=='size_budget'


def test_opaque_objects_inside_matched_regions_remain_opaque():
    text='.subckt CELL IN OUT\nR1 IN OUT 1k\nXmissing IN OUT UNKNOWN\n.ends\nX1 a b CELL\nX2 c d CELL\nRlink b d 1k'
    a=from_text(text)
    r=compare(a,a,top_a='TOP',top_b='TOP',options=Options(matching_mode='regional'))
    assert all('Xmissing' not in p['a'] and 'Xmissing' not in p['b'] for p in r['pair_options'])
    assert r['a']['coverage']['opaque']==r['b']['coverage']['opaque']==2
