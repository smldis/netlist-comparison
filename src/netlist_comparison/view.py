"""Read-only projections of saved comparison evidence.

The full report is the authority. A view is deliberately not a comparison report.
"""
from __future__ import annotations

from collections import Counter
from hashlib import sha256
import json
import re
from urllib.parse import unquote


# Canonical stores these exact reference/raw-evidence fields beside numeric and
# expression parameters. Suppression must not mistake them for sizing changes.
_REFERENCE_FIELDS = frozenset({'model', 'source_type', 'control', 'inductor1',
                               'inductor2', 'raw', 'unresolved_nets'})


def _parameter_detail(field):
    prefix, dot, name = field.casefold().partition('.')
    return prefix == 'parameters' and bool(dot) and name not in _REFERENCE_FIELDS


def _segments(path):
    if not isinstance(path, str) or not path or re.search(r"%(?![0-9a-fA-F]{2})", path):
        raise ValueError(f"invalid percent-escaped hierarchy path: {path!r}")
    try:
        parts = tuple(unquote(part, errors="strict").casefold() for part in path.split("/"))
    except UnicodeError as exc:
        raise ValueError(f"invalid UTF-8 hierarchy path: {path!r}") from exc
    if any(not part for part in parts):
        raise ValueError(f"invalid hierarchy path: {path!r}")
    return parts


def _under(path, roots):
    parts = _segments(path)
    return any(parts[:len(root)] == root for root in roots)


def _validate(report):
    if not isinstance(report, dict) or report.get("kind") == "netlist_comparison_derived_view":
        raise ValueError("expected a full comparison report, not a derived view")
    if report.get("schema_version") != 1:
        raise ValueError("unsupported comparison report schema_version; expected 1")
    for key in ("input_identity", "scope", "options", "a", "b", "pair_options", "representative_pair_ids", "connectivity", "hierarchy", "groups"):
        if key not in report:
            raise ValueError(f"invalid comparison report: missing {key}")
    for key in ("input_identity", "scope", "options", "hierarchy"):
        if not isinstance(report[key], dict):
            raise ValueError(f"invalid comparison report: {key} must be an object")
    if not isinstance(report["groups"], list):
        raise ValueError("invalid comparison report: groups must be an array")
    for key in ("a", "b"):
        side = report[key]
        if not isinstance(side, dict):
            raise ValueError(f"invalid comparison report: {key} must be an object")
        for field in ("objects", "occurrences", "disposition", "diagnostics", "unresolved"):
            if not isinstance(side.get(field), list):
                raise ValueError(f"invalid comparison report: {key}.{field} must be an array")
        if not side["occurrences"]:
            raise ValueError(f"invalid comparison report: {key}.occurrences needs the selected root")
        if not isinstance(side.get("coverage"), dict) or not isinstance(side.get("expansion_complete"), bool):
            raise ValueError(f"invalid comparison report: {key} needs coverage and expansion status")
        for field, required in (("objects", ("id",)), ("occurrences", ("path", "depth")),
                                ("disposition", ("object", "status"))):
            for row in side[field]:
                if not isinstance(row, dict) or any(name not in row for name in required):
                    raise ValueError(f"invalid comparison report: malformed {key}.{field} row")
                if any(not isinstance(row[name], str) for name in required if name != "depth") or (field == "occurrences" and type(row["depth"]) is not int):
                    raise ValueError(f"invalid comparison report: malformed {key}.{field} row fields")
    if not isinstance(report["pair_options"], list) or not isinstance(report["representative_pair_ids"], list):
        raise ValueError("invalid comparison report: malformed pair lists")
    if any(not isinstance(p, dict) or not all(isinstance(p.get(k), str) for k in ("id", "a", "b")) or
           not isinstance(p.get("raw_differences"), list) or
           any(not isinstance(d, dict) or not isinstance(d.get("field"), str) for d in p["raw_differences"])
           for p in report["pair_options"]):
        raise ValueError("invalid comparison report: malformed pair_options row")
    ids = {p["id"] for p in report["pair_options"]}
    if len(ids) != len(report["pair_options"]):
        raise ValueError("invalid comparison report: duplicate pair ID")
    if any(not isinstance(identifier, str) or identifier not in ids for identifier in report["representative_pair_ids"]):
        raise ValueError("invalid comparison report: representative pair ID missing from pair_options")
    representative_ids = set(report["representative_pair_ids"])
    if not isinstance(report["connectivity"], dict) or not isinstance(report["connectivity"].get("overlap"), list):
        raise ValueError("invalid comparison report: malformed connectivity")
    for row in report["connectivity"]["overlap"]:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) for k in ("a", "b")) or any(
            not isinstance(row.get(k), bool) for k in ("a_partitioned_across_b", "b_collects_multiple_a")) or not isinstance(row.get("endpoint_tokens"), list):
            raise ValueError("invalid comparison report: malformed connectivity overlap row")
        if any(not isinstance(token, str) or ":" not in token or token.split(":", 1)[0] not in representative_ids or
               not token.split(":", 1)[1] for token in row["endpoint_tokens"]):
            raise ValueError("invalid comparison report: connectivity endpoint token has unknown representative pair ID or role")


def _group_resolver(report, side, depth):
    """Index occurrences once; each leaf needs only a bounded ancestor walk."""
    occurrences = report[side]["occurrences"]
    root = occurrences[0]["path"]
    root_length = len(_segments(root))
    paths = {_segments(o["path"]): o["path"] for o in occurrences}

    def ancestor(leaf):
        parts = _segments(leaf)
        for length in range(min(len(parts), root_length + depth), root_length - 1, -1):
            if parts[:length] in paths:
                return paths[parts[:length]]
        return root

    return ancestor


def project_saved_report(report, *, source_path=None, source_sha256=None,
                         under_a=(), under_b=(), categories=("raw", "wiring", "unpaired"),
                         parameter=None, group_depth=None, omit_parameters=False):
    """Project a full JSON-compatible report without mutating or rematching it.

    A canonical report-content hash is always recorded. ``source_sha256`` is
    the optional digest of exact saved artifact bytes supplied by the caller.
    """
    _validate(report)
    if type(omit_parameters) is not bool:
        raise ValueError("omit_parameters must be a boolean")
    if omit_parameters and parameter is not None:
        raise ValueError("omit_parameters cannot be combined with a parameter selector")
    content_sha256 = sha256(json.dumps(report, sort_keys=True, separators=(",", ":"),
                                      ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    if not isinstance(categories, (tuple, list)) or not isinstance(under_a, (tuple, list)) or not isinstance(under_b, (tuple, list)):
        raise ValueError("categories and hierarchy selectors must be lists or tuples")
    categories = tuple(categories)
    if (not categories or any(not isinstance(c, str) for c in categories)
            or len(set(categories)) != len(categories) or set(categories) - {"raw", "wiring", "unpaired"}):
        raise ValueError("categories must be distinct choices from raw, wiring, unpaired")
    if parameter is not None and (not isinstance(parameter, str) or not parameter or "raw" not in categories):
        raise ValueError("--parameter requires the raw category and a parameter name")
    if group_depth is not None and (type(group_depth) is not int or group_depth < 0):
        raise ValueError("group_depth must be a nonnegative integer")
    roots = {"a": tuple(_segments(p) for p in under_a), "b": tuple(_segments(p) for p in under_b)}
    for side in ("a", "b"):
        available = [row["id"] for row in report[side]["objects"]] + [row["path"] for row in report[side]["occurrences"]]
        known = {_segments(p) for p in available}
        for supplied, root in zip(under_a if side == "a" else under_b, roots[side]):
            if root not in known:
                raise ValueError(f"unknown {side.upper()} hierarchy path {supplied!r}; use a path from the saved {side} catalog")
    rep_ids = set(report["representative_pair_ids"])
    pairs = [p for p in report["pair_options"] if p["id"] in rep_ids]
    path_filter = bool(roots["a"] or roots["b"])
    def selected(a=None, b=None):
        if not path_filter:
            return True
        return bool((a and _under(a, roots["a"])) or (b and _under(b, roots["b"])))

    scoped_pairs = [p for p in pairs if selected(p["a"], p["b"])]
    scoped_ids = {p["id"] for p in scoped_pairs}
    field = "parameters." + parameter.casefold() if parameter else None
    def raw_differences(pair):
        differences = pair["raw_differences"]
        if omit_parameters:
            differences = [d for d in differences if not _parameter_detail(d['field'])]
        return [d for d in differences if d["field"].casefold() == field] if field else differences
    all_raw = [p for p in pairs if p["raw_differences"]]
    raw = [{**p, "raw_differences": raw_differences(p)} for p in scoped_pairs if raw_differences(p)] if "raw" in categories else []
    # A partition row is indivisible: all its endpoint tokens survive a scope hit.
    # Rows may overlap and are never counted as independent wiring edits.
    all_wiring = [r for r in report["connectivity"]["overlap"] if r["a_partitioned_across_b"] or r["b_collects_multiple_a"]]
    wiring = [r for r in all_wiring if not path_filter or any(t.split(":", 1)[0] in scoped_ids for t in r["endpoint_tokens"])] if "wiring" in categories else []
    witness_context = report.get('representative_selection', {}).get('components', {}).get('representative_wiring_witness', {})
    all_witnesses = witness_context.get('endpoint_disagreements', [])
    witnesses = [r for r in all_witnesses if selected(r['a'], r['b'])] if 'wiring' in categories else []
    all_unpaired = {side: [r for r in report[side]["disposition"] if r["status"] in ("unpaired", "unresolved", "opaque")]
                    for side in ("a", "b")}
    unpaired = {side: [r for r in rows if not path_filter or _under(r["object"], roots[side])]
                if "unpaired" in categories else [] for side, rows in all_unpaired.items()}

    groups = []
    if group_depth is not None:
        counts = Counter()
        ancestor = {side: _group_resolver(report, side, group_depth) for side in ("a", "b")}
        keys_by_id = {}
        for p in scoped_pairs:
            key = (ancestor["a"](p["a"]), ancestor["b"](p["b"]))
            keys_by_id[p["id"]] = key
            counts[key, "representative_pairs"] += 1
        for p in raw:
            counts[keys_by_id[p["id"]], "raw_changed_pairs"] += 1
        for row in wiring:
            touched = {keys_by_id[token.split(":", 1)[0]] for token in row["endpoint_tokens"]
                       if token.split(":", 1)[0] in keys_by_id}
            for key in touched:
                counts[key, "wiring_partition_rows_touching"] += 1
        for row in witnesses:
            key = (ancestor['a'](row['a']), ancestor['b'](row['b']))
            counts[key, 'endpoint_witnesses'] += 1
        for side in ("a", "b"):
            for row in unpaired[side]:
                path = ancestor[side](row["object"])
                key = (path, None) if side == "a" else (None, path)
                counts[key, "unpaired_" + side] += 1
        keys = sorted({key for key, _ in counts}, key=lambda key: (str(key[0]), str(key[1])))
        groups = [{"a": a, "b": b, **{name: counts[(a, b), name] for name in
                   ("representative_pairs", "raw_changed_pairs", "wiring_partition_rows_touching", "endpoint_witnesses", "unpaired_a", "unpaired_b")}}
                  for a, b in keys]
    totals = {"raw": len(all_raw), "wiring": len(all_wiring),
              "unpaired": sum(map(len, all_unpaired.values()))}
    shown = {"raw": len(raw), "wiring": len(wiring), "unpaired": sum(map(len, unpaired.values()))}
    raw_fields_total = sum(len(p["raw_differences"]) for p in pairs)
    raw_fields_shown = sum(len(p["raw_differences"]) for p in raw)
    # These structures carry coupling, alternatives, parameter context, and scope.
    # Keeping them whole is intentional even when a finding selector is narrow.
    context_keys = ("groups", "inspection_regions", "partial_alignment", "reference_proposals",
                    "candidate_basis", "representative_selection", "boundary", "population_evidence")
    context = {key: report[key] for key in context_keys if key in report}
    context["pair_options"] = report["pair_options"]
    context["representative_pair_ids"] = report["representative_pair_ids"]
    context["hierarchy"] = report["hierarchy"]
    context["connectivity_unpaired_endpoints"] = {
        side: report["connectivity"].get("unpaired_endpoints_" + side, []) for side in ("a", "b")}
    view = {
        "kind": "netlist_comparison_derived_view", "view_schema_version": 1,
        "source": {"path": str(source_path) if source_path is not None else None,
                   "artifact_sha256": source_sha256, "report_content_sha256": content_sha256,
                   "input_identity": report["input_identity"],
                   "report_schema_version": report["schema_version"]},
        "filters": {"under_a": list(under_a), "under_b": list(under_b),
                    "categories": list(categories), "parameter": parameter, "group_depth": group_depth,
                    "omit_parameters": omit_parameters},
        "counts": {"representative_pairs_total": len(pairs), "representative_pairs_in_path_scope": len(scoped_pairs),
                   "by_category": {key: {"total": totals[key], "shown": shown[key], "hidden": totals[key] - shown[key]}
                                   for key in ("raw", "wiring", "unpaired")},
                   "population_groups": {"total": len(report.get("population_evidence", {}).get("groups", [])),
                                         "shown": len(report.get("population_evidence", {}).get("groups", [])) if "unpaired" in categories else 0,
                                         "hidden": 0 if "unpaired" in categories else len(report.get("population_evidence", {}).get("groups", [])),
                                         "scope": "Unfiltered whole comparison scope; separate from per-object unpaired rows."},
                   "raw_fields": {"total": raw_fields_total, "shown": raw_fields_shown,
                                  "hidden": raw_fields_total - raw_fields_shown},
                   "parameter_fields_suppressed_in_path_scope": sum(
                       _parameter_detail(d['field']) for p in scoped_pairs for d in p['raw_differences']) if omit_parameters and 'raw' in categories else 0,
                   "endpoint_witnesses": {"total": len(all_witnesses), "shown": len(witnesses),
                                          "hidden": len(all_witnesses) - len(witnesses)}},
        "findings": {"raw_pairs": raw, "wiring_partition_rows": wiring, "unpaired_objects": unpaired,
                     "endpoint_witnesses": witnesses,
                     "population_groups": report.get("population_evidence", {}).get("groups", []) if "unpaired" in categories else [],
                     "omission_search": report.get("partial_alignment", {}).get("omission_search") if "unpaired" in categories else None,
                     "swap_search": report.get("partial_alignment", {}).get("swap_search") if "wiring" in categories else None},
        "hierarchy_groups": groups,
        "source_scope": {"scope": report["scope"], "options": report["options"], "metrics": report.get("metrics"),
                         "sides": {side: {key: value for key, value in report[side].items()
                                          if key in ("expansion_complete", "expanded_leaf_count", "max_depth", "diagnostics",
                                                     "unresolved", "coverage", "black_box_leaf_count", "selection")}
                                   for side in ("a", "b")},
                         "opaque_objects": {side: [o for o in report[side]["objects"] if o.get("opaque_reason")]
                                            for side in ("a", "b")},
                         "black_box_objects": {side: [o for o in report[side]["objects"] if o.get("black_box")]
                                               for side in ("a", "b")}},
        "context": context,
        "semantics": ["Derived inspection view; never use as a full comparison report or infer equivalence from empty findings.",
                      "Pairs are tentative representatives; coupled alternatives and component factors remain in context.",
                      "Group depth is relative to each selected comparison root; shallow branches use their closest available ancestor. Group wiring rows can touch multiple groups and are not additive edit counts.",
                      "Wiring rows are overlapping endpoint-partition evidence, not independent rewiring events; raw net labels alone are not wiring evidence.",
                      "Raw finding counts cover leaf pair fields only. Definition defaults and call overrides remain unfiltered in context.hierarchy; expressions are unevaluated.",
                      "Parameter suppression removes leaf parameter detail only; type and exact canonical model/source_type/control/inductor1/inductor2/raw/unresolved_nets fields survive. Unknown non-parameter fields survive. This is not functional classification.",
                      "Endpoint witnesses are copied from one conditional leaf/net map; ties are not enumerated. Witnesses and partition rows are overlapping evidence, not additive edit counts.",
                      "Population and omission-search findings (unpaired category), and paired-swap search findings (wiring category), retain whole comparison scope even with subtree filters.",
                      "Unpaired and opaque objects are not proven additions or deletions. Filtering cannot recover unexplored correspondence."],
    }
    # JSON round-trip also guarantees detached, plain dict/list/scalar data.
    return json.loads(json.dumps(view, allow_nan=False))


def artifact_sha256(data: bytes) -> str:
    """Digest exact saved artifact bytes, including compression when present."""
    return sha256(data).hexdigest()
