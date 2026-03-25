import json
import pathlib
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
MAINTAIN_DIR = ROOT / "src" / "maintain"
if str(MAINTAIN_DIR) not in sys.path:
    sys.path.insert(0, str(MAINTAIN_DIR))

import common  # type: ignore


class MaintainCommonTest(unittest.TestCase):
    def test_default_raw_path(self):
        path = common.default_raw_path("aaai_papers", "20260325")
        self.assertTrue(path.endswith("archive/20260325/raw/aaai_papers_20260325.json"))

    def test_count_raw_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "rows.json"
            path.write_text(json.dumps([{"id": "a"}, {"id": "b"}]), encoding="utf-8")
            self.assertEqual(common.count_raw_rows(str(path)), 2)


if __name__ == "__main__":
    unittest.main()
