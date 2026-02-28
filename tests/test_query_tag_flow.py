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


class QueryTagFlowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.refine_mod = _load_module("llm_refine_mod", src_dir / "4.llm_refine_papers.py")
        cls.select_mod = _load_module("select_mod", src_dir / "5.select_papers.py")

    def test_build_user_requirements_keep_query_tag(self):
        config = {
            "subscriptions": {
                "intent_profiles": [
                    {
                        "id": "p1",
                        "tag": "SR",
                        "enabled": True,
                        "keywords": [
                            {
                                "id": "q1",
                                "keyword": "Symbolic Regression",
                                "query": "symbolic regression with rl",
                                "enabled": True,
                            },
                        ],
                    }
                ]
            }
        }
        reqs = self.refine_mod.build_user_requirements(config, [])
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["tag"], "query:sr")
        self.assertEqual(reqs[0]["id"], "req-1")

    def test_build_user_requirements_include_intent_queries(self):
        config = {
            "subscriptions": {
                "schema_migration": {"stage": "A"},
                "intent_profiles": [
                    {
                        "id": "p1",
                        "tag": "SR",
                        "keywords": [
                            {"keyword": "Symbolic Regression", "query": "symbolic regression", "enabled": True},
                        ],
                        "intent_queries": [
                            {"query": "symbolic regression with reinforcement learning", "enabled": True},
                            {"query": "equation discovery for physical systems", "enabled": True},
                        ],
                    }
                ]
            }
        }
        reqs = self.refine_mod.build_user_requirements(config, [])
        self.assertEqual(len(reqs), 3)
        self.assertEqual(reqs[0]["tag"], "query:sr")
        self.assertTrue(reqs[1]["tag"].startswith("query:sr"))
        self.assertTrue(reqs[2]["tag"].startswith("query:sr"))
        req_texts = [r["query"] for r in reqs]
        self.assertIn("symbolic regression with reinforcement learning", req_texts)
        self.assertIn("equation discovery for physical systems", req_texts)

    def test_build_scored_papers_fallback_match_tag(self):
        papers = [{"id": "p-1", "title": "t", "abstract": "a"}]
        llm_ranked = [
            {
                "paper_id": "p-1",
                "score": 8.8,
                "evidence_cn": "相关",
                "tldr_cn": "摘要",
                "tags": [],
                "matched_query_tag": "query:sr-rl",
                "matched_query_text": "symbolic regression with reinforcement learning",
                "matched_requirement_id": "req-2",
            }
        ]
        out = self.select_mod.build_scored_papers(papers, llm_ranked)
        self.assertEqual(len(out), 1)
        self.assertIn("query:sr-rl", out[0].get("llm_tags") or [])
        self.assertEqual(out[0].get("matched_requirement_id"), "req-2")


if __name__ == "__main__":
    unittest.main()
