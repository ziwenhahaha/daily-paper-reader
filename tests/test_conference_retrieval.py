import importlib.util
import pathlib
import sys
import unittest


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


class ConferenceRetrievalTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module("conference_retrieval_mod", src_dir / "conference_retrieval.py")

    def test_parse_conferences_supports_nips_alias_and_dedupes(self):
        self.assertEqual(self.mod.parse_conferences("NIPS,ICML,neurips"), ["neurips", "icml"])

    def test_parse_years_keeps_user_order_and_dedupes(self):
        self.assertEqual(self.mod.parse_years("2025,2024,2025"), [2025, 2024])

    def test_year_window_uses_calendar_year(self):
        start, end = self.mod.year_window(2025)
        self.assertEqual(start.isoformat(), "2025-01-01T00:00:00+00:00")
        self.assertEqual(end.isoformat(), "2026-01-01T00:00:00+00:00")

    def test_clone_queries_for_conference_does_not_mutate_original(self):
        queries = [{"query_text": "test", "paper_sources": ["arxiv"]}]
        cloned = self.mod.clone_queries_for_conference(queries, "icml")
        self.assertEqual(cloned[0]["paper_sources"], ["icml"])
        self.assertEqual(queries[0]["paper_sources"], ["arxiv"])

    def test_resolve_conference_backend_falls_back_to_legacy_supabase(self):
        backend = self.mod.resolve_conference_backend(
            {
                "supabase": {
                    "url": "https://example.supabase.co",
                    "anon_key": "anon",
                    "schema": "public",
                }
            },
            "icml",
        )
        self.assertEqual(backend["url"], "https://example.supabase.co")
        self.assertEqual(backend["papers_table"], "icml_openreview_papers")
        self.assertEqual(backend["bm25_rpc"], "match_icml_openreview_papers_bm25")
        self.assertEqual(backend["vector_rpc_exact"], "match_icml_openreview_papers_exact")

    def test_save_result_writes_only_tagged_papers(self):
        paper = self.mod.PaperHit(id="p1", title="Paper", pdf_url="https://openreview.net/pdf?id=p1", best_score=1.0)
        paper.tags.add("query:test")
        result = {
            "papers": {"p1": paper, "p2": self.mod.PaperHit(id="p2", title="No tag")},
            "queries": [{"query_text": "test", "sim_scores": {"p1": {"score": 1.0, "rank": 1}}}],
            "total_rpc_hits": 2,
        }
        path = pathlib.Path(self.mod.ROOT_DIR) / "tmp-test-conference-retrieval.json"
        try:
            self.mod.save_result(result, path, mode="bm25", top_k=1, conferences=["icml"], years=[2025])
            payload = __import__("json").loads(path.read_text(encoding="utf-8"))
            self.assertEqual(len(payload["papers"]), 1)
            self.assertEqual(payload["papers"][0]["pdf_url"], "https://openreview.net/pdf?id=p1")
            self.assertEqual(payload["papers"][0]["tags"], ["query:test"])
            self.assertEqual(payload["retrieval"]["mode"], "supabase_bm25")
        finally:
            if path.exists():
                path.unlink()


if __name__ == "__main__":
    unittest.main()
