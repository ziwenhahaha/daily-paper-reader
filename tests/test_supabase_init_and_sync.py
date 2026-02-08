import importlib.util
import os
import pathlib
import tempfile
import time
import unittest


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class SupabaseInitAndSyncTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        try:
            cls.init_mod = _load_module(
                "init_supabase_mod",
                src_dir / "1.3.init_supabase_from_arxiv.py",
            )
            cls.sync_mod = _load_module(
                "sync_supabase_mod",
                src_dir / "1.2.sync_supabase_public.py",
            )
        except Exception as exc:
            raise unittest.SkipTest(f"依赖不足，跳过 Supabase 初始化相关测试: {exc}")

    def test_resolve_date_token_long_range(self):
        token = self.init_mod.resolve_date_token("", 30)
        self.assertRegex(token, r"^\d{8}-\d{8}$")

    def test_resolve_date_token_manual(self):
        token = self.init_mod.resolve_date_token("20260201-20260207", 30)
        self.assertEqual(token, "20260201-20260207")

    def test_find_latest_raw_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            p1 = root / "archive" / "20260201" / "raw"
            p2 = root / "archive" / "20260201-20260207" / "raw"
            p1.mkdir(parents=True, exist_ok=True)
            p2.mkdir(parents=True, exist_ok=True)
            f1 = p1 / "arxiv_papers_20260201.json"
            f2 = p2 / "arxiv_papers_20260201-20260207.json"
            f1.write_text("[]", encoding="utf-8")
            now = time.time()
            f1_ts = now - 5
            f2_ts = now
            os.utime(f1, (f1_ts, f1_ts))
            f2.write_text("[]", encoding="utf-8")
            os.utime(f2, (f2_ts, f2_ts))
            latest = self.init_mod.find_latest_raw_file(str(root))
            self.assertTrue(latest.endswith("arxiv_papers_20260201-20260207.json"))

    def test_deduplicate_rows_by_id(self):
        rows = [
            {"id": "A", "title": "x"},
            {"id": "a", "title": "x2"},
            {"id": "B", "title": "y"},
            {"id": "", "title": "z"},
            {"title": "n/a"},
        ]
        deduped, dup_cnt = self.sync_mod.deduplicate_rows_by_id(rows)
        self.assertEqual(dup_cnt, 1)
        self.assertEqual(len(deduped), 2)
        ids = {x.get("id") for x in deduped}
        self.assertEqual(ids, {"A", "B"})


if __name__ == "__main__":
    unittest.main()
