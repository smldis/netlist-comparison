"""Behaviour checks for regional search, independent of edit-history identity."""
from dataclasses import replace

from spice_canonical.canonical_netlist import from_text, Circuit, Device
from netlist_comparison import compare, Options, InputScope
from netlist_comparison.expand import expand
from netlist_comparison.regional import net_alignment


def run(a, b):
    return compare(a, b, top_a=a.top.name, top_b=b.top.name,
                   options=Options(matching_mode='regional'))


def graph_deck(n, edges):
    text = '.subckt CELL I O\nR1 I O 1k\nC1 O 0 1p\n.ends\n'
    text += '\n'.join(f'X{i} in n{i} CELL' for i in range(n)) + '\n'
    text += '\n'.join(f'R{i} n{x} n{y} 7k' for i, (x, y) in enumerate(edges))
    return from_text(text)


def test_branched_cycles_preserve_all_endpoints_and_ambiguous_leaves():
    a = graph_deck(5, [(0, 1), (1, 2), (2, 0), (0, 3), (0, 4)])
    r = run(a, a)
    assert r['partial_alignment']['method'] == 'regional_multifrontier_v4'
    assert r['groups'][0]['hypotheses']
    for h in r['partial_alignment']['hypotheses']:
        assert h['endpoint_disagreements'] == 0 and h['unmatched_leaves'] == 0
    region = next(z for z in r['inspection_regions'] if 'TOP/X3/R1' in z['a'])
    assert set(region['b']) == {'TOP/X3/R1', 'TOP/X4/R1'}


def test_unequal_regions_are_optional_and_reported_per_hypothesis():
    a = graph_deck(4, [(0, 1), (0, 2), (0, 3)])
    b = graph_deck(5, [(0, 1), (0, 2), (0, 3), (0, 4)])
    r = run(a, b)
    assert r['partial_alignment']['regions_a'] == 4
    assert r['partial_alignment']['regions_b'] == 5
    for h in r['partial_alignment']['hypotheses']:
        assert len(h['unmatched_regions_b']) == 1
        assert not h['unmatched_regions_a']
        assert len(h['unpaired_b']) == 3
        assert h['endpoint_disagreements'] == 0
    reverse = run(b, a)
    assert [h['score'] for h in r['partial_alignment']['hypotheses']] == [h['score'] for h in reverse['partial_alignment']['hypotheses']]


def test_large_wrapper_is_opened_at_a_mixed_depth_frontier():
    # 3 regions x 44 leaves: adding a >128-leaf container must not hide regions.
    cell = '.subckt CELL I O\n' + '\n'.join(f'R{k} I O {k+1}k' for k in range(44)) + '\n.ends\n'
    a = from_text(cell + 'X0 a b CELL\nX1 b c CELL\nX2 c d CELL')
    old = replace(a.top, name='INSIDE')
    b = replace(a, top=Circuit('OUTSIDE', (), (Device('XWRAP', old.name, ()),)),
                subcircuits=(*a.subcircuits, old))
    r = run(a, b)
    assert r['partial_alignment']['regions_a'] == r['partial_alignment']['regions_b'] == 3
    assert all(p.startswith('OUTSIDE/XWRAP/') for p in r['partial_alignment']['frontier_b'])
    assert len(r['representative_pair_ids']) == 132
    assert all(h['endpoint_disagreements'] == 0 for h in r['partial_alignment']['hypotheses'])


def test_full_incidence_validation_counts_body_and_missing_roles():
    a = from_text('.model N NMOS\nM1 d g s 0 N\nR1 d 0 1k')
    b = from_text('.model N NMOS\nM1 d g s g N\nR1 d 0 1k')
    va = expand(a, 'TOP', InputScope(), Options())
    vb = expand(b, 'TOP', InputScope(), Options())
    assert net_alignment(va, vb, [(0, 0), (1, 1)])[0] == 1
    del vb.leaves[0].nets['b']
    assert net_alignment(va, vb, [(0, 0), (1, 1)])[0] == 1


def test_flat_large_shape_abstains_explicitly_and_keeps_coverage():
    a = from_text('\n'.join(f'R{i} n{i} n{i+1} 1k' for i in range(129)))
    r = run(a, a)
    assert r['partial_alignment']['stop'] == 'no_populated_frontier'
    assert not r['representative_pair_ids']
    assert sum(r['a']['coverage'].values()) == 129


def test_symmetric_interfaces_retain_coupled_alternatives_without_names_or_values():
    a = from_text('.subckt CELL A B G\nR1 A G 1k\nR2 B G 2k\n.ends\nX1 x y 0 CELL')
    b = replace(a, subcircuits=tuple(replace(c, pins=tuple(reversed(c.pins))) for c in a.subcircuits))
    r = run(a, b)
    assert len(r['groups'][0]['hypotheses']) == 2
    region = next(z for z in r['inspection_regions'] if 'TOP/X1/R1' in z['a'])
    assert set(region['b']) == {'TOP/X1/R1', 'TOP/X1/R2'}
    assert all(h['endpoint_disagreements'] == 0 for h in r['partial_alignment']['hypotheses'])


def test_all_formal_pin_permutations_preserve_small_edited_incidence():
    import importlib.util
    from itertools import permutations
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'examples/evaluate.py'
    spec = importlib.util.spec_from_file_location('formal_order_fixture', path)
    fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
    a, b, _ = fixture.stress_fixture(1)
    for order in permutations(range(3)):
        changed = replace(b, subcircuits=tuple(replace(c, pins=tuple(c.pins[i] for i in order)) for c in b.subcircuits))
        r = run(a, changed)
        assert len(r['representative_pair_ids']) == 46
        assert all(h['endpoint_disagreements'] == 0 for h in r['partial_alignment']['hypotheses'])
        assert sum(bool(p['raw_differences']) for p in r['pair_options']) == 1
