"""Raw-aware presentation inside certified whole-component automorphisms.

Never create a structural candidate here. Each factor already certifies an
independent permutation with its shared boundary fixed. Fully paired components
can exchange partners without changing represented incidence or matched sets.
"""
from collections import defaultdict, deque
from time import perf_counter

import numpy as np
from scipy.optimize import linear_sum_assignment


def profile(leaf):
    return (leaf.device.type, tuple((p.name, p.value) for p in leaf.device.parameters))


def _assignment(left, right, limit):
    """Minimize differing slots, cancelling exact vectors before a bounded LAP.

    Hamming distance is a metric: replacing x->y, z->x by x->x, z->y
    cannot increase cost. Thus equal-vector cancellation retains an optimum.
    This statement applies to this one factor with all other choices fixed.
    """
    available = defaultdict(deque)
    for j, row in enumerate(right):
        available[row].append(j)
    chosen = {}; remaining = []
    for i, row in enumerate(left):
        if available[row]:
            chosen[i] = available[row].popleft()
        else:
            remaining.append(i)
    targets = sorted(j for group in available.values() for j in group)
    if len(remaining) > limit:
        return None, len(remaining)
    if remaining:
        aa = np.array([left[i] for i in remaining])
        bb = np.array([right[j] for j in targets])
        costs = np.zeros((len(aa), len(bb)), dtype=np.int32)
        for slot in range(aa.shape[1]):
            costs += aa[:, slot, None] != bb[None, :, slot]
        rr, cc = linear_sum_assignment(costs)
        chosen.update((remaining[i], targets[j]) for i, j in zip(rr, cc))
    return chosen, len(remaining)


def refine(a, b, plans, factors, *, residual_limit=256, sweeps=2):
    """Bounded coordinate descent on certified factors; no global optimum claim."""
    start = perf_counter()
    path_indices = [{leaf.path: i for i, leaf in enumerate(v.leaves)} for v in (a, b)]
    profiles = {}; raw = []
    for view in (a, b):
        row = []
        for leaf in view.leaves:
            value = profile(leaf)
            row.append(profiles.setdefault(value, len(profiles)))
        raw.append(row)
    indexed = [(0 if f['side'] == 'a' else 1,
                [[path_indices[0 if f['side'] == 'a' else 1][p] for p in c] for c in f['components']])
               for f in factors]
    output = []; records = []
    def count(mapping):
        return sum(raw[0][i] != raw[1][j] for i, j in mapping.items())
    for h, plan in enumerate(plans):
        mapping = dict(plan); before = count(mapping)
        changes = []; skipped = set(); partial = set(); max_residual = 0
        converged = False
        for sweep in range(sweeps):
            improved = False
            for number, (side, components) in enumerate(indexed):
                current = mapping if side == 0 else {j: i for i, j in mapping.items()}
                eligible = [(k, row) for k, row in enumerate(components) if all(i in current for i in row)]
                if len(eligible) != len(components):
                    partial.add(number)
                if len(eligible) < 2:
                    continue
                rows = [row for _, row in eligible]
                partners = [[current[i] for i in row] for row in rows]
                left = [tuple(raw[side][i] for i in row) for row in rows]
                right = [tuple(raw[1-side][j] for j in row) for row in partners]
                chosen, residual = _assignment(left, right, residual_limit)
                max_residual = max(max_residual, residual)
                if chosen is None:
                    skipped.add(number)
                    continue
                old_cost = sum(x != y for aa, bb in zip(left, right) for x, y in zip(aa, bb))
                new_cost = sum(x != y for i, j in chosen.items() for x, y in zip(left[i], right[j]))
                if new_cost >= old_cost:
                    continue
                replacement = {i: j for c, d in chosen.items() for i, j in zip(rows[c], partners[d])}
                mapping.update(replacement if side == 0 else {j: i for i, j in replacement.items()})
                improved = True
                changes.append({'sweep': sweep, 'factor': number,
                                'changed_pairs_before': old_cost, 'changed_pairs_after': new_cost,
                                'component_assignment': [[eligible[c][0], eligible[d][0]]
                                                         for c, d in sorted(chosen.items()) if c != d]})
            if not improved:
                converged = True
                break
        output.append(sorted(mapping.items()))
        records.append({'hypothesis': h, 'changed_pairs_before': before, 'changed_pairs_after': count(mapping),
                        'permutations': changes, 'skipped_large_residual_factors': sorted(skipped),
                        'partially_paired_factors': sorted(partial), 'largest_residual_assignment': max_residual,
                        'no_improvement_sweep_reached': converged})
    # Population facts are independent of the representative permutation within
    # this A factor's fully paired component slots. They are still conditional on
    # the selected partner set and do not identify a historical changed device.
    balances = []
    if output:
        mapping = dict(output[-1]); reverse_profiles = {n: p for p, n in profiles.items()}
        for number, (side, components) in enumerate(indexed):
            if side != 0:
                continue
            rows = [row for row in components if all(i in mapping for i in row)]
            if not rows:
                continue
            for slot, indices in enumerate(zip(*rows)):
                aa = defaultdict(list); bb = defaultdict(list)
                for i in indices:
                    aa[raw[0][i]].append(a.leaves[i].path)
                    bb[raw[1][mapping[i]]].append(b.leaves[mapping[i]].path)
                delta = []
                for p in sorted(aa.keys() | bb.keys()):
                    if len(aa[p]) == len(bb[p]):
                        continue
                    typ, params = reverse_profiles[p]
                    delta.append({'type': typ, 'parameters': [{'name': n, 'value': v} for n, v in params],
                                  'count_a': len(aa[p]), 'count_b': len(bb[p]),
                                  'paths_a': aa[p], 'paths_b': bb[p]})
                if delta:
                    balances.append({'factor': number, 'slot': slot, 'paired_components': len(rows),
                                     'minimum_differing_pairs_in_slot': sum(max(0, len(aa[p])-len(bb[p])) for p in aa),
                                     'profiles': delta})
    wiring = {'net_pairs': [], 'endpoint_disagreements': [],
              'scope': 'One maximum-overlap net bijection conditional on the final representative leaf map. '
                       'Net-map ties are not enumerated; these are inspection witnesses, not established edit locations.'}
    if output:
        from .regional import net_alignment
        _, netmap = net_alignment(a, b, output[-1])
        wiring['net_pairs'] = [{'a': u, 'b': v} for u, v in sorted(netmap.items())]
        for i, j in output[-1]:
            aa = {r.casefold(): n for r, n in a.leaves[i].nets.items()}
            bb = {r.casefold(): n for r, n in b.leaves[j].nets.items()}
            for role in sorted(aa.keys() | bb.keys()):
                if role not in aa or role not in bb or netmap.get(aa[role]) != bb[role]:
                    wiring['endpoint_disagreements'].append({
                        'a': a.leaves[i].path, 'b': b.leaves[j].path, 'role': role,
                        'net_a': aa.get(role), 'net_b': bb.get(role),
                        'expected_b_under_net_map': netmap.get(aa.get(role))})
    return output, {
        'method': 'certified_component_raw_presentation_v1',
        'objective': 'number of paired leaves with any unequal raw type or ordered parameter list',
        'structural_ambiguity_preserved': True, 'matched_object_sets_preserved': True,
        'residual_assignment_limit': residual_limit, 'sweeps_limit': sweeps,
        'hypotheses': records, 'representative_profile_imbalances': balances,
        'representative_wiring_witness': wiring,
        'seconds': perf_counter() - start,
        'scope': 'Two bounded factor sweeps; each admitted coordinate is optimal, their joint result need not be. '
                 'Only fully paired certified components move, never individual slots. '
                 'Hypotheses are not ranked by raw values. All structural factors remain. '
                 'Profile imbalances concern the final representative partner population in A-factor slots; '
                 'they are not independent edit counts or historical identities. B-only factors and unmatched leaves are outside that inventory.'}
