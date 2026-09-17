"""Bounded omission-token beam; every candidate is a complete injective map.

An unused leaf can take an occupied partner, releasing its former partner for
another step. Full represented incidence ranks states, including uphill steps.
There is no name/value/distance admission filter and no optimality certificate.
"""
from collections import defaultdict
from time import perf_counter

from .blackbox import key as boundary_key


BEAM_WIDTH = 12
DEPTH_LIMIT = 3
RETAIN_LIMIT = 32
OMISSION_LIMIT = 64


def challenge(a, b, plans, *, work_limit):
    from .regional import net_alignment
    start = perf_counter()
    evidence = dict(method='occupied_omission_beam_v1', work_limit=work_limit,
                    work_used=0, beam_width=BEAM_WIDTH, depth_limit=DEPTH_LIMIT,
                    retained_limit=RETAIN_LIMIT, omission_limit=OMISSION_LIMIT,
                    beam_pruned=False, alternatives_truncated=False, rounds=0,
                    alternatives_complete=False, names_used=False, attributes_used=False,
                    objective='endpoint_disagreements + 0.6 * unmatched_leaves',
                    margin_scope='Conditional on evaluated complete maps only; not confidence or an optimality bound.',
                    limitations='Only omission-seeded exchanges/additions; no full-coverage swaps or deletion moves. Bounded depth, beam, scores and retained ties; order-sensitive. Native type changes allowed; external identities/interfaces remain hard constraints.')
    def finish(stop, output):
        evidence.update(stop=stop, seconds=perf_counter() - start)
        return output, evidence
    if not plans or not plans[-1]:
        return finish('no_populated_incumbent', plans)
    baseline = tuple(sorted(plans[-1]))
    used = [set(p[s] for p in baseline) for s in (0, 1)]
    missing = [[i for i, leaf in enumerate(v.leaves) if i not in used[s] and not leaf.opaque]
               for s, v in enumerate((a, b))]
    if not any(missing):
        return finish('no_supported_omission', plans)
    if sum(map(len, missing)) > OMISSION_LIMIT:
        return finish('omission_admission_limit', plans)

    # Compatible-domain indexes reopen all occupied candidates, independently of
    # reference top-k retrieval. Opaque leaves never enter the variable domain.
    domains = []
    for view in (a, b):
        index = defaultdict(list)
        for i, leaf in enumerate(view.leaves):
            if not leaf.opaque:
                index[boundary_key(leaf)].append(i)
        domains.append(index)
    def candidates(plan):
        mapping = dict(plan); inverse = {j: i for i, j in plan}
        for side, (view, used_side) in enumerate(((a, mapping), (b, inverse))):
            for u, leaf in enumerate(view.leaves):
                if u in used_side or leaf.opaque:
                    continue
                for v in domains[1 - side][boundary_key(leaf)]:
                    i, j = (u, v) if side == 0 else (v, u)
                    changed = dict(mapping)
                    if j in inverse:
                        del changed[inverse[j]]
                    changed[i] = j
                    yield tuple(sorted(changed.items()))

    def evaluate(plan):
        error, _ = net_alignment(a, b, plan)
        return error + .6 * (len(a.leaves) + len(b.leaves) - 2 * len(plan)), error
    # Baseline scoring and bounded seed scoring count against the same budget.
    scores = {}; beam = []
    for plan in [baseline, *(tuple(sorted(p)) for p in plans)]:
        if plan in scores:
            continue
        if len(scores) >= work_limit:
            break
        scores[plan] = evaluate(plan); beam.append(plan)
    initial_score, initial_error = scores[baseline]
    best = min(s[0] for s in scores.values())
    winners = [p for p in beam if abs(scores[p][0] - best) < 1e-9]
    evidence['seeds_truncated'] = len({tuple(sorted(p)) for p in plans}) > len(beam)
    evidence['beam_pruned'] = len(beam) > BEAM_WIDTH
    beam = sorted(beam, key=lambda p: (scores[p][0], p))[:BEAM_WIDTH]
    stop = 'depth_limit'
    for depth in range(DEPTH_LIMIT):
        next_beam = []; exhausted = False
        for plan in beam:
            for candidate in candidates(plan):
                if candidate in scores:
                    continue
                if len(scores) >= work_limit:
                    exhausted = True; break
                scores[candidate] = evaluate(candidate)
                value = scores[candidate][0]
                if value < best - 1e-9:
                    best = value; winners = []; evidence['alternatives_truncated'] = False
                if abs(value - best) < 1e-9:
                    winners.append(candidate)
                next_beam.append(candidate)
            if exhausted:
                break
        evidence['rounds'] = depth + 1
        if exhausted:
            stop = 'work_limit'; break
        if not next_beam:
            stop = 'neighborhood_exhausted'; break
        next_beam.sort(key=lambda p: (scores[p][0], p))
        evidence['beam_pruned'] |= len(next_beam) > BEAM_WIDTH
        beam = next_beam[:BEAM_WIDTH]
    # Keep the prior representative for ties. Improvements replace it and all
    # now-worse primary hypotheses; existing equal seeds remain valid evidence.
    selected = baseline if abs(initial_score - best) < 1e-9 else winners[0]
    # Spend the output cap first on different omitted-object sets, then on
    # permutations with the same omissions. All alternatives remain coupled.
    equal = [p for p in scores if abs(scores[p][0] - best) < 1e-9]
    def omitted_identity(plan):
        used_sides = [{p[side] for p in plan} for side in (0, 1)]
        return tuple(tuple(i for i in range(len(v.leaves)) if i not in used_sides[side])
                     for side, v in enumerate((a, b)))
    identities = {omitted_identity(selected)}; diverse = []; remainder = []
    for plan in equal:
        if plan == selected:
            continue
        identity = omitted_identity(plan)
        if identity not in identities:
            diverse.append(plan); identities.add(identity)
        else:
            remainder.append(plan)
    evidence['alternatives_truncated'] = len(equal) > RETAIN_LIMIT
    retained = (diverse + remainder)[:RETAIN_LIMIT - 1] + [selected]
    def paths(edges):
        return [[a.leaves[i].path, b.leaves[j].path] for i, j in sorted(edges)]
    evidence.update(work_used=len(scores), baseline_score=initial_score,
                    baseline_endpoint_disagreements=initial_error, best_score=best,
                    best_endpoint_disagreements=scores[selected][1],
                    score_improvement=initial_score - best,
                    baseline_pairs=paths(baseline), retained_hypotheses=len(retained))
    def witness(plan):
        return dict(removed_pairs=paths(set(baseline) - set(plan)),
                    added_pairs=paths(set(plan) - set(baseline)),
                    score=scores[plan][0], score_delta=scores[plan][0] - initial_score,
                    selected=plan == selected)
    evidence['witnesses'] = [witness(p) for p in retained if p != baseline]
    baseline_ties = [p for p in scores if p != baseline and
                     abs(scores[p][0] - initial_score) < 1e-9 and
                     omitted_identity(p) != omitted_identity(baseline)]
    evidence['baseline_tied_exchanges'] = [witness(p) for p in baseline_ties[:RETAIN_LIMIT]]
    evidence['baseline_ties_truncated'] = len(baseline_ties) > RETAIN_LIMIT
    evidence['challenges'] = []
    for side, indices in enumerate(missing):
        view = (a, b)[side]
        for index in indices:
            participating = []; omitted = []
            for plan, (score, _) in scores.items():
                (participating if any(edge[side] == index for edge in plan) else omitted).append(score)
            paired_score = min(participating, default=None)
            paired_plan = next((p for p, (s, _) in scores.items() if s == paired_score and
                                any(edge[side] == index for edge in p)), None)
            omitted_score = min(omitted, default=None)
            evidence['challenges'].append(dict(side='ab'[side], object=view.leaves[index].path,
                compatible_candidates=len(domains[1 - side][boundary_key(view.leaves[index])]),
                occupied_candidates=sum(v in used[1 - side] for v in domains[1 - side][boundary_key(view.leaves[index])]),
                best_participating_score=paired_score, best_omitted_score=omitted_score,
                participating_witness=witness(paired_plan) if paired_plan is not None else None,
                participation_margin=None if paired_score is None or omitted_score is None else paired_score - omitted_score))
    return finish(stop, [list(p) for p in retained])


def population(a, b, selected):
    """Inventory lower bounds in hard-compatible represented domains, not edits."""
    groups = defaultdict(lambda: [[], []])
    for side, view in enumerate((a, b)):
        for i, leaf in enumerate(view.leaves):
            if not leaf.opaque:
                groups[boundary_key(leaf)][side].append(i)
    rows = []
    used = [{edge[s] for edge in selected} for s in (0, 1)]
    for key, members in sorted(groups.items()):
        aa, bb = members
        if len(aa) == len(bb):
            continue
        counts = [len(aa), len(bb)]
        rows.append(dict(domain=key or 'represented_native_primitives',
                         count_a=counts[0], count_b=counts[1],
                         surplus_side='b' if counts[1] > counts[0] else 'a',
                         represented_surplus=abs(counts[1] - counts[0]),
                         selected_omissions_a=len(set(aa) - used[0]),
                         selected_omissions_b=len(set(bb) - used[1]),
                         path_examples_a=[a.leaves[i].path for i in aa[:4]],
                         path_examples_b=[b.leaves[i].path for i in bb[:4]]))
    return dict(groups=rows, scope='Whole selected comparison scope; groups are not subtree-filtered.',
                opaque_excluded_a=sum(bool(l.opaque) for l in a.leaves),
                opaque_excluded_b=sum(bool(l.opaque) for l in b.leaves),
                expansion_complete=not (a.budget_exhausted or b.budget_exhausted),
                meaning='Joint lower bound on omissions within each hard-compatible represented domain, irrespective of individual counterpart possibility. No exact new-instance identity, historical addition or hidden-internal count. Incomplete expansion restricts inventory to materialized scope.')
