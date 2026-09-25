"""Group anomalous windows into incidents and produce root-cause hints."""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from aiops.detector import DetectionConfig
from aiops.remediation import Action

SIGNAL_LEVELS = ["WARNING", "ERROR", "CRITICAL"]


@dataclass
class Incident:
    id: int
    start: pd.Timestamp
    end: pd.Timestamp
    severity: str
    warning_count: int
    error_count: int
    critical_count: int
    root_cause: str
    first_signal_time: pd.Timestamp | None
    top_templates: list[tuple[str, int]]
    novel_templates: list[str]
    planned_actions: list[Action] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "severity": self.severity,
            "counts": {
                "critical": self.critical_count,
                "error": self.error_count,
                "warning": self.warning_count,
            },
            "root_cause_candidate": self.root_cause,
            "first_signal_time": (
                self.first_signal_time.isoformat() if self.first_signal_time is not None else None
            ),
            "top_templates": [{"template": t, "count": c} for t, c in self.top_templates],
            "novel_templates": self.novel_templates,
            "planned_actions": [
                {
                    "action": a.name,
                    "params": a.params,
                    "command": a.command,
                    "matched_rule": a.matched_rule,
                }
                for a in self.planned_actions
            ],
        }


def group_windows(
    flagged: pd.DatetimeIndex, step: pd.Timedelta, max_gap_windows: int
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Merge flagged window starts into [start, end) spans, bridging small gaps."""
    spans: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for ts in sorted(flagged):
        if spans and ts - spans[-1][1] <= step * max_gap_windows:
            spans[-1] = (spans[-1][0], ts + step)
        else:
            spans.append((ts, ts + step))
    return spans


def _between(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    return (frame["timestamp"] >= start) & (frame["timestamp"] < end)


def build_incidents(
    frame: pd.DataFrame, windows: pd.DataFrame, cfg: DetectionConfig
) -> list[Incident]:
    flagged = windows.index[windows["anomaly"]]
    if len(flagged) == 0:
        return []

    step = pd.Timedelta(cfg.window)
    pad = step * cfg.context_windows
    spans = group_windows(flagged, step, cfg.max_gap_windows)

    # Baseline = everything outside incidents (and their precursor/aftershock context).
    in_or_near = pd.Series(False, index=frame.index)
    for start, end in spans:
        in_or_near |= _between(frame, start - pad, end + pad)
    baseline_counts = frame.loc[~in_or_near, "template"].value_counts()

    return [
        _analyse(number, start, end, frame, baseline_counts, cfg, pad)
        for number, (start, end) in enumerate(spans, start=1)
    ]


def _analyse(
    number: int,
    start: pd.Timestamp,
    end: pd.Timestamp,
    frame: pd.DataFrame,
    baseline_counts: pd.Series,
    cfg: DetectionConfig,
    pad: pd.Timedelta,
) -> Incident:
    events = frame[_between(frame, start, end)]
    levels = events["level"]
    warning = int((levels == "WARNING").sum())
    error = int((levels == "ERROR").sum())
    critical = int((levels == "CRITICAL").sum())
    severity = "CRITICAL" if critical else "ERROR" if error else "WARNING" if warning else "INFO"

    signal = events[levels.isin(SIGNAL_LEVELS)]
    top = [(str(t), int(c)) for t, c in signal["template"].value_counts().head(5).items()]

    # Root-cause hint: the earliest *new and repeating* warning-or-worse message, looking a
    # little before the incident too, because causes usually show up before the errors do.
    context = frame[_between(frame, start - pad, end)]
    context = context[context["level"].isin(SIGNAL_LEVELS)]
    repeats = context["template"].value_counts()
    is_novel = context["template"].map(
        lambda t: baseline_counts.get(t, 0) <= cfg.novelty_baseline_max
        and repeats[t] >= cfg.novelty_min_count
    )
    novel = context[is_novel.astype(bool)] if not context.empty else context
    novel_templates = list(dict.fromkeys(novel["template"]))

    first = None
    if not novel.empty:
        first = novel.iloc[0]
    else:
        errors = signal[signal["level"].isin(["ERROR", "CRITICAL"])]
        if not errors.empty:
            first = errors.iloc[0]

    return Incident(
        id=number,
        start=start,
        end=end,
        severity=severity,
        warning_count=warning,
        error_count=error,
        critical_count=critical,
        root_cause=str(first["template"]) if first is not None else "unknown",
        first_signal_time=first["timestamp"] if first is not None else None,
        top_templates=top,
        novel_templates=novel_templates,
    )
