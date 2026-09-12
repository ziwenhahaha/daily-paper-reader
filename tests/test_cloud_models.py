import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import model_loader
import long_range_review


class CloudModelTests(unittest.TestCase):
    def test_remote_only_blocks_force_local_and_fallback(self):
        with patch.dict(
            os.environ,
            {"DPR_MODELS_REMOTE_ONLY": "1", "DPR_EMBED_ALLOW_LOCAL_FALLBACK": "1"},
        ), patch.object(model_loader, "_load_local_sentence_transformer") as local:
            self.assertFalse(model_loader.is_local_embedding_fallback_enabled())
            with self.assertRaises(RuntimeError):
                model_loader.load_sentence_transformer(
                    "model", device="cpu", allow_remote=False
                )
            local.assert_not_called()

    def test_legacy_nonstandard_window_runs_without_local_models(self):
        remote = Mock(is_remote=True)
        remote.encode.return_value = np.ones((1, 384), dtype=np.float32)
        plan = {
            "tags": ["test"],
            "profiles": [{"tag": "test"}],
            "bm25_queries": [],
            "embedding_queries": [{"tag": "test", "query_text": "test query"}],
            "context_queries": [],
            "context_keywords": [],
        }
        with patch.dict(
            sys.modules,
            {"torch": None, "sentence_transformers": None, "transformers": None},
        ), patch.dict(
            os.environ, {"DEEPSEEK_API_KEY": "test", "DPR_MODELS_REMOTE_ONLY": "1"}
        ), patch.object(
            model_loader, "load_sentence_transformer", return_value=remote
        ), patch.object(
            long_range_review,
            "get_source_backend",
            return_value={
                "enabled": True,
                "url": "https://example.invalid",
                "anon_key": "test",
            },
        ), patch.object(
            long_range_review, "build_pipeline_inputs", return_value=plan
        ), patch.object(
            long_range_review,
            "match_papers_by_embedding",
            return_value=([], "rpc 查询成功"),
        ) as rpc, patch.object(
            long_range_review, "publish_report", return_value={"groups": [{"total": 0}]}
        ):
            long_range_review.run_review({}, 180, ROOT, "20260314-20260909")
            self.assertEqual(len(rpc.call_args.kwargs["query_embedding"]), 384)
            self.assertIsInstance(remote.encode.call_args.args[0], list)
            self.assertFalse(remote.allow_local_fallback)

    def test_legacy_local_reranker_resolves_to_cloud_in_actions(self):
        spec = importlib.util.spec_from_file_location(
            "cloud_rank_test", ROOT / "src/3.rank_papers.py"
        )
        rank = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rank)
        with patch.dict(
            os.environ,
            {
                "DPR_MODELS_REMOTE_ONLY": "1",
                "SILICONFLOW_API_KEY": "private-sf",
                "PUBLIC_RERANK_API_KEY": "public-test",
            },
        ):
            self.assertEqual(rank._normalize_rerank_provider("local"), "public_zwwen")
            self.assertEqual(
                rank._resolve_rerank_profile_config("local-qwen3-0.6b")["provider"],
                "public_zwwen",
            )
            self.assertEqual(
                rank._resolve_remote_api_key("public_zwwen"), "public-test"
            )
            with self.assertRaises(RuntimeError):
                rank.LocalQwenReranker()

    def test_workflows_set_cloud_policy_and_smoke_check(self):
        for name in ["daily-paper-reader", "conference-paper-retrieval"]:
            path = ROOT / ".github/workflows" / f"{name}.yml"
            workflow = yaml.safe_load(path.read_text())
            job = next(iter(workflow["jobs"].values()))
            self.assertEqual(job["env"]["DPR_MODELS_REMOTE_ONLY"], "1")
            self.assertEqual(job["env"]["DPR_EMBED_ALLOW_LOCAL_FALLBACK"], "0")
            self.assertNotIn("torch==", path.read_text())
            self.assertTrue(
                any(
                    "check_cloud_models.py --require-lightweight" in step.get("run", "")
                    for step in job["steps"]
                )
            )


if __name__ == "__main__":
    unittest.main()
