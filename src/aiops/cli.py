"""Command line interface: ``aiops analyze | generate-logs | metrics``."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from aiops import __version__
from aiops.config import load_config
from aiops.metrics import collect_metrics, predict_breach, verify_health
from aiops.pipeline import analyze_file
from aiops.remediation import execute_actions
from aiops.report import format_action_results, format_text, to_json, write_reports
from aiops.simulate import generate_logs

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INCIDENTS = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aiops", description="Automated Log Monitoring & Incident Remediation toolkit"
    )
    parser.add_argument("--version", action="version", version=f"aiops {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging to stderr")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="detect incidents in a log file")
    analyze.add_argument("--logs", required=True, help="path to the log file")
    analyze.add_argument("--config", help="YAML config (defaults are built in)")
    analyze.add_argument("--output", help="directory for incidents.json and windows.csv")
    analyze.add_argument("--json", action="store_true", help="print JSON instead of text")
    analyze.add_argument("--execute", action="store_true",
                         help="actually run suggested fixes (default is dry-run)")
    analyze.add_argument("--verify-wait", type=int, default=10,
                         help="seconds to wait before the post-fix health check")
    analyze.add_argument("--fail-on-incident", action="store_true",
                         help=f"exit with code {EXIT_INCIDENTS} if any incident is found (for CI)")

    gen = sub.add_parser("generate-logs", help="write a synthetic log file with 2 incidents")
    gen.add_argument("--output", default="data/sample_logs.txt")
    gen.add_argument("--start", default="2026-06-27 10:00:00", help="YYYY-MM-DD HH:MM:SS")
    gen.add_argument("--minutes", type=int, default=90)
    gen.add_argument("--seed", type=int, default=42)
    gen.add_argument("--no-incidents", action="store_true", help="baseline traffic only")

    met = sub.add_parser("metrics", help="sample host metrics and forecast threshold breaches")
    met.add_argument("--config", help="YAML config for thresholds")
    met.add_argument("--samples", type=int, default=10)
    met.add_argument("--interval", type=float, default=1.0, help="seconds between samples")
    return parser


def cmd_analyze(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    dry_run = config["remediation"]["dry_run"] and not args.execute
    result = analyze_file(args.logs, config)

    if args.json:
        print(to_json(result))
    else:
        print(format_text(result))

    if args.output:
        paths = write_reports(result, args.output)
        if not args.json:
            print("\nReports written: " + ", ".join(str(p) for p in paths))

    actions = []
    for incident in result.incidents:
        actions += [a for a in incident.planned_actions if a not in actions]
    if actions:
        results = execute_actions(actions, dry_run=dry_run)
        if not args.json:
            mode = "dry-run (add --execute to run them)" if dry_run else "EXECUTING"
            print(f"\nRemediation mode: {mode}")
            print(format_action_results(results))
        if not dry_run:
            time.sleep(args.verify_wait)
            healthy, sample = verify_health(config["metrics"])
            message = "healthy" if healthy else "STILL UNHEALTHY"
            summary = f"Post-fix check: {message} (cpu={sample['cpu']}%, mem={sample['mem']}%, " \
                      f"disk={sample['disk']}%)"
            if args.json:
                logging.getLogger("aiops").info(summary)
            else:
                print(summary)

    if args.fail_on_incident and result.incidents:
        return EXIT_INCIDENTS
    return EXIT_OK


def cmd_generate(args: argparse.Namespace) -> int:
    start = datetime.strptime(args.start, "%Y-%m-%d %H:%M:%S")
    lines = generate_logs(start, args.minutes, args.seed, with_incidents=not args.no_incidents)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(lines)} log lines to {out}")
    return EXIT_OK


def cmd_metrics(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)["metrics"]
    history: dict[str, list[float]] = {"cpu": [], "mem": [], "disk": []}
    for i in range(args.samples):
        sample = collect_metrics()
        for key, value in sample.items():
            history[key].append(value)
        print(f"[{i + 1}/{args.samples}] cpu={sample['cpu']}% mem={sample['mem']}% "
              f"disk={sample['disk']}%")
        if i < args.samples - 1:
            time.sleep(args.interval)

    warned = False
    for key in ("cpu", "mem", "disk"):
        threshold = cfg[f"{key}_threshold"]
        forecast = predict_breach(history[key], threshold, cfg["forecast_horizon"])
        if history[key][-1] >= threshold:
            print(f"WARNING: {key} is at {history[key][-1]}% (threshold {threshold}%)")
            warned = True
        if forecast.breach:
            print(f"WARNING: {key} trending up, forecast {forecast.predicted:.1f}% "
                  f"in {cfg['forecast_horizon']} samples (threshold {threshold}%)")
            warned = True
    if not warned:
        print("All metrics within thresholds, no breach forecast.")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    handlers = {"analyze": cmd_analyze, "generate-logs": cmd_generate, "metrics": cmd_metrics}
    try:
        return handlers[args.command](args)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
