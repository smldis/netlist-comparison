#!/usr/bin/env python3
"""Prepare, validate, and execute a local Luna-guided hierarchy trial.

The generated trial directory contains design-derived data. Keep it in the
authorized local environment unless it has been reviewed for disclosure.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys


PROPOSAL_FORMAT = "luna-hierarchy-window-proposals-v1"
MANIFEST_FORMAT = "hierarchy-name-window-proposal-v1"
CONFIG_FORMAT = "luna-hierarchy-trial-config-v1"
SUMMARY_FORMAT = "luna-hierarchy-trial-summary-v1"
PROPOSAL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def child_name(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def hierarchy_side(path: Path, top: str, root: str | None, max_objects: int) -> dict:
    from netlist_comparison.cli import load_netlist
    from netlist_comparison.expand import expand
    from netlist_comparison.model import InputScope, Options

    data = load_netlist(path, "canonical")
    view = expand(
        data,
        top,
        InputScope(),
        Options(black_box_missing=True, max_objects=max_objects),
        path=root,
    )
    if view.budget_exhausted:
        raise ValueError(
            f"hierarchy expansion exceeded --max-objects={max_objects}; raise it explicitly"
        )
    by_parent: dict[str, list[dict]] = {}
    selected_root = view.occurrences[0]["path"]
    for occurrence in view.occurrences:
        if occurrence["parent"] is not None:
            by_parent.setdefault(occurrence["parent"], []).append(occurrence)
    base_depth = view.occurrences[0]["depth"]
    nodes = []
    for occurrence in view.occurrences:
        children = sorted(
            by_parent.get(occurrence["path"], []), key=lambda row: row["path"]
        )
        nodes.append(
            {
                "path": occurrence["path"],
                # expand retains the outside parent for selected subtrees. The
                # handoff is a self-contained tree, so its selected root is null.
                "parent": (
                    None
                    if occurrence["path"] == selected_root
                    else occurrence["parent"]
                ),
                "name": child_name(occurrence["path"]),
                "depth": occurrence["depth"] - base_depth,
                "descendant_leaf_count": occurrence["leaf_count"],
                "direct_child_count": len(children),
                "direct_child_names": [child_name(row["path"]) for row in children],
                "port_count": len(occurrence.get("call_connections", [])),
            }
        )
    return {
        "node_count": len(nodes),
        "total_leaf_count": len(view.leaves),
        "nodes": nodes,
    }


def task_text(leaf_cap: int, trial: Path) -> str:
    script = Path(__file__).resolve()
    python = Path(sys.executable).resolve()
    validate_command = " ".join(
        shlex.quote(str(part))
        for part in (python, script, "validate", trial)
    )
    run_command = " ".join(
        shlex.quote(str(part))
        for part in (
            python,
            script,
            "run",
            trial,
            "--seconds",
            "180",
            "--memory-mib",
            "3072",
        )
    )
    return f"""# Luna hierarchy-window task

You are a Luna medium agent performing one bounded local hierarchy-window pass.
Do not delegate, use the network, install dependencies, commit, publish, or send
data outside this local environment. The operator authorizes you to read the
canonical input paths in `trial-config.json`, the full local inputs, and the
generated comparator results. Sensitive design data may be used locally.

Start with `hierarchy-only-input.json` because it is compact. It contains paths,
parent/child names, descendant leaf counts and port counts. Inspect the canonical
inputs or use small local scripts when cell types, interfaces, repeated hierarchy,
or topology would materially disambiguate a proposal. Treat every proposed
relationship as a heuristic trial, never established identity or a known change.

Write `proposals.json` and `luna-report.md`. `proposals.json` must have:

```json
{{
  "format": "{PROPOSAL_FORMAT}",
  "input_sha256": "<value from input.sha256>",
  "method": {{"summary": "...", "used_fields": [], "excluded_fields": []}},
  "proposals": [
    {{
      "id": "P001",
      "priority": 1,
      "purpose": "change_candidate",
      "relationship": "1:1",
      "paths_a": ["..."],
      "paths_b": ["..."],
      "estimated_leaves_a": 1,
      "estimated_leaves_b": 1,
      "name_evidence": ["short factual reason"],
      "uncertainty": "short limitation"
    }}
  ]
}}
```

Select no more than 50 proposals. Include up to 10 defensible quiet controls;
fewer than 5, or none, is correct when the evidence does not support more. Each
side's summed descendant-leaf count must be at most {leaf_cap}. Paths in a
same-side union must be distinct and non-overlapping: no member may contain
another. Use only paths present on that side. Estimate counts exactly from the
manifest. Prefer 1:1 same-path/name candidates with hierarchy or count signals.
Also propose defensible 1:n or n:1 split/merge trials for any positive n; do not
invent them to fill a quota. Look especially for plausible rename, move, split
and merge relationships because deterministic same-path enumeration handles
stable paths better than this pass.

After writing the proposals, run:

```sh
{validate_command}
{run_command}
```

Inspect `trial-summary.json` and only the result files needed to interpret failures
or useful cards. Write `luna-assessment.md` with proposal counts by purpose and
relationship, strongest signals, exact comparison statuses, useful schematic
locations, noisy or duplicate findings, likely blind spots, and the next local
windows worth trying. Never label a candidate quiet or changed as fact, and never
let your prior guess override the comparator evidence. Validate your JSON before
finishing.
"""


def prepare(args: argparse.Namespace) -> None:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    protected = [
        output / "hierarchy-only-input.json",
        output / "input.sha256",
        output / "LUNA_TASK.md",
        output / "trial-config.json",
    ]
    if any(path.exists() for path in protected) and not args.replace:
        raise ValueError(
            "trial files already exist; choose another directory or pass --replace"
        )

    input_a = args.input_a.resolve()
    input_b = (args.input_b or args.input_a).resolve()
    top_b = args.top_b or args.top_a
    manifest = {
        "format": MANIFEST_FORMAT,
        "evidence_boundary": (
            "This compact entry point contains hierarchy paths, parent relationships, "
            "descendant leaf counts, direct child names/counts and port counts. It omits "
            "leaf topology, cells, parameters, nets, edit truth, comparison results and "
            "prior scope selections; the authorized local Luna agent may inspect the "
            "complete inputs when useful."
        ),
        "sides": {
            "a": hierarchy_side(input_a, args.top_a, args.root_a, args.max_objects),
            "b": hierarchy_side(input_b, top_b, args.root_b, args.max_objects),
        },
    }
    encoded = json_bytes(manifest)
    digest = digest_bytes(encoded)
    config = {
        "format": CONFIG_FORMAT,
        "manifest_sha256": digest,
        "input_a": str(input_a),
        # Explicitly supplying B selects two-file CLI semantics, even if A and B
        # happen to resolve to the same file.
        "input_b": str(input_b) if args.input_b is not None else None,
        "top_a": args.top_a,
        "top_b": top_b,
        "root_a": args.root_a,
        "root_b": args.root_b,
        "leaf_cap": args.leaf_cap,
    }
    (output / "hierarchy-only-input.json").write_bytes(encoded)
    (output / "input.sha256").write_text(
        digest + "  hierarchy-only-input.json\n", encoding="utf-8"
    )
    (output / "LUNA_TASK.md").write_text(
        task_text(args.leaf_cap, output), encoding="utf-8"
    )
    (output / "trial-config.json").write_bytes(json_bytes(config))
    print(f"Prepared {output}")
    print(
        "A/B hierarchy nodes: "
        f"{manifest['sides']['a']['node_count']}/"
        f"{manifest['sides']['b']['node_count']}"
    )
    print("Trial data may be sensitive; keep the directory in the authorized local environment.")


def load_trial(directory: Path) -> tuple[dict, dict, dict]:
    manifest_path = directory / "hierarchy-only-input.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    config = json.loads((directory / "trial-config.json").read_text(encoding="utf-8"))
    proposals = json.loads((directory / "proposals.json").read_text(encoding="utf-8"))
    actual = digest_bytes(manifest_bytes)
    if manifest.get("format") != MANIFEST_FORMAT:
        raise ValueError("unexpected hierarchy manifest format")
    if config.get("format") != CONFIG_FORMAT:
        raise ValueError("unexpected trial config format")
    if config.get("manifest_sha256") != actual:
        raise ValueError("trial config does not match hierarchy manifest")
    if (
        proposals.get("format") != PROPOSAL_FORMAT
        or proposals.get("input_sha256") != actual
    ):
        raise ValueError("proposals do not match hierarchy manifest")
    return manifest, config, proposals


def _proposal_method(document: dict) -> None:
    if set(document) != {"format", "input_sha256", "method", "proposals"}:
        raise ValueError("proposal document has unexpected or missing fields")
    method = document["method"]
    if not isinstance(method, dict) or set(method) != {
        "summary",
        "used_fields",
        "excluded_fields",
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
    manifest, config, document = load_trial(directory)
    _proposal_method(document)
    proposals = document["proposals"]
    if not isinstance(proposals, list) or not 1 <= len(proposals) <= 50:
        raise ValueError("proposals must be a list containing 1-50 rows")
    lookups = {
        side: {node["path"]: node for node in manifest["sides"][side]["nodes"]}
        for side in ("a", "b")
    }
    ids: set[str] = set()
    priorities: set[int] = set()
    quiet = 0
    required = {
        "id",
        "priority",
        "purpose",
        "relationship",
        "paths_a",
        "paths_b",
        "estimated_leaves_a",
        "estimated_leaves_b",
        "name_evidence",
        "uncertainty",
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
        ids.add(proposal_id)
        priorities.add(row["priority"])
        if row["purpose"] not in ("change_candidate", "quiet_control"):
            raise ValueError(f"{proposal_id}: invalid purpose")
        quiet += row["purpose"] == "quiet_control"
        for side in ("a", "b"):
            paths = row[f"paths_{side}"]
            if (
                not isinstance(paths, list)
                or not paths
                or not all(isinstance(path, str) for path in paths)
                or len(paths) != len(set(paths))
                or any(path not in lookups[side] for path in paths)
            ):
                raise ValueError(f"{proposal_id}: invalid {side.upper()} paths")
            if any(
                x.startswith(y + "/") or y.startswith(x + "/")
                for index, x in enumerate(paths)
                for y in paths[index + 1 :]
            ):
                raise ValueError(f"{proposal_id}: overlapping {side.upper()} union")
            count = sum(
                lookups[side][path]["descendant_leaf_count"] for path in paths
            )
            estimate = row[f"estimated_leaves_{side}"]
            if type(estimate) is not int or count != estimate or count > config["leaf_cap"]:
                raise ValueError(
                    f"{proposal_id}: incorrect or over-cap {side.upper()} leaf estimate"
                )
        expected_relation = f"{len(row['paths_a'])}:{len(row['paths_b'])}"
        if (
            row["relationship"] != expected_relation
            or min(len(row["paths_a"]), len(row["paths_b"])) != 1
        ):
            raise ValueError(
                f"{proposal_id}: relationship must describe a 1:1, 1:n or n:1 proposal"
            )
        if not isinstance(row["name_evidence"], list) or not row["name_evidence"] or not all(
            isinstance(value, str) and value for value in row["name_evidence"]
        ):
            raise ValueError(f"{proposal_id}: name_evidence must be a nonempty string list")
        if not isinstance(row["uncertainty"], str) or not row["uncertainty"].strip():
            raise ValueError(f"{proposal_id}: uncertainty must be nonempty")
    if quiet > 10:
        raise ValueError("at most 10 quiet controls may be proposed")
    print(f"Validated {len(proposals)} proposals ({quiet} proposed controls)")
    return proposals


def run(args: argparse.Namespace) -> None:
    directory = args.directory.resolve()
    proposals = validate(directory)
    _, config, _ = load_trial(directory)
    results = directory / "results"
    results.mkdir(exist_ok=True)
    summary = []
    for row in sorted(proposals, key=lambda value: value["priority"]):
        target = results / f"{row['id']}.json"
        command = [
            sys.executable,
            "-c",
            "from netlist_comparison.cli import main; raise SystemExit(main())",
            config["input_a"],
        ]
        if config["input_b"] is not None:
            command += [
                config["input_b"],
                "--top-a",
                config["top_a"],
                "--top-b",
                config["top_b"],
            ]
        else:
            command += ["--top", config["top_a"]]
        for path in row["paths_a"]:
            command += ["--path-a", path]
        for path in row["paths_b"]:
            command += ["--path-b", path]
        command += [
            "--format",
            "canonical",
            "--black-box-missing",
            "--matching-mode",
            "operator_scoped",
            "--operator-seconds",
            str(args.seconds),
            "--operator-memory-mib",
            str(args.memory_mib),
            "--output",
            str(target),
            "--json",
        ]
        completed = subprocess.run(command, text=True, capture_output=True)
        item = {
            "id": row["id"],
            "priority": row["priority"],
            "purpose": row["purpose"],
            "relationship": row["relationship"],
            "returncode": completed.returncode,
        }
        if completed.returncode == 0:
            report = json.loads(target.read_text(encoding="utf-8"))
            extension = report["operator_scoped"]
            item.update(
                status=extension["status"],
                certified_internal=extension["certified_internal"],
                card_count=len(extension["cards"]),
                card_lanes=[card["lane"] for card in extension["cards"]],
                charged_count=extension["charged_count"],
                elapsed_seconds=extension["resources"].get("elapsed_seconds"),
                observed_peak_rss_kib=extension["resources"].get(
                    "observed_peak_rss_kib"
                ),
            )
        else:
            item["error"] = completed.stderr[-2000:]
        summary.append(item)
        print(
            f"{row['id']}: {item.get('status', 'runner_error')} "
            f"({item.get('card_count', 0)} cards)"
        )
    document = {
        "format": SUMMARY_FORMAT,
        "proposal_count": len(summary),
        "results": summary,
        "interpretation": (
            "Luna supplied tentative windows only. Comparator cards are conditional on "
            "those windows; quiet output does not establish equivalence or a correct "
            "relationship."
        ),
    }
    (directory / "trial-summary.json").write_bytes(json_bytes(document))
    print(f"Saved local summary and per-window evidence under {directory}")


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    sub = root.add_subparsers(dest="command", required=True)
    make = sub.add_parser("prepare", help="create a hierarchy-only Luna handoff")
    make.add_argument("--input-a", type=Path, required=True)
    make.add_argument(
        "--input-b", type=Path, help="omit for two instances in one canonical file"
    )
    make.add_argument("--top-a", required=True)
    make.add_argument("--top-b", help="defaults to --top-a")
    make.add_argument(
        "--root-a", help="complete A instance path; omit for the selected A top"
    )
    make.add_argument(
        "--root-b", help="complete B instance path; omit for the selected B top"
    )
    make.add_argument("--output", type=Path, required=True)
    make.add_argument("--leaf-cap", type=int, default=64)
    make.add_argument("--max-objects", type=int, default=20_000)
    make.add_argument("--replace", action="store_true")
    check = sub.add_parser("validate", help="validate Luna proposals without reading topology")
    check.add_argument("directory", type=Path)
    execute = sub.add_parser(
        "run", help="run operator-scoped comparisons for validated proposals"
    )
    execute.add_argument("directory", type=Path)
    execute.add_argument("--seconds", type=float, default=180)
    execute.add_argument("--memory-mib", type=int, default=3072)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "prepare":
            if args.leaf_cap < 1 or args.max_objects < 1:
                raise ValueError("caps must be positive")
            if args.input_b is None and not (args.root_a and args.root_b):
                raise ValueError("one input requires both --root-a and --root-b")
            prepare(args)
        elif args.command == "validate":
            validate(args.directory.resolve())
        else:
            if args.seconds <= 0 or args.memory_mib < 64:
                raise ValueError(
                    "run resources must be positive; memory must be at least 64 MiB"
                )
            run(args)
    except (
        ValueError,
        OSError,
        KeyError,
        TypeError,
        AttributeError,
        json.JSONDecodeError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
