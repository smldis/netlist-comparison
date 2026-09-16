from dataclasses import replace

from spice_canonical.canonical_netlist import from_text
from netlist_comparison import compare, Options, InputScope
from netlist_comparison.expand import expand
from netlist_comparison.relational import match_views

BRANCHES = 'R1 a 0 1k\nC1 a x 1p\nR3 x 0 2k\nR2 b 0 2k\nC2 b y 1p\nL1 y 0 1n'


def run(a, b=None, **kwargs):
    return compare(a, a if b is None else b, top_a='TOP', top_b='TOP',
                   options=Options(matching_mode='anchor_growth', **kwargs))


def test_growth_distinguishes_repetition_and_never_scores_values():
    a=from_text(BRANCHES)
    b=from_text(BRANCHES.replace('R1 a 0 1k','R9 a 0 2k').replace('R2 b 0 2k','R8 b 0 1k'))
    r=run(a,b)
    pairs={p['a']:p for p in r['pair_options']}
    assert len(pairs)==6
    assert pairs['TOP/R1']['b']=='TOP/R9'
    assert pairs['TOP/R2']['b']=='TOP/R8'
    assert pairs['TOP/R1']['raw_differences']
    assert all(p['correspondence']=='tentative' for p in pairs.values())
    assert sum(r['a']['coverage'].values())==6
    assert r['relational']['joint_hypothesis']==r['representative_pair_ids']


def test_true_terminal_twins_remain_coupled_without_false_identity():
    a=from_text('R1 a 0 1k\nR2 a 0 2k\nC1 a 0 1p')
    r=run(a)
    assert all(not p['a'].endswith(('/R1','/R2')) for p in r['pair_options'])
    region=next(g for g in r['inspection_regions'] if 'TOP/R1' in g['a'])
    assert set(region['a'])==set(region['b'])=={'TOP/R1','TOP/R2'}
    assert region['constraint']=='one_to_one_leaf_pairs'
    assert not region['alternatives_complete']


def test_growth_evidence_is_acyclic_and_independently_auditable():
    # A chain longer than WL radius supplies anchors at its boundaries and
    # requires growth. Every recorded token must be an actual earlier witness.
    text='\n'.join(f'R{i} n{i} n{i+1} 1k' for i in range(22))+'\nC1 n0 0 1p'
    a=from_text(text); r=run(a)
    rows={p['id']:p for p in r['pair_options']}
    objs={x['id']:x for x in r['a']['objects']}
    assert any(p['evidence']['round']>0 for p in rows.values())
    for p in rows.values():
        for role,pid,witness_role in p['evidence'].get('support_tokens',[]):
            q=rows[pid]
            assert pid!=p['id']
            assert q['evidence']['round']<p['evidence']['round']
            assert objs[p['a']]['resolved_nets'][role]==objs[q['a']]['resolved_nets'][witness_role]
    assert all(p['a']==p['b'] for p in rows.values())


def test_order_and_direction_do_not_decide_growth_pairing():
    a=from_text(BRANCHES)
    b=replace(a,top=replace(a.top,devices=tuple(reversed(a.top.devices))))
    left,right=run(a,b),run(b,a)
    assert {(p['a'],p['b']) for p in left['pair_options']}=={(p['b'],p['a']) for p in right['pair_options']}
    for r in (left,right):
        r['metrics'].pop('seconds');r['relational'].pop('seconds')
    assert left==right


def test_growth_budget_never_accepts_from_a_partial_round_and_keeps_scope():
    a=from_text('\n'.join(f'R{i} n{i} n{i+1} 1k' for i in range(22))+'\nC1 n0 0 1p')
    v=expand(a,'TOP',InputScope(),Options())
    pairs,ev=match_views(v,v,max_candidates=1)
    assert ev['stop']=='candidate_budget'
    assert all(p['round']==0 for p in pairs)
    r=run(a,max_objects=1)
    assert not r['a']['expansion_complete']
    assert not r['pair_options']
    assert not r['scope']['global_net_declarations_complete']


def test_opaque_and_isolated_objects_cannot_seed_identity():
    for text in ('R1 a b 1k','X1 a b MISSING'):
        r=run(from_text(text))
        assert not r['pair_options']
        assert sum(r['a']['coverage'].values())==1
