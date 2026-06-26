#!/usr/bin/env python
# Step 6: generate docs (deep dive + quick skim) from recommendations and update the sidebar.

import argparse
import html
import json
import math
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import tempfile
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote_plus
from datetime import datetime, timezone
from typing import Any, Dict, List, Set, Tuple

import fitz  # PyMuPDF
import requests
from llm import DeepSeekClient

SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    from paper_figures import ensure_paper_media
except Exception:  # pragma: no cover
    from src.paper_figures import ensure_paper_media

try:
    from legacy_paper_markers import (
        LEGACY_DEEP_READ_ZONE,
        LEGACY_HOME,
        LEGACY_QUICK_SKIM_ZONE,
        LEGACY_QUOTA_EXHAUSTED,
    )
except Exception:  # pragma: no cover
    from src.legacy_paper_markers import (
        LEGACY_DEEP_READ_ZONE,
        LEGACY_HOME,
        LEGACY_QUICK_SKIM_ZONE,
        LEGACY_QUOTA_EXHAUSTED,
    )

CONFIG_FILE = os.path.join(ROOT_DIR, "config.yaml")
TODAY_STR = str(os.getenv("DPR_RUN_DATE") or "").strip() or datetime.now(timezone.utc).strftime("%Y%m%d")
RANGE_DATE_RE = re.compile(r"^(\d{8})-(\d{8})$")

# LLM config (DeepSeek client from llm.py)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY") or os.getenv("SUMMARY_API_KEY")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL") or os.getenv("SUMMARY_BASE_URL") or "https://api.deepseek.com"
DEEPSEEK_MODEL = os.getenv("SUMMARY_MODEL") or os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-flash"
STEP6_STRUCTURED_MAX_TOKENS = 16 * 1024


def create_llm_client() -> DeepSeekClient | None:
    if not DEEPSEEK_API_KEY:
        return None
    return DeepSeekClient(
        api_key=DEEPSEEK_API_KEY,
        model=DEEPSEEK_MODEL,
        base_url=DEEPSEEK_BASE_URL,
    )


LLM_CLIENT = create_llm_client()

DEFAULT_DOCS_CONCURRENCY = 4


def call_llm_text(
    client: DeepSeekClient,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
    response_format: Dict[str, Any] | None = None,
) -> str:
    client.kwargs.update(
        {
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
        }
    )
    resp = client.chat(messages=messages, response_format=response_format)
    return (resp.get("content") or "").strip()


def call_llm_structured_json(
    client: DeepSeekClient,
    messages: List[Dict[str, str]],
    schema_name: str,
    schema: Dict[str, Any],
    temperature: float,
    max_tokens: int,
) -> Dict[str, Any] | None:
    client.kwargs.update(
        {
            "temperature": float(temperature),
            "max_tokens": int(max_tokens),
        }
    )
    resp = client.chat_structured(
        messages=messages,
        schema_name=schema_name,
        schema=schema,
        strict=True,
        allow_json_object_fallback=True,
    )
    if resp.get("refusal"):
        log(f"[WARN] Structured output refusal: {resp.get('refusal')}")
        return None
    if resp.get("finish_reason") not in (None, "stop"):
        log(f"[WARN] Structured output incomplete: finish_reason={resp.get('finish_reason')}")
        return None
    if resp.get("parse_error") is not None:
        raise ValueError(f"Model did not return valid JSON: {resp.get('content')}")

    parsed = resp.get("parsed")
    if not isinstance(parsed, dict):
        return None
    return parsed


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)

def log_substep(code: str, name: str, phase: str) -> None:
    """
    Sub-step markers for frontend parsing.
    Format: [SUBSTEP] 6.1 - xxx START/END
    """
    phase = str(phase or "").strip().upper()
    if phase not in ("START", "END"):
        phase = "INFO"
    log(f"[SUBSTEP] {code} - {name} {phase}")


def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        import yaml  # type: ignore
    except Exception:
        log("[WARN] PyYAML not installed; cannot parse config.yaml.")
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            return data if isinstance(data, dict) else {}
    except Exception as e:
        log(f"[WARN] Failed to read config.yaml: {e}")
        return {}


def resolve_docs_dir() -> str:
    docs_dir = os.getenv("DOCS_DIR")
    config = load_config()
    paper_setting = (config or {}).get("arxiv_paper_setting") or {}
    crawler_setting = (config or {}).get("crawler") or {}
    cfg_docs = paper_setting.get("docs_dir") or crawler_setting.get("docs_dir")
    if not docs_dir and cfg_docs:
        if os.path.isabs(cfg_docs):
            docs_dir = cfg_docs
        else:
            docs_dir = os.path.join(ROOT_DIR, cfg_docs)
    if not docs_dir:
        docs_dir = os.path.join(ROOT_DIR, "docs")
    return docs_dir


def slugify(title: str) -> str:
    s = (title or "").strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9\-]+", "", s)
    return s or "paper"


def extract_pdf_text(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    texts = []
    try:
        for page in doc:
            texts.append(page.get_text("text"))
    finally:
        doc.close()
    return "\n\n".join(texts)


def fetch_paper_markdown_via_jina(pdf_url: str, max_retries: int = 3) -> str | None:
    if not pdf_url:
        return None
    base = "https://r.jina.ai/"
    full_url = base + pdf_url
    for attempt in range(1, max_retries + 1):
        try:
            log(f"[JINA] Request attempt {attempt}: {full_url}")
            resp = requests.get(full_url, timeout=60)
            if resp.status_code != 200:
                log(f"[JINA][WARN] status {resp.status_code}, first 100 chars: {(resp.text or '')[:100]}")
            else:
                text = (resp.text or "").strip()
                if text:
                    log("[JINA] Received structured Markdown text; using it directly as .txt content.")
                    return text
        except Exception as e:
            log(f"[JINA][WARN] Request failed (attempt {attempt}): {e}")
        time.sleep(2 * attempt)
    log("[JINA][ERROR] All retries failed; falling back to PyMuPDF extraction.")
    return None


def normalize_arxiv_id(value: str) -> str:
    """
    Normalize arXiv input that may be a URL into an id.
    Supports:
    - 1706.03762
    - 1706.03762v1
    - https://arxiv.org/abs/1706.03762v1
    """
    raw = (value or "").strip()
    if not raw:
        return ""
    if raw.startswith("http://") or raw.startswith("https://"):
        raw = raw.rsplit("/", 1)[-1]
    raw = raw.split("?")[0]
    if raw.startswith("abs/"):
        raw = raw[len("abs/") :]
    if raw.startswith("pdf/"):
        raw = raw[len("pdf/") :].replace(".pdf", "")
    return raw.strip().lower()


def parse_arxiv_xml_feed(xml_text: str) -> Dict[str, Any]:
    """
    Parse the first paper entry from an arXiv API XML feed into the internal dict.
    """
    root = ET.fromstring(xml_text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    if entry is None:
        raise RuntimeError("No paper entry parsed from arXiv response")

    def _text(tag: str) -> str:
        elem = entry.find(tag, ns)
        return (elem.text or "").strip() if elem is not None else ""

    arxiv_id = _text("atom:id")
    if arxiv_id:
        arxiv_id = arxiv_id.rsplit("/", 1)[-1]

    title = " ".join(_text("atom:title").split())
    abstract = " ".join(_text("atom:summary").split())
    published = _text("atom:published")
    published_date = ""
    if published:
        published_date = published.split("T", 1)[0].replace("-", "")

    authors = []
    for a in entry.findall("atom:author", ns):
        name_elem = a.find("atom:name", ns)
        if name_elem is not None:
            name = (name_elem.text or "").strip()
            if name and name not in authors:
                authors.append(name)

    pdf_url = ""
    for link in entry.findall("atom:link", ns):
        href = (link.attrib.get("href") or "").strip()
        if href.endswith(".pdf"):
            pdf_url = href
            break
        if link.attrib.get("title") == "pdf" and href:
            pdf_url = href
            break

    return {
        "id": arxiv_id,
        "title": title,
        "abstract": abstract,
        "published": published_date,
        "authors": authors,
        "link": pdf_url,
        "pdf_url": pdf_url,
        "llm_tags": ["query:transformer", "query:attention"],
    }


def fetch_arxiv_paper_meta(arxiv_id: str) -> Dict[str, Any]:
    """
    Fetch single-paper metadata from the arXiv API for one-off generation.
    """
    pid = normalize_arxiv_id(arxiv_id)
    if not pid:
        raise ValueError("paper id must not be empty")
    url = f"https://export.arxiv.org/api/query?id_list={quote_plus(pid)}"
    log(f"[INFO] Fetching arXiv metadata: {url}")
    resp = requests.get(url, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"arXiv API request failed, status={resp.status_code}")
    return parse_arxiv_xml_feed(resp.text)


def extract_section_tail(md_text: str, heading: str) -> str:
    """
    Extract trailing content after an auto-generated heading in md.
    Returns text without the heading (stripped).
    """
    if not md_text:
        return ""
    key = f"## {heading}"
    idx = md_text.rfind(key)
    if idx == -1:
        return ""
    return md_text[idx + len(key) :].strip()


def strip_auto_sections(md_text: str) -> str:
    """
    Keep only the first half of paper Markdown metadata sent to the LLM, avoiding re-feeding old auto summaries/glance blocks.
    """
    if not md_text:
        return ""
    markers = [
        "\n\n---\n\n## Detailed Summary (auto-generated)",
        "\n\n---\n\n## At a Glance (auto-generated)",
    ]
    cut_points = [md_text.find(m) for m in markers if md_text.find(m) != -1]
    if not cut_points:
        return md_text
    cut = min(cut_points)
    return md_text[:cut].rstrip()


def normalize_meta_tldr_line(md_text: str) -> Tuple[str, bool]:
    """
    Legacy fix: meta TLDR lines were written as '**TLDR**: xxx \\'.
    Strip trailing backslashes from meta-area TLDR lines only.
    Note: the `## At a Glance` block uses `\\` for forced line breaks; do not touch those.
    """
    if not md_text:
        return md_text, False
    changed = False
    lines = md_text.splitlines()
    out: List[str] = []
    for line in lines:
        # Meta-area TLDR only (English colon `:` format)
        if line.startswith("**TLDR**:"):
            new_line = line.rstrip()
            if new_line.endswith("\\"):
                new_line = new_line[:-1].rstrip()
            if new_line != line:
                changed = True
            out.append(new_line)
        else:
            out.append(line)
    return "\n".join(out), changed


def normalize_glance_block_format(md_text: str) -> Tuple[str, bool]:
    """
    Normalize line-break markers in the `## At a Glance` block:
    - TLDR/Motivation/Method/Result lines should end with ` \\` (forced break)
    - Conclusion lines should not end with `\\`
    """
    if not md_text:
        return md_text, False

    lines = md_text.splitlines()
    out: List[str] = []
    changed = False
    in_glance = False

    def ensure_line_break(s: str) -> str:
        ss = s.rstrip()
        if ss.endswith("\\"):
            return ss
        return ss + " \\"

    def remove_line_break(s: str) -> str:
        ss = s.rstrip()
        if ss.endswith("\\"):
            return ss[:-1].rstrip()
        return ss

    for line in lines:
        stripped = line.strip()
        if stripped == "## At a Glance":
            in_glance = True
            out.append(line)
            continue

        if in_glance:
            # End glance block at separator or next level-2 heading
            if stripped == "---" or stripped.startswith("## "):
                in_glance = False
                out.append(line)
                continue

            if stripped.startswith("**TLDR**：") or stripped.startswith("**TLDR**:"):
                new_line = ensure_line_break(line)
            elif stripped.startswith("**Motivation**：") or stripped.startswith("**Motivation**:"):
                new_line = ensure_line_break(line)
            elif stripped.startswith("**Method**：") or stripped.startswith("**Method**:"):
                new_line = ensure_line_break(line)
            elif stripped.startswith("**Result**：") or stripped.startswith("**Result**:"):
                new_line = ensure_line_break(line)
            elif stripped.startswith("**Conclusion**：") or stripped.startswith("**Conclusion**:"):
                new_line = remove_line_break(line)
            else:
                new_line = line

            if new_line != line:
                changed = True
            out.append(new_line)
            continue

        out.append(line)

    return "\n".join(out), changed


def ensure_single_sentence_end(text: str) -> str:
    """
    Ensure TLDR/short sentences end with punctuation (avoid duplicate '..').
    """
    s = (text or "").strip()
    if not s:
        return s
    s = s.rstrip("。.!?！？")
    return s + "."


def upsert_auto_block(md_path: str, heading: str, content: str) -> None:
    """
    Write auto-generated content into md:
    - If the heading exists, replace from that block to EOF
    - Otherwise append at EOF
    """
    key = f"## {heading}"
    block = f"\n\n---\n\n{key}\n\n{content}".rstrip() + "\n"

    with open(md_path, "r", encoding="utf-8") as f:
        txt = f.read()

    idx = txt.rfind(key)
    if idx == -1:
        new_txt = txt.rstrip() + block
    else:
        start = txt.rfind("\n\n---\n\n", 0, idx)
        if start == -1:
            start = idx
        new_txt = txt[:start].rstrip() + block

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(new_txt)


def upsert_glance_block_in_text(md_text: str, glance: str) -> str:
    """
    Insert/replace the `## At a Glance` block in Markdown:
    - If `## At a Glance` exists, replace until the next `---` or `## ` heading
    - Otherwise insert before `## Abstract`, or append at EOF
    """
    if not glance:
        return md_text

    txt = md_text or ""
    key = "## At a Glance"
    if key in txt:
        # Replace existing glance block
        pattern = re.compile(r"(^## At a Glance\\s*\\n)(.*?)(?=\\n---\\n|\\n##\\s|\\Z)", re.S | re.M)
        return pattern.sub(rf"\\1{glance}\n", txt, count=1)

    abstract_idx = txt.find("## Abstract")
    if abstract_idx != -1:
        before = txt[:abstract_idx].rstrip()
        after = txt[abstract_idx:]
        return f"{before}\n\n## At a Glance\n{glance}\n\n---\n\n{after}"
    return (txt.rstrip() + f"\n\n## At a Glance\n{glance}\n").rstrip() + "\n"


def generate_deep_summary(
    md_file_path: str,
    txt_file_path: str,
    max_retries: int = 3,
    client: DeepSeekClient | None = None,
) -> str | None:
    active_client = client or LLM_CLIENT
    if active_client is None:
        log("[WARN] DEEPSEEK_API_KEY or SUMMARY_API_KEY not set; skipping deep-dive summary.")
        return None
    if not os.path.exists(md_file_path):
        return None

    with open(md_file_path, "r", encoding="utf-8") as f:
        paper_md_content = strip_auto_sections(f.read())

    paper_txt_content = ""
    if os.path.exists(txt_file_path):
        with open(txt_file_path, "r", encoding="utf-8") as f:
            paper_txt_content = f.read()

    system_prompt = (
        "You are a senior academic paper analyst. Write a structured, in-depth, objective summary in English Markdown."
    )
    user_prompt = (
        "Based on the paper content below, write a detailed English summary covering these points in order:\n"
        "1. Core problem and overall meaning (motivation and background).\n"
        "2. Methodology: core idea, key technical details, formulas or algorithm flow (text only).\n"
        "3. Experiments: datasets/scenarios, benchmarks, baselines compared.\n"
        "4. Compute/resources: GPUs, counts, training time if mentioned; note if absent.\n"
        "5. Experiment breadth: number of runs, ablations, whether coverage is sufficient and fair.\n"
        "6. Main conclusions and findings.\n"
        "7. Strengths: highlights of method or experimental design.\n"
        "8. Limitations: coverage gaps, bias risks, application limits.\n\n"
        "Use headings and bullets in Markdown. Be concise but complete.\n"
        "End with a single line containing only “(End)” as the completion marker."
    )

    messages = [{"role": "system", "content": system_prompt}]
    if paper_txt_content:
        messages.append({"role": "user", "content": f"### Extracted PDF text ###\n{paper_txt_content}"})
    messages.append({"role": "user", "content": f"### Paper Markdown metadata ###\n{paper_md_content}"})
    messages.append({"role": "user", "content": user_prompt})

    last = ""
    for attempt in range(1, max_retries + 1):
        try:
            summary = call_llm_text(active_client, messages, temperature=0.3, max_tokens=4096)
            summary = (summary or "").strip()
            if not summary:
                continue
            last = summary
            if os.getenv("DPR_DEBUG_STEP6") == "1":
                log(f"[DEBUG][STEP6] deep_summary attempt={attempt} len={len(summary)} tail={summary[-20:]!r}")
            if "(End)" in summary:
                return summary
            # Continue once if output was truncated
            cont_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "Your previous summary may have been truncated. Continue from where you stopped without repeating prior content."},
                {"role": "user", "content": f"Previous output:\n\n{summary}\n\nContinue and end with a single line “(End)”."},
            ]
            cont = call_llm_text(active_client, cont_messages, temperature=0.3, max_tokens=2048)
            cont = (cont or "").strip()
            merged = f"{summary}\n\n{cont}".strip()
            if os.getenv("DPR_DEBUG_STEP6") == "1":
                log(f"[DEBUG][STEP6] deep_summary_cont attempt={attempt} len={len(cont)} merged_tail={merged[-20:]!r}")
            if "(End)" in merged:
                return merged
        except Exception as e:
            log(f"[WARN] Deep-dive summary failed (attempt {attempt}): {e}")
            time.sleep(2 * attempt)
    return last or None


def generate_glance_overview(
    title: str,
    abstract: str,
    max_retries: int = 3,
    client: DeepSeekClient | None = None,
) -> str | None:
    """
    Generate paper glance (TLDR, Motivation, Method, Result, Conclusion).
    Uses structured JSON output with all five fields.
    """
    active_client = client or LLM_CLIENT
    if active_client is None:
        log("[WARN] LLM_CLIENT not configured; skipping glance generation.")
        return None

    system_prompt = "You are a paper glance assistant. Produce dense but concise English glance summaries."
    payload = {"title": title, "abstract": abstract}
    user_text = json.dumps(payload, ensure_ascii=False)
    user_prompt = (
        "From the title and abstract in the JSON above, output an English glance summary as strict JSON only:\n"
        "{\"tldr\":\"...\",\"motivation\":\"...\",\"method\":\"...\",\"result\":\"...\",\"conclusion\":\"...\"}\n"
        "Requirements:\n"
        "- tldr: 60-90 words, 3-4 short sentences in problem→method→result→impact order\n"
        "- motivation/method/result/conclusion: 15-35 words each, one concrete sentence\n"
        "- Keep proper nouns, technical terms, and model names intact\n"
        "Output must be strict JSON only, no markdown, no fences, no extra text."
    )

    schema = {
        "type": "object",
        "properties": {
            "tldr": {"type": "string"},
            "motivation": {"type": "string"},
            "method": {"type": "string"},
            "result": {"type": "string"},
            "conclusion": {"type": "string"},
        },
        "required": ["tldr", "motivation", "method", "result", "conclusion"],
        "additionalProperties": False,
    }

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
        {"role": "user", "content": user_prompt},
    ]

    for attempt in range(1, max_retries + 1):
        try:
            parsed = call_llm_structured_json(
                active_client,
                messages,
                schema_name="glance_overview",
                schema=schema,
                temperature=0.2,
                max_tokens=STEP6_STRUCTURED_MAX_TOKENS,
            )
            if not isinstance(parsed, dict):
                continue
            obj = parsed
            tldr = str(obj.get("tldr") or "").strip()
            motivation = str(obj.get("motivation") or "").strip()
            method = str(obj.get("method") or "").strip()
            result = str(obj.get("result") or "").strip()
            conclusion = str(obj.get("conclusion") or "").strip()
            if not (tldr and motivation and method and result and conclusion):
                continue
            return "\n".join(
                [
                    f"**TLDR**: {ensure_single_sentence_end(tldr)} \\",
                    f"**Motivation**: {ensure_single_sentence_end(motivation)} \\",
                    f"**Method**: {ensure_single_sentence_end(method)} \\",
                    f"**Result**: {ensure_single_sentence_end(result)} \\",
                    f"**Conclusion**: {ensure_single_sentence_end(conclusion)}",
                ]
            )
        except Exception as e:
            # Hard failures like quota exhaustion: do not retry, fall back
            msg = str(e)
            if (
                "insufficient_user_quota" in msg
                or "quota" in msg.lower() or LEGACY_QUOTA_EXHAUSTED in msg
                or "insufficient quota" in msg
                or ("403" in msg and "Forbidden" in msg)
            ):
                log(f"[WARN] Glance generation failed (quota exhausted, stop retrying): {e}")
                break
            log(f"[WARN] Glance generation failed (attempt {attempt}): {e}")
            time.sleep(2 * attempt)
    return None


def build_glance_fallback(paper: Dict[str, Any]) -> str:
    """
    Fallback glance when LLM quota is unavailable:
    - TLDR prefers llm_tldr_en/llm_tldr, else first abstract sentence;
    - Other fields use abstract heuristics so all five sections exist.
    """
    abstract = str(paper.get("abstract") or "").strip()
    tldr = (
        str(paper.get("llm_tldr_en") or paper.get("llm_tldr") or "").strip()
    )
    evidence = str(paper.get("canonical_evidence") or "").strip()

    def first_sentence(text: str) -> str:
        s = (text or "").strip()
        if not s:
            return ""
        parts = re.split(r"(?<=[。！？.!?])\\s+", s)
        return (parts[0] if parts else s).strip()

    if not tldr:
        tldr = first_sentence(abstract)
    if not tldr and evidence:
        tldr = evidence
    tldr = ensure_single_sentence_end(tldr or "Quick-read summary generated from the abstract.")

    motivation = ensure_single_sentence_end(
        first_sentence(evidence) or "This paper addresses a representative research problem and aims to improve the effectiveness or interpretability of existing methods."
    )

    method_hint = ""
    if abstract:
        m = re.search(r"(we (?:propose|present|introduce|develop)[^\\.]{0,200})\\.", abstract, re.I)
        if m:
            method_hint = m.group(1).strip()
    method = ensure_single_sentence_end(method_hint or "See the abstract and full text for methodology and implementation details.")

    result_hint = ""
    if abstract:
        m = re.search(r"(experiments? (?:show|demonstrate)[^\\.]{0,200})\\.", abstract, re.I)
        if m:
            result_hint = m.group(1).strip()
    result = ensure_single_sentence_end(result_hint or "See the abstract and full text for results and comparative conclusions.")

    conclusion = ensure_single_sentence_end("Overall, this work demonstrates effectiveness on the stated task and offers reusable ideas or tooling.")

    return "\n".join(
        [
            f"**TLDR**: {tldr} \\",
            f"**Motivation**: {motivation} \\",
            f"**Method**: {method} \\",
            f"**Result**: {result} \\",
            f"**Conclusion**: {conclusion}",
        ]
    )


def build_tags_html(section: str, llm_tags: List[str]) -> str:
    tags_html: List[str] = []
    # New pipeline shows query tags; fold legacy keyword:* into query:* to avoid duplicates.
    seen = set()
    for tag in llm_tags:
        raw = str(tag).strip()
        if not raw:
            continue
        kind, label = split_sidebar_tag(raw)
        if kind == "keyword":
            kind = "query"
        label = (label or "").strip()
        if not label:
            continue
        dedup_key = f"{kind}:{label}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)

        # Frontend primary tags use query (blue); paper is reserved.
        css = {
            "query": "tag-blue",
            "paper": "tag-pink",
        }.get(kind, "tag-pink")
        tags_html.append(
            f'<span class="tag-label {css}">{html.escape(label)}</span>'
        )
    return " ".join(tags_html)


def normalize_meta_tags_line(content: str) -> Tuple[str, bool]:
    """
    Legacy fix: article `**Tags**` no longer shows deep/quick section labels.
    Remove only spans whose text is exactly deep/quick section labels.
    """
    if not content:
        return content, False
    pattern = re.compile(
        rf'<span\s+class="tag-label\s+tag-(?:blue|green)">\s*(?:{re.escape(LEGACY_DEEP_READ_ZONE)}|{re.escape(LEGACY_QUICK_SKIM_ZONE)}|Deep Read|Quick Skim)\s*</span>\s*',
        re.IGNORECASE,
    )
    fixed = pattern.sub("", content)
    return fixed, fixed != content


def replace_meta_line(md_text: str, label: str, value: str, add_slash: bool = True) -> Tuple[str, bool]:
    """
    Replace metadata lines like `**Label**: xxx \\`.
    - Replace only the first match
    - Do not insert if missing (avoid rewriting custom meta layout)
    """
    txt = md_text or ""
    v = (value or "").strip()
    if not v:
        return txt, False
    line = f"**{label}**: {v}"
    if add_slash:
        line += " " + "\\"
    pattern = re.compile(f"^\\*\\*{re.escape(label)}\\*\\*:\\s*.*$", re.M)
    # Use callable replace so backslashes in replacement are not escape sequences
    new_txt, n = pattern.subn(lambda _m: line, txt, count=1)
    return new_txt, n > 0 and new_txt != txt


def format_date_str(date_str: str) -> str:
    s = str(date_str or "").strip()
    m = RANGE_DATE_RE.match(s)
    if m:
        a, b = m.group(1), m.group(2)
        return f"{a[:4]}-{a[4:6]}-{a[6:]} ~ {b[:4]}-{b[4:6]}-{b[6:]}"
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return date_str


def prepare_paper_paths(docs_dir: str, date_str: str, title: str, arxiv_id: str) -> Tuple[str, str, str]:
    slug = slugify(title)
    basename = f"{arxiv_id}-{slug}" if arxiv_id else slug
    if RANGE_DATE_RE.match(date_str):
        target_dir = os.path.join(docs_dir, date_str)
        paper_id = f"{date_str}/{basename}"
    else:
        ym = date_str[:6]
        day = date_str[6:]
        target_dir = os.path.join(docs_dir, ym, day)
        paper_id = f"{ym}/{day}/{basename}"
    md_path = os.path.join(target_dir, f"{basename}.md")
    txt_path = os.path.join(target_dir, f"{basename}.txt")
    return md_path, txt_path, paper_id


def prepare_day_report_paths(docs_dir: str, date_str: str) -> Tuple[str, str]:
    if RANGE_DATE_RE.match(date_str):
        day_dir = os.path.join(docs_dir, date_str)
    else:
        ym = date_str[:6]
        day = date_str[6:]
        day_dir = os.path.join(docs_dir, ym, day)
    day_readme = os.path.join(day_dir, "README.md")
    return day_dir, day_readme


def prepare_home_module_paths(docs_dir: str) -> Tuple[str, str]:
    notice_path = os.path.join(docs_dir, "_home_notice.md")
    promo_path = os.path.join(docs_dir, "_home_promo.md")
    return notice_path, promo_path


def ensure_home_module_files(docs_dir: str) -> Tuple[str, str]:
    notice_path, promo_path = prepare_home_module_paths(docs_dir)
    if not os.path.exists(notice_path):
        with open(notice_path, "w", encoding="utf-8") as f:
            f.write("────────────────────────────────────────\n")
            f.write("(Notice placeholder) Welcome to Daily Paper Reader.\n")
            f.write("(Notice placeholder) Put weekly updates and maintenance notices here.\n")
            f.write("────────────────────────────────────────\n")
    if not os.path.exists(promo_path):
        with open(promo_path, "w", encoding="utf-8") as f:
            f.write("════════════════════════════════════════\n")
            f.write("(Promo placeholder) Star / Fork this project.\n")
            f.write("(Promo placeholder) Issues and PRs welcome.\n")
            f.write("════════════════════════════════════════\n")
    return notice_path, promo_path


def _read_module_markdown(path: str) -> str:
    if not os.path.exists(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return (f.read() or "").strip()
    except Exception:
        return ""


def _format_entry_tags(tags: List[Tuple[str, str]]) -> str:
    labels: List[str] = []
    for kind, label in tags or []:
        k = (kind or "").strip()
        v = (label or "").strip()
        if k == "score":
            try:
                score_num = float(v)
                labels.append(f"Score: {score_num:.1f}/10")
            except Exception:
                labels.append(f"Score: {v}")
            continue
        if not v:
            continue
        if k in ("keyword", "query", "paper"):
            labels.append(f"{k}:{v}")
        else:
            labels.append(v)
    return ", ".join(labels) if labels else "No tags"


def _entry_score_text(tags: List[Tuple[str, str]]) -> str:
    for kind, label in tags or []:
        if (kind or "").strip() == "score":
            v = (label or "").strip()
            if not v:
                return ""
            try:
                return f"{float(v):.1f}/10"
            except Exception:
                return v
    return ""


def build_daily_brief_summary(
    date_label: str,
    deep_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    quick_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    total_count: int,
    run_status: str,
) -> str:
    if total_count == 0:
        return "> No new recommendations today; the system produced no papers to display."

    def _format_preview_item(paper_id: str, title: str, tags: List[Tuple[str, str]]) -> str:
        name = ((title or "").strip() or paper_id)
        score = _entry_score_text(tags)
        return f"“{name}” ({score})" if score else f"“{name}”"

    deep_preview = [_format_preview_item(paper_id, title, tags) for paper_id, title, tags in deep_entries[:2] if (title or paper_id)]
    quick_preview = [_format_preview_item(paper_id, title, tags) for paper_id, title, tags in quick_entries[:3] if (title or paper_id)]
    highlight = []
    if deep_preview:
        highlight.append(f"- Deep Read: {', '.join(deep_preview)}")
    if quick_preview:
        highlight.append(f"- Quick Skim: {', '.join(quick_preview)}")
    if not highlight:
        return (
            f"- Status: {run_status}.\n"
            f"- Today's generation is complete: {total_count} paper(s) total ({len(deep_entries)} deep-read, {len(quick_entries)} quick-skim)."
        )

    fallback = (
        f"- Generated {total_count} recommendation(s) today ({len(deep_entries)} deep-read, {len(quick_entries)} quick-skim)\n"
        + "\n".join(highlight)
        + "\n- These results cover currently active directions; start with the key problems and methods of the deep-read papers."
    )

    if LLM_CLIENT is None:
        return fallback

    system_prompt = (
        "You are a daily-report editor. Write up to 3 concise, specific English sentences."
        "Base content only on the provided recommendation data; do not invent papers."
    )
    user_prompt = (
        f"Report date: {date_label}\n"
        f"Status: {run_status}\n"
        f"Total: {total_count} papers\n"
        f"Deep dive: {len(deep_entries)} papers\n"
        f"Quick skim: {len(quick_entries)} papers\n"
        f"Deep list (with scores): {json.dumps(deep_preview, ensure_ascii=False)}\n"
        f"Quick list (with scores): {json.dumps(quick_preview, ensure_ascii=False)}\n\n"
        "Output format:\n"
        "1) One sentence on what today covers (headline tone).\n"
        "2) One sentence on the top 1-2 directions/findings.\n"
        "3) One sentence of next-step advice for general readers.\n"
        "Output 1-3 plain lines only; no Markdown headings or JSON."
    )
    try:
        content = call_llm_text(
            LLM_CLIENT,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.45,
            max_tokens=768,
        )
        content = (content or "").strip()
        if content:
            return content
    except Exception as e:
        log(f"[WARN] Failed to generate daily brief: {e}")

    return fallback


def build_docsify_id_href(path_no_ext: str) -> str:
    """
    Build Docsify Markdown links as `/...`.
    Note: `(#/...)` in Markdown is treated as in-page anchors and can break querySelector.
    """
    p = str(path_no_ext or "").strip()
    p = p.replace("\\", "/").strip()
    p = re.sub(r"\.md$", "", p, flags=re.IGNORECASE)
    if not p:
        return "/"
    p = p.lstrip("/")
    return f"/{p}"


def build_latest_report_section(
    date_str: str,
    date_label: str | None,
    generated_at: str,
    recommend_exists: bool,
    deep_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    quick_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    paper_evidence_by_id: Dict[str, str],
) -> str:
    effective_label = (date_label or "").strip() or format_date_str(date_str)
    run_status = "success" if recommend_exists else "no recommend file (treated as empty)"
    total = len(deep_entries) + len(quick_entries)
    summary = build_daily_brief_summary(
        date_label=effective_label,
        deep_entries=deep_entries,
        quick_entries=quick_entries,
        total_count=total,
        run_status=run_status,
    )

    lines: List[str] = []
    lines.append(f"- Latest run date: {effective_label}")
    lines.append(f"- Run time: {generated_at}")
    lines.append(f"- Run status: {run_status}")
    lines.append(f"- Total papers this run: {total}")
    lines.append(f"- Deep Read: {len(deep_entries)}")
    lines.append(f"- Quick Skim: {len(quick_entries)}")
    if summary:
        lines.append("")
        lines.append("### Today's Brief (AI)")
        lines.append(summary)
    if RANGE_DATE_RE.match(date_str):
        report_href = build_docsify_id_href(f"{date_str}/README")
    else:
        ym = date_str[:6]
        day = date_str[6:]
        report_href = build_docsify_id_href(f"{ym}/{day}/README")
    lines.append(f"- Details: [{report_href}]({report_href})")
    lines.append("")
    lines.append("### Deep Read — paper tags")
    if deep_entries:
        for idx, (paper_id, title, tags) in enumerate(deep_entries, start=1):
            safe_title = (title or "").strip() or paper_id
            evidence = (paper_evidence_by_id.get(str(paper_id).strip(), "") or "").strip()
            lines.append(f"{idx}. [{safe_title}]({build_docsify_id_href(paper_id)})  ")
            lines.append(f"   Tags: {_format_entry_tags(tags)}")
            if evidence:
                lines.append(f"   evidence: {evidence}")
    else:
        lines.append("- No deep-read recommendations this run.")
    lines.append("")
    lines.append("### Quick Skim — paper tags")
    if quick_entries:
        for idx, (paper_id, title, tags) in enumerate(quick_entries, start=1):
            safe_title = (title or "").strip() or paper_id
            evidence = (paper_evidence_by_id.get(str(paper_id).strip(), "") or "").strip()
            lines.append(f"{idx}. [{safe_title}]({build_docsify_id_href(paper_id)})  ")
            lines.append(f"   Tags: {_format_entry_tags(tags)}")
            if evidence:
                lines.append(f"   evidence: {evidence}")
    else:
        lines.append("- No quick-skim recommendations this run.")
    lines.append("")
    return "\n".join(lines)


def normalize_sidebar_tag(tag: str) -> str:
    text = (tag or "").strip()
    if not text:
        return ""
    for prefix in ("keyword:", "query:", "paper:", "ref:", "cite:"):
        if text.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def split_sidebar_tag(tag: str) -> Tuple[str, str]:
    """
    Parse tag into (kind, label):
    - keyword:xxx -> ("keyword", "xxx")
    - query:xxx   -> ("query", "xxx")
    - paper/ref/cite:xxx -> ("paper", "xxx")  # reserved citation/tracking tag
    - otherwise -> ("other", raw text)
    """
    raw = (tag or "").strip()
    if not raw:
        return ("other", "")
    for prefix, kind in (
        ("keyword:", "keyword"),
        ("query:", "query"),
        ("paper:", "paper"),
        ("ref:", "paper"),
        ("cite:", "paper"),
    ):
        if raw.startswith(prefix):
            label = raw[len(prefix) :].strip()
            # composite is an internal llm-refine requirement suffix; hide from frontend.
            if kind == "query" and label.endswith(":composite"):
                label = label[: -len(":composite")].strip()
            return (kind, label)
    return ("other", raw)


def round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def score_to_star_rating(score: Any) -> float:
    """
    Map 0-10 score to 0-5 stars, rounded to 0.5.
    e.g. 10->5, 9->4.5, 8->4, 7->3.5
    """
    try:
        s = float(score)
    except Exception:
        return 0.0
    if not math.isfinite(s):
        return 0.0
    s = max(0.0, min(10.0, s))
    return round_half_up(s) / 2.0


def build_sidebar_stars_html(score: Any) -> str:
    rating = score_to_star_rating(score)
    try:
        score_str = f"{float(score):.1f}"
    except Exception:
        score_str = ""

    if score_str:
        title = f"Score: {score_str}/10 ({rating:.1f}/5)"
    else:
        title = "Score: N/A"

    pct = max(0.0, min(100.0, (rating / 5.0) * 100.0))
    pct_str = f"{pct:.0f}%"

    # Background + fill stars for half-star display
    return (
        f'<span class="dpr-stars" title="{html.escape(title)}" '
        f'aria-label="{rating:.1f} out of 5">'
        f'<span class="dpr-stars-bg">☆☆☆☆☆</span>'
        f'<span class="dpr-stars-fill" style="width:{pct_str}">★★★★★</span>'
        f"</span>"
    )


def extract_sidebar_tags(paper: Dict[str, Any], max_tags: int = 6) -> List[Tuple[str, str]]:
    """
    Sidebar tags:
    - Use llm_tags only (match article `**Tags**`) so sidebar and body stay aligned
    - Dedupe and cap count to keep sidebar short
    """
    raw: List[str] = []
    if isinstance(paper.get("llm_tags"), list):
        raw.extend([str(t) for t in (paper.get("llm_tags") or [])])

    # Fold legacy keyword:* into query:* to avoid duplicate labels.
    seen_labels = set()
    q: List[Tuple[str, str]] = []
    paper_tags: List[Tuple[str, str]] = []
    other: List[Tuple[str, str]] = []

    for t in raw:
        kind, label = split_sidebar_tag(t)
        if kind == "keyword":
            kind = "query"
        label = (label or "").strip()
        if not label:
            continue
        dedup_key = f"{kind}:{label}"
        if dedup_key in seen_labels:
            continue
        seen_labels.add(dedup_key)
        if kind == "query":
            q.append((kind, label))
        elif kind == "paper":
            paper_tags.append((kind, label))
        else:
            other.append((kind, label))

        if max_tags > 0 and len(seen_labels) >= max_tags:
            break

    # Display order: score -> query -> paper citation -> other
    tags = q + paper_tags + other
    score = paper.get("llm_score")
    score_tag = []
    if score is not None:
        try:
            score_tag.append(("score", str(float(score))))
        except Exception:
            score_tag.append(("score", str(score)))
    return score_tag + tags


def ensure_text_content(pdf_url: str, txt_path: str) -> str:
    if os.path.exists(txt_path):
        with open(txt_path, "r", encoding="utf-8") as f:
            return f.read()
    text_content = fetch_paper_markdown_via_jina(pdf_url)
    if text_content is None and pdf_url:
        resp = requests.get(pdf_url, timeout=60)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp_pdf:
            tmp_pdf.write(resp.content)
            tmp_pdf.flush()
            text_content = extract_pdf_text(tmp_pdf.name)
    os.makedirs(os.path.dirname(txt_path), exist_ok=True)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(text_content or "")
    return text_content or ""


def yaml_escape_value(s: str) -> str:
    if not s:
        return '""'
    if any(c in s for c in [':', '#', '"', "'", '\n', '[', ']', '{', '}', ',', '&', '*', '!', '|', '>', '%', '@', '`']):
        return '"' + s.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'
    return s


def maybe_generate_paper_figures(
    paper: Dict[str, Any],
    *,
    docs_dir: str,
    paper_id: str,
    pdf_url: str,
) -> List[Dict[str, Any]]:
    figures, _tables = maybe_generate_paper_media(
        paper,
        docs_dir=docs_dir,
        paper_id=paper_id,
        pdf_url=pdf_url,
    )
    return figures


def maybe_generate_paper_media(
    paper: Dict[str, Any],
    *,
    docs_dir: str,
    paper_id: str,
    pdf_url: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    source_key = str(paper.get("source") or "").strip().lower()
    if source_key not in {"arxiv", "biorxiv"}:
        return [], []
    if not str(pdf_url or "").strip():
        return [], []

    asset_key = str(paper.get("id") or paper_id.replace("/", "-")).strip()
    try:
        return ensure_paper_media(
            pdf_url=pdf_url,
            docs_dir=docs_dir,
            source_key=source_key,
            asset_key=asset_key,
        )
    except Exception as e:
        log(f"[WARN] Paper figure extraction failed: {asset_key}: {e}")
        return [], []


def upsert_front_matter_field(md_text: str, key: str, value: str) -> Tuple[str, bool]:
    text = str(md_text or "")
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return text, False
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    end_idx = normalized.find("\n---", 3)
    if end_idx == -1:
        return text, False

    block = normalized[4:end_idx]
    lines = block.split("\n") if block else []
    updated_lines: List[str] = []
    replaced = False
    for line in lines:
        if line.startswith(f"{key}:"):
            updated_lines.append(f"{key}: {value}")
            replaced = True
        else:
            updated_lines.append(line)
    if not replaced:
        updated_lines.append(f"{key}: {value}")
    updated = "---\n" + "\n".join(updated_lines).rstrip() + "\n---" + normalized[end_idx + 4 :]
    return updated, updated != normalized


def build_markdown_content(
    paper: Dict[str, Any],
    section: str,
    tags_list: List[str],
) -> str:
    """
    Build paper Markdown with YAML front matter metadata.
    Frontend renders layout by parsing front matter.
    """
    title = (paper.get("title") or "").strip()
    authors = paper.get("authors") or []
    published = str(paper.get("published") or "").strip()
    if published:
        published = published[:10]
    pdf_url = str(paper.get("pdf_url") or paper.get("link") or "").strip()
    score = paper.get("llm_score")
    evidence = str(paper.get("canonical_evidence") or "").strip()
    tldr = (
        paper.get("llm_tldr_en")
        or paper.get("llm_tldr")
        or ""
    ).strip()
    abstract_en = (paper.get("abstract") or "").strip()
    if not abstract_en:
        abstract_en = "arXiv did not provide an abstract for this paper."
    paper_source = str(paper.get("source") or "").strip()
    selection_source = str(paper.get("selection_source") or "").strip()
    figure_assets = paper.get("_figure_assets") if isinstance(paper.get("_figure_assets"), list) else []
    table_assets = paper.get("_table_assets") if isinstance(paper.get("_table_assets"), list) else []

    # Parse glance content
    glance = paper.get("_glance_overview", "").strip()
    glance_tldr = ""
    glance_motivation = ""
    glance_method = ""
    glance_result = ""
    glance_conclusion = ""

    if glance:
        for line in glance.split("\n"):
            line = line.strip().rstrip("\\").strip()
            if line.startswith("**TLDR**：") or line.startswith("**TLDR**:"):
                glance_tldr = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif line.startswith("**Motivation**：") or line.startswith("**Motivation**:"):
                glance_motivation = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif line.startswith("**Method**：") or line.startswith("**Method**:"):
                glance_method = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif line.startswith("**Result**：") or line.startswith("**Result**:"):
                glance_result = line.split("：", 1)[-1].split(":", 1)[-1].strip()
            elif line.startswith("**Conclusion**：") or line.startswith("**Conclusion**:"):
                glance_conclusion = line.split("：", 1)[-1].split(":", 1)[-1].strip()

    # Prefer glance TLDR (~100 chars), else legacy TLDR
    display_tldr = glance_tldr if glance_tldr else tldr

    # Escape special characters in YAML string values
    # Build YAML front matter
    lines = ["---"]
    lines.append(f"title: {yaml_escape_value(title)}")
    lines.append(f"authors: {yaml_escape_value(', '.join(authors) if authors else 'Unknown')}")
    lines.append(f"date: {yaml_escape_value(published or 'Unknown')}")
    if pdf_url:
        lines.append(f"pdf: {yaml_escape_value(pdf_url)}")
    if tags_list:
        # Keep full kind:label; frontend handles display
        lines.append(f"tags: [{', '.join(yaml_escape_value(t) for t in tags_list)}]")
    if score is not None:
        lines.append(f"score: {score}")
    if evidence:
        lines.append(f"evidence: {yaml_escape_value(evidence)}")
    if display_tldr:
        lines.append(f"tldr: {yaml_escape_value(display_tldr)}")
    if paper_source:
        lines.append(f"source: {yaml_escape_value(paper_source)}")
    if selection_source:
        lines.append(f"selection_source: {yaml_escape_value(selection_source)}")
    if figure_assets:
        lines.append(f"figures_json: {yaml_escape_value(json.dumps(figure_assets, ensure_ascii=False))}")
    if table_assets:
        lines.append(f"tables_json: {yaml_escape_value(json.dumps(table_assets, ensure_ascii=False))}")

    # Glance fields
    if glance_motivation:
        lines.append(f"motivation: {yaml_escape_value(glance_motivation)}")
    if glance_method:
        lines.append(f"method: {yaml_escape_value(glance_method)}")
    if glance_result:
        lines.append(f"result: {yaml_escape_value(glance_result)}")
    if glance_conclusion:
        lines.append(f"conclusion: {yaml_escape_value(glance_conclusion)}")

    lines.append("---")
    lines.append("")

    # Body: abstract section
    lines.append("## Abstract")
    lines.append(abstract_en)

    return "\n".join(lines)


def build_tags_list(section: str, llm_tags: List[str]) -> List[str]:
    """
    Build tag list, keeping kind:label format.
    """
    tags: List[str] = []
    seen = set()
    for tag in llm_tags:
        raw = str(tag).strip()
        if not raw:
            continue
        kind, label = split_sidebar_tag(raw)
        if kind == "keyword":
            kind = "query"
        label = (label or "").strip()
        if not label:
            continue
        dedup_key = f"{kind}:{label}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        tags.append(dedup_key)
    return tags


def process_paper(
    paper: Dict[str, Any],
    section: str,
    date_str: str,
    docs_dir: str,
    glance_only: bool = False,
    force_glance: bool = False,
) -> Tuple[str, str]:
    title = (paper.get("title") or "").strip()
    arxiv_id = str(paper.get("id") or paper.get("paper_id") or "").strip()
    md_path, txt_path, paper_id = prepare_paper_paths(docs_dir, date_str, title, arxiv_id)
    abstract_en = (paper.get("abstract") or "").strip()
    pdf_url = str(paper.get("pdf_url") or paper.get("link") or "").strip()
    paper_llm_client = create_llm_client()

    glance = ""

    if os.path.exists(md_path):
        # Even in glance-only mode, ensure .txt exists for chat context etc.
        if glance_only and pdf_url:
            try:
                ensure_text_content(pdf_url, txt_path)
            except Exception:
                # Non-blocking: continue if txt fetch fails
                pass

        try:
            with open(md_path, "r", encoding="utf-8") as f:
                existing = f.read()
        except Exception:
            existing = ""

        existing_meta = _parse_front_matter(existing)
        has_figures_json = bool(str(existing_meta.get("figures_json") or "").strip()) if existing_meta else False
        has_tables_json = bool(str(existing_meta.get("tables_json") or "").strip()) if existing_meta else False
        if not has_figures_json or not has_tables_json:
            figures, tables = maybe_generate_paper_media(
                paper,
                docs_dir=docs_dir,
                paper_id=paper_id,
                pdf_url=pdf_url,
            )
            if figures and not has_figures_json:
                paper["_figure_assets"] = figures
                updated, changed = upsert_front_matter_field(
                    existing,
                    "figures_json",
                    yaml_escape_value(json.dumps(figures, ensure_ascii=False)),
                )
                if changed:
                    with open(md_path, "w", encoding="utf-8") as f:
                        f.write(updated + ("\n" if not updated.endswith("\n") else ""))
                    existing = updated
            if tables and not has_tables_json:
                paper["_table_assets"] = tables
                updated, changed = upsert_front_matter_field(
                    existing,
                    "tables_json",
                    yaml_escape_value(json.dumps(tables, ensure_ascii=False)),
                )
                if changed:
                    with open(md_path, "w", encoding="utf-8") as f:
                        f.write(updated + ("\n" if not updated.endswith("\n") else ""))
                    existing = updated

        # Skip glance if present unless force_glance=true
        has_glance = "## At a Glance" in existing
        if force_glance or not has_glance:
            glance = generate_glance_overview(title, abstract_en, client=paper_llm_client) or build_glance_fallback(paper)
            if glance:
                paper["_glance_overview"] = glance

        # Legacy fix: meta TLDR lines should not end with backslash
        fixed, changed = normalize_meta_tldr_line(existing)
        if changed:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(fixed + ("\n" if not fixed.endswith("\n") else ""))
            existing = fixed
            if os.getenv("DPR_DEBUG_STEP6") == "1":
                log(f"[DEBUG][STEP6] fixed TLDR trailing slash: {os.path.basename(md_path)}")

        # Legacy fix: remove deep/quick section labels from article Tags
        fixed, changed = normalize_meta_tags_line(existing)
        if changed:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(fixed + ("\n" if not fixed.endswith("\n") else ""))
            existing = fixed
            if os.getenv("DPR_DEBUG_STEP6") == "1":
                log(f"[DEBUG][STEP6] removed section tag from Tags: {os.path.basename(md_path)}")

        # Sync Tags line (show both keyword:SR and query:SR when both exist)
        tags_html = build_tags_html(section, paper.get("llm_tags") or [])
        if tags_html:
            updated, changed = replace_meta_line(existing, "Tags", tags_html, add_slash=True)
            if changed:
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(updated + ("\n" if not updated.endswith("\n") else ""))
                existing = updated

        # Normalize glance block line breaks
        updated, changed = normalize_glance_block_format(existing)
        if changed:
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(updated + ("\n" if not updated.endswith("\n") else ""))
            existing = updated

        # Insert/replace glance content
        if glance and (force_glance or "## At a Glance" not in existing):
            updated = upsert_glance_block_in_text(existing, glance)
            if updated != existing:
                with open(md_path, "w", encoding="utf-8") as f:
                    f.write(updated)
                existing = updated

        if glance_only:
            # Glance-only: no PDF fetch or deep summary
            return paper_id, title

        if section == "deep":
            # Deep section: skip if detailed summary exists
            tail = extract_section_tail(existing, "Detailed Summary (auto-generated)")
            if tail:
                return paper_id, title

            # Generate detailed summary
            pdf_url = str(paper.get("pdf_url") or paper.get("link") or "").strip()
            ensure_text_content(pdf_url, txt_path)
            summary = generate_deep_summary(md_path, txt_path, client=paper_llm_client)
            if summary:
                upsert_auto_block(md_path, "Detailed Summary (auto-generated)", summary)
            return paper_id, title
        else:
            # Quick section: no detailed summary, glance + abstract only
            return paper_id, title

    # New file, glance-only: skip PDF/Jina, build page from metadata
    if glance_only:
        # Glance mode still ensures full .txt (jina first, pymupdf fallback)
        if pdf_url:
            try:
                ensure_text_content(pdf_url, txt_path)
            except Exception:
                pass
        figures, tables = maybe_generate_paper_media(
            paper,
            docs_dir=docs_dir,
            paper_id=paper_id,
            pdf_url=pdf_url,
        )
        if figures:
            paper["_figure_assets"] = figures
        if tables:
            paper["_table_assets"] = tables
        glance = generate_glance_overview(title, abstract_en, client=paper_llm_client) or build_glance_fallback(paper)
        if glance:
            paper["_glance_overview"] = glance
        tags_list = build_tags_list(section, paper.get("llm_tags") or [])
        content = build_markdown_content(paper, section, tags_list)
        os.makedirs(os.path.dirname(md_path), exist_ok=True)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(content)
        return paper_id, title

    # New file: full content generation
    pdf_url = str(paper.get("pdf_url") or paper.get("link") or "").strip()
    ensure_text_content(pdf_url, txt_path)
    figures, tables = maybe_generate_paper_media(
        paper,
        docs_dir=docs_dir,
        paper_id=paper_id,
        pdf_url=pdf_url,
    )
    if figures:
        paper["_figure_assets"] = figures
    if tables:
        paper["_table_assets"] = tables

    tags_list = build_tags_list(section, paper.get("llm_tags") or [])
    glance = generate_glance_overview(title, abstract_en, client=paper_llm_client) or build_glance_fallback(paper)
    if glance:
        paper["_glance_overview"] = glance
    content = build_markdown_content(paper, section, tags_list)

    os.makedirs(os.path.dirname(md_path), exist_ok=True)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(content)

    # Deep section: generate detailed summary
    if section == "deep":
        summary = generate_deep_summary(md_path, txt_path, client=paper_llm_client)
        if summary:
            upsert_auto_block(md_path, "Detailed Summary (auto-generated)", summary)
    # Quick section: no extra summary beyond glance and abstract

    return paper_id, title


def _extract_paper_href(line: str) -> str | None:
    m = re.search(r'href="([^"]+)"', line)
    return m.group(1) if m else None


def _extract_day_block_papers(block_lines: List[str]) -> Tuple[List[str], List[str]]:
    """Extract paper link lines from a sidebar day block, grouped by section.

    Returns (deep_lines, quick_lines).
    """
    deep_lines: List[str] = []
    quick_lines: List[str] = []
    current = "deep"
    for line in block_lines:
        if "Deep Read" in line or LEGACY_DEEP_READ_ZONE in line:
            current = "deep"
            continue
        if "Quick Skim" in line or LEGACY_QUICK_SKIM_ZONE in line:
            current = "quick"
            continue
        if 'href="#/' in line and line.strip().startswith("*"):
            if current == "quick":
                quick_lines.append(line)
            else:
                deep_lines.append(line)
    return deep_lines, quick_lines


def update_sidebar(
    sidebar_path: str,
    date_str: str,
    deep_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    quick_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    paper_evidence_by_id: Dict[str, str],
    date_label: str | None = None,
) -> None:
    def build_sidebar_item_payload(
        paper_id: str,
        title: str,
        tags: List[Tuple[str, str]],
        route_href: str,
        evidence: str = "",
    ) -> str:
        score_text = "-"
        clean_tags: List[Dict[str, str]] = []
        for kind, label in (tags or []):
            safe_kind = (kind or "other").strip() or "other"
            safe_label = (label or "").strip()
            if not safe_label:
                continue
            if safe_kind == "score":
                try:
                    score_text = f"{float(safe_label):.1f}"
                except Exception:
                    score_text = safe_label
                continue
            clean_tags.append({"kind": safe_kind, "label": safe_label})

        arxiv_id = str(paper_id or "").strip().split("/")[-1]
        paper_link = f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else route_href
        payload = {
            "title": (title or "").strip() or paper_id,
            "link": paper_link,
            "score": score_text,
            "tags": clean_tags,
        }
        safe_evidence = str(evidence or "").strip()
        if safe_evidence:
            payload["evidence"] = safe_evidence
        return html.escape(json.dumps(payload, ensure_ascii=False), quote=True)

    effective_label = (date_label or "").strip() or format_date_str(date_str)
    # Hidden marker for stable day-block updates when display label changes
    marker = f"<!--dpr-date:{date_str}-->"
    day_heading = f"  * {effective_label} {marker}\n"
    legacy_day_heading = f"  * {format_date_str(date_str)}\n"

    lines: List[str] = []
    if os.path.exists(sidebar_path):
        with open(sidebar_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

    daily_idx = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("* Daily Papers"):
            daily_idx = i
            break
    if daily_idx == -1:
        if not any(("[Home]" in line or f"[{LEGACY_HOME}]" in line) for line in lines):
            lines.append("* [Home](/)\n")
        lines.append("* Daily Papers\n")
        daily_idx = len(lines) - 1

    day_idx = -1
    for i in range(daily_idx + 1, len(lines)):
        line = lines[i]
        if line.startswith("* "):
            break
        # Prefer exact marker match
        if marker in line:
            day_idx = i
            break
        # Legacy format without marker
        if line == legacy_day_heading:
            day_idx = i
            break

    existing_deep_lines: List[str] = []
    existing_quick_lines: List[str] = []
    if day_idx != -1:
        end = day_idx + 1
        while end < len(lines):
            if lines[end].startswith("  * ") and not lines[end].startswith("    * "):
                break
            end += 1
        existing_deep_lines, existing_quick_lines = _extract_day_block_papers(
            lines[day_idx + 1 : end]
        )
        del lines[day_idx:end]

    new_hrefs: Set[str] = set()
    for pid, _, _ in deep_entries:
        new_hrefs.add(f"#/{pid}")
    for pid, _, _ in quick_entries:
        new_hrefs.add(f"#/{pid}")
    extra_deep = [
        l for l in existing_deep_lines if _extract_paper_href(l) not in new_hrefs
    ]
    extra_quick = [
        l for l in existing_quick_lines if _extract_paper_href(l) not in new_hrefs
    ]

    block: List[str] = [day_heading]
    if deep_entries or extra_deep:
        block.append("    * Deep Read\n")
        for paper_id, title, tags in deep_entries:
            safe_title = html.escape((title or "").strip() or paper_id)
            href = f"#/{paper_id}"
            evidence = paper_evidence_by_id.get(str(paper_id).strip(), "")
            payload_json = build_sidebar_item_payload(paper_id, title, tags, href, evidence)
            block.append(
                "      * "
                f'<a class="dpr-sidebar-item-link dpr-sidebar-item-structured" href="{href}" data-sidebar-item="{payload_json}">{safe_title}</a>\n'
            )
        block.extend(extra_deep)
    if quick_entries or extra_quick:
        block.append("    * Quick Skim\n")
        for paper_id, title, tags in quick_entries:
            safe_title = html.escape((title or "").strip() or paper_id)
            href = f"#/{paper_id}"
            evidence = paper_evidence_by_id.get(str(paper_id).strip(), "")
            payload_json = build_sidebar_item_payload(paper_id, title, tags, href, evidence)
            block.append(
                "      * "
                f'<a class="dpr-sidebar-item-link dpr-sidebar-item-structured" href="{href}" data-sidebar-item="{payload_json}">{safe_title}</a>\n'
            )
        block.extend(extra_quick)

    insert_idx = daily_idx + 1
    lines[insert_idx:insert_idx] = block

    # Remove legacy sidebar daily-report links
    i = daily_idx + 1
    while i < len(lines):
        line = lines[i]
        if line.startswith("* "):
            break
        if lines[i].startswith("    * [Daily Report]("):
            del lines[i]
            continue
        i += 1

    with open(sidebar_path, "w", encoding="utf-8") as f:
        f.writelines(lines)


def build_day_report_markdown(
    date_str: str,
    date_label: str | None,
    deep_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    quick_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    recommend_exists: bool,
) -> str:
    effective_label = (date_label or "").strip() or format_date_str(date_str)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    total = len(deep_entries) + len(quick_entries)
    run_status = "success" if recommend_exists else "no recommend file (treated as empty)"
    summary = build_daily_brief_summary(
        date_label=effective_label,
        deep_entries=deep_entries,
        quick_entries=quick_entries,
        total_count=total,
        run_status=run_status,
    )

    lines: List[str] = []
    lines.append(f"# Daily Report · {effective_label}")
    lines.append("")
    lines.append(f"- Generated at: {generated_at}")
    lines.append(f"- Total recommendations this run: {total}")
    lines.append(f"- Deep Read: {len(deep_entries)}")
    lines.append(f"- Quick Skim: {len(quick_entries)}")
    if summary:
        lines.append("")
        lines.append("## Today's Brief (AI)")
        lines.append(summary)
    lines.append("")

    if not recommend_exists:
        lines.append("> No recommend result file was found for this run.")
        lines.append("")
    elif total == 0:
        lines.append("> This run produced no recommendable papers.")
        lines.append("")

    lines.append("## Deep Read")
    if deep_entries:
        for idx, (paper_id, title, _tags) in enumerate(deep_entries, start=1):
            safe_title = (title or "").strip() or paper_id
            score = _entry_score_text(_tags)
            suffix = f"({score})" if score else ""
            lines.append(f"{idx}. [{safe_title}]({build_docsify_id_href(paper_id)}) {suffix}")
    else:
        lines.append("- No deep-read recommendations this run.")
    lines.append("")

    lines.append("## Quick Skim")
    if quick_entries:
        for idx, (paper_id, title, _tags) in enumerate(quick_entries, start=1):
            safe_title = (title or "").strip() or paper_id
            score = _entry_score_text(_tags)
            suffix = f"({score})" if score else ""
            lines.append(f"{idx}. [{safe_title}]({build_docsify_id_href(paper_id)}) {suffix}")
    else:
        lines.append("- No quick-skim recommendations this run.")
    lines.append("")

    lines.append("---")
    lines.append("Use the keyboard arrow keys to move quickly between the daily report and papers.")
    lines.append("")
    return "\n".join(lines)


def write_day_report_readme(
    docs_dir: str,
    date_str: str,
    date_label: str | None,
    deep_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    quick_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    recommend_exists: bool,
) -> str:
    day_dir, day_readme = prepare_day_report_paths(docs_dir, date_str)
    os.makedirs(day_dir, exist_ok=True)
    content = build_day_report_markdown(
        date_str=date_str,
        date_label=date_label,
        deep_entries=deep_entries,
        quick_entries=quick_entries,
        recommend_exists=recommend_exists,
    )
    with open(day_readme, "w", encoding="utf-8") as f:
        f.write(content)
    return day_readme


def list_day_report_links(docs_dir: str) -> List[Tuple[str, str]]:
    out: List[Tuple[str, str]] = []
    if not os.path.isdir(docs_dir):
        return out
    # 1) Range dirs: YYYYMMDD-YYYYMMDD
    range_dirs = sorted(
        [d for d in os.listdir(docs_dir) if RANGE_DATE_RE.fullmatch(d)],
        reverse=True,
    )
    for rd in range_dirs:
        readme = os.path.join(docs_dir, rd, "README.md")
        if not os.path.exists(readme):
            continue
        out.append((format_date_str(rd), build_docsify_id_href(f"{rd}/README")))

    # 2) Single-day dirs: docs/YYYYMM/DD
    ym_dirs = sorted([d for d in os.listdir(docs_dir) if re.fullmatch(r"\d{6}", d)], reverse=True)
    for ym in ym_dirs:
        ym_path = os.path.join(docs_dir, ym)
        if not os.path.isdir(ym_path):
            continue
        day_dirs = sorted([d for d in os.listdir(ym_path) if re.fullmatch(r"\d{2}", d)], reverse=True)
        for day in day_dirs:
            readme = os.path.join(ym_path, day, "README.md")
            if not os.path.exists(readme):
                continue
            date8 = f"{ym}{day}"
            label = format_date_str(date8)
            href = build_docsify_id_href(f"{ym}/{day}/README")
            out.append((label, href))
    return out


def build_home_readme_content(
    docs_dir: str,
    date_str: str,
    date_label: str | None,
    generated_at: str,
    recommend_exists: bool,
    deep_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    quick_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    paper_evidence_by_id: Dict[str, str],
) -> str:
    notice_path, promo_path = ensure_home_module_files(docs_dir)
    notice_md = _read_module_markdown(notice_path)
    promo_md = _read_module_markdown(promo_path)
    latest_report_md = build_latest_report_section(
        date_str=date_str,
        date_label=date_label,
        generated_at=generated_at,
        recommend_exists=recommend_exists,
        deep_entries=deep_entries,
        quick_entries=quick_entries,
        paper_evidence_by_id=paper_evidence_by_id,
    )

    lines: List[str] = []
    lines.append(notice_md or "(Notice module empty)")
    lines.append("")
    lines.append("## Daily Reports")
    lines.append(latest_report_md)
    lines.append("")
    lines.append(promo_md or "(Promo module empty)")
    lines.append("")
    return "\n".join(lines)


def sync_home_readme_from_day_report(
    docs_dir: str,
    date_str: str,
    date_label: str | None,
    generated_at: str,
    recommend_exists: bool,
    deep_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    quick_entries: List[Tuple[str, str, List[Tuple[str, str]]]],
    paper_evidence_by_id: Dict[str, str],
) -> str:
    home_readme = os.path.join(docs_dir, "README.md")
    # Home README = notice md + latest report + promo md
    content = build_home_readme_content(
        docs_dir=docs_dir,
        date_str=date_str,
        date_label=date_label,
        generated_at=generated_at,
        recommend_exists=recommend_exists,
        deep_entries=deep_entries,
        quick_entries=quick_entries,
        paper_evidence_by_id=paper_evidence_by_id,
    )
    with open(home_readme, "w", encoding="utf-8") as f:
        f.write(content)
    return home_readme


def get_paper_sidebar_evidence(paper: Dict[str, Any]) -> str:
    return str(paper.get("canonical_evidence") or "").strip()


def write_run_daily_log(
    date_str: str,
    mode: str,
    recommend_path: str,
    recommend_exists: bool,
    deep_count: int,
    quick_count: int,
    docs_dir: str,
    day_readme: str,
) -> str:
    log_dir = os.path.join(ROOT_DIR, "archive", date_str, "logs")
    os.makedirs(log_dir, exist_ok=True)
    out_path = os.path.join(log_dir, "daily_report.json")
    payload = {
        "date": format_date_str(date_str),
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "recommend_path": recommend_path,
        "recommend_exists": bool(recommend_exists),
        "deep_count": int(deep_count),
        "quick_count": int(quick_count),
        "total_count": int(deep_count + quick_count),
        "docs_dir": docs_dir,
        "day_readme": day_readme,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return out_path


def backfill_history_day_reports(docs_dir: str) -> int:
    """
    Backfill README.md for historical date dirs when missing (home prev/next navigation).
    No LLM; builds a simple report from existing paper markdown files.
    """
    if not os.path.isdir(docs_dir):
        return 0

    created = 0
    ym_dirs = sorted(
        [d for d in os.listdir(docs_dir) if re.fullmatch(r"\d{6}", d)],
        reverse=True,
    )
    for ym in ym_dirs:
        ym_path = os.path.join(docs_dir, ym)
        if not os.path.isdir(ym_path):
            continue
        day_dirs = sorted(
            [d for d in os.listdir(ym_path) if re.fullmatch(r"\d{2}", d)],
            reverse=True,
        )
        for day in day_dirs:
            day_path = os.path.join(ym_path, day)
            if not os.path.isdir(day_path):
                continue
            readme_path = os.path.join(day_path, "README.md")
            if os.path.exists(readme_path):
                continue

            paper_files = sorted(
                [
                    fn
                    for fn in os.listdir(day_path)
                    if fn.lower().endswith(".md")
                    and fn.upper() != "README.MD"
                    and not fn.startswith("_")
                ]
            )

            date8 = f"{ym}{day}"
            date_label = format_date_str(date8)
            lines = [f"# Daily Report · {date_label}", ""]
            lines.append("- This report is a backfilled historical version (auto-generated from existing documents).")
            lines.append(f"- Paper count: {len(paper_files)}")
            lines.append("")
            lines.append("## Paper List")
            if paper_files:
                for idx, fn in enumerate(paper_files, start=1):
                    base = fn[:-3]
                    # Recover title from filename slug for clickable links
                    title_guess = re.sub(r"^[0-9]{4}\.[0-9]{5}v[0-9]-", "", base).replace("-", " ").strip()
                    title_guess = title_guess or base
                    lines.append(f"{idx}. [{title_guess}]({build_docsify_id_href(f'{ym}/{day}/{base}')})")
            else:
                lines.append("- No paper documents found in this day's directory.")
            lines.append("")

            with open(readme_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            created += 1

    return created


def _extract_md_section(md_text: str, heading: str) -> str:
    """
    Extract `## {heading}` section from Markdown until the next level-2 heading.
    """
    if not md_text:
        return ""
    marker = f"## {heading}\n"
    start = md_text.find(marker)
    if start == -1:
        return ""
    after = md_text[start + len(marker) :]
    # Next level-2 heading
    m = re.search(r"\n##\s+", after)
    return (after if not m else after[: m.start()]).strip()


def _parse_simple_yaml_list(raw: str) -> List[str]:
    items: List[str] = []
    inner = raw.strip()[1:-1].strip()
    if not inner:
        return items
    current = ""
    in_quote = False
    quote_char = ""
    escape = False
    for ch in inner:
        if escape:
            current += ch
            escape = False
            continue
        if ch == "\\":
            current += ch
            escape = True
            continue
        if ch in ("'", '"') and not in_quote:
            in_quote = True
            quote_char = ch
            current += ch
            continue
        if in_quote and ch == quote_char:
            in_quote = False
            quote_char = ""
            current += ch
            continue
        if (ch == ",") and not in_quote:
            val = current.strip()
            if val:
                items.append(val)
            current = ""
            continue
        current += ch
    last = current.strip()
    if last:
        items.append(last)

    return [re.sub(r'^["\']|["\']$', "", it).replace("\\\\", "\\").replace('\\"', '"').replace("\\'", "'") for it in items]


def _parse_front_matter(md_text: str) -> Dict[str, Any]:
    """
    Lightweight YAML front matter parser; prefer metadata fields.
    """
    text = (md_text or "").lstrip()
    if not text.startswith("---"):
        return {}
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    block = text[3:end].strip()
    meta: Dict[str, Any] = {}
    for line in block.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, raw = line.split(":", 1)
        key = key.strip()
        if not key:
            continue
        raw = raw.strip()
        if not raw:
            meta[key] = ""
            continue

        val: Any = raw
        lowered = raw.lower()
        if lowered in ("null", "~", "none"):
            val = ""
        elif raw.startswith("[") and raw.endswith("]"):
            try:
                val = json.loads(raw)
                if not isinstance(val, list):
                    raise ValueError
            except Exception:
                val = _parse_simple_yaml_list(raw)
        else:
            if (raw[0] in ('"', "'") and raw[-1] == raw[0]) or (
                raw[0] == '"' and raw[-1] == '"' and len(raw) >= 2
            ):
                raw = raw[1:-1]
            val = raw.replace("\\n", "\n").replace('\\"', '"').replace("\\'", "'").replace("\\\\", "\\")

        meta[key] = val
    return meta


def _parse_generated_md_to_meta(
    md_path: str,
    paper_id: str,
    section: str,
    selection_source: str = "",
    paper_abstract: str = "",
) -> Dict[str, Any]:
    """
    Extract exportable metadata from Step6 paper Markdown without extra LLM calls.
    """
    try:
        with open(md_path, "r", encoding="utf-8") as f:
            text = f.read()
    except Exception:
        text = ""

    lines = (text or "").splitlines()
    fm_meta: Dict[str, Any] = _parse_front_matter(text)

    legacy_meta: Dict[str, str] = {}
    for line in lines:
        m = re.match(r"^\*\*([^*]+)\*\*:\s*(.*?)(?:\s*\\\s*)?$", line.strip())
        if not m:
            continue
        k = (m.group(1) or "").strip().lower()
        legacy_meta[k] = (m.group(2) or "").strip()

    # Title: front matter > H1 > legacy meta line
    title_en = (str(fm_meta.get("title") or "").strip() if fm_meta else "")
    if not title_en:
        h1s: List[str] = []
        for line in lines:
            m = re.match(r"^#\s+(.*)$", line)
            if not m:
                break
            h1s.append((m.group(1) or "").strip())
            if len(h1s) >= 1:
                break
        if h1s:
            title_en = h1s[0]
    if not title_en:
        title_en = legacy_meta.get("title", "")

    # Tags: front matter > legacy HTML
    tags_typed: List[Dict[str, str]] = []
    raw_tags = fm_meta.get("tags") if "tags" in fm_meta else fm_meta.get("Tags")
    if isinstance(raw_tags, list):
        tag_items = [str(i).strip() for i in raw_tags if str(i).strip()]
    elif isinstance(raw_tags, str):
        candidate = raw_tags.strip()
        if candidate.startswith("[") and candidate.endswith("]"):
            tag_items = _parse_simple_yaml_list(candidate)
        else:
            tag_items = [t.strip() for t in re.split(r",|，", candidate) if t.strip()]
    else:
        tag_items = []

    if tag_items:
        for t in tag_items:
            if ":" in t:
                kind, label = t.split(":", 1)
                tags_typed.append({"kind": (kind or "paper").strip(), "label": (label or "").strip()})
            else:
                tags_typed.append({"kind": "paper", "label": t})
    else:
        # Legacy markdown HTML tag spans
        tags_html = str(fm_meta.get("tags") or legacy_meta.get("tags") or "")
        for m in re.finditer(
            r'<span\s+class="tag-label\s+([^"]+)"[^>]*>(.*?)</span>',
            tags_html,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            cls = m.group(1) or ""
            label = re.sub(r"<[^>]+>", "", (m.group(2) or "")).strip()
            if not label:
                continue
            kind = "paper"
            if "tag-green" in cls:
                kind = "keyword"
            elif "tag-blue" in cls:
                kind = "query"
            tags_typed.append({"kind": kind, "label": label})

    parsed_abstract_en = _extract_md_section(text, "Abstract")
    abstract_en = str(paper_abstract or "").strip()
    if not abstract_en:
        abstract_en = parsed_abstract_en
    if not abstract_en and "## Abstract" in text:
        # Fallback when Abstract heading exists but extracted text is empty
        abstract_en = parsed_abstract_en
    if not abstract_en:
        abstract_en = "arXiv did not provide an abstract for this paper."

    # Authors: front matter > legacy meta line
    raw_authors = fm_meta.get("authors") if "authors" in fm_meta else fm_meta.get("Authors")
    if isinstance(raw_authors, list):
        authors_line = ", ".join(str(i).strip() for i in raw_authors if str(i).strip())
    elif isinstance(raw_authors, str):
        authors_line = ", ".join(a.strip() for a in re.split(r",|，", raw_authors) if a.strip())
    else:
        authors_line = legacy_meta.get("authors", "")

    # Date/PDF/score/evidence/TLDR: front matter > legacy meta
    def _fallback_meta(*names: str) -> str:
        for name in names:
            if name in fm_meta and fm_meta[name] is not None:
                return str(fm_meta[name]).strip()
            legacy = legacy_meta.get(name.lower())
            if legacy:
                return legacy
        return ""

    date_value = _fallback_meta("date", "Date")
    pdf_value = _fallback_meta("pdf", "PDF")
    score_value = _fallback_meta("score", "Score")
    evidence_value = _fallback_meta("evidence", "Evidence")
    tldr_value = _fallback_meta("tldr", "TLDR")
    paper_source_value = str(fm_meta.get("source") or fm_meta.get("Source") or "").strip()
    src_value = str(selection_source or "").strip()
    if not src_value and "selection_source" in fm_meta:
        src_value = str(fm_meta.get("selection_source") or "").strip()

    # Tags: compact one-line string for JSON export
    tags_compact: List[str] = []
    for t in tags_typed:
        kind = (t.get("kind") or "").strip() or "paper"
        label = (t.get("label") or "").strip()
        if not label:
            continue
        tags_compact.append(f"{kind}:{label}")

    return {
        "paper_id": paper_id,
        "section": section,
        "title_en": title_en,
        "authors": authors_line,
        "date": str(date_value or "").strip(),
        "pdf": str(pdf_value or "").strip(),
        "score": str(score_value or "").strip(),
        "evidence": str(evidence_value or "").strip(),
        "tldr": str(tldr_value or "").strip(),
        "tags": ", ".join(tags_compact),
        "abstract_en": abstract_en,
        "source": paper_source_value,
        "selection_source": src_value,
    }


def write_day_meta_index_json(
    docs_dir: str,
    date_str: str,
    date_label: str | None,
    deep_list: List[Dict[str, Any]],
    quick_list: List[Dict[str, Any]],
) -> str:
    """
    Write index JSON under the docs date dir for frontend one-click download.
    """
    if RANGE_DATE_RE.match(date_str):
        target_dir = os.path.join(docs_dir, date_str)
    else:
        ym = date_str[:6]
        day = date_str[6:]
        target_dir = os.path.join(docs_dir, ym, day)
    os.makedirs(target_dir, exist_ok=True)
    out_path = os.path.join(target_dir, "papers.meta.json")

    effective_label = (date_label or "").strip() or format_date_str(date_str)

    papers: List[Dict[str, Any]] = []
    errors: List[Dict[str, str]] = []
    for section, lst in (("deep", deep_list), ("quick", quick_list)):
        for paper in lst:
            try:
                title = (paper.get("title") or "").strip()
                arxiv_id = str(paper.get("id") or paper.get("paper_id") or "").strip()
                md_path, _, pid = prepare_paper_paths(docs_dir, date_str, title, arxiv_id)
                item = _parse_generated_md_to_meta(
                    md_path,
                    pid,
                    section,
                    str(paper.get("selection_source") or ""),
                    str(paper.get("abstract") or ""),
                )
                papers.append(item)
            except Exception as e:
                errors.append(
                    {
                        "paper_id": str(paper.get("id") or paper.get("paper_id") or ""),
                        "error": str(e),
                    }
                )

    payload = {
        "label": effective_label,
        "date": format_date_str(date_str),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "count": len(papers),
        "papers": papers,
        "errors": errors,
    }

    with open(out_path, "w", encoding="utf-8") as f:
        # Download index: readable JSON pretty format
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Step 6: generate docs for deep/quick sections.")
    parser.add_argument("--date", type=str, default=TODAY_STR, help="date string YYYYMMDD.")
    parser.add_argument("--mode", type=str, default=None, help="mode for recommend file.")
    parser.add_argument("--docs-dir", type=str, default=None, help="override docs dir.")
    parser.add_argument(
        "--sidebar-date-label",
        type=str,
        default=None,
        help="Sidebar date label (e.g. 2026-01-01 ~ 2026-01-27). Defaults to single-day date.",
    )
    parser.add_argument(
        "--glance-only",
        action="store_true",
        help="Only generate/fill `## At a Glance` from title+abstract; skip PDF/Jina and deep summary.",
    )
    parser.add_argument(
        "--force-glance",
        action="store_true",
        help="Force regenerate `## At a Glance` and overwrite even if the block already exists.",
    )
    parser.add_argument(
        "--sidebar-only",
        action="store_true",
        help="Update docs/_sidebar.md only (no paper Markdown rewrite, no LLM calls).",
    )
    parser.add_argument(
        "--fix-tags-only",
        action="store_true",
        help="Fix `**Tags**` in existing articles only (remove deep/quick section labels); no LLM.",
    )
    parser.add_argument(
        "--paper-id",
        type=str,
        default=None,
        help="Single-paper mode: arXiv id (e.g. 1706.03762v1 or https://arxiv.org/abs/...).",
    )
    parser.add_argument(
        "--paper-date",
        type=str,
        default="",
        help="Single-paper mode: output date dir (YYYYMMDD); default is published date.",
    )
    parser.add_argument(
        "--paper-section",
        type=str,
        default="quick",
        help="Single-paper mode: deep or quick (default quick).",
    )
    parser.add_argument(
        "--paper-title",
        type=str,
        default=None,
        help="Single-paper mode: optional manual title override.",
    )
    parser.add_argument(
        "--docs-concurrency",
        type=int,
        default=DEFAULT_DOCS_CONCURRENCY,
        help="Concurrent per-paper generation workers for step 6.",
    )
    args = parser.parse_args()

    date_str = args.date or TODAY_STR
    mode = args.mode
    if not mode:
        config = load_config()
        setting = (config or {}).get("arxiv_paper_setting") or {}
        mode = str(setting.get("mode") or "standard").strip()
    if "," in mode:
        mode = mode.split(",", 1)[0].strip()

    docs_dir = args.docs_dir or resolve_docs_dir()
    created_reports = backfill_history_day_reports(docs_dir)
    if created_reports > 0:
        log(f"[INFO] Backfilled historical daily README files: {created_reports}")

    if args.paper_id:
        log_substep("6.p", "single-paper generation", "START")
        try:
            paper = fetch_arxiv_paper_meta(args.paper_id)
            if not str(paper.get("source") or "").strip():
                paper["source"] = "arxiv"
            if args.paper_title:
                paper["title"] = args.paper_title.strip()
            single_date = (args.paper_date or "").strip()
            if not single_date:
                single_date = (paper.get("published") or "").strip()
            if not single_date:
                single_date = TODAY_STR

            section = (args.paper_section or "quick").strip().lower()
            if section not in ("deep", "quick"):
                section = "quick"

            paper_id = str(paper.get("id") or args.paper_id).strip()
            paper["paper_id"] = paper_id
            _, paper_title = process_paper(
                paper,
                section,
                single_date,
                docs_dir,
                glance_only=args.glance_only,
                force_glance=args.force_glance,
            )
            log(f"[OK] Single paper generated: {paper_title} ({paper_id}), date={single_date}, section={section}")
            log_substep("6.p", "single-paper generation", "END")
            return
        except Exception as e:
            log(f"[ERROR] Single-paper generation failed: {e}")
            log_substep("6.p", "single-paper generation", "END")
            return

    archive_dir = os.path.join(ROOT_DIR, "archive", date_str, "recommend")
    recommend_path = os.path.join(archive_dir, f"arxiv_papers_{date_str}.{mode}.json")
    recommend_exists = os.path.exists(recommend_path)
    if not recommend_exists:
        log(f"[WARN] Recommend file missing (no new papers today may be expected): {recommend_path}. Writing empty report and updating home.")

    log_substep("6.1", "load recommend results", "START")
    payload = {}
    try:
        if recommend_exists:
            with open(recommend_path, "r", encoding="utf-8") as f:
                payload = json.load(f)
    finally:
        log_substep("6.1", "load recommend results", "END")
    deep_list = payload.get("deep_dive") or []
    quick_list = payload.get("quick_skim") or []

    def _paper_score(p: dict) -> float:
        try:
            return float(p.get("llm_score", 0) or 0)
        except Exception:
            return 0.0

    def _paper_id(p: dict) -> str:
        return str(p.get("id") or p.get("paper_id") or "").strip()

    # Sidebar order: score desc, then stable id tie-break
    deep_list = sorted(deep_list, key=lambda p: (-_paper_score(p), _paper_id(p)))
    quick_list = sorted(quick_list, key=lambda p: (-_paper_score(p), _paper_id(p)))

    if args.fix_tags_only:
        changed_files = 0
        total_files = 0
        for section, lst in (("deep", deep_list), ("quick", quick_list)):
            for paper in lst:
                title = (paper.get("title") or "").strip()
                arxiv_id = str(paper.get("id") or paper.get("paper_id") or "").strip()
                md_path, _, _ = prepare_paper_paths(docs_dir, date_str, title, arxiv_id)
                if not os.path.exists(md_path):
                    continue
                total_files += 1
                try:
                    with open(md_path, "r", encoding="utf-8") as f:
                        content = f.read()
                except Exception:
                    continue
                fixed, changed = normalize_meta_tags_line(content)
                if not changed:
                    continue
                try:
                    with open(md_path, "w", encoding="utf-8") as f:
                        f.write(fixed + ("\n" if not fixed.endswith("\n") else ""))
                    changed_files += 1
                except Exception:
                    continue
        log(f"[OK] fix-tags-only: scanned={total_files}, updated={changed_files}")
        return

    deep_entries: List[Tuple[str, str, List[Tuple[str, str]]]] = []
    quick_entries: List[Tuple[str, str, List[Tuple[str, str]]]] = []
    docs_concurrency = max(1, int(args.docs_concurrency))

    def _process_section(
        section: str,
        papers: List[Dict[str, Any]],
        paper_evidence_by_id: Dict[str, str],
    ) -> List[Tuple[str, str, List[Tuple[str, str]]]]:
        if not papers:
            return []
        max_workers = max(1, docs_concurrency)
        futures: Dict[Any, Tuple[int, Dict[str, Any]]] = {}
        results: List[Tuple[int, Tuple[str, str, List[Tuple[str, str]]]]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for index, paper in enumerate(papers):
                future = executor.submit(
                    process_paper,
                    paper,
                    section,
                    date_str,
                    docs_dir,
                    args.glance_only,
                    args.force_glance,
                )
                futures[future] = (index, paper)

            for future in as_completed(futures):
                index, paper = futures[future]
                try:
                    pid, title = future.result()
                except Exception as e:
                    log(f"[WARN] Failed to generate {section} paper: {e}")
                    continue
                paper_evidence_by_id[str((pid or "").strip())] = get_paper_sidebar_evidence(paper)
                section_tags = extract_sidebar_tags(paper)
                results.append((index, (pid, title, section_tags)))

        results.sort(key=lambda item: item[0])
        return [v for _, v in results]

    sidebar_evidence_by_id: Dict[str, str] = {}

    if args.sidebar_only:
        log_substep("6.2", "skip article generation (sidebar only)", "SKIP")
        for paper in deep_list:
            title = (paper.get("title") or "").strip()
            arxiv_id = str(paper.get("id") or paper.get("paper_id") or "").strip()
            _, _, pid = prepare_paper_paths(docs_dir, date_str, title, arxiv_id)
            sidebar_evidence_by_id[str(pid).strip()] = get_paper_sidebar_evidence(paper)
            deep_entries.append((pid, title, extract_sidebar_tags(paper)))

        for paper in quick_list:
            title = (paper.get("title") or "").strip()
            arxiv_id = str(paper.get("id") or paper.get("paper_id") or "").strip()
            _, _, pid = prepare_paper_paths(docs_dir, date_str, title, arxiv_id)
            sidebar_evidence_by_id[str(pid).strip()] = get_paper_sidebar_evidence(paper)
            quick_entries.append((pid, title, extract_sidebar_tags(paper)))
        log_substep("6.3", "skip article generation (sidebar only)", "SKIP")
    else:
        log_substep("6.2", "generate deep-dive articles", "START")
        deep_entries = _process_section("deep", deep_list, sidebar_evidence_by_id)
        log_substep("6.2", "generate deep-dive articles", "END")

        log_substep("6.3", "generate quick-skim articles", "START")
        quick_entries = _process_section("quick", quick_list, sidebar_evidence_by_id)
        log_substep("6.3", "generate quick-skim articles", "END")

    log_substep("6.4", "write daily report and sync home README", "START")
    run_generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    day_readme = write_day_report_readme(
        docs_dir=docs_dir,
        date_str=date_str,
        date_label=args.sidebar_date_label,
        deep_entries=deep_entries,
        quick_entries=quick_entries,
        recommend_exists=recommend_exists,
    )
    home_readme = sync_home_readme_from_day_report(
        docs_dir=docs_dir,
        date_str=date_str,
        date_label=args.sidebar_date_label,
        generated_at=run_generated_at,
        recommend_exists=recommend_exists,
        deep_entries=deep_entries,
        quick_entries=quick_entries,
        paper_evidence_by_id=sidebar_evidence_by_id,
    )
    log(f"[OK] day report saved: {day_readme}")
    log(f"[OK] home README synced: {home_readme}")
    log_substep("6.4", "write daily report and sync home README", "END")

    sidebar_path = os.path.join(docs_dir, "_sidebar.md")
    if deep_entries or quick_entries:
        log_substep("6.5", "update sidebar", "START")
        update_sidebar(
            sidebar_path,
            date_str,
            deep_entries,
            quick_entries,
            sidebar_evidence_by_id,
            date_label=args.sidebar_date_label,
        )
        log_substep("6.5", "update sidebar", "END")
    else:
        log_substep("6.5", "update sidebar", "SKIP")
        log("[INFO] No recommended papers; skipping sidebar date entry.")

    log_substep("6.6", "write downloadable metadata index (JSON)", "START")
    try:
        out_path = write_day_meta_index_json(
            docs_dir,
            date_str,
            args.sidebar_date_label,
            deep_list,
            quick_list,
        )
        log(f"[OK] meta index saved: {out_path}")
    except Exception as e:
        log(f"[WARN] Failed to write metadata index: {e}")
    log_substep("6.6", "write downloadable metadata index (JSON)", "END")

    log_substep("6.7", "write run log (daily report)", "START")
    run_log = write_run_daily_log(
        date_str=date_str,
        mode=mode,
        recommend_path=recommend_path,
        recommend_exists=recommend_exists,
        deep_count=len(deep_entries),
        quick_count=len(quick_entries),
        docs_dir=docs_dir,
        day_readme=day_readme,
    )
    log(f"[OK] daily report log saved: {run_log}")
    log_substep("6.7", "write run log (daily report)", "END")

    log(f"[OK] docs updated: {docs_dir}")


if __name__ == "__main__":
    main()
