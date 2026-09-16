"""Boundary observations and conditional incidence evidence, never pin identity."""
from collections import defaultdict


def _pins(view):
    selection = view.selection
    raw = {c['pin'].casefold(): c['net'] for c in selection['call_connections']}
    rows = []
    for formal, net in selection['internal_bindings'].items():
        physical = selection['physical_net_map'][net]
        endpoints = view.nets.get(net, [])
        rows.append({'formal': next(p for p in view.definitions[selection['definition']].pins
                                     if p.casefold() == formal),
                     'raw_parent_net': raw[formal], 'resolved_parent_net': physical,
                     'internal_net': net, 'global': physical.startswith('global:'),
                     'internally_unused': (not endpoints) if not view.unresolved else None,
                     'represented_endpoint_count': len(endpoints)})
    aliases = defaultdict(list)
    for row in rows:
        aliases[row['resolved_parent_net']].append(row['formal'])
    return {'pins': rows, 'aliases': [{'net': n, 'formals': ps} for n, ps in aliases.items() if len(ps) > 1],
            'scope_complete': not view.unresolved}


def boundary_report(a, b, report):
    left, right = _pins(a), _pins(b)
    pairs = {p['id']: p for p in report['pair_options']}
    hypotheses = []
    # Fixed matching retains independent group alternatives. Keep their factors
    # explicit rather than manufacturing a Cartesian product or uncoupled pairs.
    for group in report['groups']:
        for number, ids in enumerate(group['hypotheses']):
            overlaps = defaultdict(list)
            images, preimages = defaultdict(set), defaultdict(set)
            for pid in ids:
                for t in pairs[pid]['terminals']:
                    if t['paired']:
                        na, nb = t['net_a'], t['net_b']
                        overlaps[na, nb].append(pid + ':' + t['role'])
                        images[na].add(nb)
                        preimages[nb].add(na)
            candidates = []
            for pa in left['pins']:
                for pb in right['pins']:
                    na, nb = pa['internal_net'], pb['internal_net']
                    support = overlaps.get((na, nb), [])
                    if not support:
                        continue
                    candidates.append({'a': pa['formal'], 'b': pb['formal'],
                                       'support': support,
                                       'incidence_conflict': len(images[na]) > 1 or len(preimages[nb]) > 1,
                                       'outer_net_equal': pa['resolved_parent_net'] == pb['resolved_parent_net']})
            hypotheses.append({'group': group['id'], 'hypothesis': number,
                               'conditional_on_pair_ids': ids, 'pin_candidates': candidates,
                               'unresolved_a': [p['formal'] for p in left['pins']
                                                if not any(c['a'] == p['formal'] for c in candidates)],
                               'unresolved_b': [p['formal'] for p in right['pins']
                                                if not any(c['b'] == p['formal'] for c in candidates)]})
    names_a = {p['formal'].casefold() for p in left['pins']}
    names_b = {p['formal'].casefold() for p in right['pins']}
    outer = defaultdict(lambda: {'a': [], 'b': []})
    for side, catalog in (('a', left), ('b', right)):
        for p in catalog['pins']:
            outer[p['resolved_parent_net']][side].append(p['formal'])
    return {'a': left, 'b': right,
            'formal_declaration_changes': {
                'only_a': [p['formal'] for p in left['pins'] if p['formal'].casefold() not in names_b],
                'only_b': [p['formal'] for p in right['pins'] if p['formal'].casefold() not in names_a],
                'meaning': 'Raw missing/added labels, case insensitive; may be renames, not inferred identity.'},
            'outer_net_groups': [{'net': net, **members} for net, members in outer.items()], 'formal_count_delta_b_minus_a': len(right['pins']) - len(left['pins']),
            'hypotheses': hypotheses, 'correspondence': 'tentative_partial_incidence',
            'constraint': 'one_to_one_formal_pairs; hypotheses within a group are alternatives; groups are factors',
            'alternatives_complete': False,
            'unresolved_policy': 'No endpoint support means unresolved, not a proven added/deleted port. Unused ports have no inferred identity.',
            'internal_ambiguity': {'inspection_regions': report.get('inspection_regions', []),
                                   'unresolved_groups': [g['id'] for g in report['groups'] if not g['hypotheses']]},
            'outer_net_relation': 'Actual equality in this full input under declared global scope; difference is context, not an internal defect.'}
