#!/usr/bin/env python

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import random
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

from llm import DeepSeekClient, resolve_max_output_tokens
from subscription_plan import build_pipeline_inputs

SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
TODAY_STR = str(os.getenv("DPR_RUN_DATE") or "").strip() or datetime.now(timezone.utc).strftime("%Y%m%d")
ARCHIVE_DIR = os.path.join(ROOT_DIR, "archive", TODAY_STR)
RANKED_DIR = os.path.join(ARCHIVE_DIR, "rank")
CONFIG_FILE = os.getenv("DPR_CONFIG_FILE") or os.path.join(ROOT_DIR, "config.yaml")

DEFAULT_FILTER_MODEL = (
    os.getenv("DEEPSEEK_FILTER_MODEL")
    or os.getenv("SUMMARY_MODEL")
    or os.getenv("DEEPSEEK_MODEL")
    or "deepseek-v4-flash"
)
DEFAULT_DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("SUMMARY_BASE_URL") or "https://api.deepseek.com"
DEFAULT_FILTER_CONCURRENCY = 4
MAX_FILTER_RETRIES = 3


class FilterOutputTruncatedError(ValueError):
    """Raised when LLM output is truncated; prefer splitting batches over retrying the same batch."""


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def group_start(title: str) -> None:
    print(f"::group::{title}", flush=True)


def group_end() -> None:
    print("::endgroup::", flush=True)
def load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"missing file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log(f"[INFO] saved: {path}")


def load_config(config_path: str | None = None) -> Dict[str, Any]:
    path = str(config_path or CONFIG_FILE).strip() or CONFIG_FILE
    if not os.path.exists(path):
        return {}
    try:
        import yaml  # type: ignore
    except Exception:
        log("[WARN] PyYAML not installed, skip config.yaml.")
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        log(f"[WARN] failed to read config.yaml: {exc}")
        return {}


def _norm_text(value: Any) -> str:
    return str(value or "").strip()


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    lowered = _norm_text(value).lower()
    if lowered in {"0", "false", "no", "off"}:
        return False
    if lowered in {"1", "true", "yes", "on"}:
        return True
    return default


def _unique_keep_order(items: List[str]) -> List[str]:
    seen: set[str] = set()
    output: List[str] = []
    for item in items:
        text = _norm_text(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def unique_tagged(items: List[Dict[str, str]], tag_key: str = "tag") -> List[Dict[str, str]]:
    seen = set()
    result: List[Dict[str, str]] = []
    for item in items:
        tag = (item.get(tag_key) or "").strip()
        if not tag:
            continue
        payload_key = (
            (item.get("keyword") or item.get("query") or item.get("paper_id") or "").strip()
        )
        dedup_key = f"{tag}|{payload_key}" if payload_key else tag
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        result.append(item)
    return result


def _slug(text: str, fallback: str = "query") -> str:
    raw = str(text or "").strip().lower()
    raw = re.sub(r"[^a-z0-9]+", "-", raw)
    raw = re.sub(r"-+", "-", raw).strip("-")
    return raw or fallback


def _normalize_query_tag(raw_tag: str, query_text: str, idx: int) -> str:
    text = str(raw_tag or "").strip()
    if text.startswith("query:"):
        base = text.split(":", 1)[1].strip()
        return f"query:{_slug(base, fallback=f'q{idx}')}"
    if text:
        return f"query:{_slug(text, fallback=f'q{idx}')}"
    return f"query:{_slug(query_text, fallback=f'q{idx}')}"


def _collect_profile_composite_clauses(profile: Dict[str, Any]) -> List[str]:
    clauses: List[str] = []

    for item in profile.get("keywords") or []:
        if isinstance(item, dict) and not _as_bool(item.get("enabled"), True):
            continue
        if isinstance(item, dict):
            text = _norm_text(
                item.get("query")
                or item.get("keyword")
                or item.get("text")
                or item.get("expr")
                or ""
            )
        else:
            text = _norm_text(item)
        if text:
            clauses.append(text)

    for item in profile.get("intent_queries") or []:
        if isinstance(item, dict) and not _as_bool(item.get("enabled"), True):
            continue
        if isinstance(item, dict):
            text = _norm_text(
                item.get("query")
                or item.get("text")
                or item.get("keyword")
                or item.get("expr")
                or ""
            )
        else:
            text = _norm_text(item)
        if text:
            clauses.append(text)

    return _unique_keep_order(clauses)


def _build_profile_composite_requirement(
    profile: Dict[str, Any],
    index: int,
    seen_queries: set[str],
) -> Dict[str, str] | None:
    if not isinstance(profile, dict) or not _as_bool(profile.get("enabled"), True):
        return None

    clauses = _collect_profile_composite_clauses(profile)
    if len(clauses) < 2:
        return None

    tag = _norm_text(profile.get("tag") or f"profile-{index + 1}")
    description = _norm_text(profile.get("description") or tag)
    focus_label = description or tag
    composite_query = (
        f"Papers central to {focus_label}, especially work that connects or combines: "
        f"{'; '.join(clauses[:10])}."
    )
    lowered = composite_query.lower()
    if lowered in seen_queries:
        return None
    seen_queries.add(lowered)

    composite_tag = f"query:{_slug(tag, fallback=f'profile-{index + 1}')}:" "composite"
    return {
        "id": f"req-composite-{_slug(tag, fallback=f'profile-{index + 1}')}",
        "query": composite_query,
        "tag": composite_tag,
        "kind": "composite",
        "description_en": (
            f"Find papers central to the combined {focus_label} theme. "
            f"Consider these signals together: {'; '.join(clauses[:8])}"
        ),
    }


def build_user_requirements(
    config: Dict[str, Any],
    fallback_queries: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """
    Unified user-requirements list (no keyword vs query distinction):
    - Keep only query_text / semantic-query meaning
    - Generate an English description per requirement for the Step 4 scoring prompt
    """
    requirements: List[Dict[str, str]] = []
    seen = set()

    pipeline_inputs = build_pipeline_inputs(config or {})
    for item in pipeline_inputs.get("context_queries") or []:
        text = (item.get("query") or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        tag = _normalize_query_tag(
            str(item.get("tag") or "").strip(),
            text,
            len(requirements) + 1,
        )
        requirements.append(
            {
                "id": f"req-{len(requirements) + 1}",
                "query": text,
                "tag": tag,
                "kind": "direct",
                "description_en": f"Find papers relevant to this user requirement: {text}",
            }
        )

    profiles = (((config or {}).get("subscriptions") or {}).get("intent_profiles") or [])
    if isinstance(profiles, list):
        for idx, profile in enumerate(profiles):
            composite_req = _build_profile_composite_requirement(profile, idx, seen)
            if composite_req:
                requirements.append(composite_req)

    if not requirements:
        for q in fallback_queries:
            q_type = str(q.get("type") or "").strip().lower()
            if q_type and q_type not in {"llm_query", "intent_query"}:
                continue
            text = (q.get("query_text") or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            tag = _normalize_query_tag(
                str(q.get("paper_tag") or q.get("tag") or "").strip(),
                text,
                len(requirements) + 1,
            )
            requirements.append(
                {
                    "id": f"req-{len(requirements) + 1}",
                    "query": text,
                    "tag": tag,
                    "kind": "fallback",
                    "description_en": f"Find papers relevant to this user requirement: {text}",
                }
            )
    return requirements


def build_paper_map(papers: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    paper_map: Dict[str, Dict[str, Any]] = {}
    for p in papers:
        pid = p.get("id")
        if pid:
            paper_map[str(pid)] = p
    return paper_map


def format_doc(title: str, abstract: str, max_chars: int) -> str:
    content = f"Title: {title}\nAbstract: {abstract}".strip()
    if len(content) > max_chars:
        content = content[:max_chars]
    return content


def chunk_list(items: List[Any], batch_size: int) -> List[List[Any]]:
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


def build_repeated_user_prompt(query: str) -> str:
    base = _norm_text(query)
    if not base:
        return ""
    return f"{base}\n\nLet me repeat that:\n{base}"


def call_filter(
    client: DeepSeekClient,
    all_requirements: List[Dict[str, str]],
    docs: List[Dict[str, str]],
    debug_dir: str,
    debug_tag: str,
    retry_note: str = "",
) -> List[Dict[str, Any]]:
    schema = {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "matched_requirement_index": {"type": "integer"},
                        "evidence_en": {"type": "string"},
                        "tldr_en": {"type": "string"},
                        "motivation_en": {"type": "string"},
                        "method_en": {"type": "string"},
                        "result_en": {"type": "string"},
                        "conclusion_en": {"type": "string"},
                        "score": {"type": "number"},
                    },
                    "required": [
                        "id",
                        "matched_requirement_index",
                        "evidence_en",
                        "tldr_en",
                        "motivation_en",
                        "method_en",
                        "result_en",
                        "conclusion_en",
                        "score",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["results"],
        "additionalProperties": False,
    }

    system_prompt = (
        "You are an intelligent Research Relevance Evaluator. "
        "Score papers (0-10) based purely on relevance to ANY item in user's requirement list. "
        "Prioritize conceptual/method relevance over exact term overlap. "
        "Use the rubric and return JSON only."
    )
    req_lines = []
    for idx, req in enumerate(all_requirements, start=1):
        desc = (req.get("description_en") or req.get("query") or "").strip()
        req_tag = (req.get("tag") or "").strip()
        req_kind = (req.get("kind") or "").strip()
        if desc:
            if req_tag and req_kind:
                req_lines.append(f"{idx}. {desc} [tag={req_tag}; type={req_kind}]")
            elif req_tag:
                req_lines.append(f"{idx}. {desc} [tag={req_tag}]")
            else:
                req_lines.append(f"{idx}. {desc}")
    user_prompt = (
        "User requirements list:\n"
        f"{chr(10).join(req_lines)}\n\n"
        "SCORING RUBRIC:\n"
        "9-10: Direct Requirement Match (same problem target and same evaluation intent)\n"
        "8-9: Strong Method Match (different wording but equivalent objective/technical core)\n"
        "6-8: Methodological Bridge (transferable method/approach likely useful for requirement)\n"
        "3-4: Tangential (same broad discipline, weak link)\n"
        "0-2: Noise (irrelevant)\n\n"
        "GUARDRAILS:\n"
        "1) Beware of Polysemy: If a keyword is ambiguous, only match the sense that aligns with the user's intent.\n"
        "2) Reject Literal Matching: Do NOT score high just because the same word appears.\n"
        "3) Reward Conceptual Equivalence: If wording differs but goals/methods are equivalent, score as high relevance.\n"
        "4) Reward Enabling Methods: If a paper provides a generally applicable method/tool that directly supports requirement tasks, do not under-score it.\n"
        "5) Be strict only when mismatch is substantive (different task objective, incompatible setting, or no reusable method).\n"
        "6) Some requirements may be profile-level composite requirements built from multiple keywords. "
        "Use them when a paper is clearly central to the overall theme but does not fit a narrower requirement cleanly.\n"
        "7) Do not over-score generic LLM-for-science or infrastructure papers under a composite requirement unless they materially advance the core task.\n\n"
        "Papers:\n"
        f"{json.dumps(docs, ensure_ascii=False)}\n\n"
        "Output JSON format example:\n"
        "{\"results\": [{\"id\": \"paper_id\", \"matched_requirement_index\": 1, \"evidence_en\": \"short English phrase\", \"tldr_en\": \"abstract-style English TLDR\", \"motivation_en\": \"English research motivation\", \"method_en\": \"English method summary\", \"result_en\": \"English result summary\", \"conclusion_en\": \"English conclusion\", \"score\": 7}]}\n\n"
        "Requirement: You MUST return exactly one result for every input paper. "
        "The results length must match the papers length, and every input id must appear once.\n\n"
        "Output must be a single-line JSON string. "
        "Do not include line breaks inside any string fields. "
        "Avoid double quotes inside evidence text fields.\n\n"
        "Task: Evaluate papers against the WHOLE requirement list. "
        "If a paper matches any one point, it can get a high score. "
        "Set matched_requirement_index to the best-matched requirement (1-based). "
        "Use semantic interpretation, not only lexical overlap, to decide relevance and score tier. "
        "Provide evidence_en: a short English phrase linking the paper to the matched requirement; "
        "it does NOT need to be a direct quote. "
        "Also generate tldr_en. "
        "tldr_en is not a one-line slogan; write it in the same style as a paper-page TLDR abstract. "
        "For relevant papers with score > 0, tldr_en should target 60-90 words, usually 3-4 short sentences, "
        "covering the problem setting, core method, key result, and why the result matters. "
        "Reference style: first say what limitation/problem the paper addresses; then say what method it proposes; then say what experiments/results show; finally mention the broader contribution. "
        "Also generate four overview fields: motivation_en, method_en, result_en, conclusion_en. "
        "For relevant papers with score > 0, each overview field should target 15-35 words, normally one concrete sentence. "
        "Match the style of a paper page overview: concise but not a bare phrase; include concrete content from the title/abstract. "
        "These length targets are guidance, not a reason to omit a paper; if the title/abstract is sparse, return the best faithful concise summary you can. "
        "method_en should summarize the method from the title and abstract, not copy the abstract verbatim. "
        "Then give a score (0-10). "
        "If unrelated, use evidence_en=\"not relevant\", "
        "tldr_en=\"not relevant\", "
        "motivation_en=\"not relevant\", method_en=\"not relevant\", result_en=\"not relevant\", conclusion_en=\"not relevant\", "
        "score 0, matched_requirement_index=0."
    )
    if retry_note:
        user_prompt += f"\n\nRetry correction note:\n{retry_note}"
    repeated_user_prompt = build_repeated_user_prompt(user_prompt)

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": repeated_user_prompt
            + "\n\nOutput must be strict JSON only, no markdown, no fences, no extra text.",
        },
    ]
    resp = client.chat_structured(
        messages=messages,
        schema_name="rerank_batch",
        schema=schema,
        strict=True,
        allow_json_object_fallback=True,
    )
    content = str(resp.get("content") or "")
    try:
        if resp.get("refusal"):
            raise ValueError(f"structured output refusal: {resp.get('refusal')}")
        if resp.get("finish_reason") not in (None, "stop"):
            msg = f"unexpected finish_reason: {resp.get('finish_reason')}"
            if resp.get("finish_reason") == "length":
                raise FilterOutputTruncatedError(msg)
            raise ValueError(msg)
        if resp.get("parse_error") is not None:
            raise resp["parse_error"]
        payload = resp.get("parsed")
        if not isinstance(payload, dict):
            raise ValueError("parsed payload is not an object")
    except Exception as exc:
        preview = (content or "").strip().replace("\n", " ")
        if len(preview) > 800:
            preview = preview[:800] + "..."
        debug_path = ""
        if debug_dir:
            os.makedirs(debug_dir, exist_ok=True)
            tag = debug_tag or f"batch_{int(time.time())}"
            debug_path = os.path.join(debug_dir, f"filter_raw_{tag}.txt")
            with open(debug_path, "w", encoding="utf-8") as f:
                f.write(content or "")
        msg = f"JSON parse failed: {exc}. raw={preview}"
        if debug_path:
            msg = f"{msg} | saved={debug_path}"
        raise ValueError(msg)
    results = payload.get("results", [])
    if not isinstance(results, list):
        return []
    return results


def _coerce_score(value: Any) -> float:
    try:
        score = float(value)
    except Exception:
        score = 0.0
    return max(0.0, min(10.0, score))


def _coerce_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _normalize_filter_result_item(item: Dict[str, Any]) -> Dict[str, Any]:
    legacy = _norm_text(item.get("evidence"))
    evidence_en = _norm_text(item.get("evidence_en") or legacy)
    score = _coerce_score(item.get("score"))
    tldr_en = _norm_text(item.get("tldr_en")) or ("not relevant" if score <= 0 else evidence_en)
    motivation_en = _norm_text(item.get("motivation_en")) or ("not relevant" if score <= 0 else evidence_en)
    method_en = _norm_text(item.get("method_en")) or ("not relevant" if score <= 0 else "See the abstract and full text for method details.")
    result_en = _norm_text(item.get("result_en")) or ("not relevant" if score <= 0 else tldr_en)
    conclusion_en = _norm_text(item.get("conclusion_en")) or ("not relevant" if score <= 0 else tldr_en)
    return {
        "id": _norm_text(item.get("id")),
        "matched_requirement_index": _coerce_int(item.get("matched_requirement_index"), 0),
        "evidence_en": evidence_en,
        "tldr_en": tldr_en,
        "motivation_en": motivation_en,
        "method_en": method_en,
        "result_en": result_en,
        "conclusion_en": conclusion_en,
        "score": score,
    }


def validate_filter_results(
    batch_docs: List[Dict[str, str]],
    results: Any,
) -> List[Dict[str, Any]]:
    expected_ids = [_norm_text(doc.get("id")) for doc in batch_docs if _norm_text(doc.get("id"))]
    if not expected_ids:
        return []
    if not isinstance(results, list):
        raise ValueError("results must be a list")

    expected_set = set(expected_ids)
    normalized_by_id: Dict[str, Dict[str, Any]] = {}
    problems: List[str] = []

    for idx, item in enumerate(results, start=1):
        if not isinstance(item, dict):
            problems.append(f"item#{idx}: not an object")
            continue
        normalized = _normalize_filter_result_item(item)
        pid = normalized["id"]
        if not pid:
            problems.append(f"item#{idx}: missing id")
            continue
        if pid not in expected_set:
            problems.append(f"item#{idx}: unexpected id={pid}")
            continue
        if pid in normalized_by_id:
            problems.append(f"item#{idx}: duplicate id={pid}")
            continue
        normalized_by_id[pid] = normalized

    missing_ids = [pid for pid in expected_ids if pid not in normalized_by_id]
    if missing_ids:
        problems.append(f"missing ids={','.join(missing_ids)}")

    if problems:
        raise ValueError("; ".join(problems))

    return [normalized_by_id[pid] for pid in expected_ids]


def build_filter_retry_note(
    batch_docs: List[Dict[str, str]],
    attempt: int,
    error: Exception | None,
) -> str:
    expected_ids = [_norm_text(doc.get("id")) for doc in batch_docs if _norm_text(doc.get("id"))]
    previous_error = _norm_text(error) or "unknown validation error"
    return (
        f"Retry attempt {attempt}. The previous output was invalid: {previous_error}. "
        f"You must return exactly {len(expected_ids)} results for these ids only: {', '.join(expected_ids)}. "
        "Every id must appear once. Do not omit ids. Do not repeat ids. "
        "Keep matched_requirement_index as an integer and score within 0-10. "
        "Keep summaries faithful and concise; do not pad unsupported details just to satisfy a length target."
    )


def recover_filter_results(
    batch_docs: List[Dict[str, str]],
    runner: Callable[[List[Dict[str, str]], int, str], List[Dict[str, Any]]],
    max_attempts: int = MAX_FILTER_RETRIES,
    debug_tag: str = "batch",
) -> List[Dict[str, Any]]:
    if not batch_docs:
        return []

    last_error: Exception | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        retry_note = build_filter_retry_note(batch_docs, attempt, last_error) if last_error else ""
        try:
            raw_results = runner(batch_docs, attempt, retry_note)
            return validate_filter_results(batch_docs, raw_results)
        except Exception as exc:
            last_error = exc
            log(f"[WARN] filter {debug_tag} attempt {attempt}/{max_attempts} invalid: {exc}")
            if isinstance(exc, FilterOutputTruncatedError) and len(batch_docs) > 1:
                break

    if len(batch_docs) == 1:
        raise ValueError(f"{debug_tag} failed after {max_attempts} attempts: {last_error}")

    mid = max(1, len(batch_docs) // 2)
    left_docs = batch_docs[:mid]
    right_docs = batch_docs[mid:]
    log(
        f"[WARN] filter {debug_tag} split recovery: "
        f"{len(left_docs)} + {len(right_docs)} docs"
    )
    return recover_filter_results(
        left_docs,
        runner,
        max_attempts=max_attempts,
        debug_tag=f"{debug_tag}_left",
    ) + recover_filter_results(
        right_docs,
        runner,
        max_attempts=max_attempts,
        debug_tag=f"{debug_tag}_right",
    )


def _make_filter_client(api_key: str, model: str, max_output_tokens: int) -> DeepSeekClient:
    client = DeepSeekClient(api_key=api_key, model=model, base_url=DEFAULT_DEEPSEEK_BASE_URL)
    client.kwargs.update({"temperature": 0.1, "max_tokens": max_output_tokens})
    return client


def _make_filter_runner(
    client: DeepSeekClient,
    all_requirements: List[Dict[str, str]],
    debug_dir: str,
    base_tag: str,
) -> Callable[[List[Dict[str, str]], int, str], List[Dict[str, Any]]]:
    def _runner(
        docs: List[Dict[str, str]],
        attempt: int,
        retry_note: str,
    ) -> List[Dict[str, Any]]:
        return call_filter(
            client,
            all_requirements=all_requirements,
            docs=docs,
            debug_dir=debug_dir,
            debug_tag=f"{base_tag}_attempt_{attempt:02d}",
            retry_note=retry_note,
        )

    return _runner


def merge_filter_result(
    merged: Dict[str, Dict[str, Any]],
    item: Dict[str, Any],
    requirement_by_index: Dict[int, Dict[str, str]],
) -> None:
    pid = _norm_text(item.get("id") or item.get("paper_id"))
    if not pid:
        return

    score = _coerce_score(item.get("score"))
    evidence_en = _norm_text(item.get("evidence_en"))
    tldr_en = _norm_text(item.get("tldr_en"))
    motivation_en = _norm_text(item.get("motivation_en"))
    method_en = _norm_text(item.get("method_en"))
    result_en = _norm_text(item.get("result_en"))
    conclusion_en = _norm_text(item.get("conclusion_en"))
    legacy = _norm_text(item.get("evidence"))
    if not evidence_en:
        evidence_en = legacy
    if not tldr_en:
        tldr_en = "not relevant" if score <= 0 else evidence_en
    if not motivation_en:
        motivation_en = "not relevant" if score <= 0 else evidence_en
    if not method_en:
        method_en = "not relevant" if score <= 0 else "See the abstract and full text for method details."
    if not result_en:
        result_en = "not relevant" if score <= 0 else tldr_en
    if not conclusion_en:
        conclusion_en = "not relevant" if score <= 0 else tldr_en

    matched_idx = _coerce_int(item.get("matched_requirement_index"), 0)
    matched_req = requirement_by_index.get(matched_idx) if matched_idx > 0 else None
    matched_tag = _norm_text((matched_req or {}).get("tag"))
    matched_id = _norm_text((matched_req or {}).get("id"))
    matched_query = _norm_text((matched_req or {}).get("query"))

    prev = merged.get(pid)
    if (prev is None) or (score > float(prev.get("score", 0))):
        merged[pid] = {
            "paper_id": pid,
            "score": score,
            "evidence_en": evidence_en,
            "canonical_evidence": evidence_en or legacy,
            "tldr_en": tldr_en,
            "motivation_en": motivation_en,
            "method_en": method_en,
            "result_en": result_en,
            "conclusion_en": conclusion_en,
            "matched_requirement_id": matched_id,
            "matched_query_tag": matched_tag,
            "matched_query_text": matched_query,
        }


def _filter_batch(
    batch_idx: int,
    batch: List[Dict[str, str]],
    api_key: str,
    all_requirements: List[Dict[str, str]],
    filter_model: str,
    max_output_tokens: int,
    debug_dir: str,
) -> tuple[int, List[Dict[str, str]], List[Dict[str, Any]]]:
    client = _make_filter_client(api_key, filter_model, max_output_tokens)
    runner = _make_filter_runner(
        client,
        all_requirements=all_requirements,
        debug_dir=debug_dir,
        base_tag=f"batch_{batch_idx:03d}",
    )
    return (
        batch_idx,
        batch,
        recover_filter_results(
            batch,
            runner,
            max_attempts=MAX_FILTER_RETRIES,
            debug_tag=f"batch_{batch_idx:03d}",
        ),
    )


def process_file(
    input_path: str,
    output_path: str,
    config_path: str | None,
    min_star: int,
    batch_size: int,
    max_chars: int,
    filter_model: str,
    max_output_tokens: int,
    filter_concurrency: int,
) -> None:
    # If the input file is missing, there are no new papers today; exit gracefully
    if not os.path.exists(input_path):
        log(f"[INFO] Input file not found: {input_path} (no new papers today; skipping LLM refine)")
        return

    data = load_json(input_path)
    papers = data.get("papers") or []
    queries = data.get("queries") or []
    if not papers or not queries:
        log("[WARN] missing papers or queries; skipping.")
        return

    config = load_config(config_path)
    user_requirements = build_user_requirements(config, queries)
    if not user_requirements:
        log("[WARN] no user requirements built from config/queries; skipping.")
        save_json(data, output_path)
        return
    paper_map = build_paper_map(papers)

    api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("SUMMARY_API_KEY")
    if not api_key:
        raise RuntimeError("missing DEEPSEEK_API_KEY or SUMMARY_API_KEY")

    group_start(f"Step 4 - llm refine {os.path.basename(input_path)}")
    log(
        f"[INFO] Starting filter: queries={len(queries)}, papers={len(papers)}, "
        f"min_star={min_star}, batch_size={batch_size}, max_chars={max_chars}, "
        f"concurrency={filter_concurrency}"
    )

    candidate_ids: List[str] = []
    for q in queries:
        ranked = q.get("ranked") or []
        for item in ranked:
            if item.get("star_rating", 0) >= min_star:
                pid = str(item.get("paper_id"))
                if pid:
                    candidate_ids.append(pid)

    tagged_candidates = unique_tagged([{"tag": pid} for pid in candidate_ids])
    candidate_ids = [item["tag"] for item in tagged_candidates]
    if not candidate_ids:
        log("[WARN] no candidates found with star_rating >= min_star.")
        save_json(data, output_path)
        group_end()
        return

    docs: List[Dict[str, str]] = []
    for pid in candidate_ids:
        paper = paper_map.get(pid)
        if not paper:
            continue
        title = (paper.get("title") or "").strip()
        abstract = (paper.get("abstract") or "").strip()
        content = format_doc(title, abstract, max_chars)
        docs.append({"id": pid, "content": content})

    if not docs:
        log("[WARN] candidate papers not found in paper map.")
        save_json(data, output_path)
        group_end()
        return

    random.shuffle(docs)
    batches = chunk_list(docs, batch_size)
    log(
        f"[INFO] global candidates={len(docs)} batches={len(batches)} "
        f"| user_requirements={len(user_requirements)}"
    )

    merged: Dict[str, Dict[str, Any]] = {}
    debug_dir = os.path.join(RANKED_DIR, "debug")
    requirement_by_index = {i + 1: r for i, r in enumerate(user_requirements)}
    pending = {}
    max_workers = max(1, filter_concurrency)
    total_batches = len(batches)
    failed_docs: List[Dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for idx, batch in enumerate(batches, start=1):
            log(f"[INFO] Filtering batch {idx}/{total_batches} dispatch docs={len(batch)}")
            pending[executor.submit(
                _filter_batch,
                idx,
                batch,
                api_key,
                user_requirements,
                filter_model,
                max_output_tokens,
                debug_dir,
            )] = (idx, batch)
        for future in as_completed(pending):
            idx, batch = pending[future]
            try:
                _, batch_docs, results = future.result()
            except Exception as exc:
                log(f"[WARN] filter batch {idx}/{total_batches} failed: {exc}")
                failed_docs.extend(batch)
                continue
            log(f"[INFO] filter batch {idx}/{total_batches} docs={len(batch_docs)} completed")
            for item in results:
                merge_filter_result(merged, item, requirement_by_index)

    missing_docs = [doc for doc in docs if _norm_text(doc.get("id")) not in merged]
    if failed_docs or missing_docs:
        recovery_map = {
            _norm_text(doc.get("id")): doc
            for doc in (failed_docs + missing_docs)
            if _norm_text(doc.get("id"))
        }
        recovery_docs = list(recovery_map.values())
        recovery_client = _make_filter_client(api_key, filter_model, max_output_tokens)
        log(
            f"[WARN] start missing-doc recovery: failed_batches_docs={len(failed_docs)} "
            f"| missing_after_merge={len(missing_docs)} | recover_docs={len(recovery_docs)}"
        )
        for index, doc in enumerate(recovery_docs, start=1):
            doc_id = _norm_text(doc.get("id")) or f"missing-{index}"
            runner = _make_filter_runner(
                recovery_client,
                all_requirements=user_requirements,
                debug_dir=debug_dir,
                base_tag=f"recover_{_slug(doc_id, fallback=f'doc-{index}')}",
            )
            try:
                recovered_results = recover_filter_results(
                    [doc],
                    runner,
                    max_attempts=MAX_FILTER_RETRIES,
                    debug_tag=f"recover_{doc_id}",
                )
            except Exception as exc:
                log(f"[WARN] single-doc recovery failed for {doc_id}: {exc}")
                continue
            for item in recovered_results:
                merge_filter_result(merged, item, requirement_by_index)

    if not merged:
        log("[WARN] no llm results returned.")
        save_json(data, output_path)
        group_end()
        return

    llm_ranked = sorted(merged.values(), key=lambda x: x.get("score", 0), reverse=True)
    data["llm_ranked"] = llm_ranked

    data["llm_ranked_at"] = datetime.now(timezone.utc).isoformat()
    save_json(data, output_path)
    group_end()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 4: filter papers with 4o-mini for recommendations.",
    )
    parser.add_argument(
        "--input",
        type=str,
        default=os.path.join(RANKED_DIR, f"arxiv_papers_{TODAY_STR}.json"),
        help="ranked JSON input path.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=os.path.join(RANKED_DIR, f"arxiv_papers_{TODAY_STR}.llm.json"),
        help="output JSON path.",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=CONFIG_FILE,
        help="config YAML path for user requirements.",
    )
    parser.add_argument(
        "--min-star",
        type=int,
        default=4,
        help="min star_rating to keep from rerank.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=10,
        help="batch size for 4o-mini.",
    )
    parser.add_argument(
        "--max-chars",
        type=int,
        default=850,
        help="max chars per doc (title+abstract).",
    )
    parser.add_argument(
        "--filter-model",
        type=str,
        default=DEFAULT_FILTER_MODEL,
        help="model for filter (gemini-3-flash-preview-nothinking).",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=resolve_max_output_tokens(),
        help="max tokens for model output.",
    )
    parser.add_argument(
        "--filter-concurrency",
        type=int,
        default=DEFAULT_FILTER_CONCURRENCY,
        help="concurrent LLM filter requests.",
    )

    args = parser.parse_args()

    input_path = args.input
    if not os.path.isabs(input_path):
        input_path = os.path.abspath(os.path.join(ROOT_DIR, input_path))

    output_path = args.output
    if not os.path.isabs(output_path):
        output_path = os.path.abspath(os.path.join(ROOT_DIR, output_path))

    config_path = args.config
    if not os.path.isabs(config_path):
        config_path = os.path.abspath(os.path.join(ROOT_DIR, config_path))

    process_file(
        input_path=input_path,
        output_path=output_path,
        config_path=config_path,
        min_star=args.min_star,
        batch_size=args.batch_size,
        max_chars=args.max_chars,
        filter_model=args.filter_model,
        max_output_tokens=args.max_output_tokens,
        filter_concurrency=args.filter_concurrency,
    )


if __name__ == "__main__":
    main()
