"""Configuration loading: built-in defaults merged with an optional YAML file."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG: dict[str, Any] = {
    "detection": {
        "window": "1min",
        "error_threshold": 5,
        "contamination": "auto",
        "random_state": 42,
        "ml_min_bad": 2,
        "max_gap_windows": 1,
        "context_windows": 2,
        "novelty_baseline_max": 2,
        "novelty_min_count": 2,
        "min_windows_for_ml": 10,
    },
    "metrics": {
        "cpu_threshold": 85,
        "mem_threshold": 90,
        "disk_threshold": 90,
        "forecast_horizon": 3,
    },
    "remediation": {
        "dry_run": True,
        "rules": [],
    },
}


def _merge(base: dict[str, Any], override: dict[str, Any], path: str = "") -> None:
    for key, value in override.items():
        where = f"{path}{key}"
        if key not in base:
            raise ValueError(f"Unknown config option: '{where}'")
        if isinstance(base[key], dict):
            if not isinstance(value, dict):
                raise ValueError(f"Config option '{where}' must be a mapping")
            _merge(base[key], value, f"{where}.")
        else:
            base[key] = value


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Return the effective config. Unknown keys raise ValueError (catches typos)."""
    config = copy.deepcopy(DEFAULT_CONFIG)
    if path is not None:
        with open(path, encoding="utf-8") as fh:
            user = yaml.safe_load(fh) or {}
        if not isinstance(user, dict):
            raise ValueError("Config file must contain a YAML mapping at the top level")
        _merge(config, user)
    return config
