#!/usr/bin/env python3
"""Prepare and run a bounded local automatic hierarchy trial.

Generated manifests and reports contain design-derived data. Keep the complete
trial directory inside the authorized local environment unless reviewed for
disclosure.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shlex
import sys


PROPOSAL_FORMAT = "luna-unmatched-window-proposals-v2"
MANIFEST_FORMAT = "hierarchy-relative-window-input-v2"
STABLE_FORMAT = "deterministic-relative-path-windows-v1"
UNMATCHED_FORMAT = "unmatched-hierarchy-frontiers-v1"
CONFIG_FORMAT = "automatic-hierarchy-trial-config-v3"
SUMMARY_FORMAT = "automatic-hierarchy-trial-summary-v2"
RECEIPT_FORMAT = "automatic-hierarchy-batch-receipt-v1"
PROPOSAL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def atomic_write(path: Path, data: bytes, *, replace: bool = True) -> None:
    if path.exists() and not replace:
        raise ValueError(f"output already exists: {path}; pass --replace to overwrite")
    temporary = path.with_name(path.name + ".tmp")
    if temporary.exists():
        raise ValueError(f"temporary output already exists: {temporary}")
    try:
        temporary.write_bytes(data)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def relative_display(parts: tuple[str, ...]) -> str:
    if not parts:
        return "."
    from netlist_comparison.model import location
    return location(parts)


def hierarchy_side(path: Path, top: str, root: str | None, max_objects: int,
                   scope) -> dict:
    from netlist_comparison.cli import load_netlist
    from netlist_comparison.expand import expand
    from netlist_comparison.model import Options

    data = load_netlist(path, "canonical")
    view = expand(data, top, scope,
                  Options(black_box_missing=True, max_objects=max_objects), path=root)
    if view.budget_exhausted:
        raise ValueError(
            f"hierarchy expansion exceeded --max-objects={max_objects}; raise it explicitly"
        )
    root_segments = tuple(view.occurrences[0]["path_segments"])
    by_parent: dict[str, list[dict]] = {}
    for occurrence in view.occurrences:
        if occurrence["parent"] is not None:
            by_parent.setdefault(occurrence["parent"], []).append(occurrence)
    nodes = []
    seen: dict[tuple[str, ...], str] = {}
    for occurrence in view.occurrences:
        segments = tuple(occurrence["path_segments"])
        if segments[:len(root_segments)] != root_segments:
            raise ValueError("expanded occurrence escaped the selected hierarchy root")
        relative = segments[len(root_segments):]
        key = tuple(part.casefold() for part in relative)
        if key in seen:
            raise ValueError(
                f"case-folded relative hierarchy collision: {seen[key]} and {occurrence['path']}"
            )
        seen[key] = occurrence["path"]
        children = sorted(by_parent.get(occurrence["path"], []),
                          key=lambda row: row["path"])
        nodes.append({
            "path": occurrence["path"],
            "path_segments": list(segments),
            "parent": None if not relative else occurrence["parent"],
            "relative_path": relative_display(relative),
            "relative_key": list(key),
            "name": segments[-1],
            "depth": len(relative),
            "descendant_leaf_count": occurrence["leaf_count"],
            "direct_child_count": len(children),
            "direct_child_names": [row["path_segments"][-1] for row in children],
            "port_count": len(occurrence.get("call_connections", [])),
        })
    nodes.sort(key=lambda node: tuple(node["relative_key"]))
    return {
        "selected_root": view.occurrences[0]["path"],
        "selected_root_is_top": root is None,
        "node_count": len(nodes),
        "total_leaf_count": len(view.leaves),
        "nodes": nodes,
    }


def node_indexes(manifest: dict) -> dict[str, dict[tuple[str, ...], dict]]:
    indexes = {}
    for side in ("a", "b"):
        index = {}
        for node in manifest["sides"][side]["nodes"]:
            key = tuple(node["relative_key"])
            if key in index:
                raise ValueError(f"duplicate relative hierarchy key on side {side.upper()}")
            index[key] = node
        indexes[side] = index
    return indexes


def selection_paths(manifest: dict, side: str, key: tuple[str, ...], node: dict) -> list[str]:
    if not key and manifest["sides"][side]["selected_root_is_top"]:
        return []
    return [node["path"]]


def stable_id(key: tuple[str, ...]) -> str:
    encoded = json.dumps(key, separators=(",", ":"), ensure_ascii=False).encode()
    return "S" + hashlib.sha256(encoded).hexdigest()[:16]


def build_stable_windows(manifest: dict, manifest_sha256: str,
                         leaf_cap: int, max_windows: int) -> dict:
    indexes = node_indexes(manifest)
    shared = sorted(set(indexes["a"]) & set(indexes["b"]))
    windows, excluded, identifiers = [], [], set()
    for key in shared:
        a, b = indexes["a"][key], indexes["b"][key]
        counts = {"a": a["descendant_leaf_count"], "b": b["descendant_leaf_count"]}
        reasons = []
        if min(counts.values()) < 1:
            reasons.append("empty_scope")
        if max(counts.values()) > leaf_cap:
            reasons.append("leaf_cap")
        if reasons:
            excluded.append({
                "relative_path": a["relative_path"],
                "paths_a": selection_paths(manifest, "a", key, a),
                "paths_b": selection_paths(manifest, "b", key, b),
                "leaves_a": counts["a"], "leaves_b": counts["b"],
                "reasons": reasons,
            })
            continue
        identifier = stable_id(key)
        if identifier in identifiers:
            raise ValueError("stable window ID collision")
        identifiers.add(identifier)
        windows.append({
            "id": identifier,
            "source": "deterministic_relative_path",
            "relative_path": a["relative_path"],
            "paths_a": selection_paths(manifest, "a", key, a),
            "paths_b": selection_paths(manifest, "b", key, b),
            "estimated_leaves_a": counts["a"],
            "estimated_leaves_b": counts["b"],
            "hierarchy_signals": {
                "leaf_count_changed": counts["a"] != counts["b"],
                "port_count_changed": a["port_count"] != b["port_count"],
                "direct_child_names_changed":
                    sorted(name.casefold() for name in a["direct_child_names"]) !=
                    sorted(name.casefold() for name in b["direct_child_names"]),
            },
        })
    if len(windows) > max_windows:
        raise ValueError(
            f"deterministic hierarchy scan has {len(windows)} windows, above "
            f"--max-windows={max_windows}; raise the bound explicitly (no truncation performed)"
        )
    return {
        "format": STABLE_FORMAT,
        "manifest_sha256": manifest_sha256,
        "selection": (
            "Every case-insensitive relative hierarchy path shared by both selected "
            f"roots with 1..{leaf_cap} descendant leaves on each side; no ranking."
        ),
        "window_count": len(windows),
        "windows": windows,
        "shared_not_run": excluded,
        "meaning": (
            "Relative path equality supplies a deterministic comparison window, not "
            "verified correspondence or edit history."
        ),
    }


def build_unmatched_handoff(manifest: dict, manifest_sha256: str,
                            leaf_cap: int) -> dict:
    indexes = node_indexes(manifest)
    shared = set(indexes["a"]) & set(indexes["b"])
    sides = {}
    for side in ("a", "b"):
        other = "b" if side == "a" else "a"
        unmatched = set(indexes[side]) - set(indexes[other])
        frontiers = []
        for key in sorted(unmatched):
            if key[:-1] not in shared:
                continue
            parent = indexes[side][key[:-1]]
            rows = []
            for descendant_key, node in sorted(indexes[side].items()):
                if descendant_key[:len(key)] != key:
                    continue
                count = node["descendant_leaf_count"]
                rows.append({
                    **node,
                    "proposal_eligible": descendant_key in unmatched and 1 <= count <= leaf_cap,
                })
            frontiers.append({
                "root_path": indexes[side][key]["path"],
                "root_relative_path": indexes[side][key]["relative_path"],
                "shared_parent": {
                    "path": parent["path"], "relative_path": parent["relative_path"],
                },
                "nodes": rows,
            })
        eligible = sorted(
            node["path"] for key, node in indexes[side].items()
            if key in unmatched and 1 <= node["descendant_leaf_count"] <= leaf_cap
        )
        sides[side] = {
            "unmatched_path_count": len(unmatched),
            "frontier_count": len(frontiers),
            "eligible_paths": eligible,
            "frontiers": frontiers,
        }
    return {
        "format": UNMATCHED_FORMAT,
        "manifest_sha256": manifest_sha256,
        "evidence_boundary": (
            "These rows identify hierarchy labels absent at the same relative path. "
            "They do not establish additions, removals, changes or correspondence. "
            "The authorized local Luna agent may inspect the complete canonical inputs."
        ),
        "sides": sides,
    }


def local_import_roots() -> tuple[Path, ...]:
    roots = []
    for package in ("netlist_comparison", "spice_canonical"):
        module = importlib.import_module(package)
        module_file = getattr(module, "__file__", None)
        if not module_file:
            raise ValueError(f"cannot locate local import source for {package}")
        root = Path(module_file).resolve().parent.parent
        if not (root / package).is_dir():
            raise ValueError(f"unexpected local import layout for {package}: {root}")
        if root not in roots:
            roots.append(root)
    return tuple(roots)


def task_text(leaf_cap: int, trial: Path, unmatched: dict,
              import_roots: tuple[Path, ...]) -> str:
    script = Path(__file__).resolve()
    # Preserve a virtual-environment launcher instead of resolving its symlink
    # to a base interpreter that may not have the comparator's dependencies.
    python = Path(sys.executable).absolute()
    pythonpath = os.pathsep.join(str(root) for root in import_roots)
    command_prefix = ["/usr/bin/env", f"PYTHONPATH={pythonpath}", python, script]
    validate_command = " ".join(
        shlex.quote(str(part)) for part in (*command_prefix, "validate", trial)
    )
    run_command = " ".join(
        shlex.quote(str(part)) for part in (*command_prefix, "run", trial)
    )
    a = unmatched["sides"]["a"]
    b = unmatched["sides"]["b"]
    return f"""# Luna unmatched-hierarchy task

You are a Luna medium agent performing one bounded local hierarchy proposal pass.
Do not delegate, use the network, install dependencies, commit, publish, or send
data outside this local environment. The operator authorizes you to read the
canonical paths in `trial-config.json`, the complete sensitive local inputs, and
the generated comparator results. The compact handoff reduces reading cost; it
is not a privacy filter.

Start with `unmatched-branch-input.json`. There is no top-level `frontiers` key.
The exact arrays are `sides.a.frontiers` and `sides.b.frontiers`; every frontier
contains a `nodes` array. The only allowed proposal path lists are
`sides.a.eligible_paths` and `sides.b.eligible_paths`. This prepared handoff
reports A={a['frontier_count']} frontiers/{len(a['eligible_paths'])} eligible paths
and B={b['frontier_count']} frontiers/{len(b['eligible_paths'])} eligible paths.
Read those four arrays and confirm both side counts in `luna-report.md` before
abstaining. Its frontier rows have no equal relative hierarchy path on the other
side. "Unmatched" does not mean added, removed, or changed. Inspect full inputs
locally when cells, interfaces, repetition, or topology would materially
disambiguate a relationship.

Write `proposals.json` and `luna-report.md`. Use the `unmatched_sha256` value from
`trial-config.json` as `input_sha256`:

```json
{{
  "format": "{PROPOSAL_FORMAT}",
  "input_sha256": "<unmatched_sha256>",
  "method": {{"summary": "...", "used_fields": [], "excluded_fields": []}},
  "proposals": [
    {{
      "id": "P001", "priority": 1, "purpose": "change_candidate",
      "relationship": "1:1", "paths_a": ["..."], "paths_b": ["..."],
      "estimated_leaves_a": 1, "estimated_leaves_b": 1,
      "name_evidence": ["short factual reason"],
      "uncertainty": "short limitation"
    }}
  ]
}}
```

Select at most 50 rename, move, split, or merge candidates. Use only paths listed
in each side's `eligible_paths`; shared relative paths are already enumerated
deterministically. Do not propose quiet controls. Each side's summed descendant
leaf count must be at most {leaf_cap}. Same-side union members must be distinct
and non-overlapping. General 1:n and n:1 relations are allowed for any positive n.
Every proposal is a heuristic trial, never identity or a known design change.
If no relationship is defensible, write an empty `proposals` list and explain
the abstention in `luna-report.md`.

After writing proposals, run:

```sh
{validate_command}
{run_command}
```

`run` executes one ordered batch: deterministic windows first, then validated
Luna proposals. Inspect `trial-summary.json` and a bounded selection of full
results. Write `luna-assessment.md` for a schematic reader. Its first page
should contain at most eight short findings with an A location, B location,
what differs in ordinary words, and what to inspect on the schematics. Put
result IDs, exact statuses, evidence kinds and charged support next to each
finding or in a compact evidence note. Keep the opening explanation to one or
two plain sentences per finding; put internal field names, net indices and proof
details after it. Before finalizing, check every direction, count and terminal
role in the prose against the cited result; in particular, do not call A
smaller when A has more leaves or summarize one displayed mismatch as the
whole certified residual. Keep full paths in this local file; do not export
them. Lead with supported differences; place no-card comparisons,
unmatched hypotheses and abstentions in a separate short section, not the
prioritized findings. Distinguish comparator-backed observations from your
tentative interpretation and state what remains unknown.

Look for represented additions and removals, cell-class population changes,
possible block splits/merges, rewiring, and pin/interface differences. Inspect
at least one card of each evidence kind present among the card-bearing windows,
including terminal residuals when present, before deciding what deserves the
first page. A terminal residual may support a count of unavoidable attachment
disagreements and implicated terminal roles even when exact device identity is
ambiguous; explain that limit in ordinary words. For a similar-looking A/B
block, compare available formal pins, named terminal roles
and represented attachments when the inputs and result evidence support it.
Describe a specific differing pin/role only when you can trace both sides;
do not infer pin names from positional `@N` tokens or call different raw net
labels a rewire. If a result supports only an interface-count or cell-inventory
residual, say that rather than inventing a pin-level explanation. An A-only or
B-only hierarchy branch is a candidate removal/addition, rename or move until
evidence distinguishes them. A population surplus is not proof of historical
addition/removal. Keep unsupported hypotheses in a separate section.

If parent and child windows appear to show the same issue, lead with the most
specific useful location and mention the other result IDs; retain independent
child findings and abstentions. Include a brief count of certified, abstained,
card-bearing and unmatched windows, plus the most important blind spots. Keep
the first page concise enough for an operator to decide what to inspect next.
Say "no selected cards" rather than quiet or unchanged. Never let a proposal label
override comparator evidence or treat certification inside a supplied window
as proof that the A/B scopes correspond.
"""


def prepare(args: argparse.Namespace) -> None:
    from netlist_comparison import InputScope

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    protected = [output / name for name in (
        "hierarchy-only-input.json", "stable-windows.json",
        "unmatched-branch-input.json", "input.sha256", "LUNA_TASK.md",
        "trial-config.json",
    )]
    if any(path.exists() for path in protected) and not args.replace:
        raise ValueError("trial files already exist; choose another directory or pass --replace")

    input_a = args.input_a.resolve()
    input_b = (args.input_b or args.input_a).resolve()
    before_hashes = {"a": file_digest(input_a), "b": file_digest(input_b)}
    top_b = args.top_b or args.top_a
    scope = InputScope(tuple(["0", *args.global_net]), args.globals_complete)
    manifest = {
        "format": MANIFEST_FORMAT,
        "evidence_boundary": (
            "Hierarchy paths, relative keys, parent relationships, descendant leaf "
            "counts, direct child names/counts and port counts. The authorized local "
            "agent may inspect complete sensitive inputs; this is not a privacy filter."
        ),
        "sides": {
            "a": hierarchy_side(input_a, args.top_a, args.root_a, args.max_objects, scope),
            "b": hierarchy_side(input_b, top_b, args.root_b, args.max_objects, scope),
        },
    }
    after_hashes = {"a": file_digest(input_a), "b": file_digest(input_b)}
    if after_hashes != before_hashes:
        raise ValueError("canonical input changed while preparing the trial")
    manifest_bytes = json_bytes(manifest)
    manifest_hash = digest_bytes(manifest_bytes)
    stable = build_stable_windows(manifest, manifest_hash,
                                  args.leaf_cap, args.max_windows)
    unmatched = build_unmatched_handoff(manifest, manifest_hash, args.leaf_cap)
    stable_bytes, unmatched_bytes = json_bytes(stable), json_bytes(unmatched)
    stable_hash, unmatched_hash = digest_bytes(stable_bytes), digest_bytes(unmatched_bytes)
    config = {
        "format": CONFIG_FORMAT,
        "manifest_sha256": manifest_hash,
        "stable_sha256": stable_hash,
        "unmatched_sha256": unmatched_hash,
        "inputs": {
            "a": {"path": str(input_a), "sha256": before_hashes["a"]},
            "b": None if args.input_b is None else {
                "path": str(input_b), "sha256": before_hashes["b"],
            },
        },
        "top_a": args.top_a, "top_b": top_b,
        "root_a": args.root_a, "root_b": args.root_b,
        "input_scope": {
            "global_nets": list(scope.global_nets),
            "globals_complete": scope.globals_complete,
        },
        "max_objects": args.max_objects, "max_windows": args.max_windows,
        "operator": {
            "leaves": args.leaf_cap, "nets": args.net_cap,
            "counterparts": args.counterpart_cap,
            "retained_paths": args.retained_path_cap,
            "presentation_paths": args.presentation_path_cap,
            "parameters": not args.omit_parameters,
            "cards": args.card_cap, "query_seconds": args.query_seconds,
            "seconds": args.seconds, "memory_mib": args.memory_mib,
        },
    }
    writes = {
        output / "hierarchy-only-input.json": manifest_bytes,
        output / "stable-windows.json": stable_bytes,
        output / "unmatched-branch-input.json": unmatched_bytes,
        output / "trial-config.json": json_bytes(config),
        output / "LUNA_TASK.md": task_text(
            args.leaf_cap, output, unmatched, local_import_roots()
        ).encode(),
        output / "input.sha256": (
            f"{manifest_hash}  hierarchy-only-input.json\n"
            f"{stable_hash}  stable-windows.json\n"
            f"{unmatched_hash}  unmatched-branch-input.json\n"
        ).encode(),
    }
    for path, data in writes.items():
        atomic_write(path, data)
    print(f"Prepared {output}")
    print(
        f"Deterministic windows: {stable['window_count']}; unmatched frontiers A/B: "
        f"{unmatched['sides']['a']['frontier_count']}/"
        f"{unmatched['sides']['b']['frontier_count']}"
    )
    print("Trial data may be sensitive; keep the directory in the authorized local environment.")


def load_base(directory: Path, *, verify_inputs: bool = False) -> tuple[dict, dict, dict, dict]:
    paths = {
        "manifest": directory / "hierarchy-only-input.json",
        "stable": directory / "stable-windows.json",
        "unmatched": directory / "unmatched-branch-input.json",
        "config": directory / "trial-config.json",
    }
    raw = {name: path.read_bytes() for name, path in paths.items()}
    manifest, stable, unmatched, config = (json.loads(raw[name]) for name in paths)
    if manifest.get("format") != MANIFEST_FORMAT or stable.get("format") != STABLE_FORMAT:
        raise ValueError("unexpected hierarchy or stable-window format")
    if unmatched.get("format") != UNMATCHED_FORMAT or config.get("format") != CONFIG_FORMAT:
        raise ValueError("unexpected unmatched handoff or trial config format")
    hashes = {
        "manifest_sha256": digest_bytes(raw["manifest"]),
        "stable_sha256": digest_bytes(raw["stable"]),
        "unmatched_sha256": digest_bytes(raw["unmatched"]),
    }
    if any(config.get(name) != value for name, value in hashes.items()):
        raise ValueError("trial artifacts do not match trial config")
    expected_stable = build_stable_windows(
        manifest, hashes["manifest_sha256"],
        config["operator"]["leaves"], config["max_windows"],
    )
    expected_unmatched = build_unmatched_handoff(
        manifest, hashes["manifest_sha256"], config["operator"]["leaves"]
    )
    if stable != expected_stable or unmatched != expected_unmatched:
        raise ValueError("derived stable or unmatched artifact does not reconstruct")
    if verify_inputs:
        input_a = Path(config["inputs"]["a"]["path"])
        input_b_row = config["inputs"]["b"]
        actual = {"a": file_digest(input_a)}
        expected = {"a": config["inputs"]["a"]["sha256"]}
        if input_b_row is not None:
            actual["b"] = file_digest(Path(input_b_row["path"]))
            expected["b"] = input_b_row["sha256"]
        if actual != expected:
            raise ValueError("canonical input changed after trial preparation")
    return manifest, stable, unmatched, config


def _proposal_method(document: dict) -> None:
    if set(document) != {"format", "input_sha256", "method", "proposals"}:
        raise ValueError("proposal document has unexpected or missing fields")
    method = document["method"]
    if not isinstance(method, dict) or set(method) != {
        "summary", "used_fields", "excluded_fields",
    }:
        raise ValueError("method must contain summary, used_fields and excluded_fields")
    if not isinstance(method["summary"], str) or not method["summary"].strip():
        raise ValueError("method summary must be nonempty")
    for field in ("used_fields", "excluded_fields"):
        if not isinstance(method[field], list) or not all(
            isinstance(value, str) and value for value in method[field]
        ):
            raise ValueError(f"method {field} must be a list of nonempty strings")


def validate(directory: Path) -> list[dict]:
    manifest, _, unmatched, config = load_base(directory)
    document = json.loads((directory / "proposals.json").read_text(encoding="utf-8"))
    _proposal_method(document)
    if document["format"] != PROPOSAL_FORMAT or document["input_sha256"] != config["unmatched_sha256"]:
        raise ValueError("proposals do not match the unmatched-branch handoff")
    proposals = document["proposals"]
    if not isinstance(proposals, list) or len(proposals) > 50:
        raise ValueError("proposals must be a list containing 0-50 rows")
    lookups = {
        side: {node["path"]: node for node in manifest["sides"][side]["nodes"]}
        for side in ("a", "b")
    }
    eligible = {
        side: set(unmatched["sides"][side]["eligible_paths"])
        for side in ("a", "b")
    }
    ids, priorities = set(), set()
    required = {
        "id", "priority", "purpose", "relationship", "paths_a", "paths_b",
        "estimated_leaves_a", "estimated_leaves_b", "name_evidence", "uncertainty",
    }
    for row in proposals:
        if not isinstance(row, dict) or set(row) != required:
            raise ValueError("proposal row has unexpected or missing fields")
        proposal_id = row["id"]
        if not isinstance(proposal_id, str) or not PROPOSAL_ID.fullmatch(proposal_id):
            raise ValueError("proposal IDs must be safe filename components")
        if type(row["priority"]) is not int or row["priority"] < 1:
            raise ValueError(f"{proposal_id}: priority must be a positive integer")
        if proposal_id in ids or row["priority"] in priorities:
            raise ValueError("proposal IDs and priorities must be unique")
        ids.add(proposal_id); priorities.add(row["priority"])
        if row["purpose"] != "change_candidate":
            raise ValueError(f"{proposal_id}: unmatched proposals must be change_candidate")
        for side in ("a", "b"):
            paths = row[f"paths_{side}"]
            if (
                not isinstance(paths, list) or not paths
                or not all(isinstance(path, str) for path in paths)
                or len(paths) != len(set(paths))
                or any(path not in eligible[side] for path in paths)
            ):
                raise ValueError(
                    f"{proposal_id}: paths must come from unmatched eligible {side.upper()} paths"
                )
            segments = [tuple(lookups[side][path]["path_segments"]) for path in paths]
            if any(
                x[:len(y)] == y or y[:len(x)] == x
                for index, x in enumerate(segments) for y in segments[index + 1:]
            ):
                raise ValueError(f"{proposal_id}: overlapping {side.upper()} union")
            count = sum(lookups[side][path]["descendant_leaf_count"] for path in paths)
            estimate = row[f"estimated_leaves_{side}"]
            if type(estimate) is not int or count != estimate or count > config["operator"]["leaves"]:
                raise ValueError(
                    f"{proposal_id}: incorrect or over-cap {side.upper()} leaf estimate"
                )
        expected_relation = f"{len(row['paths_a'])}:{len(row['paths_b'])}"
        if row["relationship"] != expected_relation or min(len(row["paths_a"]), len(row["paths_b"])) != 1:
            raise ValueError(
                f"{proposal_id}: relationship must describe a 1:1, 1:n or n:1 proposal"
            )
        if not isinstance(row["name_evidence"], list) or not row["name_evidence"] or not all(
            isinstance(value, str) and value for value in row["name_evidence"]
        ):
            raise ValueError(f"{proposal_id}: name_evidence must be a nonempty string list")
        if not isinstance(row["uncertainty"], str) or not row["uncertainty"].strip():
            raise ValueError(f"{proposal_id}: uncertainty must be nonempty")
    print(f"Validated {len(proposals)} unmatched-branch proposals")
    return proposals


def _expected_scopes(manifest: dict, side: str, paths: list[str]) -> list[str]:
    return paths or [manifest["sides"][side]["selected_root"]]


def run(args: argparse.Namespace) -> None:
    from netlist_comparison import InputScope, Options, compare_operator_scoped_batch
    from netlist_comparison.cli import load_netlist
    from netlist_comparison.operator_scoped import validate_saved_extension

    directory = args.directory.resolve()
    manifest, stable, _, config = load_base(directory, verify_inputs=True)
    proposals_supplied = (directory / "proposals.json").exists()
    proposals = validate(directory) if proposals_supplied else []
    descriptors = [
        {**row, "result_group": "stable"} for row in stable["windows"]
    ] + [
        {**row, "source": "luna_unmatched_proposal", "result_group": "luna"}
        for row in sorted(proposals, key=lambda value: value["priority"])
    ]
    descriptor_ids = [row["id"] for row in descriptors]
    if len(descriptor_ids) != len(set(descriptor_ids)):
        raise ValueError("deterministic and Luna window IDs collide")
    if not descriptors:
        raise ValueError("trial has no deterministic windows or Luna proposals to run")
    if len(descriptors) > config["max_windows"]:
        raise ValueError(
            f"combined batch has {len(descriptors)} windows, above the hard "
            f"limit {config['max_windows']} (no truncation performed)"
        )
    result_targets = [
        directory / "results" / row["result_group"] / f"{row['id']}.json"
        for row in descriptors
    ]
    protected = result_targets + [
        directory / "trial-summary.json", directory / "batch-receipt.json",
    ]
    if not args.replace and any(path.exists() for path in protected):
        raise ValueError("result files already exist; pass --replace to overwrite this run")
    for group in ("stable", "luna"):
        (directory / "results" / group).mkdir(parents=True, exist_ok=True)

    input_a = Path(config["inputs"]["a"]["path"])
    input_b_row = config["inputs"]["b"]
    a = load_netlist(input_a, "canonical")
    b = a if input_b_row is None else load_netlist(Path(input_b_row["path"]), "canonical")
    values = config["operator"]
    options = Options(
        matching_mode="operator_scoped", black_box_missing=True,
        max_objects=config["max_objects"],
        operator_max_leaves=values["leaves"],
        operator_max_nets=values["nets"],
        operator_max_counterparts=values["counterparts"],
        operator_retained_paths=values["retained_paths"],
        operator_presentation_paths=values["presentation_paths"],
        operator_parameters=values["parameters"],
        operator_max_cards=values["cards"],
        operator_query_seconds=values["query_seconds"],
        operator_time_limit=values["seconds"],
        operator_memory_mib=values["memory_mib"],
    )
    windows = [
        {"paths_a": row["paths_a"], "paths_b": row["paths_b"]}
        for row in descriptors
    ]
    batch = compare_operator_scoped_batch(
        a, b, top_a=config["top_a"], top_b=config["top_b"], windows=windows,
        options=options,
        scope_a=InputScope(
            tuple(config["input_scope"]["global_nets"]),
            config["input_scope"]["globals_complete"],
        ),
        scope_b=InputScope(
            tuple(config["input_scope"]["global_nets"]),
            config["input_scope"]["globals_complete"],
        ),
        same_full_netlist=input_b_row is None,
    )
    if batch.get("kind") != "operator_scoped_batch_v1":
        raise ValueError("unexpected operator batch result")
    incomplete = bool(batch.get("resources", {}).get("incomplete"))
    reports = batch.get("results")
    if not isinstance(reports, list) or (incomplete and reports) or (
        not incomplete and len(reports) != len(descriptors)
    ):
        raise ValueError("operator batch returned an inconsistent result count")
    summary_rows = []
    for index, (descriptor, report, target) in enumerate(
        zip(descriptors, reports, result_targets)
    ):
        extension = report["operator_scoped"]
        validate_saved_extension(extension)
        if extension["resources"].get("batch_window_index") != index:
            raise ValueError("operator batch result order does not match requested windows")
        window = extension["windows"][0]
        for side in ("a", "b"):
            expected = _expected_scopes(manifest, side, descriptor[f"paths_{side}"])
            if window["supplied_scopes"][side] != expected:
                raise ValueError("operator batch result scope does not match requested window")
        encoded = json_bytes(report)
        atomic_write(target, encoded, replace=args.replace)
        summary_rows.append({
            "id": descriptor["id"], "source": descriptor["source"],
            "relative_path": descriptor.get("relative_path"),
            "relationship": descriptor.get("relationship", "1:1"),
            "paths_a": descriptor["paths_a"],
            "paths_b": descriptor["paths_b"],
            "status": extension["status"],
            "certified_internal": extension["certified_internal"],
            "card_count": len(extension["cards"]),
            "card_lanes": [card["lane"] for card in extension["cards"]],
            "charged_count": extension["charged_count"],
            "result": str(target.relative_to(directory)),
            "result_sha256": digest_bytes(encoded),
        })
        print(f"{descriptor['id']}: {extension['status']} ({len(extension['cards'])} cards)")
    status = batch.get("status", "incomplete" if incomplete else "complete")
    summary = {
        "format": SUMMARY_FORMAT, "status": status,
        "requested_window_count": len(descriptors),
        "completed_window_count": len(summary_rows),
        "luna_proposals": (
            "included" if proposals else
            "none_proposed" if proposals_supplied else
            "not_supplied"
        ),
        "results": summary_rows,
        "interpretation": (
            "Every scope relation is input, never discovered correspondence. A certified "
            "window with no selected cards is not an unchanged or equivalence verdict. "
            "Missing batch results are incomplete execution, never quiet evidence."
        ),
    }
    receipt = {
        "format": RECEIPT_FORMAT, "status": status,
        "manifest_sha256": config["manifest_sha256"],
        "stable_sha256": config["stable_sha256"],
        "unmatched_sha256": config["unmatched_sha256"],
        "ordered_window_ids": [row["id"] for row in descriptors],
        "reuse": batch.get("reuse"), "resources": batch.get("resources"),
    }
    atomic_write(directory / "trial-summary.json", json_bytes(summary),
                 replace=args.replace)
    atomic_write(directory / "batch-receipt.json", json_bytes(receipt),
                 replace=args.replace)
    print(f"Saved {len(summary_rows)} complete reports under {directory / 'results'}")
    if incomplete:
        print(f"Batch incomplete: {batch.get('status')}; no per-window result was inferred")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    make = sub.add_parser("prepare", help="enumerate stable windows and make a Luna handoff")
    make.add_argument("--input-a", type=Path, required=True)
    make.add_argument("--input-b", type=Path,
                      help="omit for two instances in one canonical file")
    make.add_argument("--top-a", required=True)
    make.add_argument("--top-b", help="defaults to --top-a")
    make.add_argument("--root-a",
                      help="complete A instance path; omit for the selected A top")
    make.add_argument("--root-b",
                      help="complete B instance path; omit for the selected B top")
    make.add_argument("--global-net", action="append", default=[], metavar="NAME",
                      help="repeat for each explicit global net; 0 is always included")
    make.add_argument("--globals-complete", action="store_true",
                      help="assert that 0 and --global-net names are the complete set")
    make.add_argument("--omit-parameters", action="store_true",
                      help="omit the operator-scoped parameter evidence lane")
    make.add_argument("--output", type=Path, required=True)
    make.add_argument("--leaf-cap", type=int, default=64)
    make.add_argument("--net-cap", type=int, default=96)
    make.add_argument("--counterpart-cap", type=int, default=16)
    make.add_argument("--retained-path-cap", type=int, default=200)
    make.add_argument("--presentation-path-cap", type=int, default=100)
    make.add_argument("--card-cap", type=int, default=12)
    make.add_argument("--query-seconds", type=float, default=5)
    make.add_argument("--seconds", type=float, default=60)
    make.add_argument("--memory-mib", type=int, default=3072)
    make.add_argument("--max-objects", type=int, default=20_000)
    make.add_argument("--max-windows", type=int, default=256)
    make.add_argument("--replace", action="store_true")
    check = sub.add_parser("validate", help="validate Luna unmatched-branch proposals")
    check.add_argument("directory", type=Path)
    execute = sub.add_parser("run", help="run one deterministic-plus-Luna operator batch")
    execute.add_argument("directory", type=Path)
    execute.add_argument("--replace", action="store_true")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "prepare":
            numeric = (
                args.leaf_cap, args.net_cap, args.counterpart_cap,
                args.retained_path_cap, args.presentation_path_cap, args.card_cap,
                args.query_seconds, args.seconds, args.memory_mib,
                args.max_objects, args.max_windows,
            )
            if any(value <= 0 for value in numeric):
                raise ValueError("all workflow limits must be positive")
            if args.memory_mib < 64:
                raise ValueError("memory must be at least 64 MiB")
            if args.presentation_path_cap > args.retained_path_cap:
                raise ValueError("presentation path cap cannot exceed retained path cap")
            if args.input_b is None and not (args.root_a and args.root_b):
                raise ValueError("one input requires both --root-a and --root-b")
            prepare(args)
        elif args.command == "validate":
            validate(args.directory.resolve())
        else:
            run(args)
    except (
        ValueError, OSError, KeyError, TypeError, AttributeError, IndexError,
        json.JSONDecodeError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
