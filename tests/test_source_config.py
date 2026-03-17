import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.source_config import (
    ARXIV_SOURCE_KEY,
    get_source_backend,
    migrate_source_config_inplace,
    resolve_source_backends,
)


class SourceConfigMigrationTest(unittest.TestCase):
    def test_migrate_fills_missing_paper_sources_and_source_backends(self):
        cfg = {
            "supabase": {
                "enabled": True,
                "url": "https://example.supabase.co",
                "anon_key": "anon",
                "papers_table": "arxiv_papers",
                "use_bm25_rpc": True,
                "use_vector_rpc": True,
            },
            "subscriptions": {
                "intent_profiles": [
                    {
                        "tag": "AHD",
                        "enabled": True,
                        "keywords": [{"keyword": "test", "query": "test"}],
                    }
                ]
            },
        }
        changed, notes = migrate_source_config_inplace(cfg)
        self.assertTrue(changed)
        self.assertTrue(notes)
        self.assertEqual(cfg["subscriptions"]["intent_profiles"][0]["paper_sources"], [ARXIV_SOURCE_KEY])
        self.assertIn("source_backends", cfg)
        self.assertIn(ARXIV_SOURCE_KEY, cfg["source_backends"])

    def test_migrate_rejects_empty_paper_sources(self):
        cfg = {
            "subscriptions": {
                "intent_profiles": [
                    {
                        "tag": "BAD",
                        "enabled": True,
                        "paper_sources": [],
                        "keywords": [{"keyword": "test", "query": "test"}],
                    }
                ]
            }
        }
        with self.assertRaises(ValueError):
            migrate_source_config_inplace(cfg)

    def test_resolve_source_backends_prefers_new_shape(self):
        cfg = {
            "source_backends": {
                "arxiv": {
                    "enabled": True,
                    "url": "https://new.supabase.co",
                    "anon_key": "new-key",
                    "papers_table": "papers",
                }
            },
            "supabase": {
                "enabled": True,
                "url": "https://legacy.supabase.co",
                "anon_key": "legacy-key",
            },
        }
        backends = resolve_source_backends(cfg)
        self.assertEqual(backends["arxiv"]["url"], "https://new.supabase.co")
        self.assertEqual(get_source_backend(cfg, "arxiv")["anon_key"], "new-key")


if __name__ == "__main__":
    unittest.main()
