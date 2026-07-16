import pathlib
import unittest

import yaml


class ConferenceWorkflowAndUiTest(unittest.TestCase):
    def test_daily_workflow_uses_fast_rerank_budget(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        workflow_path = root / ".github" / "workflows" / "daily-paper-reader.yml"
        text = workflow_path.read_text(encoding="utf-8")

        self.assertIn("MKL_THREADING_LAYER: GNU", text)
        self.assertIn("DPR_RERANK_GLOBAL_POOL_LIMIT: \"120\"", text)
        self.assertIn("DPR_RERANK_GUARANTEED_PER_LANE: \"2\"", text)
        self.assertIn("RERANK_PROFILE", text)
        self.assertIn("RERANK_API_KEY", text)
        self.assertIn("SILICONFLOW_API_KEY", text)
        self.assertIn('default: "public-zwwen-rerank"', text)
        self.assertIn("requirements-paper-media.txt", text)
        self.assertIn("PaperCropper smoke OK", text)

    def test_conference_retrieval_workflow_dispatches_pipeline(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        workflow_path = root / ".github" / "workflows" / "conference-paper-retrieval.yml"
        text = workflow_path.read_text(encoding="utf-8")
        workflow = yaml.safe_load(text) or {}
        on_block = workflow.get("on") or workflow.get(True) or {}
        inputs = (((on_block.get("workflow_dispatch") or {}).get("inputs")) or {})

        self.assertIn("conference", inputs)
        self.assertIn("years", inputs)
        self.assertIn("conference_pairs", inputs)
        self.assertEqual((inputs.get("top_k") or {}).get("default"), "50")
        self.assertEqual((inputs.get("rrf_top_n") or {}).get("default"), "200")
        self.assertEqual((inputs.get("run_rerank") or {}).get("default"), "true")
        self.assertEqual((inputs.get("reranker_profile") or {}).get("default"), "public-zwwen-rerank")
        self.assertEqual((inputs.get("run_llm_refine") or {}).get("default"), "true")
        self.assertIn("MKL_THREADING_LAYER: GNU", text)
        self.assertIn("DPR_RERANK_GLOBAL_POOL_LIMIT: \"120\"", text)
        self.assertIn("DPR_RERANK_GUARANTEED_PER_LANE: \"2\"", text)
        self.assertIn("RERANK_PROFILE", text)
        self.assertIn("RERANK_API_KEY", text)
        self.assertIn("SILICONFLOW_API_KEY", text)
        self.assertIn("DEEPSEEK_API_KEY", text)
        self.assertIn("requirements-paper-media.txt", text)
        self.assertIn("PaperCropper smoke OK", text)
        self.assertIn("python src/conference_pipeline.py", text)
        self.assertIn("--run-llm-refine", text)
        self.assertIn("--output-dir \"archive/${RUN_DATE}/filtered\"", text)
        self.assertIn("DPR_FILTER_PROFILE_TAG", text)
        self.assertIn("CONFERENCE_PAIRS", text)
        self.assertIn("--conference-pairs", text)

    def test_frontend_triggers_conference_retrieval_workflow(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        runner = (root / "app" / "workflows.runner.js").read_text(encoding="utf-8")
        manager = (root / "app" / "subscriptions.manager.js").read_text(encoding="utf-8")
        css = (root / "app" / "app.css").read_text(encoding="utf-8")

        self.assertIn("conference-paper-retrieval.yml", runner)
        self.assertIn("runConferenceRetrieval", runner)
        self.assertIn("/api/local/workflows/dispatch", runner)
        self.assertIn("DPR_LOCAL_API_BASE", runner)
        self.assertIn(":8567${path}", runner)
        self.assertIn("loadLocalConfigOverride", runner)
        self.assertIn("config: localConfigOverride", runner)
        self.assertIn("secret: localSecret", runner)
        github_token = (root / "app" / "subscriptions.github-token.js").read_text(encoding="utf-8")
        self.assertIn("loadLocalConfigOverride", github_token)
        self.assertIn("saveLocalConfigToDisk", github_token)
        self.assertIn("/api/local/config", github_token)
        self.assertIn("192\\.168", runner)
        self.assertTrue((root / "src" / "local_debug_server.py").exists())
        self.assertTrue((root / "scripts" / "local_debug.sh").exists())
        self.assertTrue((root / "scripts" / "bootstrap_local.sh").exists())
        self.assertTrue((root / "requirements-cpu.txt").exists())
        bootstrap = (root / "scripts" / "bootstrap_local.sh").read_text(encoding="utf-8")
        requirements = (root / "requirements.txt").read_text(encoding="utf-8")
        paper_media_requirements = (root / "requirements-paper-media.txt").read_text(encoding="utf-8")
        self.assertIn('INSTALL_MODE="${DPR_INSTALL_MODE:-remote}"', bootstrap)
        self.assertIn("python -m pip install -r requirements.txt", bootstrap)
        self.assertIn("PyMuPDF", requirements)
        self.assertIn("opencv-python-headless", requirements)
        self.assertIn("albumentations", paper_media_requirements)
        self.assertIn("thop", paper_media_requirements)
        server = (root / "src" / "local_debug_server.py").read_text(encoding="utf-8")
        self.assertIn("src/conference_pipeline.py", server)
        self.assertIn("src/conference_sidebar.py", server)
        self.assertIn(".supabase.llm.json", server)
        self.assertIn("run_rerank: 'true'", runner)
        self.assertIn("run_llm_refine: 'true'", runner)
        self.assertIn("reranker_profile: 'public-zwwen-rerank'", runner)
        self.assertIn("reranker_profile", runner)
        self.assertIn("isWorkflowLogNearBottom", runner)
        self.assertIn("scrollWorkflowLogToBottom", runner)
        self.assertIn("data-dpr-workflow-log", runner)
        self.assertIn("logEl.scrollTop = logEl.scrollHeight", runner)
        self.assertNotIn("bodyEl.scrollTop = bodyEl.scrollHeight", runner)
        self.assertIn("refreshLocalRun(r.runId)", runner)
        self.assertIn("conference_pairs: selectedPairText", manager)
        self.assertIn("runConferenceRetrieval('unified', selectedYears, {", manager)
        for conference in ["OSDI", "SOSP", "IEEE S&P", "NDSS"]:
            self.assertIn(conference, manager)
        for conference in ["OSDI", "SOSP", "S&P", "NDSS"]:
            self.assertIn(conference, runner)
        self.assertIn("profile_tag: profileTags.join(',')", manager)
        self.assertIn("会议论文检索", manager)
        self.assertNotIn("showPrettyConfirm", manager)
        self.assertNotIn("确认对 <strong>", manager)
        self.assertNotIn("dpr-run-confirm", css)
        self.assertNotIn("runConferenceMaintain(conf, years)", manager)

    def test_maintain_workflow_knows_public_systems_security_conferences(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        workflow_path = root / ".github" / "workflows" / "maintain-supabase.yml"
        text = workflow_path.read_text(encoding="utf-8")

        for source_key in ["osdi", "sosp", "ieee_sp", "ndss"]:
            self.assertIn(f"src/maintain/{source_key}.py", text)
            self.assertIn(f"DPR_ENABLE_{source_key.upper()}_BACKEND", text)
            self.assertIn(f"DPR_{source_key.upper()}_PAPERS_TABLE", text)

    def test_local_debug_uses_browser_config_override(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        server = (root / "src" / "local_debug_server.py").read_text(encoding="utf-8")
        main = (root / "src" / "main.py").read_text(encoding="utf-8")
        bm25 = (root / "src" / "2.1.retrieval_papers_bm25.py").read_text(encoding="utf-8")
        embedding = (root / "src" / "2.2.retrieval_papers_embedding.py").read_text(encoding="utf-8")
        fetch_arxiv = (root / "src" / "maintain" / "fetchers" / "fetch_arxiv.py").read_text(encoding="utf-8")

        self.assertIn("DPR_CONFIG_FILE", server)
        self.assertIn("/api/local/config", server)
        self.assertIn("CONFIG_PATH.write_text", server)
        self.assertIn("/api/local/secret", server)
        self.assertIn("SECRET_PATH.write_text", server)
        self.assertIn("ENV_PATH", server)
        self.assertIn("update_env_file", server)
        self.assertIn("build_secret_env", server)
        self.assertIn("DEEPSEEK_API_KEY", server)
        self.assertIn("SUMMARY_API_KEY", server)
        self.assertIn("config.yaml", server)
        self.assertIn("payload.get(\"config\")", server)
        self.assertIn("payload.get(\"secret\")", server)
        for text in [main, bm25, embedding, fetch_arxiv]:
            self.assertIn("DPR_CONFIG_FILE", text)

    def test_local_secret_private_is_disk_backed_and_ignored(self):
        root = pathlib.Path(__file__).resolve().parents[1]
        secret_js = (root / "app" / "secret.session.js").read_text(encoding="utf-8")
        gitignore = (root / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("/api/local/secret", secret_js)
        self.assertIn("saveLocalSecretPayloadToDisk", secret_js)
        self.assertIn("body.secret = secretPlain", secret_js)
        self.assertIn("loadLocalSecretPayloadPreferred", secret_js)
        self.assertIn("DEFAULT_RERANKER_PROFILE.value", secret_js)
        self.assertIn("secret.private", gitignore)


if __name__ == "__main__":
    unittest.main()
