"""Bounded closure of verified, whole-view structural symmetries.

Only complete zero-incidence-error alignments can supply generators. Parameters
and labels do not enter the verification. This expands supported alternatives;
it does not infer historical identity or certify the full automorphism group.
"""


def complete_closure(a, b, plans, limit=64):
    from .regional import net_alignment
    from .blackbox import compatible
    size = len(a.leaves)
    info = {'limit': limit, 'verified_generators': 0, 'added_hypotheses': 0,
            'truncated': False, 'scope': 'Closure of observed type/role/incidence automorphisms only; other structural symmetries may remain undiscovered.'}
    if len(plans) < 2 or size != len(b.leaves) or any(len(p) != size for p in plans):
        return plans, info
    if len(plans) >= limit:
        info['truncated'] = True
        return plans, info
    if any(net_alignment(a, b, p)[0] for p in plans):
        return plans, info
    maps = [tuple(j for _, j in sorted(plan)) for plan in plans]
    base = maps[0]; inverse = {j: i for i, j in enumerate(base)}
    identity = tuple(range(size)); generators = []
    for other in maps[1:]:
        permutation = tuple(inverse[j] for j in other)
        if permutation == identity or permutation in generators: continue
        if any(a.leaves[i].device.type.casefold() != a.leaves[j].device.type.casefold()
               or not compatible(a.leaves[i], a.leaves[j])
               for i, j in enumerate(permutation)): continue
        if net_alignment(a, a, list(enumerate(permutation)))[0] == 0:
            generators.append(permutation)
    info['verified_generators'] = len(generators)
    # Starting from all observed maps avoids dropping existing hypotheses when
    # the closure budget is exhausted. Composition of verified automorphisms
    # preserves typed role incidence without a new correspondence assumption.
    seen = set(maps); queue = list(maps); cursor = 0
    while cursor < len(queue):
        current = queue[cursor]; cursor += 1
        for g in generators:
            candidate = tuple(current[g[i]] for i in range(size))
            if candidate in seen: continue
            if len(queue) >= limit:
                info['truncated'] = True; continue
            seen.add(candidate); queue.append(candidate)
    info['added_hypotheses'] = len(queue) - len(maps)
    return [list(enumerate(p)) for p in queue], info
