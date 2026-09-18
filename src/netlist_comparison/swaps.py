"""Bounded discrepancy-guided transpositions of occupied leaf counterparts.

The fixed incumbent net map only orders proposals. Every admitted state is scored
with a freshly optimized full represented incidence map, including body/supply
roles. A best-first beam can expand equal or worse states, not only greedy gains.
"""
from heapq import nsmallest
from time import perf_counter

from .blackbox import compatible

BEAM_WIDTH = 12
BRANCH_LIMIT = 32
DEPTH_LIMIT = 8
RETAIN_LIMIT = 32


def challenge(a, b, plans, *, work_limit):
    from .regional import net_alignment

    start = perf_counter()
    evidence = dict(method='paired_discrepancy_beam_v1', work_limit=work_limit,
                    work_used=0, beam_width=BEAM_WIDTH, branch_limit=BRANCH_LIMIT,
                    depth_limit=DEPTH_LIMIT, retained_limit=RETAIN_LIMIT,
                    expanded_states=0, deepest_scored=0, beam_pruned=False,
                    proposals_pruned=False, depth_pruned=False,
                    proposal_comparisons=0, proposal_candidates_ranked=0,
                    alternatives_truncated=False, alternatives_complete=False,
                    names_used=False, attributes_used=False, matched_sets_preserved_per_move=True,
                    objective='endpoint_disagreements + 0.6 * unmatched_leaves',
                    limitations='Discrepancy-guided occupied transpositions only; bounded branches, beam, depth, scores and retained ties. Order-sensitive; no exhaustive symmetry, identity or optimality claim. Native type changes allowed; external cell/interface constraints remain hard.')

    def finish(stop, output):
        evidence.update(stop=stop, seconds=perf_counter() - start)
        return output, evidence

    if not work_limit:
        return finish('disabled', plans)
    if not plans or not plans[-1]:
        return finish('no_populated_incumbent', plans)

    roles = [[{r.casefold(): n for r, n in leaf.nets.items()} for leaf in v.leaves]
             for v in (a, b)]
    baseline = tuple(sorted(plans[-1]))
    scores = {}; netmaps = {}; depth = {}; parents = {}; frontier = []

    def evaluate(plan, parent=None):
        error, netmap = net_alignment(a, b, plan)
        scores[plan] = (error + .6 * (len(a.leaves) + len(b.leaves) - 2 * len(plan)), error)
        netmaps[plan] = netmap
        depth[plan] = 0 if parent is None else depth[parent] + 1
        parents[plan] = parent
        evidence['deepest_scored'] = max(evidence['deepest_scored'], depth[plan])

    for plan in [baseline, *(tuple(sorted(p)) for p in plans)]:
        if plan in scores:
            continue
        if len(scores) >= work_limit:
            break
        evaluate(plan); frontier.append(plan)
    seeds = list(frontier)
    evidence['seeds_truncated'] = len({tuple(sorted(p)) for p in plans}) > len(scores)

    def proposals(plan):
        mapping = dict(plan); netmap = netmaps[plan]
        def mismatch(i, j):
            x, y = roles[0][i], roles[1][j]
            return sum(r not in x or r not in y or netmap.get(x[r]) != y[r]
                       for r in x.keys() | y.keys())
        errors = {i: mismatch(i, j) for i, j in plan}
        active = {i for i, j in plan if errors[i] and not a.leaves[i].opaque and not b.leaves[j].opaque}
        ranked_count = 0

        def ranked_candidates():
            nonlocal ranked_count
            for i in active:
                j = mapping[i]
                for k, l in plan:
                    if k == i or a.leaves[k].opaque or b.leaves[l].opaque:
                        continue
                    # With two active ends, only the lower index emits. With
                    # one active end it emits regardless of index. No pair set
                    # or quadratic candidate list is retained.
                    if k in active and k < i:
                        continue
                    evidence['proposal_comparisons'] += 1
                    if not compatible(a.leaves[i], b.leaves[l]) or not compatible(a.leaves[k], b.leaves[j]):
                        continue
                    # Conditional proposal rank, never the final objective.
                    delta = mismatch(i, l) + mismatch(k, j) - errors[i] - errors[k]
                    ranked_count += 1
                    yield (delta, -(errors[i] + errors[k]), (min(i, k), max(i, k)))

        retained = nsmallest(BRANCH_LIMIT, ranked_candidates())
        evidence['proposal_candidates_ranked'] += ranked_count
        evidence['proposals_pruned'] |= ranked_count > BRANCH_LIMIT
        for _, _, (i, k) in retained:
            changed = dict(mapping); changed[i], changed[k] = mapping[k], mapping[i]
            yield tuple(sorted(changed.items()))

    stop = 'neighborhood_exhausted'
    while frontier:
        frontier.sort(key=lambda p: (scores[p][0], depth[p], p))
        evidence['beam_pruned'] |= len(frontier) > BEAM_WIDTH
        del frontier[BEAM_WIDTH:]
        plan = frontier.pop(0)
        if scores[plan][1] == 0:
            # Existing equal seeds survive; unseen symmetries are not enumerated.
            continue
        if depth[plan] >= DEPTH_LIMIT:
            evidence['depth_pruned'] = True
            continue
        if len(scores) >= work_limit:
            stop = 'work_limit'; break
        evidence['expanded_states'] += 1
        for candidate in proposals(plan):
            if candidate in scores:
                continue
            if len(scores) >= work_limit:
                stop = 'work_limit'; break
            evaluate(candidate, plan)
            frontier.append(candidate)
        if stop == 'work_limit':
            break
    if stop != 'work_limit' and evidence['depth_pruned']:
        stop = 'depth_limit'
    elif stop != 'work_limit' and (evidence['beam_pruned'] or evidence['proposals_pruned']):
        stop = 'bounded_frontier_exhausted'
    best = min(v[0] for v in scores.values())
    equal = [p for p in scores if abs(scores[p][0] - best) < 1e-9]
    selected = baseline if baseline in equal else equal[0]
    retained = [p for p in equal if p != selected][:RETAIN_LIMIT - 1] + [selected]
    evidence['alternatives_truncated'] = len(equal) > RETAIN_LIMIT

    def paths(edges):
        return [[a.leaves[i].path, b.leaves[j].path] for i, j in sorted(edges)]

    def seed_index(plan):
        while parents[plan] is not None:
            plan = parents[plan]
        return seeds.index(plan)

    def trajectory(plan):
        chain = []
        while plan is not None:
            chain.append(scores[plan][0]); plan = parents[plan]
        return list(reversed(chain))

    evidence.update(work_used=len(scores), baseline_score=scores[baseline][0],
                    baseline_endpoint_disagreements=scores[baseline][1], best_score=best,
                    best_endpoint_disagreements=scores[selected][1],
                    score_improvement=scores[baseline][0] - best,
                    baseline_pairs=paths(baseline), retained_hypotheses=len(retained),
                    seed_pairs=[paths(p) for p in seeds],
                    selected_seed_index=seed_index(selected),
                    selected_matched_sets_equal_baseline=all(
                        {edge[s] for edge in selected} == {edge[s] for edge in baseline}
                        for s in (0, 1)),
                    selected_score_trajectory=trajectory(selected),
                    witnesses=[dict(removed_pairs=paths(set(baseline) - set(p)),
                                    added_pairs=paths(set(p) - set(baseline)),
                                    score=scores[p][0], score_delta=scores[p][0] - scores[baseline][0],
                                    selected=p == selected, seed_index=seed_index(p),
                                    score_trajectory=trajectory(p))
                               for p in retained if p != baseline])
    return finish(stop, [list(p) for p in retained])
