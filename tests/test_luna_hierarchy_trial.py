"""The local hierarchy workflow enumerates, validates and batches bounded windows."""

import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess

from spice_canonical.canonical_netlist import from_text


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "examples" / "luna_hierarchy_trial.py"


def load_workflow():
    spec = importlib.util.spec_from_file_location("luna_hierarchy_trial", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def canonical(path, text):
    path.write_text(from_text(text).render(), encoding="utf-8")
    return path


def revisions(tmp_path):
    before = canonical(
        tmp_path / "before.canonical",
        """
.subckt UNIT a b
R1 a b 1k
.ends UNIT
.subckt OLD a b
R1 a n 1k
R2 n b 1k
.ends OLD
.subckt AROOT a b
Xsame a b UNIT
Xold a b OLD
.ends AROOT
""",
    )
    after = canonical(
        tmp_path / "after.canonical",
        """
.subckt UNIT a b
R1 a b 2k
.ends UNIT
.subckt BROOT a b
Xsame a b UNIT
Xnew1 a n UNIT
Xnew2 n b UNIT
.ends BROOT
""",
    )
    return before, after


def prepare(workflow, trial, before, after, *extra):
    return workflow.main([
        "prepare", "--input-a", str(before), "--input-b", str(after),
        "--top-a", "AROOT", "--top-b", "BROOT", "--output", str(trial),
        "--seconds", "30", "--memory-mib", "512", *extra,
    ])


def proposal_document(workflow, trial, rows):
    config = json.loads((trial / "trial-config.json").read_text())
    return {
        "format": workflow.PROPOSAL_FORMAT,
        "input_sha256": config["unmatched_sha256"],
        "method": {
            "summary": "unmatched hierarchy names and counts",
            "used_fields": ["relative_path", "descendant_leaf_count"],
            "excluded_fields": ["edit truth"],
        },
        "proposals": rows,
    }


def proposal(proposal_id="P001", purpose="change_candidate"):
    return {
        "id": proposal_id,
        "priority": 1,
        "purpose": purpose,
        "relationship": "1:2",
        "paths_a": ["AROOT/Xold"],
        "paths_b": ["BROOT/Xnew1", "BROOT/Xnew2"],
        "estimated_leaves_a": 2,
        "estimated_leaves_b": 2,
        "name_evidence": ["one unmatched branch and two unmatched siblings"],
        "uncertainty": "hierarchy labels do not establish correspondence",
    }


def test_prepare_enumerates_relative_paths_and_unmatched_frontiers(tmp_path):
    workflow = load_workflow()
    before, after = revisions(tmp_path)
    trial = tmp_path / "trial"
    assert prepare(
        workflow, trial, before, after,
        "--global-net", "VDD", "--global-net", "VSS",
    ) == 0

    stable = json.loads((trial / "stable-windows.json").read_text())
    assert [row["relative_path"] for row in stable["windows"]] == [".", "Xsame"]
    assert stable["windows"][0]["paths_a"] == []
    assert stable["windows"][0]["paths_b"] == []
    assert stable["windows"][1]["paths_a"] == ["AROOT/Xsame"]
    assert stable["windows"][1]["paths_b"] == ["BROOT/Xsame"]
    assert len({row["id"] for row in stable["windows"]}) == 2

    unmatched = json.loads((trial / "unmatched-branch-input.json").read_text())
    assert unmatched["sides"]["a"]["eligible_paths"] == ["AROOT/Xold"]
    assert unmatched["sides"]["b"]["eligible_paths"] == [
        "BROOT/Xnew1", "BROOT/Xnew2",
    ]
    assert unmatched["sides"]["a"]["frontiers"][0]["shared_parent"]["relative_path"] == "."
    config = json.loads((trial / "trial-config.json").read_text())
    assert config["operator"] == {
        "cards": 12, "counterparts": 16, "leaves": 64, "memory_mib": 512,
        "nets": 96, "presentation_paths": 100, "query_seconds": 5,
        "retained_paths": 200, "seconds": 30, "parameters": True,
    }
    assert config["input_scope"] == {
        "global_nets": ["0", "VDD", "VSS"], "globals_complete": False,
    }
    task = (trial / "LUNA_TASK.md").read_text()
    assert "Do not propose quiet controls" in task
    assert "complete sensitive local inputs" in task
    for path in (
        "sides.a.frontiers", "sides.b.frontiers",
        "sides.a.eligible_paths", "sides.b.eligible_paths",
    ):
        assert f"`{path}`" in task
    assert "every frontier\ncontains a `nodes` array" in task
    assert "A=1 frontiers/1 eligible paths" in task
    assert "B=2 frontiers/2 eligible paths" in task
    assert "confirm both side counts" in task

    empty = proposal_document(workflow, trial, [])
    (trial / "proposals.json").write_text(json.dumps(empty), encoding="utf-8")
    command_block = task.split("```sh\n", 1)[1].split("\n```", 1)[0]
    commands = command_block.splitlines()
    assert len(commands) == 2
    expected_pythonpath = os.pathsep.join(
        str(path) for path in workflow.local_import_roots()
    )
    for command in commands:
        arguments = shlex.split(command)
        assert arguments[:2] == ["/usr/bin/env", f"PYTHONPATH={expected_pythonpath}"]
        completed = subprocess.run(
            arguments, cwd=tmp_path, env={"PATH": "/usr/bin:/bin"},
            text=True, capture_output=True, check=False,
        )
        assert completed.returncode == 0, completed.stderr


def test_one_file_roots_pair_relative_children(tmp_path):
    workflow = load_workflow()
    source = canonical(
        tmp_path / "both.canonical",
        """
.subckt UNIT a b
R1 a b 1k
.ends UNIT
.subckt LEFT a b
Xsame a b UNIT
.ends LEFT
.subckt RIGHT a b
Xsame a b UNIT
.ends RIGHT
Xleft a b LEFT
Xright c d RIGHT
""",
    )
    trial = tmp_path / "trial"
    assert workflow.main([
        "prepare", "--input-a", str(source), "--top-a", "TOP",
        "--root-a", "TOP/Xleft", "--root-b", "TOP/Xright",
        "--output", str(trial), "--seconds", "30", "--memory-mib", "512",
        "--globals-complete", "--omit-parameters",
    ]) == 0
    stable = json.loads((trial / "stable-windows.json").read_text())
    assert [row["relative_path"] for row in stable["windows"]] == [".", "Xsame"]
    assert stable["windows"][0]["paths_a"] == ["TOP/Xleft"]
    assert stable["windows"][0]["paths_b"] == ["TOP/Xright"]
    manifest = json.loads((trial / "hierarchy-only-input.json").read_text())
    assert manifest["sides"]["a"]["nodes"][0]["parent"] is None
    assert manifest["sides"]["b"]["nodes"][0]["parent"] is None
    config = json.loads((trial / "trial-config.json").read_text())
    assert config["input_scope"] == {
        "global_nets": ["0"], "globals_complete": True,
    }
    assert config["operator"]["parameters"] is False

    assert workflow.main(["run", str(trial)]) == 0
    summary = json.loads((trial / "trial-summary.json").read_text())
    assert summary["completed_window_count"] == 2
    for row in summary["results"]:
        report = json.loads((trial / row["result"]).read_text())
        assert report["input_identity"]["a"] == report["input_identity"]["b"]
        assert report["scope"]["a"] == {
            "global_nets": ["0"], "globals_complete": True,
        }
        assert report["scope"]["b"] == report["scope"]["a"]
        assert report["options"]["operator_parameters"] is False


def test_prepare_refuses_collisions_truncation_and_input_mutation(
    tmp_path, capsys, monkeypatch,
):
    workflow = load_workflow()
    before, after = revisions(tmp_path)
    limited = tmp_path / "limited"
    assert prepare(workflow, limited, before, after, "--max-windows", "1") == 2
    assert "no truncation performed" in capsys.readouterr().err
    assert not (limited / "stable-windows.json").exists()

    trial = tmp_path / "trial"
    assert prepare(workflow, trial, before, after) == 0
    manifest = json.loads((trial / "hierarchy-only-input.json").read_text())
    original_stable_id = workflow.stable_id
    monkeypatch.setattr(workflow, "stable_id", lambda _key: "Sduplicate")
    try:
        workflow.build_stable_windows(manifest, "hash", 64, 256)
    except ValueError as error:
        assert str(error) == "stable window ID collision"
    else:
        raise AssertionError("stable ID collision was accepted")
    monkeypatch.setattr(workflow, "stable_id", original_stable_id)

    before.write_text(before.read_text() + "\n", encoding="utf-8")
    assert workflow.main(["run", str(trial)]) == 2
    assert "canonical input changed" in capsys.readouterr().err


def test_validation_accepts_general_unmatched_union_and_rejects_shared_or_quiet(tmp_path, capsys):
    workflow = load_workflow()
    before, after = revisions(tmp_path)
    trial = tmp_path / "trial"
    assert prepare(workflow, trial, before, after) == 0
    empty = proposal_document(workflow, trial, [])
    (trial / "proposals.json").write_text(json.dumps(empty), encoding="utf-8")
    assert workflow.main(["validate", str(trial)]) == 0
    assert "Validated 0 unmatched-branch proposals" in capsys.readouterr().out
    assert workflow.main(["run", str(trial)]) == 0
    empty_summary = json.loads((trial / "trial-summary.json").read_text())
    assert empty_summary["luna_proposals"] == "none_proposed"
    assert empty_summary["completed_window_count"] == 2

    document = proposal_document(workflow, trial, [proposal()])
    (trial / "proposals.json").write_text(json.dumps(document), encoding="utf-8")
    assert workflow.main(["validate", str(trial)]) == 0
    assert "Validated 1 unmatched-branch proposals" in capsys.readouterr().out

    document["proposals"][0] = {
        **proposal(), "paths_a": ["AROOT/Xsame"], "estimated_leaves_a": 1,
    }
    (trial / "proposals.json").write_text(json.dumps(document), encoding="utf-8")
    assert workflow.main(["validate", str(trial)]) == 2
    assert "unmatched eligible" in capsys.readouterr().err

    document["proposals"][0] = proposal(purpose="quiet_control")
    (trial / "proposals.json").write_text(json.dumps(document), encoding="utf-8")
    assert workflow.main(["validate", str(trial)]) == 2
    assert "must be change_candidate" in capsys.readouterr().err

    stable = json.loads((trial / "stable-windows.json").read_text())
    document["proposals"][0] = proposal(proposal_id=stable["windows"][0]["id"])
    (trial / "proposals.json").write_text(json.dumps(document), encoding="utf-8")
    assert workflow.main(["run", str(trial)]) == 2
    assert "window IDs collide" in capsys.readouterr().err


def test_real_batch_saves_complete_hashed_reports_and_refuses_overwrite(tmp_path, capsys):
    workflow = load_workflow()
    before, after = revisions(tmp_path)
    trial = tmp_path / "trial"
    assert prepare(workflow, trial, before, after) == 0
    document = proposal_document(workflow, trial, [proposal()])
    (trial / "proposals.json").write_text(json.dumps(document), encoding="utf-8")

    assert workflow.main(["run", str(trial)]) == 0
    summary = json.loads((trial / "trial-summary.json").read_text())
    receipt = json.loads((trial / "batch-receipt.json").read_text())
    assert summary["status"] == "complete"
    assert summary["requested_window_count"] == summary["completed_window_count"] == 3
    assert [row["source"] for row in summary["results"]] == [
        "deterministic_relative_path", "deterministic_relative_path",
        "luna_unmatched_proposal",
    ]
    assert [row["paths_a"] for row in summary["results"]] == [
        [], ["AROOT/Xsame"], ["AROOT/Xold"],
    ]
    assert [row["paths_b"] for row in summary["results"]] == [
        [], ["BROOT/Xsame"], ["BROOT/Xnew1", "BROOT/Xnew2"],
    ]
    for row in summary["results"]:
        result = trial / row["result"]
        assert result.is_file()
        assert workflow.file_digest(result) == row["result_sha256"]
        report = json.loads(result.read_text())
        assert report["operator_scoped"]["resources"]["batch_window_index"] >= 0
    assert receipt["reuse"]["window_count"] == 3
    assert receipt["resources"]["incomplete"] is False
    assert workflow.main(["run", str(trial)]) == 2
    assert "pass --replace" in capsys.readouterr().err


def test_resource_stop_writes_incomplete_receipt_without_inferred_results(
    tmp_path, monkeypatch,
):
    workflow = load_workflow()
    before, after = revisions(tmp_path)
    trial = tmp_path / "trial"
    assert prepare(workflow, trial, before, after) == 0

    import netlist_comparison

    monkeypatch.setattr(
        netlist_comparison,
        "compare_operator_scoped_batch",
        lambda *args, **kwargs: {
            "schema_version": 1,
            "kind": "operator_scoped_batch_v1",
            "status": "memory_budget_exhausted",
            "results": [],
            "resources": {
                "incomplete": True,
                "stop_reason": "memory_budget_exhausted",
            },
        },
    )
    assert workflow.main(["run", str(trial)]) == 0
    summary = json.loads((trial / "trial-summary.json").read_text())
    receipt = json.loads((trial / "batch-receipt.json").read_text())
    assert summary["status"] == "memory_budget_exhausted"
    assert summary["completed_window_count"] == 0
    assert summary["results"] == []
    assert receipt["resources"]["stop_reason"] == "memory_budget_exhausted"
    assert not list((trial / "results" / "stable").glob("*.json"))
