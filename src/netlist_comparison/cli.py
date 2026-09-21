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
from .terminal import inspection, summary, omission_summary, swap_summary
from .view import artifact_sha256, project_saved_report


EXAMPLES = """Start here (inputs are SPICE files, or spice-canonical tables with --format canonical):
  netlist-compare before.sp after.sp
      Compare the file-level circuits; a single definition is selected if needed.
  netlist-compare design.sp --inspect
      Discover circuit names and copyable instance paths without matching.
  netlist-compare before.sp after.sp --top-a AMP --top-b AMP --output result.json
      Compare named blocks and save the complete result.
  netlist-compare full.sp --top TOP --path-a TOP/X1 --path-b TOP/X2
  netlist-compare full.canonical --format canonical --top TOP --path-a TOP/XOLD --path-b TOP/XNEW --black-box-missing --matching-mode operator_scoped --text
      Compare two actual block calls, including their pins, in one file.
  netlist-compare before.sp after.sp --matching-mode regional --output result.json
      Try experimental hierarchy/regrouping matching; fixed remains the default.
  netlist-compare before.sp after.sp --black-box-missing --text
      Compare missing library cells by stable reference, pin order and overrides.
  netlist-compare before.canonical after.canonical --format canonical --black-box-missing
      Use spice-canonical exports, preserving named pins and extraction evidence.
  netlist-compare view result.json --under-a TOP/X1 --category raw --text
      Inspect a saved result without loading or matching netlists.
  netlist-compare view result.json --omit-parameters --group-depth 2 --text
      Start with types/references, wiring, unresolved scope and hierarchy membership.

Reading results:
  A/B paths are places to inspect in the two schematics. Pairings are tentative.
  Raw parameter changes are not evaluated expressions or electrical effects.
  Unpaired does not prove added/deleted; missing libraries are opaque by default.
  Zero displayed differences does not prove equivalence.
  Terminal output is readable text; redirected output is JSON. --text / --json
  override this choice. --output always saves full JSON, regardless of display.

Exit status: 0 = completed (possibly partial/ambiguous), 2 = input/usage/I/O error.
"""

GUIDE = """Operator mini-guide

Experimental supplied windows
  --matching-mode operator_scoped compares only the region correspondence you
  supply: one full canonical file with --top and both --path-a/--path-b, or two
  canonical files with --top-a/--top-b and optional per-side paths. Repeat paths
  only in this mode for unions. It makes no automatic global discovery or
  identity claim. --black-box-missing retains literal named/positional boundaries.
  At most 64 leaves/64 nets per side, 16 counterparts, 12 cards/100 full A+B paths.
  --operator-seconds 60 and --operator-memory-mib 3072 are configurable worker defaults, including CLI input loading and worker
  result encoding; final stdout/disk serialization is outside the deadline.
  POSIX /proc is required. Timeout, opaque or
  oversized scope is abstention, not certified quiet. --omit-parameters selects
  architecture/environment cards; literal parameter facts remain in full JSON.
  All weighted and K/K-1 proofs are required for terminal evidence. Equal
  boundary counts do not establish unchanged environment; alternatives remain
  unresolved. `view RESULT --category local --text` retains complete support.
  If corresponding paths are not known, a repository clone also includes the
  optional local-agent handoff at examples/luna_hierarchy_workflow.md. It uses a
  Luna medium agent to propose bounded rename/move/split/merge windows, validates
  them, then runs this mode. Proposals remain heuristics, never identities.

Choose an input shape
  A B compares two revisions.  A --inspect only discovers circuits, paths and
  extraction problems.  A --path-a PATH --path-b PATH compares two actual calls
  in one revision by default; it is not a shorthand for two revisions.
  operator_scoped additionally accepts per-side paths with two inputs. Use --top-a/--top-b
  with two files, and --top with inspect or two calls.  Inspect first when a file
  has several definitions or when a path needs percent-escaped segments.

Input and scope
  --format eldo (default) or ngspice reads SPICE; --format canonical reads a
  saved spice-canonical table and retains its extraction evidence.  --global-net
  adds known shared nets; --globals-complete is your assertion that this list and
  ground 0 are complete, not a check performed by this tool.  Missing libraries,
  malformed calls and budgets remain visible as opaque/unresolved scope.
  --black-box-missing is an explicit boundary-only assumption: same cell reference
  and compatible pin interface, with unchanged hidden internals.  It cannot make
  incompatible or one-sided definitions comparable, or establish equivalence.

Matching, uncertainty and budgets
  fixed (default) uses local feature retrieval then optional assignment. regional
  searches experimental structural/hierarchy alternatives. anchor_growth propagates
  from tentative anchors; it can diagnose supported leaves with no regional
  frontier, but is not guaranteed correct. partial_qap is the dense experimental
  structural reference. --context-mode frozen_neighbors works only with fixed.
  Regional-only --component-presentation minimum_raw is presentation inside
  certified symmetries: it chooses fewer changed raw leaf rows, preserves structural
  ambiguity, and is not edit history.
  Budgets bound named search counters, not total runtime or RAM. --candidate-top-k
  can widen reference retrieval and --max-objects can widen materialized scope.
  In contrast, raising --regional-work-limit alone cannot create a regional frontier
  after a regional hard-admission failure. No budget proves unique/equivalent results
  or repairs opaque/missing input and hard interface conflicts. A zero budget
  only disables controls whose option says so (omission challenges, paired swaps
  and alternative checks); other numeric limits require at least one. Regional
  --omission-work-limit searches unmatched participation through occupied
  counterparts; --swap-work-limit challenges existing pairs, including when no
  leaves are unmatched. Both preserve their stated constraints and remain incomplete.
  --help lists CLI-exposed controls; additional Options tuning fields are Python-only.

Read evidence, not a verdict
  Pairings are tentative. ambiguous means retained alternatives; unpaired means
  no proposed counterpart, not a proved add/delete. Regional population evidence
  can report a joint represented surplus even when individual objects are
  ambiguous; zero pair rows or zero displayed findings do not prove equivalence.
  minimum_raw counts changed raw leaf rows only, not electrical impact. Read the
  complete JSON for coupled alternatives, defaults/overrides, diagnostics and
  hierarchy; text is a bounded preview.

Save and focus later
  Redirected comparison output is full JSON; an attached terminal gets text.
  --json or --text chooses explicitly. --output always saves full JSON and never
  changes an input. `view RESULT --help` describes a read-only saved-report view:
  path filters, raw/wiring/unpaired categories, parameter omission, architecture-
  first grouping, and complete JSON versus bounded text. View only filters saved
  evidence; it never rematches. Population, omission-search and paired-swap context stays
  whole-scope under subtree filters.

Exit status: 0 means completed (possibly partial or ambiguous); 2 means an
input, usage or I/O error.

Copyable next steps
  netlist-compare design.sp --inspect
  netlist-compare before.sp after.sp --output result.json
  netlist-compare full.sp --top TOP --path-a TOP/X1 --path-b TOP/X2 --text
  netlist-compare before.canonical after.canonical --format canonical --black-box-missing \
    --matching-mode regional --omission-work-limit 512 --swap-work-limit 512 --output result.json
  netlist-compare view result.json --omit-parameters --group-depth 2 --text
"""

VIEW_EXAMPLES = """Examples:
  netlist-compare view result.json --under-a TOP/X1 --under-b TOP/X2 --category wiring --text
  netlist-compare view result.json --parameter W --category raw --json
  netlist-compare view result.json --omit-parameters --group-depth 2 --text

Subtree filters select findings, but population and both search summaries remain
whole-comparison-scope evidence. Views only filter saved evidence; they do not rematch.
"""

BUDGET_HELP = {
    "omission_work_limit": "Regional only: opt-in occupied-counterpart challenges; full-map score budget (try 512); 0 disables; not a time/RAM cap",
    "swap_work_limit": "Regional only: opt-in paired occupied-counterpart swaps; full-map incidence-score budget; 0 disables; not a time/RAM cap",
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
        description='Find possible counterparts and differences in analog netlists.\nRun with no arguments or --guide for operator decisions; no input files are modified.',
        epilog=EXAMPLES, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('a', type=Path, nargs='?', help='Old/first netlist, or full netlist for two-instance comparison')
    parser.add_argument('b', type=Path, nargs='?', help='New/second netlist; omit for --inspect or two-instance comparison')
    select = parser.add_argument_group('Choose what to compare')
    select.add_argument('--guide', action='store_true', help='Print the operator mini-guide and exit; also shown when no arguments are supplied')
    select.add_argument('--inspect', action='store_true', help='List circuits, pins, instance paths and input problems; do not match')
    select.add_argument('--top-a', metavar='CIRCUIT', help='Circuit in A; default: populated file-level TOP, or sole definition')
    select.add_argument('--top-b', metavar='CIRCUIT', help='Circuit in B; same automatic rule as A')
    select.add_argument('--top', metavar='CIRCUIT', help='Root for --inspect or --path-a/--path-b; same automatic rule')
    select.add_argument('--path-a', action='append', metavar='PATH', help='Actual A block call, e.g. TOP/X1; operator_scoped permits repetition for a scope union, including two-file inputs')
    select.add_argument('--path-b', action='append', metavar='PATH', help='Actual B block call; both required with one file; repeatable only in operator_scoped')
    select.add_argument('--format', choices=('eldo', 'ngspice', 'canonical'), default='eldo', help='Input syntax for both files (default: eldo); canonical loads spice-canonical tables without re-extraction')
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
    search.add_argument('--matching-mode', choices=('fixed', 'anchor_growth', 'partial_qap', 'regional', 'operator_scoped'), default='fixed',
                        help='fixed: local feature retrieval/optional assignment (default); regional: hierarchy alternatives; anchor_growth: tentative-anchor propagation; partial_qap: dense structural reference; operator_scoped: opt-in exact conditional evidence inside supplied windows (no global discovery)')
    search.add_argument('--context-mode', choices=('none', 'frozen_neighbors'), default='none', help='Optional fixed-mode neighbour context (default: none); incompatible with other modes')
    search.add_argument('--component-presentation', choices=('existing', 'minimum_raw'), default='existing',
                        help='Regional only: minimum_raw reduces changed leaf rows within certified whole-component permutations; preserves structural ambiguity (default: existing)')
    search.add_argument('--operator-seconds', type=float, default=60.0, help='operator_scoped only: worker computation deadline including canonical loading (default:60 seconds); expiry is incomplete, never quiet; final stdout/disk serialization is outside this deadline')
    search.add_argument('--operator-memory-mib', type=integer(64), default=3072, help='operator_scoped only: worker RSS watchdog budget (default:3072 MiB; POSIX /proc required)')
    output.add_argument('--omit-parameters', action='store_true', help='operator_scoped only: architecture/environment cards without parameter-detail cards; full local parameter facts remain in JSON')
    defaults = Options()
    for name, help_text in BUDGET_HELP.items():
        search.add_argument('--' + name.replace('_', '-'), type=integer(0 if name in ('max_alternative_checks', 'omission_work_limit', 'swap_work_limit') else 1),
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


def load_netlist(path, input_format):
    if input_format == 'canonical':
        from spice_canonical.canonical_netlist import from_canonical_file
        return from_canonical_file(path)
    return from_file(path, spice_format=input_format)


def view_parser():
    parser = argparse.ArgumentParser(prog='netlist-compare view',
                                     description='Read-only projection of a saved full comparison report: no netlist loading or rematching. Use categories and paths to focus evidence; JSON retains selected detail.',
                                     epilog=VIEW_EXAMPLES,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('result', type=Path, help='Saved full result.json (or result.json.gz)')
    parser.add_argument('--under-a', action='append', default=[], metavar='PATH', help='Focus an A subtree; repeatable, case-insensitive, percent-escaped segments; retains its paired B context')
    parser.add_argument('--under-b', action='append', default=[], metavar='PATH', help='Focus a B subtree; repeatable; either side may select a pair and retain the opposite context')
    parser.add_argument('--category', choices=('raw', 'wiring', 'unpaired', 'local'), action='append', metavar='CATEGORY',
                        help='Repeat raw|wiring|unpaired|local; default all. local=indivisible operator-scoped cards with full charged context. raw=leaf fields, wiring=represented partition rows, unpaired=dispositions/population evidence')
    details = parser.add_mutually_exclusive_group()
    details.add_argument('--parameter', metavar='NAME', help='Raw leaf parameter override name, e.g. W; requires raw category')
    details.add_argument('--omit-parameters', action='store_true',
                         help='Hide sizing/value/parameter-order findings; retain type, model/source_type and connectivity references. Default categories keep wiring/unpaired. Defaults/overrides remain in JSON context; use --group-depth for hierarchy membership. Does not rematch.')
    parser.add_argument('--group-depth', type=integer(0), metavar='N', help='Architecture-first text grouping at depth from each selected root; JSON retains selected leaf detail')
    parser.add_argument('--limit', type=integer(1), default=10, metavar='N', help='Text preview rows per section only; JSON remains complete')
    parser.add_argument('--output', type=Path, metavar='FILE', help='Write complete derived JSON view; source report is never overwritten')
    format_group = parser.add_mutually_exclusive_group()
    format_group.add_argument('--text', action='store_true', help='Readable bounded stdout')
    format_group.add_argument('--json', action='store_true', help='Complete JSON stdout, or silent stdout with --output')
    return parser


def view_summary(view, limit, output=None):
    if 'operator_scoped' in view.get('context', {}):
        from .terminal import operator_summary
        extension = {**view['context']['operator_scoped'], 'cards':view['findings'].get('local_cards', [])}
        return 'Derived saved-result view; complete retained cards keep original charges.\n' + operator_summary(extension, limit, output)
    counts = view['counts']['by_category']
    lines = ['Derived saved-result view; the full comparison remains the authority.',
             'Source: ' + str(view['source']['path']),
             'Representative pairs in path scope: ' + str(view['counts']['representative_pairs_in_path_scope']) +
             '/' + str(view['counts']['representative_pairs_total'])]
    if 'unpaired' in view['filters']['categories']:
        lines += omission_summary(view['context'].get('population_evidence'),
                                  view['findings'].get('omission_search'), limit)
    if 'wiring' in view['filters']['categories']:
        lines += swap_summary(view['findings'].get('swap_search'), limit)
    for category in ('raw', 'wiring', 'unpaired'):
        c = counts[category]
        lines.append(f'{category}: {c["shown"]}/{c["total"]} shown; {c["hidden"]} hidden')
    fields = view['counts']['raw_fields']
    lines.append(f'raw fields: {fields["shown"]}/{fields["total"]} shown; {fields["hidden"]} hidden')
    omit_parameters = view['filters'].get('omit_parameters', False)
    if omit_parameters:
        lines.append(f'Parameter fields suppressed in path scope: {view["counts"]["parameter_fields_suppressed_in_path_scope"]}. Type/model and connectivity-reference findings remain.')
        lines.append('Definition defaults and call overrides are not displayed as findings; full values remain in context.hierarchy.')
    for side in ('a', 'b'):
        data = view['source_scope']['sides'][side]
        lines.append(f'{side.upper()} scope: expansion_complete={data.get("expansion_complete")}; coverage={data.get("coverage")}; '
                     f'diagnostics={len(data.get("diagnostics", []))}; unresolved={len(data.get("unresolved", []))}; '
                     f'opaque={len(view["source_scope"]["opaque_objects"][side])}')
    assumption = view['source_scope']['scope'].get('black_box_assumption')
    if assumption:
        lines.append('Black-box assumption: ' + assumption)
    if view['filters']['group_depth'] is not None:
        groups = [row for row in view['hierarchy_groups'] if omit_parameters or any(row[k] for k in
                  ('raw_changed_pairs', 'wiring_partition_rows_touching', 'endpoint_witnesses', 'unpaired_a', 'unpaired_b'))]
        label = 'conditional memberships (including groups without findings)' if omit_parameters else 'with selected findings'
        lines.append(f'Hierarchy groups at relative depth {view["filters"]["group_depth"]}: {len(groups)} {label}')
        context_only = len(view['hierarchy_groups']) - len(groups)
        if context_only:
            lines.append(f'  {context_only} groups without selected findings omitted from text; retained in JSON.')
        for row in groups[:limit]:
            lines.append(f'  {row["a"]} -> {row["b"]}: pairs={row["representative_pairs"]}, '
                         f'raw changed pairs={row["raw_changed_pairs"]}, '
                         f'wiring rows touching={row["wiring_partition_rows_touching"]}, '
                         f'endpoint witnesses={row["endpoint_witnesses"]}, '
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
        preview('Conditional endpoint witnesses (one net map; ties not enumerated)',
                view['findings']['endpoint_witnesses'],
                lambda r: f'{r["a"]} -> {r["b"]} [{r["role"]}]: {r["net_a"]} -> {r["net_b"]}')
    if omit_parameters:
        lines.append('Hierarchy membership is conditional on matching, not a proven split/merge/redesign; use --group-depth N to inspect paths at another depth.')
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
                                    categories=args.category or ('raw', 'wiring', 'unpaired', 'local'),
                                    parameter=args.parameter, group_depth=args.group_depth,
                                    omit_parameters=args.omit_parameters)
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
        print(parser.description + '\n\n' + GUIDE + '\nAll options, choices and parser-derived defaults: netlist-compare --help')
        return 0
    if argv[0] == 'view':
        return view_main(argv[1:])
    args = parser.parse_args(argv)
    if args.guide:
        if len(argv) != 1:
            parser.error('--guide is a standalone help topic; omit input and comparison options.')
        print(GUIDE)
        return 0
    if not args.a:
        parser.error('Supply a netlist file. Start with: netlist-compare design.sp --inspect')
    instance_mode = args.path_a is not None or args.path_b is not None
    if args.inspect:
        if args.b or instance_mode or args.top_a or args.top_b or args.output or args.json:
            parser.error('--inspect takes one file and optional --top CIRCUIT; omit comparison/output options.')
    elif instance_mode and args.matching_mode == 'operator_scoped':
        if (not args.b and (not args.path_a or not args.path_b or args.top_a or args.top_b)) or (args.b and args.top):
            parser.error('operator_scoped: one file needs both paths and --top; two files use --top-a/--top-b with optional per-side paths.')
    elif instance_mode:
        if len(args.path_a or ()) > 1 or len(args.path_b or ()) > 1:
            parser.error('repeated paths require --matching-mode operator_scoped')
        if not args.path_a or not args.path_b or args.b or args.top_a or args.top_b:
            parser.error('Use one file and both --path-a and --path-b. Example: netlist-compare full.sp --top TOP --path-a TOP/X1 --path-b TOP/X2')
    elif not args.b or args.top:
        parser.error('For two files: netlist-compare before.sp after.sp [--top-a CIRCUIT --top-b CIRCUIT]. For one file, use --inspect or both --path-a/--path-b.')
    try:
        if args.context_mode != 'none' and args.matching_mode != 'fixed':
            parser.error('--context-mode frozen_neighbors requires --matching-mode fixed; omit --context-mode for other modes.')
        if args.matching_mode != 'operator_scoped' and (args.omit_parameters or args.operator_seconds != 60.0 or args.operator_memory_mib != 3072):
            parser.error('--operator-seconds/--operator-memory-mib/--omit-parameters require --matching-mode operator_scoped')
        options = Options(matching_mode=args.matching_mode, context_mode=args.context_mode,
                          operator_time_limit=args.operator_seconds, operator_memory_mib=args.operator_memory_mib, operator_parameters=not args.omit_parameters,
                          component_presentation=args.component_presentation,
                          black_box_missing=args.black_box_missing,
                          **{name: getattr(args, name) for name in BUDGET_HELP})
        scope = InputScope(tuple(['0', *args.global_net]), args.globals_complete)
        for path in filter(None, (args.a, args.b)):
            if not path.is_file():
                parser.error(f'Cannot read netlist file: {path}. Check the path; quote paths containing spaces.')
            if args.output and args.output.resolve() == path.resolve():
                parser.error('--output must be different from the input files.')
        if args.matching_mode == 'operator_scoped' and not args.inspect:
            from .operator_scoped import compare_files
            result = compare_files(args, options, scope)
        else:
            a = load_netlist(args.a, args.format)
        if args.inspect:
            top = args.top
            if top is None and (a.top.devices or len(a.subcircuits) <= 1):
                top = choose_top(a, None, '--top')
            view = expand(a, choose_top(a, top, '--top'), scope, options) if top else None
            sys.stdout.write(inspection(a, view, args.a, args.limit))
            return 0
        if args.matching_mode == 'operator_scoped':
            pass  # Complete input parsing/comparison already ran in the bounded worker.
        elif instance_mode:
            top = choose_top(a, args.top, '--top')
            result = compare_instances(a, top=top, path_a=args.path_a[0], path_b=args.path_b[0], options=options, scope=scope)
        else:
            b = load_netlist(args.b, args.format)
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
        hint = f'\nDiscover circuits and paths: netlist-compare {shlex.quote(str(args.a))} --format {args.format} --inspect'
        if args.output and isinstance(exc, OSError):
            hint += '\nCheck that the output directory exists and is writable.'
        parser.error(str(exc) + hint)
    return 0
