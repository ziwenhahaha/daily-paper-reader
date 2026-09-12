"""重置后的Fork可能没有archive；年度报告提交不能依赖该目录。"""

from pathlib import Path
import os
import subprocess
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]


class EmptyArchiveWorkflowTest(unittest.TestCase):
    def test_conference_staging_accepts_no_publishable_paper_directory(self):
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/conference-paper-retrieval.yml").read_text()
        )
        step = next(
            s
            for s in workflow["jobs"]["retrieve"]["steps"]
            if s.get("name") == "Commit conference retrieval results"
        )
        staging = (
            "shopt -s nullglob\n"
            + step["run"].split("shopt -s nullglob", 1)[1].split("git commit -m", 1)[0]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=root, check=True)
            (root / "docs").mkdir()
            (root / "docs/_sidebar.md").write_text("")
            (root / "archive/20260909/rank").mkdir(parents=True)
            (
                root / "archive/20260909/rank/conference-icml-2025.supabase.llm.json"
            ).write_text("{}")
            result = subprocess.run(
                ["bash", "-e", "-c", staging],
                cwd=root,
                env=dict(
                    os.environ,
                    GITHUB_REPOSITORY_OWNER="test",
                    GITHUB_REPOSITORY="test/example",
                ),
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_commit_staging_works_in_reset_fork_without_archive(self):
        workflow = yaml.safe_load(
            (ROOT / ".github/workflows/daily-paper-reader.yml").read_text()
        )
        step = next(
            s
            for s in workflow["jobs"]["run"]["steps"]
            if s.get("name") == "Commit results"
        )
        # 保留完整条件分支；在首次提交前退出，避免截断 if 导致伪语法错误。
        staging = (
            'git() { if [ "$1" = commit ]; then exit 0; fi; command git "$@"; }\n'
            + step["run"]
        )
        for days in ("1", "90", "365"):
            with self.subTest(days=days), tempfile.TemporaryDirectory() as directory:
                self.check_daily_staging(directory, staging, days)

    def check_daily_staging(self, directory, staging, days):
        root = Path(directory)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        (root / "docs/long-range").mkdir(parents=True)
        (root / "docs/long-range/result.json").write_text("{}")
        (root / "config.yaml").write_text("subscriptions: {}")
        env = dict(
            os.environ,
            GITHUB_REPOSITORY_OWNER="test",
            GITHUB_REPOSITORY="test/example",
            REQUESTED_DAYS=days,
        )
        result = subprocess.run(
            ["bash", "-e", "-c", staging],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        staged = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only"], cwd=root, text=True
        )
        self.assertIn("docs/long-range/result.json", staged)
        self.assertEqual("config.yaml" in staged.splitlines(), days == "1")


if __name__ == "__main__":
    unittest.main()
