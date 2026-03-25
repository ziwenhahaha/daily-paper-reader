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


class CleanupSupabaseOldPapersTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module(
            "cleanup_supabase_mod",
            src_dir / "maintain" / "cleanup.py",
        )

    def test_cleanup_old_papers_batches_until_empty(self):
        fetch_calls = []
        delete_calls = []

        def fake_fetch(**kwargs):
            fetch_calls.append(kwargs)
            if len(fetch_calls) == 1:
                return ["p1", "p2"]
            if len(fetch_calls) == 2:
                return ["p3"]
            return []

        def fake_delete(**kwargs):
            delete_calls.append(kwargs)
            return len(kwargs["ids"])

        with patch.object(self.mod, "fetch_old_paper_ids", side_effect=fake_fetch), patch.object(
            self.mod, "delete_papers_by_ids", side_effect=fake_delete
        ):
            result = self.mod.cleanup_old_papers(
                url="https://example.supabase.co",
                service_key="service-key",
                papers_table="arxiv_papers",
                schema="public",
                retention_days=45,
                batch_size=2,
            )

        self.assertEqual(result["deleted"], 3)
        self.assertEqual(result["batches"], 2)
        self.assertEqual(len(delete_calls), 2)
        self.assertEqual(delete_calls[0]["ids"], ["p1", "p2"])
        self.assertEqual(delete_calls[1]["ids"], ["p3"])

    def test_cleanup_old_papers_dry_run_stops_after_first_batch(self):
        with patch.object(self.mod, "fetch_old_paper_ids", return_value=["p1", "p2"]), patch.object(
            self.mod, "delete_papers_by_ids"
        ) as delete_mock:
            result = self.mod.cleanup_old_papers(
                url="https://example.supabase.co",
                service_key="service-key",
                papers_table="arxiv_papers",
                schema="public",
                retention_days=45,
                batch_size=2,
                dry_run=True,
            )

        self.assertEqual(result["deleted"], 2)
        self.assertEqual(result["batches"], 1)
        delete_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
