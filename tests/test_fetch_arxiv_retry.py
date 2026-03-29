import importlib.util
import pathlib
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch


def _load_module_with_stubs():
    root = pathlib.Path(__file__).resolve().parents[1]
    path = root / "src" / "maintain" / "fetchers" / "fetch_arxiv.py"

    fake_arxiv = types.ModuleType("arxiv")

    class _Search:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    class _SortCriterion:
        SubmittedDate = "SubmittedDate"

    class _SortOrder:
        Descending = "Descending"

    class _Client:
        pass

    fake_arxiv.Search = _Search
    fake_arxiv.SortCriterion = _SortCriterion
    fake_arxiv.SortOrder = _SortOrder
    fake_arxiv.Client = _Client

    fake_supabase_source = types.ModuleType("supabase_source")
    fake_supabase_source.get_supabase_read_config = lambda *_args, **_kwargs: {"enabled": False}
    fake_supabase_source.fetch_recent_papers = lambda *_args, **_kwargs: []
    fake_supabase_source.fetch_papers_by_date_range = lambda *_args, **_kwargs: []

    fake_source_config = types.ModuleType("source_config")
    fake_source_config.load_config_with_source_migration = lambda *_args, **_kwargs: {}

    stubs = {
        "arxiv": fake_arxiv,
        "supabase_source": fake_supabase_source,
        "source_config": fake_source_config,
    }

    with patch.dict(sys.modules, stubs):
        spec = importlib.util.spec_from_file_location("fetch_arxiv_mod_retry", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(mod)
    return mod


class _FakeAuthor:
    def __init__(self, name: str):
        self.name = name


class _FakeResult:
    def __init__(self, pid: str, published: datetime):
        self._pid = pid
        self.title = "title"
        self.summary = "summary"
        self.authors = [_FakeAuthor("alice")]
        self.primary_category = "cs.AI"
        self.categories = ["cs.AI"]
        self.published = published
        self.entry_id = f"https://arxiv.org/abs/{pid}"
        self.pdf_url = f"https://arxiv.org/pdf/{pid}.pdf"

    def get_short_id(self):
        return self._pid


class _SequenceClient:
    def __init__(self, effects):
        self._effects = list(effects)
        self.calls = 0

    def results(self, _search):
        self.calls += 1
        effect = self._effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return iter(effect)


class FetchArxivRetryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module_with_stubs()

    def test_transient_http_429_retries_with_exponential_backoff(self):
        published = datetime(2026, 3, 28, 17, 0, tzinfo=timezone.utc)
        client = _SequenceClient(
            [
                Exception("Page request resulted in HTTP 429"),
                Exception("Page request resulted in HTTP 429"),
                [_FakeResult("1234.5678", published)],
            ],
        )

        seen_ids = set()
        unique_papers = {}
        windows = [(published - timedelta(hours=1), published)]

        with patch.object(self.mod.time, "sleep") as mock_sleep:
            max_pub = self.mod.fetch_category_in_windows(
                client=client,
                category="cs",
                windows=windows,
                seen_ids=seen_ids,
                unique_papers=unique_papers,
            )

        self.assertEqual(client.calls, 3)
        self.assertEqual(mock_sleep.call_args_list[0].args[0], 5.0)
        self.assertEqual(mock_sleep.call_args_list[1].args[0], 10.0)
        self.assertEqual(len(unique_papers), 1)
        self.assertIn("1234.5678", seen_ids)
        self.assertEqual(max_pub, published)

    def test_error_splits_window_after_retry_budget_exhausted(self):
        base = datetime(2026, 3, 28, 0, 0, tzinfo=timezone.utc)
        client = _SequenceClient(
            [
                Exception("Page request resulted in HTTP 503"),
                Exception("hard failure left"),
                Exception("hard failure right"),
            ],
        )

        with patch.object(self.mod.time, "sleep") as mock_sleep:
            self.mod.fetch_category_in_windows(
                client=client,
                category="math",
                windows=[(base, base + timedelta(days=1))],
                seen_ids=set(),
                unique_papers={},
                split_on_error_depth=1,
                max_window_retries=0,
            )

        self.assertEqual(client.calls, 3)
        self.assertEqual(mock_sleep.call_count, 3)


if __name__ == "__main__":
    unittest.main()
