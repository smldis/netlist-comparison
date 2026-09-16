import argparse
import json
from pathlib import Path
import sys

from spice_canonical.canonical_netlist import from_file

from .api import compare, compare_instances
from .model import InputScope, Options


def main(argv=None):
    parser = argparse.ArgumentParser(description="Tentative netlist counterparts and conditional raw differences")
    parser.add_argument("a", type=Path)
    parser.add_argument("b", type=Path, nargs="?")
    parser.add_argument("--top-a", help="TOP for canonical top level, or a subcircuit name")
    parser.add_argument("--top-b")
    parser.add_argument("--top", help="Full-input top for instance comparison")
    parser.add_argument("--path-a")
    parser.add_argument("--path-b")
    parser.add_argument("--matching-mode", choices=("fixed", "anchor_growth", "partial_qap", "regional"), default="fixed")
    parser.add_argument("--context-mode", choices=("none", "frozen_neighbors"), default="none")
    parser.add_argument("--format", choices=("eldo", "ngspice"), default="eldo")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--global-net", action="append", default=[], help="Explicit global net on both sides; repeatable")
    parser.add_argument("--globals-complete", action="store_true", help="Assert supplied global nets plus 0 are complete")
    for name in ("regional_work_limit", "candidate_top_k", "max_objects", "max_pair_scores", "max_component_nodes", "max_alternative_checks"):
        parser.add_argument("--" + name.replace("_", "-"), type=int, default=getattr(Options(), name))
    args = parser.parse_args(argv)
    try:
        options = Options(matching_mode=args.matching_mode, context_mode=args.context_mode, **{name: getattr(args, name) for name in
                             ("regional_work_limit", "candidate_top_k", "max_objects", "max_pair_scores", "max_component_nodes", "max_alternative_checks")})
        scope = InputScope(tuple(["0", *args.global_net]), args.globals_complete)
        if any((args.top, args.path_a, args.path_b)):
            if not all((args.top, args.path_a, args.path_b)) or args.b or args.top_a or args.top_b:
                parser.error("instance mode requires one input, --top, --path-a and --path-b")
            result = compare_instances(from_file(args.a, spice_format=args.format), top=args.top,
                                       path_a=args.path_a, path_b=args.path_b, options=options, scope=scope)
        else:
            if not all((args.b, args.top_a, args.top_b)):
                parser.error("definition mode requires two inputs, --top-a and --top-b")
            result = compare(from_file(args.a, spice_format=args.format),
                             from_file(args.b, spice_format=args.format),
                             top_a=args.top_a, top_b=args.top_b, options=options,
                             scope_a=scope, scope_b=scope)
        encoded = json.dumps(result, indent=2, allow_nan=False) + "\n"
        if args.output:
            args.output.write_text(encoded, encoding="utf-8")
        else:
            sys.stdout.write(encoded)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 0
