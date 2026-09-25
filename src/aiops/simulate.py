"""Deterministic synthetic log generator.

Produces realistic baseline traffic plus two injected incidents (a database outage and a
disk-full event) so the detector, root-cause logic and CI can be exercised with no real logs.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

# (weight, level, message template)
_BASELINE = [
    (5.0, "INFO", "API request received: GET /products from {ip} status=200 latency={lat}ms"),
    (3.0, "INFO", "API request received: POST /order from {ip} status=201 latency={lat}ms"),
    (2.0, "INFO", "User {uid} logged in from {ip}"),
    (2.0, "INFO", "Transaction committed id={txn}"),
    (1.0, "INFO", "Cache hit ratio at {pct}%"),
    (2.0, "INFO", "Health check passed for service {svc}"),
    (0.25, "WARNING", "Slow query detected: {slow}ms"),
    (0.20, "WARNING", "Cache miss for user session {uid}"),
    (0.05, "ERROR", "Request failed with status=404 for GET /missing"),
]
_MIN_MINUTES = 30

Event = tuple[datetime, str, str]


def _values(rng: random.Random) -> dict:
    return {
        "ip": f"10.0.{rng.randint(0, 9)}.{rng.randint(1, 254)}",
        "lat": rng.randint(20, 180),
        "uid": rng.randint(1000, 9999),
        "txn": rng.randint(10000, 99999),
        "pct": rng.randint(85, 99),
        "svc": rng.choice(["auth", "catalog", "payment-api", "gateway"]),
        "slow": rng.randint(500, 1500),
    }


def _at(rng: random.Random, start: datetime, minute: int) -> datetime:
    return start + timedelta(minutes=minute, seconds=rng.randint(0, 59))


def _emit(events: list[Event], rng, start, minute, count, level, message) -> None:
    for _ in range(count):
        events.append((_at(rng, start, minute), level, message.format(**_values(rng))))


def _db_outage(rng: random.Random, start: datetime, events: list[Event]) -> None:
    """6 minutes: connection pool exhaustion -> DB timeouts -> API 500s -> service unhealthy."""
    for minute in range(6):
        if minute in (0, 1):
            _emit(events, rng, start, minute, 3, "WARNING",
                  "Database connection pool exhausted: active=100 max=100")
        if minute >= 1:
            _emit(events, rng, start, minute, rng.randint(4, 6), "ERROR",
                  "Database connection failed: timeout after 30s")
            _emit(events, rng, start, minute, rng.randint(4, 8), "ERROR",
                  "API request failed: POST /order status=500 latency=30001ms")
            _emit(events, rng, start, minute, rng.randint(2, 3), "ERROR",
                  "Unhandled exception in payment module")
        if 2 <= minute <= 4:
            _emit(events, rng, start, minute, 2, "WARNING", "CPU usage at {pct}%")
        if minute >= 3:
            _emit(events, rng, start, minute, rng.randint(1, 2), "CRITICAL",
                  "Service payment-api unhealthy: health check failed")


def _disk_full(rng: random.Random, start: datetime, events: list[Event]) -> None:
    """5 minutes: disk usage warnings -> write failures -> database goes read-only."""
    for minute in range(5):
        if minute <= 1:
            for _ in range(2):
                pct = 88 + minute * 4 + rng.randint(0, 3)
                events.append((_at(rng, start, minute), "WARNING",
                               f"Disk usage at {pct}% on /var/lib/postgresql"))
        if minute >= 1:
            _emit(events, rng, start, minute, 2, "WARNING", "Slow query detected: {slow}ms")
        if minute >= 2:
            _emit(events, rng, start, minute, rng.randint(3, 5), "ERROR",
                  "Disk write failure detected on /var/lib/postgresql")
            _emit(events, rng, start, minute, rng.randint(2, 4), "ERROR",
                  "Database write failed: no space left on device")
        if minute == 4:
            _emit(events, rng, start, minute, rng.randint(1, 2), "CRITICAL",
                  "Database switched to read-only mode")


def generate_logs(
    start: datetime, minutes: int = 90, seed: int = 42, with_incidents: bool = True
) -> list[str]:
    """Return chronologically ordered log lines."""
    if minutes < _MIN_MINUTES:
        raise ValueError(f"minutes must be at least {_MIN_MINUTES}")

    rng = random.Random(seed)
    weights = [w for w, _, _ in _BASELINE]
    events: list[Event] = []

    for minute in range(minutes):
        for _ in range(rng.randint(6, 10)):
            _, level, template = rng.choices(_BASELINE, weights=weights, k=1)[0]
            events.append((_at(rng, start, minute), level, template.format(**_values(rng))))

    if with_incidents:
        _db_outage(rng, start + timedelta(minutes=int(minutes * 0.33)), events)
        _disk_full(rng, start + timedelta(minutes=int(minutes * 0.70)), events)

    events.sort(key=lambda e: e[0])
    return [f"{ts:%Y-%m-%d %H:%M:%S} {level} {message}" for ts, level, message in events]
