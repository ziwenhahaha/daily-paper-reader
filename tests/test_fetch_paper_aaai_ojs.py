import importlib.util
import pathlib
import sys
import unittest


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class FetchPaperAAAIOJSTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module(
            "fetch_aaai_ojs_mod",
            src_dir / "maintain" / "fetchers" / "fetch_aaai_ojs.py",
        )

    def test_extract_issue_year(self):
        self.assertEqual(self.mod.extract_issue_year("AAAI-25 Technical Tracks 3"), 2025)
        self.assertIsNone(self.mod.extract_issue_year("IAAI-25 Student Abstracts"))

    def test_is_target_issue_title(self):
        self.assertTrue(self.mod.is_target_issue_title("AAAI-24 Technical Tracks 15", [2023, 2024, 2025]))
        self.assertFalse(self.mod.is_target_issue_title("IAAI-25 Student Abstracts", [2025]))

    def test_normalize_date_to_iso(self):
        self.assertEqual(
            self.mod._normalize_date_to_iso("2025-04-11"),
            "2025-04-11T00:00:00+00:00",
        )
        self.assertEqual(
            self.mod._normalize_date_to_iso("2025/04/11"),
            "2025-04-11T00:00:00+00:00",
        )

    def test_build_source_label(self):
        self.assertEqual(self.mod.build_source_label(2025), "AAAI-2025-Accepted")


if __name__ == "__main__":
    unittest.main()
