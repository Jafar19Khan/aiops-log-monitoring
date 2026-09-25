"""End-to-end analysis: parse -> features -> detect -> incidents -> remediation plan."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from aiops.detector import DetectionConfig, detect_anomalous_windows
from aiops.features import build_window_features
from aiops.incidents import Incident, build_incidents
from aiops.parser import ParseResult, parse_file
from aiops.remediation import plan_actions


@dataclass
class AnalysisResult:
    log_file: str
    total_lines: int
    skipped_lines: int
    windows: pd.DataFrame
    incidents: list[Incident]


def analyze_parsed(parsed: ParseResult, config: dict[str, Any], log_file: str = "<memory>") -> AnalysisResult:
    cfg = DetectionConfig.from_dict(config["detection"])
    features = build_window_features(parsed.frame, cfg.window)
    windows = detect_anomalous_windows(features, cfg)
    incidents = build_incidents(parsed.frame, windows, cfg)
    for incident in incidents:
        incident.planned_actions = plan_actions(incident, config["remediation"]["rules"])
    return AnalysisResult(
        log_file=log_file,
        total_lines=parsed.total_lines,
        skipped_lines=parsed.skipped_lines,
        windows=windows,
        incidents=incidents,
    )


def analyze_file(path: str | Path, config: dict[str, Any]) -> AnalysisResult:
    return analyze_parsed(parse_file(path), config, log_file=str(path))
