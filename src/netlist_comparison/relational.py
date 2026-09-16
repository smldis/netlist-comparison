"""Bounded role-aware anchor growth, adapted from IP-Matcher Algorithms 1/3.

Independent implementation from the paper, not author code. The published
prime-product hash, greedy neighbour binding and IP covering are NOT reproduced.
We use role-labelled WL hashes, mutual unique support, explicit abstention and
acyclic round provenance. Dense nets remain intact in the reporting view.
"""
from collections import Counter, defaultdict
from time import perf_counter

from .context import digest
from .blackbox import key as black_box_key, compatible


def structural_labels(view, depth, degree_limit):
    dense = {net for net, es in view.nets.items() if len({i for i, _ in es}) > degree_limit}
    labels = [digest([leaf.device.type.casefold(), sorted(r.casefold() for r in leaf.nets), bool(leaf.opaque)]
                     + ([black_box_key(leaf)] if leaf.black_box else []))
              for leaf in view.leaves]
    history = [labels]
    for _ in range(depth):
        nets = {net: digest(['dense']) if net in dense else
                digest(sorted((role.casefold(), labels[i]) for i, role in endpoints))
                for net, endpoints in view.nets.items()}
        labels = [digest([labels[i], sorted((r.casefold(), nets[n]) for r, n in leaf.nets.items())])
                  for i, leaf in enumerate(view.leaves)]
        history.append(labels)
    return history, dense


def match_views(a, b, *, depth=3, rounds=64, degree_limit=32, max_candidates=200000):
    start = perf_counter()
    ha, dense_a = structural_labels(a, depth, degree_limit)
    hb, dense_b = structural_labels(b, depth, degree_limit)
    def index(labels, view):
        out = defaultdict(list)
        for i, label in enumerate(labels):
            if not view.leaves[i].opaque:
                out[label].append(i)
        return out
    ia, ib = index(ha[-1], a), index(hb[-1], b)
    pairs, used_a, used_b = [], {}, {}
    def add(i, j, evidence):
        pid = f'p{len(pairs)}'
        pairs.append({'id': pid, 'i': i, 'j': j, **evidence})
        used_a[i] = used_b[j] = pid
    for label in sorted(ia.keys() & ib.keys()):
        if len(ia[label]) == len(ib[label]) == 1:
            i, j = ia[label][0], ib[label][0]
            # An isolated device's type/role signature is not identity support.
            if any(len({k for k, _ in a.nets[n]}) > 1 and n not in dense_a for n in a.leaves[i].nets.values()):
                add(i, j, {'basis': 'unique_role_wl', 'round': 0, 'signature': label, 'support_pairs': []})
    seeds = len(pairs)
    history = [{'round': 0, 'accepted': seeds}]
    candidate_work = 0
    final_ties = []
    stop = 'fixed_point'

    def contexts(view, used, dense):
        net_support = {}
        for net, endpoints in view.nets.items():
            if net not in dense:
                net_support[net] = {(used[i], r.casefold()) for i, r in endpoints if i in used}
        result = {}
        for i, leaf in enumerate(view.leaves):
            if i in used or leaf.opaque:
                continue
            tokens = {(r.casefold(), pid, role) for r, net in leaf.nets.items()
                      for pid, role in net_support.get(net, ())}
            if tokens:
                result[i] = tokens
        return result

    for round_id in range(1, rounds + 1):
        ca, cb = contexts(a, used_a, dense_a), contexts(b, used_b, dense_b)
        inverted = defaultdict(set)
        for j, tokens in cb.items():
            for token in tokens:
                inverted[token].add(j)
        scores = {}
        for i, tokens in ca.items():
            possible = set().union(*(inverted[t] for t in tokens))
            for j in sorted(possible):
                candidate_work += 1
                if candidate_work > max_candidates:
                    stop = 'candidate_budget'
                    break
                la, lb = a.leaves[i], b.leaves[j]
                if not compatible(la, lb):
                    continue
                if la.device.type.casefold() != lb.device.type.casefold() or {r.casefold() for r in la.nets} != {r.casefold() for r in lb.nets}:
                    continue
                overlap = tokens & cb[j]
                # Dice over independently frozen earlier pairs. No new pair votes
                # for itself, or another pair accepted in this round.
                score = 2 * len(overlap) / (len(tokens) + len(cb[j]))
                if score >= 0.8:
                    scores[i, j] = (score, overlap)
            if stop == 'candidate_budget':
                break
        if stop == 'candidate_budget':
            break  # Never accept from a partially traversed round.
        best_a, best_b = defaultdict(list), defaultdict(list)
        for (i, j), (score, _) in scores.items():
            best_a[i].append((score, j))
            best_b[j].append((score, i))
        def best(rows):
            result = {}
            for i, values in rows.items():
                high = max(s for s, _ in values)
                result[i] = [j for s, j in values if s >= high - 1e-12]
            return result
        ba, bb = best(best_a), best(best_b)
        accepted = [(i, js[0]) for i, js in ba.items() if len(js) == 1 and bb[js[0]] == [i]]
        final_ties = [{'a': [a.leaves[i].path], 'b': [b.leaves[j].path for j in sorted(js)],
                       'reason': 'non_unique_supported_growth', 'constraint': 'one_to_one_leaf_pairs'}
                      for i, js in sorted(ba.items()) if len(js) > 1 or bb[js[0]] != [i]]
        history.append({'round': round_id, 'accepted': len(accepted), 'candidate_edges': len(scores)})
        if not accepted:
            break
        for i, j in sorted(accepted):
            score, overlap = scores[i, j]
            add(i, j, {'basis': 'prior_round_terminal_support', 'round': round_id,
                       'support_pairs': sorted({pid for _, pid, _ in overlap}),
                       'support_tokens': sorted(overlap), 'support_dice': score})
    else:
        stop = 'round_budget'
    return pairs, {'method': 'role_wl_anchor_growth_experiment', 'wl_depth': depth,
                   'growth_round_limit': rounds, 'dense_net_degree_limit': degree_limit,
                   'candidate_work_limit': max_candidates,
                   'dense_nets_search_suppressed': {'a': sorted(dense_a), 'b': sorted(dense_b)},
                   'seed_count': seeds, 'rounds': history, 'stop': stop,
                   'candidate_work': candidate_work, 'unresolved_growth_options': final_ties,
                   'seconds': perf_counter() - start}


def apply_growth_report(result, a, b, options):
    """Replace proposals, retaining v1 retrieval as explicitly excluded alternatives."""
    from .report import pair_record, connectivity, hierarchy
    from dataclasses import asdict

    selected, evidence = match_views(a, b, rounds=options.growth_rounds,
                                      max_candidates=min(200000, options.max_pair_scores))
    old_groups = result['groups']
    ca = {path: c['id'] for c in result['a']['classes'] for path in c['members']}
    cb = {path: c['id'] for c in result['b']['classes'] for path in c['members']}
    ga = {cid: g for g in old_groups for cid in g['a_classes']}
    for g in old_groups:
        g['reference_assignment_domain'] = g.pop('assignment_domain')
        g['hypotheses'] = []
        g['status'] = 'unresolved'
        g['proposal_domain'] = 'physical leaves; bounded role-aware anchor growth; reference candidate alternatives remain visible'
        for key in ('objective', 'selected_edge_checks', 'selected_edges_checked', 'candidate_truncated'):
            g.pop(key, None)
    records = []
    for row in selected:
        la, lb = a.leaves[row['i']], b.leaves[row['j']]
        group = ga.get(ca[la.path])
        if group is None or cb[lb.path] not in group['b_classes']:
            group = {'id': f'growth{len(old_groups)}', 'a_classes': [ca[la.path]], 'b_classes': [cb[lb.path]],
                     'relation': None, 'constraint': 'one_to_one_leaf_pairs', 'alternatives_complete': False,
                     'hypotheses': [], 'reasons': ['outside_reference_candidate_component']}
            old_groups.append(group)
        group['status'] = 'partial'
        if not group['hypotheses']:
            group['hypotheses'] = [[]]
        group['hypotheses'][0].append(row['id'])
        record = pair_record(la, lb, row['id'], group['id'], 1 - row.get('support_dice', 1))
        record.update(status='representative', correspondence='tentative',
                      cost_basis='one minus growth support Dice; zero for exact unique WL anchors',
                      evidence={k: v for k, v in row.items() if k not in ('id', 'i', 'j')})
        records.append(record)
    for side in ('a', 'b'):
        paired = {r[side]: r for r in records}
        for row in result[side]['disposition']:
            if row['object'] in paired:
                row.update(status='tentative', group=paired[row['object']]['group'], reason='conditional_anchor_growth_proposal')
            elif row['status'] != 'opaque':
                row.update(status='unresolved', reason='anchor_growth_abstained; reference candidates remain visible')
        result[side]['coverage'] = dict.fromkeys(('tentative', 'ambiguous', 'unresolved', 'unpaired', 'opaque'), 0)
        for row in result[side]['disposition']:
            result[side]['coverage'][row['status']] += 1
    # Compact tied neighbour options by identical counterpart sets. These are
    # conditional shortlists, not deletion of the broader reference alternatives.
    regions = {}
    paired_a, paired_b = {r['a'] for r in records}, {r['b'] for r in records}
    for row in evidence.pop('unresolved_growth_options'):
        left = [p for p in row['a'] if p not in paired_a]
        right = tuple(p for p in row['b'] if p not in paired_b)
        if left and right:
            regions.setdefault(right, []).extend(left)
    region_rows = [{'a': sorted(set(aa)), 'b': list(bb), 'basis': 'tied_prior_pair_terminal_support',
                    'constraint': 'one_to_one_leaf_pairs', 'alternatives_complete': False}
                   for bb, aa in sorted(regions.items())]
    covered = {p for r in region_rows for p in r['a']}
    ha, _ = structural_labels(a, 3, 32)
    hb, _ = structural_labels(b, 3, 32)
    aa, bb = defaultdict(list), defaultdict(list)
    for i, l in enumerate(a.leaves):
        if l.path not in paired_a and l.path not in covered and not l.opaque:
            aa[ha[-1][i]].append(l.path)
    for i, l in enumerate(b.leaves):
        if l.path not in paired_b and not l.opaque:
            bb[hb[-1][i]].append(l.path)
    for label in sorted(aa.keys() & bb.keys()):
        region_rows.append({'a': aa[label], 'b': bb[label], 'basis': 'equal_role_wl_unresolved',
                            'constraint': 'one_to_one_leaf_pairs', 'alternatives_complete': False})
    evidence.update(joint_hypothesis=[r['id'] for r in records],
                    uncertainty='All growth is conditional on earlier tentative anchors. No rollback or optimality claim. Unexplored reference alternatives remain visible.',
                    regions_meaning='Conditional inspection shortlists; not exhaustive candidate regions or proven automorphism orbits')
    result.update(algorithm='role_wl_anchor_growth_experiment', options=asdict(options),
                  candidate_basis='v1 reference retrieval, retained even when excluded by the growth heuristic',
                  pair_options=records, representative_pair_ids=[r['id'] for r in records],
                  connectivity=connectivity(a, b, records), hierarchy=hierarchy(a, b, records),
                  relational=evidence, inspection_regions=region_rows)
    result['metrics']['seconds']['growth'] = evidence['seconds']
    result['metrics']['reference_assignment_calls'] = result['metrics'].pop('assignment_calls')
    result['metrics']['reference_alternative_calls'] = result['metrics'].pop('alternative_calls')
    result['metrics']['assignment_calls'] = result['metrics']['alternative_calls'] = 0
    return result
