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


class FetchChemRxivTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module(
            "fetch_chemrxiv_mod",
            src_dir / "maintain" / "fetchers" / "fetch_chemrxiv.py",
        )

    def test_normalize_chemrxiv_record(self):
        raw = {
            "id": "abc123",
            "doi": "10.26434/chemrxiv-2026-xyz.v1",
            "title": "Chem Test",
            "abstract": "<p>Hello <b>world</b></p>",
            "authors": [
                {"firstName": "Ada", "lastName": "Lovelace"},
                {"firstName": "Alan", "lastName": "Turing"},
            ],
            "categories": [{"name": "Chemical Biology"}],
            "subject": "General Chemistry",
            "publishedDate": "2026-03-20T00:00:00.000Z",
            "version": 1,
            "asset": {"original": {"url": "https://example.org/paper.pdf"}},
        }
        normalized = self.mod.normalize_chemrxiv_record(raw)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["id"], "chemrxiv-abc123")
        self.assertEqual(normalized["source"], "chemrxiv")
        self.assertEqual(normalized["source_paper_id"], "abc123")
        self.assertEqual(normalized["primary_category"], "Chemical Biology")
        self.assertEqual(normalized["categories"], ["Chemical Biology", "General Chemistry"])
        self.assertEqual(normalized["abstract"], "Hello world")
        self.assertEqual(len(normalized["authors"]), 2)


if __name__ == "__main__":
    unittest.main()
