"""Log parsing: raw text lines -> a tidy, time-sorted DataFrame."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
COLUMNS = ["timestamp", "level", "message", "template"]

LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+(?P<message>.+)$"
)

_IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_NUM = re.compile(r"\b\d+(?:\.\d+)?")


def to_template(message: str) -> str:
    """Collapse variable parts so similar messages share one template.

    "Database connection failed: timeout after 30s" and "... after 45s" become the same
    template, which lets us count *kinds* of events instead of unique strings.
    """
    message = _IP.sub("<IP>", message)
    return _NUM.sub("<NUM>", message)


@dataclass(frozen=True)
class ParseResult:
    frame: pd.DataFrame
    total_lines: int
    skipped_lines: int


def parse_lines(lines: Iterable[str]) -> ParseResult:
    """Parse ``YYYY-MM-DD HH:MM:SS LEVEL message`` lines.

    Blank lines are ignored. Lines that do not match are counted in ``skipped_lines``
    instead of being dropped silently.
    """
    rows = []
    total = 0
    skipped = 0
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        total += 1
        match = LOG_PATTERN.match(line)
        if match is None:
            skipped += 1
            continue
        message = match["message"]
        rows.append((match["timestamp"], match["level"], message, to_template(message)))

    frame = pd.DataFrame(rows, columns=COLUMNS)
    frame["timestamp"] = pd.to_datetime(
        frame["timestamp"], format="%Y-%m-%d %H:%M:%S", errors="coerce"
    )
    bad_dates = frame["timestamp"].isna()
    skipped += int(bad_dates.sum())
    frame = frame.loc[~bad_dates].sort_values("timestamp", kind="stable").reset_index(drop=True)
    return ParseResult(frame=frame, total_lines=total, skipped_lines=skipped)


def parse_file(path: str | Path) -> ParseResult:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return parse_lines(fh)
