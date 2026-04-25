import importlib.util
import pathlib
import sys
import tempfile
import unittest
import json

import numpy as np
import yaml


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class QueryEmbeddingCacheTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        sys.path.insert(0, str(src_dir))
        cls.mod = _load_module(
            "embedding_cache_mod",
            src_dir / "2.2.retrieval_papers_embedding.py",
        )

    def test_build_query_embedding_hash_is_stable(self):
        h1 = self.mod.build_query_embedding_hash("BAAI/bge-small-en-v1.5", "symbolic regression")
        h2 = self.mod.build_query_embedding_hash("BAAI/bge-small-en-v1.5", "symbolic regression")
        h3 = self.mod.build_query_embedding_hash("BAAI/bge-small-en-v1.5", "equation discovery")
        self.assertEqual(h1, h2)
        self.assertNotEqual(h1, h3)

    def test_hydrate_query_embeddings_uses_per_item_cache_and_only_encodes_misses(self):
        cfg = {
            "subscriptions": {
                "intent_profiles": [
                    {
                        "tag": "SR",
                        "description": "desc",
                        "keywords": [
                            {
                                "keyword": "cached keyword",
                                "query": "cached query",
                                "embedding_cache": {},
                            }
                        ],
                        "intent_queries": [
                            {
                                "query": "missing query",
                            }
                        ],
                    }
                ]
            }
        }
        cached_hash = self.mod.build_query_embedding_hash("BAAI/bge-small-en-v1.5", "cached query")
        cfg["subscriptions"]["intent_profiles"][0]["keywords"][0]["embedding_cache"] = {
            "version": 1,
            "hash": cached_hash,
            "model": "BAAI/bge-small-en-v1.5",
            "query_text": "cached query",
            "prefixed_text": "query: cached query",
            "embedding_json": "[0.1,0.2,0.3]",
        }
        queries = [
            {
                "query_text": "cached query",
                "embedding_cache": cfg["subscriptions"]["intent_profiles"][0]["keywords"][0]["embedding_cache"],
                "cache_ref": {"profile_index": 0, "item_kind": "keywords", "item_index": 0},
            },
            {
                "query_text": "missing query",
                "cache_ref": {"profile_index": 0, "item_kind": "intent_queries", "item_index": 0},
            },
        ]

        provider_calls = {"count": 0}

        class DummyModel:
            pass

        def fake_provider():
            provider_calls["count"] += 1
            return DummyModel()

        original_encode = self.mod.encode_queries

        def fake_encode(_model, texts, batch_size=8, max_length=None):
            self.assertEqual(texts, ["missing query"])
            return np.asarray([[0.4, 0.5, 0.6]], dtype=np.float32)

        self.mod.encode_queries = fake_encode
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / "config.yaml"
                stats = self.mod.hydrate_query_embeddings_from_config(
                    config=cfg,
                    queries=queries,
                    model_name="BAAI/bge-small-en-v1.5",
                    model_provider=fake_provider,
                    batch_size=8,
                    max_length=None,
                    config_path=str(path),
                )
                self.assertEqual(stats["hits"], 1)
                self.assertEqual(stats["misses"], 1)
                self.assertEqual(stats["written"], 1)
                self.assertEqual(provider_calls["count"], 1)
                self.assertTrue(isinstance(queries[0]["query_embedding"], np.ndarray))
                self.assertTrue(isinstance(queries[1]["query_embedding"], np.ndarray))
                cached_item = cfg["subscriptions"]["intent_profiles"][0]["keywords"][0]["embedding_cache"]
                missing_item = cfg["subscriptions"]["intent_profiles"][0]["intent_queries"][0]["embedding_cache"]
                self.assertEqual(cached_item["hash"], cached_hash)
                self.assertEqual(missing_item["query_text"], "missing query")
                self.assertEqual(
                    json.loads(missing_item["embedding_json"]),
                    [0.4, 0.5, 0.6],
                )
        finally:
            self.mod.encode_queries = original_encode

    def test_save_config_with_embedding_cache_keeps_embedding_json_on_one_line(self):
        cfg = {
            "subscriptions": {
                "intent_profiles": [
                    {
                        "tag": "SR",
                        "description": "desc",
                        "keywords": [
                            {
                                "keyword": "symbolic regression",
                                "query": "symbolic regression",
                                "embedding_cache": {
                                    "embedding_json": "[0.1,0.2,0.3]",
                                },
                            }
                        ],
                    }
                ]
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / "config.yaml"
            ok = self.mod.save_config_with_embedding_cache(cfg, str(path))
            self.assertTrue(ok)
            text = path.read_text(encoding="utf-8")
            self.assertRegex(text, r"embedding_json:\s*['\"]\[0\.1,0\.2,0\.3\]['\"]")
            loaded = yaml.safe_load(text)
            self.assertEqual(
                loaded["subscriptions"]["intent_profiles"][0]["keywords"][0]["embedding_cache"]["embedding_json"],
                "[0.1,0.2,0.3]",
            )

    def test_subscription_plan_emb_query_contains_cache_ref(self):
        from src.subscription_plan import build_pipeline_inputs

        cfg = {
            "subscriptions": {
                "intent_profiles": [
                    {
                        "tag": "SR",
                        "description": "desc",
                        "keywords": [
                            {
                                "keyword": "symbolic regression",
                                "query": "symbolic regression methods",
                                "embedding_cache": {"embedding_json": "[0.1,0.2,0.3]"},
                            }
                        ],
                        "intent_queries": [
                            {"query": "equation discovery"},
                        ],
                    }
                ]
            }
        }
        plan = build_pipeline_inputs(cfg)
        emb_queries = plan["embedding_queries"]
        self.assertEqual(len(emb_queries), 2)
        keyword_query = [x for x in emb_queries if x.get("type") == "keyword"][0]
        self.assertEqual(keyword_query["cache_ref"]["item_kind"], "keywords")
        self.assertEqual(keyword_query["cache_ref"]["item_index"], 0)
        self.assertEqual(
            keyword_query["embedding_cache"]["embedding_json"],
            "[0.1,0.2,0.3]",
        )

    def test_group_queries_after_hydrate_keeps_query_embedding_on_source_copies(self):
        queries = [
            {
                "query_text": "genetics",
                "paper_sources": ["biorxiv"],
                "cache_ref": {"profile_index": 0, "item_kind": "intent_queries", "item_index": 0},
            }
        ]
        cfg = {
            "subscriptions": {
                "intent_profiles": [
                    {
                        "tag": "GENE",
                        "description": "desc",
                        "intent_queries": [{"query": "genetics"}],
                    }
                ]
            }
        }

        original_encode = self.mod.encode_queries

        def fake_encode(_model, texts, batch_size=8, max_length=None):
            self.assertEqual(texts, ["genetics"])
            return np.asarray([[0.7, 0.8, 0.9]], dtype=np.float32)

        class DummyModel:
            pass

        self.mod.encode_queries = fake_encode
        try:
            with tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / "config.yaml"
                self.mod.hydrate_query_embeddings_from_config(
                    config=cfg,
                    queries=queries,
                    model_name="BAAI/bge-small-en-v1.5",
                    model_provider=lambda: DummyModel(),
                    batch_size=8,
                    max_length=None,
                    config_path=str(path),
                )
                grouped = self.mod.group_queries_by_source(queries)
                self.assertIn("biorxiv", grouped)
                copied_query = grouped["biorxiv"][0]
                self.assertTrue(isinstance(copied_query.get("query_embedding"), np.ndarray))
                np.testing.assert_allclose(copied_query["query_embedding"], np.asarray([0.7, 0.8, 0.9], dtype=np.float32))
        finally:
            self.mod.encode_queries = original_encode


if __name__ == "__main__":
    unittest.main()
