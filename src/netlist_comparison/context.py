"""One frozen structural step, computed independently within each revision.

No seed pairs, attributes, paths, hierarchy or iterative labels enter scoring.
The commutative bag fingerprint avoids a quadratic clique on high-degree nets.
Hash equality is a search hint, never a proof of graph identity.
"""
from collections import defaultdict
import hashlib
import json
import math

import numpy as np

from .candidates import FeatureClass

MODULUS = 1 << 256


def digest(value):
    return hashlib.sha256(json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def refine(view, classes):
    signatures = {}
    base_for_leaf = {}
    records = []
    for c in classes:
        tag = digest([c.type, c.vector.tolist(), c.supported])
        records.append({"signature": tag, "members": [view.leaves[i].path for i in c.members]})
        for i in c.members:
            signatures[i] = tag
            base_for_leaf[i] = c
    bags = {}
    own = defaultdict(int)
    own_count = defaultdict(int)
    for net, endpoints in view.nets.items():
        total = 0
        for i, role in endpoints:
            value = int(digest([signatures[i], role.casefold()]), 16)
            total += value
            own[i, net] += value
            own_count[i, net] += 1
        bags[net] = (total % MODULUS, len(endpoints), len({i for i, _ in endpoints}))
    grouped = {}
    for i, leaf in enumerate(view.leaves):
        context = []
        for role, net in sorted(leaf.nets.items(), key=lambda item: item[0].casefold()):
            total, count, degree = bags[net]
            count -= own_count[i, net]
            tag = f"{(total - own[i, net]) % MODULUS:064x}"
            context.append((role.casefold(), count, tag, 1 / math.sqrt(max(1, degree - 1))))
        context = tuple(context)
        base = base_for_leaf[i]
        key = (base.type, tuple(base.vector), base.supported, context, base.black_box_key)
        if key not in grouped:
            grouped[key] = FeatureClass([], base.vector, base.type, base.supported, context, base.black_box_key)
        grouped[key].members.append(i)
    evidence = {
        "recipe": "sha256 JSON [type,v1_vector,supported]; endpoint sha256 [signature,lowercase_role]; sum modulo 2^256, excluding all subject endpoints",
        "rounds": 1, "inferred_pairs_used": 0,
        "limitations": "Neighbour v1 observations share input incidence with the subject; these are not independent identity witnesses. Bag hash equality is heuristic.",
        "base_classes": records,
        "net_bags": [{"net": net, "bag": f"{total:064x}", "endpoints": count, "devices": degree}
                     for net, (total, count, degree) in sorted(bags.items())],
    }
    return [grouped[key] for key in sorted(grouped)], evidence


def context_arrays(a, b):
    roles = sorted({r for c in [*a, *b] for r, *_ in c.context})
    labels = sorted({(n, tag) for c in [*a, *b] for _, n, tag, _ in c.context})
    ids = {label: i + 1 for i, label in enumerate(labels)}
    role_ids = {r: i for i, r in enumerate(roles)}

    def arrays(classes):
        labels = np.zeros((len(classes), len(roles)), dtype=np.int64)
        weights = np.zeros_like(labels, dtype=float)
        counts = np.zeros(len(classes))
        for i, c in enumerate(classes):
            counts[i] = len(c.context)
            for r, n, tag, weight in c.context:
                labels[i, role_ids[r]] = ids[n, tag]
                weights[i, role_ids[r]] = weight
        return labels, weights, counts

    la, wa, ca = arrays(a)
    lb, wb, cb = arrays(b)
    return la, lb, wa, wb, ca, cb
