import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from legacy_config_fields import read_note


class LegacyConfigFieldsTest(unittest.TestCase):
    def test_read_note_prefers_current_field(self):
        self.assertEqual(read_note({"note": "current"}), "current")

    def test_read_note_falls_back_to_legacy_keys(self):
        self.assertEqual(read_note({"logic_cn": "legacy"}), "legacy")
        self.assertEqual(read_note({"keyword_cn": "legacy keyword"}), "legacy keyword")


if __name__ == "__main__":
    unittest.main()
