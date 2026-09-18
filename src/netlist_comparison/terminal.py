"""Bounded deterministic display of existing evidence, without new interpretation."""
import json
import shlex


def rows(lines, items, limit, render):
    for item in items[:limit]:
        lines.append('  ' + render(item))
    if len(items) > limit:
        lines.append(f'  ... {len(items) - limit} more not displayed; increase --limit or save full JSON.')


def inspection(data, view, path, limit):
    lines = [f'Inspecting: {path}', 'Circuits (direct device counts, not expanded totals):']
    rows(lines, [data.top, *data.subcircuits], limit,
         lambda c: f'{c.name}: {len(c.devices)} devices; pins: {", ".join(c.pins) or "(none)"}')
    if view is None:
        lines += ['Choose a circuit to list its actual instance paths:',
                  f'  netlist-compare {shlex.quote(str(path))} --inspect --top CIRCUIT']
    else:
        lines.append('Actual block paths (copy these exactly; special characters are percent-escaped):')
        rows(lines, [o for o in view.occurrences if o['parent'] is not None], limit,
             lambda o: f'{o["path"]}  -> {o["definition"]}')
        if len(view.occurrences) == 1:
            lines.append('  No available descendant block calls were expanded.')
        lines.append(f'Expansion finished within budget: {not view.budget_exhausted}; unresolved regions: {len(view.unresolved)}')
        rows(lines, view.unresolved, limit, lambda u: f'{u["region"]}: {u["reason"]}')
        lines += ['Compare two listed block paths:',
                  f'  netlist-compare {shlex.quote(str(path))} --top {shlex.quote(view.occurrences[0]["definition"])} --path-a PATH --path-b PATH']
    lines.append(f'Input diagnostics: {len(data.diagnostics)}')
    rows(lines, list(data.diagnostics), limit, lambda d: f'{d.source or path}:{d.line}: {d.message}')
    lines.append('Missing model bodies/opaque libraries are not necessarily diagnosed; no electrical equivalence is checked.')
    return '\n'.join(lines) + '\n'


def omission_summary(population, search, limit):
    lines = []
    def domain_label(domain):
        if domain == 'represented_native_primitives':
            return 'Represented native primitives'
        try:
            cell, basis, pins = json.loads(domain)
            return f'{cell} ({basis}, {len(pins)} pins)'
        except (ValueError, TypeError):
            return domain
    if population:
        lines.append('Represented population (whole comparison scope; no exact new-instance identity):')
        rows(lines, population.get('groups', []), limit,
             lambda r: f'{domain_label(r["domain"])}: A/B={r["count_a"]}/{r["count_b"]}; '
                       f'{r["surplus_side"].upper()} represented surplus {r["represented_surplus"]} jointly; '
                       f'selected omissions A/B={r["selected_omissions_a"]}/{r["selected_omissions_b"]}')
        lines.append(f'  Expansion complete: {population.get("expansion_complete")}; '
                     f'opaque excluded A/B={population.get("opaque_excluded_a")}/{population.get("opaque_excluded_b")}.')
    if search:
        lines.append(f'Occupied omission search: {search["stop"]}; scores {search["work_used"]}/{search["work_limit"]}; '
                     f'conditional score {search.get("baseline_score")} -> {search.get("best_score")}; alternatives incomplete.')
        rows(lines, search.get('challenges', []), limit,
             lambda r: f'{r["side"].upper()} {r["object"]}: '
                       f'{r["occupied_candidates"]}/{r["compatible_candidates"]} compatible candidates occupied initially; '
                       f'best sampled participation/omission scores={r["best_participating_score"]}/{r["best_omitted_score"]}; '
                       f'conditional margin={r["participation_margin"]}')
        primary = search.get('witnesses', [])
        ordered = [('Improving selected exchange', w) for w in primary
                   if w.get('selected') and w['score_delta'] < 0]
        ordered += [(f'Best sampled participation for {item["object"]}', item['participating_witness'])
                    for item in search.get('challenges', []) if item.get('participating_witness')]
        ordered += [('Retained primary alternative', w) for w in primary]
        ordered += [('Baseline-score diagnostic alternative (may be superseded)', w)
                    for w in search.get('baseline_tied_exchanges', [])]
        distinct = []; seen = set()
        for label, witness in ordered:
            key = tuple(tuple(sorted(tuple(pair) for pair in witness[field]))
                        for field in ('removed_pairs', 'added_pairs'))
            if key not in seen:
                seen.add(key); distinct.append((label, witness))
        lines.append(f'  Distinct coupled exchange witnesses: {len(distinct)}; showing {min(limit, len(distinct))}.')
        for label, witness in distinct[:limit]:
            lines.append(f'  {label}: score {witness["score"]}; delta {witness["score_delta"]}.')
            rows(lines, witness['removed_pairs'], limit, lambda p: f'release {p[0]} -> {p[1]}')
            rows(lines, witness['added_pairs'], limit, lambda p: f'pair {p[0]} -> {p[1]}')
        if len(distinct) > limit:
            lines.append(f'  {len(distinct) - limit} distinct exchange witnesses omitted; see full JSON or increase --limit.')
        lines.append('  Margins concern sampled maps only; no calibrated probability or global optimum.')
    return lines


def swap_summary(search, limit):
    """Display conditional swap evidence without implying a filtered search."""
    if not search:
        return []
    lines = [f'Paired-counterpart search (whole comparison scope): {search["stop"]}; '
             f'scores {search["work_used"]}/{search["work_limit"]}; alternatives incomplete.']
    if 'best_score' in search:
        lines.append(f'  Conditional score {search["baseline_score"]} -> {search["best_score"]}; '
                     f'paired-terminal discrepancies {search["baseline_endpoint_disagreements"]} -> '
                     f'{search["best_endpoint_disagreements"]}.')
    witnesses = sorted(search.get('witnesses', []), key=lambda w: not w.get('selected'))
    for witness in witnesses[:limit]:
        label = 'Selected improvement' if witness.get('selected') else 'Retained alternative'
        lines.append(f'  {label}: score {witness["score"]}; delta {witness["score_delta"]}.')
        rows(lines, witness['removed_pairs'], limit, lambda p: f'release {p[0]} -> {p[1]}')
        rows(lines, witness['added_pairs'], limit, lambda p: f'pair {p[0]} -> {p[1]}')
    if len(witnesses) > limit:
        lines.append(f'  {len(witnesses) - limit} more swap witnesses in full JSON.')
    lines.append('  Swaps preserve each seed\'s matched objects; costs are conditional, not identity or optimality evidence.')
    return lines


def summary(report, limit, output=None):
    scope = report['scope']
    lines = [f'Comparison: {scope["top_a"]} -> {scope["top_b"]}',
             f'Matching: {report["options"]["matching_mode"]}; all counterparts are tentative.']
    lines.append(f'Reference candidate screening complete: {report["metrics"]["screening_complete"]}')
    if 'black_box_assumption' in scope:
        lines.append('Black-box assumption: ' + scope['black_box_assumption'])
    budget = report.get('partial_alignment', {}).get('compute_budget')
    if budget:
        lines.append(f'Regional work: {budget["used"]}/{budget["limit"]}; exhausted: {budget["exhausted"]} (not a time/RAM cap)')
    lines += omission_summary(report.get('population_evidence'),
                              report.get('partial_alignment', {}).get('omission_search'), limit)
    lines += swap_summary(report.get('partial_alignment', {}).get('swap_search'), limit)
    if 'boundary' in report:
        lines.append(f'Instances: {report["a"]["selection"]["path"]} -> {report["b"]["selection"]["path"]}')
        lines.append('Pin correspondence and external shorts are retained separately in the full JSON boundary section.')
    for side in ('a', 'b'):
        data = report[side]
        coverage = ', '.join(f'{k}={v}' for k, v in data['coverage'].items())
        lines += [f'{side.upper()}: {data["expanded_leaf_count"]} materialized leaves; {coverage}',
                  f'  Expansion finished within budget: {data["expansion_complete"]}; input diagnostics: {len(data["diagnostics"])}']
        if data.get('black_box_leaf_count'):
            lines.append(f'  Black-box leaves with comparable terminals: {data["black_box_leaf_count"]}; hidden internals unavailable.')
        rows(lines, data['unresolved'], limit, lambda u: f'{u["region"]}: {u["reason"]}')
        not_paired = [d for d in data['disposition'] if d['status'] in ('unpaired', 'unresolved', 'opaque')]
        rows(lines, not_paired, limit, lambda d: f'{d["object"]}: {d["status"]} ({d["reason"]})')
        rows(lines, data['diagnostics'], limit, lambda d: f'{d.get("source") or "input"}:{d["line"]}: {d["message"]}')
    ids = set(report['representative_pair_ids'])
    pairs = [p for p in report['pair_options'] if p['id'] in ids]
    changed = [p for p in pairs if p['raw_differences']]
    component_selection = report.get('representative_selection', {}).get('components')
    if component_selection:
        history = component_selection['hypotheses']
        if history:
            last = history[-1]
            lines.append(f'Certified component presentation: {last["changed_pairs_before"]} -> {last["changed_pairs_after"]} raw-change pairs; all structural alternatives retained.')
            lines.append(f'  Skipped large residual factors: {len(last["skipped_large_residual_factors"])}; partially paired factors: {len(last["partially_paired_factors"])}.')
        else:
            lines.append('Certified component presentation: no retained hypothesis to refine.')
        lines.append('Raw values select a less noisy representative, never unique identity or hidden edit history.')
    lines.append(f'Representative pairs: {len(pairs)}; pairs with raw field changes: {len(changed)}')
    rows(lines, changed, limit, lambda p: f'{p["a"]} -> {p["b"]}: ' + '; '.join(
        f'{d["field"]}: {d["a"]!r} -> {d["b"]!r}' for d in p['raw_differences']))
    if component_selection:
        regions = report.get('inspection_regions', [])
        for p in changed[:limit]:
            related = [r for r in regions if p['a'] in r['a'] and p['b'] in r['b']]
            aa = {x for r in related for x in r['a']}; bb = {x for r in related for x in r['b']}
            lines.append(f'  Structural inspection scope for {p["a"]} -> {p["b"]}: {len(aa)} A / {len(bb)} B possible paths; coupled, see inspection_regions.')
        balances = component_selection['representative_profile_imbalances']
        lines.append(f'Unequal raw-profile populations in paired A-component slots: {len(balances)} (conditional on partner sets).')
        rows(lines, balances, limit, lambda r: f'factor {r["factor"]}, slot {r["slot"]}: at least {r["minimum_differing_pairs_in_slot"]} differing paired leaves; candidate paths/values in representative_selection.components.representative_profile_imbalances.')
        for balance in balances[:limit]:
            for profile in balance['profiles'][:limit]:
                side = 'a' if profile['count_a'] > profile['count_b'] else 'b'
                paths = profile['paths_' + side]
                excess = abs(profile['count_a'] - profile['count_b'])
                preview = ', '.join(paths[:limit]) + (f', ... ({len(paths)} total)' if len(paths) > limit else '')
                lines.append(f'  {side.upper()} raw-profile surplus {excess}; possible inventory witnesses: {preview}')
    wiring = [r for r in report['connectivity']['overlap'] if r['a_partitioned_across_b'] or r['b_collects_multiple_a']]
    lines.append(f'Conditional net-partition rows needing inspection: {len(wiring)} (not a count of independent wiring edits)')
    rows(lines, wiring, limit, lambda r: f'{r["a"]} -> {r["b"]}; {len(r["endpoint_tokens"])} paired endpoints')
    if component_selection:
        witness = component_selection['representative_wiring_witness']['endpoint_disagreements']
        lines.append(f'Endpoint inspection witnesses: {len(witness)} under one conditional maximum-overlap net map; net-map ties are not enumerated.')
        rows(lines, witness, limit, lambda p: f'Endpoint example: {p["a"]} -> {p["b"]} ({p["role"]}); {p["net_a"]} -> {p["net_b"]}')
    lines += ['Unpaired is not proven added/deleted. Alternatives are coupled and not exhaustive; this preview shows one representative.',
              'Definition defaults, call overrides, hierarchy and pin details remain in the full JSON.',
              'Model bodies and parameter evaluation are unavailable; budget completion does not mean complete semantics.',
              'Zero displayed changes does not establish equivalence.']
    if output:
        lines.append(f'Full JSON saved to: {output}')
    else:
        lines.append('Save the complete evidence and alternatives with --output result.json; use --json for JSON stdout.')
    return '\n'.join(lines) + '\n'
