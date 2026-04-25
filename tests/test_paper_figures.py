import importlib.util
import io
import json
import os
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

    def test_extract_figures_with_pdffigures2_payload(self):
        with tempfile.TemporaryDirectory() as d:
            tmp_dir = Path(d)
            pdf_path = tmp_dir / "sample.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\n")
            output_dir = tmp_dir / "out"

            render_img = self._make_png_bytes((640, 480), (20, 180, 120))

            original_resolve = self.mod._resolve_pdffigures2_jar
            original_which = self.mod.shutil.which
            original_run = self.mod.subprocess.run

            class DummyResult:
                def __init__(self):
                    self.returncode = 0
                    self.stdout = ""
                    self.stderr = ""

            def fake_run(cmd, stdout=None, stderr=None, text=None, check=None):
                input_dir = Path(cmd[4])
                data_dir = Path(cmd[6])
                image_dir = Path(cmd[8])
                base_name = next(input_dir.glob("*.pdf")).stem
                image_dir.mkdir(parents=True, exist_ok=True)
                data_dir.mkdir(parents=True, exist_ok=True)
                image_path = image_dir / f"{base_name}-Figure1-1.png"
                image_path.write_bytes(render_img)
                payload = {
                    "figures": [
                        {
                            "renderURL": str(image_path),
                            "caption": "Figure 1. Demo caption",
                            "page": 0,
                        }
                    ]
                }
                (data_dir / f"{base_name}.json").write_text(
                    json.dumps(payload),
                    encoding="utf-8",
                )
                return DummyResult()

            self.mod._resolve_pdffigures2_jar = lambda: "/tmp/pdffigures2.jar"
            self.mod.shutil.which = lambda name: "/usr/bin/java" if name == "java" else original_which(name)
            self.mod.subprocess.run = fake_run
            try:
                figures = self.mod._extract_figures_with_pdffigures2(
                    str(pdf_path),
                    str(output_dir),
                    "assets/figures/arxiv/sample",
                )
            finally:
                self.mod._resolve_pdffigures2_jar = original_resolve
                self.mod.shutil.which = original_which
                self.mod.subprocess.run = original_run

            self.assertEqual(len(figures), 1)
            self.assertEqual(figures[0]["caption"], "Figure 1. Demo caption")
            self.assertEqual(figures[0]["page"], 1)
            self.assertTrue((output_dir / "fig-001.webp").exists())
            meta = json.loads((output_dir / "meta.json").read_text(encoding="utf-8"))
            self.assertEqual(meta["extractor"], "pdffigures2")


if __name__ == "__main__":
    unittest.main()
