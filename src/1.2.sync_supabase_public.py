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
from model_loader import load_sentence_transformer
try:
    from source_config import get_source_backend
except Exception:  # pragma: no cover
    from src.source_config import get_source_backend

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
TODAY_STR = str(os.getenv("DPR_RUN_DATE") or "").strip() or datetime.now(timezone.utc).strftime("%Y%m%d")
CONFIG_FILE = os.path.join(ROOT_DIR, "config.yaml")
DEFAULT_EMBED_MODEL = "BAAI/bge-small-en-v1.5"
SYNC_START_TS = time.time()


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _brief_row_ids(rows: List[Dict[str, Any]], limit: int = 3) -> str:
    if not rows:
        return "[]"
    ids = []
    for row in rows:
        pid = _norm(row.get("id"))
        if pid:
            ids.append(pid)
        if len(ids) >= limit:
            break
    suffix = ""
    if len(rows) > limit:
        suffix = ", ..."
    return f"[{', '.join(ids)}{suffix}]"


def _norm(v: Any) -> str:
    return str(v or "").strip()


def _base_rest(url: str) -> str:
    return _norm(url).rstrip("/") + "/rest/v1"


def _headers(service_key: str, prefer: str | None = None, schema: str = "public") -> Dict[str, str]:
    safe_schema = _norm(schema)
    h = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    if safe_schema:
        h["Accept-Profile"] = safe_schema
        h["Content-Profile"] = safe_schema
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


def resolve_supabase_url(args_url: str, backend_key: str = "arxiv") -> str:
    direct = _norm(args_url)
    if direct:
        return direct
    cfg = load_config()
    backend = get_source_backend(cfg, backend_key)
    if backend:
        return _norm((backend or {}).get("url") or "")
    sb = (cfg.get("supabase") or {}) if isinstance(cfg, dict) else {}
    return _norm((sb or {}).get("url") or "")


def resolve_papers_table(args_table: str, backend_key: str = "arxiv") -> str:
    direct = _norm(args_table)
    if direct:
        return direct
    cfg = load_config()
    backend = get_source_backend(cfg, backend_key)
    if backend:
        return _norm((backend or {}).get("papers_table") or "")
    sb = (cfg.get("supabase") or {}) if isinstance(cfg, dict) else {}
    return _norm((sb or {}).get("papers_table") or "")


def resolve_default_raw_path(date_str: str, backend_key: str) -> str:
    safe_backend = _norm(backend_key).lower() or "arxiv"
    prefix = "arxiv_papers"
    if safe_backend == "biorxiv":
        prefix = "biorxiv_papers"
    return os.path.join(ROOT_DIR, "archive", date_str, "raw", f"{prefix}_{date_str}.json")


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
    total_rows = len(rows)
    if total_rows == 0:
        return 0
    log(f"[Embedding] 开始编码：{total_rows} 条")
    batch_size = max(int(batch_size or 1), 1)
    use_devices = devices or ["cpu"]
    total_batches = (total_rows + batch_size - 1) // batch_size
    if len(use_devices) == 1:
        device = use_devices[0]
        log(f"[Embedding] 加载模型：{model_name}（device={device}）")
        model = load_sentence_transformer(model_name, device=use_devices[0])
        if max_length > 0 and hasattr(model, "max_seq_length"):
            try:
                model.max_seq_length = max_length
            except Exception:
                pass

        now_iso = _now_iso()
        for batch_index in range(total_batches):
            batch_from = batch_index * batch_size
            batch_to = min((batch_index + 1) * batch_size, total_rows)
            texts_batch = texts[batch_from:batch_to]
            rows_batch = rows[batch_from:batch_to]
            log(
                f"[Embedding] 正在编码第 {batch_index + 1}/{total_batches} 批 "
                f"（{batch_from + 1}-{batch_to}/{total_rows}，device={device}）"
            )
            emb = model.encode(
                texts_batch,
                convert_to_numpy=True,
                normalize_embeddings=True,
                batch_size=max(batch_size, 1),
                show_progress_bar=False,
            )
            if batch_index == 0:
                dim = int(emb.shape[1]) if hasattr(emb, "shape") and len(emb.shape) >= 2 else 0
            if len(emb) != len(rows_batch):
                raise RuntimeError("embedding 输出长度与输入批次不一致")
            for local_idx, row in enumerate(rows_batch):
                vec = emb[local_idx].tolist()
                row["embedding"] = to_pgvector_literal(vec)
                row["embedding_model"] = model_name
                row["embedding_dim"] = dim
                row["embedding_updated_at"] = now_iso
            log(
                f"[Embedding] 完成编码第 {batch_index + 1}/{total_batches} 批 "
                f"（{batch_from + 1}-{batch_to}/{total_rows}）"
            )
        if dim <= 0:
            raise RuntimeError("embedding 输出维度异常")
        return dim

    else:
        log(f"[Embedding] 开始分流编码：total={total_rows}, batch={batch_size}, multi-device={use_devices}")
        log(f"[Embedding] 加载模型：{model_name}（multi-device={use_devices}）")
        model = load_sentence_transformer(model_name, device=use_devices[0])
        if max_length > 0 and hasattr(model, "max_seq_length"):
            try:
                model.max_seq_length = max_length
            except Exception:
                pass
        pool = model.start_multi_process_pool(target_devices=use_devices)
        try:
            now_iso = _now_iso()
            for batch_index in range(total_batches):
                batch_from = batch_index * batch_size
                batch_to = min((batch_index + 1) * batch_size, total_rows)
                texts_batch = texts[batch_from:batch_to]
                rows_batch = rows[batch_from:batch_to]
                log(
                    f"[Embedding] 多卡第 {batch_index + 1}/{total_batches} 批编码 "
                    f"（{batch_from + 1}-{batch_to}/{total_rows}，multi-device={use_devices}）"
                )
                emb = model.encode_multi_process(
                    texts_batch,
                    pool=pool,
                    batch_size=max(int(batch_size or 8), 1),
                    normalize_embeddings=True,
                )
                if batch_index == 0:
                    dim = int(emb.shape[1]) if hasattr(emb, "shape") and len(emb.shape) >= 2 else 0
                if len(emb) != len(rows_batch):
                    raise RuntimeError("embedding 输出长度与输入批次不一致")
                for local_idx, row in enumerate(rows_batch):
                    vec = emb[local_idx].tolist()
                    row["embedding"] = to_pgvector_literal(vec)
                    row["embedding_model"] = model_name
                    row["embedding_dim"] = dim
                    row["embedding_updated_at"] = now_iso
                log(
                    f"[Embedding] 完成多卡第 {batch_index + 1}/{total_batches} 批 "
                    f"（{batch_from + 1}-{batch_to}/{total_rows}）"
                )
        finally:
            model.stop_multi_process_pool(pool)

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
    rows = [x for x in data if isinstance(x, dict)]
    log(f"[INFO] 读取原始抓取文件：{path}，共 {len(rows)} 行")
    if rows:
        log(f"[INFO] 原始文件前 3 条 id：{_brief_row_ids(rows)}")
    return rows


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


def deduplicate_rows_by_id(rows: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], int]:
    seen = set()
    out: List[Dict[str, Any]] = []
    duplicates = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        pid = _norm(row.get("id"))
        if not pid:
            continue
        key = pid.lower()
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        out.append(row)
    return out, duplicates


def upsert_papers(
    *,
    url: str,
    service_key: str,
    table: str,
    rows: List[Dict[str, Any]],
    schema: str = "public",
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
    log(
        "[Supabase] 开始同步参数："
        f" table={table}, schema={schema}, total={total}, "
        f"batch_size={batch_size}, timeout={timeout}s, retries={retries}, retry_wait={retry_wait}s"
    )

    max_attempts = max(int(retries or 0), 0) + 1
    uploaded = 0
    batch_index = 0
    batch_total = (total + batch_size - 1) // batch_size

    def _post_chunk(chunk: List[Dict[str, Any]]) -> int:
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                payload_size = len(json.dumps(chunk, ensure_ascii=False, separators=(",", ":")))
                start_t = time.time()
                resp = requests.post(
                    endpoint,
                    headers=_headers(service_key, "resolution=merge-duplicates", schema=schema),
                    data=json.dumps(chunk, ensure_ascii=False, separators=(",", ":")),
                    timeout=max(int(timeout or 30), 1),
                )
                spent_ms = int((time.time() - start_t) * 1000)
                if resp.status_code >= 300:
                    raise RuntimeError(f"HTTP {resp.status_code} {resp.text[:200]}")
                log(
                    f"[Supabase] upsert 成功: rows={len(chunk)}, bytes={payload_size}, "
                    f"status={resp.status_code}, cost={spent_ms}ms"
                )
                return attempt
            except Exception as e:
                last_error = e
                if attempt >= max_attempts:
                    break
                wait_s = max(float(retry_wait or 0.0), 0.0) * attempt
                log(
                    f"[WARN] upsert 批次失败（rows={len(chunk)}, batch_index={batch_index}, "
                    f"sample_ids={_brief_row_ids(chunk)}），准备重试 "
                    f"(attempt={attempt}/{max_attempts}, wait={wait_s:.1f}s): {e}"
                )
                if wait_s > 0:
                    time.sleep(wait_s)
        if last_error is not None:
            raise last_error

    def _upsert_with_split(chunk: List[Dict[str, Any]], depth: int = 0) -> None:
        nonlocal uploaded
        if not chunk:
            return
        try:
            used_attempt = _post_chunk(chunk)
            uploaded += len(chunk)
            log(
                f"[Supabase] upsert papers: {uploaded}/{total} "
                f"(batch={len(chunk)}, attempt={used_attempt}/{max_attempts}, depth={depth})"
            )
            return
        except Exception as e:
            if len(chunk) <= 1:
                pid = _norm((chunk[0] or {}).get("id")) if chunk else ""
                raise RuntimeError(
                    f"upsert papers 最小分片仍失败：id={pid or '<unknown>'}, error={e}"
                ) from e
            mid = max(len(chunk) // 2, 1)
            left = chunk[:mid]
            right = chunk[mid:]
            log(
                f"[WARN] upsert 批次失败，自动拆分重试 "
                f"(size={len(chunk)}, depth={depth}, left={len(left)}, right={len(right)}): {e}"
            )
            _upsert_with_split(left, depth + 1)
            _upsert_with_split(right, depth + 1)

    for i in range(0, total, batch_size):
        batch_index += 1
        chunk = rows[i : i + batch_size]
        batch_start = i + 1
        batch_end = min(i + batch_size, total)
        if batch_size > 0:
            log(
                f"[Supabase] 上传进度：第 {batch_index}/{batch_total} 批，"
                f"覆盖范围 {batch_start}-{batch_end}，ids={_brief_row_ids(chunk)}"
            )
        try:
            _upsert_with_split(chunk, depth=0)
        except Exception as e:
            raise RuntimeError(
                f"upsert papers 失败：offset={i}, batch={len(chunk)}, error={e}"
            ) from e

    cost_sec = max(time.time() - SYNC_START_TS, 0.0)
    log(f"[Supabase] 全量同步结束：成功上报 {uploaded} 条，共耗时 {cost_sec:.1f}s")

def main() -> None:
    parser = argparse.ArgumentParser(description="Sync raw arXiv papers to Supabase public tables.")
    parser.add_argument("--date", type=str, default=TODAY_STR, help="日期 token（YYYYMMDD 或 YYYYMMDD-YYYYMMDD）")
    parser.add_argument(
        "--raw-input",
        type=str,
        default="",
        help="可选：直接指定原始 JSON 文件路径；指定后优先于 --date。",
    )
    parser.add_argument("--backend-key", type=str, default=os.getenv("SUPABASE_BACKEND_KEY", "arxiv"))
    parser.add_argument("--url", type=str, default=os.getenv("SUPABASE_URL", ""))
    parser.add_argument("--service-key", type=str, default=os.getenv("SUPABASE_SERVICE_KEY", ""))
    parser.add_argument("--papers-table", type=str, default=os.getenv("SUPABASE_PAPERS_TABLE", ""))
    parser.add_argument("--schema", type=str, default=os.getenv("SUPABASE_SCHEMA", "public"))
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

    backend_key = _norm(args.backend_key) or "arxiv"
    url = resolve_supabase_url(args.url, backend_key)
    key = _norm(args.service_key)
    papers_table = resolve_papers_table(args.papers_table, backend_key) or "arxiv_papers"
    if not url or not key:
        log("[INFO] 缺少 Supabase 连接信息（url 或 service key），跳过同步。")
        return

    raw_path = _norm(args.raw_input)
    if raw_path and not os.path.isabs(raw_path):
        raw_path = os.path.abspath(os.path.join(ROOT_DIR, raw_path))
    if not raw_path:
        raw_path = resolve_default_raw_path(args.date, backend_key)
    rows_raw = load_raw(raw_path)
    rows = [r for r in (normalize_paper(x) for x in rows_raw) if r]
    rows, dup_cnt = deduplicate_rows_by_id(rows)
    if dup_cnt > 0:
        log(f"[WARN] 检测到重复论文 ID，已去重：{dup_cnt} 条")
    if not rows:
        raise RuntimeError(f"原始文件无有效论文记录：{raw_path}")

    try:
        if args.with_embeddings:
            model_name = resolve_embed_model(args.embed_model)
            log(
                f"[Embedding] 配置：model={model_name}, embed_device={args.embed_device}, "
                f"embed_devices={args.embed_devices or '<auto>'}, batch={args.embed_batch_size}, "
                f"max_length={args.embed_max_length}"
            )
            log("[Embedding] 开始执行文本向量编码阶段")
            emb_start = time.time()
            embed_devices = resolve_embed_devices(args.embed_devices, args.embed_device)
            attach_embeddings(
                rows,
                model_name=model_name,
                devices=embed_devices,
                batch_size=int(args.embed_batch_size or 8),
                max_length=int(args.embed_max_length or 0),
            )
            log(
                f"[Embedding] 文本向量编码阶段结束，耗时 "
                f"{(time.time() - emb_start):.1f}s"
            )
        else:
            log("[Embedding] 已禁用 embedding 同步（--no-embeddings）")

        upsert_papers(
            url=url,
            service_key=key,
            table=papers_table,
            schema=_norm(args.schema),
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
