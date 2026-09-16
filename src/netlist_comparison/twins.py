"""Representative selection within exact represented-terminal symmetries.

Raw fields rank presentation only inside an already established same-type,
identical-role/incidence class. They do not seed or rank graph correspondence.
"""
from collections import defaultdict
import numpy as np
from scipy.optimize import linear_sum_assignment
from .report import parameter_differences


def terminal_twins(view):
    groups = defaultdict(list)
    for i, leaf in enumerate(view.leaves):
        if not leaf.opaque:
            key = (leaf.device.type.casefold(), tuple(sorted((r.casefold(), n) for r, n in leaf.nets.items())))
            groups[key].append(i)
    return list(groups.values())


def representatives(a, b, plans, max_class=128):
    """Improve fixed matched sets by twin-only swaps, preserving incidence.

    Two bounded alternating sweeps over exact A/B classes. Each local optional
    permutation is adopted only if it strictly reduces raw field differences.
    This is not a claim to globally optimize all coupled symmetry permutations.
    Unmatched objects never enter this presentation refinement.
    """
    ga = [g for g in terminal_twins(a) if len(g) > 1]
    gb = [g for g in terminal_twins(b) if len(g) > 1]
    costs = {}
    def cost(i, j):
        if (i, j) not in costs:
            x, y = a.leaves[i].device, b.leaves[j].device
            costs[i, j] = len(parameter_differences(x.parameters, y.parameters, 'parameters')) + (x.type != y.type)
        return costs[i, j]
    output = []; records = []
    for k, plan in enumerate(plans):
        mapping = dict(plan)
        before = sum(cost(i, j) for i, j in plan); skipped = set(); swaps = 0
        for _ in range(2):
            changed = False
            for side, groups in enumerate((ga, gb)):
                inverse = {j: i for i, j in mapping.items()}
                for number, group in enumerate(groups):
                    indices = [i for i in group if i in (mapping if side == 0 else inverse)]
                    if len(indices) < 2: continue
                    if len(indices) > max_class:
                        skipped.add((side, number)); continue
                    aa = indices if side == 0 else [inverse[j] for j in indices]
                    bb = [mapping[i] for i in indices] if side == 0 else indices
                    matrix = np.array([[cost(i, j) for j in bb] for i in aa])
                    rr, cc = linear_sum_assignment(matrix)
                    if matrix[rr, cc].sum() < sum(cost(i, mapping[i]) for i in aa):
                        replacement = {aa[i]: bb[j] for i, j in zip(rr, cc)}
                        swaps += sum(mapping[i] != j for i, j in replacement.items())
                        mapping.update(replacement); changed = True
            if not changed: break
        revised = sorted(mapping.items()); output.append(revised)
        records.append({'hypothesis': k, 'raw_field_differences_before': int(before),
                        'raw_field_differences_after': int(sum(cost(i, j) for i, j in revised)),
                        'reassigned_pairs': swaps, 'skipped_large_classes': len(skipped)})
    return output, {'method': 'exact_terminal_twins_minimum_raw_fields_v1',
                    'structural_ambiguity_preserved': True, 'matched_object_sets_preserved': True,
                    'class_limit': max_class, 'hypotheses': records,
                    'scope': 'Representative only: two bounded twin-permutation sweeps. All structural twin alternatives remain in inspection_regions; matching raw fields do not prove identity or absence of hidden swaps.'}
