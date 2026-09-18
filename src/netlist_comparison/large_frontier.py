"""Sparse, conditional admission when regional decomposition produced no map.

Unique WL labels propose anchors, never certify identity. Conflicting terminal
maps quarantine *all* incident proposals. Only a consistent core propagates;
a final one-terminal completion is reported but cannot recruit more leaves.
"""
from collections import defaultdict
from time import perf_counter

from .blackbox import key as black_box_key
from .relational import structural_labels


def match(a, b, *, work_limit, rounds=64, degree_limit=32):
    start = perf_counter()
    work = 0
    trace = []
    rejected = set()
    stop = 'fixed_point'
    views = (a, b)
    nets = [[{r.casefold(): n for r, n in leaf.nets.items()} for leaf in v.leaves]
            for v in views]
    domains = [[(leaf.device.type.casefold(), black_box_key(leaf), tuple(sorted(ns)))
                for leaf, ns in zip(v.leaves, side)] for v, side in zip(views, nets)]
    sparse = [{n for n, es in v.nets.items() if len(es) <= degree_limit
               and not n.startswith('global:')} for v in views]
    histories = [structural_labels(v, 3, degree_limit)[0][-1] for v in views]
    indexes = []
    for v, labels in zip(views, histories):
        index = defaultdict(list)
        for i, label in enumerate(labels):
            if not v.leaves[i].opaque:
                index[label].append(i)
        indexes.append(index)
    aa, bb = indexes
    seeds = [(aa[s][0], bb[s][0]) for s in sorted(aa.keys() & bb.keys())
             if len(aa[s]) == len(bb[s]) == 1
             and domains[0][aa[s][0]] == domains[1][bb[s][0]]
             and any(n in sparse[0] and len(a.nets[n]) > 1 for n in nets[0][aa[s][0]].values())
             and any(n in sparse[1] and len(b.nets[n]) > 1 for n in nets[1][bb[s][0]].values())]

    def maps(plan):
        ab, ba = defaultdict(set), defaultdict(set)
        for i, j in plan:
            for r, u in nets[0][i].items():
                v = nets[1][j][r]
                ab[u].add(v); ba[v].add(u)
        return ab, ba

    def consistent(proposals, core):
        ab, ba = maps([*core, *proposals])
        kept = []
        for i, j in proposals:
            if all(len(ab[u]) == len(ba[nets[1][j][r]]) == 1 for r, u in nets[0][i].items()):
                kept.append((i, j))
            else:
                rejected.add((i, j))
        return kept

    # A partial seed traversal could conceal a later conflict. Admission is
    # atomic, as are subsequent candidate rounds. No arbitrary prefix commits.
    if len(seeds) > work_limit:
        core = []; stop = 'seed_work_limit'
    else:
        work += len(seeds)
        core = consistent(seeds, [])
    seed_count = len(core)
    seed_paths = [[a.leaves[i].path, b.leaves[j].path] for i, j in core]

    def candidates(core, completion=False):
        nonlocal work
        ab, _ = maps(core)
        mapping = {u: next(iter(vs)) for u, vs in ab.items()}
        used_a, used_b = {i for i, _ in core}, {j for _, j in core}
        inverted = defaultdict(list)
        for j, ns in enumerate(nets[1]):
            if j in used_b or b.leaves[j].opaque:
                continue
            for r, v in ns.items():
                if v in sparse[1]:
                    inverted[domains[1][j], r, v].append(j)
        scores = {}
        for i, ns in enumerate(nets[0]):
            if i in used_a or a.leaves[i].opaque:
                continue
            # At most degree_limit entries per represented terminal. Never a
            # Cartesian product of the compatible leaf populations.
            possible = {j for r, u in ns.items() if u in sparse[0] and u in mapping
                        for j in inverted.get((domains[0][i], r, mapping[u]), ())}
            for j in sorted(possible):
                if work >= work_limit:
                    return None
                work += 1
                target = nets[1][j]
                hits = sum(mapping.get(u) == target[r] for r, u in ns.items())
                support = len({u for r, u in ns.items() if u in sparse[0]
                               and target[r] in sparse[1] and mapping.get(u) == target[r]})
                if completion:
                    # Unknown roles count as differences here. This guarantees
                    # at most one extra discrepancy per added pair under an
                    # extension of the core net bijection.
                    if len(ns) - hits <= 1 and support >= 2:
                        scores[i, j] = (len(ns) - hits, -support)
                else:
                    scores[i, j] = (0, -support)
        left, right = defaultdict(list), defaultdict(list)
        for (i, j), score in scores.items():
            left[i].append((score, j)); right[j].append((score, i))
        def best(rows):
            out = {}
            for i, values in rows.items():
                low = min(s for s, _ in values)
                out[i] = [j for s, j in values if s == low]
            return out
        left, right = best(left), best(right)
        return [(i, js[0]) for i, js in sorted(left.items())
                if len(js) == 1 and right[js[0]] == [i]]

    if core:
        for step in range(rounds):
            proposed = candidates(core)
            if proposed is None:
                stop = 'candidate_work_limit'; break
            accepted = consistent(proposed, core)
            trace.append({'round': step + 1, 'proposed': len(proposed), 'accepted': len(accepted)})
            if not accepted:
                break
            core.extend(accepted)
        else:
            stop = 'round_limit'
    elif stop == 'fixed_point':
        stop = 'no_consistent_seeds'
    completion = []
    if core and stop not in ('candidate_work_limit', 'seed_work_limit'):
        proposed = candidates(core, completion=True)
        if proposed is None:
            stop = 'completion_work_limit'
        else:
            completion = proposed
    plan = sorted([*core, *completion])
    used = ({i for i, _ in plan}, {j for _, j in plan})
    classes = []
    for label in sorted(aa.keys() & bb.keys()):
        left = [a.leaves[i].path for i in aa[label] if i not in used[0]]
        right = [b.leaves[j].path for j in bb[label] if j not in used[1]]
        if left and right:
            classes.append({'a': left, 'b': right, 'basis': 'equal_WL_label_only_not_automorphism'})
    return ([plan] if plan else []), {
        'stop': stop, 'work_used': work, 'work_limit': work_limit,
        'work_unit': 'singleton seed checks and sparse candidate scores; incomplete batches discarded',
        'seed_proposals': len(seeds), 'consistent_seeds': seed_count,
        'seed_pair_paths': seed_paths,
        'quarantined_proposals': len(rejected), 'core_pairs': len(core),
        'completion_pairs': len(completion), 'round_limit': rounds, 'rounds': trace,
        'degree_limit': degree_limit, 'wl_depth': 3,
        'unresolved_label_classes': classes,
        'completion_pair_paths': [[a.leaves[i].path, b.leaves[j].path] for i, j in completion],
        'seconds': perf_counter() - start,
        'scope': 'Conditional on unique-WL tentative seeds and consistent-core choices. '
                 'Conflicts abstain, ties abstain; labels are not identity or automorphism proof. '
                 'Completion has at most one unsupported terminal and never propagates. '
                 'No exhaustive alternatives or history recovery. Preprocessing, validation and '
                 'reporting are outside the work counter; not a time/RAM cap.'}
