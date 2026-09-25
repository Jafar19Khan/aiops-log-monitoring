import unittest

from aiops.config import load_config


class TestConfig(unittest.TestCase):
    def test_defaults_load(self):
        cfg = load_config()
        self.assertEqual(cfg["detection"]["window"], "1min")

    def test_unknown_top_level_key_rejected(self):
        import os
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
            f.write("not_a_section:\n  x: 1\n")
            path = f.name
        try:
            with self.assertRaises(ValueError):
                load_config(path)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
