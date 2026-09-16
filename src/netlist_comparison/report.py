"""Raw comparisons and membership tables, always conditional on pair choices."""
from collections import Counter, defaultdict
from dataclasses import asdict
import hashlib
import json

from .model import View


def identity(netlist):
    document = asdict(netlist)
    document["subcircuits"] = sorted(document["subcircuits"], key=lambda c: c["name"].casefold())
    for c in [document["top"], *document["subcircuits"]]:
        c["devices"] = sorted(c["devices"], key=lambda d: d["name"].casefold())
    return hashlib.sha256(json.dumps(document, sort_keys=True, default=str).encode()).hexdigest()


def parameter_differences(a, b, prefix):
    # Lists retain duplicate assignments and distinguish absence from a value.
    left, right = defaultdict(list), defaultdict(list)
    for p in a:
        left[p.name].append(p.value)
    for p in b:
        right[p.name].append(p.value)
    result = [{"field": f"{prefix}.{name}", "a": left.get(name), "b": right.get(name)}
              for name in sorted(left.keys() | right.keys()) if left.get(name) != right.get(name)]
    if [p.name for p in a] != [p.name for p in b]:
        result.append({"field": f"{prefix}.$order", "a": [p.name for p in a],
                       "b": [p.name for p in b]})
    return result


def pair_record(a, b, pair_id, group_id, cost):
    differences = parameter_differences(a.device.parameters, b.device.parameters, "parameters")
    if a.device.type != b.device.type:
        differences.insert(0, {"field": "type", "a": a.device.type, "b": b.device.type})
    ca = {c.pin.casefold(): c for c in a.device.connections}
    cb = {c.pin.casefold(): c for c in b.device.connections}
    terminals = []
    for role in sorted(ca.keys() | cb.keys()):
        aa, bb = ca.get(role), cb.get(role)
        terminals.append({"role": role, "role_a": aa.pin if aa else None,
                          "role_b": bb.pin if bb else None,
                          "raw_a": aa.net if aa else None, "raw_b": bb.net if bb else None,
                          "net_a": a.nets[aa.pin] if aa else None,
                          "net_b": b.nets[bb.pin] if bb else None,
                          "paired": aa is not None and bb is not None,
                          "raw_binding_differs": aa != bb,
                          "resolved_identifier_differs": ((a.nets[aa.pin] if aa else None) !=
                                                          (b.nets[bb.pin] if bb else None))})
    return {"id": pair_id, "group": group_id, "a": a.path, "b": b.path,
            "status": "tentative", "cost": cost, "raw_differences": differences,
            "terminals": terminals}


def catalog(view: View):
    return {
        "objects": [{"id": l.path, "path_segments": list(l.segments), "parent": l.parent,
                     "definition": l.definition, "type": l.device.type,
                     "parameters": [asdict(p) for p in l.device.parameters],
                     "connections": [asdict(c) for c in l.device.connections],
                     "resolved_nets": l.nets, "opaque_reason": l.opaque}
                    for l in view.leaves],
        "occurrences": view.occurrences,
        "definitions": [{"name": c.name, "pins": list(c.pins),
                         "parameter_defaults": [asdict(p) for p in c.parameter_defaults],
                         "direct_device_count": len(c.devices)}
                        for c in sorted(view.definitions.values(), key=lambda c: c.name)],
        "diagnostics": view.diagnostics,
        "unresolved": view.unresolved,
        "expansion_complete": not view.budget_exhausted,
        "expanded_leaf_count": len(view.leaves),
        "max_depth": max((o["depth"] for o in view.occurrences), default=0),
    }


def connectivity(a: View, b: View, pairs):
    table, used_a, used_b = defaultdict(list), Counter(), Counter()
    for record in pairs:
        for t in record["terminals"]:
            if t["paired"]:
                table[t["net_a"], t["net_b"]].append(record["id"] + ":" + t["role"])
                used_a[t["net_a"]] += 1
                used_b[t["net_b"]] += 1
    images, preimages = defaultdict(set), defaultdict(set)
    for na, nb in table:
        images[na].add(nb)
        preimages[nb].add(na)
    return {
        "conditional_on_pair_ids": [p["id"] for p in pairs],
        "meaning": "net partitions of paired endpoints under declared scoping; not net identity",
        "overlap": [{"a": na, "b": nb, "endpoint_tokens": sorted(tokens),
                     "a_partitioned_across_b": len(images[na]) > 1,
                     "b_collects_multiple_a": len(preimages[nb]) > 1,
                     "single_endpoint_only": len(tokens) == 1}
                    for (na, nb), tokens in sorted(table.items())],
        "unpaired_endpoints_a": [{"net": n, "count": len(es) - used_a[n]}
                                 for n, es in sorted(a.nets.items()) if len(es) > used_a[n]],
        "unpaired_endpoints_b": [{"net": n, "count": len(es) - used_b[n]}
                                 for n, es in sorted(b.nets.items()) if len(es) > used_b[n]],
    }


def hierarchy(a: View, b: View, pairs):
    la, lb = {l.path: l for l in a.leaves}, {l.path: l for l in b.leaves}
    oa, ob = {o["path"]: o for o in a.occurrences}, {o["path"]: o for o in b.occurrences}
    counts, owners = Counter(), set()
    for pair in pairs:
        aa, bb = la[pair["a"]], lb[pair["b"]]
        owners.add((aa.definition, bb.definition))
        for pa in aa.ancestors:
            for pb in bb.ancestors:
                counts[pa, pb] += 1
    memberships = [{"a": pa, "b": pb, "paired_leaves": count,
                    "total_a": oa[pa]["leaf_count"], "total_b": ob[pb]["leaf_count"],
                    "depth_a": oa[pa]["depth"], "depth_b": ob[pb]["depth"], "relation": None}
                   for (pa, pb), count in sorted(counts.items())]
    # Pure single-child wrappers have equally good memberships; retain ties.
    # Mutual maximal Dice overlap proposes containers without requiring same depth.
    best_a, best_b = defaultdict(float), defaultdict(float)
    for row in memberships:
        score = 2 * row["paired_leaves"] / (row["total_a"] + row["total_b"])
        best_a[row["a"]] = max(best_a[row["a"]], score)
        best_b[row["b"]] = max(best_b[row["b"]], score)
    occurrences = []
    for row in memberships:
        score = 2 * row["paired_leaves"] / (row["total_a"] + row["total_b"])
        if score == best_a[row["a"]] == best_b[row["b"]]:
            aa, bb = oa[row["a"]], ob[row["b"]]
            owners.add((aa["definition"], bb["definition"]))
            # Already plain records; compare ordered raw overrides directly.
            occurrences.append({"a": row["a"], "b": row["b"], "relation": None,
                                "basis": "mutual_maximum_leaf_membership",
                                "overrides_a": aa["overrides"], "overrides_b": bb["overrides"],
                                "overrides_differ": aa["overrides"] != bb["overrides"]})
    definitions = []
    named = {(ca.name, cb.name) for ca in a.definitions.values() for cb in b.definitions.values()
             if ca.name.casefold() == cb.name.casefold()}
    for da, db in sorted(owners | named):
        ca, cb = a.definitions[da], b.definitions[db]
        changes = parameter_differences(ca.parameter_defaults, cb.parameter_defaults, "defaults")
        if ca.pins != cb.pins:
            changes.append({"field": "pins", "a": list(ca.pins), "b": list(cb.pins)})
        definitions.append({"a": da, "b": db,
                            "basis": "tentative_occurrence_membership" if (da, db) in owners else "name_only_candidate",
                            "raw_differences": changes,
                            "occurrences_a": [o["path"] for o in a.occurrences if o["definition"] == da],
                            "occurrences_b": [o["path"] for o in b.occurrences if o["definition"] == db]})
    return {"conditional_on_pair_ids": [p["id"] for p in pairs], "memberships": memberships,
            "occurrence_options": occurrences, "definition_options": definitions}
