"""Immutable local features and tiled class-candidate search."""
from dataclasses import dataclass
import math

import numpy as np
from scipy.spatial.distance import cdist

from .model import Options, View


ROLES = ("d", "g", "s", "b", "p", "n", "a", "k", "c", "e", "cp", "cn",
         "p1", "n1", "p2", "n2", "common", "other")
KINDS = ("nmos", "pmos", "mosfet", "resistor", "capacitor", "inductor", "vsource", "other")
WIDTH = 4 + len(KINDS)


@dataclass
class FeatureClass:
    members: list[int]
    vector: np.ndarray
    type: str
    supported: bool
    context: tuple = ()


def features(view: View) -> list[FeatureClass]:
    kinds = [KINDS.index(l.device.type.casefold()) if l.device.type.casefold() in KINDS
             else len(KINDS) - 1 for l in view.leaves]
    net_info = {}
    for net, endpoints in view.nets.items():
        distinct = {i for i, _ in endpoints}
        histogram = np.bincount([kinds[i] for i in distinct], minlength=len(KINDS)).astype(float)
        net_info[net] = (len(distinct), histogram)
    grouped = {}
    for i, leaf in enumerate(view.leaves):
        vector = np.zeros((len(ROLES), WIDTH), dtype=float)
        external = False
        for role, net in leaf.nets.items():
            r = ROLES.index(role.casefold()) if role.casefold() in ROLES else len(ROLES) - 1
            degree, histogram = net_info[net]
            neighbours = histogram.copy()
            neighbours[kinds[i]] -= 1
            external |= degree > 1
            vector[r, 0] += 1
            vector[r, 1] += min(math.log2(max(1, degree)), 16) / 16
            vector[r, 2] += (degree > 1) / math.sqrt(max(1, degree))
            vector[r, 3] += (sum(n == net for n in leaf.nets.values()) - 1) / max(1, len(leaf.nets))
            # Degree-weighted histograms limit rail domination without deleting
            # any terminal. Exclude the device itself as a witness.
            vector[r, 4:] += neighbours / max(1, degree - 1) / math.sqrt(max(1, degree))
        vector = vector.ravel()
        supported = external and leaf.opaque is None
        key = (leaf.device.type.casefold(), tuple(vector), supported)
        if key not in grouped:
            grouped[key] = FeatureClass([], vector, key[0], supported)
        grouped[key].members.append(i)
    # Class IDs depend on structural values, never on instance traversal order.
    return [grouped[key] for key in sorted(grouped)]


def search(a: list[FeatureClass], b: list[FeatureClass], options: Options):
    na, nb, k = len(a), len(b), options.candidate_top_k
    # One extra retained entry detects ties at the cutoff without listing all ties.
    best_a = np.full((na, k + 1), np.inf)
    ids_a = np.full((na, k + 1), -1, dtype=int)
    best_b = np.full((nb, k + 1), np.inf)
    ids_b = np.full((nb, k + 1), -1, dtype=int)
    examined_a = np.zeros(na, dtype=int)
    examined_b = np.zeros(nb, dtype=int)
    scores = 0
    va = np.stack([c.vector for c in a]) if a else np.empty((0, len(ROLES) * WIDTH))
    vb = np.stack([c.vector for c in b]) if b else np.empty((0, len(ROLES) * WIDTH))
    ta = np.array([c.type for c in a])
    tb = np.array([c.type for c in b])

    def retain(costs, ids, row, values, candidates):
        cs = np.concatenate((costs[row], values))
        js = np.concatenate((ids[row], candidates))
        order = np.lexsort((js, cs))[:k + 1]
        costs[row], ids[row] = cs[order], js[order]

    context = None
    if options.context_mode == "frozen_neighbors":
        from .context import context_arrays
        context = context_arrays(a, b)
    stopped = False
    for i in range(0, na, options.tile_size):
        ni = min(options.tile_size, na - i)
        for j in range(0, nb, options.tile_size):
            nj = min(options.tile_size, nb - j)
            # Full tiles only; a too-small budget explicitly produces no search.
            if scores + ni * nj > options.max_pair_scores:
                stopped = True
                break
            distances = cdist(va[i:i + ni], vb[j:j + nj], metric="cityblock") / 8
            if context is not None:
                labels_a, labels_b, weights_a, weights_b, counts_a, counts_b = context
                # Bounded tile; no leaf-pair or endpoint-pair clique is stored.
                penalty = np.zeros((ni, nj))
                for role in range(labels_a.shape[1]):
                    different = labels_a[i:i + ni, role, None] != labels_b[None, j:j + nj, role]
                    weight = (weights_a[i:i + ni, role, None] + weights_b[None, j:j + nj, role]) / 2
                    penalty += different * weight
                distances += options.context_weight * penalty / np.maximum(
                    1, np.maximum(counts_a[i:i + ni, None], counts_b[None, j:j + nj]))
            costs = distances + options.type_penalty * (ta[i:i + ni, None] != tb[None, j:j + nj])
            for r in range(ni):
                retain(best_a, ids_a, i + r, costs[r], np.arange(j, j + nj))
            for c in range(nj):
                retain(best_b, ids_b, j + c, costs[:, c], np.arange(i, i + ni))
            examined_a[i:i + ni] += nj
            examined_b[j:j + nj] += ni
            scores += ni * nj
        if stopped:
            break
    candidates = {}
    for i in range(na):
        for cost, j in zip(best_a[i, :k], ids_a[i, :k]):
            if j >= 0:
                candidates[i, int(j)] = float(cost)
    for j in range(nb):
        for cost, i in zip(best_b[j, :k], ids_b[j, :k]):
            if i >= 0:
                candidates[int(i), j] = float(cost)

    def records(best, examined, opposite):
        return [{"examined_classes": int(examined[i]), "available_classes": opposite,
                 "search_complete": int(examined[i]) == opposite,
                 "top_k_truncated": int(examined[i]) > k,
                 "cutoff_tie": bool(np.isfinite(best[i, k]) and
                                    best[i, k] <= best[i, k - 1] + options.ambiguity_tolerance)}
                for i in range(len(best))]

    ra, rb = records(best_a, examined_a, nb), records(best_b, examined_b, na)
    return candidates, {"pair_scores": scores, "possible_class_pairs": na * nb,
                        "screening_complete": not stopped, "a": ra, "b": rb}


def components(edges):
    """Connected components of candidate competition, not circuit connectivity."""
    adjacency = {}
    for i, j in edges:
        adjacency.setdefault(("a", i), set()).add(("b", j))
        adjacency.setdefault(("b", j), set()).add(("a", i))
    seen = set()
    result = []
    for start in sorted(adjacency):
        if start in seen:
            continue
        pending, members = [start], set()
        while pending:
            node = pending.pop()
            if node in seen:
                continue
            seen.add(node)
            members.add(node)
            pending.extend(adjacency[node] - seen)
        result.append((sorted(i for side, i in members if side == "a"),
                       sorted(i for side, i in members if side == "b")))
    return result
