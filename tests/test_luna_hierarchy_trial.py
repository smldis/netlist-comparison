"""The public Luna handoff prepares, validates and executes local trials."""

import importlib.util
import json
from pathlib import Path

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


def proposal_document(workflow, trial, rows):
    digest = (trial / "input.sha256").read_text(encoding="utf-8").split()[0]
    return {
        "format": workflow.PROPOSAL_FORMAT,
        "input_sha256": digest,
        "method": {
            "summary": "hierarchy names and counts",
            "used_fields": ["path", "descendant_leaf_count"],
            "excluded_fields": ["topology"],
        },
        "proposals": rows,
    }


def row(proposal_id, paths_a, paths_b, leaves_a, leaves_b, *, purpose="change_candidate"):
    return {
        "id": proposal_id,
        "priority": 1,
        "purpose": purpose,
        "relationship": f"{len(paths_a)}:{len(paths_b)}",
        "paths_a": paths_a,
        "paths_b": paths_b,
        "estimated_leaves_a": leaves_a,
        "estimated_leaves_b": leaves_b,
        "name_evidence": ["bounded hierarchy candidate"],
        "uncertainty": "names do not establish correspondence",
    }


def test_prepare_makes_selected_subtrees_self_contained(tmp_path):
    workflow = load_workflow()
    source = canonical(
        tmp_path / "both.canonical",
        """
.subckt BLOCK a b
R1 a b 1k
.ends BLOCK
Xold left 0 BLOCK
Xnew right 0 BLOCK
""",
    )
    trial = tmp_path / "trial"

    assert workflow.main([
        "prepare", "--input-a", str(source), "--top-a", "TOP",
        "--root-a", "TOP/Xold", "--root-b", "TOP/Xnew",
        "--output", str(trial),
    ]) == 0

    manifest = json.loads((trial / "hierarchy-only-input.json").read_text())
    assert manifest["sides"]["a"]["nodes"][0]["path"] == "TOP/Xold"
    assert manifest["sides"]["a"]["nodes"][0]["parent"] is None
    assert manifest["sides"]["b"]["nodes"][0]["parent"] is None
    task = (trial / "LUNA_TASK.md").read_text(encoding="utf-8")
    assert "fewer than 5, or none" in task
    assert "for any positive n" in task
    assert str(SCRIPT) in task


def test_validation_accepts_general_one_to_many_and_rejects_unsafe_id(tmp_path, capsys):
    workflow = load_workflow()
    before = canonical(
        tmp_path / "before.canonical",
        """
.subckt OLD a b
R1 a n1 1k
R2 n1 n2 1k
R3 n2 b 1k
.ends OLD
Xold in out OLD
""",
    )
    after = canonical(
        tmp_path / "after.canonical",
        """
.subckt PART a b
R1 a b 1k
.ends PART
Xleft in n1 PART
Xmiddle n1 n2 PART
Xright n2 out PART
""",
    )
    trial = tmp_path / "trial"
    assert workflow.main([
        "prepare", "--input-a", str(before), "--input-b", str(after),
        "--top-a", "TOP", "--top-b", "TOP", "--output", str(trial),
    ]) == 0
    proposal = row(
        "P001", ["TOP/Xold"],
        ["TOP/Xleft", "TOP/Xmiddle", "TOP/Xright"], 3, 3,
    )
    document = proposal_document(workflow, trial, [proposal])
    (trial / "proposals.json").write_text(json.dumps(document), encoding="utf-8")

    assert workflow.main(["validate", str(trial)]) == 0
    assert "Validated 1 proposals (0 proposed controls)" in capsys.readouterr().out

    document["proposals"][0]["id"] = "../outside"
    (trial / "proposals.json").write_text(json.dumps(document), encoding="utf-8")
    assert workflow.main(["validate", str(trial)]) == 2
    assert "safe filename components" in capsys.readouterr().err


def test_tiny_validated_proposal_runs_operator_scoped(tmp_path):
    workflow = load_workflow()
    before = canonical(
        tmp_path / "before.canonical",
        """
.subckt CELL a b
R1 a b 1k
.ends CELL
Xold in out CELL
""",
    )
    after = canonical(
        tmp_path / "after.canonical",
        """
.subckt CELL a b
R1 a b 2k
.ends CELL
Xnew in out CELL
""",
    )
    trial = tmp_path / "trial"
    assert workflow.main([
        "prepare", "--input-a", str(before), "--input-b", str(after),
        "--top-a", "TOP", "--top-b", "TOP", "--output", str(trial),
    ]) == 0
    document = proposal_document(
        workflow,
        trial,
        [row("P001", ["TOP/Xold"], ["TOP/Xnew"], 1, 1)],
    )
    (trial / "proposals.json").write_text(json.dumps(document), encoding="utf-8")

    assert workflow.main([
        "run", str(trial), "--seconds", "30", "--memory-mib", "512",
    ]) == 0
    summary = json.loads((trial / "trial-summary.json").read_text())
    assert summary["proposal_count"] == 1
    assert summary["results"][0]["returncode"] == 0
    assert summary["results"][0]["status"] == "certified"
    assert (trial / "results" / "P001.json").is_file()
