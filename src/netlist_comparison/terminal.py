"""Bounded deterministic display of existing evidence, without new interpretation."""
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
    lines.append(f'Representative pairs: {len(pairs)}; pairs with raw field changes: {len(changed)}')
    rows(lines, changed, limit, lambda p: f'{p["a"]} -> {p["b"]}: ' + '; '.join(
        f'{d["field"]}: {d["a"]!r} -> {d["b"]!r}' for d in p['raw_differences']))
    wiring = [r for r in report['connectivity']['overlap'] if r['a_partitioned_across_b'] or r['b_collects_multiple_a']]
    lines.append(f'Conditional net-partition rows needing inspection: {len(wiring)} (not a count of independent wiring edits)')
    rows(lines, wiring, limit, lambda r: f'{r["a"]} -> {r["b"]}; {len(r["endpoint_tokens"])} paired endpoints')
    lines += ['Unpaired is not proven added/deleted. Alternatives are coupled and not exhaustive; this preview shows one representative.',
              'Definition defaults, call overrides, hierarchy and pin details remain in the full JSON.',
              'Model bodies and parameter evaluation are unavailable; budget completion does not mean complete semantics.',
              'Zero displayed changes does not establish equivalence.']
    if output:
        lines.append(f'Full JSON saved to: {output}')
    else:
        lines.append('Save the complete evidence and alternatives with --output result.json; use --json for JSON stdout.')
    return '\n'.join(lines) + '\n'
