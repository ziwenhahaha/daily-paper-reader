"""Tests for PostgreSQL statement timeout (57014) handling and date-filter
payload in Supabase RPC calls.

When the database returns a statement timeout error (HTTP 500, code 57014),
the client should:
1. Skip retries in _request_with_retries (retrying won't resolve a server-side limit)
2. Allow higher-level BM25 logic to shard large windows so queries can still return

To prevent the timeout in the first place, the client now passes
filter_published_start / filter_published_end in the RPC payload so the
database can narrow the search scope with a WHERE clause before computing
vector similarity.
"""

import importlib.util
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from supabase_source import (
    _build_date_filter_payload,
    _is_statement_timeout,
    _parse_content_range_total,
    _request_with_retries,
    count_papers_by_date_range,
    match_papers_by_embedding,
    match_papers_by_bm25,
)


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class IsStatementTimeoutTest(unittest.TestCase):
    """Tests for _is_statement_timeout helper."""

    def _make_response(self, text: str, status_code: int = 500) -> MagicMock:
        resp = MagicMock()
        resp.text = text
        resp.status_code = status_code
        return resp

    def test_detects_57014_in_json_body(self):
        body = '{"code":"57014","details":null,"hint":null,"message":"canceling statement due to statement timeout"}'
        resp = self._make_response(body)
        self.assertTrue(_is_statement_timeout(resp))

    def test_false_for_other_500_errors(self):
        body = '{"code":"XX000","message":"internal error"}'
        resp = self._make_response(body)
        self.assertFalse(_is_statement_timeout(resp))

    def test_false_for_empty_body(self):
        resp = self._make_response("")
        self.assertFalse(_is_statement_timeout(resp))

    def test_false_for_none_text(self):
        resp = MagicMock()
        resp.text = None
        self.assertFalse(_is_statement_timeout(resp))

    def test_false_for_57014_in_non_code_field(self):
        """Should not match 57014 appearing outside the 'code' field."""
        body = '{"code":"XX000","message":"error 57014 occurred"}'
        resp = self._make_response(body)
        self.assertFalse(_is_statement_timeout(resp))

    def test_false_for_non_json_body(self):
        resp = self._make_response("Internal Server Error")
        self.assertFalse(_is_statement_timeout(resp))


class RequestWithRetriesTimeoutTest(unittest.TestCase):
    """_request_with_retries should not retry on statement timeout."""

    @patch("supabase_source.requests.request")
    def test_no_retry_on_statement_timeout(self, mock_request):
        timeout_body = '{"code":"57014","message":"canceling statement due to statement timeout"}'
        resp = MagicMock()
        resp.status_code = 500
        resp.text = timeout_body
        mock_request.return_value = resp

        result = _request_with_retries(
            "POST",
            "https://example.com/rpc/test",
            headers={"apikey": "test"},
            timeout=20,
            retries=3,
        )
        # Should only be called once (no retries)
        self.assertEqual(mock_request.call_count, 1)
        self.assertEqual(result.status_code, 500)

    @patch("supabase_source.requests.request")
    def test_retries_on_non_timeout_500(self, mock_request):
        resp = MagicMock()
        resp.status_code = 500
        resp.text = '{"message":"internal error"}'
        mock_request.return_value = resp

        result = _request_with_retries(
            "POST",
            "https://example.com/rpc/test",
            headers={"apikey": "test"},
            timeout=20,
            retries=3,
            retry_wait_seconds=0,
        )
        # Should retry all 4 attempts (1 initial + 3 retries)
        self.assertEqual(mock_request.call_count, 4)
        self.assertEqual(result.status_code, 500)


class MatchPapersTimeoutTest(unittest.TestCase):
    """match_papers_by_embedding should propagate 57014 in error message."""

    @patch("supabase_source._request_with_retries")
    def test_error_message_contains_57014(self, mock_req):
        resp = MagicMock()
        resp.status_code = 500
        resp.text = '{"code":"57014","message":"canceling statement due to statement timeout"}'
        mock_req.return_value = resp

        rows, msg = match_papers_by_embedding(
            url="https://example.supabase.co",
            api_key="test-key",
            rpc_name="match_arxiv_papers_exact",
            query_embedding=[0.1, 0.2, 0.3],
            match_count=10,
        )
        self.assertEqual(rows, [])
        self.assertIn("57014", msg)


class BuildDateFilterPayloadTest(unittest.TestCase):
    """_build_date_filter_payload should produce ISO 8601 strings."""

    def test_both_dates(self):
        s = datetime(2026, 3, 2, tzinfo=timezone.utc)
        e = datetime(2026, 3, 12, tzinfo=timezone.utc)
        out = _build_date_filter_payload(s, e)
        self.assertIn("filter_published_start", out)
        self.assertIn("filter_published_end", out)
        self.assertTrue(out["filter_published_start"].startswith("2026-03-02"))
        self.assertTrue(out["filter_published_end"].startswith("2026-03-12"))

    def test_only_start(self):
        s = datetime(2026, 3, 2, tzinfo=timezone.utc)
        out = _build_date_filter_payload(s, None)
        self.assertIn("filter_published_start", out)
        self.assertNotIn("filter_published_end", out)

    def test_only_end(self):
        e = datetime(2026, 3, 12, tzinfo=timezone.utc)
        out = _build_date_filter_payload(None, e)
        self.assertNotIn("filter_published_start", out)
        self.assertIn("filter_published_end", out)

    def test_neither(self):
        out = _build_date_filter_payload(None, None)
        self.assertEqual(out, {})


class ParseContentRangeTotalTest(unittest.TestCase):
    def test_parse_standard_content_range(self):
        self.assertEqual(_parse_content_range_total("0-0/6707"), 6707)

    def test_parse_zero_content_range(self):
        self.assertEqual(_parse_content_range_total("*/0"), 0)

    def test_parse_missing_content_range(self):
        self.assertIsNone(_parse_content_range_total(""))


class CountPapersByDateRangeTest(unittest.TestCase):
    @patch("supabase_source._request_with_retries")
    def test_count_uses_content_range_total(self, mock_req):
        resp = MagicMock()
        resp.status_code = 206
        resp.headers = {"Content-Range": "0-0/10772"}
        mock_req.return_value = resp

        count, msg = count_papers_by_date_range(
            url="https://example.supabase.co",
            api_key="test-key",
            papers_table="arxiv_papers",
            start_dt=datetime(2026, 3, 2, tzinfo=timezone.utc),
            end_dt=datetime(2026, 3, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(count, 10772)
        self.assertIn("10772", msg)


class EmbeddingPayloadContainsDateFiltersTest(unittest.TestCase):
    """match_papers_by_embedding should include date filters in the payload."""

    @patch("supabase_source._request_with_retries")
    def test_payload_includes_date_filters(self, mock_req):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = []
        mock_req.return_value = resp

        s = datetime(2026, 3, 2, tzinfo=timezone.utc)
        e = datetime(2026, 3, 12, tzinfo=timezone.utc)
        match_papers_by_embedding(
            url="https://example.supabase.co",
            api_key="test-key",
            rpc_name="match_arxiv_papers_exact",
            query_embedding=[0.1, 0.2, 0.3],
            match_count=10,
            start_dt=s,
            end_dt=e,
        )
        call_kwargs = mock_req.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        self.assertIn("filter_published_start", payload)
        self.assertIn("filter_published_end", payload)
        self.assertIn("query_embedding", payload)
        self.assertIn("match_count", payload)

    @patch("supabase_source._request_with_retries")
    def test_payload_omits_date_filters_when_none(self, mock_req):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = []
        mock_req.return_value = resp

        match_papers_by_embedding(
            url="https://example.supabase.co",
            api_key="test-key",
            rpc_name="match_arxiv_papers",
            query_embedding=[0.1, 0.2, 0.3],
            match_count=10,
        )
        call_kwargs = mock_req.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        self.assertNotIn("filter_published_start", payload)
        self.assertNotIn("filter_published_end", payload)


class Bm25PayloadContainsDateFiltersTest(unittest.TestCase):
    """match_papers_by_bm25 should include date filters in the payload."""

    @patch("supabase_source._request_with_retries")
    def test_payload_includes_date_filters(self, mock_req):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = []
        mock_req.return_value = resp

        s = datetime(2026, 3, 2, tzinfo=timezone.utc)
        e = datetime(2026, 3, 12, tzinfo=timezone.utc)
        match_papers_by_bm25(
            url="https://example.supabase.co",
            api_key="test-key",
            rpc_name="match_arxiv_papers_bm25",
            query_text="attention mechanism",
            match_count=10,
            start_dt=s,
            end_dt=e,
        )
        call_kwargs = mock_req.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        self.assertIn("filter_published_start", payload)
        self.assertIn("filter_published_end", payload)
        self.assertIn("query_text", payload)
        self.assertIn("match_count", payload)


class SupabaseBm25ShardFallbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bm25_mod = _load_module(
            "bm25_mod_for_shards",
            ROOT / "src" / "2.1.retrieval_papers_bm25.py",
        )

    def test_split_supabase_time_window_uses_seven_day_shards(self):
        start_dt = datetime(2026, 3, 1, tzinfo=timezone.utc)
        end_dt = datetime(2026, 3, 31, tzinfo=timezone.utc)

        shards = self.bm25_mod.split_supabase_time_window(start_dt, end_dt)

        self.assertEqual(len(shards), 5)
        self.assertEqual(shards[0], (start_dt, datetime(2026, 3, 8, tzinfo=timezone.utc)))
        self.assertEqual(shards[1], (datetime(2026, 3, 8, tzinfo=timezone.utc), datetime(2026, 3, 15, tzinfo=timezone.utc)))
        self.assertEqual(shards[2], (datetime(2026, 3, 15, tzinfo=timezone.utc), datetime(2026, 3, 22, tzinfo=timezone.utc)))
        self.assertEqual(shards[3], (datetime(2026, 3, 22, tzinfo=timezone.utc), datetime(2026, 3, 29, tzinfo=timezone.utc)))
        self.assertEqual(shards[4], (datetime(2026, 3, 29, tzinfo=timezone.utc), end_dt))

    def test_rank_papers_for_queries_via_supabase_recovers_results_from_smaller_shards(self):
        start_dt = datetime(2026, 3, 1, tzinfo=timezone.utc)
        end_dt = datetime(2026, 3, 31, tzinfo=timezone.utc)
        queries = [
            {
                "type": "keyword",
                "tag": "ML",
                "paper_tag": "keyword:ML",
                "query_text": "machine learning",
            }
        ]

        timeout_msg = 'rpc 查询失败：HTTP 500 {"code":"57014","message":"canceling statement due to statement timeout"}'
        responses = {
            (datetime(2026, 3, 1, tzinfo=timezone.utc), datetime(2026, 3, 8, tzinfo=timezone.utc)): ([], timeout_msg),
            (datetime(2026, 3, 1, tzinfo=timezone.utc), datetime(2026, 3, 4, tzinfo=timezone.utc)): (
                [
                    {"id": "p1", "title": "Paper 1", "abstract": "A", "authors": [], "published": "2026-03-03T00:00:00+00:00", "link": "https://example/p1", "score": 0.91},
                ],
                "rpc 查询成功：1 条",
            ),
            (datetime(2026, 3, 4, tzinfo=timezone.utc), datetime(2026, 3, 7, tzinfo=timezone.utc)): (
                [
                    {"id": "p2", "title": "Paper 2", "abstract": "B", "authors": [], "published": "2026-03-05T00:00:00+00:00", "link": "https://example/p2", "score": 0.60},
                ],
                "rpc 查询成功：1 条",
            ),
            (datetime(2026, 3, 7, tzinfo=timezone.utc), datetime(2026, 3, 8, tzinfo=timezone.utc)): ([], "rpc 查询成功：0 条"),
            (datetime(2026, 3, 8, tzinfo=timezone.utc), datetime(2026, 3, 15, tzinfo=timezone.utc)): (
                [
                    {"id": "p3", "title": "Paper 3", "abstract": "C", "authors": [], "published": "2026-03-10T00:00:00+00:00", "link": "https://example/p3", "score": 0.95},
                    {"id": "p1", "title": "Paper 1 dup", "abstract": "A2", "authors": [], "published": "2026-03-11T00:00:00+00:00", "link": "https://example/p1b", "score": 0.88},
                ],
                "rpc 查询成功：2 条",
            ),
            (datetime(2026, 3, 15, tzinfo=timezone.utc), datetime(2026, 3, 22, tzinfo=timezone.utc)): ([], "rpc 查询成功：0 条"),
            (datetime(2026, 3, 22, tzinfo=timezone.utc), datetime(2026, 3, 29, tzinfo=timezone.utc)): (
                [
                    {"id": "p4", "title": "Paper 4", "abstract": "D", "authors": [], "published": "2026-03-24T00:00:00+00:00", "link": "https://example/p4", "score": 0.72},
                ],
                "rpc 查询成功：1 条",
            ),
            (datetime(2026, 3, 29, tzinfo=timezone.utc), datetime(2026, 3, 31, tzinfo=timezone.utc)): ([], "rpc 查询成功：0 条"),
        }

        seen_windows = []

        def fake_match(**kwargs):
            window = (kwargs.get("start_dt"), kwargs.get("end_dt"))
            seen_windows.append(window)
            self.assertEqual(kwargs.get("query_text"), "machine learning")
            self.assertEqual(kwargs.get("match_count"), 3)
            if window not in responses:
                raise AssertionError(f"unexpected window: {window}")
            return responses[window]

        with patch.object(self.bm25_mod, "match_papers_by_bm25", side_effect=fake_match):
            result = self.bm25_mod.rank_papers_for_queries_via_supabase(
                queries=queries,
                top_k=3,
                supabase_conf={
                    "url": "https://example.supabase.co",
                    "anon_key": "test-key",
                    "bm25_rpc": "match_arxiv_papers_bm25",
                    "schema": "public",
                },
                start_dt=start_dt,
                end_dt=end_dt,
            )

        self.assertEqual(len(seen_windows), 8)
        self.assertEqual(result["total_hits"], 3)
        self.assertEqual(len(result["queries"]), 1)
        self.assertIn((datetime(2026, 3, 1, tzinfo=timezone.utc), datetime(2026, 3, 8, tzinfo=timezone.utc)), seen_windows)
        self.assertIn((datetime(2026, 3, 1, tzinfo=timezone.utc), datetime(2026, 3, 4, tzinfo=timezone.utc)), seen_windows)
        self.assertIn((datetime(2026, 3, 4, tzinfo=timezone.utc), datetime(2026, 3, 7, tzinfo=timezone.utc)), seen_windows)
        self.assertIn((datetime(2026, 3, 7, tzinfo=timezone.utc), datetime(2026, 3, 8, tzinfo=timezone.utc)), seen_windows)

        sim_scores = result["queries"][0]["sim_scores"]
        self.assertEqual(list(sim_scores.keys()), ["p3", "p1", "p4"])
        self.assertEqual(sim_scores["p3"]["rank"], 1)
        self.assertEqual(sim_scores["p1"]["rank"], 2)
        self.assertEqual(sim_scores["p4"]["rank"], 3)
        self.assertAlmostEqual(sim_scores["p3"]["score"], 0.95)
        self.assertAlmostEqual(sim_scores["p1"]["score"], 0.91)
        self.assertAlmostEqual(sim_scores["p4"]["score"], 0.72)

        self.assertEqual(sorted(result["papers"].keys()), ["p1", "p3", "p4"])
        self.assertEqual(result["papers"]["p1"].title, "Paper 1")
        self.assertIn("keyword:ML", result["papers"]["p1"].tags)
        self.assertIn("keyword:ML", result["papers"]["p3"].tags)
        self.assertIn("keyword:ML", result["papers"]["p4"].tags)


class SupabaseVectorExactShardFallbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.embedding_mod = _load_module(
            "embedding_mod_for_shards",
            ROOT / "src" / "2.2.retrieval_papers_embedding.py",
        )

    def test_split_supabase_time_window_uses_seven_day_shards(self):
        start_dt = datetime(2026, 3, 1, tzinfo=timezone.utc)
        end_dt = datetime(2026, 3, 31, tzinfo=timezone.utc)

        shards = self.embedding_mod.split_supabase_time_window(start_dt, end_dt)

        self.assertEqual(len(shards), 5)
        self.assertEqual(shards[0], (start_dt, datetime(2026, 3, 8, tzinfo=timezone.utc)))
        self.assertEqual(shards[-1], (datetime(2026, 3, 29, tzinfo=timezone.utc), end_dt))

    def test_rank_papers_for_queries_via_supabase_exact_recovers_results_from_smaller_shards(self):
        start_dt = datetime(2026, 3, 1, tzinfo=timezone.utc)
        end_dt = datetime(2026, 3, 31, tzinfo=timezone.utc)
        queries = [
            {
                "type": "keyword",
                "tag": "ML",
                "paper_tag": "keyword:ML",
                "query_text": "machine learning",
            }
        ]

        timeout_msg = 'rpc 查询失败：HTTP 500 {"code":"57014","message":"canceling statement due to statement timeout"}'
        responses = {
            (datetime(2026, 3, 1, tzinfo=timezone.utc), datetime(2026, 3, 8, tzinfo=timezone.utc)): ([], timeout_msg),
            (datetime(2026, 3, 1, tzinfo=timezone.utc), datetime(2026, 3, 4, tzinfo=timezone.utc)): (
                [
                    {"id": "p1", "title": "Paper 1", "abstract": "A", "authors": [], "published": "2026-03-03T00:00:00+00:00", "link": "https://example/p1", "similarity": 0.91},
                ],
                "rpc 查询成功：1 条",
            ),
            (datetime(2026, 3, 4, tzinfo=timezone.utc), datetime(2026, 3, 7, tzinfo=timezone.utc)): (
                [
                    {"id": "p2", "title": "Paper 2", "abstract": "B", "authors": [], "published": "2026-03-05T00:00:00+00:00", "link": "https://example/p2", "similarity": 0.60},
                ],
                "rpc 查询成功：1 条",
            ),
            (datetime(2026, 3, 7, tzinfo=timezone.utc), datetime(2026, 3, 8, tzinfo=timezone.utc)): ([], "rpc 查询成功：0 条"),
            (datetime(2026, 3, 8, tzinfo=timezone.utc), datetime(2026, 3, 15, tzinfo=timezone.utc)): (
                [
                    {"id": "p3", "title": "Paper 3", "abstract": "C", "authors": [], "published": "2026-03-10T00:00:00+00:00", "link": "https://example/p3", "similarity": 0.95},
                    {"id": "p1", "title": "Paper 1 dup", "abstract": "A2", "authors": [], "published": "2026-03-11T00:00:00+00:00", "link": "https://example/p1b", "similarity": 0.88},
                ],
                "rpc 查询成功：2 条",
            ),
            (datetime(2026, 3, 15, tzinfo=timezone.utc), datetime(2026, 3, 22, tzinfo=timezone.utc)): ([], "rpc 查询成功：0 条"),
            (datetime(2026, 3, 22, tzinfo=timezone.utc), datetime(2026, 3, 29, tzinfo=timezone.utc)): (
                [
                    {"id": "p4", "title": "Paper 4", "abstract": "D", "authors": [], "published": "2026-03-24T00:00:00+00:00", "link": "https://example/p4", "similarity": 0.72},
                ],
                "rpc 查询成功：1 条",
            ),
            (datetime(2026, 3, 29, tzinfo=timezone.utc), datetime(2026, 3, 31, tzinfo=timezone.utc)): ([], "rpc 查询成功：0 条"),
        }

        seen_windows = []

        def fake_encode_queries(_model, q_texts):
            self.assertEqual(q_texts, ["machine learning"])
            return np.array([[0.1, 0.2, 0.3]], dtype=np.float32)

        def fake_match(**kwargs):
            window = (kwargs.get("start_dt"), kwargs.get("end_dt"))
            seen_windows.append(window)
            self.assertEqual(kwargs.get("match_count"), 3)
            if window not in responses:
                raise AssertionError(f"unexpected window: {window}")
            return responses[window]

        with patch.object(self.embedding_mod, "encode_queries", side_effect=fake_encode_queries):
            with patch.object(self.embedding_mod, "match_papers_by_embedding", side_effect=fake_match):
                result = self.embedding_mod.rank_papers_for_queries_via_supabase(
                    model=object(),
                    queries=queries,
                    top_k=3,
                    supabase_conf={
                        "url": "https://example.supabase.co",
                        "anon_key": "test-key",
                        "vector_rpc": "match_arxiv_papers",
                        "vector_rpc_exact": "match_arxiv_papers_exact",
                        "schema": "public",
                    },
                    start_dt=start_dt,
                    end_dt=end_dt,
                    rpc_name_override="match_arxiv_papers_exact",
                    rpc_mode="exact",
                )

        self.assertEqual(len(seen_windows), 8)
        self.assertEqual(result["total_hits"], 3)
        self.assertEqual(result["non_empty_queries"], 1)

        sim_scores = result["queries"][0]["sim_scores"]
        self.assertEqual(list(sim_scores.keys()), ["p3", "p1", "p4"])
        self.assertAlmostEqual(sim_scores["p3"]["score"], 0.95)
        self.assertAlmostEqual(sim_scores["p1"]["score"], 0.91)
        self.assertAlmostEqual(sim_scores["p4"]["score"], 0.72)
        self.assertEqual(sim_scores["p3"]["rank"], 1)
        self.assertEqual(sim_scores["p1"]["rank"], 2)
        self.assertEqual(sim_scores["p4"]["rank"], 3)

        self.assertEqual(sorted(result["papers"].keys()), ["p1", "p3", "p4"])
        self.assertEqual(result["papers"]["p1"].title, "Paper 1")
        self.assertIn("keyword:ML", result["papers"]["p1"].tags)
        self.assertIn("keyword:ML", result["papers"]["p3"].tags)
        self.assertIn("keyword:ML", result["papers"]["p4"].tags)


if __name__ == "__main__":
    unittest.main()
