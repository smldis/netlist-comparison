"""Reproducible prototype evidence; no claim of a representative analog design.

Run using the ASS venv. The stress ledger is evaluator-only and is never passed
to compare(). Public-file evaluation reads an existing file without copying it.
"""
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import resource
import time

import numpy
import scipy
from spice_canonical.canonical_netlist import (CanonicalNetlist, Circuit, Connection,
                                               Device, Parameter, from_file, from_text)
from netlist_comparison import compare, InputScope, Options


HERE = Path(__file__).resolve().parent


def stress_fixture(banks=44):
    # Each level has two populated children plus its own connected R and C.
    # CELL=4 leaves, STAGE1=10, STAGE2=22, STAGE3=46; not empty wrappers.
    core = from_file(HERE / "before.sp").subcircuits[0]
    definitions = [core]
    child = "CELL"
    for level in range(1, 4):
        name = f"STAGE{level}"
        text = (f".subckt {name} IN OUT VSS\n"
                f"XL IN MID VSS {child}\nXR MID OUT VSS {child}\n"
                "RLOAD MID VSS 10k\nCLOAD OUT VSS 2p\n.ends\n")
        # Declare child pin signature so canonical extraction binds each call.
        dummy = f".subckt {child} IN OUT VSS\n.ends\n"
        definitions.append(from_text(dummy + text).subcircuits[-1])
        child = name
    top = Circuit("TOP", (), tuple(
        [Device(f"XB{i}", child, (Connection("IN", "input"), Connection("OUT", f"out{i}"), Connection("VSS", "0")))
         for i in range(banks)] +
        [Device(f"RLINK{i}", "resistor", (Connection("p", f"out{i}"), Connection("n", f"out{i+1}")),
                (Parameter("value", "100k"),)) for i in range(banks - 1)]))
    before = CanonicalNetlist(top, tuple(definitions))

    def renamed_name(name):
        return name[0] + "z" + name[1:]

    def renamed_net(name):
        return "0" if name == "0" else "n_" + name

    def rename_circuit(circuit):
        devices = []
        for d in reversed(circuit.devices):
            call = d.name.startswith("X")
            devices.append(replace(d, name=renamed_name(d.name),
                                   type=d.type + "_v2" if call else d.type,
                                   connections=tuple(Connection(renamed_net(c.pin) if call else c.pin,
                                                                renamed_net(c.net)) for c in d.connections)))
        return replace(circuit, name=circuit.name + "_v2", pins=tuple(renamed_net(p) for p in circuit.pins),
                       devices=tuple(devices))

    after_defs = {c.name: rename_circuit(c) for c in before.subcircuits}
    after_top = rename_circuit(top)
    renamed_by_name = {c.name: c for c in after_defs.values()}
    clones = []

    def specialize(name, levels):
        c = renamed_by_name[name]
        devices = list(c.devices)
        chosen = "XzL" if levels else "Mz1"
        index = next(i for i, d in enumerate(devices) if d.name == chosen)
        d = devices[index]
        if levels:
            devices[index] = replace(d, type=specialize(d.type, levels - 1))
        else:
            devices[index] = replace(d, parameters=tuple(Parameter(p.name, "6u") if p.name == "W" else p
                                                        for p in d.parameters))
        clone = replace(c, name=c.name + "_SPECIAL", devices=tuple(devices))
        clones.append(clone)
        return clone.name

    specialized = specialize("STAGE3_v2", 3)
    wrapper = Circuit("RELOCATED", ("n_IN", "n_OUT", "n_VSS"),
                      (Device("XPLACED", specialized, tuple(Connection(p, p) for p in ("n_IN", "n_OUT", "n_VSS"))),))
    after_top = replace(after_top, devices=tuple(replace(d, type=wrapper.name) if d.name == "XzB0" else d
                                               for d in after_top.devices))
    after = CanonicalNetlist(after_top, (*after_defs.values(), *clones, wrapper))

    # An independent recursive enumeration is used only to build the edit ledger.
    # It neither calls the comparator expansion nor supplies IDs to the matcher.
    cells = {c.name: c for c in before.subcircuits}
    ledger = {}

    def walk(c, parts):
        for d in c.devices:
            path = parts + [d.name]
            if d.name.startswith("X"):
                walk(cells[d.type], path)
            else:
                target = ["TOP_v2"] + [renamed_name(p) for p in path[1:]]
                if path[1] == "XB0":
                    target.insert(2, "XPLACED")
                ledger["/".join(path)] = "/".join(target)
    walk(before.top, ["TOP"])
    assert len(ledger) == banks * 46 + banks - 1
    return before, after, ledger


def summarize(result, ledger=None):
    selected = {p["id"]: p for p in result["pair_options"]}
    pairs = [selected[i] for i in result["representative_pair_ids"]]
    summary = {"leaves": {s: result[s]["expanded_leaf_count"] for s in ("a", "b")},
               "depth": {s: result[s]["max_depth"] for s in ("a", "b")},
               "coverage": {s: result[s]["coverage"] for s in ("a", "b")},
               "feature_classes": {s: len(result[s]["classes"]) for s in ("a", "b")},
               "group_count": len(result["groups"]), "representative_pairs": len(pairs),
               "pairs_with_raw_differences": sum(bool(p["raw_differences"]) for p in pairs),
               "metrics": result["metrics"]}
    if ledger:
        ca = {m: c["id"] for c in result["a"]["classes"] for m in c["members"]}
        cb = {m: c["id"] for c in result["b"]["classes"] for m in c["members"]}
        edges = {(e["a_class"], e["b_class"]) for e in result["candidate_edges"]}
        eligible = {(e["a_class"], e["b_class"]) for e in result["candidate_edges"] if e["eligible"]}
        summary["ledger_check"] = {
            "scope": "Generator history, NOT a unique admissible mapping for repeated circuits",
            "retained_counterparts": sum((ca[a], cb[b]) in edges for a, b in ledger.items()),
            "eligible_counterparts": sum((ca[a], cb[b]) in eligible for a, b in ledger.items()),
            "ledger_pairs": len(ledger),
            "selected_agree_with_ledger": sum(ledger.get(p["a"]) == p["b"] for p in pairs),
            "path_name_baseline_pairs": len(set(ca) & set(cb)),
        }
        moved = "TOP/XB0/XL/XL/XL/M1"
        target = ledger[moved]
        assert target in cb
        profile = next(profile for cls in result["b"]["classes"] for profile in cls["raw_profiles"]
                       if target in profile["members"])
        assert {"name": "W", "value": "6u"} in profile["parameters"]
        group_sizes = [(sum(len(c["members"]) for c in result["a"]["classes"] if c["id"] in g["a_classes"]),
                        sum(len(c["members"]) for c in result["b"]["classes"] if c["id"] in g["b_classes"]))
                       for g in result["groups"] if ca[moved] in g["a_classes"]]
        summary["edited_occurrence"] = {"a": moved, "b": target, "new_value_profile_members": len(profile["members"]),
                                        "candidate_retained": (ca[moved], cb[target]) in edges,
                                        "group_sizes_a_b": group_sizes}
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-netlist", type=Path)
    parser.add_argument("--public-format", default="ngspice", choices=("eldo", "ngspice"))
    parser.add_argument("--banks", type=int, default=44)
    args = parser.parse_args()
    if args.banks < 1:
        parser.error("--banks must be positive")
    evidence = {"date_utc": datetime.now(timezone.utc).isoformat(),
                "python": platform.python_version(), "numpy": numpy.__version__, "scipy": scipy.__version__,
                "platform": platform.platform(), "options": {},
                "limits": ["No simulator or electrical validation", "No representative workplace design",
                           "Synthetic stress history is not unique truth under symmetry",
                           "Frozen-context extension not implemented or compared", "Peak RSS includes interpreter and imported libraries"]}
    a, b = from_file(HERE / "before.sp"), from_file(HERE / "after.sp")
    result = compare(a, b, top_a="TOP", top_b="TOP", scope_a=InputScope(globals_complete=True), scope_b=InputScope(globals_complete=True))
    evidence["small"] = summarize(result)
    a, b, ledger = stress_fixture(args.banks)
    start = time.perf_counter()
    result = compare(a, b, top_a="TOP", top_b="TOP_v2", scope_a=InputScope(globals_complete=True), scope_b=InputScope(globals_complete=True))
    evidence["stress"] = summarize(result, ledger)
    evidence["stress"]["wall_seconds"] = time.perf_counter() - start
    evidence["stress"]["description"] = "Synthetic analog motifs, populated branching hierarchy, connected banks; rename/reorder plus moved specialized leaf edit"
    evidence["options"] = result["options"]
    if args.public_netlist:
        data = from_file(args.public_netlist, spice_format=args.public_format)
        circuits = [data.top, *data.subcircuits]
        # One raw primitive value edit, while all object names remain intact.
        owner = next(c for c in circuits if any(d.name.startswith("R") and d.parameters for d in c.devices))
        device = next(d for d in owner.devices if d.name.startswith("R") and d.parameters)
        changed = replace(device, parameters=(replace(device.parameters[0], value="{2*(" + device.parameters[0].value + ")}"), *device.parameters[1:]))
        updated = replace(owner, devices=tuple(changed if d is device else d for d in owner.devices))
        other = replace(data, top=updated if owner is data.top else data.top,
                        subcircuits=tuple(updated if c is owner else c for c in data.subcircuits))
        result = compare(data, other, top_a=data.top.name, top_b=data.top.name)
        evidence["public"] = {"filename": args.public_netlist.name,
                              "sha256": hashlib.sha256(args.public_netlist.read_bytes()).hexdigest(),
                              "diagnostics": len(data.diagnostics), "edited_definition": owner.name,
                              "edited_device": device.name, **summarize(result)}
    evidence["peak_process_rss_kib_linux"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    args.output.write_text(json.dumps(evidence, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"stress": evidence["stress"], "peak_rss_kib": evidence["peak_process_rss_kib_linux"]}, indent=2))


if __name__ == "__main__":
    main()
