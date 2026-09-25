"""Human- and machine-readable reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from aiops.pipeline import AnalysisResult
from aiops.remediation import ActionResult


def to_dict(result: AnalysisResult) -> dict:
    flagged = int(result.windows["anomaly"].sum()) if not result.windows.empty else 0
    return {
        "log_file": result.log_file,
        "lines_total": result.total_lines,
        "lines_skipped": result.skipped_lines,
        "windows_analysed": len(result.windows),
        "windows_flagged": flagged,
        "incidents": [incident.to_dict() for incident in result.incidents],
    }


def to_json(result: AnalysisResult) -> str:
    return json.dumps(to_dict(result), indent=2)


def format_text(result: AnalysisResult) -> str:
    data = to_dict(result)
    parsed = result.total_lines - result.skipped_lines
    lines = [
        "AIOps analysis",
        "==============",
        f"Log file         : {result.log_file}",
        f"Lines parsed     : {parsed} of {result.total_lines} ({result.skipped_lines} skipped)",
        f"Windows analysed : {data['windows_analysed']} ({data['windows_flagged']} flagged)",
        f"Incidents found  : {len(result.incidents)}",
    ]
    for inc in result.incidents:
        lines += [
            "",
            f"Incident #{inc.id} [{inc.severity}]  "
            f"{inc.start:%Y-%m-%d %H:%M:%S} -> {inc.end:%H:%M:%S}",
            f"  events          : {inc.critical_count} critical, {inc.error_count} error, "
            f"{inc.warning_count} warning",
            f"  root cause hint : {inc.root_cause}",
        ]
        if inc.first_signal_time is not None:
            lines.append(f"  first signal at : {inc.first_signal_time:%H:%M:%S}")
        lines.append("  top messages    :")
        lines += [f"    {count:>4}x {template}" for template, count in inc.top_templates[:3]]
        if inc.planned_actions:
            lines.append("  suggested fixes :")
            lines += [f"    {a.name}: {' '.join(a.command)}" for a in inc.planned_actions]
    return "\n".join(lines)


def format_action_results(results: Iterable[ActionResult]) -> str:
    lines = []
    for r in results:
        cmd = " ".join(r.action.command)
        if r.executed:
            lines.append(f"  ran     : {cmd} (exit {r.returncode})")
        elif r.returncode is None:
            lines.append(f"  dry-run : {cmd}")
        else:
            lines.append(f"  failed  : {cmd} ({r.output})")
    return "\n".join(lines)


def write_reports(result: AnalysisResult, out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = out / "incidents.json"
    report.write_text(to_json(result) + "\n", encoding="utf-8")
    windows = out / "windows.csv"
    result.windows.to_csv(windows)
    return [report, windows]
