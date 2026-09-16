"""Incidence quality, factored ambiguity and honest bounded partial output."""
from dataclasses import replace
import hashlib

import pytest
from spice_canonical.canonical_netlist import from_text, Connection
from netlist_comparison import compare, InputScope, Options
from netlist_comparison.expand import expand
from netlist_comparison.regional import net_alignment


def salted(data, salt):
    # Deliberately independent local names, reversed declarations and pin order.
    tag = lambda x: hashlib.sha256((salt + x).encode()).hexdigest()[:12]
    cn = lambda c: 'C' + tag(c)
    nn = lambda c, n: '0' if n == '0' else 'n' + tag(c + '/' + n)
    defs = {c.name: c for c in (data.top, *data.subcircuits)}
    def cell(c):
        ds = []
        for d in c.devices:
            target = defs.get(d.type) if d.name.startswith('X') else None
            ds.append(replace(d, name=d.name[0] + tag(c.name + d.name), type=cn(target.name) if target else d.type,
                              connections=tuple(Connection(nn(target.name, x.pin) if target else x.pin,
                                                           nn(c.name, x.net)) for x in reversed(d.connections))))
        return replace(c, name=cn(c.name), devices=tuple(reversed(ds)), pins=tuple(nn(c.name, p) for p in reversed(c.pins)))
    return replace(data, top=cell(data.top), subcircuits=tuple(cell(c) for c in reversed(data.subcircuits)))


def run(a, b, **kwargs):
    return compare(a, b, top_a=a.top.name, top_b=b.top.name, options=Options(matching_mode='regional', **kwargs))


def passive():
    text = '.subckt RC A B G\n' + '\n'.join(
        [f'R{k} n{k} n{k+1} {k+1}k' for k in range(12)] +
        [f'C{k} n{k+1} G {k+1}p' for k in range(12)]) + '\n.ends\nXOLD in out 0 RC'
    return from_text(text), from_text(text.replace('R5 n5 n6', 'R5 n5 n9').replace('C8 n9 G', 'C8 fresh G'))


def test_join_split_repair_survives_independent_renames_without_raw_noise():
    a, b = passive(); a, b = salted(a, 'left'), salted(b, 'right')
    r = run(a, b)
    assert len(r['representative_pair_ids']) == 24
    assert {h['endpoint_disagreements'] for h in r['partial_alignment']['hypotheses']} == {2}
    assert not any(p['raw_differences'] for p in r['pair_options'])
    assert r['partial_alignment']['incidence_search']['beam_truncated']


def repeated(n=70):
    cell = '.model N NMOS\n.subckt C I O G\nM1 O I T G N W=1u\nM2 T I G G N W=2u\nR1 O G 1k\nC1 T G 1p\n.ends\n'
    calls = '\n'.join(f'X{k} i{k} o{k} 0 C' for k in range(n))
    a = from_text(cell + calls)
    special = cell.replace('.model N NMOS\n', '').replace('.subckt C ', '.subckt EDIT ').replace('M1 O I T G N W=1u', 'M1 O I T I N W=9u')
    b = from_text(cell + special + calls.replace('X0 i0 o0 0 C', 'X0 i0 o0 0 EDIT'))
    return a, b


def test_more_than_64_regions_keep_full_incidence_and_certified_copy_ambiguity():
    a, b = repeated(); r = run(a, b)
    assert len(r['representative_pair_ids']) == 280
    assert {h['endpoint_disagreements'] for h in r['partial_alignment']['hypotheses']} == {1}
    assert r['a']['coverage']['ambiguous'] == 280
    region = next(z for z in r['inspection_regions'] if 'TOP/X0/M1' in z['b'])
    assert len(region['a']) == 70 and 'TOP/X0/M1' in region['a']
    # A whole-component permutation preserves all original roles and boundary
    # incidence; individual independent slot swaps are not being asserted.
    factor = next(z for z in r['partial_alignment']['component_permutation_factors'] if z['side'] == 'a')
    v = expand(a, a.top.name, InputScope(), Options())
    ids = {leaf.path: i for i, leaf in enumerate(v.leaves)}
    mapping = dict(enumerate(range(len(v.leaves))))
    for p, q in zip(*factor['components'][:2]): mapping[ids[p]], mapping[ids[q]] = ids[q], ids[p]
    assert net_alignment(v, v, list(mapping.items()))[0] == 0
    assert sum(bool(p['raw_differences']) for p in r['pair_options']) == 1


def test_exhausted_component_budget_retains_feasible_partial_incumbent():
    a, b = repeated(); r = run(a, b, regional_work_limit=8)
    assert 0 < len(r['representative_pair_ids']) < 280
    assert r['partial_alignment']['stop'] == 'work_budget'
    assert r['partial_alignment']['compute_budget']['used'] == 8
    assert r['partial_alignment']['compute_budget']['exhausted']
    for side in ('a', 'b'): assert sum(r[side]['coverage'].values()) == 280
    assert all(h['unmatched_leaves'] > 0 for h in r['partial_alignment']['hypotheses'])


def test_small_work_budget_preserves_old_feasible_incumbent():
    a, b = passive(); r = run(a, b, regional_work_limit=1)
    assert len(r['representative_pair_ids']) == 24
    assert r['partial_alignment']['compute_budget']['used'] == 1
    assert r['partial_alignment']['compute_budget']['exhausted']
    assert all(h['endpoint_disagreements'] <= 8 for h in r['partial_alignment']['hypotheses'])


def test_dense_omission_has_separate_more_expensive_inspection_hypothesis():
    cell = '.model N NMOS\n.subckt D I BUS VDD G\nM1 BUS I T G N W=1u\nM2 T I G G N W=2u\nE1 BUS G I G 2\nR1 T G 3k\n.ends\n'
    calls = '\n'.join(f'X{k} in{k} bus vdd 0 D' for k in range(12))
    a = from_text(cell + calls); b = from_text(cell + calls.replace('X7 in7 bus vdd 0 D', 'X7 in7 bus2 vdd in7 D'))
    r = run(a, b); ev = r['partial_alignment']
    assert len(r['representative_pair_ids']) < 48
    tradeoff = ev['coverage_tradeoffs'][0]
    assert len(tradeoff['pairs']) == 48
    assert tradeoff['endpoint_disagreements'] == 8
    assert tradeoff['score'] > tradeoff['base_score']
    assert {'TOP/X7/M1', 'TOP/X7/M2'} <= {b for a, b in tradeoff['extra_pairs']}


@pytest.mark.parametrize('budget', [0, -1, 1.5, True])
def test_invalid_regional_work_budget(budget):
    with pytest.raises(ValueError): Options(regional_work_limit=budget)
