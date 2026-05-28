import importlib.util
import pathlib
import sys
import tempfile
import unittest


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


class LocalDebugEnvTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        cls.mod = _load_module("local_debug_server_mod", root / "src" / "local_debug_server.py")

    def test_build_secret_env_maps_plain_secret_to_runtime_env(self):
        env = self.mod.build_secret_env(
            {
                "summarizedLLM": {
                    "apiKey": "sk-new-key",
                    "baseUrl": "https://api.deepseek.com",
                    "model": "deepseek-v4-flash",
                },
                "rerankerLLM": {
                    "profile": "public-zwwen-rerank",
                    "provider": "public_zwwen",
                    "apiKey": "",
                    "baseUrl": "https://zwwen.online/rerank",
                    "model": "Qwen/Qwen3-Reranker-0.6B",
                },
            }
        )

        self.assertEqual(env["DEEPSEEK_API_KEY"], "sk-new-key")
        self.assertEqual(env["SUMMARY_API_KEY"], "sk-new-key")
        self.assertEqual(env["DEEPSEEK_BASE_URL"], "https://api.deepseek.com")
        self.assertEqual(env["RERANK_PROFILE"], "public-zwwen-rerank")
        self.assertEqual(env["PUBLIC_RERANK_API_KEY"], "")
        self.assertEqual(env["PUBLIC_RERANK_API_BASE_URL"], "https://zwwen.online/rerank")

    def test_update_env_file_replaces_old_keys_preserves_comments_and_clears_stale_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / ".env"
            path.write_text(
                "# local debug\n"
                "DEEPSEEK_API_KEY=old\n"
                "PUBLIC_RERANK_API_KEY=old-rerank\n"
                "UNCHANGED=value\n",
                encoding="utf-8",
            )

            self.mod.update_env_file(
                path,
                {
                    "DEEPSEEK_API_KEY": "sk-new",
                    "SUMMARY_API_KEY": "sk-new",
                    "DEEPSEEK_BASE_URL": "https://api.deepseek.com",
                    "PUBLIC_RERANK_API_KEY": "",
                },
            )
            text = path.read_text(encoding="utf-8")

            self.assertIn("# local debug", text)
            self.assertIn("UNCHANGED=value", text)
            self.assertIn("DEEPSEEK_API_KEY=sk-new", text)
            self.assertIn("SUMMARY_API_KEY=sk-new", text)
            self.assertIn("DEEPSEEK_BASE_URL=https://api.deepseek.com", text)
            self.assertIn("PUBLIC_RERANK_API_KEY=", text)
            self.assertNotIn("DEEPSEEK_API_KEY=old", text)
            self.assertNotIn("PUBLIC_RERANK_API_KEY=old-rerank", text)

    def test_local_conference_command_skips_existing_topic_before_pipeline(self):
        cmd = self.mod.build_command(
            "conference-retrieval",
            "conference-paper-retrieval.yml",
            {"conference": "ICML", "years": "2025", "profile_tag": "RL"},
        )
        script = cmd[-1]

        self.assertIn("export DPR_FILTER_PROFILE_TAG=\"$PROFILE_TAG\"", script)
        self.assertIn("build_conference_topic_marker", script)
        self.assertIn("已存在会议词条，跳过重复检索", script)
        self.assertIn("src/conference_pipeline.py", script)
        self.assertNotIn("\npython src/conference_sidebar.py", script)
        self.assertIn(f"\n{self.mod.sys.executable} src/conference_sidebar.py", script)
        self.assertLess(script.index("TOPIC_MARKER="), script.index("src/conference_pipeline.py"))
        self.assertLess(script.index("grep -Fq \"$TOPIC_MARKER\""), script.index("src/conference_pipeline.py"))


if __name__ == "__main__":
    unittest.main()
