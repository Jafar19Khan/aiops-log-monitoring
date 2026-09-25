"""Turn a log frame into per-time-window features."""

from __future__ import annotations

import pandas as pd

from aiops.parser import LEVELS

FEATURE_COLUMNS = [
    "total",
    "warning",
    "error",
    "critical",
    "bad",
    "error_ratio",
    "unique_templates",
]


def build_window_features(frame: pd.DataFrame, window: str = "1min") -> pd.DataFrame:
    """Aggregate events into fixed windows (empty windows are kept with zero counts)."""
    if frame.empty:
        empty = pd.DataFrame(columns=FEATURE_COLUMNS)
        empty.index.name = "window"
        return empty

    bucket = frame["timestamp"].dt.floor(window)
    counts = pd.crosstab(bucket, frame["level"]).reindex(columns=LEVELS, fill_value=0)
    index = pd.date_range(bucket.min(), bucket.max(), freq=window, name="window")
    counts = counts.reindex(index, fill_value=0)

    feats = pd.DataFrame(index=index)
    feats["total"] = counts.sum(axis=1)
    feats["warning"] = counts["WARNING"]
    feats["error"] = counts["ERROR"]
    feats["critical"] = counts["CRITICAL"]
    feats["bad"] = feats["error"] + feats["critical"]
    feats["error_ratio"] = (feats["bad"] / feats["total"].where(feats["total"] > 0)).fillna(0.0)
    unique = frame.groupby(bucket)["template"].nunique()
    feats["unique_templates"] = unique.reindex(index, fill_value=0)
    return feats[FEATURE_COLUMNS]
