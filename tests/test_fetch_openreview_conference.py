import importlib.util
import pathlib
import sys
import unittest
from unittest import mock


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

    def test_resolve_target_years_prefers_explicit_years(self):
        self.assertEqual(
            self.mod.resolve_target_years(years="2025,2024", year_end=2026, year_count=3),
            [2025, 2024],
        )

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

    def test_fetch_openreview_submissions_rest_fallback_paginates_and_keeps_public_pdf_only(self):
        login_response = mock.Mock()
        login_response.status_code = 200
        login_response.json.return_value = {"token": "token-123"}
        login_response.raise_for_status.return_value = None

        group_response = mock.Mock()
        group_response.status_code = 200
        group_response.json.return_value = {
            "groups": [
                {
                    "content": {
                        "submission_id": {
                            "value": "ICML.cc/2026/Conference/-/Submission",
                        },
                    },
                },
            ],
        }
        group_response.raise_for_status.return_value = None

        def make_note(note_id, readers, pdf="/pdf/public.pdf"):
            return {
                "id": note_id,
                "forum": note_id,
                "readers": readers,
                "cdate": 1760560023346,
                "content": {
                    "title": {"value": f"Paper {note_id}"},
                    "abstract": {"value": "Abstract body"},
                    "authors": {"value": ["Alice"]},
                    "keywords": {"value": ["learning"]},
                    "pdf": {"value": pdf},
                    "venue": {"value": "ICML 2026 regular"},
                },
                "details": {"replies": []},
            }

        first_notes_response = mock.Mock()
        first_notes_response.status_code = 200
        first_notes_response.json.return_value = {
            "notes": [
                make_note("public-a", ["everyone"], "/pdf/a.pdf"),
                make_note("private-b", ["ICML.cc/2026/Conference"], "/pdf/b.pdf"),
            ],
            "count": 3,
        }
        first_notes_response.raise_for_status.return_value = None

        second_notes_response = mock.Mock()
        second_notes_response.status_code = 200
        second_notes_response.json.return_value = {
            "notes": [
                make_note("public-c", ["everyone"], "/pdf/c.pdf"),
            ],
            "count": 3,
        }
        second_notes_response.raise_for_status.return_value = None

        session = mock.Mock()
        session.post.return_value = login_response
        session.get.side_effect = [group_response, first_notes_response, second_notes_response]

        with mock.patch.object(self.mod.requests, "Session", return_value=session):
            papers = self.mod.fetch_openreview_submissions_via_rest(
                conference="ICML",
                years=[2026],
                username="user",
                password="pass",
                public_only=True,
                page_size=2,
            )

        self.assertEqual([paper["source_paper_id"] for paper in papers], ["public-a", "public-c"])
        self.assertEqual(papers[0]["pdf_url"], "https://openreview.net/pdf/a.pdf")
        note_calls = [
            call
            for call in session.get.call_args_list
            if call.kwargs.get("params", {}).get("invitation") == "ICML.cc/2026/Conference/-/Submission"
        ]
        self.assertEqual([call.kwargs["params"]["offset"] for call in note_calls], [0, 2])


if __name__ == "__main__":
    unittest.main()
