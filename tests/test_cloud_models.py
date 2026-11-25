import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import model_loader


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
        for name in ["daily-paper-reader", "conference-paper-retrieval", "topic-research"]:
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
            if name in ("daily-paper-reader", "topic-research"):
                for key in ("SUMMARY_API_KEY", "SUMMARY_BASE_URL", "SUMMARY_MODEL", "SILICONFLOW_API_KEY"):
                    self.assertIn(key, job["env"], f"{name}.yml 必须透传 {key}")


if __name__ == "__main__":
    unittest.main()
