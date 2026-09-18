"""Public synthetic controls; no files, models or names from workplace inputs.

Run with the repository/dependency src directories on PYTHONPATH. Measures full
API calls separately from the matcher, using fresh deterministic canonical data.
"""
import argparse
import json
import random
from time import perf_counter

from spice_canonical.canonical_netlist import from_text
from netlist_comparison import InputScope, Options, compare
from netlist_comparison.expand import expand
from netlist_comparison.regional import net_alignment


def fixture(n, *, changed=False, hierarchical=False, rename=False, additions=0):
    rng = random.Random(811)
    edges = [(i, i + 1, rng.randrange(n + 1)) for i in range(n)]
    edited = n // 2
    if changed:
        edges[edited] = (edited, edited + 2, edges[edited][2])
    edges += [(n + i, n + i + 1, n + (i // 2)) for i in range(additions)]
    net = lambda i: f'z{(i * 7919 + 31)}' if rename else f'n{i}'
    name = lambda i: f'Xq{(i * 3571 + 17)}' if rename else f'X{i}'
    rows = [(i, f'{name(i)} ' + ' '.join(net(k) for k in ns) +
             f' Cell W={2 if changed and i == edited else 1}') for i, ns in enumerate(edges)]
    if changed:
        rows = [(i, row) for i, row in rows if i != n // 3]
    if rename:
        rng.shuffle(rows)
    ledger = {}
    if not hierarchical:
        ledger = {i: f'TOP/{name(i)}' for i, _ in rows}
        return from_text('\n'.join(row for _, row in rows)), ledger
    # Populated depth four versus five; allocation changes across four banks.
    # Every bank exceeds local admission on thousands-leaf cases. All touched
    # nets are explicit interfaces, so arbitrary grouping preserves incidence.
    depth = 5 if changed else 4
    definitions, calls = [], []
    for bank in range(4):
        selected = [(i, row) for i, row in rows if ((i * 7 + i // 4) if changed else i) % 4 == bank]
        touched = sorted({k for i, _ in selected for k in edges[i]})
        ports = ' '.join(net(k) for k in touched)
        prefix = f'B{bank}' if not rename else f'J{3-bank}'
        definitions += [f'.subckt {prefix}0 {ports}', *[row for _, row in selected], '.ends']
        for level in range(1, depth - 1):
            definitions += [f'.subckt {prefix}{level} {ports}',
                            f'Xwrap{level} {ports} {prefix}{level-1}', '.ends']
        calls.append(f'X{prefix} {ports} {prefix}{depth-2}')
        path = '/'.join(['TOP', f'X{prefix}', *[f'Xwrap{k}' for k in range(depth-2, 0, -1)]])
        ledger.update({i: f'{path}/{name(i)}' for i, _ in selected})
    return from_text('\n'.join([*definitions, *calls])), ledger


def measure(n, *, hierarchical=False, changed=False, additions=0):
    a, la = fixture(n, hierarchical=hierarchical)
    b, lb = fixture(n, hierarchical=hierarchical, changed=changed, rename=True, additions=additions)
    out = []
    opts = Options(black_box_missing=True)
    va, vb = [expand(data, 'TOP', InputScope(), opts) for data in (a, b)]
    ai, bi = [{leaf.path: i for i, leaf in enumerate(v.leaves)} for v in (va, vb)]
    original_ids = {path: i for i, path in la.items()}
    for mode, budget in [('regional', 0), ('anchor_growth', 0), ('regional', 50000)]:
        start = perf_counter()
        report = compare(a, b, top_a='TOP', top_b='TOP', options=Options(
            matching_mode=mode, black_box_missing=True, large_frontier_work_limit=budget))
        elapsed = perf_counter() - start
        selected = set(report['representative_pair_ids'])
        pairs = [p for p in report['pair_options'] if p['id'] in selected]
        plan = [(ai[p['a']], bi[p['b']]) for p in pairs]
        evidence = report.get('partial_alignment', report.get('relational', {}))
        raw = [p for p in pairs if p['raw_differences']]
        sparse = evidence.get('large_frontier_search', {})
        out.append(dict(mode=mode, large_frontier_work_limit=budget, leaves=[len(va.leaves), len(vb.leaves)],
                        pairs=len(pairs), endpoint_disagreements=net_alignment(va, vb, plan)[0],
                        unpaired=[len(va.leaves)-len(pairs), len(vb.leaves)-len(pairs)],
                        raw_changed_pairs=len(raw), edited_pair_present=any(
                            p['a']==la[n//2] and p['b']==lb[n//2] for p in raw),
                        historical_disagreements=sum(lb.get(original_ids[p['a']])!=p['b'] for p in pairs),
                        seconds=round(elapsed, 4), stop=evidence.get('stop'),
                        work=sparse.get('work_used', evidence.get('candidate_work', evidence.get('compute_budget', {}).get('used'))),
                        core_pairs=sparse.get('core_pairs'), completion_pairs=sparse.get('completion_pairs')))
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--leaves', type=int, default=2000)
    parser.add_argument('--hierarchical', action='store_true')
    parser.add_argument('--changed', action='store_true')
    parser.add_argument('--additions', type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(measure(args.leaves, hierarchical=args.hierarchical,
                             changed=args.changed, additions=args.additions), indent=2))
