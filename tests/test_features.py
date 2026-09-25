import unittest

from aiops.features import build_window_features
from aiops.parser import parse_lines


class TestFeatures(unittest.TestCase):
    def test_empty_windows_are_kept_with_zero_counts(self):
        lines = [
            "2026-06-27 10:00:00 INFO a",
            "2026-06-27 10:02:00 ERROR b",  # 10:01 window has no events at all
        ]
        frame = parse_lines(lines).frame
        feats = build_window_features(frame, "1min")
        self.assertEqual(len(feats), 3)
        self.assertEqual(feats.loc[feats.index[1], "total"], 0)

    def test_error_ratio(self):
        lines = [
            "2026-06-27 10:00:00 INFO a",
            "2026-06-27 10:00:01 ERROR b",
            "2026-06-27 10:00:02 ERROR c",
            "2026-06-27 10:00:03 INFO d",
        ]
        feats = build_window_features(parse_lines(lines).frame, "1min")
        self.assertAlmostEqual(feats.iloc[0]["error_ratio"], 0.5)


if __name__ == "__main__":
    unittest.main()
