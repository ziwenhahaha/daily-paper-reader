from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Tuple

import fitz
import requests
from PIL import Image


MIN_FIGURE_WIDTH = 240
MIN_FIGURE_HEIGHT = 180
MIN_FIGURE_AREA = 120_000
WEBP_QUALITY = 82
FIGURE_META_VERSION = 2
PAPERCROPPER_SCRIPT_ENV = "PAPERCROPPER_SCRIPT"
PAPERCROPPER_DIR_ENV = "PAPERCROPPER_DIR"
PAPERCROPPER_MODEL_ENV = "PAPERCROPPER_MODEL"
PAPERCROPPER_PYTHON_ENV = "PAPERCROPPER_PYTHON"
PAPERCROPPER_DISABLE_ENV = "PAPERCROPPER_DISABLE"
PAPERCROPPER_MODEL_FILENAME = "doclayout_yolo_docstructbench_imgsz1280_2501.pt"
PAPERCROPPER_LOG_LIMIT = 1200


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


def _relative_tables_prefix(source_key: str, asset_key: str) -> str:
    return "/".join(["assets", "tables", source_key, _safe_asset_key(asset_key)])


def _absolute_tables_dir(docs_dir: str, source_key: str, asset_key: str) -> str:
    return os.path.join(docs_dir, "assets", "tables", source_key, _safe_asset_key(asset_key))


def _load_cached_media(meta_path: str, key: str) -> List[Dict[str, Any]]:
    if not os.path.exists(meta_path):
        return []
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            payload = json.load(f) or {}
    except Exception:
        return []
    if int(payload.get("version") or 0) != FIGURE_META_VERSION:
        return []
    items = payload.get(key)
    if not isinstance(items, list):
        return []
    out: List[Dict[str, Any]] = []
    for item in items:
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


def _load_cached_figures(meta_path: str) -> List[Dict[str, Any]]:
    return _load_cached_media(meta_path, "figures")


def _load_cached_tables(meta_path: str) -> List[Dict[str, Any]]:
    return _load_cached_media(meta_path, "tables")


def _save_media_meta(meta_path: str, items: List[Dict[str, Any]], *, extractor: str, key: str) -> None:
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "version": FIGURE_META_VERSION,
                "extractor": extractor,
                key: items,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def _save_figures_meta(meta_path: str, figures: List[Dict[str, Any]], *, extractor: str) -> None:
    _save_media_meta(meta_path, figures, extractor=extractor, key="figures")


def _save_tables_meta(meta_path: str, tables: List[Dict[str, Any]], *, extractor: str) -> None:
    _save_media_meta(meta_path, tables, extractor=extractor, key="tables")


def _warn_papercropper(message: str) -> None:
    print(f"[WARN] PaperCropper 表格/图表提取降级：{message}", flush=True)


def _tail_log_text(text: str, limit: int = PAPERCROPPER_LOG_LIMIT) -> str:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(compact) <= limit:
        return compact
    return "..." + compact[-limit:]


def _papercropper_was_configured() -> bool:
    return any(
        str(os.getenv(name) or "").strip()
        for name in [PAPERCROPPER_SCRIPT_ENV, PAPERCROPPER_DIR_ENV, PAPERCROPPER_MODEL_ENV, PAPERCROPPER_PYTHON_ENV]
    )


def _download_pdf_bytes(pdf_url: str, timeout: int = 90) -> bytes:
    resp = requests.get(
        str(pdf_url or "").strip(),
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=max(int(timeout or 1), 1),
    )
    resp.raise_for_status()
    return resp.content


def _truthy_env(name: str) -> bool:
    return str(os.getenv(name) or "").strip().lower() in {"1", "true", "yes", "on"}


def _first_existing(candidates: List[str]) -> str:
    for candidate in candidates:
        path = str(candidate or "").strip()
        if path and os.path.exists(path):
            return path
    return ""


def _resolve_papercropper() -> Tuple[str, str, str]:
    if _truthy_env(PAPERCROPPER_DISABLE_ENV):
        return "", "", ""

    configured_dir = str(os.getenv(PAPERCROPPER_DIR_ENV) or "").strip()
    cache_root = os.path.expanduser("~/.cache/dpr-tools/papercropper")
    script_path = _first_existing(
        [
            str(os.getenv(PAPERCROPPER_SCRIPT_ENV) or "").strip(),
            os.path.join(configured_dir, "extract.py") if configured_dir else "",
            os.path.join(cache_root, "PaperCropper", "extract.py"),
            os.path.expanduser("~/.cache/dpr-tools/PaperCropper/extract.py"),
            "/tmp/PaperCropper/extract.py",
        ]
    )
    model_path = _first_existing(
        [
            str(os.getenv(PAPERCROPPER_MODEL_ENV) or "").strip(),
            os.path.join(configured_dir, "models", PAPERCROPPER_MODEL_FILENAME) if configured_dir else "",
            os.path.join(cache_root, "models", PAPERCROPPER_MODEL_FILENAME),
            os.path.expanduser(f"~/.cache/dpr-tools/papercropper/models/{PAPERCROPPER_MODEL_FILENAME}"),
            f"/tmp/papercropper-run/models/{PAPERCROPPER_MODEL_FILENAME}",
        ]
    )
    python_path = _first_existing(
        [
            str(os.getenv(PAPERCROPPER_PYTHON_ENV) or "").strip(),
            os.path.join(cache_root, "venv", "bin", "python"),
            "/tmp/papercropper-venv/bin/python",
            sys.executable,
        ]
    )
    if not script_path or not model_path or not python_path:
        return "", "", ""
    return python_path, script_path, model_path


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


def _natural_sort_key(path: str) -> List[Any]:
    name = os.path.basename(path)
    parts = re.split(r"(\d+)", name)
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def _collect_papercropper_pngs(
    src_dir: str,
    output_dir: str,
    relative_prefix: str,
    *,
    file_prefix: str,
    label: str,
) -> List[Dict[str, Any]]:
    if not os.path.isdir(src_dir):
        return []

    os.makedirs(output_dir, exist_ok=True)
    items: List[Dict[str, Any]] = []
    seen_hash: set[str] = set()
    paths = [
        os.path.join(src_dir, name)
        for name in os.listdir(src_dir)
        if name.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
    ]
    for index, src_path in enumerate(sorted(paths, key=_natural_sort_key), start=1):
        try:
            with open(src_path, "rb") as f:
                sha = hashlib.sha256(f.read()).hexdigest()
        except Exception:
            continue
        if sha in seen_hash:
            continue
        seen_hash.add(sha)
        file_name = f"{file_prefix}-{len(items) + 1:03d}.webp"
        abs_path = os.path.join(output_dir, file_name)
        try:
            width, height = _save_webp_from_path(src_path, abs_path)
        except Exception:
            continue
        items.append(
            {
                "url": "/".join([relative_prefix.strip("/"), file_name]),
                "caption": "",
                "page": 0,
                "index": len(items) + 1,
                "width": width,
                "height": height,
                "label": label,
            }
        )
    return items


def _extract_media_with_papercropper(
    pdf_path: str,
    figure_output_dir: str,
    figure_relative_prefix: str,
    table_output_dir: str,
    table_relative_prefix: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    python_path, script_path, model_path = _resolve_papercropper()
    if not python_path or not script_path or not model_path:
        if not _truthy_env(PAPERCROPPER_DISABLE_ENV) and _papercropper_was_configured():
            _warn_papercropper("未找到可用的 PaperCropper 脚本或模型，改用备用图片提取器。")
        return [], []

    timeout = int(os.getenv("PAPERCROPPER_TIMEOUT_SECONDS") or "360")
    conf = str(os.getenv("PAPERCROPPER_CONF") or "0.4")
    imgsz = str(os.getenv("PAPERCROPPER_IMGSZ") or "1024")
    dpi = str(os.getenv("PAPERCROPPER_DPI") or "200")
    png_dpi = str(os.getenv("PAPERCROPPER_PNG_DPI") or "260")
    batch_size = str(os.getenv("PAPERCROPPER_BATCH_SIZE") or "4")
    padding = str(os.getenv("PAPERCROPPER_PADDING") or "2.0")

    with tempfile.TemporaryDirectory(prefix="papercropper_") as tmp_root:
        cmd = [
            python_path,
            script_path,
            "--pdf",
            pdf_path,
            "--model",
            model_path,
            "--output",
            tmp_root,
            "--formats",
            "png",
            "--targets",
            "figure,table",
            "--conf",
            conf,
            "--imgsz",
            imgsz,
            "--dpi",
            dpi,
            "--png-dpi",
            png_dpi,
            "--batch-size",
            batch_size,
            "--padding",
            padding,
        ]
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=max(timeout, 30),
                check=False,
            )
        except subprocess.TimeoutExpired:
            _warn_papercropper(f"执行超时（>{max(timeout, 30)}s），改用备用图片提取器。")
            return [], []
        if proc.returncode != 0:
            detail = _tail_log_text("\n".join([proc.stdout or "", proc.stderr or ""]))
            suffix = f"；输出：{detail}" if detail else ""
            _warn_papercropper(f"执行失败 returncode={proc.returncode}{suffix}")
            return [], []

        doc_output = os.path.join(tmp_root, os.path.splitext(os.path.basename(pdf_path))[0])
        figures = _collect_papercropper_pngs(
            os.path.join(doc_output, "Figures_png"),
            figure_output_dir,
            figure_relative_prefix,
            file_prefix="fig",
            label="Figure",
        )
        tables = _collect_papercropper_pngs(
            os.path.join(doc_output, "Tables_png"),
            table_output_dir,
            table_relative_prefix,
            file_prefix="table",
            label="Table",
        )
        if figures:
            _save_figures_meta(os.path.join(figure_output_dir, "meta.json"), figures, extractor="papercropper")
        if tables:
            _save_tables_meta(os.path.join(table_output_dir, "meta.json"), tables, extractor="papercropper")
        if not figures and not tables:
            detail = _tail_log_text("\n".join([proc.stdout or "", proc.stderr or ""]))
            suffix = f"；输出：{detail}" if detail else ""
            _warn_papercropper(f"执行完成但未产出 figure/table{suffix}")
        else:
            print(f"[INFO] PaperCropper 提取完成：figures={len(figures)} tables={len(tables)}", flush=True)
        return figures, tables


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
    figures, _tables = ensure_paper_media(
        pdf_url=pdf_url,
        docs_dir=docs_dir,
        source_key=source_key,
        asset_key=asset_key,
        force=force,
    )
    return figures


def ensure_paper_media(
    *,
    pdf_url: str,
    docs_dir: str,
    source_key: str,
    asset_key: str,
    force: bool = False,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not str(pdf_url or "").strip():
        return [], []

    figure_dir = _absolute_dir(docs_dir, source_key, asset_key)
    table_dir = _absolute_tables_dir(docs_dir, source_key, asset_key)
    figure_relative_prefix = _relative_prefix(source_key, asset_key)
    table_relative_prefix = _relative_tables_prefix(source_key, asset_key)
    figure_meta_path = os.path.join(figure_dir, "meta.json")
    table_meta_path = os.path.join(table_dir, "meta.json")
    if not force:
        cached_figures = _load_cached_figures(figure_meta_path)
        cached_tables = _load_cached_tables(table_meta_path)
        if cached_figures and cached_tables:
            return cached_figures, cached_tables
        if (cached_figures or os.path.exists(figure_meta_path)) and os.path.exists(table_meta_path):
            return cached_figures, cached_tables

    pdf_bytes = _download_pdf_bytes(pdf_url)
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp_pdf:
        tmp_pdf.write(pdf_bytes)
        tmp_pdf.flush()

        figures, tables = _extract_media_with_papercropper(
            tmp_pdf.name,
            figure_dir,
            figure_relative_prefix,
            table_dir,
            table_relative_prefix,
        )
        if figures or tables:
            return figures, tables

        return extract_figures_from_pdf(tmp_pdf.name, figure_dir, figure_relative_prefix), []
