"""Real primitive repartitioning: populated sibling blocks, unequal interfaces."""
from dataclasses import replace
from itertools import permutations
from spice_canonical.canonical_netlist import from_text,Connection
from netlist_comparison import compare,Options


def run(a,b):
    return compare(a,b,top_a='TOP',top_b='TOP',options=Options(matching_mode='regional'))


def fixture(edit=False):
    models='.model N NMOS\n.model P PMOS\n'
    a=models+'''.subckt BANK IN OUT G
M1 OUT IN T G N W=2u
M2 T IN G G N W=3u
R1 OUT G 1k
C1 T G 1p
.ends
X0 in out0 0 BANK
X1 in out1 0 BANK
Rlink out0 out1 10k
'''
    # The old BANK occurrence is removed. Its primitives are allocated to
    # sibling blocks by kind, with the former internal T exposed as a pin.
    b=models+'''.subckt ACTIVE INPUT OUTPUT TAIL GROUND
M9 OUTPUT INPUT TAIL GROUND N W=2u
M8 TAIL INPUT GROUND GROUND N W=3u
.ends
.subckt PASSIVE OUTPUT TAIL GROUND
R9 OUTPUT GROUND 1k
C9 TAIL GROUND 1p
.ends
Xactive0 in out0 t0 0 ACTIVE
Xpassive0 out0 t0 0 PASSIVE
Xactive1 in out1 t1 0 ACTIVE
Xpassive1 out1 t1 0 PASSIVE
Rnew out0 out1 10k
'''
    right=from_text(b)
    if edit:
        # Specialize only one physical occurrence, including body/type/width.
        c=right.subcircuits[0]
        ds=tuple(replace(d,type='pmos',parameters=tuple(replace(p,value='6u') if p.name=='W' else p for p in d.parameters),
                         connections=tuple(replace(x,net='INPUT') if x.pin=='b' else x for x in d.connections)) if d.name=='M9' else d for d in c.devices)
        changed=replace(c,name='SPECIAL',devices=ds)
        right=replace(right,subcircuits=(*right.subcircuits,changed),top=replace(right.top,devices=tuple(replace(d,type='SPECIAL') if d.name=='Xactive0' else d for d in right.top.devices)))
    return from_text(a),right


def test_actual_split_and_merge_keep_every_physical_leaf_and_conditional_membership():
    a,b=fixture()
    for x,y in ((a,b),(b,a)):
        r=run(x,y)
        assert len(r['representative_pair_ids'])==9
        assert all(h['endpoint_disagreements']==0 for h in r['partial_alignment']['hypotheses'])
        assert all(h['frontier_basis']=='connectivity' for h in r['partial_alignment']['hypotheses'])
        rows=r['hierarchy']['frontier_membership_hypotheses'][0]['memberships']
        assert len(rows)==4 and {row['paired_leaves'] for row in rows}=={2}
        assert not any(p['raw_differences'] for p in r['pair_options'])


def test_split_with_combined_body_type_width_edit_is_not_hidden_by_partial_pairing():
    a,b=fixture(True);r=run(a,b)
    assert len(r['representative_pair_ids'])==9
    assert all(h['endpoint_disagreements']==1 for h in r['partial_alignment']['hypotheses'])
    region=next(z for z in r['inspection_regions'] if 'TOP/Xactive0/M9' in z['b'])
    assert region['a']==['TOP/X0/M1']
    assert any({d['field'] for d in p['raw_differences']}=={'type','parameters.W'} for p in r['pair_options'])


def test_unused_formal_pin_can_be_added_without_changing_physical_incidence():
    a=from_text('.subckt C A B\nR1 A B 1k\nC1 A B 1p\n.ends\nX1 in 0 C')
    c=replace(a.subcircuits[0],pins=('UNUSED','B','A'))
    d=a.top.devices[0]
    b=replace(a,subcircuits=(c,),top=replace(a.top,devices=(replace(d,connections=(*d.connections,Connection('UNUSED','unused'))),)))
    r=run(a,b)
    assert len(r['representative_pair_ids'])==2
    assert all(h['endpoint_disagreements']==0 for h in r['partial_alignment']['hypotheses'])


def test_exact_terminal_twins_minimize_reporting_noise_but_keep_real_edits_ambiguous():
    # Primitive declaration/traversal order is reversed by a genuine regroup.
    # Both resistors have the exact same terminals, but different raw values.
    a=from_text('.subckt C IN G\nR1 IN G 1k\nR2 IN G 10k\n.ends\nXold in 0 C')
    source='.subckt P S T\nRz S T 1k\nRa S T 10k\n.ends\nXnew in 0 P'
    for changed in (False,True):
        b=from_text(source.replace('10k','12k') if changed else source)
        r=run(a,b)
        for group in r['groups']:
            pp={p['id']:p for p in r['pair_options']}
            for h in group['hypotheses']:
                assert sum(bool(pp[i]['raw_differences']) for i in h)==int(changed)
        assert r['representative_selection']['structural_ambiguity_preserved']
        assert r['a']['coverage']['ambiguous']==r['b']['coverage']['ambiguous']==2
        region=next(z for z in r['inspection_regions'] if 'TOP/Xold/R1' in z['a'])
        assert set(region['b'])=={'TOP/Xnew/Ra','TOP/Xnew/Rz'}
        assert all(h['endpoint_disagreements']==0 for h in r['partial_alignment']['hypotheses'])


def test_passive_only_small_fallback_does_not_use_a_name_hypothesis():
    a=from_text('R1 a 0 1k\nC1 a b 1p\nR2 b 0 2k')
    b=from_text('R9 x 0 1k\nC7 x y 1p\nR8 y 0 2k')
    r=run(a,b)
    assert r['partial_alignment']['regional_fallback']=='small_partial_qap'
    assert r['partial_alignment']['names_used'] is False
    assert [h['basis'] for h in r['partial_alignment']['hypotheses']]==['structure']


def test_complete_structural_symmetries_compose_without_using_values():
    from netlist_comparison.symmetry import complete_closure
    from netlist_comparison.expand import expand
    from netlist_comparison import InputScope
    # Three disjoint but structurally identical resistors: two transpositions
    # generate six maps. Different raw values must not remove these symmetries.
    a=from_text('R1 a 0 1k\nR2 b 0 2k\nR3 c 0 3k')
    v=expand(a,'TOP',InputScope(),Options())
    plans=[[(0,0),(1,1),(2,2)],[(0,1),(1,0),(2,2)],[(0,0),(1,2),(2,1)]]
    complete,ev=complete_closure(v,v,plans)
    assert len(complete)==6 and ev['verified_generators']==2 and not ev['truncated']
    bounded,ev=complete_closure(v,v,plans,limit=4)
    assert len(bounded)==4 and ev['truncated']
    already_full,ev=complete_closure(v,v,plans,limit=2)
    assert already_full==plans and ev['truncated']
    partial=[[(0,0),(1,1)],[(0,1),(1,0)]]
    assert complete_closure(v,v,partial)[0]==partial
