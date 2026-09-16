"""Self-contained terminal entry point; redirected comparison output stays JSON."""
import argparse
import gzip
import json
import os
from pathlib import Path
import shlex
import sys

from spice_canonical.canonical_netlist import from_file

from .api import compare, compare_instances
from .expand import expand
from .model import InputScope, Options
from .terminal import inspection, summary
from .view import artifact_sha256, project_saved_report


EXAMPLES = """Start here (inputs are SPICE/Eldo/ngspice files, not rendered canonical tables):
  netlist-compare before.sp after.sp
      Compare the file-level circuits; a single definition is selected if needed.
  netlist-compare design.sp --inspect
      Discover circuit names and copyable instance paths without matching.
  netlist-compare before.sp after.sp --top-a AMP --top-b AMP --output result.json
      Compare named blocks and save the complete result.
  netlist-compare full.sp --top TOP --path-a TOP/X1 --path-b TOP/X2
      Compare two actual block calls, including their pins, in one file.
  netlist-compare before.sp after.sp --matching-mode regional --output result.json
      Try experimental hierarchy/regrouping matching; fixed remains the default.
  netlist-compare before.sp after.sp --black-box-missing --text
      Compare missing library cells by stable reference, pin order and overrides.
  netlist-compare view result.json --under-a TOP/X1 --category raw --text
      Inspect a saved result without loading or matching netlists.

Reading results:
  A/B paths are places to inspect in the two schematics. Pairings are tentative.
  Raw parameter changes are not evaluated expressions or electrical effects.
  Unpaired does not prove added/deleted; missing libraries are opaque by default.
  Zero displayed differences does not prove equivalence.
  Terminal output is readable text; redirected output is JSON. --text / --json
  override this choice. --output always saves full JSON, regardless of display.

Exit status: 0 = completed (possibly partial/ambiguous), 2 = input/usage/I/O error.
"""

BUDGET_HELP = {
    'regional_work_limit': 'Regional candidate/certificate work limit; NOT a time or RAM cap',
    'candidate_top_k': 'Candidate feature classes per object; not individual copies',
    'max_objects': 'Expansion limit per input/selected subtree, counting calls and leaves',
    'max_depth': 'Expansion depth below the selected root',
    'max_pair_scores': 'Maximum screened class-pair scores',
    'max_component_nodes': 'Fixed-matcher assignment component size limit',
    'max_alternative_checks': 'Additional alternative-assignment checks; zero disables them',
}


def integer(minimum):
    def parse(value):
        try:
            number = int(value)
        except ValueError:
            raise argparse.ArgumentTypeError('must be an integer') from None
        if number < minimum:
            raise argparse.ArgumentTypeError(f'must be at least {minimum}')
        return number
    return parse


def build_parser():
    parser = argparse.ArgumentParser(
        prog='netlist-compare', usage='%(prog)s A [B] [options]',
        description='Find possible counterparts and differences in analog netlists.\nRun with no arguments for this guide; no input files are modified.',
        epilog=EXAMPLES, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('a', type=Path, nargs='?', help='Old/first netlist, or full netlist for two-instance comparison')
    parser.add_argument('b', type=Path, nargs='?', help='New/second netlist; omit for --inspect or two-instance comparison')
    select = parser.add_argument_group('Choose what to compare')
    select.add_argument('--inspect', action='store_true', help='List circuits, pins, instance paths and input problems; do not match')
    select.add_argument('--top-a', metavar='CIRCUIT', help='Circuit in A; default: populated file-level TOP, or sole definition')
    select.add_argument('--top-b', metavar='CIRCUIT', help='Circuit in B; same automatic rule as A')
    select.add_argument('--top', metavar='CIRCUIT', help='Root for --inspect or --path-a/--path-b; same automatic rule')
    select.add_argument('--path-a', metavar='PATH', help='First actual block call, e.g. TOP/X1; discover with --inspect')
    select.add_argument('--path-b', metavar='PATH', help='Second actual block call, e.g. TOP/X2; both paths required')
    select.add_argument('--format', choices=('eldo', 'ngspice'), default='eldo', help='Input syntax for both files (default: eldo)')
    select.add_argument('--global-net', action='append', default=[], metavar='NET', help='Extra global net on both sides, e.g. VDD; repeatable; ground 0 is included')
    select.add_argument('--globals-complete', action='store_true', help='Assert these globals plus 0 are complete; otherwise completeness is unknown')
    select.add_argument('--black-box-missing', action='store_true', help='Compare undefined cells as black boxes: assume unchanged internals and stable cell references/pin order; incompatible interfaces stay unresolved')
    output = parser.add_argument_group('Read or save results')
    output.add_argument('--output', type=Path, metavar='FILE', help='Save complete JSON (replaces FILE); show a short terminal summary')
    display = output.add_mutually_exclusive_group()
    display.add_argument('--text', action='store_true', help='Readable stdout even when redirected; bounded preview, not the complete report')
    display.add_argument('--json', action='store_true', help='Full JSON stdout, or silent stdout with --output (comparison only)')
    output.add_argument('--limit', type=integer(1), default=10, metavar='N', help='Maximum rows per text/inspection section (default: 10); does not limit matching')
    search = parser.add_argument_group('Matching and compute (optional)')
    search.add_argument('--matching-mode', choices=('fixed', 'anchor_growth', 'partial_qap', 'regional'), default='fixed',
                        help='fixed: baseline (default); regional: experimental hierarchy/regrouping; anchor_growth and partial_qap: research alternatives')
    search.add_argument('--context-mode', choices=('none', 'frozen_neighbors'), default='none', help='Optional fixed-mode neighbour context (default: none); incompatible with other modes')
    defaults = Options()
    for name, help_text in BUDGET_HELP.items():
        search.add_argument('--' + name.replace('_', '-'), type=integer(0 if name == 'max_alternative_checks' else 1),
                            default=getattr(defaults, name), metavar='N', help=f'{help_text} (default: {getattr(defaults, name)})')
    return parser


def choose_top(data, requested, flag):
    circuits = (data.top, *data.subcircuits)
    names = ', '.join(c.name for c in circuits)
    if requested:
        if requested.casefold() not in {c.name.casefold() for c in circuits}:
            raise ValueError(f'unknown top circuit: {requested}. Available circuits: {names}. Select with {flag} CIRCUIT.')
        return next(c.name for c in circuits if c.name.casefold() == requested.casefold())
    if data.top.devices or not data.subcircuits:
        return data.top.name
    if len(data.subcircuits) == 1:
        return data.subcircuits[0].name
    raise ValueError(f'File-level {data.top.name} is empty and several definitions exist. Choose {flag} CIRCUIT. Available circuits: {names}.')


def view_parser():
    parser = argparse.ArgumentParser(prog='netlist-compare view',
                                     description='Project a saved full comparison report; no matching or netlist loading.')
    parser.add_argument('result', type=Path, help='Saved full result.json (or result.json.gz)')
    parser.add_argument('--under-a', action='append', default=[], metavar='PATH', help='A subtree; repeatable, case-insensitive, percent-escaped segments')
    parser.add_argument('--under-b', action='append', default=[], metavar='PATH', help='B subtree; repeatable; either side may select a pair')
    parser.add_argument('--category', choices=('raw', 'wiring', 'unpaired'), action='append', metavar='CATEGORY',
                        help='Repeat raw|wiring|unpaired; default all. raw = leaf raw fields; wiring = represented partition rows')
    parser.add_argument('--parameter', metavar='NAME', help='Raw leaf parameter override name, e.g. W; requires raw category')
    parser.add_argument('--group-depth', type=integer(0), metavar='N', help='Collapse text to finding counts at depth from each selected root; JSON retains detail')
    parser.add_argument('--limit', type=integer(1), default=10, metavar='N', help='Text preview rows per section only; JSON remains complete')
    parser.add_argument('--output', type=Path, metavar='FILE', help='Write complete derived JSON view; source report is never overwritten')
    format_group = parser.add_mutually_exclusive_group()
    format_group.add_argument('--text', action='store_true', help='Readable bounded stdout')
    format_group.add_argument('--json', action='store_true', help='Complete JSON stdout, or silent stdout with --output')
    return parser


def view_summary(view, limit, output=None):
    counts = view['counts']['by_category']
    lines = ['Derived saved-result view; the full comparison remains the authority.',
             'Source: ' + str(view['source']['path']),
             'Representative pairs in path scope: ' + str(view['counts']['representative_pairs_in_path_scope']) +
             '/' + str(view['counts']['representative_pairs_total'])]
    for category in ('raw', 'wiring', 'unpaired'):
        c = counts[category]
        lines.append(f'{category}: {c["shown"]}/{c["total"]} shown; {c["hidden"]} hidden')
    fields = view['counts']['raw_fields']
    lines.append(f'raw fields: {fields["shown"]}/{fields["total"]} shown; {fields["hidden"]} hidden')
    for side in ('a', 'b'):
        data = view['source_scope']['sides'][side]
        lines.append(f'{side.upper()} scope: expansion_complete={data.get("expansion_complete")}; coverage={data.get("coverage")}; '
                     f'diagnostics={len(data.get("diagnostics", []))}; unresolved={len(data.get("unresolved", []))}; '
                     f'opaque={len(view["source_scope"]["opaque_objects"][side])}')
    assumption = view['source_scope']['scope'].get('black_box_assumption')
    if assumption:
        lines.append('Black-box assumption: ' + assumption)
    if view['filters']['group_depth'] is not None:
        groups = [row for row in view['hierarchy_groups'] if any(row[k] for k in
                  ('raw_changed_pairs', 'wiring_partition_rows_touching', 'unpaired_a', 'unpaired_b'))]
        lines.append(f'Hierarchy groups at relative depth {view["filters"]["group_depth"]}: {len(groups)} with selected findings')
        context_only = len(view['hierarchy_groups']) - len(groups)
        if context_only:
            lines.append(f'  {context_only} groups without selected findings omitted from text; retained in JSON.')
        for row in groups[:limit]:
            lines.append(f'  {row["a"]} -> {row["b"]}: pairs={row["representative_pairs"]}, '
                         f'raw changed pairs={row["raw_changed_pairs"]}, '
                         f'wiring rows touching={row["wiring_partition_rows_touching"]}, '
                         f'unpaired A/B={row["unpaired_a"]}/{row["unpaired_b"]}')
        if len(groups) > limit:
            lines.append(f'  ... {len(groups) - limit} more groups; JSON retains all rows.')
        lines.append('One wiring partition row may touch several groups; group counts are not independent edits.')
    else:
        def preview(label, rows, render):
            lines.append(f'{label}: {len(rows)}')
            lines.extend('  ' + render(row) for row in rows[:limit])
            if len(rows) > limit:
                lines.append(f'  ... {len(rows) - limit} more; JSON retains all rows.')
        preview('Raw leaf pairs', view['findings']['raw_pairs'],
                lambda p: f'{p["a"]} -> {p["b"]}: {p["raw_differences"]}')
        pair_by_id = {p['id']: p for p in view['context']['pair_options']}
        wiring = view['findings']['wiring_partition_rows']
        lines.append(f'Wiring partition rows: {len(wiring)}')
        for row in wiring[:limit]:
            lines.append(f'  {row["a"]} -> {row["b"]}: {len(row["endpoint_tokens"])} paired endpoints')
            for token in row['endpoint_tokens'][:limit]:
                pair_id, role = token.split(':', 1)
                pair = pair_by_id[pair_id]
                lines.append(f'    {pair["a"]} -> {pair["b"]} [{role}]')
            if len(row['endpoint_tokens']) > limit:
                lines.append(f'    ... {len(row["endpoint_tokens"]) - limit} more endpoints; JSON retains all.')
        if len(wiring) > limit:
            lines.append(f'  ... {len(wiring) - limit} more wiring rows; JSON retains all.')
        preview('A unpaired/opaque', view['findings']['unpaired_objects']['a'],
                lambda r: f'{r["object"]}: {r["status"]}')
        preview('B unpaired/opaque', view['findings']['unpaired_objects']['b'],
                lambda r: f'{r["object"]}: {r["status"]}')
    lines.append('Pairs remain tentative; alternatives, hierarchy/default/override context, and full scope are in JSON.')
    lines.append('Empty findings mean none selected, not equivalence. Wiring rows are not independent edit counts.')
    if output:
        lines.append('Derived JSON saved to: ' + str(output))
    return '\n'.join(lines) + '\n'


def view_main(argv):
    parser = view_parser()
    args = parser.parse_args(argv)
    if args.output and (args.output.resolve() == args.result.resolve() or
                        (args.output.exists() and args.result.exists() and os.path.samefile(args.output, args.result))):
        parser.error('--output must differ from the source report, including same-file aliases')
    try:
        data = args.result.read_bytes()
        decoded = gzip.decompress(data) if args.result.suffix == '.gz' else data
        report = json.loads(decoded)
        view = project_saved_report(report, source_path=args.result, source_sha256=artifact_sha256(data),
                                    under_a=args.under_a, under_b=args.under_b,
                                    categories=args.category or ('raw', 'wiring', 'unpaired'),
                                    parameter=args.parameter, group_depth=args.group_depth)
        encoded = json.dumps(view, indent=2, allow_nan=False) + '\n'
        if args.output:
            args.output.write_text(encoded, encoding='utf-8')
        text_mode = args.text or (not args.json and sys.stdout.isatty())
        if text_mode or (args.output and not args.json):
            (sys.stdout if text_mode else sys.stderr).write(view_summary(view, args.limit, args.output))
        elif not args.output:
            sys.stdout.write(encoded)
    except (ValueError, OSError, UnicodeError, EOFError, KeyError, TypeError, AttributeError, IndexError) as exc:
        parser.error(f'Cannot project saved result: {exc}. Check the report schema, selector paths and options.')
    return 0


def main(argv=None):
    parser = build_parser()
    argv = sys.argv[1:] if argv is None else list(argv)
    if not argv:
        print(parser.description + '\n\n' + EXAMPLES + '\nAll options and defaults: netlist-compare --help')
        return 0
    if argv[0] == 'view':
        return view_main(argv[1:])
    args = parser.parse_args(argv)
    if not args.a:
        parser.error('Supply a netlist file. Start with: netlist-compare design.sp --inspect')
    instance_mode = args.path_a is not None or args.path_b is not None
    if args.inspect:
        if args.b or instance_mode or args.top_a or args.top_b or args.output or args.json:
            parser.error('--inspect takes one file and optional --top CIRCUIT; omit comparison/output options.')
    elif instance_mode:
        if not args.path_a or not args.path_b or args.b or args.top_a or args.top_b:
            parser.error('Use one file and both --path-a and --path-b. Example: netlist-compare full.sp --top TOP --path-a TOP/X1 --path-b TOP/X2')
    elif not args.b or args.top:
        parser.error('For two files: netlist-compare before.sp after.sp [--top-a CIRCUIT --top-b CIRCUIT]. For one file, use --inspect or both --path-a/--path-b.')
    try:
        if args.context_mode != 'none' and args.matching_mode != 'fixed':
            parser.error('--context-mode frozen_neighbors requires --matching-mode fixed; omit --context-mode for other modes.')
        options = Options(matching_mode=args.matching_mode, context_mode=args.context_mode,
                          black_box_missing=args.black_box_missing,
                          **{name: getattr(args, name) for name in BUDGET_HELP})
        scope = InputScope(tuple(['0', *args.global_net]), args.globals_complete)
        for path in filter(None, (args.a, args.b)):
            if not path.is_file():
                parser.error(f'Cannot read netlist file: {path}. Check the path; quote paths containing spaces.')
            if args.output and args.output.resolve() == path.resolve():
                parser.error('--output must be different from the input files.')
        a = from_file(args.a, spice_format=args.format)
        if args.inspect:
            top = args.top
            if top is None and (a.top.devices or len(a.subcircuits) <= 1):
                top = choose_top(a, None, '--top')
            view = expand(a, choose_top(a, top, '--top'), scope, options) if top else None
            sys.stdout.write(inspection(a, view, args.a, args.limit))
            return 0
        if instance_mode:
            top = choose_top(a, args.top, '--top')
            result = compare_instances(a, top=top, path_a=args.path_a, path_b=args.path_b, options=options, scope=scope)
        else:
            b = from_file(args.b, spice_format=args.format)
            result = compare(a, b, top_a=choose_top(a, args.top_a, '--top-a'),
                             top_b=choose_top(b, args.top_b, '--top-b'), options=options, scope_a=scope, scope_b=scope)
        encoded = json.dumps(result, indent=2, allow_nan=False) + '\n'
        if args.output:
            args.output.write_text(encoded, encoding='utf-8')
        text_mode = args.text or (not args.json and sys.stdout.isatty())
        if text_mode or (args.output and not args.json):
            stream = sys.stdout if text_mode else sys.stderr
            stream.write(summary(result, args.limit, args.output))
        elif not args.output:
            sys.stdout.write(encoded)
    except (ValueError, OSError) as exc:
        hint = f'\nDiscover circuits and paths: netlist-compare {shlex.quote(str(args.a))} --inspect'
        if args.output and isinstance(exc, OSError):
            hint += '\nCheck that the output directory exists and is writable.'
        parser.error(str(exc) + hint)
    return 0
