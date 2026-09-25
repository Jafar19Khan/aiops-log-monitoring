import unittest

from aiops.config import load_config
from aiops.pipeline import analyze_parsed
from aiops.parser import parse_lines
from aiops.simulate import generate_logs
from datetime import datetime


class TestIncidentsOnSimulatedLogs(unittest.TestCase):
    def test_two_injected_incidents_are_detected(self):
        lines = generate_logs(datetime(2026, 1, 1, 9, 0, 0), minutes=90, seed=1)
        result = analyze_parsed(parse_lines(lines), load_config())
        self.assertGreaterEqual(len(result.incidents), 2)
        severities = {i.severity for i in result.incidents}
        self.assertIn("CRITICAL", severities)

    def test_root_cause_mentions_database_for_db_incident(self):
        lines = generate_logs(datetime(2026, 1, 1, 9, 0, 0), minutes=90, seed=1)
        result = analyze_parsed(parse_lines(lines), load_config())
        causes = " ".join(i.root_cause for i in result.incidents).lower()
        self.assertIn("database", causes)

    def test_no_incidents_without_injection(self):
        lines = generate_logs(datetime(2026, 1, 1, 9, 0, 0), minutes=60, seed=1,
                               with_incidents=False)
        result = analyze_parsed(parse_lines(lines), load_config())
        self.assertEqual(len(result.incidents), 0)


if __name__ == "__main__":
    unittest.main()
