import importlib.util
from pathlib import Path
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "request_pages_build", ROOT / "scripts/request_pages_build.py"
)
pages = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pages)


class PagesBuildTests(unittest.TestCase):
    def api(self, builds):
        values = [
            {
                "build_type": "legacy",
                "source": {"branch": "main", "path": "/"},
                "html_url": "https://example.github.io/repo/",
            },
            {"default_branch": "main"},
            {"status": "queued"},
            *builds,
        ]
        return Mock(side_effect=values)

    def test_waits_for_requested_commit_not_old_build(self):
        api = self.api(
            [
                {"commit": "b" * 40, "status": "built"},
                {"commit": "a" * 40, "status": "building"},
                {"commit": "a" * 40, "status": "built"},
            ]
        )
        result = pages.request_build(
            api, "owner/repo", "main", "a" * 40, sleep=lambda _: None
        )
        self.assertEqual(result["commit"], "a" * 40)
        self.assertEqual(
            api.call_args_list[2].args, ("POST", "/repos/owner/repo/pages/builds")
        )
        self.assertEqual(api.call_count, 6)

    def test_unsupported_mode_and_wrong_branch_never_mutate(self):
        for site in [
            {"build_type": "workflow", "source": {"branch": "main", "path": "/"}},
            {"build_type": "legacy", "source": {"branch": "gh-pages", "path": "/"}},
            {"source": {"branch": "main", "path": "/"}},
        ]:
            api = Mock(return_value=site)
            with self.assertRaises(RuntimeError):
                pages.request_build(api, "owner/repo", "main", "a" * 40)
            self.assertTrue(all(c.args[0] == "GET" for c in api.call_args_list))

    def test_failed_and_timed_out_builds_fail_workflow(self):
        with self.assertRaises(RuntimeError):
            pages.request_build(
                self.api([{"commit": "a" * 40, "status": "errored"}]),
                "owner/repo",
                "main",
                "a" * 40,
            )
        with self.assertRaises(TimeoutError):
            pages.request_build(self.api([]), "owner/repo", "main", "a" * 40, timeout=0)

    def test_workflow_explicit_pages_and_narrow_hidden_artifact(self):
        text = (ROOT / ".github/workflows/starter-pack.yml").read_text()
        self.assertIn("pages: write", text)
        self.assertIn("include-hidden-files: true", text)
        self.assertIn("scripts/request_pages_build.py", text)
        self.assertLess(
            text.index("git push origin"), text.index("scripts/request_pages_build.py")
        )


if __name__ == "__main__":
    unittest.main()
