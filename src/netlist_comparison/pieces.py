"""A hierarchy-independent candidate frontier over expanded physical leaves.

Multi-terminal cores connect through sparse non-gate-only nets. Two-terminal
objects join an unambiguous core or remain residual connectors. This structural
heuristic does not infer circuit function, evaluate values, or collapse copies.
"""
from collections import defaultdict
from .coarse import LOCAL_LIMIT, REGION_LIMIT


def connectivity_frontier(view):
    cores = {i for i, leaf in enumerate(view.leaves) if not leaf.opaque and len(leaf.nets) >= 3}
    if not cores:
        return None
    parent = {i: i for i in cores}
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    def union(a, b):
        a, b = find(a), find(b)
        if a != b: parent[b] = a
    excluded = {n for n, es in view.nets.items()
                if n.startswith('global:') or len({i for i, _ in es}) > 32}
    core_roles = {}
    for net, endpoints in view.nets.items():
        es = [(i, r.casefold()) for i, r in endpoints if i in cores]
        core_roles[net] = {r for _, r in es} - {'b'}
        # A common gate fanout is weak grouping evidence, even below the dense
        # threshold. Body/supply incidence remains in final validation.
        if net in excluded or core_roles[net] <= {'g'}:
            continue
        for i, _ in es[1:]: union(es[0][0], i)
    groups = defaultdict(list)
    for i in sorted(cores): groups[find(i)].append(i)
    owners = defaultdict(set)
    for i in cores:
        for net in view.leaves[i].nets.values():
            if net not in excluded: owners[net].add(find(i))
    for i, leaf in enumerate(view.leaves):
        if i in cores or leaf.opaque: continue
        ns = set(leaf.nets.values()) - excluded
        choices = set().union(*(owners[n] for n in ns))
        # Do not grow greedily through an unresolved passive chain: that would
        # make a newly created region boundary depend on traversal order.
        supported = all(owners[n] or len({j for j, _ in view.nets[n]}) == 1 for n in ns)
        if len(choices) == 1 and supported:
            groups[next(iter(choices))].append(i)
    members = sorted((sorted(ii) for ii in groups.values()), key=lambda ii: ii[0])
    if len(members) > REGION_LIMIT or any(len(ii) > LOCAL_LIMIT for ii in members):
        return None
    regions = []
    for k, ii in enumerate(members):
        inside = set(ii)
        touched = {n for i in ii for n in view.leaves[i].nets.values()}
        ports = sorted(n for n in touched if n in excluded or
                       any(i not in inside for i, _ in view.nets[n]) or
                       len(core_roles[n]) == 1)
        regions.append({'path': f'@connectivity/{k}', 'kind': 'connectivity_piece',
                        'interface_nets': ports, 'bindings': {str(j): n for j, n in enumerate(ports)},
                        'member_paths': [view.leaves[i].path for i in ii]})
    used = {i for ii in members for i in ii}
    return regions, members, [i for i in range(len(view.leaves)) if i not in used]


def frontier_memberships(a, b, plans):
    """Compact conditional many-to-many authored membership for each leaf map.

    Search pieces may cross these boundaries. No historical split/merge event
    is inferred; each row refers to the complete hypothesis at the same index.
    """
    from collections import Counter
    from .coarse import partition
    def owners(view):
        regions, members, _ = partition(view)
        return {i: region['path'] for region, ii in zip(regions, members) for i in ii}
    oa, ob = owners(a), owners(b)
    result = []
    for k, plan in enumerate(plans):
        counts = Counter((oa[i], ob[j]) for i, j in plan if i in oa and j in ob)
        result.append({'hypothesis': k, 'basis': 'conditional_physical_leaf_membership',
                       'memberships': [{'a': p, 'b': q, 'paired_leaves': n} for (p, q), n in sorted(counts.items())]})
    return result
