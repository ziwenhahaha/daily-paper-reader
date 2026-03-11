import importlib.util
import pathlib
import sys
import unittest


def _load_module(module_name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class NormalizeArxivIdTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module("select_mod", src_dir / "5.select_papers.py")

    def test_strips_version_suffix(self):
        self.assertEqual(self.mod.normalize_arxiv_id("2501.12345v1"), "2501.12345")
        self.assertEqual(self.mod.normalize_arxiv_id("2501.12345v2"), "2501.12345")
        self.assertEqual(self.mod.normalize_arxiv_id("2501.12345v10"), "2501.12345")

    def test_keeps_plain_id(self):
        self.assertEqual(self.mod.normalize_arxiv_id("2501.12345"), "2501.12345")

    def test_non_arxiv_id_unchanged(self):
        self.assertEqual(self.mod.normalize_arxiv_id("custom-paper-id"), "custom-paper-id")
        self.assertEqual(self.mod.normalize_arxiv_id("ABC123"), "abc123")

    def test_empty_and_none(self):
        self.assertEqual(self.mod.normalize_arxiv_id(""), "")
        self.assertEqual(self.mod.normalize_arxiv_id(None), "")

    def test_five_digit_id(self):
        self.assertEqual(self.mod.normalize_arxiv_id("2501.12345v3"), "2501.12345")


class BuildScoredPapersDeduplicationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module("select_mod", src_dir / "5.select_papers.py")

    def test_dedup_same_paper_different_versions(self):
        """Same paper with v1 and v2 should be merged, keeping higher score."""
        papers = [
            {"id": "2501.12345v1", "title": "Paper A", "abstract": "abs"},
            {"id": "2501.12345v2", "title": "Paper A", "abstract": "abs"},
        ]
        llm_ranked = [
            {
                "paper_id": "2501.12345v1",
                "score": 8.0,
                "evidence_cn": "v1 evidence",
                "tags": ["query:test"],
            },
            {
                "paper_id": "2501.12345v2",
                "score": 9.0,
                "evidence_cn": "v2 evidence",
                "tags": ["query:test"],
            },
        ]
        out = self.mod.build_scored_papers(papers, llm_ranked)
        self.assertEqual(len(out), 1)
        self.assertEqual(float(out[0]["llm_score"]), 9.0)
        self.assertEqual(out[0]["llm_evidence_cn"], "v2 evidence")

    def test_dedup_same_paper_versioned_and_plain(self):
        """Paper with version in papers list but plain in llm_ranked should still match."""
        papers = [
            {"id": "2501.12345v1", "title": "Paper A", "abstract": "abs"},
        ]
        llm_ranked = [
            {
                "paper_id": "2501.12345",
                "score": 8.5,
                "evidence_cn": "evidence",
                "tags": ["query:test"],
            },
        ]
        out = self.mod.build_scored_papers(papers, llm_ranked)
        self.assertEqual(len(out), 1)
        self.assertEqual(float(out[0]["llm_score"]), 8.5)

    def test_different_papers_not_merged(self):
        """Different papers should not be deduplicated."""
        papers = [
            {"id": "2501.12345", "title": "Paper A", "abstract": "abs"},
            {"id": "2501.67890", "title": "Paper B", "abstract": "abs"},
        ]
        llm_ranked = [
            {"paper_id": "2501.12345", "score": 8.0, "tags": []},
            {"paper_id": "2501.67890", "score": 9.0, "tags": []},
        ]
        out = self.mod.build_scored_papers(papers, llm_ranked)
        self.assertEqual(len(out), 2)


class BuildCandidatesDeduplicationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module("select_mod", src_dir / "5.select_papers.py")

    def test_dedup_scored_papers_by_normalized_id(self):
        """scored_papers with different versions of the same ID should be deduplicated."""
        scored = [
            {"id": "2501.12345v1", "title": "Paper A", "llm_score": 8.5},
            {"id": "2501.12345v2", "title": "Paper A", "llm_score": 9.0},
        ]
        out = self.mod.build_candidates(scored, [], set())
        self.assertEqual(len(out), 1)

    def test_seen_ids_normalized(self):
        """A seen ID with version should block the same paper without version."""
        scored = [
            {"id": "2501.12345", "title": "Paper A", "llm_score": 8.5},
        ]
        out = self.mod.build_candidates(scored, [], {"2501.12345v1"})
        self.assertEqual(len(out), 0)

    def test_carryover_dedup_with_scored(self):
        """Carryover and scored with different versions of same paper should not duplicate."""
        scored = [
            {"id": "2501.12345v2", "title": "Paper A", "llm_score": 9.0},
        ]
        carryover = [
            {"id": "2501.12345v1", "title": "Paper A", "llm_score": 8.5},
        ]
        out = self.mod.build_candidates(scored, carryover, set())
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
