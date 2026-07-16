import importlib.util
import io
import pathlib
import sys
import unittest
from unittest.mock import Mock, patch


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


class PublicConferenceSupabaseDeployTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module(
            "public_conference_supabase_deploy_mod",
            root / "scripts" / "public_conference_supabase_deploy.py",
        )

    def test_resolve_project_ref_from_supabase_url(self):
        self.assertEqual(
            self.mod.resolve_project_ref("https://lyucdwgefyfbmaiopjbk.supabase.co"),
            "lyucdwgefyfbmaiopjbk",
        )
        self.assertEqual(self.mod.resolve_project_ref("https://example.com", "manual-ref"), "manual-ref")

    def test_sql_plan_covers_four_public_conferences(self):
        names = [path.name for path in self.mod.sql_paths()]
        for conference in ["osdi", "sosp", "ieee_sp", "ndss"]:
            self.assertIn(f"create_{conference}_papers_schema.sql", names)
            self.assertIn(f"match_{conference}_papers.sql", names)
        self.assertIn("enable_conference_anon_read_policies.sql", names)

    def test_run_management_query_uses_beta_database_query_endpoint(self):
        response = Mock()
        response.text = '{"ok": true}'
        response.json.return_value = {"ok": True}
        response.raise_for_status.return_value = None
        with patch.object(self.mod.requests, "post", return_value=response) as post:
            result = self.mod.run_management_query(
                project_ref="project-ref",
                access_token="secret-token",
                query="select 1;",
            )
        self.assertEqual(result, {"ok": True})
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://api.supabase.com/v1/projects/project-ref/database/query")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer secret-token")
        self.assertEqual(kwargs["json"], {"query": "select 1;", "read_only": False})

    def test_parse_content_range_reads_total_count(self):
        self.assertEqual(self.mod.parse_content_range("0-0/106"), 106)
        self.assertIsNone(self.mod.parse_content_range("0-0/*"))
        self.assertIsNone(self.mod.parse_content_range(""))

    def test_verify_table_uses_anon_rest_and_count_header(self):
        response = Mock()
        response.headers = {"content-range": "0-0/616"}
        response.json.return_value = [{"id": "ndss-2026-demo", "pdf_url": "https://example.test/demo.pdf"}]
        response.raise_for_status.return_value = None
        with patch.object(self.mod.requests, "get", return_value=response) as get:
            count = self.mod.verify_table(
                supabase_url="https://example.supabase.co",
                anon_key="anon-key",
                table="ndss_papers",
                expected_count=600,
            )
        self.assertEqual(count, 616)
        args, kwargs = get.call_args
        self.assertEqual(args[0], "https://example.supabase.co/rest/v1/ndss_papers")
        self.assertEqual(kwargs["headers"]["apikey"], "anon-key")
        self.assertEqual(kwargs["headers"]["Prefer"], "count=exact")

    def test_verify_rpc_posts_payload_to_rest_rpc_endpoint(self):
        response = Mock()
        response.json.return_value = [{"id": "osdi-2025-demo", "pdf_url": "https://example.test/demo.pdf"}]
        response.raise_for_status.return_value = None
        with patch.object(self.mod.requests, "post", return_value=response) as post:
            rows = self.mod.verify_rpc(
                supabase_url="https://example.supabase.co",
                anon_key="anon-key",
                rpc_name="match_osdi_papers_bm25",
                payload={"query_text": "operating system", "match_count": 1},
            )
        self.assertEqual(len(rows), 1)
        args, kwargs = post.call_args
        self.assertEqual(args[0], "https://example.supabase.co/rest/v1/rpc/match_osdi_papers_bm25")
        self.assertEqual(kwargs["json"], {"query_text": "operating system", "match_count": 1})
        self.assertEqual(kwargs["headers"]["apikey"], "anon-key")

    def test_verify_flag_without_yes_stays_dry_run(self):
        argv = ["public_conference_supabase_deploy.py", "--verify"]
        with patch.object(sys, "argv", argv), patch.object(self.mod.requests, "post") as post, patch("sys.stdout", new_callable=io.StringIO):
            self.mod.main()
        post.assert_not_called()

    def test_build_sync_commands_uses_python_argument_arrays(self):
        commands = self.mod.build_sync_commands(raw_dir="/tmp/raw", run_date="20260629")
        self.assertEqual(len(commands), 4)
        first = commands[0]
        self.assertEqual(first[1], "src/maintain/sync.py")
        self.assertIn("--backend-key", first)
        self.assertIn("osdi", first)
        self.assertIn("--raw-input", first)
        self.assertIn("/tmp/raw/osdi.json", first)
        self.assertNotIn(";", " ".join(first))

    def test_sync_flag_without_yes_stays_dry_run(self):
        argv = ["public_conference_supabase_deploy.py", "--sync"]
        with patch.object(sys, "argv", argv), patch.object(self.mod.subprocess, "run") as run, patch("sys.stdout", new_callable=io.StringIO):
            self.mod.main()
        run.assert_not_called()

    def test_run_sync_commands_sets_pythonpath_and_runs_all_conferences(self):
        with patch.object(self.mod.subprocess, "run") as run:
            self.mod.run_sync_commands(raw_dir="/tmp/raw", run_date="20260629")
        self.assertEqual(run.call_count, 4)
        args, kwargs = run.call_args
        self.assertEqual(kwargs["cwd"], self.mod.ROOT_DIR)
        self.assertIn(str(self.mod.SRC_DIR), kwargs["env"]["PYTHONPATH"])
        self.assertEqual(args[0][1], "src/maintain/sync.py")


if __name__ == "__main__":
    unittest.main()
