from __future__ import annotations

import copy
import os
from typing import Any, Dict, List, Tuple

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


ARXIV_SOURCE_KEY = "arxiv"
DEFAULT_SUPPORTED_SOURCES = (ARXIV_SOURCE_KEY, "biorxiv", "medrxiv", "chemrxiv", "neurips", "iclr", "icml", "acl", "emnlp", "aaai")


def _norm(value: Any) -> str:
    return str(value or "").strip()


def normalize_source_key(value: Any) -> str:
    return _norm(value).lower()


def normalize_source_list(value: Any) -> List[str]:
    if isinstance(value, str):
        raw_items = [value]
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = []

    out: List[str] = []
    seen = set()
    for item in raw_items:
        key = normalize_source_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _merge_dicts(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base if isinstance(base, dict) else {})
    for key, value in (override or {}).items():
        out[key] = value
    return out


def get_supabase_shared_config(config: Dict[str, Any]) -> Dict[str, Any]:
    cfg = config if isinstance(config, dict) else {}
    shared = cfg.get("supabase_shared")
    if isinstance(shared, dict):
        return copy.deepcopy(shared)
    return {}


def _env_bool(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name) or "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


def build_env_source_backend_overrides() -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}

    if _env_bool("DPR_ENABLE_BIORXIV_BACKEND", False):
        backend: Dict[str, Any] = {
            "enabled": _env_bool("DPR_BIORXIV_ENABLED", True),
            "papers_table": _norm(os.getenv("DPR_BIORXIV_PAPERS_TABLE") or "biorxiv_papers"),
            "use_vector_rpc": _env_bool("DPR_BIORXIV_USE_VECTOR_RPC", True),
            "vector_rpc": _norm(os.getenv("DPR_BIORXIV_VECTOR_RPC") or "match_biorxiv_papers_exact"),
            "vector_rpc_exact": _norm(os.getenv("DPR_BIORXIV_VECTOR_RPC_EXACT") or "match_biorxiv_papers_exact"),
            "use_bm25_rpc": _env_bool("DPR_BIORXIV_USE_BM25_RPC", True),
            "bm25_rpc": _norm(os.getenv("DPR_BIORXIV_BM25_RPC") or "match_biorxiv_papers_bm25"),
        }
        if _norm(os.getenv("DPR_BIORXIV_URL")):
            backend["url"] = _norm(os.getenv("DPR_BIORXIV_URL"))
        if _norm(os.getenv("DPR_BIORXIV_ANON_KEY")):
            backend["anon_key"] = _norm(os.getenv("DPR_BIORXIV_ANON_KEY"))
        if _norm(os.getenv("DPR_BIORXIV_SCHEMA")):
            backend["schema"] = _norm(os.getenv("DPR_BIORXIV_SCHEMA"))
        out["biorxiv"] = backend

    if _env_bool("DPR_ENABLE_MEDRXIV_BACKEND", False):
        backend = {
            "enabled": _env_bool("DPR_MEDRXIV_ENABLED", True),
            "papers_table": _norm(os.getenv("DPR_MEDRXIV_PAPERS_TABLE") or "medrxiv_papers"),
            "use_vector_rpc": _env_bool("DPR_MEDRXIV_USE_VECTOR_RPC", True),
            "vector_rpc": _norm(os.getenv("DPR_MEDRXIV_VECTOR_RPC") or "match_medrxiv_papers_exact"),
            "vector_rpc_exact": _norm(os.getenv("DPR_MEDRXIV_VECTOR_RPC_EXACT") or "match_medrxiv_papers_exact"),
            "use_bm25_rpc": _env_bool("DPR_MEDRXIV_USE_BM25_RPC", True),
            "bm25_rpc": _norm(os.getenv("DPR_MEDRXIV_BM25_RPC") or "match_medrxiv_papers_bm25"),
        }
        if _norm(os.getenv("DPR_MEDRXIV_URL")):
            backend["url"] = _norm(os.getenv("DPR_MEDRXIV_URL"))
        if _norm(os.getenv("DPR_MEDRXIV_ANON_KEY")):
            backend["anon_key"] = _norm(os.getenv("DPR_MEDRXIV_ANON_KEY"))
        if _norm(os.getenv("DPR_MEDRXIV_SCHEMA")):
            backend["schema"] = _norm(os.getenv("DPR_MEDRXIV_SCHEMA"))
        out["medrxiv"] = backend

    if _env_bool("DPR_ENABLE_CHEMRXIV_BACKEND", False):
        backend = {
            "enabled": _env_bool("DPR_CHEMRXIV_ENABLED", True),
            "papers_table": _norm(os.getenv("DPR_CHEMRXIV_PAPERS_TABLE") or "chemrxiv_papers"),
            "use_vector_rpc": _env_bool("DPR_CHEMRXIV_USE_VECTOR_RPC", True),
            "vector_rpc": _norm(os.getenv("DPR_CHEMRXIV_VECTOR_RPC") or "match_chemrxiv_papers_exact"),
            "vector_rpc_exact": _norm(os.getenv("DPR_CHEMRXIV_VECTOR_RPC_EXACT") or "match_chemrxiv_papers_exact"),
            "use_bm25_rpc": _env_bool("DPR_CHEMRXIV_USE_BM25_RPC", True),
            "bm25_rpc": _norm(os.getenv("DPR_CHEMRXIV_BM25_RPC") or "match_chemrxiv_papers_bm25"),
        }
        if _norm(os.getenv("DPR_CHEMRXIV_URL")):
            backend["url"] = _norm(os.getenv("DPR_CHEMRXIV_URL"))
        if _norm(os.getenv("DPR_CHEMRXIV_ANON_KEY")):
            backend["anon_key"] = _norm(os.getenv("DPR_CHEMRXIV_ANON_KEY"))
        if _norm(os.getenv("DPR_CHEMRXIV_SCHEMA")):
            backend["schema"] = _norm(os.getenv("DPR_CHEMRXIV_SCHEMA"))
        out["chemrxiv"] = backend

    if _env_bool("DPR_ENABLE_NEURIPS_BACKEND", False):
        backend = {
            "enabled": _env_bool("DPR_NEURIPS_ENABLED", True),
            "papers_table": _norm(os.getenv("DPR_NEURIPS_PAPERS_TABLE") or "neurips_openreview_papers"),
            "use_vector_rpc": _env_bool("DPR_NEURIPS_USE_VECTOR_RPC", True),
            "vector_rpc": _norm(os.getenv("DPR_NEURIPS_VECTOR_RPC") or "match_neurips_openreview_papers_exact"),
            "vector_rpc_exact": _norm(os.getenv("DPR_NEURIPS_VECTOR_RPC_EXACT") or "match_neurips_openreview_papers_exact"),
            "use_bm25_rpc": _env_bool("DPR_NEURIPS_USE_BM25_RPC", True),
            "bm25_rpc": _norm(os.getenv("DPR_NEURIPS_BM25_RPC") or "match_neurips_openreview_papers_bm25"),
        }
        if _norm(os.getenv("DPR_NEURIPS_URL")):
            backend["url"] = _norm(os.getenv("DPR_NEURIPS_URL"))
        if _norm(os.getenv("DPR_NEURIPS_ANON_KEY")):
            backend["anon_key"] = _norm(os.getenv("DPR_NEURIPS_ANON_KEY"))
        if _norm(os.getenv("DPR_NEURIPS_SCHEMA")):
            backend["schema"] = _norm(os.getenv("DPR_NEURIPS_SCHEMA"))
        out["neurips"] = backend

    if _env_bool("DPR_ENABLE_ICLR_BACKEND", False):
        backend = {
            "enabled": _env_bool("DPR_ICLR_ENABLED", True),
            "papers_table": _norm(os.getenv("DPR_ICLR_PAPERS_TABLE") or "iclr_openreview_papers"),
            "use_vector_rpc": _env_bool("DPR_ICLR_USE_VECTOR_RPC", True),
            "vector_rpc": _norm(os.getenv("DPR_ICLR_VECTOR_RPC") or "match_iclr_openreview_papers_exact"),
            "vector_rpc_exact": _norm(os.getenv("DPR_ICLR_VECTOR_RPC_EXACT") or "match_iclr_openreview_papers_exact"),
            "use_bm25_rpc": _env_bool("DPR_ICLR_USE_BM25_RPC", True),
            "bm25_rpc": _norm(os.getenv("DPR_ICLR_BM25_RPC") or "match_iclr_openreview_papers_bm25"),
        }
        if _norm(os.getenv("DPR_ICLR_URL")):
            backend["url"] = _norm(os.getenv("DPR_ICLR_URL"))
        if _norm(os.getenv("DPR_ICLR_ANON_KEY")):
            backend["anon_key"] = _norm(os.getenv("DPR_ICLR_ANON_KEY"))
        if _norm(os.getenv("DPR_ICLR_SCHEMA")):
            backend["schema"] = _norm(os.getenv("DPR_ICLR_SCHEMA"))
        out["iclr"] = backend

    if _env_bool("DPR_ENABLE_ICML_BACKEND", False):
        backend = {
            "enabled": _env_bool("DPR_ICML_ENABLED", True),
            "papers_table": _norm(os.getenv("DPR_ICML_PAPERS_TABLE") or "icml_openreview_papers"),
            "use_vector_rpc": _env_bool("DPR_ICML_USE_VECTOR_RPC", True),
            "vector_rpc": _norm(os.getenv("DPR_ICML_VECTOR_RPC") or "match_icml_openreview_papers_exact"),
            "vector_rpc_exact": _norm(os.getenv("DPR_ICML_VECTOR_RPC_EXACT") or "match_icml_openreview_papers_exact"),
            "use_bm25_rpc": _env_bool("DPR_ICML_USE_BM25_RPC", True),
            "bm25_rpc": _norm(os.getenv("DPR_ICML_BM25_RPC") or "match_icml_openreview_papers_bm25"),
        }
        if _norm(os.getenv("DPR_ICML_URL")):
            backend["url"] = _norm(os.getenv("DPR_ICML_URL"))
        if _norm(os.getenv("DPR_ICML_ANON_KEY")):
            backend["anon_key"] = _norm(os.getenv("DPR_ICML_ANON_KEY"))
        if _norm(os.getenv("DPR_ICML_SCHEMA")):
            backend["schema"] = _norm(os.getenv("DPR_ICML_SCHEMA"))
        out["icml"] = backend

    if _env_bool("DPR_ENABLE_ACL_BACKEND", False):
        backend = {
            "enabled": _env_bool("DPR_ACL_ENABLED", True),
            "papers_table": _norm(os.getenv("DPR_ACL_PAPERS_TABLE") or "acl_papers"),
            "use_vector_rpc": _env_bool("DPR_ACL_USE_VECTOR_RPC", True),
            "vector_rpc": _norm(os.getenv("DPR_ACL_VECTOR_RPC") or "match_acl_papers_exact"),
            "vector_rpc_exact": _norm(os.getenv("DPR_ACL_VECTOR_RPC_EXACT") or "match_acl_papers_exact"),
            "use_bm25_rpc": _env_bool("DPR_ACL_USE_BM25_RPC", True),
            "bm25_rpc": _norm(os.getenv("DPR_ACL_BM25_RPC") or "match_acl_papers_bm25"),
        }
        if _norm(os.getenv("DPR_ACL_URL")):
            backend["url"] = _norm(os.getenv("DPR_ACL_URL"))
        if _norm(os.getenv("DPR_ACL_ANON_KEY")):
            backend["anon_key"] = _norm(os.getenv("DPR_ACL_ANON_KEY"))
        if _norm(os.getenv("DPR_ACL_SCHEMA")):
            backend["schema"] = _norm(os.getenv("DPR_ACL_SCHEMA"))
        out["acl"] = backend

    if _env_bool("DPR_ENABLE_EMNLP_BACKEND", False):
        backend = {
            "enabled": _env_bool("DPR_EMNLP_ENABLED", True),
            "papers_table": _norm(os.getenv("DPR_EMNLP_PAPERS_TABLE") or "emnlp_papers"),
            "use_vector_rpc": _env_bool("DPR_EMNLP_USE_VECTOR_RPC", True),
            "vector_rpc": _norm(os.getenv("DPR_EMNLP_VECTOR_RPC") or "match_emnlp_papers_exact"),
            "vector_rpc_exact": _norm(os.getenv("DPR_EMNLP_VECTOR_RPC_EXACT") or "match_emnlp_papers_exact"),
            "use_bm25_rpc": _env_bool("DPR_EMNLP_USE_BM25_RPC", True),
            "bm25_rpc": _norm(os.getenv("DPR_EMNLP_BM25_RPC") or "match_emnlp_papers_bm25"),
        }
        if _norm(os.getenv("DPR_EMNLP_URL")):
            backend["url"] = _norm(os.getenv("DPR_EMNLP_URL"))
        if _norm(os.getenv("DPR_EMNLP_ANON_KEY")):
            backend["anon_key"] = _norm(os.getenv("DPR_EMNLP_ANON_KEY"))
        if _norm(os.getenv("DPR_EMNLP_SCHEMA")):
            backend["schema"] = _norm(os.getenv("DPR_EMNLP_SCHEMA"))
        out["emnlp"] = backend

    if _env_bool("DPR_ENABLE_AAAI_BACKEND", False):
        backend = {
            "enabled": _env_bool("DPR_AAAI_ENABLED", True),
            "papers_table": _norm(os.getenv("DPR_AAAI_PAPERS_TABLE") or "aaai_papers"),
            "use_vector_rpc": _env_bool("DPR_AAAI_USE_VECTOR_RPC", True),
            "vector_rpc": _norm(os.getenv("DPR_AAAI_VECTOR_RPC") or "match_aaai_papers_exact"),
            "vector_rpc_exact": _norm(os.getenv("DPR_AAAI_VECTOR_RPC_EXACT") or "match_aaai_papers_exact"),
            "use_bm25_rpc": _env_bool("DPR_AAAI_USE_BM25_RPC", True),
            "bm25_rpc": _norm(os.getenv("DPR_AAAI_BM25_RPC") or "match_aaai_papers_bm25"),
        }
        if _norm(os.getenv("DPR_AAAI_URL")):
            backend["url"] = _norm(os.getenv("DPR_AAAI_URL"))
        if _norm(os.getenv("DPR_AAAI_ANON_KEY")):
            backend["anon_key"] = _norm(os.getenv("DPR_AAAI_ANON_KEY"))
        if _norm(os.getenv("DPR_AAAI_SCHEMA")):
            backend["schema"] = _norm(os.getenv("DPR_AAAI_SCHEMA"))
        out["aaai"] = backend

    return out


def _normalize_backend_entry(
    raw: Dict[str, Any],
    *,
    default_papers_table: str,
    shared: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    entry = _merge_dicts(shared or {}, raw if isinstance(raw, dict) else {})
    vector_rpc_exact = _norm(entry.get("vector_rpc_exact") or "")
    vector_rpc = _norm(entry.get("vector_rpc") or "")
    return {
        "kind": _norm(entry.get("kind") or "supabase") or "supabase",
        "enabled": bool(entry.get("enabled", True)),
        "url": _norm(entry.get("url")),
        "anon_key": _norm(entry.get("anon_key")),
        "schema": _norm(entry.get("schema") or "public") or "public",
        "papers_table": _norm(entry.get("papers_table") or default_papers_table) or default_papers_table,
        "use_vector_rpc": bool(entry.get("use_vector_rpc", False)),
        # exact-only：优先使用显式 exact RPC；若缺失则兼容旧字段 vector_rpc
        "vector_rpc": vector_rpc_exact or vector_rpc or "match_papers_exact",
        "vector_rpc_exact": vector_rpc_exact or vector_rpc or "match_papers_exact",
        "use_bm25_rpc": bool(entry.get("use_bm25_rpc", False)),
        "bm25_rpc": _norm(entry.get("bm25_rpc") or "match_papers_bm25"),
        "sync_table": _norm(entry.get("sync_table") or ""),
        "sync_success_value": _norm(entry.get("sync_success_value") or ""),
    }


def _normalize_legacy_supabase_entry(raw: Dict[str, Any]) -> Dict[str, Any]:
    entry = _normalize_backend_entry(raw, default_papers_table=_norm(raw.get("papers_table") or "arxiv_papers") or "arxiv_papers")
    if not entry.get("vector_rpc"):
        entry["vector_rpc"] = _norm(raw.get("vector_rpc_exact") or raw.get("vector_rpc") or "match_arxiv_papers_exact")
    if not entry.get("vector_rpc_exact"):
        entry["vector_rpc_exact"] = entry["vector_rpc"] or "match_arxiv_papers_exact"
    if not entry.get("bm25_rpc"):
        entry["bm25_rpc"] = _norm(raw.get("bm25_rpc") or "match_arxiv_papers_bm25")
    if not entry.get("sync_table"):
        entry["sync_table"] = _norm(raw.get("sync_table") or "arxiv_sync_status")
    if not entry.get("sync_success_value"):
        entry["sync_success_value"] = _norm(raw.get("sync_success_value") or "success")
    return entry


def resolve_source_backends(config: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    cfg = config if isinstance(config, dict) else {}
    backends: Dict[str, Dict[str, Any]] = {}
    shared = get_supabase_shared_config(cfg)

    raw_backends = cfg.get("source_backends")
    if isinstance(raw_backends, dict):
        for raw_key, raw_value in raw_backends.items():
            source_key = normalize_source_key(raw_key)
            if not source_key:
                continue
            if not isinstance(raw_value, dict):
                continue
            backends[source_key] = _normalize_backend_entry(
                raw_value,
                default_papers_table="papers",
                shared=shared,
            )

    env_backends = build_env_source_backend_overrides()
    for source_key, override in env_backends.items():
        existing = backends.get(source_key) or {}
        merged = _merge_dicts(existing, override)
        backends[source_key] = _normalize_backend_entry(
            merged,
            default_papers_table="papers",
            shared=shared,
        )

    legacy_supabase = cfg.get("supabase")
    if ARXIV_SOURCE_KEY not in backends and isinstance(legacy_supabase, dict):
        backends[ARXIV_SOURCE_KEY] = _normalize_legacy_supabase_entry(legacy_supabase)

    return backends


def list_known_source_keys(config: Dict[str, Any]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in list(DEFAULT_SUPPORTED_SOURCES) + list(resolve_source_backends(config).keys()):
        key = normalize_source_key(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def get_source_backend(config: Dict[str, Any], source_key: str) -> Dict[str, Any]:
    return copy.deepcopy(resolve_source_backends(config).get(normalize_source_key(source_key)) or {})


def validate_profile_paper_sources(
    profile: Dict[str, Any],
    *,
    known_sources: List[str],
) -> Tuple[List[str], bool]:
    if not isinstance(profile, dict):
        return ([], False)

    if "paper_sources" not in profile:
        return ([ARXIV_SOURCE_KEY], True)

    normalized = normalize_source_list(profile.get("paper_sources"))
    if not normalized:
        tag = _norm(profile.get("tag") or "<unknown>")
        raise ValueError(f"词条「{tag}」的 paper_sources 不能为空。")

    unknown = [item for item in normalized if item not in known_sources]
    if unknown:
        tag = _norm(profile.get("tag") or "<unknown>")
        raise ValueError(f"词条「{tag}」包含未知论文源：{', '.join(unknown)}")

    return (normalized, False)


def migrate_source_config_inplace(config: Dict[str, Any]) -> tuple[bool, List[str]]:
    cfg = config if isinstance(config, dict) else {}
    changed = False
    notes: List[str] = []

    backends = resolve_source_backends(cfg)
    if backends:
        raw_backends = cfg.get("source_backends")
        if raw_backends != backends:
            cfg["source_backends"] = copy.deepcopy(backends)
            changed = True
            notes.append("已同步 source_backends。")

    subs = cfg.get("subscriptions")
    if subs is None:
        return changed, notes
    if not isinstance(subs, dict):
        raise ValueError("subscriptions 顶层结构必须为对象。")

    profiles = subs.get("intent_profiles")
    if not isinstance(profiles, list):
        return changed, notes

    known_sources = list_known_source_keys(cfg)
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        sources, filled = validate_profile_paper_sources(profile, known_sources=known_sources)
        if filled or profile.get("paper_sources") != sources:
            profile["paper_sources"] = sources
            changed = True
            tag = _norm(profile.get("tag") or "<unknown>")
            if filled:
                notes.append(f"词条「{tag}」缺少 paper_sources，已回填 [arxiv]。")
            else:
                notes.append(f"词条「{tag}」的 paper_sources 已规范化。")

    return changed, notes


def save_config(config: Dict[str, Any], path: str) -> None:
    if yaml is None:
        raise RuntimeError("未安装 PyYAML，无法写回 config.yaml。")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f, allow_unicode=True, sort_keys=False, width=10**9)


def load_config_with_source_migration(path: str, *, write_back: bool = True) -> Dict[str, Any]:
    if yaml is None:
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}

    if not isinstance(data, dict):
        return {}

    changed, _notes = migrate_source_config_inplace(data)
    if changed and write_back:
        save_config(data, path)
    return data
