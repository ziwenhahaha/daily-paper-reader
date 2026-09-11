import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import starter_pack_retrieval as retrieval


class StarterRetrievalTests(unittest.TestCase):
    def test_conference_order_does_not_change_run_identity(self):
        first = retrieval.build_tasks(
            self.config(), "ATSP", "2026-09-11", ["icml", "iclr"], {"items": []}
        )
        second = retrieval.build_tasks(
            self.config(), "ATSP", "2026-09-11", ["iclr", "icml", "iclr"], {"items": []}
        )
        self.assertEqual(first["run_id"], second["run_id"])

    def config(self):
        return {
            "subscriptions": {
                "intent_profiles": [
                    {
                        "tag": "ATSP",
                        "enabled": True,
                        "keywords": ["ATSP"],
                        "intent_queries": [],
                        "paper_sources": ["arxiv"],
                    }
                ]
            }
        }

    def plan(self):
        return retrieval.build_tasks(
            self.config(), "ATSP", "2026-09-11", ["icml"], {"items": []}
        )

    def test_calendar_window_queries_and_nonmutation(self):
        config = self.config()
        before = copy.deepcopy(config)
        plan = retrieval.build_tasks(
            config, "ATSP", "2024-02-29", ["icml"], {"items": []}
        )
        self.assertEqual(plan["conference_start"], "2022-02-28")
        self.assertEqual(
            {t["year"] for t in plan["tasks"] if t["source"] == "icml"},
            {2022, 2023, 2024},
        )
        self.assertEqual(config, before)
        self.assertIn(
            "asymmetric travelling salesperson",
            [t["query"]["query_text"] for t in plan["tasks"]],
        )

    def test_paused_disabled_empty_rejected(self):
        for field in ["paused", "enabled", "keywords"]:
            config = self.config()
            config["subscriptions"]["intent_profiles"][0][field] = {
                "paused": True,
                "enabled": False,
                "keywords": [],
            }[field]
            with self.assertRaises(ValueError):
                retrieval.build_tasks(config, "ATSP", "2026-09-11", [])

    def test_missing_inventory_not_a_completed_query(self):
        plan = retrieval.build_tasks(
            self.config(),
            "ATSP",
            "2026-09-11",
            ["icml"],
            {
                "items": [
                    {"conference_key": "icml", "year": 2026, "stored_total_count": 0}
                ]
            },
        )
        self.assertEqual(
            plan["missing_inventory"], [{"conference": "icml", "year": 2026}]
        )
        self.assertFalse(any(t.get("year") == 2026 for t in plan["tasks"]))

    def test_review_keywords_exclude_retrieval_aliases(self):
        self.assertEqual(self.plan()["profile"]["review_keywords"], ["ATSP"])

    def test_selected_conference_temporary_profile_is_not_hidden_or_mutated(self):
        config = self.config()
        config["subscriptions"]["intent_profiles"][0].update(
            scope="conference", temporary=True, conference_only=True
        )
        before = copy.deepcopy(config)
        plan = retrieval.build_tasks(config, "ATSP", "2026-09-11", ["icml"])
        self.assertTrue(plan["tasks"])
        self.assertEqual(config, before)

    def test_custom_endpoint_invalidates_task_but_default_retains_legacy_key(self):
        plan = self.plan()
        task = next(
            t
            for t in plan["tasks"]
            if t["source"] == "arxiv" and t["lane"] == "embedding"
        )
        plan["tasks"] = [task]
        backend = {"url": "https://example.invalid", "anon_key": "secret"}
        legacy = retrieval.fingerprint(
            {
                "version": retrieval.VERSION,
                "task": task,
                "profile": plan["profile"],
                "backend": retrieval._backend_identity(backend),
                "model": retrieval.MODEL,
            }
        )
        with tempfile.TemporaryDirectory() as root, patch.object(
            retrieval, "get_source_backend", return_value=backend
        ), patch.object(retrieval, "_vector", return_value=[1.0] * 384), patch.object(
            retrieval, "match_papers_by_embedding", return_value=([], "rpc 查询成功")
        ) as rpc, patch.dict(
            os.environ, {"DPR_EMBED_API_URL": "https://zwwen.online/embed"}
        ):
            first = retrieval.run_retrieval(plan, {}, root)
            self.assertEqual(first["tasks"][0]["key"], legacy)
            retrieval.run_retrieval(plan, {}, root)
            self.assertEqual(rpc.call_count, 1)
            with patch.dict(
                os.environ, {"DPR_EMBED_API_URL": "https://custom.invalid/embed"}
            ):
                second = retrieval.run_retrieval(plan, {}, root)
            self.assertNotEqual(second["tasks"][0]["key"], legacy)
            self.assertEqual(rpc.call_count, 2)

    def test_vector_cache_uses_real_endpoint(self):
        import numpy as np

        def prepare(queries, **kwargs):
            queries[0]["query_embedding"] = np.ones(384)

        with tempfile.TemporaryDirectory() as root, patch(
            "conference_retrieval.prepare_embedding_queries", side_effect=prepare
        ) as encode, patch.dict(
            os.environ, {"DPR_EMBED_API_URL": "https://one.invalid"}
        ):
            query = {"query_text": "ATSP"}
            retrieval._vector(query, Path(root))
            retrieval._vector(query, Path(root))
            self.assertEqual(encode.call_count, 1)
            with patch.dict(os.environ, {"DPR_EMBED_API_URL": "https://two.invalid"}):
                retrieval._vector(query, Path(root))
            self.assertEqual(encode.call_count, 2)

    def test_rejected_and_withdrawn_are_not_conference_acceptances(self):
        plan = self.plan()
        plan["tasks"] = [t for t in plan["tasks"] if t.get("year") == 2025][:1]
        rows = [
            {"id": str(i), "source": "ICML-2025-" + status, "title": "ATSP"}
            for i, status in enumerate(["Rejected", "Withdrawn", "Accepted"])
        ]
        backend = {"url": "https://example.invalid", "anon_key": "secret"}
        with tempfile.TemporaryDirectory() as root, patch(
            "conference_retrieval.resolve_unified_conference_backend",
            return_value=backend,
        ), patch.object(
            retrieval, "match_papers_by_bm25", return_value=(rows, "rpc 查询成功")
        ):
            result = retrieval.run_retrieval(plan, {}, root)
            self.assertEqual([p["id"] for p in result["papers"]], ["2"])
            self.assertEqual(result["coverage"]["excluded_nonaccepted"], 2)

    def test_failure_not_cached_and_completed_query_resumed(self):
        plan = self.plan()
        plan["tasks"] = [
            t for t in plan["tasks"] if t["source"] == "arxiv" and t["lane"] == "bm25"
        ][:2]
        backend = {
            "enabled": True,
            "url": "https://example.invalid",
            "anon_key": "secret",
        }
        row = {"id": "2601.12345", "title": "ATSP", "published": "2026-01-01"}
        with tempfile.TemporaryDirectory() as root, patch.object(
            retrieval, "get_source_backend", return_value=backend
        ), patch.object(
            retrieval,
            "match_papers_by_bm25",
            side_effect=lambda **kwargs: (
                ([row], "rpc 查询成功")
                if kwargs["query_text"] == plan["tasks"][0]["query"]["query_text"]
                else ([], "network error")
            ),
        ) as rpc:
            with self.assertRaises(RuntimeError):
                retrieval.run_retrieval(plan, {}, root)
            rpc.side_effect = None
            rpc.return_value = ([row], "rpc 查询成功")
            result = retrieval.run_retrieval(plan, {}, root)
            self.assertEqual(rpc.call_count, 3)
            self.assertEqual(len(result["papers"]), 1)
            self.assertTrue(result["tasks"][0]["restored"])
            self.assertFalse(result["tasks"][1]["restored"])
            for path in Path(root).rglob("*.json"):
                self.assertNotIn("secret", path.read_text())

    def test_four_tasks_concurrent_but_result_order_is_deterministic(self):
        plan = self.plan()
        plan["tasks"] = [
            t for t in plan["tasks"] if t["source"] == "arxiv" and t["lane"] == "bm25"
        ][:4]
        barrier = threading.Barrier(4)
        queries = [t["query"]["query_text"] for t in plan["tasks"]]

        def call(**kwargs):
            barrier.wait(timeout=3)
            pid = str(queries.index(kwargs["query_text"]))
            return [
                {"id": pid, "title": "ATSP", "published": "2026-01-01"}
            ], "rpc 查询成功"

        with tempfile.TemporaryDirectory() as root, patch.object(
            retrieval,
            "get_source_backend",
            return_value={"url": "https://example.invalid", "anon_key": "secret"},
        ), patch.object(retrieval, "match_papers_by_bm25", side_effect=call) as rpc:
            first = retrieval.run_retrieval(plan, {}, root)
            second = retrieval.run_retrieval(plan, {}, root)
            self.assertEqual([p["id"] for p in first["papers"]], ["0", "1", "2", "3"])
            self.assertEqual(first["papers"], second["papers"])
            self.assertEqual(rpc.call_count, 4)
            self.assertTrue(all(t["restored"] for t in second["tasks"]))

    def test_concurrent_same_query_only_encoded_once(self):
        import numpy as np

        plan = self.plan()
        plan["tasks"] = [
            t
            for t in plan["tasks"]
            if t["source"] == "arxiv" and t["lane"] == "embedding"
        ][:4]

        def prepare(queries, **kwargs):
            queries[0]["query_embedding"] = np.ones(384)

        with tempfile.TemporaryDirectory() as root, patch.object(
            retrieval,
            "get_source_backend",
            return_value={"url": "https://example.invalid", "anon_key": "secret"},
        ), patch.object(
            retrieval, "match_papers_by_embedding", return_value=([], "rpc 查询成功")
        ), patch(
            "conference_retrieval.prepare_embedding_queries", side_effect=prepare
        ) as encoder:
            result = retrieval.run_retrieval(plan, {}, root)
            self.assertEqual(len(result["tasks"]), 4)
            self.assertEqual(encoder.call_count, 1)

    def test_conference_exact_year_and_uncertain_boundary(self):
        plan = self.plan()
        plan["tasks"] = [t for t in plan["tasks"] if t.get("year") == 2024][:1]
        backend = {
            "enabled": True,
            "url": "https://example.invalid",
            "anon_key": "secret",
        }
        row = {
            "id": "p",
            "source": "ICML-2024-Public",
            "title": "ATSP",
            "published": "2024-01-01",
        }
        with tempfile.TemporaryDirectory() as root, patch(
            "conference_retrieval.resolve_unified_conference_backend",
            return_value=backend,
        ), patch.object(
            retrieval, "match_papers_by_bm25", return_value=([row], "rpc 查询成功")
        ) as rpc, patch.object(
            retrieval,
            "resolve_publication_date",
            return_value={
                "publication_date": "2024",
                "publication_date_precision": "year",
                "publication_date_source": "year",
                "publication_date_kind": "unknown",
            },
        ):
            result = retrieval.run_retrieval(plan, {}, root)
            self.assertEqual(
                rpc.call_args.kwargs["extra_payload"]["filter_pairs"], ["icml:2024"]
            )
            self.assertEqual(
                result["papers"][0]["publication_window_status"], "uncertain"
            )
            self.assertFalse(result["coverage"]["guarantees_all_relevant_papers"])
            row["source"] = "ICML-2025-Public"
            with tempfile.TemporaryDirectory() as other, self.assertRaises(
                RuntimeError
            ):
                retrieval.run_retrieval(plan, {}, other)


if __name__ == "__main__":
    unittest.main()
