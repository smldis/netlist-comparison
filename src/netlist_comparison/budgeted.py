"""Budgeted incidence search and verified repeated-component factorization.

Names and raw values never rank correspondence. A net-map beam uses optional
leaf assignment as an optimistic partial-map bound. Component factors are only
accepted after exact typed role incidence, with shared boundary nets fixed, has
been checked. Neither mechanism establishes historical identity.
"""
from collections import Counter, defaultdict
from dataclasses import dataclass
from time import perf_counter

import numpy as np
from scipy.optimize import linear_sum_assignment

from .context import digest
from .model import View
from .blackbox import key as black_box_key


@dataclass
class Work:
    limit: int
    used: int = 0
    exhausted: bool = False

    def take(self):
        if self.used >= self.limit:
            self.exhausted = True
            return False
        self.used += 1
        return True

    def report(self):
        return {'limit': self.limit, 'used': self.used, 'exhausted': self.exhausted,
                'unit': 'net-map candidate assignments and component certificates',
                'scope': 'New incidence/factor search only; legacy frontier search, expansion and reporting excluded. Not a time or RSS cap.'}


def subview(view, indices):
    result = View(leaves=[view.leaves[i] for i in indices])
    for i, leaf in enumerate(result.leaves):
        for role, net in leaf.nets.items():
            result.nets.setdefault(net, []).append((i, role.casefold()))
    return result


def incidence_search(a, b, work, *, fixed=(), width=64):
    """Search injective partial net maps; every returned leaf map is feasible.

    Unknown nets incur no disagreement in the bound. Null net/leaf choices allow
    additions/removals. Full-role scoring of incumbents is independent of that
    bound. Beam truncation is explicit; this is not a global optimality proof.
    """
    from .regional import net_alignment
    na, nb = len(a.leaves), len(b.leaves)
    if not na or not nb or max(na, nb) > 64 or max(len(a.nets), len(b.nets)) > 64:
        return [], {'stop': 'local_incidence_admission', 'beam_truncated': False}
    an, bn = list(a.nets), list(b.nets)
    ai, bi = {n: i for i, n in enumerate(an)}, {n: i for i, n in enumerate(bn)}
    roles = sorted({r.casefold() for v in (a, b) for leaf in v.leaves for r in leaf.nets})
    def arrays(view, index):
        return np.array([[index.get({r.casefold(): n for r, n in leaf.nets.items()}.get(role), -1)
                          for role in roles] for leaf in view.leaves])
    ax, bx = arrays(a, ai), arrays(b, bi)
    types = np.array([x.device.type.casefold() for x in a.leaves])[:, None] != np.array([x.device.type.casefold() for x in b.leaves])[None, :]
    base = .12 * types - 1.2
    for r in range(len(roles)):
        base += (ax[:, r, None] < 0) != (bx[None, :, r] < 0)
    forbidden = np.array([bool(x.opaque) for x in a.leaves])[:, None] | np.array([bool(x.opaque) for x in b.leaves])[None, :]
    forbidden |= (np.array([black_box_key(x) for x in a.leaves])[:, None] !=
                  np.array([black_box_key(x) for x in b.leaves])[None, :])
    def assignment(mapping):
        am = np.full(len(an) + 1, -3); bm = np.full(len(bn) + 1, -3)
        for u, v in mapping:
            am[u] = v
            if v >= 0: bm[v] = u
        cost = base.copy()
        for r in range(len(roles)):
            ar, br = ax[:, r, None], bx[None, :, r]
            cost += (ar >= 0) & (br >= 0) & (((am[ar] != -3) & (am[ar] != br)) |
                                                          ((bm[br] != -3) & (bm[br] != ar)))
        cost[forbidden] = 1e6
        matrix = np.zeros((na, nb + na)); matrix[:, :nb] = cost
        rr, cc = linear_sum_assignment(matrix)
        pairs = tuple((int(i), int(j)) for i, j in zip(rr, cc) if j < nb)
        return float(matrix[rr, cc].sum() + .6 * (na + nb)), pairs
    apro = [Counter((r.casefold(), a.leaves[i].device.type.casefold()) for i, r in a.nets[n]) for n in an]
    bpro = [Counter((r.casefold(), b.leaves[i].device.type.casefold()) for i, r in b.nets[n]) for n in bn]
    distances = [[sum(abs(x[k] - y[k]) for k in x.keys() | y.keys()) for y in bpro] for x in apro]
    initial = tuple((ai[u], bi[v]) for u, v in fixed if u in ai and v in bi)
    remaining = set(range(len(an))) - {u for u, _ in initial}
    order = []; seen = {i for u, _ in initial for i, _ in a.nets[an[u]]}
    while remaining:
        u = max(remaining, key=lambda n: (-distances[n].count(min(distances[n])),
                                         len({i for i, _ in a.nets[an[n]]} & seen), len(a.nets[an[n]])))
        order.append(u); remaining.remove(u); seen.update(i for i, _ in a.nets[an[u]])
    score, pairs = assignment(initial)
    states = [(score, initial, pairs)]; incumbents = {}; truncated = False
    def remember(plan):
        if plan not in incumbents:
            error, _ = net_alignment(a, b, plan)
            incumbents[plan] = (error + .6 * (na + nb - 2 * len(plan)), sum(types[i, j] for i, j in plan))
    remember(pairs)
    completed = 0
    for u in order:
        candidates = []
        for _, mapping, _ in states:
            used = {v for _, v in mapping}
            # Degree profiles only order work; no compatible candidate is vetoed.
            targets = sorted(set(range(len(bn))) - used, key=lambda v: distances[u][v]) + [-2]
            for v in targets:
                if not work.take(): break
                mapped = (*mapping, (u, v))
                score, pairs = assignment(mapped)
                candidates.append((score, mapped, pairs))
            if work.exhausted: break
        if not candidates: break
        candidates.sort(key=lambda row: (row[0], row[1]))
        truncated |= len(candidates) > width
        states = candidates[:width]
        # Completed states are actual candidates; the best partial-bound state
        # also supplies a feasible incumbent if the budget stops before a leaf.
        remember(states[0][2])
        if work.exhausted: break
        completed += 1
    for _, _, pairs in states: remember(pairs)
    best = min(incumbents.values())
    plans = [list(p) for p, score in incumbents.items() if score == best]
    return plans[:24], {'stop': 'work_budget' if work.exhausted else 'bounded_net_search',
                        'beam_width': width, 'beam_truncated': truncated,
                        'completed_net_levels': completed, 'net_levels': len(order),
                        'incumbents_scored': len(incumbents), 'alternatives_truncated': len(plans) > 24,
                        'search_type_penalty': .12, 'final_type_tiebreak': True}


def components(view):
    """Cut only explicit globals and high-degree nets; retain them as boundaries."""
    excluded = {n for n, es in view.nets.items() if n.startswith('global:') or len({i for i, _ in es}) > 32}
    parent = list(range(len(view.leaves)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for n, es in view.nets.items():
        if n in excluded: continue
        for i, _ in es[1:]: parent[find(i)] = find(es[0][0])
    groups = defaultdict(list)
    for i in range(len(parent)): groups[find(i)].append(i)
    return list(groups.values()), excluded


def certificate(view, indices, boundary):
    """WL orders singleton roles; the resulting exact incidence code certifies.

    WL collisions and repeated labels cannot create a certificate: repeated
    labels abstain; exact code includes all roles, types and boundary incidence.
    """
    local = subview(view, indices)
    labels = [digest([l.device.type.casefold(), sorted(r.casefold() for r in l.nets)]) for l in local.leaves]
    for _ in range(4):
        nets = {n: ('boundary', boundary[n]) if n in boundary else ('inside', sorted((r, labels[i]) for i, r in es))
                for n, es in local.nets.items()}
        labels = [digest([labels[i], sorted((r.casefold(), nets[n]) for r, n in l.nets.items())])
                  for i, l in enumerate(local.leaves)]
    if len(set(labels)) != len(labels) or any(l.opaque for l in local.leaves): return None
    order = sorted(range(len(indices)), key=lambda i: labels[i])
    internal = {}; rows = []
    for i in order:
        leaf = local.leaves[i]; endpoints = []
        for r, n in sorted(leaf.nets.items()):
            if n not in boundary and n not in internal: internal[n] = len(internal)
            endpoints.append((r.casefold(), ('boundary', boundary[n]) if n in boundary else ('inside', internal[n])))
        row = (leaf.device.type.casefold(), tuple(endpoints))
        rows.append(row + (black_box_key(leaf),) if leaf.black_box else row)
    return tuple(rows), [indices[i] for i in order]


def factor_match(a, b, work):
    """Cancel certified repeated pieces, then solve the small edited remainder.

    This factorization is used only when both full graphs split into small
    components. Opaque components cannot certify, but do not veto other pieces.
    All retained maps undergo a final whole-graph incidence check.
    Component permutations are recorded as factors, not silently made unique.
    """
    ma, ba = components(a); mb, bb = components(b)
    info = {'components_a': len(ma), 'components_b': len(mb), 'stop': 'factor_not_applicable'}
    if min(len(ma), len(mb)) < 2 or max(map(len, ma + mb), default=0) > 64 or max(len(ba), len(bb)) > 8:
        return [], info
    # A boundary assignment is a hypothesis. Equal profile ambiguity abstains;
    # final validation never deletes body/supply endpoints.
    ba, bb = sorted(ba), sorted(bb)
    if len(ba) != len(bb): return [], info
    profile = lambda v, n: Counter(r.casefold() for _, r in v.nets[n])
    pa, pb = [profile(a, n) for n in ba], [profile(b, n) for n in bb]
    distance = lambda x, y: sum(abs(x[k] - y[k]) for k in x.keys() | y.keys())
    costs = np.array([[distance(x, y) for y in pb] for x in pa])
    if ba:
        rr, cc = linear_sum_assignment(costs)
        if any(sum(costs[i] == costs[i, j]) > 1 for i, j in zip(rr, cc)): return [], info
        boundary_a = {ba[i]: int(i) for i in rr}; boundary_b = {bb[j]: int(i) for i, j in zip(rr, cc)}
        fixed = [(ba[i], bb[j]) for i, j in zip(rr, cc)]
    else: boundary_a = {}; boundary_b = {}; fixed = []
    # Interleave certificates so an exhausted budget can retain a paired prefix.
    groups = [defaultdict(list), defaultdict(list)]
    opaque_components = [0, 0]
    for k in range(max(len(ma), len(mb))):
        for side, (view, members, boundary) in enumerate(((a, ma, boundary_a), (b, mb, boundary_b))):
            if k >= len(members): continue
            if not work.take(): break
            if any(view.leaves[i].opaque for i in members[k]):
                opaque_components[side] += 1
                continue
            cert = certificate(view, members[k], boundary)
            if cert is None: return [], dict(info, stop='non_singleton_component_certificate')
            key, order = cert; groups[side][key].append(order)
        if work.exhausted: break
    ga, gb = groups; plan = []; used_a = set(); used_b = set()
    for key in sorted(ga.keys() & gb.keys(), key=repr):
        for ia, ib in zip(ga[key], gb[key]):
            plan.extend(zip(ia, ib)); used_a.update(ia); used_b.update(ib)
    # A largely unexplained graph goes back to the multi-frontier matcher.
    # Opaque leaves remain in the original view, coverage and final unmatched
    # cost. They have no admissible assignment and must not consume the local
    # known-structure admission limit. Known neighbours of opaque leaves can
    # still participate in the remainder search without certifying that piece.
    ra = [i for i in range(len(a.leaves)) if i not in used_a and not a.leaves[i].opaque]
    rb = [i for i in range(len(b.leaves)) if i not in used_b and not b.leaves[i].opaque]
    if not plan or (max(len(ra), len(rb)) > 64 and not work.exhausted):
        return [], dict(info, stop='large_factor_remainder')
    variants, search = incidence_search(subview(a, ra), subview(b, rb), work, fixed=fixed) if ra and rb and not work.exhausted else ([[]], {'stop': 'work_budget' if work.exhausted else 'empty_remainder'})
    if not variants: variants = [[]]
    plans = [sorted(plan + [(ra[i], rb[j]) for i, j in variant]) for variant in variants]
    # Certified component permutations on either side generate coupled leaf
    # alternatives. The slot lists are linear-size, unlike their pair expansion.
    factors = []
    for side, indexed, view in (('a', ga, a), ('b', gb, b)):
        for rows in indexed.values():
            if len(rows) > 1:
                factors.append({'side': side, 'components': [[view.leaves[i].path for i in row] for row in rows],
                                'basis': 'exact_typed_role_incidence_with_fixed_shared_boundary',
                                'scope': 'represented_terminal_incidence_only; opaque internals and unrepresented attachments excluded',
                                'constraint': 'permute_whole_components; corresponding_slots_move_together'})
    info.update(stop='work_budget' if work.exhausted else 'bounded_component_factors', exact_pairs=len(plan), remainder_a=len(ra), remainder_b=len(rb),
                opaque_components_a=opaque_components[0], opaque_components_b=opaque_components[1],
                remainder_search=search, component_permutation_factors=factors,
                boundary_hypothesis=[{'a': u, 'b': v} for u, v in fixed])
    return plans, info


def factor_regions(a, b, plans, factors):
    """Apply certified side orbits to each retained map, without closing maps.

    Different edited hypotheses are not themselves symmetry generators. Only
    the independently certified component permutations can expand their pairs.
    """
    orbit = {}; members = {}
    for side, view in (('a', a), ('b', b)):
        for leaf in view.leaves:
            key = (side, leaf.path); orbit[key] = key; members[key] = [leaf.path]
    for factor in factors:
        side = factor['side']
        for slot in zip(*factor['components']):
            key = (side, slot[0]); members[key] = list(slot)
            for path in slot: orbit[side, path] = key
    choices = defaultdict(set)
    for plan in plans:
        for i, j in plan:
            choices[orbit['a', a.leaves[i].path]].add(orbit['b', b.leaves[j].path])
    grouped = defaultdict(list)
    for source, targets in choices.items(): grouped[tuple(sorted(targets))].extend(members[source])
    return [{'a': sorted(paths), 'b': sorted({p for key in targets for p in members[key]}),
             'basis': 'certified_component_permutation_orbit',
             'constraint': 'coupled_whole_component_permutations; see component_permutation_factors',
             'alternatives_complete': False} for targets, paths in grouped.items()]
