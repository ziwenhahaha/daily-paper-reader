import importlib.util
import io
import json
import os
import contextlib
import sys
import tempfile
import unittest
from pathlib import Path

import fitz
from PIL import Image


def _load_module(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)
    return mod


class PaperFiguresTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        src_dir = root / "src"
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        cls.mod = _load_module("paper_figures_mod", src_dir / "paper_figures.py")

    def _make_png_bytes(self, size, color):
        img = Image.new("RGB", size, color)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def test_extract_figures_from_pdf(self):
        with tempfile.TemporaryDirectory() as d:
            pdf_path = Path(d) / "sample.pdf"
            out_dir = Path(d) / "assets"

            big_img = self._make_png_bytes((640, 480), (220, 80, 80))
            small_img = self._make_png_bytes((80, 80), (80, 80, 220))

            doc = fitz.open()
            page = doc.new_page()
            page.insert_image(fitz.Rect(40, 40, 400, 320), stream=big_img)
            page.insert_image(fitz.Rect(420, 40, 500, 120), stream=small_img)
            doc.save(pdf_path)
            doc.close()

            figures = self.mod.extract_figures_from_pdf(
                str(pdf_path),
                str(out_dir),
                "assets/figures/arxiv/test-paper",
            )

            self.assertEqual(len(figures), 1)
            self.assertTrue(figures[0]["url"].endswith("fig-001.webp"))
            self.assertTrue((out_dir / "fig-001.webp").exists())

            meta_path = out_dir / "meta.json"
            self.assertTrue(meta_path.exists())
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            self.assertEqual(len(meta["figures"]), 1)
            self.assertEqual(meta["version"], 2)

    def test_papercropper_failure_is_reported_before_fallback(self):
        with tempfile.TemporaryDirectory() as d:
            tmp_dir = Path(d)
            pdf_path = tmp_dir / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")

            original_resolve = self.mod._resolve_papercropper
            original_run = self.mod.subprocess.run

            class DummyResult:
                returncode = 1
                stdout = "starting"
                stderr = "ModuleNotFoundError: No module named 'scipy'"

            def fake_run(*args, **kwargs):
                return DummyResult()

            self.mod._resolve_papercropper = lambda: (sys.executable, "/tmp/extract.py", "/tmp/model.pt")
            self.mod.subprocess.run = fake_run
            output = io.StringIO()
            try:
                with contextlib.redirect_stdout(output):
                    figures, tables = self.mod._extract_media_with_papercropper(
                        str(pdf_path),
                        str(tmp_dir / "figures"),
                        "assets/figures/arxiv/sample",
                        str(tmp_dir / "tables"),
                        "assets/tables/arxiv/sample",
                    )
            finally:
                self.mod._resolve_papercropper = original_resolve
                self.mod.subprocess.run = original_run

            self.assertEqual(figures, [])
            self.assertEqual(tables, [])
            self.assertIn("PaperCropper 表格/图表提取降级", output.getvalue())
            self.assertIn("No module named 'scipy'", output.getvalue())

    def test_papercropper_empty_output_is_reported(self):
        with tempfile.TemporaryDirectory() as d:
            tmp_dir = Path(d)
            pdf_path = tmp_dir / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")

            original_resolve = self.mod._resolve_papercropper
            original_run = self.mod.subprocess.run

            class DummyResult:
                returncode = 0
                stdout = "done"
                stderr = ""

            def fake_run(*args, **kwargs):
                return DummyResult()

            self.mod._resolve_papercropper = lambda: (sys.executable, "/tmp/extract.py", "/tmp/model.pt")
            self.mod.subprocess.run = fake_run
            output = io.StringIO()
            try:
                with contextlib.redirect_stdout(output):
                    figures, tables = self.mod._extract_media_with_papercropper(
                        str(pdf_path),
                        str(tmp_dir / "figures"),
                        "assets/figures/arxiv/sample",
                        str(tmp_dir / "tables"),
                        "assets/tables/arxiv/sample",
                    )
            finally:
                self.mod._resolve_papercropper = original_resolve
                self.mod.subprocess.run = original_run

            self.assertEqual(figures, [])
            self.assertEqual(tables, [])
            self.assertIn("执行完成但未产出 figure/table", output.getvalue())


if __name__ == "__main__":
    unittest.main()
