from collections import defaultdict
from dataclasses import asdict
from time import perf_counter

from spice_canonical.canonical_netlist import CanonicalNetlist

from .assignment import solve
from .candidates import components, features, search
from .expand import expand
from .model import InputScope, Options
from .report import catalog, connectivity, hierarchy, identity, pair_record


def compare(a: CanonicalNetlist, b: CanonicalNetlist, *, top_a: str, top_b: str,
            options: Options | None = None, scope_a: InputScope | None = None,
            scope_b: InputScope | None = None, paths_a: tuple[str, ...] = (),
            paths_b: tuple[str, ...] = ()) -> dict:
    """Return JSON-compatible tentative correspondence and conditional facts.

    Explicit tops name either the canonical root or a subcircuit definition.
    Inputs are not modified. Costs, classes and representative solutions are not
    probabilities or verified identities. Legacy modes enforce size admission,
    without a native solver deadline. Experimental operator_scoped runs in an
    isolated POSIX worker with configurable time/RSS watchdogs. Empty paths_a/b
    select their whole tops; path tuples explicitly compose supplied regions.
    Caller-side canonical parsing and final stdout/disk serialization are outside
    the API computation deadline. Local witnesses never become global identity.
    """
    options = options or Options()
    scope_a, scope_b = scope_a or InputScope(), scope_b or InputScope()
    if options.matching_mode == 'operator_scoped':
        from .operator_scoped import bounded_compare
        return bounded_compare(a, b, top_a=top_a, top_b=top_b, paths_a=paths_a, paths_b=paths_b,
                               options=options, scope_a=scope_a, scope_b=scope_b)
    if paths_a or paths_b:
        raise ValueError('per-side path tuples require matching_mode operator_scoped')
    start = perf_counter()
    va, vb = expand(a, top_a, scope_a, options), expand(b, top_b, scope_b, options)
    return _compare_views(a, b, va, vb, options, scope_a, scope_b, start, top_a, top_b)


def _compare_views(a, b, va, vb, options, scope_a, scope_b, start, top_a, top_b):
    if options.black_box_missing:
        from .blackbox import reconcile
        reconcile(va, vb)
    expanded = perf_counter()
    fa, fb = features(va), features(vb)
    context_evidence = None
    if options.context_mode == "frozen_neighbors":
        from .context import refine
        fa, evidence_a = refine(va, fa)
        fb, evidence_b = refine(vb, fb)
        context_evidence = {"a": evidence_a, "b": evidence_b}
    featured = perf_counter()
    costs, screening = search(fa, fb, options)
    searched = perf_counter()
    eligible = {(i, j): c for (i, j), c in costs.items()
                if fa[i].supported and fb[j].supported and c < 2 * options.unmatched_cost}
    comps = components(eligible)
    comp_for_a = {i: number for number, (aa, _) in enumerate(comps) for i in aa}
    comp_costs = [{} for _ in comps]
    for edge, cost in eligible.items():
        comp_costs[comp_for_a[edge[0]]][edge] = cost
    groups, pair_options, representatives = [], [], []
    status_a, status_b = {}, {}
    checks_left = options.max_alternative_checks
    base_calls = extra_calls = 0
    for number, ((aa, bb), cc) in enumerate(zip(comps, comp_costs)):
        group_id = f"g{number}"
        left = [i for c in aa for i in fa[c].members]
        right = [j for c in bb for j in fb[c].members]
        group = {"id": group_id, "a_classes": [f"a{i}" for i in aa],
                 "b_classes": [f"b{j}" for j in bb], "relation": None,
                 "constraint": "one_to_one_leaf_pairs", "hypotheses": [],
                 "alternatives_complete": False}
        excluded = []
        domain = {}
        for side, ids, classes in (("a", aa, fa), ("b", bb, fb)):
            domain[side] = []
            for c in ids:
                reasons = []
                if len(classes[c].members) > 1:
                    reasons.append("repeated_feature_class")
                if screening[side][c]["cutoff_tie"]:
                    reasons.append("candidate_cutoff_tie")
                if not screening[side][c]["search_complete"]:
                    reasons.append("screening_budget")
                if reasons:
                    excluded.append({"class": f"{side}{c}", "reasons": reasons})
                else:
                    domain[side].append(c)
        da, db = set(domain["a"]), set(domain["b"])
        solver_costs = {edge: c for edge, c in cc.items() if edge[0] in da and edge[1] in db}
        group["assignment_domain"] = {"a_classes": [f"a{i}" for i in sorted(da)],
                                       "b_classes": [f"b{i}" for i in sorted(db)],
                                       "excluded": excluded,
                                       "meaning": "restricted singleton proposal; other class alternatives remain unresolved"}
        for i in left:
            status_a[i] = ("unresolved", group_id)
        for j in right:
            status_b[j] = ("unresolved", group_id)
        reasons = sorted({r for entry in excluded for r in entry["reasons"]})
        if len(da) + len(db) > options.max_component_nodes or len(solver_costs) > options.max_component_edges:
            reasons.append("assignment_size_budget")
            solver_costs = {}
        if not solver_costs:
            group.update(status="unresolved", reasons=reasons or ["no_singleton_edges"])
            groups.append(group)
            continue
        selected, objective = solve(sorted(da), sorted(db), solver_costs, options.unmatched_cost)
        base_calls += 1
        hypotheses = [selected]
        sensitivity_checked = 0
        for edge in selected:
            if checks_left == 0:
                break
            alternative, alternative_cost = solve(sorted(da), sorted(db), solver_costs, options.unmatched_cost, forbidden=edge)
            checks_left -= 1
            extra_calls += 1
            sensitivity_checked += 1
            if alternative_cost <= objective + options.ambiguity_tolerance and alternative not in hypotheses:
                hypotheses.append(alternative)
        pair_ids = {}
        for candidate in sorted({edge for h in hypotheses for edge in h}):
            i, j = candidate
            record = pair_record(va.leaves[fa[i].members[0]], vb.leaves[fb[j].members[0]],
                                 f"p{len(pair_options)}", group_id, cc[candidate])
            record["status"] = "representative" if candidate in selected else "alternative"
            # Status describes presentation choice, never certainty.
            record["correspondence"] = "tentative"
            type_equal = fa[i].type == fb[j].type
            record["evidence"] = {"structure_cost": cc[candidate] - (0 if type_equal else options.type_penalty),
                                  "type_equal": type_equal, "external_neighbors_on_both_sides": all(
                                      any(len({n for n, _ in view.nets[net]}) > 1
                                          for net in view.leaves[cls.members[0]].nets.values())
                                      for view, cls in ((va, fa[i]), (vb, fb[j]))),
                                  "raw_attributes_used_for_scoring": False}
            if fa[i].black_box_key:
                record['evidence']['black_box_interface_assumed'] = True
            if context_evidence is not None:
                base_cost = float(abs(fa[i].vector - fb[j].vector).sum() / 8)
                record["evidence"].update(
                    structure_cost=base_cost,
                    context_cost=cc[candidate] - base_cost - (0 if type_equal else options.type_penalty),
                    context_classes=[f"a{i}", f"b{j}"],
                    context_basis="frozen input signatures; no inferred pair support")
            pair_options.append(record)
            pair_ids[candidate] = record["id"]
            if candidate in selected:
                representatives.append(record)
        for h in hypotheses:
            group["hypotheses"].append([pair_ids[edge] for edge in h])
        ambiguous = len(hypotheses) > 1
        group.update(status="partial" if excluded else ("ambiguous" if ambiguous else "tentative"),
                     reasons=reasons,
                     objective=objective, selected_edge_checks=sensitivity_checked,
                     selected_edges_checked=sensitivity_checked == len(selected),
                     candidate_truncated=any(screening[s][i]["top_k_truncated"]
                                             for s, ids in (("a", aa), ("b", bb)) for i in ids))
        # Even checking every selected edge does not enumerate all near optima.
        for c in da:
            status_a[fa[c].members[0]] = ("ambiguous" if ambiguous else "unpaired", group_id)
        for c in db:
            status_b[fb[c].members[0]] = ("ambiguous" if ambiguous else "unpaired", group_id)
        for i, j in selected:
            state = "ambiguous" if ambiguous else "tentative"
            status_a[fa[i].members[0]] = (state, group_id)
            status_b[fb[j].members[0]] = (state, group_id)
        groups.append(group)
    solved = perf_counter()

    def side_catalog(view, classes, status, side):
        result = catalog(view)
        result["classes"] = []
        for i, c in enumerate(classes):
            profiles = defaultdict(list)
            for n in c.members:
                leaf = view.leaves[n]
                key = (leaf.device.type, tuple((p.name, p.value) for p in leaf.device.parameters))
                profiles[key].append(leaf.path)
            result["classes"].append({"id": f"{side}{i}", "members": [view.leaves[n].path for n in c.members],
                                      "structural_support": c.supported, **screening[side][i],
                                      "context": [{"role": r, "external_endpoints": n, "bag": tag, "weight": w}
                                                  for r, n, tag, w in c.context],
                                      "raw_profiles": [{"type": t, "parameters": [{"name": n, "value": v} for n, v in ps],
                                                        "members": members, "count": len(members)}
                                                       for (t, ps), members in sorted(profiles.items())]})
        class_for_leaf = {n: i for i, c in enumerate(classes) for n in c.members}
        accounting = {"tentative": 0, "ambiguous": 0, "unresolved": 0, "unpaired": 0, "opaque": 0}
        result["disposition"] = []
        for i, leaf in enumerate(view.leaves):
            cls = class_for_leaf[i]
            if leaf.opaque:
                state, group, reason = "opaque", None, leaf.opaque
            elif i in status:
                state, group = status[i]
                reason = "see_group" if state != "unpaired" else "not_selected_by_optional_assignment"
            else:
                state, group = "unpaired", None
                reason = ("screening_budget" if not screening[side][cls]["search_complete"]
                          else "no_supported_candidate_below_unmatched_cost")
                if reason == "screening_budget":
                    state = "unresolved"
            accounting[state] += 1
            result["disposition"].append({"object": leaf.path, "status": state, "group": group, "reason": reason})
        result["coverage"] = accounting
        return result

    result = {
        "schema_version": 1,
        "algorithm": ("frozen_neighbors_optional_assignment_experiment" if context_evidence is not None
                      else "fixed_features_optional_assignment_v1"),
        "scope": {"comparison": "represented_structure", "top_a": top_a, "top_b": top_b,
                  "a": asdict(scope_a), "b": asdict(scope_b),
                  "net_scoping": "formal bindings, explicit globals and ground; other nets local",
                  "unavailable": ["model_bodies", "global_parameter_semantics", "source_map",
                                  "unretained_directives", "nonterminal_reference_resolution"],
                  "unevaluated": ["parameter_expressions", "effective_defaults_and_overrides"],
                  "global_net_declarations_complete": scope_a.globals_complete and scope_b.globals_complete},
        "input_identity": {"kind": "retained_canonical_data_sha256",
                           "a": identity(a), "b": identity(b)},
        "options": asdict(options),
        "a": side_catalog(va, fa, status_a, "a"), "b": side_catalog(vb, fb, status_b, "b"),
        "candidate_edges": [{"a_class": f"a{i}", "b_class": f"b{j}", "cost": c,
                             "eligible": (i, j) in eligible} for (i, j), c in sorted(costs.items())],
        "groups": groups, "pair_options": pair_options,
        "representative_pair_ids": [p["id"] for p in representatives],
        "connectivity": connectivity(va, vb, representatives),
        "hierarchy": hierarchy(va, vb, representatives),
        "metrics": {"class_pair_scores": screening["pair_scores"],
                    "possible_class_pairs": screening["possible_class_pairs"],
                    "screening_complete": screening["screening_complete"],
                    "retained_class_edges": len(costs), "assignment_calls": base_calls,
                    "alternative_calls": extra_calls,
                    "seconds": {"expand": expanded - start, "features": featured - expanded,
                                "search": searched - featured, "assignment": solved - searched}},
    }
    if options.black_box_missing:
        result['scope']['black_box_assumption'] = (
            'Missing cells with the same case-insensitive reference and compatible terminals '
            'have unchanged hidden implementations and stable pin order/names. '
            'Only connections and raw instance overrides are compared; internals are unavailable.')
    if context_evidence is not None:
        result["context_evidence"] = context_evidence
    result["metrics"]["seconds"]["report"] = perf_counter() - solved
    if options.matching_mode == "anchor_growth":
        from .relational import apply_growth_report
        return apply_growth_report(result, va, vb, options)
    if options.matching_mode in ("partial_qap", "regional"):
        from .partial import apply_partial_report
        return apply_partial_report(result, va, vb, options)
    return result


def compare_instances(netlist: CanonicalNetlist, *, top: str, path_a: str,
                      path_b: str, options: Options | None = None,
                      scope: InputScope | None = None) -> dict:
    """Compare actual block calls in one full input, with separate boundary facts."""
    from .boundary import boundary_report
    if not isinstance(path_a, str) or not isinstance(path_b, str):
        raise ValueError("instance paths must be percent-escaped strings")
    options, scope = options or Options(), scope or InputScope()
    if options.matching_mode == 'operator_scoped':
        from .operator_scoped import bounded_compare
        return bounded_compare(netlist, netlist, top_a=top, top_b=top, paths_a=(path_a,), paths_b=(path_b,),
                               options=options, scope_a=scope, scope_b=scope, same_full_netlist=True)
    start = perf_counter()
    va = expand(netlist, top, scope, options, path=path_a)
    vb = expand(netlist, top, scope, options, path=path_b)
    result = _compare_views(netlist, netlist, va, vb, options, scope, scope, start, top, top)
    result["boundary"] = boundary_report(va, vb, result)
    result["scope"].update(selection="subcircuit_occurrences", top=top,
                           internal_nets="distinct formal ports; outer aliases excluded",
                           same_full_netlist=True)
    for side, view in (("a", va), ("b", vb)):
        result[side]["selection"] = view.selection
        mapping = view.selection["physical_net_map"]
        for occurrence in result[side]["occurrences"]:
            occurrence["internal_bindings"] = occurrence["bindings"]
            occurrence["bindings"] = {r: mapping.get(n, n) for r, n in occurrence["internal_bindings"].items()}
        for obj in result[side]["objects"]:
            obj["internal_nets"] = obj["resolved_nets"]
            obj["resolved_nets"] = {r: mapping.get(n, n) for r, n in obj["internal_nets"].items()}
    for pair in result["pair_options"]:
        for terminal in pair["terminals"]:
            for side, view in (("a", va), ("b", vb)):
                net = terminal["net_" + side]
                terminal["physical_net_" + side] = view.selection["physical_net_map"].get(net, net)
    return result
