"""Sparse optional unary assignment; this does not optimize graph connectivity."""
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import min_weight_full_bipartite_matching


def solve(old, new, costs, unmatched, forbidden=None):
    ai, bj = {x: i for i, x in enumerate(old)}, {x: j for j, x in enumerate(new)}
    edges = {(ai[i], bj[j]): c - unmatched for (i, j), c in costs.items()
             if (i, j) != forbidden}
    edges.update({(i, len(new) + i): unmatched for i in range(len(old))})
    if not old:
        return [], len(new) * unmatched
    shift = max(1., 1. - min(edges.values()))
    matrix = csr_matrix(([v + shift for v in edges.values()],
                         ([i for i, _ in edges], [j for _, j in edges])),
                        shape=(len(old), len(new) + len(old)), dtype=np.float64)
    rows, cols = min_weight_full_bipartite_matching(matrix)
    pairs = sorted((old[int(i)], new[int(j)]) for i, j in zip(rows, cols) if j < len(new))
    objective = sum(costs[p] for p in pairs) + unmatched * (len(old) + len(new) - 2 * len(pairs))
    return pairs, float(objective)
