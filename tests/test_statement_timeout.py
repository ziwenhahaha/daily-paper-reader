"""Tests for PostgreSQL statement timeout (57014) handling and date-filter
payload in Supabase RPC calls.

When the database returns a statement timeout error (HTTP 500, code 57014),
the client should:
1. Skip retries in _request_with_retries (retrying won't resolve a server-side limit)
2. Break early in rank_papers_for_queries_via_supabase (subsequent batches will also time out)

To prevent the timeout in the first place, the client now passes
filter_published_start / filter_published_end in the RPC payload so the
database can narrow the search scope with a WHERE clause before computing
vector similarity.
"""

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from supabase_source import (
    _build_date_filter_payload,
    _is_statement_timeout,
    _request_with_retries,
    match_papers_by_embedding,
    match_papers_by_bm25,
)


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


if __name__ == "__main__":
    unittest.main()
