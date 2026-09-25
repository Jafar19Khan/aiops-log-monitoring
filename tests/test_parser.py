import unittest

from aiops.parser import parse_lines, to_template


class TestTemplate(unittest.TestCase):
    def test_numbers_and_ips_collapsed(self):
        a = to_template("Database timeout after 30s from 10.0.1.5")
        b = to_template("Database timeout after 45s from 10.0.9.200")
        self.assertEqual(a, b)


class TestParseLines(unittest.TestCase):
    def test_valid_lines_parsed_and_sorted(self):
        lines = [
            "2026-06-27 10:00:05 INFO second",
            "2026-06-27 10:00:01 ERROR first",
        ]
        result = parse_lines(lines)
        self.assertEqual(result.total_lines, 2)
        self.assertEqual(result.skipped_lines, 0)
        self.assertEqual(list(result.frame["message"]), ["first", "second"])

    def test_malformed_lines_are_counted_not_dropped_silently(self):
        lines = ["not a log line", "", "2026-06-27 10:00:01 INFO ok"]
        result = parse_lines(lines)
        self.assertEqual(result.total_lines, 2)  # blank line not counted
        self.assertEqual(result.skipped_lines, 1)
        self.assertEqual(len(result.frame), 1)

    def test_bad_level_is_skipped(self):
        result = parse_lines(["2026-06-27 10:00:01 NOTALEVEL message"])
        self.assertEqual(result.skipped_lines, 1)


if __name__ == "__main__":
    unittest.main()
