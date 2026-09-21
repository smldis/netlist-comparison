"""Bounded exact local incidence evidence. No paths, names or history enter here.

The MILP is the binary leaf/net/mismatch model, not optional unary assignment.
Mathematical certificates are checked against integer witnesses before use.
"""
from collections import Counter, defaultdict
from copy import deepcopy
import hashlib
import json
import random
import time
import warnings

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, linear_sum_assignment, milp
from scipy.sparse import coo_matrix

ORDERINGS = (None, 101, 202)


def signature(o):
    return (o['cell'], o['pin_basis'], tuple(sorted(o['nets'])))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def counts(graph):
    return {s: Counter(signature(o) for o in graph[s]['objects']) for s in ('a', 'b')}


def cardinality(graph):
    c = counts(graph)
    return sum(min(n, c['b'][sig]) for sig, n in c['a'].items())


def compatible_pairs(graph):
    return [(i, j) for i, a in enumerate(graph['a']['objects'])
            for j, b in enumerate(graph['b']['objects']) if signature(a) == signature(b)]


def validate_witness(graph, q, coverage=None):
    """Reject malformed/incompatible/noninjective maps, not just their score."""
    pairs, netmap = q['pairs'], {int(a): int(b) for a, b in q['netmap'].items()}
    na, nb = (len(graph[s]['objects']) for s in ('a', 'b'))
    if (len({a for a, b in pairs}) != len(pairs) or len({b for a, b in pairs}) != len(pairs)
            or any(type(a) is not int or type(b) is not int or not 0 <= a < na or not 0 <= b < nb
                   for a, b in pairs)):
        raise ValueError('invalid local leaf injection')
    if any(signature(graph['a']['objects'][a]) != signature(graph['b']['objects'][b]) for a, b in pairs):
        raise ValueError('incompatible local leaf witness')
    if (len(netmap) != len(set(netmap.values())) or any(not 0 <= a < graph['a']['net_count']
            or not 0 <= b < graph['b']['net_count'] for a, b in netmap.items())):
        raise ValueError('invalid local net injection')
    error = sum(netmap.get(n) != graph['b']['objects'][b]['nets'][role]
                for a, b in pairs for role, n in graph['a']['objects'][a]['nets'].items())
    if (error != q['error'] or q['coverage'] != len(pairs) or
            q['weighted_cost'] != 5 * error + 3 * (na + nb - 2 * len(pairs)) or
            (coverage is not None and len(pairs) != coverage)):
        raise ValueError('local objective/incidence witness mismatch')
    return q


def witness(graph, pairs, netmap):
    error = sum(netmap.get(n) != graph['b']['objects'][b]['nets'][role]
                for a, b in pairs for role, n in graph['a']['objects'][a]['nets'].items())
    q = {'pairs': [list(p) for p in pairs], 'netmap': {str(a): b for a, b in netmap.items()},
         'coverage': len(pairs), 'error': error,
         'weighted_cost': 5 * error + 3 * (sum(len(graph[s]['objects']) for s in ('a', 'b')) - 2 * len(pairs))}
    return validate_witness(graph, q)


def histogram(graph):
    out = {}
    for s in ('a', 'b'):
        out[s] = [Counter() for _ in range(graph[s]['net_count'])]
        for o in graph[s]['objects']:
            for role, net in o['nets'].items():
                out[s][net][(signature(o), role)] += 1
    return out


def capacity_bound(graph, k):
    if any(len(graph[s]['objects']) != k for s in ('a', 'b')):
        return {'kind': 'nonnegative_mismatch', 'lower_bound': 0}
    h = histogram(graph)
    matrix = np.zeros((len(h['a']), len(h['b'])), dtype=np.int64)
    for i, aa in enumerate(h['a']):
        for j, bb in enumerate(h['b']):
            matrix[i, j] = sum((aa & bb).values())
    ii, jj = linear_sum_assignment(matrix, maximize=True)
    capacity = int(matrix[ii, jj].sum())
    total = sum(sum(x.values()) for x in h['a'])
    return {'kind': 'full_coverage_relaxed_terminal_capacity', 'terminals': total,
            'maximum_relaxed_agreements': capacity, 'lower_bound': total - capacity}


def topology_hint(graph):
    h = histogram(graph)
    colors = {s: [digest(sorted((repr(k), v) for k, v in row.items())) for row in h[s]] for s in h}
    initial = deepcopy(colors)
    for _ in range(3):
        leaves = {s: [digest([signature(o), sorted((r, colors[s][n]) for r, n in o['nets'].items())])
                       for o in graph[s]['objects']] for s in h}
        next_colors = {}
        for s in h:
            endpoints = [[] for _ in colors[s]]
            for i, o in enumerate(graph[s]['objects']):
                for role, n in o['nets'].items():
                    endpoints[n].append((leaves[s][i], role))
            next_colors[s] = [digest(sorted(x)) for x in endpoints]
        colors = next_colors
    matrix = np.zeros((len(h['a']), len(h['b'])), dtype=np.int64)
    for i, aa in enumerate(h['a']):
        for j, bb in enumerate(h['b']):
            matrix[i, j] = (1_000_000 * (colors['a'][i] == colors['b'][j]) +
                            10_000 * (initial['a'][i] == initial['b'][j]) + sum((aa & bb).values()))
    ii, jj = linear_sum_assignment(matrix, maximize=True)
    netmap = {int(a): int(b) for a, b in zip(ii, jj)}
    groups = {s: defaultdict(list) for s in h}
    for s in h:
        for i, o in enumerate(graph[s]['objects']):
            groups[s][signature(o)].append(i)
    pairs = []
    for sig, aa in groups['a'].items():
        bb = groups['b'].get(sig, [])
        weights = np.zeros((len(aa), len(bb)), dtype=np.int64)
        for i, a in enumerate(aa):
            for j, b in enumerate(bb):
                weights[i, j] = 100 * sum(netmap.get(n) == graph['b']['objects'][b]['nets'][r]
                                          for r, n in graph['a']['objects'][a]['nets'].items()) + (leaves['a'][a] == leaves['b'][b])
        ii, jj = linear_sum_assignment(weights, maximize=True)
        pairs.extend((aa[i], bb[j]) for i, j in zip(ii, jj))
    return witness(graph, pairs, netmap)


def permute(graph, seed):
    new, maps = deepcopy(graph), {}
    for s in ('a', 'b'):
        rng = random.Random(str(seed) + '/' + s)
        leaves = list(range(len(graph[s]['objects'])))
        nets = list(range(graph[s]['net_count']))
        if seed is not None:
            rng.shuffle(leaves); rng.shuffle(nets)
        inverse = {old: i for i, old in enumerate(nets)}
        new[s]['objects'] = []
        for old in leaves:
            obj = deepcopy(graph[s]['objects'][old])
            obj['nets'] = {r: inverse[n] for r, n in obj['nets'].items()}
            new[s]['objects'].append(obj)
        maps[s] = {'leaves': leaves, 'nets': nets}
    return new, maps


def transfer(original, reordered, maps, q):
    """Validate the full bijection before transferring any claimed lower bound."""
    for s in ('a', 'b'):
        m = maps[s]
        if sorted(m['leaves']) != list(range(len(original[s]['objects']))) or sorted(m['nets']) != list(range(original[s]['net_count'])):
            raise ValueError('invalid local model bijection')
        for i, old in enumerate(m['leaves']):
            obj = deepcopy(reordered[s]['objects'][i])
            obj['nets'] = {r: m['nets'][n] for r, n in obj['nets'].items()}
            if obj != original[s]['objects'][old]:
                raise ValueError('local bijection changes attributes or incidence')
    candidates = {(maps['a']['leaves'][a], maps['b']['leaves'][b]) for a, b in compatible_pairs(reordered)}
    if candidates != set(compatible_pairs(original)):
        raise ValueError('incomplete transferred candidate catalogue')
    result = deepcopy(q)
    if 'pairs' in q:
        pairs = [(maps['a']['leaves'][a], maps['b']['leaves'][b]) for a, b in q['pairs']]
        netmap = {maps['a']['nets'][int(a)]: maps['b']['nets'][b] for a, b in q['netmap'].items()}
        checked = witness(original, pairs, netmap)
        if any(checked[k] != q[k] for k in ('coverage', 'error', 'weighted_cost')):
            raise ValueError('transferred objective changed')
        result.update(checked)
    result['transfer'] = {'original_sha256': digest(original), 'source_sha256': digest(reordered), 'bijection': maps}
    return result


def solve_milp(graph, coverage, seconds, forbidden=None):
    """Same exact binary model as the studied oracle; existing SciPy/HiGHS only."""
    start = time.monotonic()
    pairs = compatible_pairs(graph)
    na, nb = (len(graph[s]['objects']) for s in ('a', 'b'))
    an, bn = graph['a']['net_count'], graph['b']['net_count']
    x = {p: i for i, p in enumerate(pairs)}
    y = {(a, b): len(x) + a * bn + b for a in range(an) for b in range(bn)}
    z = []
    for a, b in pairs:
        for role, net in graph['a']['objects'][a]['nets'].items():
            z.append((x[a, b], y[net, graph['b']['objects'][b]['nets'][role]]))
    variables = len(x) + len(y) + len(z)
    c = np.zeros(variables)
    if coverage is None:
        c[:len(x)] = -6
    c[len(x) + len(y):] = 5 if coverage is None else 1
    rr, cc, vv, lower, upper = [], [], [], [], []
    def constraint(terms, lo=-np.inf, hi=np.inf):
        row = len(lower)
        for col, value in terms:
            rr.append(row); cc.append(col); vv.append(value)
        lower.append(lo); upper.append(hi)
    for i in range(na): constraint([(v, 1) for (a, b), v in x.items() if a == i], hi=1)
    for j in range(nb): constraint([(v, 1) for (a, b), v in x.items() if b == j], hi=1)
    for a in range(an): constraint([(y[a, b], 1) for b in range(bn)], hi=1)
    for b in range(bn): constraint([(y[a, b], 1) for a in range(an)], hi=1)
    for i, (xx, yy) in enumerate(z):
        zz = len(x) + len(y) + i
        constraint([(zz, 1), (xx, -1)], hi=0)
        constraint([(zz, 1), (yy, 1)], hi=1)
        constraint([(zz, 1), (xx, -1), (yy, 1)], lo=0)
    if coverage is not None:
        constraint([(v, 1) for v in x.values()], coverage, coverage)
    if forbidden is not None:
        chosen = set(map(tuple, forbidden))
        constraint([(v, -1 if p in chosen else 1) for p, v in x.items()], lo=1 - len(chosen))
    matrix = coo_matrix((vv, (rr, cc)), shape=(len(lower), variables)).tocsc()
    # HiGHS receives threads=1; SciPy explicitly forwards unrecognized options.
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message="Unrecognized options detected:.*threads")
        solved = milp(c, integrality=np.ones(variables), bounds=Bounds(0, 1),
                      constraints=LinearConstraint(matrix, lower, upper),
                      options={'time_limit': max(.001, seconds), 'mip_rel_gap': 0.0, 'threads': 1})
    out = {'status': 'incomplete', 'proof': 'scipy_highs_milp', 'solver_status': int(solved.status),
           'seconds': time.monotonic() - start, 'query_seconds': seconds,
           'objective': 'weighted' if coverage is None else 'fixed_coverage_error',
           'requested_coverage': coverage, 'message': str(solved.message)}
    if solved.x is not None and np.all(np.abs(solved.x - np.rint(solved.x)) <= 1e-6):
        chosen = [p for p, i in x.items() if solved.x[i] > .5]
        netmap = {a: b for (a, b), i in y.items() if solved.x[i] > .5}
        try:
            q = validate_witness(graph, witness(graph, chosen, netmap), coverage)
        except ValueError:
            return out
        if forbidden is not None and set(map(tuple,q['pairs'])) == set(map(tuple,forbidden)):
            return out
        value = q['weighted_cost'] if coverage is None else q['error']
        raw_bound = getattr(solved, 'mip_dual_bound', None)
        bound = float(raw_bound) + (3 * (na + nb) if coverage is None else 0) if raw_bound is not None else None
        out.update(q, lower_bound=bound)
        if solved.status == 0 and bound is not None and abs(bound - value) <= 1e-6:
            out['status'] = 'optimal'
        elif coverage is not None and q['error'] == 0:
            out.update(status='optimal', lower_bound=0, proof='nonnegative_feasible_witness')
    return out


class Executor:
    """One cold executor per supplied region; no process-global solution cache."""
    def __init__(self, graph, deadline):
        self.graph, self.deadline = graph, deadline
        self.cache = {}
        self.attempts = []

    def search(self, coverage):
        for seed in ORDERINGS:
            if time.monotonic() >= self.deadline:
                break
            graph, maps = permute(self.graph, seed)
            hint = topology_hint(graph)
            bound = capacity_bound(graph, coverage) if coverage is not None else None
            if coverage == cardinality(graph) and hint['error'] == bound['lower_bound']:
                q = {**hint, 'status': 'optimal', 'proof': 'attained_terminal_capacity_bound',
                     'lower_bound': bound['lower_bound'], 'certificate': bound,
                     'requested_coverage': coverage, 'solver_status': None}
            else:
                q = solve_milp(graph, coverage, min(10., max(.001, self.deadline-time.monotonic())))
            q = transfer(self.graph, graph, maps, q)
            self.attempts.append({'ordering': seed, 'status': q['status'], 'proof': q['proof'],
                                  'requested_coverage': coverage, 'seconds': q.get('seconds', 0)})
            if q['status'] == 'optimal':
                return q
        return {'status': 'incomplete', 'proof': 'ordering_portfolio_exhausted', 'requested_coverage': coverage}

    def fixed(self, k):
        if k in self.cache:
            return deepcopy(self.cache[k])
        q = None
        if k == 0:
            q = {**witness(self.graph, [], {}), 'status': 'optimal', 'proof': 'nonnegative_empty_witness',
                 'lower_bound': 0, 'requested_coverage': 0, 'solver_status': None}
        previous = self.cache.get(k+1)
        if q is None and previous and previous['status'] == 'optimal':
            for pair in previous['pairs']:
                smaller = witness(self.graph, [p for p in previous['pairs'] if p != pair],
                                  {int(a): b for a,b in previous['netmap'].items()})
                if smaller['error'] == 0:
                    q = {**smaller, 'status': 'optimal', 'proof': 'nonnegative_restricted_witness',
                         'lower_bound': 0, 'requested_coverage': k, 'solver_status': None}
                    break
        self.cache[k] = q or self.search(k)
        return deepcopy(self.cache[k])

    def run(self):
        k = cardinality(self.graph)
        full = self.fixed(k)
        lower = self.fixed(k-1) if k else None
        weighted = None
        if full['status'] == 'optimal' and (lower is None or lower['status'] == 'optimal'):
            choices = [q for q in (full, lower) if q is not None]
            base = 3 * (sum(len(self.graph[s]['objects']) for s in ('a','b')) - 2*k)
            bounds = [q['weighted_cost'] for q in choices] + ([base+12] if k >= 2 else [])
            best = min(choices, key=lambda q: (q['weighted_cost'], -q['coverage']))
            if best['weighted_cost'] == min(bounds):
                weighted = {**{key:deepcopy(best[key]) for key in ('pairs','netmap','coverage','error','weighted_cost')},
                            'status':'optimal','proof':'exhaustive_cardinality_partition',
                            'lower_bound':min(bounds),'certificate':{'K':k,'full_cost':full['weighted_cost'],
                             'one_less_cost':lower['weighted_cost'] if lower else None,'smaller_cost_lower_bound':base+12 if k>=2 else None}}
        weighted = weighted or self.search(None)
        return {'K':k, 'weighted':weighted, 'maximum_coverage':full, 'one_pair_less':lower,
                'certified':all(q['status']=='optimal' for q in (weighted,full) if q) and (lower is None or lower['status']=='optimal'),
                'attempts':self.attempts, 'alternatives':'Unresolved; one optimal witness does not establish identity or a unique explanation.'}
