"""Tests for the skip-fetch optimization in main.py.

When Supabase is fully configured as the retrieval backend (both BM25 and
vector RPCs enabled, prefer_supabase_read=true), Step 1 (全量数据拉取) can be
skipped because the downstream retrieval steps query Supabase directly.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure src/ is importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from main import should_skip_fetch  # noqa: E402


class ShouldSkipFetchTest(unittest.TestCase):
    """Unit tests for should_skip_fetch()."""

    FULL_SUPABASE_CONFIG = {
        "arxiv_paper_setting": {
            "prefer_supabase_read": True,
        },
        "supabase": {
            "enabled": True,
            "url": "https://example.supabase.co",
            "anon_key": "test-key",
            "use_bm25_rpc": True,
            "use_vector_rpc": True,
        },
    }

    def test_skip_when_fully_configured(self):
        """All Supabase retrieval features on → skip fetch."""
        self.assertTrue(should_skip_fetch(self.FULL_SUPABASE_CONFIG))

    def test_skip_when_source_backends_arxiv_fully_configured(self):
        cfg = {
            "arxiv_paper_setting": {"prefer_supabase_read": True},
            "source_backends": {
                "arxiv": {
                    "enabled": True,
                    "url": "https://example.supabase.co",
                    "anon_key": "test-key",
                    "use_bm25_rpc": True,
                    "use_vector_rpc": True,
                }
            },
        }
        self.assertTrue(should_skip_fetch(cfg))

    def test_no_skip_when_supabase_disabled(self):
        cfg = {
            "supabase": {
                "enabled": False,
                "url": "https://example.supabase.co",
                "anon_key": "test-key",
                "use_bm25_rpc": True,
                "use_vector_rpc": True,
            },
        }
        self.assertFalse(should_skip_fetch(cfg))

    def test_no_skip_when_bm25_rpc_disabled(self):
        cfg = {
            "arxiv_paper_setting": {"prefer_supabase_read": True},
            "supabase": {
                "enabled": True,
                "url": "https://example.supabase.co",
                "anon_key": "test-key",
                "use_bm25_rpc": False,
                "use_vector_rpc": True,
            },
        }
        self.assertFalse(should_skip_fetch(cfg))

    def test_no_skip_when_vector_rpc_disabled(self):
        cfg = {
            "arxiv_paper_setting": {"prefer_supabase_read": True},
            "supabase": {
                "enabled": True,
                "url": "https://example.supabase.co",
                "anon_key": "test-key",
                "use_bm25_rpc": True,
                "use_vector_rpc": False,
            },
        }
        self.assertFalse(should_skip_fetch(cfg))

    def test_no_skip_when_prefer_supabase_read_missing(self):
        cfg = {
            "arxiv_paper_setting": {},
            "supabase": {
                "enabled": True,
                "url": "https://example.supabase.co",
                "anon_key": "test-key",
                "use_bm25_rpc": True,
                "use_vector_rpc": True,
            },
        }
        self.assertFalse(should_skip_fetch(cfg))

    def test_no_skip_when_url_missing(self):
        cfg = {
            "arxiv_paper_setting": {"prefer_supabase_read": True},
            "supabase": {
                "enabled": True,
                "url": "",
                "anon_key": "test-key",
                "use_bm25_rpc": True,
                "use_vector_rpc": True,
            },
        }
        self.assertFalse(should_skip_fetch(cfg))

    def test_no_skip_when_anon_key_missing(self):
        cfg = {
            "arxiv_paper_setting": {"prefer_supabase_read": True},
            "supabase": {
                "enabled": True,
                "url": "https://example.supabase.co",
                "anon_key": "",
                "use_bm25_rpc": True,
                "use_vector_rpc": True,
            },
        }
        self.assertFalse(should_skip_fetch(cfg))

    def test_no_skip_when_empty_config(self):
        self.assertFalse(should_skip_fetch({}))

    def test_no_skip_when_none_config(self):
        """When config=None, should_skip_fetch loads from file; mock to empty."""
        with patch("main._load_full_config", return_value={}):
            self.assertFalse(should_skip_fetch())


if __name__ == "__main__":
    unittest.main()
