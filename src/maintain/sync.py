#!/usr/bin/env python
# 将当天抓取的 arXiv 元数据（含 embedding）同步到 Supabase 公共库

from __future__ import annotations

import argparse
from concurrent.futures import ALL_COMPLETED, FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Tuple
import requests
try:
    import torch
except Exception:  # pragma: no cover
    torch = None

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

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
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", ".."))
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
    elif safe_backend == "medrxiv":
        prefix = "medrxiv_papers"
    elif safe_backend == "chemrxiv":
        prefix = "chemrxiv_papers"
    elif safe_backend == "iclr":
        prefix = "iclr_openreview_papers"
    elif safe_backend == "icml":
        prefix = "icml_openreview_papers"
    elif safe_backend == "acl":
        prefix = "acl_papers"
    elif safe_backend == "emnlp":
        prefix = "emnlp_papers"
    elif safe_backend == "aaai":
        prefix = "aaai_papers"
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


def configure_local_embedding_runtime(reserve_upload_cpus: int) -> Tuple[int, int]:
    total_cpus = max(int(os.cpu_count() or 1), 1)
    reserved = min(max(int(reserve_upload_cpus or 0), 0), max(total_cpus - 1, 0))
    embed_cpus = max(total_cpus - reserved, 1)
    thread_env_keys = (
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "BLIS_NUM_THREADS",
    )
    for key in thread_env_keys:
        os.environ[key] = str(embed_cpus)
    os.environ["TOKENIZERS_PARALLELISM"] = "true"
    if torch is not None:
        try:
            torch.set_num_threads(embed_cpus)
        except Exception:
            pass
        try:
            torch.set_num_interop_threads(max(min(embed_cpus // 4, 8), 1))
        except Exception:
            pass
    return embed_cpus, reserved


def _load_embedding_model(
    *,
    model_name: str,
    devices: List[str],
    max_length: int,
    allow_remote: bool,
):
    use_devices = devices or ["cpu"]
    single_device = use_devices[0]
    if len(use_devices) == 1:
        log(f"[Embedding] 加载模型：{model_name}（device={single_device}）")
    else:
        log(f"[Embedding] 加载模型：{model_name}（multi-device={use_devices}）")
    model = load_sentence_transformer(
        model_name,
        device=single_device,
        allow_remote=allow_remote,
        log=log,
    )
    if max_length > 0 and hasattr(model, "max_seq_length"):
        try:
            model.max_seq_length = max_length
        except Exception:
            pass
    return model


def iter_embedded_row_chunks(
    rows: List[Dict[str, Any]],
    *,
    model_name: str,
    devices: List[str],
    encode_batch_size: int,
    stream_chunk_size: int,
    max_length: int,
    allow_remote: bool,
) -> Iterator[Tuple[List[Dict[str, Any]], int]]:
    total_rows = len(rows or [])
    if total_rows <= 0:
        return

    use_devices = devices or ["cpu"]
    safe_encode_batch = max(int(encode_batch_size or 1), 1)
    safe_chunk_size = max(int(stream_chunk_size or safe_encode_batch), safe_encode_batch)
    total_chunks = (total_rows + safe_chunk_size - 1) // safe_chunk_size
    log(
        f"[Embedding] 开始流式编码：total={total_rows}, "
        f"stream_chunk={safe_chunk_size}, encode_batch={safe_encode_batch}, devices={use_devices}"
    )

    model = _load_embedding_model(
        model_name=model_name,
        devices=use_devices,
        max_length=max_length,
        allow_remote=allow_remote,
    )
    now_iso = _now_iso()
    dim = 0

    if len(use_devices) == 1:
        for chunk_index in range(total_chunks):
            chunk_from = chunk_index * safe_chunk_size
            chunk_to = min((chunk_index + 1) * safe_chunk_size, total_rows)
            rows_chunk = rows[chunk_from:chunk_to]
            texts_chunk = [build_embedding_text(row) for row in rows_chunk]
            log(
                f"[Embedding] 编码分片 {chunk_index + 1}/{total_chunks} "
                f"（{chunk_from + 1}-{chunk_to}/{total_rows}，device={use_devices[0]}）"
            )
            emb = model.encode(
                texts_chunk,
                convert_to_numpy=True,
                normalize_embeddings=True,
                batch_size=safe_encode_batch,
                show_progress_bar=False,
            )
            chunk_dim = int(emb.shape[1]) if hasattr(emb, "shape") and len(emb.shape) >= 2 else 0
            if chunk_dim <= 0:
                raise RuntimeError("embedding 输出维度异常")
            if len(emb) != len(rows_chunk):
                raise RuntimeError("embedding 输出长度与输入分片不一致")
            dim = chunk_dim
            for local_idx, row in enumerate(rows_chunk):
                vec = emb[local_idx].tolist()
                row["embedding"] = to_pgvector_literal(vec)
                row["embedding_model"] = model_name
                row["embedding_dim"] = dim
                row["embedding_updated_at"] = now_iso
            log(
                f"[Embedding] 完成分片 {chunk_index + 1}/{total_chunks} "
                f"（{chunk_from + 1}-{chunk_to}/{total_rows}，dim={dim}）"
            )
            yield rows_chunk, dim
        return

    pool = model.start_multi_process_pool(target_devices=use_devices)
    try:
        for chunk_index in range(total_chunks):
            chunk_from = chunk_index * safe_chunk_size
            chunk_to = min((chunk_index + 1) * safe_chunk_size, total_rows)
            rows_chunk = rows[chunk_from:chunk_to]
            texts_chunk = [build_embedding_text(row) for row in rows_chunk]
            log(
                f"[Embedding] 多设备分片 {chunk_index + 1}/{total_chunks} "
                f"（{chunk_from + 1}-{chunk_to}/{total_rows}，devices={use_devices}）"
            )
            emb = model.encode_multi_process(
                texts_chunk,
                pool=pool,
                batch_size=safe_encode_batch,
                normalize_embeddings=True,
            )
            chunk_dim = int(emb.shape[1]) if hasattr(emb, "shape") and len(emb.shape) >= 2 else 0
            if chunk_dim <= 0:
                raise RuntimeError("embedding 输出维度异常")
            if len(emb) != len(rows_chunk):
                raise RuntimeError("embedding 输出长度与输入分片不一致")
            dim = chunk_dim
            for local_idx, row in enumerate(rows_chunk):
                vec = emb[local_idx].tolist()
                row["embedding"] = to_pgvector_literal(vec)
                row["embedding_model"] = model_name
                row["embedding_dim"] = dim
                row["embedding_updated_at"] = now_iso
            log(
                f"[Embedding] 完成多设备分片 {chunk_index + 1}/{total_chunks} "
                f"（{chunk_from + 1}-{chunk_to}/{total_rows}，dim={dim}）"
            )
            yield rows_chunk, dim
    finally:
        model.stop_multi_process_pool(pool)


def attach_embeddings(
    rows: List[Dict[str, Any]],
    *,
    model_name: str,
    devices: List[str],
    batch_size: int,
    max_length: int,
    allow_remote: bool = True,
) -> int:
    dim = 0
    for _rows_chunk, chunk_dim in iter_embedded_row_chunks(
        rows,
        model_name=model_name,
        devices=devices,
        encode_batch_size=batch_size,
        stream_chunk_size=batch_size,
        max_length=max_length,
        allow_remote=allow_remote,
    ):
        dim = chunk_dim
    return dim


def resolve_embed_devices(embed_devices: str, embed_device: str) -> List[str]:
    raw = _norm(embed_devices)
    if raw:
        items = [_norm(x) for x in raw.split(",") if _norm(x)]
        if items:
            return items

    single = _norm(embed_device)
    if single and single.lower() != "auto":
        return [single]

    cuda_mod = getattr(torch, "cuda", None)
    cuda_available = bool(cuda_mod and getattr(cuda_mod, "is_available", lambda: False)())
    if cuda_available:
        count = int(getattr(cuda_mod, "device_count", lambda: 0)() or 0)
        if count >= 1:
            return [f"cuda:{idx}" for idx in range(count)]
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


def _wait_upload_futures(pending: List[Future[None]], *, drain_all: bool = False) -> List[Future[None]]:
    if not pending:
        return []
    done, not_done = wait(
        pending,
        return_when=ALL_COMPLETED if drain_all else FIRST_COMPLETED,
    )
    for fut in done:
        fut.result()
    return list(not_done)


def stream_embed_and_upsert(
    *,
    rows: List[Dict[str, Any]],
    url: str,
    service_key: str,
    table: str,
    schema: str,
    model_name: str,
    devices: List[str],
    embed_batch_size: int,
    embed_chunk_size: int,
    embed_max_length: int,
    embed_local_only: bool,
    upload_workers: int,
    max_pending_upload_chunks: int,
    upsert_batch_size: int,
    upsert_timeout: int,
    upsert_retries: int,
    upsert_retry_wait: float,
) -> int:
    total_rows = len(rows or [])
    if total_rows <= 0:
        return 0
    worker_count = max(int(upload_workers or 1), 1)
    pending_limit = max(int(max_pending_upload_chunks or worker_count), worker_count)
    pending: List[Future[None]] = []
    dim = 0
    log(
        f"[Pipeline] 启动流式 embedding+上传：total={total_rows}, "
        f"upload_workers={worker_count}, pending_limit={pending_limit}"
    )
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="supabase-upload") as executor:
        for rows_chunk, chunk_dim in iter_embedded_row_chunks(
            rows,
            model_name=model_name,
            devices=devices,
            encode_batch_size=embed_batch_size,
            stream_chunk_size=embed_chunk_size,
            max_length=embed_max_length,
            allow_remote=not embed_local_only,
        ):
            dim = chunk_dim
            while len(pending) >= pending_limit:
                pending = _wait_upload_futures(pending, drain_all=False)
            chunk_first_id = _norm((rows_chunk[0] or {}).get("id")) if rows_chunk else ""
            chunk_last_id = _norm((rows_chunk[-1] or {}).get("id")) if rows_chunk else ""
            log(
                f"[Pipeline] 提交上传分片：rows={len(rows_chunk)}, "
                f"first={chunk_first_id or '<none>'}, last={chunk_last_id or '<none>'}"
            )
            pending.append(
                executor.submit(
                    upsert_papers,
                    url=url,
                    service_key=service_key,
                    table=table,
                    schema=schema,
                    rows=rows_chunk,
                    batch_size=upsert_batch_size,
                    timeout=upsert_timeout,
                    retries=upsert_retries,
                    retry_wait=upsert_retry_wait,
                )
            )
        pending = _wait_upload_futures(pending, drain_all=True)
    log(f"[Pipeline] 流式 embedding+上传完成：dim={dim}")
    return dim

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
    parser.add_argument("--embed-chunk-size", type=int, default=512)
    parser.add_argument("--embed-max-length", type=int, default=0)
    parser.add_argument("--embed-local-only", action="store_true")
    parser.add_argument("--reserve-upload-cpus", type=int, default=2)
    parser.add_argument("--upload-workers", type=int, default=2)
    parser.add_argument("--max-pending-upload-chunks", type=int, default=2)
    parser.add_argument("--upsert-batch-size", type=int, default=200)
    parser.add_argument("--upsert-timeout", type=int, default=120)
    parser.add_argument("--upsert-retries", type=int, default=5)
    parser.add_argument("--upsert-retry-wait", type=float, default=2.0)
    parser.add_argument("--with-embeddings", dest="with_embeddings", action="store_true", default=True)
    parser.add_argument("--no-embeddings", dest="with_embeddings", action="store_false")
    parser.add_argument("--stream-upsert", dest="stream_upsert", action="store_true", default=False)
    parser.add_argument("--no-stream-upsert", dest="stream_upsert", action="store_false")
    parser.add_argument("--local-maintain-mode", action="store_true")
    parser.add_argument("--mode", type=str, default="standard")
    args = parser.parse_args()

    if args.local_maintain_mode:
        args.embed_local_only = True
        args.stream_upsert = True

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
            if args.embed_local_only:
                embed_cpus, reserved_cpus = configure_local_embedding_runtime(args.reserve_upload_cpus)
                log(
                    f"[Embedding] 已切换为本地优先模式：embed_cpus={embed_cpus}, "
                    f"reserved_upload_cpus={reserved_cpus}"
                )
            log(
                f"[Embedding] 配置：model={model_name}, embed_device={args.embed_device}, "
                f"embed_devices={args.embed_devices or '<auto>'}, batch={args.embed_batch_size}, "
                f"chunk={args.embed_chunk_size}, max_length={args.embed_max_length}, "
                f"local_only={bool(args.embed_local_only)}, stream_upsert={bool(args.stream_upsert)}"
            )
            log("[Embedding] 开始执行文本向量编码阶段")
            emb_start = time.time()
            embed_devices = resolve_embed_devices(args.embed_devices, args.embed_device)
            if args.stream_upsert:
                stream_embed_and_upsert(
                    rows=rows,
                    url=url,
                    service_key=key,
                    table=papers_table,
                    schema=_norm(args.schema),
                    model_name=model_name,
                    devices=embed_devices,
                    embed_batch_size=max(int(args.embed_batch_size or 1), 1),
                    embed_chunk_size=max(int(args.embed_chunk_size or 1), 1),
                    embed_max_length=int(args.embed_max_length or 0),
                    embed_local_only=bool(args.embed_local_only),
                    upload_workers=max(int(args.upload_workers or 1), 1),
                    max_pending_upload_chunks=max(int(args.max_pending_upload_chunks or 1), 1),
                    upsert_batch_size=max(int(args.upsert_batch_size or 1), 1),
                    upsert_timeout=max(int(args.upsert_timeout or 1), 1),
                    upsert_retries=max(int(args.upsert_retries or 0), 0),
                    upsert_retry_wait=max(float(args.upsert_retry_wait or 0.0), 0.0),
                )
            else:
                attach_embeddings(
                    rows,
                    model_name=model_name,
                    devices=embed_devices,
                    batch_size=int(args.embed_batch_size or 8),
                    max_length=int(args.embed_max_length or 0),
                    allow_remote=not bool(args.embed_local_only),
                )
            log(
                f"[Embedding] 文本向量编码阶段结束，耗时 "
                f"{(time.time() - emb_start):.1f}s"
            )
        else:
            log("[Embedding] 已禁用 embedding 同步（--no-embeddings）")
        if (not args.with_embeddings) or (not args.stream_upsert):
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
