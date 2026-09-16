import importlib.util
from pathlib import Path

from netlist_comparison import compare, InputScope


def test_thousands_of_occurrences_keep_depth_edit_and_coverage():
    path = Path(__file__).resolve().parents[1] / "examples" / "evaluate.py"
    spec = importlib.util.spec_from_file_location("comparison_evaluator", path)
    evaluator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluator)
    a, b, ledger = evaluator.stress_fixture()
    report = compare(a, b, top_a="TOP", top_b="TOP_v2",
                     scope_a=InputScope(globals_complete=True), scope_b=InputScope(globals_complete=True))
    summary = evaluator.summarize(report, ledger)
    assert summary["leaves"] == {"a": 2067, "b": 2067}
    assert summary["depth"] == {"a": 4, "b": 5}
    assert summary["edited_occurrence"]["candidate_retained"]
    assert summary["edited_occurrence"]["new_value_profile_members"] == 1
    for side in ("a", "b"):
        assert sum(report[side]["coverage"].values()) == 2067
    # This is bounded resource/representation evidence, not a quality gate.
    assert report["metrics"]["class_pair_scores"] < 2067 ** 2
    assert report["a"]["coverage"]["unresolved"] > 0
