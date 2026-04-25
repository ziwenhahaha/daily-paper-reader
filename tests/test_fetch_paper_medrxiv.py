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


class FetchMedRxivTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module("fetch_medrxiv_mod", src_dir / "maintain" / "fetchers" / "fetch_medrxiv.py")

    def test_build_medrxiv_paper_id_is_path_safe(self):
        paper_id = self.mod.build_medrxiv_paper_id("10.1101/2024.01.11.575298", "3")
        self.assertEqual(paper_id, "medrxiv-10-1101-2024-01-11-575298-v3")

    def test_normalize_medrxiv_record(self):
        raw = {
            "doi": "10.1101/859942",
            "version": "4",
            "title": "Prioritized neural processing",
            "authors": "El Zein, M.; Mennella, R.; Sequestro, M.;",
            "abstract": "Test abstract",
            "date": "2024-01-02",
            "category": "neuroscience",
        }
        normalized = self.mod.normalize_medrxiv_record(raw)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["source"], "medrxiv")
        self.assertEqual(normalized["source_paper_id"], "10.1101/859942")
        self.assertEqual(normalized["primary_category"], "neuroscience")
        self.assertEqual(normalized["categories"], ["neuroscience"])
        self.assertIn("medrxiv.org", normalized["link"])
        self.assertEqual(len(normalized["authors"]), 3)


if __name__ == "__main__":
    unittest.main()
