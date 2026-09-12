import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import long_range_review as review


class LongRangeReviewTests(unittest.TestCase):
    def test_new_reports_require_fulltext_but_index_rebuild_remains_offline(self):
        with tempfile.TemporaryDirectory() as root, patch(
            "long_range_native.publish_native_reports"
        ) as publish:
            review.publish_report(
                root,
                "report",
                {},
                {"start": "2025-09-10", "end_exclusive": "2026-09-10"},
            )
            self.assertTrue(publish.call_args.kwargs["with_fulltext"])
            self.assertTrue(publish.call_args.kwargs["with_reading"])
            review.rebuild_report_index(root)
            self.assertFalse(publish.call_args.kwargs["with_fulltext"])
            self.assertFalse(publish.call_args.kwargs["with_reading"])

    def test_empty_query_profile_is_rejected_before_network_or_model_loading(self):
        with patch.object(
            review,
            "get_source_backend",
            return_value={
                "enabled": True,
                "url": "https://example.invalid",
                "anon_key": "test",
            },
        ), patch.object(
            review,
            "build_pipeline_inputs",
            return_value={
                "tags": ["empty"],
                "bm25_queries": [],
                "embedding_queries": [],
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "没有启用的关键词"):
                review.run_review({}, 90, ROOT, "20260612-20260909")

    def test_days_and_numeric_version_dedup(self):
        for n in [0, -1, 366, 90.5, True]:
            with self.assertRaises(ValueError):
                review.validate_days(n)
        self.assertEqual(review.validate_days(365), 365)
        rows = [{"id": "2601.00001v9"}, {"id": "2601.00001v10"}]
        self.assertEqual(review.unique_papers(rows), [rows[1]])

    def test_saturated_keyword_window_splits_without_missing_boundaries(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        data = [
            {"id": str(i), "time": start + timedelta(seconds=i)} for i in range(601)
        ]

        def call(a, b, n):
            return [r for r in data if a <= r["time"] < b][:n], "rpc 查询成功"

        found = review.collect_window(
            call, start, start + timedelta(seconds=601), exhaustive=True, limit=500
        )
        self.assertEqual({r["id"] for r in found}, {r["id"] for r in data})
        self.assertEqual(len(found), 601)
        sampled = review.collect_window(
            call, start, start + timedelta(seconds=601), exhaustive=False, limit=100
        )
        self.assertEqual(len(sampled), 100)

    def test_failure_or_unsplittable_page_never_pretends_to_be_complete(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for call in [
            lambda *args: ([], "rpc 查询失败：HTTP 403"),
            lambda *args: ([{}] * 500, "rpc 查询成功"),
        ]:
            with self.assertRaises(RuntimeError):
                review.collect_window(
                    call,
                    start,
                    start + timedelta(seconds=1),
                    exhaustive=True,
                    limit=500,
                )

    def test_score_needs_scope_and_verbatim_evidence(self):
        self.assertIn('"papers"', review.SYSTEM_PROMPT)
        self.assertIn('"scope_match"', review.SYSTEM_PROMPT)
        paper = {"id": "x", "title": "ATSP", "abstract": "We solve asymmetric TSP."}
        record = {
            "id": "x",
            "score": 9,
            "scope_match": True,
            "evidence": "asymmetric TSP",
            "reason": "明确求解目标",
        }
        self.assertEqual(review.classify_review(record, paper)["bucket"], "core")
        self.assertEqual(
            review.classify_review(dict(record, evidence="fabricated"), paper)[
                "bucket"
            ],
            "review",
        )
        self.assertEqual(
            review.classify_review(dict(record, scope_match=False), paper)["bucket"],
            "review",
        )
        self.assertEqual(
            review.classify_review(dict(record, score=7), paper)["bucket"], "related"
        )

    def test_atsp_guard_rejects_generic_tsp_and_keyword_aliases_fill_gap(self):
        topic = {"tag": "ATSP", "description": "非对称旅行商问题 ATSP"}
        paper = {
            "id": "x",
            "title": "Solving TSP",
            "abstract": "We solve the traveling salesman problem.",
        }
        result = {
            "id": "x",
            "score": 8,
            "scope_match": True,
            "evidence": "traveling salesman problem",
            "reason": "研究TSP",
        }
        self.assertEqual(
            review.classify_review(result, paper, topic)["bucket"], "review"
        )
        broad_topic = {
            "tag": "NCO",
            "description": "routing",
            "queries": ["asymmetric traveling salesman", "symmetric TSP"],
        }
        self.assertEqual(
            review.classify_review(result, paper, broad_topic)["bucket"], "core"
        )
        paper["abstract"] = (
            "We improve the approximation ratio for the Asymmetric TSP to less than 15."
        )
        result["evidence"] = "Asymmetric TSP"
        self.assertEqual(review.classify_review(result, paper, topic)["bucket"], "core")
        self.assertIn("asymmetric TSP", review.keyword_aliases(topic))
        self.assertEqual(
            review.keyword_aliases({"description": "symbolic regression"}), []
        )

    def test_cached_scores_reuse_and_topic_change_invalidates(self):
        paper = {"id": "x", "title": "ATSP", "abstract": "We solve asymmetric TSP."}
        record = {
            "id": "x",
            "score": 9,
            "scope_match": True,
            "evidence": "asymmetric TSP",
            "reason": "明确求解目标",
        }
        client = Mock()
        client.chat_structured.return_value = {"parsed": {"papers": [record]}}
        factory = Mock(return_value=client)
        with tempfile.TemporaryDirectory() as cache:
            for _ in range(2):
                review.review_batch([paper], "ATSP", cache, factory, "model")
            self.assertEqual(factory.call_count, 1)
            review.review_batch([paper], "new topic", cache, factory, "model")
            self.assertEqual(factory.call_count, 2)
            client.chat_structured.return_value = {"parsed": {"papers": []}}
            with self.assertRaises(ValueError):
                review.review_batch([paper], "third topic", cache, factory, "model")

    def test_report_is_paginated_and_retains_empty_group(self):
        rows = [
            {
                "id": str(i),
                "title": "<script>unsafe</script>",
                "score": 8,
                "bucket": "core",
            }
            for i in range(51)
        ]
        with tempfile.TemporaryDirectory() as root:
            manifest = review.publish_report(
                root,
                "safe-token",
                {"ATSP": rows, "empty": []},
                {"start": "2025-09-10", "end_exclusive": "2026-09-10"},
                with_fulltext=False,
                with_reading=False,
            )
            self.assertEqual(len(manifest["groups"][0]["buckets"]["core"]["pages"]), 2)
            self.assertEqual(manifest["groups"][1]["total"], 0)
            catalog = json.loads(
                (Path(root) / "docs/long-range/index.json").read_text()
            )
            self.assertEqual(catalog["version"], 1)
            self.assertEqual(catalog["reports"][0]["token"], "safe-token")
            self.assertFalse(
                (Path(root) / "docs/long-range/safe-token/index.html").exists()
            )
            self.assertTrue((Path(root) / "docs/20250910-20260909/0.md").exists())

    def test_main_routes_long_range_and_does_not_launch_legacy_steps(self):
        spec = importlib.util.spec_from_file_location(
            "review_main", ROOT / "src/main.py"
        )
        main = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(main)
        with patch.dict(os.environ, {}, clear=False), patch.object(
            sys, "argv", ["main.py", "--fetch-days", "365", "--profile-tag", "ATSP"]
        ), patch.object(main, "_load_full_config", return_value={}), patch.object(
            main, "run_step"
        ) as legacy, patch(
            "long_range_review.run_review"
        ) as run:
            main.main()
            self.assertEqual(run.call_args.args[1], 365)
            legacy.assert_not_called()

    def test_workflow_validates_range_and_saves_progress_on_failure(self):
        import yaml

        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/daily-paper-reader.yml").read_text()
        )
        steps = {step.get("name"): step for step in workflow["jobs"]["run"]["steps"]}
        self.assertIn("1 <= days <= 365", steps["Validate requested window"]["run"])
        self.assertIn("always()", steps["Save long-range review progress"]["if"])
        paths = steps["Save long-range review progress"]["with"]["path"].splitlines()
        self.assertIn(".local-runs/long-range-cache", paths)
        self.assertIn(".local-runs/starter-pack-cache", paths)
        self.assertIn(".local-runs/topic-research-rerank-cache", paths)
        commit_step = steps["Commit results"]["run"]
        self.assertLess(
            commit_step.index("git rebase"), commit_step.index("--rebuild-index")
        )
        self.assertNotIn("Prepare PaperCropper (optional)", steps)
        self.assertIn(
            "--require-lightweight", steps["Check cloud embedding and reranker"]["run"]
        )

    def test_rebuild_index_includes_merged_reports_without_running_models(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(
            review, "run_review", side_effect=AssertionError("不得运行模型")
        ):
            root = Path(directory)
            tokens = [
                "20250910-20260909-aaaaaaaaaaaa",
                "20260612-20260909-bbbbbbbbbbbb",
            ]
            for token in tokens:
                folder = root / "docs/long-range" / token
                folder.mkdir(parents=True)
                (folder / "manifest.json").write_text(
                    json.dumps(
                        {
                            "start": "2025-09-10",
                            "end_exclusive": "2026-09-10",
                            "generated_at": token,
                            "groups": [],
                        }
                    )
                )
            review.rebuild_report_index(root)
            index = root / "docs/long-range/index.json"
            before = index.read_text()
            self.assertEqual(
                {r["token"] for r in json.loads(before)["reports"]}, set(tokens)
            )
            review.rebuild_report_index(root)
            self.assertEqual(index.read_text(), before)


if __name__ == "__main__":
    unittest.main()
