"""Explicit boundary-only interpretation of canonical missing-library calls."""
from collections import defaultdict
from dataclasses import asdict, replace
import json
import re

from spice_canonical.canonical_netlist import Connection


def represent(device):
    """Use retained call evidence; never infer formal names or hidden devices."""
    boundary = getattr(device, 'black_box', None)
    if boundary is not None:
        return device, {'cell': boundary.cell, 'pin_basis': boundary.pin_basis,
                        'internals': 'unavailable', 'retained_unresolved_nets': []}
    # Compatibility for canonical objects produced before explicit boundaries.
    raw = [p for p in device.parameters if p.name.casefold() == 'unresolved_nets']
    if device.type.casefold() == 'unresolved':
        return device, None
    if device.connections and not raw:
        basis = 'named'
    elif (not device.connections and len(raw) == 1 and raw[0].value.split()
          and not re.search(r'''["'{}()]|\[[^\]]*\s''', raw[0].value)):
        # This legacy canonical field joins net tokens with spaces. Do not
        # invent token boundaries for quoted/grouped names; retain them opaque.
        basis = 'positional'
        device = replace(device, connections=tuple(
            Connection(f'@{i}', net) for i, net in enumerate(raw[0].value.split(), 1)),
            parameters=tuple(p for p in device.parameters if p is not raw[0]))
    else:
        return device, None
    cell = next((p.value for p in reversed(device.parameters)
                 if p.name.casefold() == 'source_type'), device.type)
    return device, {'cell': cell, 'pin_basis': basis,
                    'internals': 'unavailable',
                    'retained_unresolved_nets': [asdict(p) for p in raw]}


def key(leaf):
    if leaf.black_box is None:
        return ''
    return json.dumps([leaf.black_box['cell'].casefold(), leaf.black_box['pin_basis'],
                       sorted(r.casefold() for r in leaf.nets)])


def compatible(a, b):
    return key(a) == key(b)


def reconcile(a, b):
    """Reject contradictory interfaces rather than treating changed arity as pins."""
    interfaces = defaultdict(set)
    defined = {name.casefold() for view in (a, b) for name in view.declared_subcircuits}
    for view in (a, b):
        for leaf in view.leaves:
            if leaf.black_box:
                interfaces[leaf.black_box['cell'].casefold()].add(key(leaf))
    for view in (a, b):
        for leaf in view.leaves:
            if not leaf.black_box or leaf.opaque:
                continue
            cell = leaf.black_box['cell'].casefold()
            reason = ('black_box_definition_available_on_one_side' if cell in defined else
                      'incompatible_black_box_interfaces' if len(interfaces[cell]) > 1 else None)
            if reason:
                leaf.opaque = reason
                view.unresolved.append({'region': leaf.path, 'reason': reason,
                                        'hidden_leaf_count': None})
