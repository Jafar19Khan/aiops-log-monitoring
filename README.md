# AIOps — Automated Log Monitoring & Incident Remediation

A small, self-contained automated log monitoring and incident remediation toolkit for DevOps
use: it parses application/system logs,
detects anomalous time windows (a threshold rule **and** an Isolation Forest model), groups
them into incidents with a root-cause hint, and — only if you enable it — runs a safe,
allow-listed remediation command.

## Why this exists

Most "AIOps demo" scripts on GitHub run on random synthetic data with no real signal, so
their anomaly detection can't be trusted. This project instead:

- ships a **deterministic incident simulator** (`aiops generate-logs`) that injects realistic
  incident patterns (a database outage, a disk-full event) into normal traffic, so detection
  logic can be tested against something with a known right answer;
- uses **message templating** (numbers/IPs collapsed) so "timeout after 30s" and "timeout
  after 45s" count as the same kind of event;
- treats remediation as **allow-listed, validated, dry-run-by-default** — no raw shell
  strings, no `rm -rf`.

## Install

```bash
git clone <this-repo-url>
cd aiops-log-monitoring
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install -e .          # gives you the `aiops` command
```

## Quick start

```bash
# 1. Generate a sample log file with two injected incidents
aiops generate-logs --output data/sample_logs.txt

# 2. Analyze it
aiops analyze --logs data/sample_logs.txt --config config/config.yaml --output reports
```

This prints a text report and writes `reports/incidents.json` and `reports/windows.csv`.
Add `--json` for machine-readable output, and `--fail-on-incident` to make the command exit
non-zero when an incident is found (useful as a CI gate).

### Sample output

```
Incident #1 [CRITICAL]  2026-06-27 10:30:00 -> 10:35:00
  events          : 5 critical, 69 error, 9 warning
  root cause hint : Database connection pool exhausted: active=<NUM> max=<NUM>
  first signal at : 10:29:40
  top messages    :
      29x API request failed: POST /order status=<NUM> latency=<NUM>ms
      27x Database connection failed: timeout after <NUM>s
      12x Unhandled exception in payment module
  suggested fixes :
    restart_service: systemctl restart postgresql
    scale_deployment: kubectl scale deployment/payment-api --replicas=5
```

### Live host metrics

```bash
aiops metrics --config config/config.yaml --samples 10 --interval 5
```

Samples CPU/memory/disk with `psutil`, warns on threshold breaches, and forecasts whether a
rising trend will cross the threshold in the next few samples.

## How detection works

1. **Parse** (`aiops/parser.py`) — `YYYY-MM-DD HH:MM:SS LEVEL message` lines are parsed,
   time-sorted, and each message is reduced to a *template* (numbers/IPs replaced).
2. **Feature windows** (`aiops/features.py`) — logs are bucketed into fixed windows (default
   1 minute); each window gets counts per level, error ratio, and unique-template count.
   Empty windows are kept as zero rows so gaps in traffic aren't silently skipped.
3. **Detect** (`aiops/detector.py`) — a window is anomalous if it crosses a configurable
   error-count threshold, **or** an Isolation Forest (fit on the window features) calls it
   unusual *and* it has a minimum number of actual errors — this stops the model flagging
   quiet periods just because traffic dropped.
4. **Group into incidents** (`aiops/incidents.py`) — adjacent anomalous windows are merged;
   the root-cause hint is the earliest message template that is both new (rare outside the
   incident) and repeating (recurs inside it) — looking slightly *before* the incident window
   too, since causes often precede the error spike.
5. **Remediation** (`aiops/remediation.py`) — incident text is matched against regex rules
   from `config.yaml`. Only three actions exist (`restart_service`, `scale_deployment`,
   `vacuum_journal`), each built as a fixed argv list with every parameter validated by a
   strict pattern — never a shell string. **Dry-run is the default**; pass `--execute` to
   actually run commands, and the tool waits, then re-checks host metrics afterward.

## Configuration

All settings live in `config/config.yaml` (see comments there); anything you omit falls back
to a built-in default, and an unknown key raises an error instead of being silently ignored —
this catches typos early.

## Project layout

```
src/aiops/        importable package (parser, features, detector, incidents,
                  remediation, metrics, simulate, pipeline, report, cli, config)
tests/            unit tests (stdlib unittest, also pytest-compatible)
config/config.yaml  default configuration
.github/workflows/ci.yml  lint + test + smoke-test on every push/PR
Dockerfile        containerized CLI
```

## Running tests

```bash
pip install -r requirements-dev.txt
PYTHONPATH=src pytest -v
```

## Docker

```bash
docker build -t aiops .
docker run --rm -v "$PWD/data:/app/data" -v "$PWD/reports:/app/reports" \
  aiops analyze --logs data/sample_logs.txt --config config/config.yaml --output reports
```

## Safety notes

- Remediation only ever executes one of three allow-listed commands, each parameter-validated;
  there is no shell interpolation anywhere in the codebase.
- `dry_run: true` in `config.yaml` is the default — review the proposed commands before
  flipping it, or before passing `--execute` on the CLI.
- This is a reference/learning implementation, not a production incident-response system —
  review and adapt the remediation rules to your own infrastructure before relying on them.

## License

MIT — see [LICENSE](LICENSE).
