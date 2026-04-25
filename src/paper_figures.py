from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List

import fitz
import requests
from PIL import Image


MIN_FIGURE_WIDTH = 240
MIN_FIGURE_HEIGHT = 180
MIN_FIGURE_AREA = 120_000
WEBP_QUALITY = 82
FIGURE_META_VERSION = 2
PDFFIGURES2_JAR_ENV = "PDFFIGURES2_JAR"
PDFFIGURES2_DEFAULT_CACHE = os.path.expanduser("~/.cache/dpr-tools/pdffigures2/pdffigures2.jar")
PDFFIGURES2_REPO_CACHE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools", "pdffigures2.jar"))


def _safe_asset_key(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "paper"
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text)
    text = text.strip("-._")
    return text or "paper"


def _relative_prefix(source_key: str, asset_key: str) -> str:
    return "/".join(["assets", "figures", source_key, _safe_asset_key(asset_key)])


def _absolute_dir(docs_dir: str, source_key: str, asset_key: str) -> str:
    return os.path.join(docs_dir, "assets", "figures", source_key, _safe_asset_key(asset_key))


def _load_cached_figures(meta_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(meta_path):
        return []
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            payload = json.load(f) or {}
    except Exception:
        return []
    if int(payload.get("version") or 0) != FIGURE_META_VERSION:
        return []
    figures = payload.get("figures")
    if not isinstance(figures, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in figures:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        out.append(
            {
                "url": url,
                "caption": str(item.get("caption") or "").strip(),
                "page": int(item.get("page") or 0),
                "index": int(item.get("index") or 0),
                "width": int(item.get("width") or 0),
                "height": int(item.get("height") or 0),
            }
        )
    return out


def _save_figures_meta(meta_path: str, figures: List[Dict[str, Any]], *, extractor: str) -> None:
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "version": FIGURE_META_VERSION,
                "extractor": extractor,
                "figures": figures,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def _download_pdf_bytes(pdf_url: str, timeout: int = 90) -> bytes:
    resp = requests.get(
        str(pdf_url or "").strip(),
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=max(int(timeout or 1), 1),
    )
    resp.raise_for_status()
    return resp.content


def _resolve_pdffigures2_jar() -> str:
    candidates = [
        str(os.getenv(PDFFIGURES2_JAR_ENV) or "").strip(),
        PDFFIGURES2_DEFAULT_CACHE,
        PDFFIGURES2_REPO_CACHE,
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return ""


def _load_image_size(path: str) -> tuple[int, int]:
    with Image.open(path) as img:
        img.load()
        return img.size


def _save_webp_from_path(src_path: str, dst_path: str) -> tuple[int, int]:
    with Image.open(src_path) as img:
        img.load()
        width, height = img.size
        if img.mode == "RGBA":
            bg = Image.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[-1])
            export_img = bg
        elif img.mode != "RGB":
            export_img = img.convert("RGB")
        else:
            export_img = img.copy()
        export_img.save(dst_path, format="WEBP", quality=WEBP_QUALITY, method=6)
        return width, height


def _extract_figures_with_pdffigures2(
    pdf_path: str,
    output_dir: str,
    relative_prefix: str,
) -> List[Dict[str, Any]]:
    jar_path = _resolve_pdffigures2_jar()
    java_path = shutil.which("java")
    if not jar_path or not java_path:
        return []

    with tempfile.TemporaryDirectory(prefix="pdffigures2_") as tmp_root:
        input_dir = os.path.join(tmp_root, "input")
        data_dir = os.path.join(tmp_root, "data")
        image_dir = os.path.join(tmp_root, "images")
        os.makedirs(input_dir, exist_ok=True)
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(image_dir, exist_ok=True)

        base_name = os.path.basename(pdf_path)
        truncated = os.path.splitext(base_name)[0]
        tmp_pdf = os.path.join(input_dir, base_name)
        shutil.copy2(pdf_path, tmp_pdf)

        cmd = [
            java_path,
            "-Dsun.java2d.cmm=sun.java2d.cmm.kcms.KcmsServiceProvider",
            "-jar",
            jar_path,
            input_dir,
            "-g",
            data_dir + os.sep,
            "-m",
            image_dir + os.sep,
            "-f",
            "png",
            "-q",
        ]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            return []

        json_path = os.path.join(data_dir, f"{truncated}.json")
        if not os.path.exists(json_path):
            return []
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                payload = json.load(f) or {}
        except Exception:
            return []

        raw_figures = payload.get("figures") if isinstance(payload, dict) else None
        if not isinstance(raw_figures, list):
            return []

        os.makedirs(output_dir, exist_ok=True)
        figures: List[Dict[str, Any]] = []
        seen_hash: set[str] = set()
        fig_index = 1
        for item in raw_figures:
            if not isinstance(item, dict):
                continue
            render_url = str(item.get("renderURL") or item.get("renderUrl") or "").strip()
            if not render_url or not os.path.exists(render_url):
                continue
            try:
                width, height = _load_image_size(render_url)
            except Exception:
                continue
            if width < MIN_FIGURE_WIDTH or height < MIN_FIGURE_HEIGHT or width * height < MIN_FIGURE_AREA:
                continue
            try:
                with open(render_url, "rb") as f:
                    sha = hashlib.sha256(f.read()).hexdigest()
            except Exception:
                continue
            if sha in seen_hash:
                continue
            seen_hash.add(sha)

            file_name = f"fig-{fig_index:03d}.webp"
            abs_path = os.path.join(output_dir, file_name)
            width, height = _save_webp_from_path(render_url, abs_path)
            page = int(item.get("page") or 0) + 1
            caption = str(item.get("caption") or "").strip()
            figures.append(
                {
                    "url": "/".join([relative_prefix.strip("/"), file_name]),
                    "caption": caption,
                    "page": page,
                    "index": fig_index,
                    "width": width,
                    "height": height,
                }
            )
            fig_index += 1

        if figures:
            _save_figures_meta(os.path.join(output_dir, "meta.json"), figures, extractor="pdffigures2")
        return figures


def extract_figures_from_pdf(
    pdf_path: str,
    output_dir: str,
    relative_prefix: str,
    *,
    min_width: int = MIN_FIGURE_WIDTH,
    min_height: int = MIN_FIGURE_HEIGHT,
    min_area: int = MIN_FIGURE_AREA,
) -> List[Dict[str, Any]]:
    os.makedirs(output_dir, exist_ok=True)
    figures: List[Dict[str, Any]] = []
    seen_xref: set[int] = set()
    seen_sha: set[str] = set()
    fig_index = 1

    with fitz.open(pdf_path) as doc:
        for page_idx in range(len(doc)):
            page = doc[page_idx]
            for image_info in page.get_images(full=True):
                xref = int(image_info[0] or 0)
                if xref <= 0 or xref in seen_xref:
                    continue
                seen_xref.add(xref)
                try:
                    raw = doc.extract_image(xref)
                except Exception:
                    continue
                image_bytes = raw.get("image") if isinstance(raw, dict) else None
                if not image_bytes:
                    continue
                sha = hashlib.sha256(image_bytes).hexdigest()
                if sha in seen_sha:
                    continue
                seen_sha.add(sha)

                try:
                    with Image.open(io.BytesIO(image_bytes)) as img:
                        img.load()
                        width, height = img.size
                        if width < min_width or height < min_height or width * height < min_area:
                            continue
                        if img.mode == "RGBA":
                            bg = Image.new("RGB", img.size, (255, 255, 255))
                            bg.paste(img, mask=img.split()[-1])
                            export_img = bg
                        elif img.mode != "RGB":
                            export_img = img.convert("RGB")
                        else:
                            export_img = img.copy()
                except Exception:
                    continue

                file_name = f"fig-{fig_index:03d}.webp"
                abs_path = os.path.join(output_dir, file_name)
                export_img.save(abs_path, format="WEBP", quality=WEBP_QUALITY, method=6)

                figures.append(
                    {
                        "url": "/".join([relative_prefix.strip("/"), file_name]),
                        "caption": "",
                        "page": page_idx + 1,
                        "index": fig_index,
                        "width": width,
                        "height": height,
                    }
                )
                fig_index += 1

    _save_figures_meta(os.path.join(output_dir, "meta.json"), figures, extractor="pymupdf-images")
    return figures


def ensure_paper_figures(
    *,
    pdf_url: str,
    docs_dir: str,
    source_key: str,
    asset_key: str,
    force: bool = False,
) -> List[Dict[str, Any]]:
    if not str(pdf_url or "").strip():
        return []

    asset_dir = _absolute_dir(docs_dir, source_key, asset_key)
    relative_prefix = _relative_prefix(source_key, asset_key)
    meta_path = os.path.join(asset_dir, "meta.json")
    if not force:
        cached = _load_cached_figures(meta_path)
        if cached:
            return cached
        if os.path.exists(meta_path):
            return []

    pdf_bytes = _download_pdf_bytes(pdf_url)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp_pdf:
        tmp_pdf.write(pdf_bytes)
        tmp_pdf.flush()
        figures = _extract_figures_with_pdffigures2(tmp_pdf.name, asset_dir, relative_prefix)
        if figures:
            return figures
        return extract_figures_from_pdf(tmp_pdf.name, asset_dir, relative_prefix)
