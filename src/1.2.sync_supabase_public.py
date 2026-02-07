#!/usr/bin/env python
# 将当天抓取的 arXiv 元数据（含 embedding）同步到 Supabase 公共库

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List
import requests
import torch
from sentence_transformers import SentenceTransformer

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
CONFIG_FILE = os.path.join(ROOT_DIR, "config.yaml")
DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _norm(v: Any) -> str:
    return str(v or "").strip()


def _base_rest(url: str) -> str:
    return _norm(url).rstrip("/") + "/rest/v1"


def _headers(service_key: str, prefer: str | None = None) -> Dict[str, str]:
    h = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_config() -> Dict[str, Any]:
    if yaml is None or not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve_embed_model(args_model: str) -> str:
    arg_model = _norm(args_model)
    if arg_model:
        return arg_model
    cfg = load_config()
    ef = (cfg.get("embedding_filter") or {}) if isinstance(cfg, dict) else {}
    model = _norm((ef or {}).get("model_name") or "")
    return model or DEFAULT_EMBED_MODEL


def build_embedding_text(row: Dict[str, Any]) -> str:
    title = _norm(row.get("title"))
    abstract = _norm(row.get("abstract"))
    if title and abstract:
        return f"passage: Title: {title}\n\nAbstract: {abstract}"
    if title:
        return f"passage: Title: {title}"
    if abstract:
        return f"passage: Abstract: {abstract}"
    return ""


def to_pgvector_literal(vec: List[float]) -> str:
    return "[" + ",".join(f"{float(x):.8f}" for x in vec) + "]"


def attach_embeddings(
    rows: List[Dict[str, Any]],
    *,
    model_name: str,
    devices: List[str],
    batch_size: int,
    max_length: int,
) -> int:
    if not rows:
        return 0

    texts = [build_embedding_text(r) for r in rows]
    log(f"[Embedding] 开始编码：{len(texts)} 条")
    use_devices = devices or ["cpu"]
    if len(use_devices) == 1:
        log(f"[Embedding] 加载模型：{model_name}（device={use_devices[0]}）")
        model = SentenceTransformer(model_name, device=use_devices[0])
        if max_length > 0 and hasattr(model, "max_seq_length"):
            try:
                model.max_seq_length = max_length
            except Exception:
                pass
        emb = model.encode(
            texts,
            convert_to_numpy=True,
            normalize_embeddings=True,
            batch_size=max(int(batch_size or 8), 1),
            show_progress_bar=False,
        )
    else:
        log(f"[Embedding] 加载模型：{model_name}（multi-device={use_devices}）")
        model = SentenceTransformer(model_name)
        if max_length > 0 and hasattr(model, "max_seq_length"):
            try:
                model.max_seq_length = max_length
            except Exception:
                pass
        pool = model.start_multi_process_pool(target_devices=use_devices)
        try:
            emb = model.encode_multi_process(
                texts,
                pool=pool,
                batch_size=max(int(batch_size or 8), 1),
                normalize_embeddings=True,
            )
        finally:
            model.stop_multi_process_pool(pool)

    if len(emb.shape) != 2 or emb.shape[0] != len(rows):
        raise RuntimeError("embedding 输出维度异常")

    dim = int(emb.shape[1])
    now_iso = _now_iso()
    for idx, row in enumerate(rows):
        vec = emb[idx].tolist()
        row["embedding"] = to_pgvector_literal(vec)
        row["embedding_model"] = model_name
        row["embedding_dim"] = dim
        row["embedding_updated_at"] = now_iso
    log(f"[Embedding] 编码完成：dim={dim}")
    return dim


def resolve_embed_devices(embed_devices: str, embed_device: str) -> List[str]:
    raw = _norm(embed_devices)
    if raw:
        items = [_norm(x) for x in raw.split(",") if _norm(x)]
        if items:
            return items

    single = _norm(embed_device)
    if single:
        return [single]

    if torch.cuda.is_available():
        count = int(torch.cuda.device_count() or 0)
        if count >= 2:
            return ["cuda:0", "cuda:1"]
        if count == 1:
            return ["cuda:0"]
    return ["cpu"]


def load_raw(path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"原始文件不存在：{path}")
    if os.path.getsize(path) <= 0:
        raise RuntimeError(f"原始文件为空（0 字节）：{path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or []
    except json.JSONDecodeError as e:
        raise RuntimeError(f"原始文件 JSON 解析失败：{path} ({e})") from e
    except Exception as e:
        raise RuntimeError(f"读取原始文件失败：{path} ({e})") from e
    if not isinstance(data, list):
        raise RuntimeError(f"原始文件格式错误（期望 list）：{path}")
    return [x for x in data if isinstance(x, dict)]


def normalize_paper(x: Dict[str, Any]) -> Dict[str, Any] | None:
    pid = _norm(x.get("id"))
    if not pid:
        return None
    return {
        "id": pid,
        "title": _norm(x.get("title")),
        "abstract": _norm(x.get("abstract")),
        "authors": x.get("authors") if isinstance(x.get("authors"), list) else [],
        "primary_category": _norm(x.get("primary_category")) or None,
        "categories": x.get("categories") if isinstance(x.get("categories"), list) else [],
        "published": _norm(x.get("published")) or None,
        "link": _norm(x.get("link")) or None,
        "source": _norm(x.get("source") or "supabase"),
        "updated_at": _now_iso(),
    }


def upsert_papers(
    *,
    url: str,
    service_key: str,
    table: str,
    rows: List[Dict[str, Any]],
    batch_size: int = 500,
    timeout: int = 30,
    retries: int = 3,
    retry_wait: float = 2.0,
) -> None:
    rest = _base_rest(url)
    endpoint = f"{rest}/{table}?on_conflict=id"
    total = len(rows)
    if total == 0:
        return
    for i in range(0, total, batch_size):
        chunk = rows[i : i + batch_size]
        last_error: Exception | None = None
        max_attempts = max(int(retries or 0), 0) + 1
        for attempt in range(1, max_attempts + 1):
            try:
                resp = requests.post(
                    endpoint,
                    headers=_headers(service_key, "resolution=merge-duplicates"),
                    data=json.dumps(chunk, ensure_ascii=False),
                    timeout=max(int(timeout or 30), 1),
                )
                if resp.status_code >= 300:
                    raise RuntimeError(f"HTTP {resp.status_code} {resp.text[:200]}")
                log(
                    f"[Supabase] upsert papers: {min(i + batch_size, total)}/{total}"
                    f" (batch={len(chunk)}, attempt={attempt}/{max_attempts})"
                )
                last_error = None
                break
            except Exception as e:
                last_error = e
                if attempt >= max_attempts:
                    break
                wait_s = max(float(retry_wait or 0.0), 0.0) * attempt
                log(
                    f"[WARN] upsert 批次失败，准备重试 "
                    f"(attempt={attempt}/{max_attempts}, wait={wait_s:.1f}s): {e}"
                )
                if wait_s > 0:
                    time.sleep(wait_s)
        if last_error is not None:
            raise RuntimeError(
                f"upsert papers 失败：offset={i}, batch={len(chunk)}, error={last_error}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync raw arXiv papers to Supabase public tables.")
    parser.add_argument("--date", type=str, default=TODAY_STR, help="YYYYMMDD")
    parser.add_argument(
        "--raw-input",
        type=str,
        default="",
        help="可选：直接指定原始 JSON 文件路径；指定后优先于 --date。",
    )
    parser.add_argument("--url", type=str, default=os.getenv("SUPABASE_URL", ""))
    parser.add_argument("--service-key", type=str, default=os.getenv("SUPABASE_SERVICE_KEY", ""))
    parser.add_argument("--papers-table", type=str, default=os.getenv("SUPABASE_PAPERS_TABLE", "arxiv_papers"))
    parser.add_argument("--embed-model", type=str, default="")
    parser.add_argument("--embed-device", type=str, default="cpu")
    parser.add_argument("--embed-devices", type=str, default="")
    parser.add_argument("--embed-batch-size", type=int, default=8)
    parser.add_argument("--embed-max-length", type=int, default=0)
    parser.add_argument("--upsert-batch-size", type=int, default=200)
    parser.add_argument("--upsert-timeout", type=int, default=120)
    parser.add_argument("--upsert-retries", type=int, default=5)
    parser.add_argument("--upsert-retry-wait", type=float, default=2.0)
    parser.add_argument("--with-embeddings", dest="with_embeddings", action="store_true", default=True)
    parser.add_argument("--no-embeddings", dest="with_embeddings", action="store_false")
    parser.add_argument("--mode", type=str, default="standard")
    args = parser.parse_args()

    url = _norm(args.url)
    key = _norm(args.service_key)
    if not url or not key:
        log("[INFO] SUPABASE_URL / SUPABASE_SERVICE_KEY 未配置，跳过同步。")
        return

    raw_path = _norm(args.raw_input)
    if raw_path and not os.path.isabs(raw_path):
        raw_path = os.path.abspath(os.path.join(ROOT_DIR, raw_path))
    if not raw_path:
        raw_path = os.path.join(ROOT_DIR, "archive", args.date, "raw", f"arxiv_papers_{args.date}.json")
    rows_raw = load_raw(raw_path)
    rows = [r for r in (normalize_paper(x) for x in rows_raw) if r]
    if not rows:
        raise RuntimeError(f"原始文件无有效论文记录：{raw_path}")

    try:
        if args.with_embeddings:
            model_name = resolve_embed_model(args.embed_model)
            embed_devices = resolve_embed_devices(args.embed_devices, args.embed_device)
            attach_embeddings(
                rows,
                model_name=model_name,
                devices=embed_devices,
                batch_size=int(args.embed_batch_size or 8),
                max_length=int(args.embed_max_length or 0),
            )
        else:
            log("[Embedding] 已禁用 embedding 同步（--no-embeddings）")

        upsert_papers(
            url=url,
            service_key=key,
            table=args.papers_table,
            rows=rows,
            batch_size=max(int(args.upsert_batch_size or 1), 1),
            timeout=max(int(args.upsert_timeout or 1), 1),
            retries=max(int(args.upsert_retries or 0), 0),
            retry_wait=max(float(args.upsert_retry_wait or 0.0), 0.0),
        )
        log(f"[OK] Supabase 同步完成：{len(rows)} 篇")
    except Exception as e:
        log(f"[ERROR] Supabase 同步失败：{e}")
        raise


if __name__ == "__main__":
    main()
