import importlib.util
import pathlib
import sys
import unittest
from unittest.mock import patch


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class SyncBackendKeyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module("sync_supabase_mod", src_dir / "maintain" / "sync.py")

    def test_resolve_supabase_url_prefers_backend_key(self):
        cfg = {
            "source_backends": {
                "biorxiv": {
                    "url": "https://biorxiv.example.supabase.co",
                    "papers_table": "papers",
                }
            }
        }
        with patch.object(self.mod, "load_config", return_value=cfg):
            url = self.mod.resolve_supabase_url("", "biorxiv")
        self.assertEqual(url, "https://biorxiv.example.supabase.co")

    def test_resolve_papers_table_prefers_backend_key(self):
        cfg = {
            "source_backends": {
                "biorxiv": {
                    "url": "https://biorxiv.example.supabase.co",
                    "papers_table": "papers",
                }
            }
        }
        with patch.object(self.mod, "load_config", return_value=cfg):
            table = self.mod.resolve_papers_table("", "biorxiv")
        self.assertEqual(table, "papers")

    def test_resolve_default_raw_path_uses_biorxiv_prefix(self):
        path = self.mod.resolve_default_raw_path("20260318", "biorxiv")
        self.assertTrue(path.endswith("archive/20260318/raw/biorxiv_papers_20260318.json"))


if __name__ == "__main__":
    unittest.main()
