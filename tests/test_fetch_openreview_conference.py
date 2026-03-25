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


class FetchOpenReviewConferenceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = pathlib.Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module(
            "fetch_openreview_mod",
            src_dir / "maintain" / "fetchers" / "fetch_openreview.py",
        )

    def test_build_source_label(self):
        self.assertEqual(
            self.mod.build_source_label("NeurIPS", 2025, "Accepted"),
            "NeurIPS-2025-Accepted",
        )

    def test_iter_target_years(self):
        self.assertEqual(self.mod.iter_target_years(2026, 3), [2024, 2025, 2026])

    def test_build_venue_id_supports_aaai(self):
        self.assertEqual(
            self.mod.build_venue_id("AAAI", 2025),
            "AAAI.org/2025/Conference",
        )

    def test_normalize_openreview_submission_public_rejected(self):
        note = {
            "id": "note123",
            "forum": "forum123",
            "readers": ["everyone"],
            "cdate": 1735689600000,
            "content": {
                "title": {"value": "Test Submission"},
                "abstract": {"value": "Abstract body"},
                "authors": {"value": ["Alice", "Bob"]},
                "keywords": {"value": ["machine learning", "optimization"]},
                "pdf": {"value": "/pdf?id=forum123"},
            },
            "details": {
                "replies": [
                    {
                        "invitations": ["NeurIPS.cc/2025/Conference/-/Decision"],
                        "content": {
                            "decision": {"value": "Reject"},
                        },
                    }
                ]
            },
        }
        paper = self.mod.normalize_openreview_submission(
            note,
            conference="NeurIPS",
            year=2025,
            public_only=True,
        )
        self.assertIsNotNone(paper)
        self.assertEqual(paper["source"], "NeurIPS-2025-Rejected-Public")
        self.assertEqual(paper["source_paper_id"], "note123")
        self.assertEqual(paper["link"], "https://openreview.net/forum?id=forum123")
        self.assertTrue(paper["pdf_url"].endswith("forum123"))

    def test_normalize_openreview_submission_skips_nonpublic_without_pdf(self):
        note = {
            "id": "note456",
            "forum": "forum456",
            "readers": ["NeurIPS.cc/2025/Conference"],
            "content": {
                "title": {"value": "Private Submission"},
                "abstract": {"value": "Abstract body"},
            },
            "details": {"replies": []},
        }
        paper = self.mod.normalize_openreview_submission(
            note,
            conference="NeurIPS",
            year=2025,
            public_only=True,
        )
        self.assertIsNone(paper)


if __name__ == "__main__":
    unittest.main()
