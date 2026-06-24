import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


def _load_module():
    root = Path(__file__).resolve().parents[1]
    if "fitz" not in sys.modules:
        fitz_stub = types.ModuleType("fitz")
        fitz_stub.open = lambda *args, **kwargs: None
        sys.modules["fitz"] = fitz_stub
    if "llm" not in sys.modules:
        llm_stub = types.ModuleType("llm")

        class DummyDeepSeekClient:
            def __init__(self, *args, **kwargs):
                pass

        llm_stub.DeepSeekClient = DummyDeepSeekClient
        llm_stub.resolve_max_output_tokens = lambda default=393216: default
        sys.modules["llm"] = llm_stub

    src_path = root / "src" / "6.generate_docs.py"
    spec = importlib.util.spec_from_file_location("gen6_mod_merge", src_path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class UpdateSidebarMergeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_module()

    def _run_update(self, sidebar_path, date_str, deep, quick, evidence=None):
        self.mod.update_sidebar(
            sidebar_path=sidebar_path,
            date_str=date_str,
            deep_entries=deep,
            quick_entries=quick,
            paper_evidence_by_id=evidence or {},
        )

    def test_extract_day_block_papers_groups_by_section(self):
        block = [
            "    * 精读区\n",
            '      * <a class="dpr-sidebar-item-link" href="#/papers/A" data-sidebar-item="">A</a>\n',
            "    * 速读区\n",
            '      * <a class="dpr-sidebar-item-link" href="#/papers/B" data-sidebar-item="">B</a>\n',
        ]
        deep, quick = self.mod._extract_day_block_papers(block)
        self.assertEqual(len(deep), 1)
        self.assertEqual(len(quick), 1)
        self.assertIn("#/papers/A", deep[0])
        self.assertIn("#/papers/B", quick[0])

    def test_two_runs_same_date_merge_papers(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidebar = Path(tmp) / "_sidebar.md"
            sidebar.write_text("* [首页](/)\n", encoding="utf-8")

            # Run A: NLP profile, papers A1 (deep), A2 (quick)
            self._run_update(
                str(sidebar),
                "20260624",
                deep=[("papers/A1", "NLP Paper 1", [])],
                quick=[("papers/A2", "NLP Paper 2", [])],
            )
            after_a = sidebar.read_text(encoding="utf-8")
            self.assertIn("#/papers/A1", after_a)
            self.assertIn("#/papers/A2", after_a)

            # Run B: CV profile (same date), papers B1 (deep), B2 (quick)
            self._run_update(
                str(sidebar),
                "20260624",
                deep=[("papers/B1", "CV Paper 1", [])],
                quick=[("papers/B2", "CV Paper 2", [])],
            )
            after_b = sidebar.read_text(encoding="utf-8")

            # All four papers should still be present
            self.assertIn("#/papers/A1", after_b)
            self.assertIn("#/papers/A2", after_b)
            self.assertIn("#/papers/B1", after_b)
            self.assertIn("#/papers/B2", after_b)

            # Day marker appears exactly once
            self.assertEqual(after_b.count("<!--dpr-date:20260624-->"), 1)

    def test_new_papers_first_existing_appended(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidebar = Path(tmp) / "_sidebar.md"
            sidebar.write_text("* [首页](/)\n", encoding="utf-8")
            self._run_update(
                str(sidebar),
                "20260624",
                deep=[("papers/OLD", "Old Paper", [])],
                quick=[],
            )
            self._run_update(
                str(sidebar),
                "20260624",
                deep=[("papers/NEW", "New Paper", [])],
                quick=[],
            )
            text = sidebar.read_text(encoding="utf-8")
            pos_new = text.find("#/papers/NEW")
            pos_old = text.find("#/papers/OLD")
            self.assertGreater(pos_new, 0)
            self.assertGreater(pos_old, 0)
            self.assertLess(pos_new, pos_old, "new papers should appear before existing")

    def test_duplicate_paper_id_not_duplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidebar = Path(tmp) / "_sidebar.md"
            sidebar.write_text("* [首页](/)\n", encoding="utf-8")
            self._run_update(
                str(sidebar),
                "20260624",
                deep=[("papers/X", "X", [])],
                quick=[],
            )
            self._run_update(
                str(sidebar),
                "20260624",
                deep=[("papers/X", "X updated", []), ("papers/Y", "Y", [])],
                quick=[],
            )
            text = sidebar.read_text(encoding="utf-8")
            self.assertEqual(text.count('href="#/papers/X"'), 1)
            self.assertIn("#/papers/Y", text)

    def test_section_only_created_when_papers_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            sidebar = Path(tmp) / "_sidebar.md"
            sidebar.write_text("* [首页](/)\n", encoding="utf-8")
            # First run: only quick papers
            self._run_update(
                str(sidebar),
                "20260624",
                deep=[],
                quick=[("papers/Q1", "Quick 1", [])],
            )
            text1 = sidebar.read_text(encoding="utf-8")
            self.assertNotIn("精读区", text1)
            self.assertIn("速读区", text1)

            # Second run: adds a deep paper, quick section should remain merged
            self._run_update(
                str(sidebar),
                "20260624",
                deep=[("papers/D1", "Deep 1", [])],
                quick=[],
            )
            text2 = sidebar.read_text(encoding="utf-8")
            self.assertIn("精读区", text2)
            self.assertIn("速读区", text2)
            self.assertIn("#/papers/D1", text2)
            self.assertIn("#/papers/Q1", text2)


if __name__ == "__main__":
    unittest.main()
