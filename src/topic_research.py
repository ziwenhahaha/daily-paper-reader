"""专题研究统一编排（90天 / 365天 / 大礼包）：全面复用标准 Step 2→3→4→5→6 流水线。"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Callable, Dict, List, Tuple

import yaml

from conference_sidebar import (
    build_conference_paper_route,
    resolve_conference_pdf_url,
    resolve_publication_date,
)
from daily_report_state import (
    bootstrap_daily_state_from_sidebar,
    daily_state_path,
    entries_from_state,
    load_daily_state,
    merge_daily_state,
    save_daily_state,
)
from paper_dedupe import deduplicate_papers
from starter_pack_guide import (
    _escape,
    generate_guide,
    guide_cache_key,
    render_guide,
    validate_guide,
)
from starter_pack_publications import verify_publications
from starter_pack_retrieval import build_tasks, fingerprint, run_retrieval, write_json
from topic_research_export import export_records, render_export
from workflow_status import WorkflowStatusReporter


SRC_DIR = Path(__file__).resolve().parent
ROOT_DIR = SRC_DIR.parent
VERSION = "topic-research-v3"
MODES = {"90", "365", "starter"}
DEFAULT_MAX_PAPERS = 50
MAX_PAPERS_LIMIT = 100
DEFAULT_RERANK_POOL_LIMIT = 300
DEFAULT_MIN_SCORE = 6.0
DEFAULT_DEEP_MIN_SCORE = 8.0
DEFAULT_LLM_MIN_STAR = 4
DEFAULT_DOCS_CONCURRENCY = 4
RRF_K = 60

_MODULE_CACHE: Dict[str, Any] = {}


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def _load_step_module(filename: str, module_name: str):
    cached = _MODULE_CACHE.get(module_name)
    if cached is not None:
        return cached
    module_path = SRC_DIR / filename
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载标准流水线模块：{module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    _MODULE_CACHE[module_name] = module
    return module


def _slug_ascii(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").strip().lower()).strip("-")
    if slug:
        return slug[:40].rstrip("-")
    return "t" + fingerprint(str(text or ""))[:8]


def _resolve_summary_env() -> Dict[str, str]:
    env = os.environ.copy()
    api_key = (
        str(os.getenv("SUMMARY_API_KEY") or "").strip()
        or str(os.getenv("DEEPSEEK_API_KEY") or "").strip()
    )
    base_url = (
        str(os.getenv("SUMMARY_BASE_URL") or "").strip()
        or str(os.getenv("DEEPSEEK_BASE_URL") or "").strip()
    )
    model = (
        str(os.getenv("SUMMARY_MODEL") or "").strip()
        or str(os.getenv("DEEPSEEK_MODEL") or "").strip()
    )
    if api_key:
        env["SUMMARY_API_KEY"] = api_key
        env["DEEPSEEK_API_KEY"] = api_key
    if base_url:
        env["LLM_PRIMARY_BASE_URL"] = base_url
        env["SUMMARY_BASE_URL"] = base_url
        env["DEEPSEEK_BASE_URL"] = base_url
    if model:
        env["SUMMARY_MODEL"] = model
        env["DEEPSEEK_MODEL"] = model
    return env


def _default_step_runner(label: str, cmd: List[str], env: Dict[str, str] | None = None) -> None:
    log(f"[INFO] {label}: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(ROOT_DIR), check=True, env=env)


def safe_profile(value: Any, tag: str) -> Dict[str, Any]:
    if not isinstance(value, dict) or value.get("tag") != tag:
        raise ValueError("需求快照必须对应所选词条")
    result: Dict[str, Any] = {
        "tag": tag,
        "enabled": True,
        "paused": False,
        "paper_sources": ["arxiv"],
    }
    for key in ("description", "refinement"):
        text = value.get(key) or ""
        if not isinstance(text, str) or len(text) > 6000:
            raise ValueError("需求说明过长或格式无效")
        result[key] = text
    for key, field, maximum in (
        ("keywords", "keyword", 24),
        ("intent_queries", "query", 12),
    ):
        rows = value.get(key) or []
        if not isinstance(rows, list) or len(rows) > maximum:
            raise ValueError("查询数量超出任务预算")
        cleaned = []
        for row in rows:
            if isinstance(row, str):
                row = {field: row}
            if not isinstance(row, dict):
                raise ValueError("查询格式无效")
            if str(row.get("enabled", True)).strip().lower() in (
                "false",
                "0",
                "no",
                "off",
            ):
                continue
            text = (
                (row.get("keyword") or row.get("text") or row.get("query") or "")
                if key == "keywords"
                else (row.get(field) or "")
            )
            if not isinstance(text, str) or not text.strip() or len(text) > 1200:
                raise ValueError("查询内容无效")
            entry = {field: text.strip(), "enabled": True}
            if key == "keywords" and row.get("query"):
                semantic = row["query"]
                if not isinstance(semantic, str) or len(semantic) > 1200:
                    raise ValueError("语义重写内容无效")
                entry["query"] = semantic.strip()
            cleaned.append(entry)
        result[key] = cleaned
    groups = value.get("constraint_groups") or []
    if groups:
        combinations = 1
        if not isinstance(groups, list) or len(groups) > 3:
            raise ValueError("检索约束组无效")
        for group in groups:
            if (
                not isinstance(group, list)
                or not 1 <= len(group) <= 8
                or any(
                    not isinstance(term, str)
                    or not term.strip()
                    or len(term) > 300
                    or not re.search(r"[A-Za-z]", term)
                    or re.search(r"[\u3400-\u9fff]", term)
                    for term in group
                )
            ):
                raise ValueError("约束组必须包含可执行的英文检索词")
            combinations *= len(group)
        if combinations > 32:
            raise ValueError("检索约束组合超过32种")
        result["constraint_groups"] = copy.deepcopy(groups)
    if result["refinement"] and not groups:
        raise ValueError("细化需求缺少实际检索约束，不能只修改显示说明")
    return result


def build_topic_token(
    arxiv_start: str,
    as_of: str,
    mode: str,
    profile_tag: str,
    snapshot: Dict[str, Any] | None = None,
) -> str:
    start = date.fromisoformat(str(arxiv_start)[:10])
    end = date.fromisoformat(str(as_of)[:10]) - timedelta(days=1)
    span = f"{start:%Y%m%d}-{end:%Y%m%d}"
    mode_slug = re.sub(r"[^a-z0-9]+", "", str(mode or "starter").lower()) or "topic"
    tag_slug = _slug_ascii(profile_tag)
    token = f"{span}-{mode_slug}-{tag_slug}"
    snap = snapshot or {}
    if snap.get("refinement") or snap.get("constraint_groups"):
        suffix = fingerprint(
            {
                "refinement": snap.get("refinement") or "",
                "constraint_groups": snap.get("constraint_groups") or [],
            }
        )[:6]
        token = f"{token}-{suffix}"
    return token


def _mode_display_label(mode: str, arxiv_days: int) -> str:
    if mode == "starter":
        return "大礼包"
    if mode in {"90", "365"}:
        return f"{mode}天"
    return f"{arxiv_days}天"


def research_plan(
    config: Dict[str, Any],
    profile_tag: str,
    mode: str,
    as_of: str,
    profile_snapshot: Dict[str, Any] | None = None,
    conferences: List[str] | None = None,
    *,
    arxiv_days: int | None = None,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if mode not in MODES and arxiv_days is None:
        raise ValueError("专题研究仅支持90天、365天和研究方向大礼包")
    date.fromisoformat(as_of)
    profiles = (config.get("subscriptions") or {}).get("intent_profiles") or []
    original = [
        p for p in profiles if isinstance(p, dict) and p.get("tag") == profile_tag
    ]
    if len(original) != 1:
        raise ValueError("请选择唯一已保存词条")
    snapshot = safe_profile(
        profile_snapshot if profile_snapshot is not None else original[0], profile_tag
    )
    scoped = copy.deepcopy(config)
    scoped.setdefault("subscriptions", {})["intent_profiles"] = [snapshot]
    effective_days = (
        int(arxiv_days)
        if arxiv_days is not None
        else (90 if mode == "90" else 365)
    )
    plan = build_tasks(
        scoped,
        profile_tag,
        as_of,
        conferences if mode == "starter" else [],
        arxiv_days=effective_days,
        bounded=True,
    )
    plan.update(
        mode=mode,
        arxiv_days=effective_days,
        snapshot=snapshot,
        research_version=VERSION,
    )
    if mode != "starter":
        plan["windows"].pop("conference", None)
    topic_token = build_topic_token(
        plan["windows"]["arxiv"]["start"], as_of, mode, profile_tag, snapshot
    )
    plan["topic_token"] = topic_token
    plan["run_id"] = topic_token
    return plan, scoped


def _conference_key(paper: Dict[str, Any]) -> str:
    if str(paper.get("source") or "").lower() == "arxiv" or paper.get("retrieval_source") == "arxiv":
        return ""
    value = str(
        paper.get("conference")
        or paper.get("conference_key")
        or re.split(r"[-_ ]20\d{2}", str(paper.get("source") or ""))[0]
    ).strip().lower()
    return "" if value in ("", "arxiv") else value


def _qualified_version(paper: Dict[str, Any]) -> bool:
    if not str(paper.get("abstract") or "").strip():
        return False
    if paper.get("publication_window_status") in ("excluded", "uncertain"):
        return False
    if paper.get("conference_acceptance_status") in (
        "unverified",
        "rejected",
        "withdrawn",
    ):
        return False
    return True


def _project_version(work: Dict[str, Any], selected: Dict[str, Any]) -> Dict[str, Any]:
    projected = copy.deepcopy(selected)
    projected["canonical_id"] = work.get("canonical_id") or selected.get("id")
    projected["versions"] = copy.deepcopy(work.get("versions") or [selected])
    if work.get("route_aliases"):
        projected["route_aliases"] = list(work["route_aliases"])
    return projected


def _project_qualified_work(work: Dict[str, Any]) -> Dict[str, Any] | None:
    if _qualified_version(work):
        return _project_version(work, work)
    versions = work.get("versions") or [work]
    qualified = [v for v in versions if _qualified_version(v)]
    if not qualified:
        return None
    qualified.sort(
        key=lambda p: (
            -len(str(p.get("abstract") or "")),
            not bool(p.get("pdf_url")),
            str(p.get("id") or ""),
        )
    )
    return _project_version(work, qualified[0])


def build_standard_rrf_payload(
    deduped_works: List[Dict[str, Any]],
    plan: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Dict[str, Any]], Dict[str, int]]:
    """把多源去重后的合格候选桥接为标准 Step 2.3 RRF JSON，直接喂给 3.rank_papers.py。"""
    profile = plan.get("profile") or {}
    tag = str(profile.get("tag") or "").strip()
    papers: List[Dict[str, Any]] = []
    works_by_id: Dict[str, Dict[str, Any]] = {}
    lane_scores: Dict[Tuple[str, str], Dict[str, float]] = {}
    excluded_unqualified = 0

    for work in deduped_works:
        projected = _project_qualified_work(work)
        if projected is None:
            excluded_unqualified += 1
            continue
        pid = str(projected.get("id") or projected.get("canonical_id") or "").strip()
        if not pid or pid in works_by_id:
            continue
        projected["id"] = pid
        paper_tags = set()
        for version in work.get("versions") or [work]:
            if not _qualified_version(version):
                continue
            for ev in version.get("retrieval_evidence") or []:
                lane = str(ev.get("lane") or "").strip().lower()
                query_text = str(ev.get("query_text") or ev.get("query") or "").strip()
                if not lane or not query_text:
                    continue
                rank = ev.get("rank")
                if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
                    rank = 1
                lane_key = (lane, query_text)
                bucket = lane_scores.setdefault(lane_key, {})
                bucket[pid] = bucket.get(pid, 0.0) + 1.0 / (RRF_K + rank)
                paper_tags.add(f"keyword:{tag}" if lane == "bm25" else f"query:{tag}")
        if not paper_tags and tag:
            paper_tags.add(f"query:{tag}")
        projected["tags"] = sorted(paper_tags)
        papers.append(projected)
        works_by_id[pid] = projected

    queries: List[Dict[str, Any]] = []
    has_intent = False
    for (lane, query_text), score_map in sorted(lane_scores.items()):
        if not score_map:
            continue
        ranked_items = sorted(score_map.items(), key=lambda item: (-item[1], item[0]))
        sim_scores = {
            pid: {"score": float(score), "rank": idx}
            for idx, (pid, score) in enumerate(ranked_items, start=1)
        }
        q_type = "intent_query" if lane == "embedding" else "keyword"
        if q_type == "intent_query":
            has_intent = True
        queries.append(
            {
                "type": q_type,
                "tag": tag,
                "paper_tag": f"query:{tag}" if q_type == "intent_query" else f"keyword:{tag}",
                "query_text": query_text,
                "sim_scores": sim_scores,
            }
        )

    # 3.rank_papers.py 仅对 intent_query 执行 Qwen3 重排；若用户词条只配了关键词，
    # 自动补充一条语义汇总 intent_query，确保标准 Step 3 仍正常执行。
    if not has_intent and papers:
        combined_scores: Dict[str, float] = {}
        for q in queries:
            for pid, meta in (q.get("sim_scores") or {}).items():
                rank = int((meta or {}).get("rank") or 1)
                combined_scores[pid] = combined_scores.get(pid, 0.0) + 1.0 / (RRF_K + rank)
        if not combined_scores:
            combined_scores = {p["id"]: 1.0 / (RRF_K + i) for i, p in enumerate(papers, 1)}
        ranked_items = sorted(combined_scores.items(), key=lambda item: (-item[1], item[0]))
        fallback_query = (
            str(profile.get("description") or "").strip()
            or "; ".join(profile.get("review_keywords") or [])
            or tag
        )
        queries.append(
            {
                "type": "intent_query",
                "tag": tag,
                "paper_tag": f"query:{tag}",
                "query_text": fallback_query,
                "sim_scores": {
                    pid: {"score": float(score), "rank": idx}
                    for idx, (pid, score) in enumerate(ranked_items, start=1)
                },
            }
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "papers": papers,
        "queries": queries,
    }
    stats = {
        "deduplicated_count": len(deduped_works),
        "eligible_count": len(papers),
        "excluded_unqualified_count": excluded_unqualified,
        "query_lane_count": len(queries),
    }
    return payload, works_by_id, stats


def _write_scoped_llm_config(path: Path, base_config: Dict[str, Any], snapshot: Dict[str, Any]) -> None:
    scoped = copy.deepcopy(base_config or {})
    prof = copy.deepcopy(snapshot)
    if prof.get("refinement"):
        desc = str(prof.get("description") or "").strip()
        ref = str(prof["refinement"]).strip()
        prof["description"] = f"{desc}\nFocused refinement constraint: {ref}".strip()
    scoped.setdefault("subscriptions", {})["intent_profiles"] = [prof]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(scoped, allow_unicode=True, sort_keys=False, width=10**9),
        encoding="utf-8",
    )


def _max_rerank_scores(llm_payload: Dict[str, Any]) -> Dict[str, float]:
    best: Dict[str, float] = {}
    for query in llm_payload.get("queries") or []:
        if not isinstance(query, dict):
            continue
        for item in query.get("ranked") or []:
            if not isinstance(item, dict):
                continue
            pid = str(item.get("paper_id") or "").strip()
            if not pid:
                continue
            try:
                score = float(item.get("score") or 0.0)
            except (TypeError, ValueError):
                score = 0.0
            if pid not in best or score > best[pid]:
                best[pid] = score
    return best


def select_topic_papers(
    llm_payload: Dict[str, Any],
    works_by_id: Dict[str, Dict[str, Any]],
    profile_tag: str,
    *,
    max_papers: int = DEFAULT_MAX_PAPERS,
    min_score: float = DEFAULT_MIN_SCORE,
    deep_min_score: float = DEFAULT_DEEP_MIN_SCORE,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """复用标准 Step 5 映射逻辑与分数阈值（≥8精读、6–8速读），不排除已见论文。"""
    if isinstance(max_papers, bool) or not isinstance(max_papers, int) or not 1 <= max_papers <= MAX_PAPERS_LIMIT:
        raise ValueError(f"精选上限必须为 1–{MAX_PAPERS_LIMIT} 的整数")
    selector = _load_step_module("5.select_papers.py", "dpr_select_papers_for_topic")
    papers = llm_payload.get("papers") or []
    llm_ranked = llm_payload.get("llm_ranked") or []
    scored = selector.build_scored_papers(papers, llm_ranked)
    rerank_scores = _max_rerank_scores(llm_payload)

    eligible: List[Dict[str, Any]] = []
    seen_canonical = set()
    for item in scored:
        score = float(item.get("llm_score") or 0.0)
        if score < float(min_score):
            continue
        pid = str(item.get("id") or "").strip()
        work = works_by_id.get(pid)
        if work:
            merged = copy.deepcopy(work)
            merged.update(item)
        else:
            merged = dict(item)
        canonical = str(merged.get("canonical_id") or pid)
        if canonical in seen_canonical:
            continue
        seen_canonical.add(canonical)
        merged["score"] = score
        merged["rerank_score"] = rerank_scores.get(pid, 0.0)
        merged["selection_source"] = "topic_research"
        tags: List[str] = []
        seen_tags_lower = set()
        for candidate_tag in (
            list(merged.get("llm_tags") or [])
            + ([f"query:{profile_tag}"] if profile_tag else [])
            + list(merged.get("tags") or [])
        ):
            raw_tag = str(candidate_tag or "").strip()
            if not raw_tag:
                continue
            tag_label = raw_tag.split(":", 1)[1].strip() if ":" in raw_tag else raw_tag
            key_lower = tag_label.lower()
            if not key_lower or key_lower in seen_tags_lower:
                continue
            seen_tags_lower.add(key_lower)
            tags.append(raw_tag)
        merged["llm_tags"] = tags
        eligible.append(merged)

    def _arxiv_sort_key(paper: Dict[str, Any]) -> str:
        joined = " ".join(
            str(paper.get(k) or "") for k in ("id", "canonical_id", "route", "link", "pdf_url")
        )
        m = re.search(
            r"(?:^|[/:_-])(\d{2})(0[1-9]|1[0-2])\.(\d{4,5})(?:v\d+)?(?=$|[^0-9])",
            joined,
        )
        if not m:
            return ""
        return f"20{m.group(1)}-{m.group(2)}-{m.group(3).zfill(5)}"

    def _recency_sort_key(paper: Dict[str, Any]) -> str:
        pub = str(paper.get("publication_date") or paper.get("published") or "").strip()
        if re.match(r"^\d{4}(?:-\d{2}(?:-\d{2})?)?", pub):
            return pub[:10]
        arxiv_key = _arxiv_sort_key(paper)
        if arxiv_key:
            return arxiv_key[:7]
        year = str(paper.get("conference_year") or paper.get("year") or "").strip()
        return year if re.fullmatch(r"\d{4}", year) else ""

    def _star_rank(paper: Dict[str, Any]) -> int:
        # 与前端 starHtmlFromScore 的 Math.round(score / 2) 保持一致（四舍五入 half-up）
        s = float(paper.get("llm_score") or 0.0)
        return max(0, min(5, int((s / 2.0) + 0.5)))

    eligible.sort(key=lambda p: str(p.get("canonical_id") or p.get("id") or ""))
    # 先按精确相关分截断 Top-N，避免低分挤掉高分；入选后再按“星级降序 → 会议优先 → 时间降序”排展示顺序
    eligible.sort(
        key=lambda p: (
            float(p.get("llm_score") or 0.0),
            1 if _conference_key(p) else 0,
            _recency_sort_key(p),
            _arxiv_sort_key(p),
            float(p.get("rerank_score") or 0.0),
        ),
        reverse=True,
    )
    selected = eligible[:max_papers]

    def _display_sort_key(paper: Dict[str, Any]):
        return (
            _star_rank(paper),
            1 if _conference_key(paper) else 0,
            _recency_sort_key(paper),
            _arxiv_sort_key(paper),
            float(paper.get("llm_score") or 0.0),
            float(paper.get("rerank_score") or 0.0),
        )

    deep_dive = sorted(
        [p for p in selected if float(p.get("llm_score") or 0.0) >= float(deep_min_score)],
        key=_display_sort_key,
        reverse=True,
    )
    quick_skim = sorted(
        [p for p in selected if float(p.get("llm_score") or 0.0) < float(deep_min_score)],
        key=_display_sort_key,
        reverse=True,
    )
    return deep_dive, quick_skim


def _paper_identities(paper: Dict[str, Any]) -> set[Tuple[str, str]]:
    found: set[Tuple[str, str]] = set()
    for field in ("id", "arxiv_id", "paper_id"):
        raw = str(paper.get(field) or "").strip()
        if raw:
            found.add(("id", raw.lower()))
            base = re.sub(r"v\d+$", "", raw, flags=re.I)
            if re.fullmatch(r"\d{4}\.\d{4,5}", base):
                found.add(("arxiv_exact", raw.lower()))
    doi = str(paper.get("doi") or "").strip().lower()
    if doi:
        found.add(("doi", doi))
    return found


def _build_existing_route_index(docs: Path, generator: Any) -> Dict[Tuple[str, str], List[str]]:
    index: Dict[Tuple[str, str], List[str]] = {}
    if not docs.exists():
        return index
    for path in sorted(docs.rglob("*.md")):
        rel = path.relative_to(docs).as_posix()
        if rel.startswith(("_", "starter-pack/", "long-range/")) or path.name.upper() == "README.MD" or path.name == "papers.md":
            continue
        route = rel[:-3]
        try:
            head = path.read_text(encoding="utf-8", errors="ignore")[:4000]
        except OSError:
            continue
        meta = generator._parse_front_matter(head)
        if not meta:
            continue
        ids = _paper_identities(meta)
        stem = path.stem.lower()
        arxiv_match = re.match(r"^(\d{4}\.\d{4,5}v\d+)(?:-|$)", stem)
        if arxiv_match:
            ids.add(("id", arxiv_match.group(1)))
            ids.add(("arxiv_exact", arxiv_match.group(1)))
        for key in ids:
            routes = index.setdefault(key, [])
            if route not in routes:
                routes.append(route)
    return index


def _route_matches_version(docs: Path, route: str, paper: Dict[str, Any], generator: Any) -> bool:
    doc = docs / f"{route}.md"
    if not doc.exists():
        return False
    meta = generator._parse_front_matter(doc.read_text(encoding="utf-8", errors="ignore")[:4000])
    conf = _conference_key(paper)
    if conf:
        year = str(paper.get("conference_year") or paper.get("year") or "")
        expected_prefix = f"conference/{conf}-{year}/" if year else f"conference/{conf}"
        if not route.startswith(expected_prefix):
            return False
    elif route.startswith("conference/"):
        return False
    paper_id = str(paper.get("id") or "").strip().lower()
    meta_id = str(meta.get("id") or "").strip().lower()
    if paper_id and meta_id:
        return paper_id == meta_id
    stem = doc.stem.lower()
    return bool(paper_id and (stem == paper_id or stem.startswith(paper_id + "-")))


def _resolve_paper_pdf(paper: Dict[str, Any]) -> str:
    conf = _conference_key(paper)
    official_pdf = ""
    if conf:
        official_pdf = str(paper.get("official_pdf_url") or "").strip()
        if not official_pdf:
            for version in paper.get("versions") or []:
                if (
                    isinstance(version, dict)
                    and version.get("official_pdf_url")
                    and _qualified_version(version)
                    and str(version.get("id") or "") == str(paper.get("id") or "")
                    and _conference_key(version) == conf
                ):
                    official_pdf = str(version["official_pdf_url"]).strip()
                    break
    pdf = official_pdf or str(paper.get("pdf_url") or paper.get("pdf") or "").strip()
    if not pdf and not conf and re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", str(paper.get("id") or "")):
        pdf = f"https://arxiv.org/pdf/{paper['id']}"
    if not pdf and conf:
        pdf = resolve_conference_pdf_url(paper)
    return pdf


def _assign_route(
    docs: Path,
    paper: Dict[str, Any],
    topic_token: str,
    existing_index: Dict[Tuple[str, str], List[str]],
    generator: Any,
) -> str:
    for key in sorted(_paper_identities(paper)):
        for candidate in existing_index.get(key, []):
            if _route_matches_version(docs, candidate, paper, generator):
                return candidate
    conf = _conference_key(paper)
    if conf:
        year = str(paper.get("conference_year") or paper.get("year") or "")
        return build_conference_paper_route(paper, conf, year)
    title = str(paper.get("title") or "").strip()
    pid = str(paper.get("id") or paper.get("paper_id") or "").strip()
    _, _, route = generator.prepare_paper_paths(str(docs), topic_token, title, pid)
    return route


def _action_bar_markdown(export_path: str) -> str:
    return (
        '<div class="dpr-topic-result-actions">'
        f'<button type="button" class="arxiv-tool-btn" data-topic-copy="{_escape(export_path)}">复制完整清单</button> '
        f'<a class="arxiv-tool-btn" href="{_escape(export_path)}" download data-no-router>下载 Markdown 清单</a>'
        "</div>\n\n"
    )


def _inject_action_bar_after_h1(markdown_text: str, actions_md: str) -> str:
    lines = markdown_text.splitlines(keepends=True)
    if lines and lines[0].startswith("# "):
        rest = "".join(lines[1:]).lstrip("\n")
        return lines[0] + "\n" + actions_md + rest
    return actions_md + markdown_text


def _generate_or_load_guide(
    root: Path,
    plan: Dict[str, Any],
    papers: List[Dict[str, Any]],
    guide_client_factory: Callable[[], Any] | None = None,
) -> Dict[str, Any]:
    env = _resolve_summary_env()
    model = env.get("SUMMARY_MODEL") or env.get("DEEPSEEK_MODEL") or "deepseek-v4-flash"
    endpoint = env.get("SUMMARY_BASE_URL") or env.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
    key = guide_cache_key(plan["profile"], papers, model, endpoint)
    cache_path = root / ".local-runs/topic-research-cache/guides" / f"{key}.json"
    if cache_path.exists():
        try:
            return validate_guide(json.loads(cache_path.read_text(encoding="utf-8")), papers)
        except Exception:
            pass
    client = None
    if papers:
        if guide_client_factory is not None:
            client = guide_client_factory()
        else:
            from llm import DeepSeekClient

            api_key = env.get("SUMMARY_API_KEY") or env.get("DEEPSEEK_API_KEY") or ""
            if not api_key:
                raise RuntimeError("缺少导读模型凭据（SUMMARY_API_KEY / DEEPSEEK_API_KEY）")
            client = DeepSeekClient(api_key, model, endpoint)
            client.kwargs.update(max_tokens=16000, thinking={"type": "disabled"})
    guide = generate_guide(plan["profile"], papers, client)
    write_json(cache_path, guide)
    return guide


def publish_topic_results(
    root: Path,
    plan: Dict[str, Any],
    deep_dive: List[Dict[str, Any]],
    quick_skim: List[Dict[str, Any]],
    coverage: Dict[str, Any],
    *,
    docs_concurrency: int = DEFAULT_DOCS_CONCURRENCY,
    guide_client_factory: Callable[[], Any] | None = None,
    status_reporter: WorkflowStatusReporter | None = None,
) -> Dict[str, Any]:
    """使用标准 Step 6 process_paper + 单轨 _sidebar.md/_daily_state.json/papers.meta.json 发布成果。"""
    root = Path(root).resolve()
    if root == ROOT_DIR and os.getenv("GITHUB_REPOSITORY", "").strip().lower() in (
        "",
        "ziwenhahaha/daily-paper-reader",
    ):
        raise ValueError("主仓库不能写入个性化专题研究结果，请使用独立 root 或 Fork")

    summary_env = _resolve_summary_env()
    for key in (
        "SUMMARY_API_KEY",
        "DEEPSEEK_API_KEY",
        "SUMMARY_BASE_URL",
        "DEEPSEEK_BASE_URL",
        "LLM_PRIMARY_BASE_URL",
        "SUMMARY_MODEL",
        "DEEPSEEK_MODEL",
    ):
        if summary_env.get(key):
            os.environ[key] = summary_env[key]

    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    generator = _load_step_module("6.generate_docs.py", "dpr_generate_docs_for_topic")
    topic_token = plan["topic_token"]
    tag = str(plan["profile"]["tag"])
    mode = str(plan["mode"])
    arxiv_start = plan["windows"]["arxiv"]["start"]
    as_of = plan["as_of"]
    start_date = date.fromisoformat(arxiv_start[:10])
    end_date = date.fromisoformat(as_of[:10]) - timedelta(days=1)
    window_label = f"{start_date} ~ {end_date}"
    conf_window = (plan.get("windows") or {}).get("conference") or {}
    if mode == "starter":
        conf_start_raw = str(conf_window.get("start") or "")[:10]
        coverage_window_label = (
            f"arXiv {start_date} ~ {end_date}；顶会近 24 个月（{conf_start_raw} ~ {end_date}）"
            if conf_start_raw
            else f"arXiv {start_date} ~ {end_date}；顶会近 24 个月"
        )
    else:
        coverage_window_label = f"arXiv {window_label}"
    mode_label = _mode_display_label(mode, int(plan.get("arxiv_days") or 365))
    sidebar_label = (
        f"{tag} · {mode_label}（截至 {end_date}）"
        if mode == "starter"
        else f"{tag} · {mode_label}（{window_label}）"
    )

    all_selected = [(p, "deep") for p in deep_dive] + [(p, "quick") for p in quick_skim]
    existing_index = _build_existing_route_index(docs, generator)

    # 先解析精选论文的官方会议 PDF（不拖累大候选池）
    if all_selected:
        resolved_all = verify_publications(
            [p for p, _ in all_selected], root, resolve_pdfs=True
        )
        all_selected = [
            (resolved_all[i], sec) for i, (_, sec) in enumerate(all_selected)
        ]

    # 预先分配确定性 route，并发调用标准 Step 6 process_paper()
    tasks: List[Tuple[int, Dict[str, Any], str, str]] = []
    for idx, (paper, sec) in enumerate(all_selected):
        conf = _conference_key(paper)
        if conf:
            pub = resolve_publication_date(
                paper,
                conf,
                str(paper.get("conference_year") or paper.get("year") or ""),
            )
            paper.update(pub)
            if not paper.get("published") and pub.get("publication_date"):
                paper["published"] = pub["publication_date"]
        paper["pdf_url"] = _resolve_paper_pdf(paper)
        route = _assign_route(docs, paper, topic_token, existing_index, generator)
        paper["route"] = route
        tasks.append((idx, paper, sec, route))

    generated_results: Dict[int, Tuple[Dict[str, Any], str, str]] = {}
    failed_papers: List[str] = []
    workers = max(1, int(docs_concurrency or DEFAULT_DOCS_CONCURRENCY))
    if tasks:
        total_docs = len(tasks)
        done_docs = 0
        if status_reporter is not None:
            status_reporter.report(
                step_code="step6",
                step_label="Step 6 生成论文与图表",
                progress_current=0,
                progress_total=total_docs,
                detail=f"共 {total_docs} 篇（精读 {len(deep_dive)} / 速读 {len(quick_skim)}）",
                force=True,
            )
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    generator.process_paper,
                    paper,
                    sec,
                    topic_token,
                    str(docs),
                    False,
                    False,
                    route,
                    False,
                ): (idx, paper, sec, route)
                for idx, paper, sec, route in tasks
            }
            for future in as_completed(futures):
                idx, paper, sec, route = futures[future]
                try:
                    resolved_route, _ = future.result()
                    paper["route"] = resolved_route
                    generated_results[idx] = (paper, sec, resolved_route)
                except Exception as exc:
                    pid = str(paper.get("id") or route)
                    log(f"[WARN] Step 6 生成论文失败（已隔离继续）：{pid}: {exc}")
                    failed_papers.append(pid)
                finally:
                    done_docs += 1
                    if status_reporter is not None:
                        status_reporter.report(
                            step_code="step6",
                            step_label="Step 6 生成论文与图表",
                            progress_current=done_docs,
                            progress_total=total_docs,
                        )

    ordered_done = [generated_results[i] for i in sorted(generated_results)]
    deep_done = [p for p, sec, _ in ordered_done if sec == "deep"]
    quick_done = [p for p, sec, _ in ordered_done if sec != "deep"]
    final_papers = [p for p, _, _ in ordered_done]

    # 从已生成的标准 Markdown 回读 title_zh / tldr / evidence，供导读与侧边栏使用
    records_for_state: List[Dict[str, Any]] = []
    paper_meta_by_id: Dict[str, Dict[str, Any]] = {}
    for paper, sec, route in ordered_done:
        md_path = docs / f"{route}.md"
        meta = (
            generator._parse_front_matter(md_path.read_text(encoding="utf-8", errors="ignore"))
            if md_path.exists()
            else {}
        )
        if meta.get("tldr") and not paper.get("tldr"):
            paper["tldr"] = meta["tldr"]
        if meta.get("title_zh"):
            paper["zh_title"] = meta["title_zh"]
        evidence = str(
            paper.get("llm_evidence_cn")
            or paper.get("canonical_evidence")
            or meta.get("evidence")
            or ""
        ).strip()
        paper["canonical_evidence"] = evidence
        raw_tags = generator.build_tags_list(sec, paper.get("llm_tags") or [f"query:{tag}"])
        state_tags = []
        for raw_tag in raw_tags:
            kind, _, label = raw_tag.partition(":")
            if label:
                state_tags.append({"kind": kind or "query", "label": label})
        records_for_state.append(
            {
                "paper_id": str(paper.get("id") or route),
                "route": route,
                "title": str(paper.get("title") or route).strip(),
                "section": sec,
                "tags": state_tags,
                "score": paper.get("llm_score", paper.get("score")),
                "evidence": evidence,
            }
        )
        link = str(
            paper.get("official_link")
            or paper.get("link")
            or paper.get("pdf_url")
            or ""
        ).strip()
        paper_meta_by_id[route] = {
            "link": link,
            "published": str(paper.get("published") or ""),
            "publication_date": str(paper.get("publication_date") or paper.get("published") or ""),
            "publication_date_precision": str(paper.get("publication_date_precision") or ""),
            "publication_date_source": str(paper.get("publication_date_source") or ""),
            "publication_date_kind": str(paper.get("publication_date_kind") or ""),
            "conference_year": str(paper.get("conference_year") or paper.get("year") or ""),
        }

    # 1. 导出清单（docs/<topic_token>/papers.md & papers.json）
    topic_dir = docs / topic_token
    topic_dir.mkdir(parents=True, exist_ok=True)
    export_rel_path = f"docs/{topic_token}/papers.md"
    for p, sec, _ in ordered_done:
        p["_export_section"] = sec
    exports = export_records(final_papers)
    description = str((plan.get("profile") or {}).get("description") or "").strip()
    refinement = str((plan.get("snapshot") or {}).get("refinement") or "").strip()
    export_meta = {
        "description": description,
        "refinement": refinement,
        "window": coverage_window_label,
    }
    (topic_dir / "papers.md").write_text(
        render_export(exports, f"{tag} · {mode_label}", export_meta),
        encoding="utf-8",
    )
    write_json(topic_dir / "papers.json", exports)

    # 2. 更新标准 _daily_state.json + _sidebar.md（单轨）+ papers.meta.json
    generated_at = datetime.now(timezone.utc).isoformat()
    state_file = daily_state_path(str(docs), topic_token)
    existing_state = load_daily_state(state_file) or bootstrap_daily_state_from_sidebar(
        str(docs / "_sidebar.md"), topic_token, date_label=sidebar_label, generated_at=generated_at
    )
    merged_state = merge_daily_state(
        existing_state,
        topic_token,
        records_for_state,
        generated_at,
        True,
        date_label=sidebar_label,
    )
    save_daily_state(state_file, merged_state)
    deep_entries, quick_entries, evidence_by_route = entries_from_state(merged_state)

    topic_meta = {
        "mode": mode,
        "tag": tag,
        "report": f"#/{topic_token}/README",
        "export": export_rel_path,
        "as_of": as_of,
        "window": coverage_window_label,
    }
    if description:
        topic_meta["description"] = description[:240]
    if refinement:
        topic_meta["refinement"] = refinement[:240]

    generator.update_sidebar(
        str(docs / "_sidebar.md"),
        topic_token,
        deep_entries,
        quick_entries,
        evidence_by_route,
        date_label=sidebar_label,
        replace_existing=True,
        topic_meta=topic_meta,
        paper_meta_by_id=paper_meta_by_id,
    )
    generator.write_day_meta_index_json(
        str(docs),
        topic_token,
        sidebar_label,
        deep_done,
        quick_done,
        merged_deep_entries=deep_entries,
        merged_quick_entries=quick_entries,
    )

    # 3. 写入 docs/<topic_token>/README.md（大礼包为方向导读，90/365 为标准总览报告）
    actions_md = _action_bar_markdown(export_rel_path)

    def _build_topic_catalog_markdown() -> str:
        from starter_pack_guide import _link as guide_link, _url as guide_url, format_venue_time_badge

        blocks: List[str] = ["## 完整论文目录", ""]
        missing = coverage.get("missing_inventory") or []
        if missing:
            blocks.append(
                "> 缺失会议库存："
                + "、".join(
                    _escape(f"{m.get('conference', '')} {m.get('year', '')}") for m in missing
                )
            )
            blocks.append("")

        def _append_group(heading: str, items: List[Dict[str, Any]]) -> None:
            if not items:
                return
            blocks.append(f"### {heading}（{len(items)} 篇）")
            blocks.append("")
            for i, p in enumerate(items, 1):
                route = str(p.get("route") or "").strip()
                link = guide_link(str(p.get("title") or route), guide_url(route, local=True))
                zh = str(p.get("zh_title") or p.get("title_zh") or "").strip()
                venue = format_venue_time_badge(p)
                score_val = p.get("llm_score", p.get("score"))
                ev = str(p.get("canonical_evidence") or p.get("llm_evidence_cn") or "").strip()
                meta_parts = []
                if venue:
                    meta_parts.append(f"`{_escape(venue)}`")
                if score_val is not None:
                    try:
                        meta_parts.append(f"{float(score_val):.1f}分")
                    except (TypeError, ValueError):
                        pass
                head = f"{i}. {link}"
                if meta_parts:
                    head += f"（{' · '.join(meta_parts)}）"
                blocks.append(head)
                if zh:
                    blocks.append(f"   - {_escape(zh)}")
                if ev:
                    blocks.append(f"   - {_escape(ev)}")
            blocks.append("")

        _append_group("精读区", deep_done)
        _append_group("速读区", quick_done)
        if not deep_done and not quick_done:
            blocks.append("当前检索窗口暂无满足入选条件的论文。")
            blocks.append("")
        return "\n".join(blocks).rstrip() + "\n"

    catalog_md = _build_topic_catalog_markdown()
    guide_status = "not_required"
    if mode == "starter":
        if status_reporter is not None:
            status_reporter.report(
                step_code="guide",
                step_label="生成方向导读与清单",
                detail=f"基于 {len(final_papers)} 篇入选论文生成导读",
                force=True,
            )
        try:
            guide = _generate_or_load_guide(
                root, plan, final_papers, guide_client_factory=guide_client_factory
            )
            guide_md = render_guide(
                guide,
                final_papers,
                {
                    "topic": tag,
                    "window": coverage_window_label,
                    "description": description,
                    "refinement": refinement,
                    "deep_count": len(deep_done),
                    "quick_count": len(quick_done),
                },
            )
            readme_text = _inject_action_bar_after_h1(
                guide_md + "\n---\n\n" + catalog_md, actions_md
            )
            guide_status = "complete"
        except Exception as exc:
            log(f"[WARN] 方向导读生成失败，已降级为完整目录总览：{exc}")
            guide_status = "failed"
            fallback_head = [
                f"# {_escape(tag)} · {_escape(mode_label)}",
                "",
                f"- **覆盖范围**：{_escape(coverage_window_label)}",
                f"- **精选论文**：共 {len(final_papers)} 篇（精读 {len(deep_done)} 篇 · 速读 {len(quick_done)} 篇）",
            ]
            if description:
                fallback_head.insert(2, f"- **研究方向**：{_escape(description)}")
            readme_text = _inject_action_bar_after_h1(
                "\n".join(fallback_head) + "\n\n" + catalog_md, actions_md
            )
    else:
        overview_head = [
            f"# {_escape(tag)} · {_escape(mode_label)}",
            "",
            f"- **覆盖范围**：{_escape(coverage_window_label)}",
            f"- **精选论文**：共 {len(final_papers)} 篇（精读 {len(deep_done)} 篇 · 速读 {len(quick_done)} 篇）",
        ]
        if description:
            overview_head.insert(2, f"- **研究方向**：{_escape(description)}")
        if refinement:
            overview_head.append(f"- **本次细化**：{_escape(refinement)}")
        readme_text = _inject_action_bar_after_h1(
            "\n".join(overview_head) + "\n\n" + catalog_md, actions_md
        )

    (topic_dir / "README.md").write_text(readme_text, encoding="utf-8")
    return {
        "topic_token": topic_token,
        "status": "complete",
        "guide_status": guide_status,
        "selected_count": len(final_papers),
        "deep_count": len(deep_done),
        "quick_count": len(quick_done),
        "failed_count": len(failed_papers),
        "report_href": f"#/{topic_token}/README",
        "export_path": export_rel_path,
    }


def run_research(
    config: Dict[str, Any],
    profile_tag: str,
    mode: str,
    as_of: str,
    root: str | Path,
    *,
    profile_snapshot: Dict[str, Any] | None = None,
    conferences: List[str] | None = None,
    max_papers: int = DEFAULT_MAX_PAPERS,
    rerank_pool_limit: int = DEFAULT_RERANK_POOL_LIMIT,
    llm_min_star: int = DEFAULT_LLM_MIN_STAR,
    docs_concurrency: int = DEFAULT_DOCS_CONCURRENCY,
    arxiv_days: int | None = None,
    publish: bool = True,
    retrieve_only: bool = False,
    step_runner: Callable[[str, List[str], Dict[str, str] | None], None] | None = None,
    guide_client_factory: Callable[[], Any] | None = None,
) -> Dict[str, Any]:
    if isinstance(max_papers, bool) or not isinstance(max_papers, int) or not 1 <= max_papers <= MAX_PAPERS_LIMIT:
        raise ValueError(f"最终结果数量上限必须为 1–{MAX_PAPERS_LIMIT} 的整数")
    if isinstance(rerank_pool_limit, bool) or not isinstance(rerank_pool_limit, int) or not 10 <= rerank_pool_limit <= 500:
        raise ValueError("重排候选池上限必须为 10–500 的整数")

    root = Path(root).resolve()
    plan, scoped = research_plan(
        config,
        profile_tag,
        mode,
        as_of,
        profile_snapshot,
        conferences,
        arxiv_days=arxiv_days,
    )
    topic_token = plan["topic_token"]
    archive_dir = root / "archive" / topic_token
    filtered_dir = archive_dir / "filtered"
    rank_dir = archive_dir / "rank"
    recommend_dir = archive_dir / "recommend"
    for d in (filtered_dir, rank_dir, recommend_dir):
        d.mkdir(parents=True, exist_ok=True)

    mode_label = _mode_display_label(mode, int(plan.get("arxiv_days") or 365))
    reporter = WorkflowStatusReporter(
        workflow_key="topic-research",
        workflow_file="topic-research.yml",
        display_label=f"专题研究 · {profile_tag}（{mode_label}）",
    )

    # Step 2a: 多源宽窗召回（含独立检查点）
    log(f"[INFO] 专题研究启动：mode={mode} tag={profile_tag} token={topic_token}")
    reporter.report(
        step_code="step2",
        step_label="Step 2 多源召回与去重",
        detail=f"{profile_tag} · {mode_label}",
        force=True,
    )
    retrieval = run_retrieval(plan, scoped, root)
    checked = verify_publications(retrieval["papers"], root, resolve_pdfs=False)
    merged = deduplicate_papers(
        [p for p in checked if p.get("conference_acceptance_status") != "rejected"]
    )

    # Step 2b: 桥接为标准 Step 2.3 RRF JSON
    rrf_payload, works_by_id, bridge_stats = build_standard_rrf_payload(
        merged["papers"], plan
    )
    rrf_path = filtered_dir / f"topic_papers_{topic_token}.json"
    write_json(rrf_path, rrf_payload)

    coverage = {**retrieval["coverage"], "bridge": bridge_stats}
    manifest: Dict[str, Any] = {
        "research_version": VERSION,
        "run_id": topic_token,
        "topic_token": topic_token,
        "mode": mode,
        "profile": plan["profile"],
        "windows": plan["windows"],
        "conferences": plan["conferences"],
        "retrieved_records": len(retrieval["papers"]),
        "unique_papers": len(merged["papers"]),
        "eligible_papers": len(rrf_payload["papers"]),
        "coverage": coverage,
        "status": "retrieved",
    }
    if retrieve_only:
        return manifest

    if not rrf_payload["papers"]:
        log("[INFO] 召回后无合格候选论文，跳过 Step 3/4 并输出空态结果。")
        deep_dive, quick_skim = [], []
    else:
        runner = step_runner or _default_step_runner
        step_env = os.environ.copy()
        step_env["DPR_RUN_DATE"] = topic_token
        step_env.setdefault("MKL_THREADING_LAYER", "GNU")

        # Step 3: 标准 3.rank_papers.py（逐 query Qwen3 重排）
        reporter.report(
            step_code="step3",
            step_label="Step 3 云端重排",
            detail=f"合格候选 {len(rrf_payload['papers'])} 篇",
            force=True,
        )
        rerank_path = rank_dir / f"topic_papers_{topic_token}.json"
        runner(
            "Topic Step 3 - Standard Rerank",
            [
                sys.executable,
                str(SRC_DIR / "3.rank_papers.py"),
                "--input",
                str(rrf_path),
                "--output",
                str(rerank_path),
                "--rerank-global-pool-limit",
                str(rerank_pool_limit),
                "--top-n",
                str(rerank_pool_limit),
            ],
            step_env,
        )

        # Step 4: 标准 4.llm_refine_papers.py（统一 DeepSeek 评分 + 中英摘要/速览）
        reporter.report(
            step_code="step4",
            step_label="Step 4 DeepSeek 精排",
            force=True,
        )
        scoped_cfg_path = archive_dir / "scoped_config.yaml"
        _write_scoped_llm_config(scoped_cfg_path, config, plan["snapshot"])
        llm_path = rank_dir / f"topic_papers_{topic_token}.llm.json"
        runner(
            "Topic Step 4 - Standard LLM Refine",
            [
                sys.executable,
                str(SRC_DIR / "4.llm_refine_papers.py"),
                "--input",
                str(rerank_path),
                "--output",
                str(llm_path),
                "--config",
                str(scoped_cfg_path),
                "--min-star",
                str(max(int(llm_min_star), 1)),
                "--batch-size",
                "10",
                "--filter-concurrency",
                "4",
            ],
            step_env,
        )

        llm_payload = json.loads(llm_path.read_text(encoding="utf-8"))
        # Step 5: 标准阈值选篇（≥8精读，6–8速读，最多 max_papers 篇）
        reporter.report(
            step_code="step5",
            step_label="Step 5 筛选精读与速读",
            force=True,
        )
        deep_dive, quick_skim = select_topic_papers(
            llm_payload,
            works_by_id,
            profile_tag,
            max_papers=max_papers,
        )

    recommend_path = recommend_dir / f"topic_papers_{topic_token}.standard.json"
    write_json(
        recommend_path,
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "topic_token": topic_token,
            "mode": mode,
            "profile_tag": profile_tag,
            "deep_dive": deep_dive,
            "quick_skim": quick_skim,
        },
    )
    manifest["selected_count"] = len(deep_dive) + len(quick_skim)
    manifest["deep_count"] = len(deep_dive)
    manifest["quick_count"] = len(quick_skim)
    manifest["status"] = "selected"

    # Step 6: 标准并发文档生成 + 图表提取 + 导读 + 单轨侧边栏
    if publish:
        pub_result = publish_topic_results(
            root,
            plan,
            deep_dive,
            quick_skim,
            coverage,
            docs_concurrency=docs_concurrency,
            guide_client_factory=guide_client_factory,
            status_reporter=reporter,
        )
        manifest.update(status=pub_result["status"], result=pub_result)
    return manifest


def main(argv: List[str] | None = None) -> None:
    from local_env import load_local_env

    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--root", type=Path, default=ROOT_DIR)
    parser.add_argument("--profile-tag", required=True)
    parser.add_argument("--mode", choices=sorted(MODES), default="starter")
    parser.add_argument(
        "--as-of", default=datetime.now(timezone.utc).date().isoformat()
    )
    parser.add_argument("--profile-snapshot", default="")
    parser.add_argument("--conferences", default="")
    parser.add_argument("--max-papers", type=int, default=DEFAULT_MAX_PAPERS)
    parser.add_argument(
        "--rerank-pool-limit", type=int, default=DEFAULT_RERANK_POOL_LIMIT
    )
    parser.add_argument("--llm-min-star", type=int, default=DEFAULT_LLM_MIN_STAR)
    parser.add_argument(
        "--docs-concurrency", type=int, default=DEFAULT_DOCS_CONCURRENCY
    )
    parser.add_argument("--arxiv-days", type=int, default=None)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--retrieve-only", action="store_true")
    args = parser.parse_args(argv)
    if len(args.profile_snapshot) > 32768:
        parser.error("需求快照过大")
    config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
    result = run_research(
        config,
        args.profile_tag,
        args.mode,
        args.as_of,
        args.root,
        profile_snapshot=(
            json.loads(args.profile_snapshot) if args.profile_snapshot else None
        ),
        conferences=[c.strip() for c in args.conferences.split(",") if c.strip()]
        or None,
        max_papers=args.max_papers,
        rerank_pool_limit=args.rerank_pool_limit,
        llm_min_star=args.llm_min_star,
        docs_concurrency=args.docs_concurrency,
        arxiv_days=args.arxiv_days,
        publish=args.publish,
        retrieve_only=args.retrieve_only,
    )
    print(
        json.dumps(
            {
                key: result.get(key)
                for key in (
                    "topic_token",
                    "mode",
                    "status",
                    "selected_count",
                    "deep_count",
                    "quick_count",
                )
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
