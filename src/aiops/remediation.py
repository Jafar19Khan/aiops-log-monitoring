"""Safe auto-remediation.

Design rules:
* Only actions in ``ALLOWED_ACTIONS`` exist; each maps to a fixed argv list (no shell).
* Every parameter is validated against a strict pattern before it reaches a command.
* Dry-run is the default. Real execution needs ``--execute`` (or ``dry_run: false``).
"""

from __future__ import annotations

import logging
import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any, Iterable

logger = logging.getLogger(__name__)

ALLOWED_ACTIONS = ("restart_service", "scale_deployment", "vacuum_journal")

_SERVICE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,63}$")
_K8S_NAME_RE = re.compile(r"^[a-z0-9]([-a-z0-9.]{0,251}[a-z0-9])?$")
_SIZE_RE = re.compile(r"^\d{1,5}[KMG]$")
_ACTIONABLE_SEVERITIES = {"ERROR", "CRITICAL"}


@dataclass(frozen=True)
class Action:
    name: str
    params: dict[str, Any]
    command: list[str]
    matched_rule: str


@dataclass
class ActionResult:
    action: Action
    executed: bool
    returncode: int | None
    output: str


def build_command(name: str, params: dict[str, Any]) -> list[str]:
    """Validate ``params`` and return the argv list for ``name``."""
    if name not in ALLOWED_ACTIONS:
        raise ValueError(f"Action '{name}' is not allowed. Allowed: {', '.join(ALLOWED_ACTIONS)}")

    if name == "restart_service":
        service = str(params.get("service", ""))
        if not _SERVICE_RE.match(service):
            raise ValueError(f"Invalid service name: {service!r}")
        return ["systemctl", "restart", service]

    if name == "scale_deployment":
        deployment = str(params.get("deployment", ""))
        if not _K8S_NAME_RE.match(deployment):
            raise ValueError(f"Invalid deployment name: {deployment!r}")
        try:
            replicas = int(params.get("replicas"))
        except (TypeError, ValueError):
            raise ValueError("'replicas' must be an integer") from None
        if not 1 <= replicas <= 20:
            raise ValueError("'replicas' must be between 1 and 20")
        return ["kubectl", "scale", f"deployment/{deployment}", f"--replicas={replicas}"]

    size = str(params.get("max_size", ""))  # vacuum_journal
    if not _SIZE_RE.match(size):
        raise ValueError(f"Invalid max_size (use e.g. 200M): {size!r}")
    return ["journalctl", f"--vacuum-size={size}"]


def plan_actions(incident: Any, rules: Iterable[dict[str, Any]]) -> list[Action]:
    """Match config rules against an incident's root cause and top messages.

    Only ERROR/CRITICAL incidents are actionable: a warning-only blip never triggers a fix.
    """
    if incident.severity not in _ACTIONABLE_SEVERITIES:
        return []

    texts = [incident.root_cause] + [template for template, _ in incident.top_templates]
    actions: list[Action] = []
    seen: set[tuple[str, ...]] = set()
    for rule in rules:
        if "pattern" not in rule or "action" not in rule:
            raise ValueError("Each remediation rule needs 'pattern' and 'action'")
        regex = re.compile(rule["pattern"], re.IGNORECASE)
        if not any(regex.search(text) for text in texts):
            continue
        params = dict(rule.get("params") or {})
        command = build_command(rule["action"], params)
        if tuple(command) in seen:
            continue
        seen.add(tuple(command))
        actions.append(Action(rule["action"], params, command, rule["pattern"]))
    return actions


def execute_actions(
    actions: Iterable[Action], dry_run: bool = True, timeout: int = 30
) -> list[ActionResult]:
    results: list[ActionResult] = []
    for action in actions:
        command = build_command(action.name, action.params)  # re-validate right before running
        printable = shlex.join(command)
        if dry_run:
            logger.info("[dry-run] would run: %s", printable)
            results.append(ActionResult(action, False, None, "dry-run"))
            continue

        logger.warning("Executing: %s", printable)
        try:
            proc = subprocess.run(
                command, capture_output=True, text=True, timeout=timeout, check=False
            )
        except FileNotFoundError:
            results.append(ActionResult(action, False, 127, f"command not found: {command[0]}"))
        except subprocess.TimeoutExpired:
            results.append(ActionResult(action, True, 124, f"timed out after {timeout}s"))
        else:
            output = (proc.stdout + proc.stderr).strip()
            results.append(ActionResult(action, True, proc.returncode, output))
    return results
