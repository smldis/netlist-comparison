"""Regional graph beam search followed by optional local correspondence.

No names or values enter the regional kernel. Full role incidence ranks the
bounded candidate ensemble; accepted hypotheses remain conditional and incomplete.
"""
from collections import defaultdict, deque
from time import perf_counter
from itertools import permutations
from heapq import nsmallest

import numpy as np
from scipy.optimize import linear_sum_assignment
from scipy.spatial.distance import cdist

from .model import View
from .partial import vectors, match_partial
from .relational import structural_labels
from .coarse import partition, graph, search, REGION_LIMIT, REFINE_LIMIT, BEAM_WIDTH


def local(view,indices,occurrence):
    result=View(leaves=[view.leaves[i] for i in indices])
    for i,l in enumerate(result.leaves):
        for role,net in l.nets.items():result.nets.setdefault(net,[]).append((i,role))
    if 'interface_nets' in occurrence:
        ports = occurrence['interface_nets']
    else:
        pins = view.definitions[occurrence['definition']].pins
        ports = list(dict.fromkeys(occurrence['bindings'][p.casefold()] for p in pins))
    # Distances traverse only non-dense local nets. Dense interface nets retain
    # direct-distance evidence but never become a shortcut through the region.
    distances=[]
    for start in ports:
        ds={start:0};queue=deque([start]);visited=set()
        while queue:
            net=queue.popleft()
            if net!=start and len({i for i,_ in result.nets.get(net,[])})>8:continue
            for i,_ in result.nets.get(net,[]):
                if i in visited:continue
                visited.add(i)
                for n in result.leaves[i].nets.values():
                    if n not in ds:ds[n]=ds[net]+1;queue.append(n)
        distances.append(ds)
    return result,distances


def local_features(view, indices, occurrence, roles):
    local_view, distances = local(view, indices, occurrence)
    descriptor = np.array([[min(d.get({r.casefold(): n for r, n in leaf.nets.items()}.get(role), 32), 32) / 8
                            for role in roles for d in distances] for leaf in local_view.leaves])
    hashes, _ = structural_labels(local_view, 3, 32)
    return (len(distances), vectors(local_view), descriptor,
            np.array([leaf.device.type.casefold() for leaf in local_view.leaves]),
            [np.array(hashes[d]) for d in (1, 2, 3)],
            np.array([bool(leaf.opaque) for leaf in local_view.leaves]), local_view)


def local_pairs(ia, ib, fa, fb):
    """Try partial interface maps, then retain best complete local incidence.

    For <=6 distinct boundary nets enumerate all interface bijections, without
    literal names, values or formal indices as evidence. Unequal sets use partial injections; above six ports use
    per-role distance distributions (less discriminating, order independent).
    Local symmetries survive as alternative leaf assignments. The full graph
    later evaluates boundary consistency, including residual devices.
    """
    from .blackbox import key as black_box_key
    incompatible = (np.array([black_box_key(x) for x in fa[6].leaves])[:, None] !=
                    np.array([black_box_key(x) for x in fb[6].leaves])[None, :])
    base = cdist(fa[1], fb[1], 'cityblock') / 8
    base += .12 * (fa[3][:, None] != fb[3][None, :])
    for ha, hb in zip(fa[4], fb[4]):
        base += .02 * (ha[:, None] != hb[None, :])
    pa, pb = fa[0], fb[0]
    roles = len(fa[2][0]) // pa if pa else (len(fb[2][0]) // pb if pb else 0)
    da = fa[2].reshape(len(ia), roles, pa)
    db = fb[2].reshape(len(ib), roles, pb)
    # Unequal boundary sets provide partial context, never a leaf-pair veto.
    # Enumerate injections of the smaller set into the larger (<=720).
    small, large = min(pa, pb), max(pa, pb)
    orders = permutations(range(large), small) if large <= 6 else [None]
    results = {}; best = float('inf')
    for order in orders:
        if order is None:
            # Fixed-width empirical distance distributions permit unequal sets.
            def hist(ds):
                return np.stack([(ds == distance / 8).mean(axis=2) if ds.shape[2]
                                 else np.zeros(ds.shape[:2]) for distance in range(33)], axis=2)
            xa, xb = hist(da), hist(db)
        elif pa <= pb:
            xa, xb = da, db[:, :, order]
        else:
            xa, xb = da[:, :, order], db
        cost = base + .25 * cdist(xa.reshape(len(ia), -1), xb.reshape(len(ib), -1), 'cityblock')
        cost[fa[5], :] = 1e6; cost[:, fb[5]] = 1e6
        cost[incompatible] = 1e6
        matrix = np.full((len(ia), len(ib) + len(ia)), 1e6)
        matrix[:, :len(ib)] = cost - 1.2
        matrix[np.arange(len(ia)), len(ib) + np.arange(len(ia))] = 0
        rr, cc = linear_sum_assignment(matrix)
        pairs = tuple((int(i), int(j)) for i, j in zip(rr, cc) if j < len(ib))
        if pairs in results:
            continue
        error, _ = net_alignment(fa[6], fb[6], pairs)
        score = error + .6 * (len(ia) + len(ib) - 2 * len(pairs))
        results[pairs] = score; best = min(best, score)
    return [[(ia[i], ib[j]) for i, j in pairs] for pairs, score in sorted(results.items())
            if score <= best + 1e-9]


def net_alignment(a, b, plan):
    """Exact maximum overlap for this plan's role incidence, in sparse blocks.

    Unrepresented/missing roles are counted too. This validates a supplied leaf
    map, not an electrical claim or globally minimum edit correspondence.
    """
    overlap = defaultdict(int); adjacency = defaultdict(set); total = 0
    for i, j in plan:
        x = {r.casefold(): n for r, n in a.leaves[i].nets.items()}
        y = {r.casefold(): n for r, n in b.leaves[j].nets.items()}
        total += len(x.keys() | y.keys())
        for role in x.keys() & y.keys():
            u, v = (0, x[role]), (1, y[role])
            overlap[u, v] += 1
            adjacency[u].add(v); adjacency[v].add(u)
    seen = set(); mapping = {}; preserved = 0
    for start in adjacency:
        if start in seen:
            continue
        todo = [start]; seen.add(start); nodes = []
        while todo:
            u = todo.pop(); nodes.append(u)
            for v in adjacency[u] - seen:
                seen.add(v); todo.append(v)
        aa = sorted(u for u in nodes if u[0] == 0)
        bb = sorted(u for u in nodes if u[0] == 1)
        matrix = np.array([[overlap[u, v] for v in bb] for u in aa])
        rr, cc = linear_sum_assignment(matrix, maximize=True)
        for i, j in zip(rr, cc):
            if matrix[i, j]:
                preserved += int(matrix[i, j]); mapping[aa[i][1]] = bb[j][1]
    return total - preserved, mapping


def residual_pairs(a, b, ia, ib, netmap, *, unmatched_per_side=.6):
    """Pair small residual sets using mapped terminal roles, with null choices."""
    from .blackbox import compatible
    if not ia or not ib:
        return []
    cost = np.full((len(ia), len(ib) + len(ia)), 1e6)
    for i, ai in enumerate(ia):
        x = a.leaves[ai]
        if x.opaque:
            continue
        xn = {r.casefold(): n for r, n in x.nets.items()}
        for j, bj in enumerate(ib):
            y = b.leaves[bj]
            if y.opaque or not compatible(x, y):
                continue
            yn = {r.casefold(): n for r, n in y.nets.items()}
            roles = xn.keys() | yn.keys()
            hits = sum(r in xn and r in yn and netmap.get(xn[r]) == yn[r] for r in roles)
            # Require some already mapped incidence. A changed endpoint can
            # compete with add/remove; unsupported isolated residues stay open.
            if hits:
                cost[i, j] = len(roles) - hits + .12 * (x.device.type != y.device.type) - 2 * unmatched_per_side
    cost[np.arange(len(ia)), len(ib) + np.arange(len(ia))] = 0
    rr, cc = linear_sum_assignment(cost)
    return [(ia[i], ib[j]) for i, j in zip(rr, cc) if j < len(ib)]


def _match_frontier(a, b, frontier_a, frontier_b):
    start = perf_counter()
    ra, ma, xa = frontier_a; rb, mb, xb = frontier_b
    if not ra or not rb:
        if max(len(a.leaves), len(b.leaves)) <= 128:
            plans, evidence = match_partial(a, b, use_names=False)
            evidence['regional_fallback'] = 'small_partial_qap'
            return plans, evidence
        return [], {'stop': 'no_populated_frontier', 'seconds': perf_counter() - start, 'hypotheses': []}
    if max(len(ra), len(rb)) > REGION_LIMIT or max(len(xa), len(xb)) > 256:
        return [], {'stop': 'regional_size_budget', 'seconds': perf_counter() - start, 'hypotheses': []}
    ga, gb = graph(a, ra, ma, xa), graph(b, rb, mb, xb)
    forward, fa = search(ga, gb, list(map(len, ma)), list(map(len, mb)))
    reverse, fb = search(gb, ga, list(map(len, mb)), list(map(len, ma)))
    candidates = {pairs: score for score, pairs in forward}
    for score, pairs in reverse:
        inverse = tuple(sorted((j, i) for i, j in pairs))
        candidates[inverse] = min(score, candidates.get(inverse, float('inf')))
    roles = sorted({r.casefold() for view in (a, b) for leaf in view.leaves for r in leaf.nets})
    features_a = [local_features(a, ii, o, roles) for ii, o in zip(ma, ra)]
    features_b = [local_features(b, ii, o, roles) for ii, o in zip(mb, rb)]
    cache = {}; results = []; unsupported = 0
    local_ensemble_truncated = False; local_ensemble_limit = 24
    coarse_best = min(candidates.values(), default=0)
    coarse_pruned = 0
    for placement, coarse_score in sorted(candidates.items(), key=lambda row: (row[1], row[0])):
        if coarse_score > coarse_best + .5:
            coarse_pruned += 1; continue
        ensemble = [[]]; valid = True
        for i, j in placement:
            if (i, j) not in cache:
                cache[i, j] = local_pairs(ma[i], mb[j], features_a[i], features_b[j])
            variants = cache[i, j]
            if variants is None:
                valid = False; break
            local_ensemble_truncated |= len(ensemble) * len(variants) > local_ensemble_limit
            # Stream bounded alternatives; stable leaf-pair ordering, never
            # interface declaration order.
            ensemble = nsmallest(local_ensemble_limit,
                                 (prefix + variant for prefix in ensemble for variant in variants),
                                 key=lambda pairs: tuple(sorted(pairs)))
        if not valid:
            unsupported += 1; continue
        for plan in ensemble:
            _, netmap = net_alignment(a, b, plan)
            plan += residual_pairs(a, b, xa, xb, netmap)
            error, _ = net_alignment(a, b, plan)
            unmatched = len(a.leaves) + len(b.leaves) - 2 * len(plan)
            score = error + .6 * unmatched
            results.append((score, tuple(sorted(plan)), placement, error, unmatched, coarse_score))
    results.sort(key=lambda row: (row[0], row[1]))
    best = results[0][0] if results else float('inf')
    retained = []; seen = set()
    for row in results:
        if row[0] > best + 1e-9 or row[1] in seen:
            continue
        seen.add(row[1]); retained.append(row)
    plans = [list(row[1]) for row in retained]
    def unmatched(items, pairs, side, location):
        used = {p[side] for p in pairs}
        return [location(item) for i, item in enumerate(items) if i not in used]
    return plans, {
        'method': 'regional_frontier_assignment_v4', 'stop': 'bounded_region_search',
        'seconds': perf_counter() - start, 'regions_a': len(ra), 'regions_b': len(rb),
        'frontier_a': [o['path'] for o in ra], 'frontier_b': [o['path'] for o in rb],
        'residual_a': len(xa), 'residual_b': len(xb), 'local_solves': len(cache),
        'beam_width': BEAM_WIDTH, 'refine_limit_per_direction': REFINE_LIMIT,
        'search_forward': fa, 'search_reverse': fb, 'refined': len(results),
        'unsupported_local_placements': unsupported,
        'coarse_slack': .5, 'coarse_score_pruned': coarse_pruned,
        'interface_basis': 'partial_injections_up_to_6_nets_else_distance_distributions',
        'local_ensemble_limit': local_ensemble_limit, 'local_ensemble_truncated': local_ensemble_truncated,
        'hypotheses': [{'regions': [[ra[i]['path'], rb[j]['path']] for i, j in row[2]],
                        'endpoint_disagreements': row[3], 'unmatched_leaves': row[4],
                        'score': row[0], 'coarse_score': row[5],
                        'unmatched_regions_a': unmatched(ra, row[2], 0, lambda o: o['path']),
                        'unmatched_regions_b': unmatched(rb, row[2], 1, lambda o: o['path']),
                        'unpaired_a': unmatched(a.leaves, row[1], 0, lambda leaf: leaf.path),
                        'unpaired_b': unmatched(b.leaves, row[1], 1, lambda leaf: leaf.path)}
                       for row in retained],
        'names_used': False, 'attributes_used': False,
        'scope': 'Bounded graph beam; incomplete alternatives. Size-selected hierarchy frontier, permutation-independent interface evidence, local optional assignments. Dense buses omitted only from coarse search. No arbitrary split/merge guarantee.'}


def _match_multifrontier(a, b):
    """Compare hierarchy and connectivity frontiers using the same leaf score."""
    from .pieces import connectivity_frontier
    start = perf_counter()
    ha, hb = partition(a), partition(b)
    ca, cb = connectivity_frontier(a), connectivity_frontier(b)
    trials = [('hierarchy', ha, hb)]
    if ca is not None and cb is not None:
        # Identical physical partitions need no second coarse search. Original
        # interfaces already pass permutation controls; differing partitions
        # are exactly where a hierarchy-independent candidate is useful.
        same = lambda x, y: {tuple(ii) for ii in x[1]} == {tuple(ii) for ii in y[1]}
        if not same(ha, ca) or not same(hb, cb):
            trials.append(('connectivity', ca, cb))
    evaluated = []; summaries = []
    for label, fa, fb in trials:
        plans, evidence = _match_frontier(a, b, fa, fb)
        if len(trials) == 1 and evidence.get('regional_fallback'):
            return plans, evidence
        summaries.append({'basis': label, 'evidence': evidence})
        for k, plan in enumerate(plans):
            error, _ = net_alignment(a, b, plan)
            score = error + .6 * (len(a.leaves) + len(b.leaves) - 2 * len(plan))
            detail = evidence['hypotheses'][k] if evidence.get('method') == 'regional_frontier_assignment_v4' else {}
            evaluated.append((score, tuple(sorted(plan)), label, detail, evidence))
    if not evaluated:
        evidence = summaries[0]['evidence']
        evidence.update(frontier_trials=summaries[1:], connectivity_frontier_available=ca is not None and cb is not None)
        return [], evidence
    best = min(row[0] for row in evaluated); seen = set(); retained = []
    for row in sorted(evaluated, key=lambda row: (row[0], row[1], row[2])):
        if row[0] > best + 1e-9 or row[1] in seen: continue
        seen.add(row[1]); retained.append(row)
    from .symmetry import complete_closure
    plans, closure = complete_closure(a, b, [list(row[1]) for row in retained])
    details = [dict(row[3], frontier_basis=row[2]) for row in retained]
    details += [{'frontier_basis': 'verified_structural_symmetry_composition',
                 'regions': [], 'endpoint_disagreements': 0, 'unmatched_leaves': 0,
                 'score': 0., 'coarse_score': None, 'unpaired_a': [], 'unpaired_b': [],
                 'unmatched_regions_a': [], 'unmatched_regions_b': []}
                for _ in plans[len(retained):]]
    evidence = dict(retained[0][4])
    evidence.update(method='regional_multifrontier_v4', seconds=perf_counter() - start,
                    frontier_trials=[{'basis': row['basis'], 'stop': row['evidence']['stop'],
                                      'hypotheses': len(row['evidence']['hypotheses']),
                                      'seconds': row['evidence']['seconds']} for row in summaries],
                    connectivity_frontier_available=ca is not None and cb is not None,
                    hypotheses=details, structural_symmetry_closure=closure,
                    scope='Bounded hierarchy/connectivity frontiers; partial interface correspondence; incomplete coupled alternatives. Original physical leaves are never merged.')
    if any(row[2] == 'connectivity' for row in retained):
        evidence['connectivity_pieces_a'] = ca[0]
        evidence['connectivity_pieces_b'] = cb[0]
    return plans, evidence


def match_regional(a, b, *, work_limit=50_000):
    """Factor certified repeats; challenge small incumbents with incidence search."""
    from .budgeted import Work, factor_match, incidence_search
    start = perf_counter(); work = Work(work_limit)
    factor_info = {'stop': 'small_whole_view'}
    if max(len(a.leaves), len(b.leaves)) > 128:
        plans, factor_info = factor_match(a, b, work)
        if plans:
            evidence = {'method': 'regional_budgeted_v5', 'stop': factor_info['stop'],
                        'names_used': False, 'attributes_used': False,
                        'hypotheses': [], **factor_info}
        else:
            plans, evidence = _match_multifrontier(a, b)
    else:
        plans, evidence = _match_multifrontier(a, b)
    def score(plan):
        error, _ = net_alignment(a, b, plan)
        return error + .6 * (len(a.leaves) + len(b.leaves) - 2 * len(plan))
    incumbent = min(map(score, plans), default=float('inf'))
    search_info = {'stop': 'incumbent_zero_or_local_admission'}
    if incumbent > 0 and max(len(a.leaves), len(b.leaves)) <= 64 and not work.exhausted:
        candidates, search_info = incidence_search(a, b, work)
        if candidates and min(map(score, candidates)) < incumbent - 1e-9:
            plans = candidates
            evidence = {'method': 'regional_budgeted_v5', 'stop': search_info['stop'],
                        'names_used': False, 'attributes_used': False,
                        'previous_incumbent_score': incumbent if np.isfinite(incumbent) else None,
                        'hypotheses': []}
    # A cheap omission objective can prefer hiding a multiply edited device.
    # Preserve the incumbent, but expose a separately labelled higher-coverage
    # completion for small unmatched sets supported by existing net incidence.
    tradeoffs = []
    if plans:
        base_plan = min(plans, key=score); extended = list(base_plan)
        for _ in range(3):
            used_a = {i for i, _ in extended}; used_b = {j for _, j in extended}
            ia = [i for i in range(len(a.leaves)) if i not in used_a]
            ib = [j for j in range(len(b.leaves)) if j not in used_b]
            if not ia or not ib or max(len(ia), len(ib)) > 64: break
            _, netmap = net_alignment(a, b, extended)
            extra = residual_pairs(a, b, ia, ib, netmap, unmatched_per_side=2.)
            if not extra: break
            extended += extra
        if len(extended) > len(base_plan):
            error, _ = net_alignment(a, b, extended)
            tradeoffs.append({'pairs': [[a.leaves[i].path, b.leaves[j].path] for i, j in sorted(extended)],
                              'endpoint_disagreements': error, 'score': score(extended),
                              'unmatched_leaves': len(a.leaves) + len(b.leaves) - 2 * len(extended),
                              'extra_pairs': [[a.leaves[i].path, b.leaves[j].path] for i, j in extended[len(base_plan):]],
                              'base_score': score(base_plan), 'completion_unmatched_cost_per_side': 2.,
                              'meaning': 'Separate coverage tradeoff under an increased omission cost; not a retained minimum-score hypothesis or identity.'})
    if plans and tradeoffs and tradeoffs[0]['score'] < min(map(score, plans)) - 1e-9:
        plans = [extended]
        evidence.update(method='regional_budgeted_v5', stop='incidence_completion_improved',
                        names_used=False, attributes_used=False)
        tradeoffs = []
    if evidence.get('method') == 'regional_budgeted_v5':
        evidence['hypotheses'] = []
        for plan in plans:
            error, _ = net_alignment(a, b, plan)
            used_a = {i for i, _ in plan}; used_b = {j for _, j in plan}
            evidence['hypotheses'].append({
                'endpoint_disagreements': error,
                'unmatched_leaves': len(a.leaves) + len(b.leaves) - 2 * len(plan),
                'score': score(plan), 'regions': [], 'coarse_score': None,
                'frontier_basis': 'certified_components' if evidence.get('component_permutation_factors') else 'net_incidence_beam',
                'unpaired_a': [l.path for i, l in enumerate(a.leaves) if i not in used_a],
                'unpaired_b': [l.path for j, l in enumerate(b.leaves) if j not in used_b]})
    evidence['coverage_tradeoffs'] = tradeoffs
    evidence.update(objective='endpoint_disagreements + 0.6 * unmatched_leaves',
                    alternatives_complete=False,
                    seconds=perf_counter() - start, compute_budget=work.report(),
                    factor_search=factor_info if not evidence.get('component_permutation_factors') else {'stop': factor_info['stop']},
                    incidence_search=search_info)
    return plans, evidence
