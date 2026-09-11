import json
import html
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from requests import HTTPError, Response

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import starter_pack_reading as reading


def paper(pid="2501.12345v1", **changes):
    return {
        "id": pid,
        "canonical_id": "arxiv:" + pid,
        "title": "A test paper",
        "abstract": "Abstract",
        "bucket": "core",
        "score": 9,
        "source": "arxiv",
        "publication_window_status": "included",
        **changes,
    }


class ReadingTests(unittest.TestCase):
    def test_ineligible_representative_projects_qualified_arxiv_version(self):
        arxiv = paper(
            "2509.20384", published="2025-09-24", publication_date="2025-09-24"
        )
        representative = paper(
            "sp-id",
            source="IEEE-SP-2026-CSDL",
            conference="IEEE_SP",
            conference_year=2026,
            canonical_id="arxiv:2509.20384",
            conference_acceptance_status="unverified",
            publication_window_status="uncertain",
            pdf_url="https://ieee.example/wrong.pdf",
            official_pdf_url="https://ieee.example/also-wrong.pdf",
            doi="10.1234/conference",
            publication_date="2026",
            categories=["conference"],
            primary_category="security",
            versions=[arxiv],
            route_aliases=["conference/old/page"],
        )
        selected = reading.select_reading_papers([representative])[0]
        self.assertEqual(selected["id"], "2509.20384")
        self.assertEqual(selected["source"], "arxiv")
        self.assertEqual(selected["publication_date"], "2025-09-24")
        self.assertNotIn("conference", selected)
        self.assertNotIn("pdf_url", selected)
        self.assertNotIn("official_pdf_url", selected)
        self.assertNotIn("doi", selected)
        self.assertNotIn("categories", selected)
        self.assertNotIn("primary_category", selected)
        self.assertEqual(selected["canonical_id"], "arxiv:2509.20384")
        self.assertEqual(selected["score"], 9)
        self.assertEqual(selected["route_aliases"], ["conference/old/page"])

    def test_existing_v1_and_v2_reuses_v2_even_when_v1_is_indexed_first(self):
        generator = self.generator()
        complete = {
            key: "已有"
            for key in (
                "title_zh",
                "tldr",
                "motivation",
                "method",
                "result",
                "conclusion",
            )
        }
        generator._parse_front_matter.side_effect = lambda text: {
            **complete,
            "id": "2501.12345v1" if "V1" in text else "2501.12345v2",
            "reading_section": "deep",
            "tags": ["query:ATSP"],
        }
        generator.extract_section_tail.return_value = "总结（完）"
        with tempfile.TemporaryDirectory() as root, patch.object(
            reading, "_generator", return_value=generator
        ):
            docs = Path(root) / "docs"
            old_routes = [
                "20250101-20251231/2501.12345v1",
                "20250102-20260101/2501.12345v2",
            ]
            for version, route in enumerate(old_routes, 1):
                document = docs / (route + ".md")
                document.parent.mkdir(parents=True)
                document.write_text(f"V{version}\n## 摘要\n用户笔记")
            (docs / "_sidebar.md").write_text(
                "\n".join(f'<a href="#/{route}">Old</a>' for route in old_routes)
            )
            result = reading.prepare_reading(
                [paper("2501.12345v2")], root, "ATSP", "run", "2025-09-11", "2026-09-11"
            )
            self.assertEqual(result[0]["route"], old_routes[1])
            self.assertFalse((docs / "20250911-20260910").exists())
            generator.create_llm_client.assert_not_called()
            generator.build_markdown_content.assert_not_called()

    def test_conference_same_id_different_meeting_or_year_is_not_reused(self):
        generator = self.generator()
        generator._parse_front_matter.return_value = {
            "id": "shared-id",
            "doi": "10.1234/shared",
        }
        with tempfile.TemporaryDirectory() as root:
            docs = Path(root) / "docs"
            row = paper(
                "shared-id",
                source="ICML",
                conference="ICML",
                conference_year=2025,
                doi="10.1234/shared",
            )
            for namespace, expected in [
                ("icml-2025", True),
                ("iclr-2025", False),
                ("icml-2024", False),
            ]:
                route = f"conference/{namespace}/shared-id"
                path = docs / (route + ".md")
                path.parent.mkdir(parents=True)
                path.write_text("Existing")
                self.assertEqual(
                    reading._route_is_selected_version(docs, route, row, generator),
                    expected,
                )

    def test_qualified_representative_keeps_identity_and_never_borrows_other_pdf(self):
        generator = self.generator()
        row = paper(
            versions=[
                paper(
                    "wrong",
                    source="IEEE_SP",
                    publication_window_status="uncertain",
                    conference_acceptance_status="unverified",
                    pdf_url="https://example.org/wrong.pdf",
                )
            ]
        )
        self.assertEqual(reading.select_reading_papers([row])[0]["id"], row["id"])
        with tempfile.TemporaryDirectory() as root, patch.object(
            reading, "_generator", return_value=generator
        ):
            reading.prepare_reading(
                [row], root, "RL", "run", "2025-09-11", "2026-09-11"
            )
            self.assertEqual(
                generator.ensure_text_content.call_args.args[0],
                "https://arxiv.org/pdf/2501.12345v1",
            )

    def test_ineligible_conference_route_is_untouched_and_arxiv_page_is_created(self):
        generator = self.generator()
        generator._parse_front_matter.side_effect = lambda text: (
            {
                "id": "sp-id",
                "canonical_id": "arxiv:2509.20384",
                "pdf": "https://ieee.example/wrong.pdf",
            }
            if "旧会议版" in text
            else {}
        )
        with tempfile.TemporaryDirectory() as root, patch.object(
            reading, "_generator", return_value=generator
        ):
            docs = Path(root) / "docs"
            old = docs / "conference/ieee-sp-2026/old.md"
            old.parent.mkdir(parents=True)
            old.write_text("旧会议版正文与用户笔记")
            old.with_suffix(".txt").write_text("旧会议版全文")
            (docs / "_sidebar.md").write_text(
                '<a href="#/conference/ieee-sp-2026/old">旧论文</a>'
            )
            version = paper(
                "2509.20384", published="2025-09-24", publication_date="2025-09-24"
            )
            row = paper(
                "sp-id",
                source="IEEE-SP-2026-CSDL",
                conference="IEEE_SP",
                conference_year=2026,
                canonical_id="arxiv:2509.20384",
                conference_acceptance_status="unverified",
                publication_window_status="uncertain",
                pdf_url="https://ieee.example/wrong.pdf",
                versions=[version],
                route_aliases=["conference/ieee-sp-2026/old"],
            )
            result = reading.prepare_reading(
                [row], root, "RL", "run", "2025-09-11", "2026-09-11"
            )[0]
            self.assertEqual(result["route"], "20250911-20260910/2509.20384")
            self.assertEqual(result["source"], "arxiv")
            self.assertEqual(
                generator.ensure_text_content.call_args.args[0],
                "https://arxiv.org/pdf/2509.20384",
            )
            self.assertEqual(old.read_text(), "旧会议版正文与用户笔记")
            self.assertEqual(old.with_suffix(".txt").read_text(), "旧会议版全文")
            self.assertIn("旧论文", (docs / "_sidebar.md").read_text())
            self.assertIn("reading_route_reuse_skipped", result)

    def test_route_reuse_requires_real_identifier_not_url_substring(self):
        self.assertEqual(
            reading._identities(
                {"link": "https://example.org/reference/10.1234/paper"}
            ),
            set(),
        )
        self.assertEqual(
            reading._identities({"pdf_url": "https://not-arxiv.org/pdf/2501.12345v2"}),
            set(),
        )
        for row, expected in [
            ({"canonical_id": "doi:10.1234/Paper"}, "doi:10.1234/paper"),
            ({"link": "https://doi.org/10.1234/Paper?download=1"}, "doi:10.1234/paper"),
            ({"canonical_id": "arxiv:2501.12345v2"}, "arxiv:2501.12345"),
            ({"paper_id": "2501.12345v2"}, "arxiv:2501.12345"),
        ]:
            self.assertEqual(reading._identities(row), {expected})

    def setUp(self):
        verifier = patch.object(
            reading,
            "verify_publications",
            side_effect=lambda papers, root, **kwargs: papers,
        )
        self.verify_publications = verifier.start()
        self.addCleanup(verifier.stop)

    def test_selection_excludes_uncertain_notice_missing_abstract(self):
        rows = [
            paper(),
            paper("2", bucket="related", score=10),
            paper("3", bucket="notice"),
            paper("4", publication_window_status="uncertain"),
            paper("5", abstract=""),
        ]
        result = reading.select_reading_papers(rows)
        self.assertEqual([row["id"] for row in result], ["2501.12345v1", "2"])
        mixed = paper(
            versions=[
                {"publication_window_status": "uncertain"},
                {"publication_window_status": "included"},
            ]
        )
        self.assertEqual(len(reading.select_reading_papers([mixed])), 1)
        unverified = paper(
            source="ICML",
            conference_acceptance_status="unverified",
            versions=[
                {
                    "source": "ICML",
                    "publication_window_status": "included",
                    "conference_acceptance_status": "unverified",
                }
            ],
        )
        self.assertEqual(reading.select_reading_papers([unverified]), [])
        unverified["versions"].append(paper("2501.12345v1"))
        self.assertEqual(len(reading.select_reading_papers([unverified])), 1)
        for invalid in (21, -1, True, 1.5):
            with self.assertRaises(ValueError):
                reading.select_reading_papers([], invalid)

    def test_id_and_doi_match_versions_without_title_guessing(self):
        self.assertEqual(
            reading._identities({"id": "2501.12345v2"}),
            reading._identities({"link": "https://arxiv.org/abs/2501.12345v1"}),
        )
        self.assertEqual(
            reading._identities({"doi": "10.1234/ABC"}),
            reading._identities({"link": "https://doi.org/10.1234/abc"}),
        )
        self.assertEqual(reading._identities({"title": "Same title"}), set())

    def generator(self):
        generator = Mock()
        generator.PaperFulltextUnavailable = type("Unavailable", (Exception,), {})
        generator._parse_front_matter.return_value = {}
        generator.build_markdown_content.return_value = (
            "---\ntitle: Test\n---\n## Abstract\nAbstract\n"
        )
        generator.upsert_front_matter_field.side_effect = lambda text, key, value: (
            text,
            True,
        )
        generator.create_llm_client.return_value = SimpleNamespace(kwargs={})
        generator.ensure_reading_content.return_value = {
            "reading_section": "deep",
            "evidence": "中文短说明",
        }
        return generator

    def test_new_arxiv_uses_native_generator_and_cumulative_state(self):
        generator = self.generator()
        with tempfile.TemporaryDirectory() as root, patch.object(
            reading, "_generator", return_value=generator
        ):
            result = reading.prepare_reading(
                [paper()], root, "ATSP", "run", "2025-09-11", "2026-09-11"
            )
            self.assertEqual(result[0]["route"], "20250911-20260910/2501.12345v1")
            self.assertEqual(result[0]["reading_status"], "complete")
            self.assertEqual(generator.ensure_reading_content.call_args.args[1], "deep")
            self.assertTrue(
                generator.ensure_reading_content.call_args.kwargs["require_complete"]
            )
            self.assertTrue(
                generator.ensure_text_content.call_args.args[1].endswith(".txt")
            )
            state = json.loads(
                (Path(root) / "docs/20250911-20260910/_daily_state.json").read_text()
            )
            self.assertEqual(state["papers"][0]["paper_id"], "2501.12345v1")
            generator.update_sidebar.assert_called_once()
            self.assertEqual(len(self.verify_publications.call_args.args[0]), 1)
            self.assertTrue(self.verify_publications.call_args.kwargs["resolve_pdfs"])

    def test_existing_complete_content_and_notes_not_rewritten_or_called(self):
        generator = self.generator()
        complete = {
            key: "已有"
            for key in (
                "title_zh",
                "tldr",
                "motivation",
                "method",
                "result",
                "conclusion",
            )
        }
        generator._parse_front_matter.return_value = {
            **complete,
            "id": "2501.12345v1",
            "reading_section": "deep",
        }
        generator.extract_section_tail.return_value = "总结（完）"
        with tempfile.TemporaryDirectory() as root, patch.object(
            reading, "_generator", return_value=generator
        ):
            docs = Path(root) / "docs"
            target = docs / "20250910-20260909/2501.12345v1.md"
            target.parent.mkdir(parents=True)
            target.write_text("## 摘要\n旧摘要\n用户笔记不得重写")
            (docs / "_sidebar.md").write_text(
                '<a href="#/20250910-20260909/2501.12345v1">Old</a>'
            )
            result = reading.prepare_reading(
                [paper("2501.12345v1")], root, "ATSP", "run", "2025-09-11", "2026-09-11"
            )
            self.assertEqual(result[0]["route"], "20250910-20260909/2501.12345v1")
            self.assertEqual(result[0]["tldr"], "已有")
            self.assertIn("用户笔记不得重写", target.read_text())
            generator.ensure_reading_content.assert_not_called()
            generator.create_llm_client.assert_not_called()
            generator.update_sidebar.assert_not_called()

    def test_unavailable_fulltext_is_not_deep_success(self):
        generator = self.generator()
        generator.ensure_text_content.side_effect = generator.PaperFulltextUnavailable(
            "该版本已撤回"
        )
        with tempfile.TemporaryDirectory() as root, patch.object(
            reading, "_generator", return_value=generator
        ):
            result = reading.prepare_reading(
                [paper()], root, "ATSP", "run", "2025-09-11", "2026-09-11"
            )
            self.assertEqual(result[0]["reading_status"], "unavailable")
            self.assertEqual(
                generator.ensure_reading_content.call_args.args[1], "quick"
            )
            self.assertIn("撤回", result[0]["reading_reason"])

    def test_http_403_and_404_unavailable_but_transient_errors_retry(self):
        for status in (403, 404, 429, 503):
            with self.subTest(status=status):
                generator = self.generator()
                response = Response()
                response.status_code = status
                generator.ensure_text_content.side_effect = HTTPError(
                    f"HTTP {status}", response=response
                )
                with tempfile.TemporaryDirectory() as root, patch.object(
                    reading, "_generator", return_value=generator
                ):
                    if status in (403, 404):
                        result = reading.prepare_reading(
                            [paper()], root, "ATSP", "run", "2025-09-11", "2026-09-11"
                        )
                        self.assertEqual(result[0]["reading_status"], "unavailable")
                        self.assertIn(f"HTTP {status}", result[0]["reading_reason"])
                        self.assertNotIn("撤回", result[0]["reading_reason"])
                        self.assertEqual(
                            generator.ensure_reading_content.call_args.args[1], "quick"
                        )
                    else:
                        with self.assertRaises(HTTPError):
                            reading.prepare_reading(
                                [paper()],
                                root,
                                "ATSP",
                                "run",
                                "2025-09-11",
                                "2026-09-11",
                            )
                        generator.update_sidebar.assert_not_called()

    def test_generation_failure_propagates_for_resume(self):
        generator = self.generator()
        generator.ensure_reading_content.side_effect = RuntimeError("未完整生成")
        with tempfile.TemporaryDirectory() as root, patch.object(
            reading, "_generator", return_value=generator
        ):
            with self.assertRaisesRegex(RuntimeError, "未完整生成"):
                reading.prepare_reading(
                    [paper()], root, "ATSP", "run", "2025-09-11", "2026-09-11"
                )
            generator.update_sidebar.assert_not_called()

    def test_conference_navigation_preserves_existing_group_and_daily(self):
        with tempfile.TemporaryDirectory() as root:
            docs = Path(root) / "docs"
            docs.mkdir()
            sidebar = docs / "_sidebar.md"
            sidebar.write_text("* Daily Papers\n  * 旧日报\n    * 保留用户条目\n")
            document = docs / "conference/icml-2025/paper-1.md"
            document.parent.mkdir(parents=True)
            document.write_text("---\ntitle: test\n---")
            row = paper(
                "icml-1", source="ICML", conference="ICML", conference_year=2025
            )
            args = (
                docs,
                row,
                "conference/icml-2025/paper-1",
                {"evidence": "关联说明"},
                "ATSP",
                "20250911-20260910",
                "日期区间",
                self.generator(),
            )
            reading._attach_navigation(*args)
            first = sidebar.read_text()
            self.assertIn("* Conference Papers", first)
            self.assertIn("dpr-conference:icml-2025", first)
            self.assertIn("保留用户条目", first)
            self.assertIn('href="#/conference/icml-2025/paper-1"', first)
            reading._attach_navigation(*args)
            self.assertEqual(sidebar.read_text(), first)

    def test_code_root_guard_permits_fork_only(self):
        for repository in ("", "ziwenhahaha/daily-paper-reader"):
            with patch.dict("os.environ", {"GITHUB_REPOSITORY": repository}):
                with self.assertRaisesRegex(ValueError, "主仓库"):
                    reading.prepare_reading(
                        [], ROOT, "ATSP", "run", "2025-09-11", "2026-09-11"
                    )
        with patch.dict("os.environ", {"GITHUB_REPOSITORY": "5-xj/daily-paper-reader"}):
            self.assertEqual(
                reading.prepare_reading(
                    [], ROOT, "ATSP", "run", "2025-09-11", "2026-09-11"
                ),
                [],
            )

    def test_existing_pdf_frontmatter_and_md_href_reused(self):
        generator = self.generator()
        generator._parse_front_matter.return_value = {
            "id": "icml-existing",
            "pdf": "https://openreview.net/pdf?id=real",
        }
        with tempfile.TemporaryDirectory() as root, patch.object(
            reading, "_generator", return_value=generator
        ):
            docs = Path(root) / "docs"
            document = docs / "conference/icml-2025/existing.md"
            document.parent.mkdir(parents=True)
            document.write_text("## Abstract\nExisting")
            sidebar = docs / "_sidebar.md"
            sidebar.write_text(
                '<a href="/conference/icml-2025/existing.md">Existing</a>'
            )
            row = paper(
                "icml-existing", source="ICML", conference="ICML", conference_year=2025
            )
            result = reading.prepare_reading(
                [row], root, "ATSP", "run", "2025-09-11", "2026-09-11"
            )
            self.assertEqual(result[0]["route"], "conference/icml-2025/existing")
            self.assertEqual(
                generator.ensure_text_content.call_args.args[0],
                "https://openreview.net/pdf?id=real",
            )
            self.assertEqual(
                sidebar.read_text(),
                '<a href="/conference/icml-2025/existing.md">Existing</a>',
            )

    def test_new_conference_uses_release_date_and_openreview_pdf(self):
        generator = self.generator()
        with tempfile.TemporaryDirectory() as root, patch.object(
            reading, "_generator", return_value=generator
        ):
            row = paper(
                "icml-new",
                source="ICML",
                conference="ICML",
                conference_year=2025,
                published="2024-09-01",
                publication_date="2025-07-13",
                publication_date_precision="day",
                publication_date_source="https://official.example/proceedings",
                publication_date_kind="proceedings",
                link="https://openreview.net/forum?id=real",
            )
            reading.prepare_reading(
                [row], root, "ATSP", "run", "2025-09-11", "2026-09-11"
            )
            self.assertEqual(
                generator.ensure_text_content.call_args.args[0],
                "https://openreview.net/pdf?id=real",
            )
            fields = {
                call.args[1]: call.args[2]
                for call in generator.upsert_front_matter_field.call_args_list
            }
            self.assertIn("publication_date_precision", fields)
            self.assertIn("publication_date_source", fields)
            generator.yaml_escape_value.assert_any_call("2025-07-13")

    def test_official_conference_pdf_updates_only_frontmatter(self):
        generator = self.generator()
        generator._parse_front_matter.return_value = {
            "id": "icml-existing",
            "pdf": "https://openreview.net/pdf?id=old",
        }
        with tempfile.TemporaryDirectory() as root, patch.object(
            reading, "_generator", return_value=generator
        ):
            docs = Path(root) / "docs"
            document = docs / "conference/icml-2025/existing.md"
            document.parent.mkdir(parents=True)
            document.write_text("## Abstract\n用户笔记")
            row = paper(
                "icml-existing",
                source="ICML",
                conference="ICML",
                conference_year=2025,
                official_pdf_url="https://proceedings.mlr.press/v267/paper.pdf",
                official_link="https://proceedings.mlr.press/v267/paper.html",
                conference_acceptance_status="accepted",
            )
            reading.prepare_reading(
                [row], root, "ATSP", "run", "2025-09-11", "2026-09-11"
            )
            self.assertEqual(
                generator.ensure_text_content.call_args.args[0], row["official_pdf_url"]
            )
            self.assertIn("用户笔记", document.read_text())
            written = [
                call.args[1]
                for call in generator.upsert_front_matter_field.call_args_list
            ]
            self.assertIn("official_link", written)
            self.assertIn("pdf", written)

    def test_arxiv_existing_route_keeps_original_pdf_even_for_merged_conference(self):
        generator = self.generator()
        generator._parse_front_matter.return_value = {
            "id": "2501.12345v1",
            "pdf": "https://arxiv.org/pdf/2501.12345v1",
        }
        with tempfile.TemporaryDirectory() as root, patch.object(
            reading, "_generator", return_value=generator
        ):
            docs = Path(root) / "docs"
            document = docs / "20250910-20260909/2501.12345v1.md"
            document.parent.mkdir(parents=True)
            document.write_text("## Abstract\n用户笔记")
            row = paper(
                source="ICML",
                conference="ICML",
                conference_year=2025,
                official_pdf_url="https://proceedings.mlr.press/v267/paper.pdf",
                conference_acceptance_status="accepted",
            )
            result = reading.prepare_reading(
                [row], root, "ATSP", "run", "2025-09-11", "2026-09-11"
            )
            self.assertEqual(
                generator.ensure_text_content.call_args.args[0],
                "https://proceedings.mlr.press/v267/paper.pdf",
            )
            self.assertTrue(result[0]["route"].startswith("conference/"))
            self.assertEqual(document.read_text(), "## Abstract\n用户笔记")
            self.assertEqual(
                result[0]["reading_route_reuse_skipped"][0]["route"],
                "20250910-20260909/2501.12345v1",
            )

    def test_unsafe_route_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            docs = Path(root) / "docs"
            docs.mkdir()
            (Path(root) / "outside.md").write_text("outside")
            self.assertIsNone(reading._safe_route(docs, "../outside"))
            self.assertIsNone(reading._safe_route(docs, "https://evil.invalid/page"))

    def test_sr_then_rl_merges_tags_in_original_route_without_new_run(self):
        for route in (
            "20250910-20260909/2501.12345v1",
            "conference/icml-2025/existing",
        ):
            with self.subTest(route=route), tempfile.TemporaryDirectory() as root:
                docs = Path(root) / "docs"
                document = docs / (route + ".md")
                document.parent.mkdir(parents=True)
                document.write_text(
                    '---\ntags: ["query:SR", "paper:核心"]\n---\n用户笔记保持不变\n'
                )
                payload = {
                    "title": "论文",
                    "tags": [
                        {"kind": "query", "label": "SR"},
                        {"kind": "paper", "label": "核心"},
                    ],
                }
                sidebar = docs / "_sidebar.md"
                sidebar.write_text(
                    f'<a href="#/{route}" data-sidebar-item="{html.escape(json.dumps(payload), quote=True)}">Paper</a>'
                )
                state_path = document.parent / "_daily_state.json"
                state_path.write_text(
                    json.dumps(
                        {
                            "run_count": 7,
                            "papers": [
                                {
                                    "paper_id": "2501.12345v1",
                                    "route": route,
                                    "tags": payload["tags"],
                                }
                            ],
                        }
                    )
                )
                generator = reading._generator(root)
                with patch.object(
                    generator,
                    "create_llm_client",
                    side_effect=AssertionError("不应调用模型"),
                ):
                    reading._attach_navigation(
                        docs,
                        paper(),
                        route,
                        {},
                        "RL",
                        "20250911-20260910",
                        "新日期",
                        generator,
                    )
                    state = json.loads(state_path.read_text())
                    self.assertEqual(state["run_count"], 7)
                    self.assertIn(
                        {"kind": "query", "label": "RL"}, state["papers"][0]["tags"]
                    )
                    self.assertIn(
                        {"kind": "paper", "label": "核心"}, state["papers"][0]["tags"]
                    )
                    self.assertIn("query:RL", document.read_text())
                    self.assertIn("用户笔记保持不变", document.read_text())
                    self.assertEqual(sidebar.read_text().count("href="), 1)
                    self.assertIn("RL", sidebar.read_text())
                    snapshot = [
                        path.read_bytes() for path in (document, sidebar, state_path)
                    ]
                    reading._attach_navigation(
                        docs,
                        paper(),
                        route,
                        {},
                        "RL",
                        "20250911-20260910",
                        "新日期",
                        generator,
                    )
                    self.assertEqual(
                        snapshot,
                        [path.read_bytes() for path in (document, sidebar, state_path)],
                    )
                    self.assertFalse((docs / "20250911-20260910").exists())


if __name__ == "__main__":
    unittest.main()
