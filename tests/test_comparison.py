import itertools
import json
from dataclasses import replace
from pathlib import Path

import pytest

from spice_canonical.canonical_netlist import from_file, from_text
from netlist_comparison import InputScope, Options, compare
from netlist_comparison.assignment import solve
from netlist_comparison.cli import main
from netlist_comparison.expand import expand


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def run(a, b, **kwargs):
    return compare(from_text(a), from_text(b), top_a="TOP", top_b="TOP", **kwargs)


def example_pair():
    return from_file(EXAMPLES / "before.sp"), from_file(EXAMPLES / "after.sp")


def test_move_edit_and_definition_default_are_conditional():
    a, b = example_pair()
    result = compare(a, b, top_a="TOP", top_b="TOP")
    assert len(result["representative_pair_ids"]) == 4
    pairs = {p["a"]: p for p in result["pair_options"] if p["status"] == "representative"}
    edited = pairs["TOP/XOLD/XCH/M1"]
    assert edited["b"] == "TOP/XMOVED/XCORE/XNEW/M8"
    assert {"field": "parameters.W", "a": ["W"], "b": ["6u"]} in edited["raw_differences"]
    assert all(row["relation"] is None for row in result["hierarchy"]["memberships"])
    defaults = [r for r in result["hierarchy"]["definition_options"] if (r["a"], r["b"]) == ("CELL", "RENAMED")]
    assert len(defaults) == 1
    assert {"field": "defaults.W", "a": ["2u"], "b": ["5u"]} in defaults[0]["raw_differences"]
    assert result["connectivity"]["conditional_on_pair_ids"] == result["representative_pair_ids"]
    assert all(not r["a_partitioned_across_b"] and not r["b_collects_multiple_a"]
               for r in result["connectivity"]["overlap"])
    json.dumps(result, allow_nan=False)


def test_reorder_is_deterministic_except_timings_and_input_is_untouched():
    a, b = example_pair()
    old_a = a.render()
    shuffled = replace(a, subcircuits=tuple(replace(c, devices=tuple(reversed(c.devices)))
                                            for c in reversed(a.subcircuits)))
    first = compare(a, b, top_a="TOP", top_b="TOP")
    second = compare(shuffled, b, top_a="TOP", top_b="TOP")
    first["metrics"].pop("seconds")
    second["metrics"].pop("seconds")
    assert first == second
    assert a.render() == old_a


def test_repeated_copies_are_compact_and_not_arbitrarily_paired():
    a = "\n".join(f"R{i} a 0 1k" for i in range(1000))
    b = a.replace("R999", "Rchanged").replace("Rchanged a 0 1k", "Rchanged a 0 2k")
    result = run(a, b)
    assert result["metrics"]["class_pair_scores"] == 1
    assert result["pair_options"] == []
    assert len(result["a"]["classes"]) == 1
    assert result["a"]["coverage"]["unresolved"] == 1000
    assert "repeated_feature_class" in result["groups"][0]["reasons"]
    assert any(o["parameters"][0]["value"] == "2k" for o in result["b"]["objects"])


def test_attributes_and_names_do_not_supply_structural_support():
    result = run("R1 a b 1k", "R1 x y 1k")
    assert result["representative_pair_ids"] == []
    assert result["candidate_edges"][0]["eligible"] is False
    assert result["a"]["coverage"]["unpaired"] == 1


def test_body_rewire_is_preserved_and_not_a_net_name_claim():
    a, _ = example_pair()
    text = (EXAMPLES / "before.sp").read_text()
    b = from_text(text.replace("M1 OUT IN T VSS", "M1 OUT IN T IN"))
    result = compare(a, b, top_a="TOP", top_b="TOP")
    pair = next(p for p in result["pair_options"] if p["a"].endswith("/M1") and p["status"] == "representative")
    assert pair["b"].endswith("/M1")
    body = next(t for t in pair["terminals"] if t["role"] == "b")
    assert (body["raw_a"], body["raw_b"]) == ("VSS", "IN")
    assert any(r["a_partitioned_across_b"] or r["b_collects_multiple_a"]
               for r in result["connectivity"]["overlap"])


def test_call_binding_edit_is_visible_when_leaf_raw_formal_is_unchanged():
    text = (EXAMPLES / "before.sp").read_text()
    result = run(text, text.replace("XOLD in out 0 WRAP", "XOLD in out VBB WRAP"))
    pair = next(p for p in result["pair_options"] if p["a"].endswith("/M1") and p["status"] == "representative")
    terminal = next(t for t in pair["terminals"] if t["role"] == "b")
    assert terminal["raw_a"] == terminal["raw_b"] == "VSS"
    assert terminal["raw_binding_differs"] is False
    assert terminal["resolved_identifier_differs"] is True
    assert terminal["net_a"] == "global:0"
    assert terminal["net_b"] == "local:TOP:vbb"


def test_formal_bindings_scope_and_explicit_globals():
    text = ".subckt A IN OUT\nR1 IN local 1k\nC1 local OUT 1p\nR2 VDD OUT 2k\n.ends\nX1 a b A\nX2 c d A"
    data = from_text(text)
    local = expand(data, "TOP", InputScope(), Options())
    x1 = next(l for l in local.leaves if l.path == "TOP/X1/R1")
    x2 = next(l for l in local.leaves if l.path == "TOP/X2/R1")
    assert x1.nets["p"] == "local:TOP:a"
    assert x1.nets["n"] != x2.nets["n"]
    known = expand(data, "TOP", InputScope(("0", "VDD"), True), Options())
    assert all(l.nets["p"] == "global:vdd" for l in known.leaves if l.device.name == "R2")


def test_normalized_subcircuit_type_resolves_original_definition():
    from spice_canonical.canonical_netlist import normalize_device_types
    data = from_text(".subckt CELL A B\nR1 A B 1k\n.ends\nX1 a b CELL")
    data = normalize_device_types(data, {"CELL": "some_normalized_type"})
    view = expand(data, "TOP", InputScope(), Options())
    assert [l.path for l in view.leaves] == ["TOP/X1/R1"]


def test_primitive_type_collision_is_not_expanded_as_a_call():
    data = from_text(".model N NMOS\n.subckt nmos D G S B\nR1 D S 1k\n.ends\nM1 d g 0 0 N")
    view = expand(data, "TOP", InputScope(), Options())
    assert [l.path for l in view.leaves] == ["TOP/M1"]


@pytest.mark.parametrize("text,reason", [
    ("X1 a b MISSING", "unresolved_definition"),
    (".subckt A IN\nXSELF IN A\n.ends\nX1 a A", "recursive_call"),
    ("K1 L1 L2 .9", "unrepresented_connectivity"),
])
def test_opaque_connectivity_is_visible(text, reason):
    result = run(text, text)
    assert result["a"]["coverage"]["opaque"] == 1
    assert result["a"]["unresolved"][0]["reason"] == reason
    assert not result["representative_pair_ids"]


def test_expansion_and_search_budgets_do_not_erase_scope():
    a, b = example_pair()
    result = compare(a, b, top_a="TOP", top_b="TOP", options=Options(max_objects=1))
    assert not result["a"]["expansion_complete"]
    assert result["a"]["unresolved"][0]["hidden_leaf_count"] is None
    result = compare(a, b, top_a="TOP", top_b="TOP", options=Options(max_pair_scores=1))
    assert not result["metrics"]["screening_complete"]
    assert result["a"]["coverage"]["unresolved"] == 4
    assert result["pair_options"] == []


def test_empty_sides_and_coverage_accounting():
    for a, b in (("", ""), ("R1 a b 1k", ""), ("", "R1 a b 1k")):
        result = run(a, b)
        for side in ("a", "b"):
            assert sum(result[side]["coverage"].values()) == len(result[side]["objects"])
        assert result["pair_options"] == []


def test_optional_solver_against_independent_partial_injections():
    costs = {(0, 0): 0, (0, 1): 1, (1, 0): 1, (1, 1): 2}
    pairs, objective = solve([0, 1], [0, 1], costs, 10)
    alternate, alt_cost = solve([0, 1], [0, 1], costs, 10, forbidden=pairs[0])
    assert objective == alt_cost == 2 and alternate != pairs
    for n, m in itertools.product(range(4), repeat=2):
        edges = {(i, j): float((i * 3 + j * 5) % 9) for i in range(n) for j in range(m) if (i + j) % 3}
        _, score = solve(list(range(n)), list(range(m)), edges, 2)
        expected = []
        for image in itertools.product(*[[None] + [j for j in range(m) if (i, j) in edges] for i in range(n)]):
            used = [j for j in image if j is not None]
            if len(used) != len(set(used)):
                continue
            expected.append(sum(edges[i, j] for i, j in enumerate(image) if j is not None) + 2 * (n + m - 2 * len(used)))
        assert score == min(expected)


def test_raw_default_and_override_differences_survive_shared_ambiguity():
    text = ".subckt CELL A B W=1u\nR1 A B W\n.ends\nX1 a 0 CELL W=2u\nX2 a 0 CELL W=3u"
    result = run(text, text.replace("W=1u", "W=4u").replace("W=2u", "W=5u"))
    definition = next(d for d in result["hierarchy"]["definition_options"] if d["a"] == "CELL")
    assert definition["basis"] == "name_only_candidate"
    assert definition["raw_differences"][0]["a"] == ["1u"]
    assert definition["raw_differences"][0]["b"] == ["4u"]
    assert len(definition["occurrences_a"]) == 2
    assert any(o["overrides"] == [{"name": "W", "value": "5u"}] for o in result["b"]["occurrences"])


def test_regroup_across_two_containers_keeps_cross_boundary_connectivity():
    a, _ = example_pair()
    b = from_text(""".model N NMOS
.subckt MOS OUT IN T VSS
M8 OUT IN T VSS N W=W L=1u
M9 T IN VSS VSS N W=3u L=1u
.ends
.subckt LOAD OUT T VSS
R9 OUT VSS 1k
C9 T VSS 1p
.ends
.subckt REGROUP IN OUT VSS W=2u
XCORE OUT IN T VSS MOS
XLOAD OUT T VSS LOAD
.ends
XWHOLE in out 0 REGROUP W=4u
""")
    result = compare(a, b, top_a="TOP", top_b="TOP")
    assert len(result["representative_pair_ids"]) == 4
    memberships = result["hierarchy"]["memberships"]
    for target in ("TOP/XWHOLE/XCORE", "TOP/XWHOLE/XLOAD"):
        assert any(r["a"] == "TOP/XOLD/XCH" and r["b"] == target and r["paired_leaves"] == 2
                   for r in memberships)
    assert not any(r["a_partitioned_across_b"] or r["b_collects_multiple_a"]
                   for r in result["connectivity"]["overlap"])


def test_type_replacement_remains_a_candidate_and_raw_change():
    text = (EXAMPLES / "before.sp").read_text()
    result = run(text, text.replace("C1 T VSS 1p", "RNEW T VSS 7k"))
    pair = next(p for p in result["pair_options"] if p["a"].endswith("/C1") and p["b"].endswith("/RNEW"))
    assert {"field": "type", "a": "capacitor", "b": "resistor"} in pair["raw_differences"]


def test_mixed_removal_keeps_unpaired_accounting_without_claiming_deletion():
    text = (EXAMPLES / "before.sp").read_text()
    result = run(text, text.replace("C1 T VSS 1p\n", ""))
    assert sum(result["a"]["coverage"].values()) == 4
    assert sum(result["b"]["coverage"].values()) == 3
    assert len(result["representative_pair_ids"]) <= 3
    assert result["a"]["coverage"]["unpaired"] + result["a"]["coverage"]["unresolved"] >= 1


def test_joint_alternative_hypotheses_do_not_become_independent_rows(monkeypatch):
    # Inject the review's exact tie into the candidate-cost boundary; test the
    # public ambiguity/report contract independently of feature quality.
    import netlist_comparison.api as api
    def controlled_search(a, b, options):
        assert len(a) == len(b) == 2
        records = [{"examined_classes": 2, "available_classes": 2, "search_complete": True,
                    "top_k_truncated": False, "cutoff_tie": False} for _ in range(2)]
        return {(0, 0): 0., (0, 1): .1, (1, 0): .1, (1, 1): .2}, {
            "a": records, "b": records, "pair_scores": 4, "possible_class_pairs": 4, "screening_complete": True}
    monkeypatch.setattr(api, "search", controlled_search)
    text = "R1 a 0 1k\nC1 a 0 1p"
    result = run(text, text, options=Options(type_penalty=0))
    group = result["groups"][0]
    assert group["status"] == "ambiguous"
    assert len(group["hypotheses"]) == 2
    assert result["a"]["coverage"]["ambiguous"] == 2
    pairs = {p["id"]: p for p in result["pair_options"]}
    for hypothesis in group["hypotheses"]:
        assert len({pairs[p]["a"] for p in hypothesis}) == 2
        assert len({pairs[p]["b"] for p in hypothesis}) == 2


def test_repeated_class_does_not_veto_singleton_proposals():
    text = "R1 a 0 1k\nR2 a 0 1k\nC1 a 0 1p"
    result = run(text, text)
    assert any(p["a"] == p["b"] == "TOP/C1" for p in result["pair_options"])
    assert result["a"]["coverage"]["unresolved"] == 2
    assert result["groups"][0]["assignment_domain"]["excluded"]


def test_assignment_admission_limit_and_alternative_budget_are_reported():
    a, b = example_pair()
    result = compare(a, b, top_a="TOP", top_b="TOP", options=Options(max_component_nodes=1))
    assert all("assignment_size_budget" in g["reasons"] for g in result["groups"])
    assert not result["pair_options"]
    result = compare(a, b, top_a="TOP", top_b="TOP", options=Options(max_alternative_checks=0))
    assert all(not g["selected_edges_checked"] for g in result["groups"])
    assert result["metrics"]["alternative_calls"] == 0


def test_invalid_inputs_and_cli(tmp_path, capsys):
    with pytest.raises(ValueError, match="unknown top"):
        compare(from_text(""), from_text(""), top_a="MISSING", top_b="TOP")
    with pytest.raises(ValueError):
        Options(candidate_top_k=0)
    output = tmp_path / "report.json"
    assert main([str(EXAMPLES / "before.sp"), str(EXAMPLES / "after.sp"), "--top-a", "TOP",
                 "--top-b", "TOP", "--output", str(output)]) == 0
    assert json.loads(output.read_text())["schema_version"] == 1
    with pytest.raises(SystemExit) as exc:
        main([str(EXAMPLES / "before.sp"), str(EXAMPLES / "after.sp"), "--top-a", "NO", "--top-b", "TOP"])
    assert exc.value.code == 2
    assert "unknown top" in capsys.readouterr().err
