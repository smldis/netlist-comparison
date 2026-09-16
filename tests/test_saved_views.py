import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from spice_canonical.canonical_netlist import from_file, from_text
from netlist_comparison import Options, compare, compare_instances, project_saved_report
from netlist_comparison.cli import main


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def report():
    return compare(from_file(EXAMPLES / "before.sp"), from_file(EXAMPLES / "after.sp"),
                   top_a="TOP", top_b="TOP")


def test_moved_counterpart_and_immutable_source(report):
    original = copy.deepcopy(report)
    view = project_saved_report(report, under_a=["top/xold"], under_b=["top/xmoved/xcore/xnew"])
    assert any(p["a"] == "TOP/XOLD/XCH/M1" and p["b"] == "TOP/XMOVED/XCORE/XNEW/M8"
               for p in view["findings"]["raw_pairs"])
    assert view["counts"]["representative_pairs_in_path_scope"] >= 1
    assert report == original
    assert view["source"]["report_content_sha256"] == hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                   allow_nan=False).encode()).hexdigest()
    view["context"]["pair_options"][0]["a"] = "changed-in-view"
    view["source_scope"]["sides"]["a"]["coverage"]["unresolved"] = -1
    assert report == original
    assert view["kind"] == "netlist_comparison_derived_view"
    with pytest.raises(ValueError, match="full comparison"):
        project_saved_report(view)


def test_raw_only_parameter_and_context(report):
    view = project_saved_report(report, categories=["raw"], parameter="w")
    assert view["counts"]["by_category"]["wiring"]["shown"] == 0
    assert all(d["field"] == "parameters.W" for p in view["findings"]["raw_pairs"]
               for d in p["raw_differences"])
    assert view["context"]["hierarchy"] == report["hierarchy"]
    assert view["counts"]["raw_fields"]["hidden"] >= view["counts"]["by_category"]["raw"]["hidden"]
    assert view["source_scope"]["scope"] == json.loads(json.dumps(report["scope"]))
    assert view["source_scope"]["sides"]["a"]["coverage"] == report["a"]["coverage"]
    with pytest.raises(ValueError, match="requires the raw"):
        project_saved_report(report, categories=["wiring"], parameter="W")


def test_wiring_row_keeps_all_endpoints_across_scope(report):
    changed = copy.deepcopy(report)
    row = changed["connectivity"]["overlap"][0]
    row["a_partitioned_across_b"] = True
    row["endpoint_tokens"] = [changed["representative_pair_ids"][0] + ":bus:0",
                              changed["representative_pair_ids"][-1] + ":n"]
    first = next(p for p in changed["pair_options"] if p["id"] == changed["representative_pair_ids"][0])
    view = project_saved_report(changed, under_a=[first["a"]], categories=["wiring"])
    assert row in view["findings"]["wiring_partition_rows"]
    assert len(view["findings"]["wiring_partition_rows"][0]["endpoint_tokens"]) == 2
    assert view["hierarchy_groups"] == []


def test_grouping_preserves_deeper_pairs_and_coupling(report):
    report["partial_alignment"] = {"component_permutation_factors": [{"constraint": "whole_component_permutation"}],
                                   "coverage_tradeoffs": [{"meaning": "separate alternative"}]}
    report["inspection_regions"] = [{"alternatives_complete": False}]
    view = project_saved_report(report, group_depth=1, categories=["raw"])
    assert sum(g["representative_pairs"] for g in view["hierarchy_groups"]) == len(report["representative_pair_ids"])
    assert view["context"]["groups"] == report["groups"]
    assert view["context"]["pair_options"] == report["pair_options"]
    assert view["context"]["partial_alignment"] == report["partial_alignment"]
    assert view["context"]["inspection_regions"] == report["inspection_regions"]
    assert view["context"]["hierarchy"] == report["hierarchy"]
    assert view["counts"]["representative_pairs_in_path_scope"] == len(report["representative_pair_ids"])
    assert sum(g["raw_changed_pairs"] for g in view["hierarchy_groups"]) == len(view["findings"]["raw_pairs"])


def test_group_depth_zero_shallow_branch_and_selected_roots(report):
    root = project_saved_report(report, group_depth=0)
    assert any(g["a"] == "TOP" and g["b"] == "TOP" and
               g["representative_pairs"] == len(report["representative_pair_ids"])
               for g in root["hierarchy_groups"])
    deep = project_saved_report(report, group_depth=3)
    assert any(g["a"] == "TOP/XOLD/XCH" and g["b"] == "TOP/XMOVED/XCORE/XNEW"
               for g in deep["hierarchy_groups"])
    source = from_text(".subckt CELL A B\nR1 A B 1k\n.ends\nX1 a b CELL\nX2 c d CELL")
    selected = compare_instances(source, top="TOP", path_a="TOP/X1", path_b="TOP/X2")
    selected_view = project_saved_report(selected, group_depth=0)
    assert selected_view["hierarchy_groups"]
    assert all(g["a"] in (None, "TOP/X1") and g["b"] in (None, "TOP/X2")
               for g in selected_view["hierarchy_groups"])


def test_black_box_and_opaque_scope_survive_raw_filter():
    source = from_text("X1 a b MISSING W=1u")
    other = from_text("X1 a b MISSING W=2u")
    result = compare(source, other, top_a="TOP", top_b="TOP", options=Options(black_box_missing=True))
    view = project_saved_report(result, categories=["raw"])
    assert view["source_scope"]["scope"]["black_box_assumption"] == result["scope"]["black_box_assumption"]
    assert view["source_scope"]["sides"]["a"]["black_box_leaf_count"] == result["a"]["black_box_leaf_count"]
    assert view["source_scope"]["black_box_objects"]["a"]
    assert view["source_scope"]["sides"]["a"]["unresolved"] == result["a"]["unresolved"]
    opaque = compare(source, other, top_a="TOP", top_b="TOP")
    projected = project_saved_report(opaque, categories=["raw"])
    assert projected["source_scope"]["opaque_objects"]["a"]
    assert projected["source_scope"]["sides"]["a"]["coverage"]["opaque"] == 1


def test_cli_json_text_errors_and_source_alias(tmp_path, report, capsys):
    path = tmp_path / "result.json"
    data = json.dumps(report).encode()
    path.write_bytes(data)
    output = tmp_path / "view.json"
    assert main(["view", str(path), "--category", "raw", "--output", str(output), "--text", "--limit", "1"]) == 0
    assert "Derived saved-result view" in capsys.readouterr().out
    view = json.loads(output.read_text())
    assert view["source"]["artifact_sha256"] == hashlib.sha256(data).hexdigest()
    assert view["source"]["input_identity"] == report["input_identity"]
    assert path.read_bytes() == data
    alias = tmp_path / "alias.json"
    os.link(path, alias)
    with pytest.raises(SystemExit) as exc:
        main(["view", str(path), "--output", str(alias)])
    assert exc.value.code == 2
    assert path.read_bytes() == data
    for args in (["view", str(path), "--under-a", "TOP/NOPE"],
                 ["view", str(path), "--category", "wiring", "--parameter", "W"]):
        with pytest.raises(SystemExit) as exc:
            main(args)
        assert exc.value.code == 2
    assert "unknown A hierarchy path" in capsys.readouterr().err
    bad = tmp_path / "bad.json"
    for content in ("{", '{"schema_version": 1}'):
        bad.write_text(content)
        with pytest.raises(SystemExit) as exc:
            main(["view", str(bad)])
        assert exc.value.code == 2
    malformed = copy.deepcopy(report)
    malformed["scope"] = []
    bad.write_text(json.dumps(malformed))
    with pytest.raises(ValueError, match="scope must be an object"):
        project_saved_report(malformed)
    with pytest.raises(SystemExit) as exc:
        main(["view", str(bad), "--text"])
    assert exc.value.code == 2
    assert "scope must be an object" in capsys.readouterr().err
    malformed = copy.deepcopy(report)
    del malformed["a"]["diagnostics"]
    with pytest.raises(ValueError, match="a.diagnostics must be an array"):
        project_saved_report(malformed)
    malformed = copy.deepcopy(report)
    malformed["connectivity"]["overlap"][0]["endpoint_tokens"] = ["missing:bus:0"]
    with pytest.raises(ValueError, match="unknown representative pair ID"):
        project_saved_report(malformed)


def test_wiring_text_paths_roles_limit_and_group_collapse(tmp_path, report, capsys):
    row = report["connectivity"]["overlap"][0]
    row["a_partitioned_across_b"] = True
    row["endpoint_tokens"] = [report["representative_pair_ids"][0] + ":bus:0",
                              report["representative_pair_ids"][-1] + ":n"]
    path = tmp_path / "result.json"
    path.write_text(json.dumps(report))
    assert main(["view", str(path), "--category", "wiring", "--text", "--limit", "1"]) == 0
    output = capsys.readouterr().out
    first = next(p for p in report["pair_options"] if p["id"] == report["representative_pair_ids"][0])
    assert f'{first["a"]} -> {first["b"]} [bus:0]' in output
    assert "more endpoints" in output
    assert main(["view", str(path), "--category", "wiring", "--group-depth", "0", "--text"]) == 0
    grouped = capsys.readouterr().out
    assert "wiring rows touching=1" in grouped
    assert "[bus:0]" not in grouped


def test_help_and_backward_cli(capsys):
    assert main([]) == 0
    assert "netlist-compare view result.json" in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        main(["view", "--help"])
    assert exc.value.code == 0
    assert "--under-a" in capsys.readouterr().out
    assert main([str(EXAMPLES / "before.sp"), str(EXAMPLES / "after.sp"), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["schema_version"] == 1


def test_grouped_text_omits_context_only_groups(tmp_path, report, capsys):
    path = tmp_path / "result.json"
    path.write_text(json.dumps(report))
    assert main(["view", str(path), "--category", "raw", "--parameter", "NO_SUCH_PARAMETER",
                 "--group-depth", "1", "--text"]) == 0
    text = capsys.readouterr().out
    assert "0 with selected findings" in text
    assert "groups without selected findings omitted from text" in text
    assert "raw changed pairs=" not in text
