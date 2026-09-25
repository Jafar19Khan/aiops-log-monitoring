import unittest

import pandas as pd

from aiops.detector import DetectionConfig, detect_anomalous_windows


class TestDetector(unittest.TestCase):
    def test_rule_flags_high_error_window(self):
        idx = pd.date_range("2026-01-01", periods=3, freq="1min")
        feats = pd.DataFrame(
            {
                "total": [10, 10, 10],
                "warning": [0, 0, 0],
                "error": [0, 6, 0],
                "critical": [0, 0, 0],
                "bad": [0, 6, 0],
                "error_ratio": [0.0, 0.6, 0.0],
                "unique_templates": [2, 2, 2],
            },
            index=idx,
        )
        cfg = DetectionConfig(error_threshold=5)
        out = detect_anomalous_windows(feats, cfg)
        self.assertListEqual(list(out["rule_flag"]), [False, True, False])
        self.assertListEqual(list(out["anomaly"]), [False, True, False])

    def test_unknown_config_key_rejected(self):
        with self.assertRaises(ValueError):
            DetectionConfig.from_dict({"not_a_real_option": 1})


if __name__ == "__main__":
    unittest.main()
