"""Occurrence expansion without parameter evaluation or guessed global aliases."""
from dataclasses import asdict
import re
from urllib.parse import unquote

from spice_canonical.canonical_netlist import CanonicalNetlist

from .model import InputScope, Leaf, Options, View, location
from .blackbox import represent


def expand(netlist: CanonicalNetlist, top: str, scope: InputScope, options: Options, *, path: str | None = None) -> View:
    definitions = {}
    for circuit in (netlist.top, *netlist.subcircuits):
        key = circuit.name.casefold()
        if key in definitions:
            raise ValueError(f"duplicate circuit definition: {circuit.name}")
        definitions[key] = circuit
        for items, label in ((circuit.pins, "pins"),
                             ([d.name for d in circuit.devices], "devices")):
            lowered = [x.casefold() for x in items]
            if len(lowered) != len(set(lowered)):
                raise ValueError(f"duplicate {label} in {circuit.name}")
    if top.casefold() not in definitions:
        raise ValueError(f"unknown top circuit: {top}")
    view = View(definitions={c.name: c for c in definitions.values()})
    view.diagnostics = [{**asdict(d), "source": str(d.source) if d.source else None}
                        for d in netlist.diagnostics]
    globals_ = {name.casefold() for name in scope.global_nets}
    # Ground remains global even when the caller supplies additional names.
    globals_.add("0")
    root = definitions[top.casefold()]
    root_parts = (root.name,)

    def resolve(raw, bindings, parts):
        key = raw.casefold()
        if key in globals_:
            return "global:" + location((key,))
        if key in bindings:
            return bindings[key]
        return "local:" + location(parts) + ":" + location((key,))

    def enter(circuit, parts, bindings, active, ancestors, call):
        path = location(parts)
        view.occurrences.append({"path": path, "path_segments": list(parts),
                                 "parent": ancestors[-1] if ancestors else (location(parts[:-1]) if call else None),
                                 "depth": len(parts) - 1, "definition": circuit.name,
                                 "call_type": call.type if call else None,
                                 "call_connections": [asdict(c) for c in call.connections] if call else [],
                                 "overrides": [asdict(p) for p in call.parameters] if call else [],
                                 "bindings": dict(bindings), "leaf_count": 0})
        # One iterator per active level: no exponentially expanded pending queue.
        devices = sorted(circuit.devices, key=lambda d: (d.name.casefold(), d.name))
        return [circuit, parts, bindings, active + (circuit.name.casefold(),),
                ancestors + (path,), iter(devices), len(devices)]

    selected_bindings, selected_call, active = {}, None, ()
    if path is not None:
        if not isinstance(path, str) or re.search(r"%(?![0-9a-fA-F]{2})", path):
            raise ValueError("invalid percent-escaped occurrence path")
        try:
            segments = tuple(unquote(p, errors="strict") for p in path.split("/"))
        except UnicodeError as exc:
            raise ValueError("invalid UTF-8 occurrence path") from exc
        if len(segments) < 2 or any(not p for p in segments):
            raise ValueError("path must include top and a subcircuit occurrence")
        if segments[0].casefold() != root.name.casefold():
            raise ValueError("occurrence path must start with the selected top")
        top_context = {"definition": root.name, "defaults": [asdict(p) for p in root.parameter_defaults]}
        chain = []
        for segment in segments[1:]:
            calls = [d for d in root.devices if d.name.casefold() == segment.casefold()]
            if len(calls) != 1:
                raise ValueError(f"unknown or ambiguous occurrence path: {path}")
            call = calls[0]
            if call.name[:1].casefold() != "x":
                raise ValueError("selected path must traverse subcircuit calls, not primitives")
            params = {p.name.casefold(): p.value for p in call.parameters}
            target = definitions.get(params.get("source_type", call.type).casefold())
            if target is None:
                raise ValueError(f"unresolved_definition at {location(root_parts + (call.name,))}")
            roles = [c.pin.casefold() for c in call.connections]
            if len(set(roles)) != len(roles) or set(roles) != {p.casefold() for p in target.pins}:
                raise ValueError(f"invalid_call_bindings at {location(root_parts + (call.name,))}")
            active += (root.name.casefold(),)
            if target.name.casefold() in active:
                raise ValueError("recursive_call on selected ancestor path")
            selected_bindings = {c.pin.casefold(): resolve(c.net, selected_bindings, root_parts)
                                 for c in call.connections}
            root_parts += (call.name,)
            root, selected_call = target, call
            chain.append({"path": location(root_parts), "definition": root.name,
                          "bindings": dict(selected_bindings),
                          "overrides": [asdict(p) for p in call.parameters],
                          "defaults": [asdict(p) for p in root.parameter_defaults]})
        # Physical attachments are context; distinct formal ports stay distinct
        # for internal matching even when the caller shorts them together.
        intrinsic = {p.casefold(): ("global:" + location((p.casefold(),))
                                   if p.casefold() in globals_ else
                                   "boundary:" + location(root_parts) + ":" + location((p.casefold(),)))
                     for p in root.pins}
        physical = {intrinsic[p.casefold()]: resolve(p, selected_bindings, root_parts)
                    for p in root.pins}
        view.selection = {"path": location(root_parts), "path_segments": list(root_parts),
                          "definition": root.name, "ancestor_calls": chain, "top_context": top_context,
                          "overrides": [asdict(p) for p in selected_call.parameters],
                          "defaults": [asdict(p) for p in root.parameter_defaults],
                          "physical_bindings": selected_bindings,
                          "internal_bindings": intrinsic, "physical_net_map": physical,
                          "call_connections": [asdict(c) for c in selected_call.connections]}
        selected_bindings = intrinsic
    stack = [enter(root, root_parts, selected_bindings, active, (), selected_call)]
    objects = 1
    while stack:
        circuit, parts, bindings, active, ancestors, devices, remaining = stack[-1]
        if remaining == 0:
            stack.pop()
            continue
        if objects >= options.max_objects:
            view.budget_exhausted = True
            view.unresolved.extend({"region": location(frame[1]), "reason": "expansion_budget",
                                    "remaining_direct_devices": frame[6],
                                    "hidden_leaf_count": None}
                                   for frame in stack if frame[6])
            break
        device = next(devices)
        stack[-1][6] -= 1
        objects += 1
        child_parts = parts + (device.name,)
        path = location(child_parts)
        params = {p.name.casefold(): p.value for p in device.parameters}
        # Canonical's public extraction uses SPICE instance prefixes; type alone
        # can collide with a primitive's model type and cannot identify a call.
        is_call = device.name[:1].casefold() == "x"
        target = definitions.get(params.get("source_type", device.type).casefold()) if is_call else None
        black_box = None
        if is_call and target is None and options.black_box_missing:
            device, black_box = represent(device)
        pins = [c.pin.casefold() for c in device.connections]
        opaque = None
        if len(pins) != len(set(pins)):
            opaque = "duplicate_terminal_roles"
        nets = {c.pin: resolve(c.net, bindings, parts) for c in device.connections}
        if target and not opaque:
            if set(pins) != {p.casefold() for p in target.pins}:
                opaque = "invalid_call_bindings"
            elif target.name.casefold() in active:
                opaque = "recursive_call"
            elif len(child_parts) - len(root_parts) > options.max_depth:
                opaque = "depth_budget"
            else:
                child_bindings = {c.pin.casefold(): nets[c.pin] for c in device.connections}
                stack.append(enter(target, child_parts, child_bindings, active, ancestors, device))
                continue
        elif is_call and black_box is None:
            opaque = opaque or "unresolved_definition"
        if device.type.casefold() == "unresolved" or not device.connections:
            opaque = opaque or "unrepresented_connectivity"
        if opaque:
            view.unresolved.append({"region": path, "reason": opaque, "hidden_leaf_count": None})
        if black_box and not opaque:
            view.unresolved.append({"region": path, "reason": "black_box_internals_unavailable",
                                    "hidden_leaf_count": None})
        leaf = Leaf(path, child_parts, ancestors[-1], ancestors, circuit.name, device, nets, opaque, black_box)
        index = len(view.leaves)
        view.leaves.append(leaf)
        for role, net in nets.items():
            view.nets.setdefault(net, []).append((index, role))
    counts = {o["path"]: 0 for o in view.occurrences}
    for leaf in view.leaves:
        for ancestor in leaf.ancestors:
            counts[ancestor] += 1
    for occurrence in view.occurrences:
        occurrence["leaf_count"] = counts[occurrence["path"]]
    if view.selection is not None:
        used = {o["definition"] for o in view.occurrences}
        view.definitions = {n: c for n, c in view.definitions.items() if n in used}
    return view
