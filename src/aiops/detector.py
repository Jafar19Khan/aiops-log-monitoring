"""Anomaly detection on window features: a transparent rule plus an Isolation Forest."""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Any

import pandas as pd
from sklearn.ensemble import IsolationForest

ML_FEATURES = ["total", "warning", "error", "critical", "error_ratio", "unique_templates"]


@dataclass(frozen=True)
class DetectionConfig:
    window: str = "1min"
    error_threshold: int = 5          # rule: ERROR+CRITICAL per window >= this
    contamination: float | str = "auto"
    random_state: int = 42
    ml_min_bad: int = 2               # ML flags only count if the window has >= this many errors
    max_gap_windows: int = 1          # merge flagged windows separated by <= this many windows
    context_windows: int = 2          # look this many windows before/after an incident
    novelty_baseline_max: int = 2     # "novel" = seen <= this often outside incidents
    novelty_min_count: int = 2        # ... and repeated at least this often inside the incident
    min_windows_for_ml: int = 10      # too little history -> rely on the rule only

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DetectionConfig":
        known = {f.name for f in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ValueError(f"Unknown detection option(s): {', '.join(sorted(unknown))}")
        return cls(**data)


def detect_anomalous_windows(features: pd.DataFrame, cfg: DetectionConfig) -> pd.DataFrame:
    """Add ``rule_flag``, ``ml_flag``, ``score`` and ``anomaly`` columns.

    * rule_flag - errors+criticals in the window reach ``error_threshold``.
    * ml_flag   - Isolation Forest calls the window unusual *and* it has at least
                  ``ml_min_bad`` errors, so a quiet traffic dip is not an incident.
    * anomaly   - rule_flag or ml_flag.
    """
    out = features.copy()
    out["rule_flag"] = out["bad"] >= cfg.error_threshold
    out["ml_flag"] = False
    out["score"] = 0.0

    if len(out) >= cfg.min_windows_for_ml:
        model = IsolationForest(
            n_estimators=200,
            contamination=cfg.contamination,
            random_state=cfg.random_state,
        )
        x = out[ML_FEATURES].astype(float)
        model.fit(x)
        out["ml_flag"] = model.predict(x) == -1
        out["score"] = -model.score_samples(x)  # higher = more unusual
        out["ml_flag"] = out["ml_flag"] & (out["bad"] >= cfg.ml_min_bad)

    out["anomaly"] = out["rule_flag"] | out["ml_flag"]
    return out
