"""A dead recall backend is not the same as a successful empty search."""

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from recall_health import RECALL_NOT_RUN, RECALL_UNAVAILABLE, REPORT_RECALL_STATUS
from src import main as pipeline


def load_lane(filename):
    spec = importlib.util.spec_from_file_location(filename, SRC / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DailyRecallHealthTest(unittest.TestCase):
    def run_lanes(self, responses, *, local_papers=None, orchestrated=False, with_queries=True):
        for lane, filename, match_fn in (
            ("bm25", "2.1.retrieval_papers_bm25.py", "match_papers_by_bm25"),
            ("embedding", "2.2.retrieval_papers_embedding.py", "match_papers_by_embedding"),
        ):
            with self.subTest(lane=lane), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                mod = load_lane(filename)
                queries = [{
                    "type": "keyword", "tag": "mock", "paper_tag": "keyword:mock",
                    "query_text": "mock term", "query_embedding": [1.0, 0.0],
                }] if with_queries else []
                backend = {
                    "enabled": True, "url": "https://mock.invalid", "anon_key": "synthetic",
                    "use_bm25_rpc": True, "use_vector_rpc": True,
                }
                start = datetime(2026, 3, 1, tzinfo=timezone.utc)
                end = datetime(2026, 3, 10, tzinfo=timezone.utc)
                mod.load_config = lambda: {}
                mod.get_supabase_read_config = lambda _: backend
                mod.resolve_supabase_recall_window = lambda _: (start, end)
                mod.multi_source_rpc_enabled = lambda: False
                mod.build_pipeline_inputs = lambda _: {lane + "_queries": queries}
                mod.RAW_DIR = str(root / "raw")
                mod.FILTERED_DIR = str(root / "filtered")
                if lane == "embedding":
                    mod.hydrate_query_embeddings_from_config = lambda **_: {}
                    # Cached vectors exercise the real cosine ranking without initializing a model.
                    mod.EmbeddingCoarseFilter = lambda **_: SimpleNamespace(model=None)
                if local_papers is not None:
                    (root / "raw").mkdir()
                    (root / "raw" / "papers.json").write_text(json.dumps(local_papers), encoding="utf-8")
                with (
                    patch.object(mod, match_fn, side_effect=responses) as rpc,
                    patch.object(sys, "argv", [filename, "--top-k", "2"]),
                    patch.dict(os.environ, {REPORT_RECALL_STATUS: "1" if orchestrated else "0"}),
                ):
                    try:
                        mod.main()
                    except SystemExit as exc:
                        code = exc.code
                    else:
                        code = 0
                outputs = [
                    json.loads(path.read_text(encoding="utf-8"))
                    for path in (root / "filtered").glob("*.json")
                ]
                self.assertEqual(rpc.call_count, 2 if with_queries else 0)
                yield code, outputs

    def test_total_outage_without_local_data_fails_without_writing_results(self):
        for local_papers in (None, []):
            failures = [([], "rpc 查询失败：mock DNS")] * 2
            for code, outputs in self.run_lanes(failures, local_papers=local_papers):
                self.assertEqual(code, RECALL_UNAVAILABLE)
                self.assertEqual(outputs, [])

    def test_successful_zero_results_are_not_an_outage(self):
        empty = [([], "rpc 查询成功：0 条")] * 2
        for code, _ in self.run_lanes(empty, orchestrated=True):
            self.assertEqual(code, 0)

    def test_one_successful_shard_is_not_an_outage(self):
        rows = [{"id": "remote-1", "title": "Mock", "similarity": 0.9, "score": 0.9}]
        partial = [([], "rpc 查询失败：mock DNS"), (rows, "rpc 查询成功：1 条")]
        for code, outputs in self.run_lanes(partial, orchestrated=True):
            self.assertEqual(code, 0)
            self.assertIn("remote-1", json.dumps(outputs))
        healthy_empty = [([], "rpc 查询失败：mock DNS"), ([], "rpc 查询成功：0 条")]
        for code, _ in self.run_lanes(healthy_empty, orchestrated=True):
            self.assertEqual(code, 0)

    def test_local_results_recover_a_remote_outage(self):
        papers = [{"id": "local-1", "title": "Mock term", "embedding": [1.0, 0.0]}]
        failures = [([], "rpc 查询失败：mock DNS")] * 2
        for code, outputs in self.run_lanes(failures, local_papers=papers):
            self.assertEqual(code, 0)
            self.assertIn("local-1", json.dumps(outputs))

    def test_no_active_query_is_neither_success_nor_outage(self):
        for code, _ in self.run_lanes([], orchestrated=True, with_queries=False):
            self.assertEqual(code, RECALL_NOT_RUN)
        for code, _ in self.run_lanes([], with_queries=False):
            self.assertEqual(code, 0)

    def test_pipeline_only_stops_on_unrecovered_outage(self):
        for bm25, embedding, stopped in (
            (RECALL_UNAVAILABLE, RECALL_UNAVAILABLE, True),
            (RECALL_UNAVAILABLE, RECALL_NOT_RUN, True),
            (RECALL_NOT_RUN, RECALL_UNAVAILABLE, True),
            (RECALL_UNAVAILABLE, 0, False),
            (0, RECALL_UNAVAILABLE, False),
            (0, 0, False),
        ):
            with self.subTest(bm25=bm25, embedding=embedding), tempfile.TemporaryDirectory() as tmp:
                calls = []

                def run_step(label, args, env=None):
                    calls.append(label)
                    code = {"Step 2.1 - BM25": bm25, "Step 2.2 - Embedding": embedding}.get(label, 0)
                    if label.startswith(("Step 2.1", "Step 2.2")):
                        self.assertEqual(env.get(REPORT_RECALL_STATUS), "1")
                    if code:
                        raise subprocess.CalledProcessError(code, args)

                with (
                    patch.object(pipeline, "ROOT_DIR", tmp),
                    patch.object(pipeline, "run_step", side_effect=run_step),
                    patch.object(sys, "argv", ["main.py", "--skip-fetch"]),
                    patch.dict(os.environ, {}, clear=True),
                ):
                    if stopped:
                        with self.assertRaisesRegex(SystemExit, "已停止生成日报"):
                            pipeline.main()
                    else:
                        pipeline.main()
                self.assertIn("Step 2.2 - Embedding", calls)
                self.assertEqual("Step 2.3 - RRF" not in calls, stopped)
                self.assertEqual(any(label.startswith("Step 6") for label in calls), not stopped)

    def test_unexpected_subprocess_error_is_not_treated_as_outage(self):
        error = subprocess.CalledProcessError(1, ["mock-step"])
        with patch.object(pipeline, "run_step", side_effect=error):
            with self.assertRaises(subprocess.CalledProcessError) as caught:
                pipeline.run_recall_step("unexpected", ["mock-step"])
        self.assertIs(caught.exception, error)
