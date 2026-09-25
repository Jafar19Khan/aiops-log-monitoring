"""Host metrics, simple trend forecasting and post-fix health verification."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable, Sequence

import numpy as np
import psutil


def collect_metrics(cpu_interval: float = 0.5) -> dict[str, float]:
    """Cross-platform CPU / memory / disk usage in percent."""
    return {
        "cpu": float(psutil.cpu_percent(interval=cpu_interval)),
        "mem": float(psutil.virtual_memory().percent),
        "disk": float(psutil.disk_usage(os.path.abspath(os.sep)).percent),
    }


@dataclass(frozen=True)
class Forecast:
    breach: bool
    predicted: float
    slope: float


def predict_breach(
    history: Sequence[float], threshold: float, horizon: int = 3, min_points: int = 5
) -> Forecast:
        """Fit a straight line to ``history`` and check if it crosses ``threshold`` within ``horizon``.

    A breach is only predicted for a *rising* trend; a value that is already high but flat
    is a current-threshold problem, not a forecast.
    """
    if len(history) < min_points:
        return Forecast(False, float(history[-1]) if len(history) else 0.0, 0.0)
    x = np.arange(len(history))
    slope, intercept = np.polyfit(x, np.asarray(history, dtype=float), 1)
    predicted = float(slope * (len(history) - 1 + horizon) + intercept)
    return Forecast(breach=bool(slope > 1e-6 and predicted > threshold),
                    predicted=predicted, slope=float(slope))


def verify_health(
    metrics_cfg: dict[str, Any],
    sampler: Callable[[], dict[str, float]] | None = None,
) -> tuple[bool, dict[str, float]]:
    """Return (healthy, metrics) using the configured thresholds."""
    sample = (sampler or collect_metrics)()
    healthy = (
        sample["cpu"] < metrics_cfg["cpu_threshold"]
        and sample["mem"] < metrics_cfg["mem_threshold"]
        and sample["disk"] < metrics_cfg["disk_threshold"]
    )
    return healthy, sample
