import unittest

from aiops.remediation import build_command, execute_actions, plan_actions


class FakeIncident:
    def __init__(self, severity, root_cause, top_templates=()):
        self.severity = severity
        self.root_cause = root_cause
        self.top_templates = list(top_templates)


class TestBuildCommand(unittest.TestCase):
    def test_valid_service_name(self):
        cmd = build_command("restart_service", {"service": "postgresql"})
        self.assertEqual(cmd, ["systemctl", "restart", "postgresql"])

    def test_rejects_shell_injection_attempt(self):
        with self.assertRaises(ValueError):
            build_command("restart_service", {"service": "postgresql; rm -rf /"})

    def test_rejects_unknown_action(self):
        with self.assertRaises(ValueError):
            build_command("delete_everything", {})

    def test_scale_replica_bounds(self):
        with self.assertRaises(ValueError):
            build_command("scale_deployment", {"deployment": "api", "replicas": 999})


class TestPlanActions(unittest.TestCase):
    def setUp(self):
        self.rules = [{"pattern": "Database connection", "action": "restart_service",
                        "params": {"service": "postgresql"}}]

    def test_matches_root_cause(self):
        incident = FakeIncident("ERROR", "Database connection failed: timeout after <NUM>s")
        actions = plan_actions(incident, self.rules)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].command, ["systemctl", "restart", "postgresql"])

    def test_warning_only_incident_is_not_actionable(self):
        incident = FakeIncident("WARNING", "Database connection failed: timeout after <NUM>s")
        self.assertEqual(plan_actions(incident, self.rules), [])

    def test_no_match_no_actions(self):
        incident = FakeIncident("ERROR", "totally unrelated thing")
        self.assertEqual(plan_actions(incident, self.rules), [])


class TestExecuteActions(unittest.TestCase):
    def test_dry_run_does_not_execute(self):
        incident = FakeIncident("ERROR", "Database connection failed")
        actions = plan_actions(incident, [{"pattern": "Database", "action": "restart_service",
                                            "params": {"service": "postgresql"}}])
        results = execute_actions(actions, dry_run=True)
        self.assertFalse(results[0].executed)


if __name__ == "__main__":
    unittest.main()
