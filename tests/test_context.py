import hashlib
import json
from dataclasses import replace

import pytest

from spice_canonical.canonical_netlist import from_text
from netlist_comparison import compare, Options, InputScope
from netlist_comparison.candidates import features
from netlist_comparison.context import refine
from netlist_comparison.expand import expand

TEXT = 'R1 a 0 1k\nC1 a x 1p\nR3 x 0 2k\nR2 b 0 2k\nC2 b y 1p\nL1 y 0 1n'


def run(a, b=None, **options):
    return compare(from_text(a), from_text(b or a), top_a='TOP', top_b='TOP',
                   options=Options(context_mode='frozen_neighbors', **options))


def test_context_splits_structurally_distinguishable_repetition_without_attributes():
    base = compare(from_text(TEXT), from_text(TEXT), top_a='TOP', top_b='TOP')
    report = run(TEXT, TEXT.replace('R1 a 0 1k', 'R9 a 0 2k').replace('R2 b 0 2k', 'R8 b 0 1k'))
    assert len(report['a']['classes']) > len(base['a']['classes'])
    pairs = {p['a']: p for p in report['pair_options'] if p['status'] == 'representative'}
    assert pairs['TOP/R1']['b'] == 'TOP/R9'
    assert pairs['TOP/R2']['b'] == 'TOP/R8'
    assert report['context_evidence']['a']['inferred_pairs_used'] == 0
    assert pairs['TOP/R1']['evidence']['context_cost'] == 0


def test_frozen_bags_match_direct_neighbor_enumeration_excluding_all_self_endpoints():
    view = expand(from_text(TEXT + '\nM1 a x 0 0 N'), 'TOP', InputScope(), Options())
    base = features(view)
    classes, evidence = refine(view, base)
    sig = {path: c['signature'] for c in evidence['base_classes'] for path in c['members']}
    def digest(value):
        return int(hashlib.sha256(json.dumps(value, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest(), 16)
    for c in classes:
        for i in c.members:
            leaf = view.leaves[i]
            for role, count, bag, _ in c.context:
                endpoints = [(j, r) for j, r in view.nets[leaf.nets[role]] if j != i]
                assert count == len(endpoints)
                assert int(bag, 16) == sum(digest([sig[view.leaves[j].path], r.casefold()])
                                          for j, r in endpoints) % (1 << 256)


def test_context_is_order_invariant_and_does_not_promote_true_ambiguity():
    text = '\n'.join(f'R{i} a 0 {i+1}k' for i in range(100))
    first = run(text)
    second = run('\n'.join(reversed(text.splitlines())))
    for result in (first, second):
        result['metrics'].pop('seconds')
        assert not result['pair_options']
        assert result['a']['coverage']['unresolved'] == 100
    assert first == second


def test_no_context_pair_proposals_when_screening_is_incomplete():
    report = run(TEXT, max_pair_scores=1)
    assert not report['pair_options']
    assert report['a']['coverage']['unresolved'] == 6
    assert sum(report['a']['coverage'].values()) == 6


@pytest.mark.parametrize('options', [{'context_mode': 'recursive'}, {'context_weight': float('nan')}, {'context_weight': -1}])
def test_context_options_are_explicit_and_validated(options):
    with pytest.raises(ValueError):
        Options(**options)
