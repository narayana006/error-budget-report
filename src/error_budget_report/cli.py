"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .budget import EXHAUSTED, default_as_of, evaluate_all
from .events import parse_timestamp, read_events, read_events_file
from .render import to_html, to_markdown
from .slo import load_slos, parse_duration


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="error-budget-report",
        description="Report error budget remaining and burn rate for each SLO, "
                    "from SLO definitions and good/total event counts.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--slos", required=True, metavar="PATH",
                        help="SLO definition file, or a directory of .yaml/.yml/.json files")
    parser.add_argument("--events", required=True, metavar="FILE",
                        help="event counts CSV (timestamp,slo,good,total); '-' reads stdin")
    parser.add_argument("--window", default="7d",
                        help="reporting window, e.g. 7d (default: 7d)")
    parser.add_argument("--burn-windows", default="1h,6h,1d", metavar="LIST",
                        help="comma-separated extra burn-rate windows (default: 1h,6h,1d)")
    parser.add_argument("--as-of", metavar="TIMESTAMP",
                        help="end of all windows (default: end of the newest bucket in the events file)")
    parser.add_argument("--top-days", type=int, default=3, metavar="N",
                        help="worst days to list per SLO (default: 3)")
    parser.add_argument("--format", choices=("markdown", "html"), default="markdown",
                        help="output format (default: markdown)")
    parser.add_argument("--output", metavar="FILE", help="write the report here instead of stdout")
    parser.add_argument("--fail-on-exhausted", action="store_true",
                        help="exit with status 2 if any SLO has no budget left")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report_window = (args.window.strip(), parse_duration(args.window))
        burn_windows = []
        for label in [part.strip() for part in args.burn_windows.split(",") if part.strip()]:
            if label != report_window[0] and label not in [w[0] for w in burn_windows]:
                burn_windows.append((label, parse_duration(label)))
        burn_windows.sort(key=lambda w: w[1])
        burn_windows.append(report_window)

        slos = load_slos(args.slos)
        events = read_events(sys.stdin) if args.events == "-" else read_events_file(args.events)
        if not events:
            raise ValueError("events file has a header but no data rows")
        if args.as_of:
            try:
                as_of = parse_timestamp(args.as_of)
            except ValueError:
                raise ValueError(f"--as-of {args.as_of!r} is not an ISO 8601 timestamp") from None
        else:
            as_of = default_as_of(events)
    except (OSError, ValueError) as exc:
        print(f"error-budget-report: error: {exc}", file=sys.stderr)
        return 1

    known = {slo.name for slo in slos}
    for name in sorted(set(events) - known):
        print(f"error-budget-report: warning: events for unknown SLO {name!r} ignored", file=sys.stderr)

    reports = evaluate_all(slos, events, as_of, report_window, burn_windows, args.top_days)
    render = to_html if args.format == "html" else to_markdown
    text = render(reports, as_of, report_window[0])
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(text)
    else:
        sys.stdout.write(text)
    return 2 if args.fail_on_exhausted and any(r.status == EXHAUSTED for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
