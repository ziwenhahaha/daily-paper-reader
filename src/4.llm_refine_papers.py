#!/usr/bin/env python

import argparse
import json
import os
import random
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from llm import BltClient
from subscription_plan import build_pipeline_inputs

SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
TODAY_STR = str(os.getenv("DPR_RUN_DATE") or "").strip() or datetime.now(timezone.utc).strftime("%Y%m%d")
ARCHIVE_DIR = os.path.join(ROOT_DIR, "archive", TODAY_STR)
RANKED_DIR = os.path.join(ARCHIVE_DIR, "rank")
CONFIG_FILE = os.path.join(ROOT_DIR, "config.yaml")

DEFAULT_FILTER_MODEL = os.getenv("BLT_FILTER_MODEL") or "gemini-3-flash-preview-nothinking"


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


def load_config() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        import yaml  # type: ignore
    except Exception:
        log("[WARN] PyYAML not installed, skip config.yaml.")
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    except Exception as exc:
        log(f"[WARN] failed to read config.yaml: {exc}")
        return {}


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


def build_context_lists(
    config: Dict[str, Any],
    fallback_queries: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    keywords: List[Dict[str, str]] = []
    queries: List[Dict[str, str]] = []

    # 优先读取新结构（intent_profiles）统一编译后的上下文
    pipeline_inputs = build_pipeline_inputs(config or {})
    for item in pipeline_inputs.get("context_keywords") or []:
        tag = (item.get("tag") or "").strip()
        keyword = (item.get("keyword") or "").strip()
        logic_cn = (item.get("logic_cn") or "").strip()
        if tag and keyword:
            keywords.append({"tag": tag, "keyword": keyword, "logic_cn": logic_cn})
    for item in pipeline_inputs.get("context_queries") or []:
        tag = (item.get("tag") or "").strip()
        query_text = (item.get("query") or "").strip()
        logic_cn = (item.get("logic_cn") or "").strip()
        if tag and query_text:
            queries.append({"tag": tag, "query": query_text, "logic_cn": logic_cn})

    if not keywords:
        for q in fallback_queries:
            if (q.get("type") or "") != "keyword":
                continue
            text = (q.get("query_text") or "").strip()
            if text:
                tag_label = (q.get("tag") or text).strip()
                keywords.append({"tag": f"keyword:{tag_label}", "keyword": text})

    if not queries:
        for q in fallback_queries:
            if (q.get("type") or "") != "llm_query":
                continue
            text = (q.get("query_text") or "").strip()
            if text:
                tag_label = (q.get("tag") or text).strip()
                queries.append({"tag": f"query:{tag_label}", "query": text})

    return unique_tagged(keywords), unique_tagged(queries)


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


def call_filter(
    client: BltClient,
    keywords: List[Dict[str, str]],
    queries: List[Dict[str, str]],
    docs: List[Dict[str, str]],
    debug_dir: str,
    debug_tag: str,
) -> List[Dict[str, Any]]:
    def load_json_lenient(text: str) -> Dict[str, Any]:
        """
        宽松解析模型返回的 JSON。
        兼容常见问题：
        - JSON 后面夹带了额外文本（json.loads 报 Extra data）
        - 前后包含多余空白或换行
        """
        raw = (text or "").strip()
        if not raw:
            return {}

        decoder = json.JSONDecoder()
        try:
            obj, _idx = decoder.raw_decode(raw)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                clipped = raw[start : end + 1]
                obj = json.loads(clipped)
                return obj if isinstance(obj, dict) else {}
            raise

    schema = {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "evidence_en": {"type": "string"},
                        "evidence_cn": {"type": "string"},
                        "tldr_en": {"type": "string"},
                        "tldr_cn": {"type": "string"},
                        "score": {"type": "number"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": [
                        "id",
                        "evidence_en",
                        "evidence_cn",
                        "tldr_en",
                        "tldr_cn",
                        "score",
                        "tags",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["results"],
        "additionalProperties": False,
    }

    use_json_object = "gemini" in (client.model or "").lower()
    if use_json_object:
        response_format = {"type": "json_object"}
    else:
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "rerank_batch",
                "schema": schema,
                "strict": True,
            },
        }

    system_prompt = (
        "You are an intelligent Research Relevance Evaluator. "
        "Score papers (0-10) based purely on relevance to the user's profile and queries. "
        "Use the rubric and return JSON only."
    )
    user_prompt = (
        "Context (packaged):\n"
        f"KeywordsWithTags: {json.dumps(keywords, ensure_ascii=False)}\n"
        f"QueriesWithTags: {json.dumps(queries, ensure_ascii=False)}\n\n"
        "USER PROFILE (for reference):\n"
        f"Long_Term_Interests = {json.dumps(keywords, ensure_ascii=False)}\n"
        f"Current_Search_Queries = {json.dumps(queries, ensure_ascii=False)}\n\n"
        "SCORING RUBRIC:\n"
        "9-10: Perfect Match (directly answers a query and aligns with interests)\n"
        "7-8: Domain Hit (strongly aligns with interests, slightly broader than query)\n"
        "5-6: Methodological Bridge (transferable method/approach)\n"
        "3-4: Tangential (same broad discipline, weak link)\n"
        "0-2: Noise (irrelevant)\n\n"
        "GUARDRAILS:\n"
        "1) Beware of Polysemy: If a keyword is ambiguous, only match the sense that aligns with the user's intent.\n"
        "2) Reject Literal Matching: Do NOT assign a tag just because the word appears; require conceptual relevance.\n\n"
        "Papers:\n"
        f"{json.dumps(docs, ensure_ascii=False)}\n\n"
        "Output JSON format example:\n"
        "{\"results\": [{\"id\": \"paper_id\", \"evidence_en\": \"short English phrase\", \"evidence_cn\": \"简短中文短语\", \"tldr_en\": \"one-sentence TLDR\", \"tldr_cn\": \"一句话 TLDR\", \"score\": 7, \"tags\": [\"tag1\", \"tag2\"]}]}\n\n"
        "Requirement: You MUST return exactly one result for every input paper. "
        "The results length must match the papers length, and every input id must appear once.\n\n"
        "Output must be a single-line JSON string. "
        "Do not include line breaks inside any string fields. "
        "Avoid double quotes inside evidence text fields.\n\n"
        "Task: Identify papers worth recommending, using divergent thinking. "
        "Evidence must be provided in both languages: "
        "evidence_en (English) and evidence_cn (Chinese). "
        "They should be short phrases linking the paper to the queries or interests; "
        "they do NOT need to be direct quotes. "
        "Also generate TLDR in both languages: tldr_en and tldr_cn. "
        "TLDR should be one sentence summarizing what the paper does and why it matters. "
        "Keep TLDR concise: <= 120 characters in English and <= 60 Chinese characters. "
        "Then give a score (0-10). "
        "Tags must be selected from the provided tags (use tag values only). "
        "Tag values already include prefixes like \"keyword:\" or \"query:\", keep them as-is. "
        "If unrelated, use evidence_en=\"not relevant\", evidence_cn=\"不相关\", "
        "tldr_en=\"not relevant\", tldr_cn=\"不相关\", score 0, and tags=[]."
    )

    resp = client.chat(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format=response_format,
    )
    content = resp.get("content", "")
    try:
        payload = load_json_lenient(content)
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


def process_file(
    input_path: str,
    output_path: str,
    min_star: int,
    batch_size: int,
    max_chars: int,
    filter_model: str,
    max_output_tokens: int,
) -> None:
    # 检查输入文件是否存在，如果不存在说明今天没有新论文，优雅退出
    if not os.path.exists(input_path):
        log(f"[INFO] 输入文件不存在：{input_path}（今天没有新论文，将跳过 LLM refine）")
        return

    data = load_json(input_path)
    papers = data.get("papers") or []
    queries = data.get("queries") or []
    if not papers or not queries:
        log("[WARN] missing papers or queries, skip.")
        return

    config = load_config()
    keywords, query_items = build_context_lists(config, queries)
    paper_map = build_paper_map(papers)

    api_key = os.getenv("BLT_API_KEY")
    if not api_key:
        raise RuntimeError("missing BLT_API_KEY")

    filter_client = BltClient(api_key=api_key, model=filter_model)
    filter_client.kwargs.update({"temperature": 0.1, "max_tokens": max_output_tokens})

    group_start(f"Step 4 - llm refine {os.path.basename(input_path)}")
    log(
        f"[INFO] start filter: queries={len(queries)}, papers={len(papers)}, "
        f"min_star={min_star}, batch_size={batch_size}, max_chars={max_chars}"
    )

    candidate_ids: List[str] = []
    for q in queries:
        ranked = q.get("ranked") or []
        for item in ranked:
            if item.get("star_rating", 0) >= min_star:
                pid = str(item.get("paper_id"))
                if pid:
                    candidate_ids.append(pid)

    candidate_ids = unique_tagged([{"tag": pid} for pid in candidate_ids])
    candidate_ids = [item["tag"] for item in candidate_ids]
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
        f"| keywords={len(keywords)} queries={len(query_items)}"
    )

    merged: Dict[str, Dict[str, Any]] = {}
    debug_dir = os.path.join(RANKED_DIR, "debug")
    for idx, batch in enumerate(batches, start=1):
        log(f"[INFO] filter batch {idx}/{len(batches)} docs={len(batch)}")
        try:
            results = call_filter(
                filter_client,
                keywords,
                query_items,
                batch,
                debug_dir=debug_dir,
                debug_tag=f"batch_{idx:03d}",
            )
        except Exception as exc:
            log(f"[WARN] filter batch failed: {exc}")
            continue

        batch_ids = {str(d.get("id")) for d in batch}
        for item in results:
            pid = str(item.get("id", "")).strip()
            if pid not in batch_ids:
                continue
            try:
                score = float(item.get("score", 0))
            except Exception:
                score = 0.0
            # 新字段：中英双语 evidence（兼容旧字段 evidence）
            evidence_en = str(item.get("evidence_en") or "").strip()
            evidence_cn = str(item.get("evidence_cn") or "").strip()
            tldr_en = str(item.get("tldr_en") or "").strip()
            tldr_cn = str(item.get("tldr_cn") or "").strip()
            legacy = str(item.get("evidence", "")).strip()
            if not evidence_en:
                evidence_en = legacy
            if not evidence_cn:
                # 若模型未返回中文 evidence，则回退为英文（下游可再做翻译/展示策略）
                evidence_cn = legacy or evidence_en
            if not tldr_en:
                tldr_en = "not relevant" if score <= 0 else evidence_en
            if not tldr_cn:
                tldr_cn = "不相关" if score <= 0 else (evidence_cn or tldr_en)
            tags = item.get("tags")
            if not isinstance(tags, list):
                tags = []
            tags = [str(t).strip() for t in tags if str(t).strip()]
            prev = merged.get(pid)
            if (prev is None) or (score > float(prev.get("score", 0))):
                merged[pid] = {
                    "paper_id": pid,
                    "score": score,
                    "evidence_en": evidence_en,
                    "evidence_cn": evidence_cn,
                    "tldr_en": tldr_en,
                    "tldr_cn": tldr_cn,
                    "tags": tags,
                }

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
        default=4096,
        help="max tokens for model output (clamped to 4096 in llm.py).",
    )

    args = parser.parse_args()

    input_path = args.input
    if not os.path.isabs(input_path):
        input_path = os.path.abspath(os.path.join(ROOT_DIR, input_path))

    output_path = args.output
    if not os.path.isabs(output_path):
        output_path = os.path.abspath(os.path.join(ROOT_DIR, output_path))

    process_file(
        input_path=input_path,
        output_path=output_path,
        min_star=args.min_star,
        batch_size=args.batch_size,
        max_chars=args.max_chars,
        filter_model=args.filter_model,
        max_output_tokens=args.max_output_tokens,
    )


if __name__ == "__main__":
    main()
