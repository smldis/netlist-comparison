"""Bounded region graph edit search, independently designed for this prototype.

A beam carries competing partial injective maps. There are no frozen anchors.
Connector roles and interface incidence are fallible relational evidence;
labels and parameter values do not contribute. This is not exact graph edit
distance or a reproduction of FAQ/FUGAL or IP-Matcher.
"""
from collections import Counter, defaultdict

import numpy as np

LOCAL_LIMIT = 128
REGION_LIMIT = 64
BEAM_WIDTH = 192
REFINE_LIMIT = 24


def partition(view):
    """Largest populated occurrences below the local limit, skipping wrappers.

    Oversized occurrences are opened; their direct primitives become residual
    connectors. This frontier can have mixed depths and need not have equal
    cardinality across revisions. It does not solve arbitrary split/merge.
    """
    selected = []
    for o in sorted(view.occurrences, key=lambda o: o['depth']):
        if not o['depth'] or not o['leaf_count'] or o['leaf_count'] > LOCAL_LIMIT:
            continue
        if not any(o['path'].startswith(p['path'] + '/') for p in selected):
            selected.append(o)
    members = [[i for i, l in enumerate(view.leaves) if o['path'] in l.ancestors]
               for o in selected]
    used = {i for row in members for i in row}
    residual = [i for i in range(len(view.leaves)) if i not in used]
    return selected, members, residual


def graph(view, regions, members, residual):
    ports = defaultdict(list)
    for i, o in enumerate(regions):
        # A set of resolved interface nets: declaration order and duplicate
        # aliases carry no graph identity. Names only resolve local bindings.
        for net in set(o['bindings'].values()):
            ports[net].append(i)
    edges = defaultdict(Counter)
    # Direct shared interfaces, excluding dense buses from search only.
    for owners in ports.values():
        if 1 < len(owners) <= 8:
            for i in owners:
                for j in owners:
                    if i != j:
                        edges[i, j]['shared'] += 1
    # Residual devices can link regions regardless of their hierarchy depth.
    for index in residual:
        leaf = view.leaves[index]
        if leaf.opaque:
            continue
        endpoints = [(role.casefold(), ports[net][0]) for role, net in leaf.nets.items()
                     if len(ports[net]) == 1]
        for role, i in endpoints:
            for other, j in endpoints:
                if i != j:
                    edges[i, j]['device', role, other] += 1
    profiles = []
    for indices in members:
        # Soft multiset differences permit primitive replacement and local edits.
        profiles.append(Counter(view.leaves[i].device.type.casefold() for i in indices))
    return edges, profiles


def search(ga, gb, sizes_a, sizes_b):
    """Return bounded competing maps, including optional unmatched regions.

    The frontier estimate counts still-unexplained incident relation channels.
    It is a heuristic ranking term, not a certified lower bound. Ties at the
    beam boundary can depend on traversal order and are reported as truncation.
    """
    ea, pa = ga; eb, pb = gb
    na, nb = len(pa), len(pb)
    keys = sorted({k for e in (ea, eb) for row in e.values() for k in row}, key=repr)
    channels = {k: i for i, k in enumerate(keys)}
    def tensor(edges, n):
        out = np.zeros((n + 1, n + 1, max(1, len(keys))))
        for (i, j), values in edges.items():
            for k, count in values.items():
                out[i, j, channels[k]] = count
        return out
    aa, bb = tensor(ea, na), tensor(eb, nb)
    unary = np.array([[.08 * sum(abs(x[k] - y[k]) for k in x.keys() | y.keys())
                      for y in pb] for x in pa])
    # Charge per unmatched region plus its size; a missing populated bank is
    # allowed but cannot cheaply hide many changed endpoints.
    ua = 2 + np.asarray(sizes_a) / 16
    ub = 2 + np.asarray(sizes_b) / 16
    degree = aa.sum(axis=(1, 2))[:na]
    # Prefer a sparse boundary then follow the populated frontier. Reverse
    # search is supplied by the caller to reduce fixed-side ordering bias.
    remaining = set(range(na)); order = []
    while remaining:
        if not order:
            chosen = min(remaining, key=lambda i: (degree[i] == 0, degree[i], i))
        else:
            chosen = min(remaining, key=lambda i: (-aa[i, order].sum(), degree[i], i))
        order.append(chosen); remaining.remove(chosen)
    # State is (committed cost, assigned B indices in A traversal order).
    beam = [(0., ())]; truncated = False; tie_truncated = False
    expanded = 0
    for depth, i in enumerate(order):
        prior = order[:depth]; future = order[depth + 1:]
        candidates = []
        demand_a = aa[order[:depth + 1]][:, future].sum(axis=1)
        for cost, mapping in beam:
            available = [j for j in range(nb) if j not in mapping] + [nb]
            js = np.asarray(available)
            increments = np.r_[unary[i] - ub, ua[i]][js].copy()
            if prior:
                increments += np.abs(aa[i, prior][None, :, :] - bb[js[:, None], np.array(mapping)[None, :]]).sum(axis=(1, 2))
            free = available[:-1]
            prior_demand = bb[list(mapping)][:, free].sum(axis=1)
            demands = np.empty((len(js), depth + 1, aa.shape[2]))
            if prior:
                demands[:, :depth] = prior_demand[None, :, :] - bb[np.array(mapping)[None, :], js[:, None]]
            demands[:, depth] = bb[js][:, free].sum(axis=1)
            estimates = .5 * np.abs(demand_a[None, :, :] - demands).sum(axis=(1, 2))
            for j, delta, estimate in zip(available, increments, estimates):
                committed = cost + float(delta)
                candidates.append((committed + float(estimate), committed, mapping + (j,)))
        expanded += len(candidates)
        candidates.sort(key=lambda row: (row[0], row[2]))
        if len(candidates) > BEAM_WIDTH:
            truncated = True
            tie_truncated |= abs(candidates[BEAM_WIDTH - 1][0] - candidates[BEAM_WIDTH][0]) < 1e-9
        beam = [(cost, mapping) for _, cost, mapping in candidates[:BEAM_WIDTH]]
    results = []
    for cost, mapping in sorted(beam):
        pairs = tuple(sorted((i, j) for i, j in zip(order, mapping) if j != nb))
        results.append((cost + float(ub.sum()), pairs))
    return results[:REFINE_LIMIT], {'expanded': expanded, 'beam_truncated': truncated,
                                   'tie_truncated': tie_truncated}
