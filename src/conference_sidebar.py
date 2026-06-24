#!/usr/bin/env python
"""将会议检索结果写入 docs/_sidebar.md 的 Conference Papers 分组。"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import html
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SIDEBAR_PATH = ROOT_DIR / "docs" / "_sidebar.md"
DEFAULT_DOCS_DIR = ROOT_DIR / "docs"
CONFERENCE_HEADING = "* Conference Papers\n"
CONFERENCE_DISPLAY_MIN_SCORE = 4.0
CONFERENCE_DEEP_MIN_SCORE = 4.0
_GENERATE_DOCS_MODULE = None


def norm_text(value: Any) -> str:
    return str(value or "").strip()


def parse_conference_result_name(path: Path) -> Tuple[str, str]:
    name = path.name
    match = re.match(r"^conference-([a-z0-9-]+?)-([0-9]{4}(?:-[0-9]{4})*)\.supabase\.(?:llm|rerank|rrf)\.json$", name)
    if not match:
        raise ValueError(f"无法从会议结果文件名解析会议和年份：{path}")
    conference = match.group(1).upper()
    years = match.group(2).replace("-", ",")
    return conference, years


def build_conference_marker(conference: str, years: str) -> str:
    key = f"{norm_text(conference).lower()}-{norm_text(years).replace(',', '-')}"
    key = re.sub(r"[^a-z0-9-]+", "-", key).strip("-")
    return f"<!--dpr-conference:{key}-->"


def build_conference_label(conference: str, years: str) -> str:
    year_label = ", ".join(part.strip() for part in norm_text(years).split(",") if part.strip())
    return f"{norm_text(conference).upper()} {year_label}".strip()


def build_conference_key(conference: str, years: str) -> str:
    key = f"{norm_text(conference).lower()}-{norm_text(years).replace(',', '-')}"
    return re.sub(r"[^a-z0-9-]+", "-", key).strip("-") or "conference"


def build_topic_key(kind: str, label: str) -> str:
    raw = f"{norm_text(kind).lower() or 'query'}-{norm_text(label).lower() or 'general'}"
    key = re.sub(r"[^a-z0-9-]+", "-", raw).strip("-")
    if key:
        return key
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:8]
    return f"topic-{digest}"


def build_conference_topic_marker(conference: str, years: str, kind: str, label: str) -> str:
    return f"<!--dpr-conference-topic:{build_conference_key(conference, years)}:{build_topic_key(kind, label)}-->"


def topic_from_ranked_item(item: Dict[str, Any]) -> Tuple[str, str]:
    matched_tag = norm_text(item.get("matched_query_tag"))
    if matched_tag:
        kind, label = normalize_sidebar_tag(matched_tag)
        if label:
            return kind or "query", label
    return "query", "General"


def topic_from_profile_tag(profile_tag: str) -> Tuple[str, str]:
    text = norm_text(profile_tag)
    if not text:
        return "query", "General"
    kind, label = normalize_sidebar_tag(text)
    return kind or "query", label or text


def slugify(value: str) -> str:
    text = norm_text(value).lower()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^a-z0-9-]+", "", text)
    return text.strip("-") or "paper"


def yaml_escape_value(value: Any) -> str:
    text = norm_text(value)
    if not text:
        return '""'
    if any(ch in text for ch in [":", "#", '"', "'", "\n", "[", "]", "{", "}", ",", "&", "*", "!", "|", ">", "%", "@", "`"]):
        return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
    return text


def load_generate_docs_module():
    global _GENERATE_DOCS_MODULE
    if _GENERATE_DOCS_MODULE is not None:
        return _GENERATE_DOCS_MODULE

    src_dir = ROOT_DIR / "src"
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    module_path = src_dir / "6.generate_docs.py"
    spec = importlib.util.spec_from_file_location("dpr_generate_docs_for_conference", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载日常页生成模块：{module_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _GENERATE_DOCS_MODULE = module
    return module


def parse_front_matter(text: str) -> Dict[str, str]:
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    if not raw.startswith("---\n"):
        return {}
    end = raw.find("\n---", 4)
    if end < 0:
        return {}
    out: Dict[str, str] = {}
    for line in raw[4:end].splitlines():
        key, sep, value = line.partition(":")
        if not sep:
            continue
        out[key.strip()] = value.strip()
    return out


def parse_json_front_matter_value(value: Any) -> Any:
    text = norm_text(value)
    if not text:
        return None
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1].replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
    try:
        return json.loads(text)
    except Exception:
        return None


def normalize_sidebar_tag(raw_tag: str) -> Tuple[str, str]:
    text = norm_text(raw_tag)
    if not text:
        return "", ""
    kind, sep, label = text.partition(":")
    if not sep:
        return "query", text
    kind = norm_text(kind).lower() or "query"
    if kind == "keyword":
        kind = "query"
    if kind not in {"keyword", "query", "paper", "other"}:
        kind = "other"
    label = norm_text(label)
    if kind == "query" and label.endswith(":composite"):
        label = label[: -len(":composite")].strip()
    return kind, label


def build_conference_paper_route(paper: Dict[str, Any], conference: str, years: str) -> str:
    paper_id = norm_text(paper.get("id")) or "paper"
    title_slug = slugify(norm_text(paper.get("title")) or paper_id)
    basename = f"{slugify(paper_id)}-{title_slug}"
    return f"conference/{build_conference_key(conference, years)}/{basename}"


def get_evidence(ranked_item: Dict[str, Any]) -> str:
    return norm_text(
        ranked_item.get("canonical_evidence")
        or ranked_item.get("evidence_cn")
        or ranked_item.get("evidence_en")
        or ranked_item.get("tldr_cn")
        or ranked_item.get("tldr_en")
    )


def get_tldr(ranked_item: Dict[str, Any]) -> str:
    return norm_text(ranked_item.get("tldr_cn") or ranked_item.get("tldr_en"))


def ensure_sentence(value: str) -> str:
    text = re.sub(r"\s+", " ", norm_text(value)).strip()
    if not text:
        return ""
    if text[-1] in ".。！？!?":
        return text
    return text + "。"


def first_sentence(value: str) -> str:
    text = re.sub(r"\s+", " ", norm_text(value)).strip()
    if not text:
        return ""
    match = re.search(r"(.+?[。！？!?]|.+?\.(?:\s|$))", text)
    return norm_text(match.group(1)) if match else text[:180].strip()


def build_glance_fields(paper: Dict[str, Any], ranked_item: Dict[str, Any]) -> Dict[str, str]:
    title = norm_text(paper.get("title")) or "该论文"
    evidence = get_evidence(ranked_item)
    tldr = get_tldr(ranked_item) or evidence
    query_text = norm_text(ranked_item.get("matched_query_text"))
    return {
        "tldr": ensure_sentence(tldr or f"{title} 是一篇会议检索命中的相关论文"),
        "motivation": ensure_sentence(
            norm_text(ranked_item.get("motivation_cn")) or evidence or "本文关注会议检索需求中的相关研究问题"
        ),
        "method": ensure_sentence(
            norm_text(ranked_item.get("method_cn")) or "方法细节请参考摘要与 OpenReview 原文"
        ),
        "result": ensure_sentence(
            norm_text(ranked_item.get("result_cn")) or tldr or evidence or "结果与实验结论请参考摘要与原文"
        ),
        "conclusion": ensure_sentence(
            norm_text(ranked_item.get("conclusion_cn"))
            or (f"该论文与检索需求“{query_text}”相关" if query_text else "该论文与当前会议检索需求相关")
        ),
    }


def build_conference_summary_lines(
    paper: Dict[str, Any],
    ranked_item: Dict[str, Any],
    link: str,
) -> List[str]:
    deep_summary = norm_text(ranked_item.get("_deep_summary"))
    if deep_summary:
        return ["---", "", "## 论文详细总结（自动生成）", "", deep_summary.rstrip(), ""]

    evidence = get_evidence(ranked_item)
    tldr = get_tldr(ranked_item)
    query_text = norm_text(ranked_item.get("matched_query_text"))
    abstract = norm_text(paper.get("abstract"))
    source = norm_text(paper.get("source"))

    lines = [
        "---",
        "",
        "## 论文详细总结（自动生成）",
        "",
        "### 1. 检索相关性",
        ensure_sentence(evidence or "该论文由会议检索链路召回，具体相关性可结合检索需求和原文进一步判断"),
        "",
        "### 2. 核心内容",
        ensure_sentence(tldr or first_sentence(abstract) or "核心内容请参考摘要与 OpenReview 原文"),
        "",
        "### 3. 对应检索需求",
        ensure_sentence(query_text or "当前结果未记录具体命中的检索需求"),
        "",
        "### 4. 来源与原文",
    ]
    if source:
        lines.append(f"- Source：{source}")
    if link:
        lines.append(f"- OpenReview：[{link}]({link})")
    if not source and not link:
        lines.append("- 来源信息未记录。")
    lines.append("")
    return lines


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def score_from_ranked_item(item: Dict[str, Any]) -> float:
    for key in ("score", "star_rating"):
        try:
            return float(item.get(key))
        except Exception:
            continue
    return 0.0


def resolve_conference_pdf_url(paper: Dict[str, Any]) -> str:
    pdf_url = norm_text(paper.get("pdf_url"))
    if pdf_url:
        return pdf_url
    link = norm_text(paper.get("link"))
    if not link:
        return ""
    if re.search(r"\.pdf(?:$|[?#])", link, flags=re.IGNORECASE) or "/pdf?" in link:
        return link
    match = re.search(r"[?&]id=([^&#]+)", link)
    if "openreview.net/forum" in link and match:
        return f"https://openreview.net/pdf?id={match.group(1)}"
    # CVF (CVPR/WACV): .../html/XXX_paper.html → .../papers/XXX_paper.pdf
    if "openaccess.thecvf.com" in link and "/html/" in link:
        return link.replace("/html/", "/papers/").replace("_paper.html", "_paper.pdf")
    # ECVA (ECCV): .../html/3012_ECCV_2024_paper.php → .../papers/03012.pdf (zero-padded to 5 digits)
    if "ecva.net" in link and "/html/" in link:
        m = re.search(r"/html/(\d+)_", link)
        if m:
            base = link[:link.index("/html/")]
            padded = m.group(1).zfill(5)
            return f"{base}/papers/{padded}.pdf"
        return link.replace("/html/", "/pdf/").replace("_paper.php", "_paper.pdf")
    # ACL Anthology: https://aclanthology.org/2025.findings-emnlp.1018/ → .../2025.findings-emnlp.1018.pdf
    if "aclanthology.org" in link:
        clean = link.rstrip("/")
        if not clean.endswith(".pdf"):
            return clean + ".pdf"
        return clean
    return link


def source_key_for_figures(paper: Dict[str, Any]) -> str:
    paper_id = norm_text(paper.get("id"))
    source = norm_text(paper.get("source")).lower()
    if paper_id.startswith("openreview-") or "openreview" in source or "icml-" in source or "neurips-" in source or "iclr-" in source:
        return "openreview"
    if "biorxiv" in source:
        return "biorxiv"
    if "arxiv" in source:
        return "arxiv"
    return slugify(source) or "conference"


def ensure_conference_figures(
    paper: Dict[str, Any],
    *,
    docs_dir: Path,
    pdf_url: str,
) -> List[Dict[str, Any]]:
    figures, _tables = ensure_conference_media(paper, docs_dir=docs_dir, pdf_url=pdf_url)
    return figures


def ensure_conference_media(
    paper: Dict[str, Any],
    *,
    docs_dir: Path,
    pdf_url: str,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    if not pdf_url:
        return [], []
    asset_key = norm_text(paper.get("id")) or slugify(norm_text(paper.get("title")))
    try:
        from paper_figures import ensure_paper_media

        return ensure_paper_media(
            pdf_url=pdf_url,
            docs_dir=str(docs_dir),
            source_key=source_key_for_figures(paper),
            asset_key=asset_key,
        )
    except Exception as exc:
        print(f"[WARN] 会议论文图表提取失败：{asset_key}: {exc}", flush=True)
        return [], []


def is_generated_deep_summary(text: str) -> bool:
    summary = norm_text(text)
    if not summary:
        return False
    if "### 1. 检索相关性" in summary[:500] and "### 4. 来源与原文" in summary[:1500]:
        return False
    return "（完）" in summary or "## " in summary or "### " in summary or len(summary) > 600


def collect_ranked_ids(data: Dict[str, Any], limit: int, min_score: float = CONFERENCE_DISPLAY_MIN_SCORE) -> List[Dict[str, Any]]:
    papers = data.get("papers") if isinstance(data.get("papers"), list) else []
    paper_ids = [norm_text(p.get("id")) for p in papers if isinstance(p, dict) and norm_text(p.get("id"))]
    llm_ranked = data.get("llm_ranked") if isinstance(data.get("llm_ranked"), list) else []
    ranked: List[Dict[str, Any]] = []
    seen = set()

    for item in llm_ranked:
        if not isinstance(item, dict):
            continue
        paper_id = norm_text(item.get("paper_id"))
        if not paper_id or paper_id in seen:
            continue
        seen.add(paper_id)
        ranked.append(item)

    if not ranked:
        queries = data.get("queries") if isinstance(data.get("queries"), list) else []
        merged: Dict[str, Dict[str, Any]] = {}
        for query in queries:
            if not isinstance(query, dict):
                continue
            for item in query.get("ranked") or []:
                if not isinstance(item, dict):
                    continue
                paper_id = norm_text(item.get("paper_id"))
                if not paper_id:
                    continue
                current = merged.get(paper_id)
                if current is None or score_from_ranked_item(item) > score_from_ranked_item(current):
                    merged[paper_id] = item
        ranked = sorted(merged.values(), key=score_from_ranked_item, reverse=True)

    if not ranked:
        ranked = [{"paper_id": paper_id} for paper_id in paper_ids]

    if min_score >= 0:
        ranked = [item for item in ranked if score_from_ranked_item(item) >= min_score]
    if limit > 0:
        ranked = ranked[:limit]
    return ranked


def build_sidebar_payload(
    paper: Dict[str, Any],
    ranked_item: Dict[str, Any],
    conference: str,
    years: str,
) -> str:
    title = norm_text(paper.get("title")) or norm_text(ranked_item.get("paper_id")) or "Untitled"
    link = norm_text(paper.get("link")) or "#"
    score = ranked_item.get("score", ranked_item.get("star_rating", "-"))
    try:
        score_text = f"{float(score):.1f}"
    except Exception:
        score_text = norm_text(score) or "-"
    tags: List[Dict[str, str]] = []
    matched_tag = norm_text(ranked_item.get("matched_query_tag"))
    if matched_tag:
        kind, label = normalize_sidebar_tag(matched_tag)
        if label:
            tags.append({"kind": kind or "query", "label": label})

    payload = {
        "title": title,
        "link": link,
        "score": score_text,
        "selection_source": "conference_retrieval",
        "tags": tags,
    }
    evidence = get_evidence(ranked_item)
    if evidence:
        payload["evidence"] = evidence
    return html.escape(json.dumps(payload, ensure_ascii=False), quote=True)


def build_conference_markdown(
    paper: Dict[str, Any],
    ranked_item: Dict[str, Any],
    conference: str,
    years: str,
) -> str:
    title = norm_text(paper.get("title")) or norm_text(ranked_item.get("paper_id")) or "Untitled"
    title_zh = norm_text(ranked_item.get("title_zh") or paper.get("title_zh"))
    authors = paper.get("authors") if isinstance(paper.get("authors"), list) else []
    authors_text = ", ".join(norm_text(item) for item in authors if norm_text(item)) or "Unknown"
    published = norm_text(paper.get("published"))[:10] or "Unknown"
    source = norm_text(paper.get("source"))
    link = norm_text(paper.get("link"))
    pdf_url = resolve_conference_pdf_url(paper)
    abstract = norm_text(paper.get("abstract")) or "No abstract is available."
    evidence = get_evidence(ranked_item)
    tldr = get_tldr(ranked_item)
    glance = build_glance_fields(paper, ranked_item)
    score = ranked_item.get("score", ranked_item.get("star_rating", ""))
    try:
        score_text = f"{float(score):.1f}"
    except Exception:
        score_text = norm_text(score)

    tags: List[str] = []
    matched_tag = norm_text(ranked_item.get("matched_query_tag"))
    if matched_tag:
        kind, label = normalize_sidebar_tag(matched_tag)
        if label:
            tags.append(f"{kind}:{label}")

    lines = ["---"]
    lines.append(f"title: {yaml_escape_value(title)}")
    if title_zh:
        lines.append(f"title_zh: {yaml_escape_value(title_zh)}")
    lines.append(f"authors: {yaml_escape_value(authors_text)}")
    lines.append(f"date: {yaml_escape_value(published)}")
    if pdf_url:
        lines.append(f"pdf: {yaml_escape_value(pdf_url)}")
    if tags:
        lines.append(f"tags: [{', '.join(yaml_escape_value(tag) for tag in tags)}]")
    if score_text:
        lines.append(f"score: {score_text}")
    if evidence:
        lines.append(f"evidence: {yaml_escape_value(evidence)}")
    if tldr:
        lines.append(f"tldr: {yaml_escape_value(tldr)}")
    if source:
        lines.append(f"source: {yaml_escape_value(source)}")
    lines.append("selection_source: conference_retrieval")
    figure_assets = paper.get("_figure_assets") if isinstance(paper.get("_figure_assets"), list) else []
    table_assets = paper.get("_table_assets") if isinstance(paper.get("_table_assets"), list) else []
    if figure_assets:
        lines.append(f"figures_json: {yaml_escape_value(json.dumps(figure_assets, ensure_ascii=False))}")
    if table_assets:
        lines.append(f"tables_json: {yaml_escape_value(json.dumps(table_assets, ensure_ascii=False))}")
    lines.append(f"motivation: {yaml_escape_value(glance['motivation'])}")
    lines.append(f"method: {yaml_escape_value(glance['method'])}")
    lines.append(f"result: {yaml_escape_value(glance['result'])}")
    lines.append(f"conclusion: {yaml_escape_value(glance['conclusion'])}")
    lines.append("---")
    lines.append("")
    lines.append("## Abstract")
    lines.append(abstract)
    lines.append("")
    lines.extend(build_conference_summary_lines(paper, ranked_item, link))
    return "\n".join(lines)


def write_conference_docs(
    docs_dir: Path,
    papers: Dict[str, Dict[str, Any]],
    ranked: List[Dict[str, Any]],
    conference: str,
    years: str,
    *,
    deep_min_score: float = CONFERENCE_DEEP_MIN_SCORE,
) -> Dict[str, str]:
    _ = deep_min_score  # 兼容旧参数；会议链路当前对所有展示论文生成精读与图表。
    route_by_id: Dict[str, str] = {}
    for item in ranked:
        paper_id = norm_text(item.get("paper_id"))
        paper = papers.get(paper_id)
        if not paper:
            continue
        route = build_conference_paper_route(paper, conference, years)
        md_path = docs_dir / f"{route}.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        enrich_conference_paper_for_deep_read(
            paper,
            item,
            md_path=md_path,
            docs_dir=docs_dir,
            conference=conference,
            years=years,
        )
        md_path.write_text(build_conference_markdown(paper, item, conference, years), encoding="utf-8")
        route_by_id[paper_id] = route
    return route_by_id


def enrich_conference_paper_for_deep_read(
    paper: Dict[str, Any],
    ranked_item: Dict[str, Any],
    *,
    md_path: Path,
    docs_dir: Path,
    conference: str,
    years: str,
) -> None:
    pdf_url = resolve_conference_pdf_url(paper)
    if not pdf_url:
        return

    existing = md_path.read_text(encoding="utf-8") if md_path.exists() else ""
    existing_meta = parse_front_matter(existing)
    cached_figures = parse_json_front_matter_value(existing_meta.get("figures_json"))
    if isinstance(cached_figures, list) and cached_figures:
        paper["_figure_assets"] = cached_figures
    cached_tables = parse_json_front_matter_value(existing_meta.get("tables_json"))
    if isinstance(cached_tables, list) and cached_tables:
        paper["_table_assets"] = cached_tables

    if not norm_text(existing_meta.get("figures_json")) or not norm_text(existing_meta.get("tables_json")):
        figures, tables = ensure_conference_media(paper, docs_dir=docs_dir, pdf_url=pdf_url)
        if figures:
            paper["_figure_assets"] = figures
        if tables:
            paper["_table_assets"] = tables

    existing_summary = ""
    if existing:
        try:
            generate_docs = load_generate_docs_module()
            existing_summary = generate_docs.extract_section_tail(existing, "论文详细总结（自动生成）")
        except Exception:
            existing_summary = ""
    if existing_summary:
        if is_generated_deep_summary(existing_summary):
            ranked_item["_deep_summary"] = existing_summary
            return
        ranked_item.pop("_deep_summary", None)

    base_md = build_conference_markdown(paper, ranked_item, conference, years)
    md_path.write_text(base_md, encoding="utf-8")
    txt_path = md_path.with_suffix(".txt")
    try:
        generate_docs = load_generate_docs_module()
        generate_docs.ensure_text_content(pdf_url, str(txt_path))
        summary = generate_docs.generate_deep_summary(str(md_path), str(txt_path))
        if summary:
            ranked_item["_deep_summary"] = summary
    except Exception as exc:
        print(f"[WARN] 会议论文精读生成失败：{paper.get('id') or md_path.stem}: {exc}", flush=True)


def cleanup_conference_outputs(
    docs_dir: Path,
    papers: Dict[str, Dict[str, Any]],
    kept_ranked: List[Dict[str, Any]],
    conference: str,
    years: str,
) -> None:
    # 会议检索会被不同 profile/tag 反复触发。这里不能删除整个 conference/year
    # 目录，否则新词条会覆盖旧词条已经生成的正文页和图表资源。
    return None


def group_ranked_by_topic(ranked: List[Dict[str, Any]]) -> List[Tuple[str, str, List[Dict[str, Any]]]]:
    grouped: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    order: List[Tuple[str, str]] = []
    for item in ranked:
        kind, label = topic_from_ranked_item(item)
        key = (kind, label)
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(item)
    return [(kind, label, grouped[(kind, label)]) for kind, label in order]


def build_conference_block(
    result_path: Path,
    docs_dir: Path,
    limit: int = 80,
    deep_min_score: float = CONFERENCE_DEEP_MIN_SCORE,
    display_min_score: float = CONFERENCE_DISPLAY_MIN_SCORE,
) -> List[str]:
    data = load_json(result_path)
    conference, years = parse_conference_result_name(result_path)
    marker = build_conference_marker(conference, years)
    label = build_conference_label(conference, years)
    papers = {
        norm_text(item.get("id")): item
        for item in (data.get("papers") if isinstance(data.get("papers"), list) else [])
        if isinstance(item, dict) and norm_text(item.get("id"))
    }
    ranked = collect_ranked_ids(data, limit, min_score=display_min_score)
    route_by_id = write_conference_docs(
        docs_dir,
        papers,
        ranked,
        conference,
        years,
        deep_min_score=deep_min_score,
    )

    lines = [f"  * {label} {marker}\n"]
    for kind, topic_label, topic_ranked in group_ranked_by_topic(ranked):
        topic_marker = build_conference_topic_marker(conference, years, kind, topic_label)
        lines.append(f"    * {html.escape(topic_label)} {topic_marker}\n")
        for item in topic_ranked:
            paper_id = norm_text(item.get("paper_id"))
            paper = papers.get(paper_id)
            if not paper:
                continue
            title = norm_text(paper.get("title")) or paper_id
            route = route_by_id.get(paper_id) or build_conference_paper_route(paper, conference, years)
            href = f"#/{route}"
            payload = build_sidebar_payload(paper, item, conference, years)
            lines.append(
                "      * "
                f'<a class="dpr-sidebar-item-link dpr-sidebar-item-structured" href="{html.escape(href, quote=True)}" '
                f'data-sidebar-item="{payload}">{html.escape(title)}</a>\n'
            )
    return lines


def find_conference_heading(lines: List[str]) -> int:
    for idx, line in enumerate(lines):
        if line.strip() == "* Conference Papers":
            return idx
    return -1


def remove_existing_conference_block(lines: List[str], marker: str) -> None:
    heading_idx = find_conference_heading(lines)
    if heading_idx < 0:
        return
    block_idx = -1
    for idx in range(heading_idx + 1, len(lines)):
        if lines[idx].startswith("* "):
            break
        if marker in lines[idx]:
            block_idx = idx
            break
    if block_idx < 0:
        return
    end = block_idx + 1
    while end < len(lines):
        if lines[end].startswith("  * ") and not lines[end].startswith("    * "):
            break
        if lines[end].startswith("* "):
            break
        end += 1
    del lines[block_idx:end]


def find_conference_block(lines: List[str], marker: str) -> Tuple[int, int]:
    heading_idx = find_conference_heading(lines)
    if heading_idx < 0:
        return -1, -1
    block_idx = -1
    for idx in range(heading_idx + 1, len(lines)):
        if lines[idx].startswith("* "):
            break
        if marker in lines[idx]:
            block_idx = idx
            break
    if block_idx < 0:
        return -1, -1
    end = block_idx + 1
    while end < len(lines):
        if lines[end].startswith("  * ") and not lines[end].startswith("    * "):
            break
        if lines[end].startswith("* "):
            break
        end += 1
    return block_idx, end


def extract_conference_paper_lines(lines: List[str], marker: str) -> List[str]:
    block_idx, block_end = find_conference_block(lines, marker)
    if block_idx < 0:
        return []

    paper_lines: List[str] = []
    for line in lines[block_idx + 1:block_end]:
        if "dpr-sidebar-item-link" not in line:
            continue
        paper_lines.append(line)
    return paper_lines


def sidebar_line_keys(line: str) -> List[str]:
    href_re = re.compile(r'href="([^"]+)"')
    link_re = re.compile(r'&quot;link&quot;:\s*&quot;([^&]+)&quot;')
    keys: List[str] = []
    href_match = href_re.search(line)
    if href_match:
        keys.append(f"href:{href_match.group(1)}")
    link_match = link_re.search(line)
    if link_match:
        keys.append(f"link:{html.unescape(link_match.group(1))}")
    return keys


def infer_topic_from_sidebar_line(line: str) -> Tuple[str, str]:
    match = re.search(r'data-sidebar-item="([^"]+)"', line)
    if match:
        try:
            payload = json.loads(html.unescape(match.group(1)))
            tags = payload.get("tags") if isinstance(payload, dict) else []
            if isinstance(tags, list) and tags:
                tag = tags[0]
                if isinstance(tag, dict):
                    kind = norm_text(tag.get("kind")) or "query"
                    label = norm_text(tag.get("label")) or "General"
                    return kind, label
        except Exception:
            pass
    return "query", "General"


def topic_line_for(conference: str, years: str, kind: str, label: str) -> str:
    safe_label = html.escape(norm_text(label) or "General")
    return f"    * {safe_label} {build_conference_topic_marker(conference, years, kind, label)}\n"


def normalize_conference_paper_line(line: str) -> str:
    return re.sub(r"^\s*\*\s+", "      * ", line)


def merge_conference_paper_lines(
    new_block: List[str],
    existing_paper_lines: List[str],
    conference: str,
    years: str,
) -> List[str]:
    if not new_block:
        return []

    header = new_block[0]
    topic_order: List[str] = []
    topic_lines: Dict[str, str] = {}
    topic_papers: Dict[str, List[str]] = {}
    seen_keys = set()
    current_topic_key = ""

    def add_topic(kind: str, label: str, line: str = "") -> str:
        key = build_conference_topic_marker(conference, years, kind, label)
        if key not in topic_lines:
            topic_lines[key] = line or topic_line_for(conference, years, kind, label)
            topic_papers[key] = []
            topic_order.append(key)
        return key

    def add_paper(topic_key: str, line: str) -> None:
        keys = sidebar_line_keys(line)
        if keys and any(key in seen_keys for key in keys):
            return
        seen_keys.update(keys)
        topic_papers.setdefault(topic_key, []).append(normalize_conference_paper_line(line))

    for line in new_block:
        if line == header:
            continue
        if "<!--dpr-conference-topic:" in line:
            marker_match = re.search(r"(<!--dpr-conference-topic:[^>]+-->)", line)
            current_topic_key = marker_match.group(1) if marker_match else ""
            if current_topic_key and current_topic_key not in topic_lines:
                topic_lines[current_topic_key] = line
                topic_papers[current_topic_key] = []
                topic_order.append(current_topic_key)
            continue
        if "dpr-sidebar-item-link" in line:
            if not current_topic_key:
                kind, label = infer_topic_from_sidebar_line(line)
                current_topic_key = add_topic(kind, label)
            add_paper(current_topic_key, line)

    for line in existing_paper_lines:
        kind, label = infer_topic_from_sidebar_line(line)
        topic_key = add_topic(kind, label)
        add_paper(topic_key, line)

    merged: List[str] = [header]
    for topic_key in topic_order:
        papers = topic_papers.get(topic_key) or []
        if not papers:
            continue
        merged.append(topic_lines[topic_key])
        merged.extend(papers)
    return merged


def ensure_conference_heading(lines: List[str]) -> int:
    heading_idx = find_conference_heading(lines)
    if heading_idx >= 0:
        return heading_idx

    daily_idx = -1
    for idx, line in enumerate(lines):
        if line.strip() == "* Daily Papers":
            daily_idx = idx
            break
    insert_idx = daily_idx if daily_idx >= 0 else len(lines)
    if insert_idx > 0 and lines[insert_idx - 1].strip():
        lines.insert(insert_idx, "\n")
        insert_idx += 1
    lines.insert(insert_idx, CONFERENCE_HEADING)
    return insert_idx


def _conference_block_sort_key(block: List[str]) -> Tuple[str, int, int, int, str]:
    header = block[0] if block else ""
    marker_match = re.search(r"<!--dpr-conference:([^>]+)-->", header)
    marker = marker_match.group(1) if marker_match else ""
    label = re.sub(r"<!--.*?-->", "", header)
    label = re.sub(r"^\s*\*\s*", "", label).strip()
    conf = marker.split("-")[0] if marker else label.split()[0] if label else ""
    years = [int(item) for item in re.findall(r"(?:19|20)\d{2}", marker or label)]
    latest_year = max(years) if years else 0
    earliest_year = min(years) if years else 0
    is_range = 1 if len(set(years)) > 1 else 0
    return (conf.upper(), -latest_year, is_range, -earliest_year, marker or label)


def sort_conference_blocks(lines: List[str]) -> None:
    heading_idx = find_conference_heading(lines)
    if heading_idx < 0:
        return

    block_start = heading_idx + 1
    block_end = block_start
    while block_end < len(lines) and not lines[block_end].startswith("* "):
        block_end += 1

    prefix: List[str] = []
    conference_lines = lines[block_start:block_end]
    blocks: List[List[str]] = []
    current: List[str] = []
    for line in conference_lines:
        if line.startswith("  * ") and not line.startswith("    * "):
            if current:
                blocks.append(current)
            current = [line]
        elif current:
            current.append(line)
        else:
            prefix.append(line)
    if current:
        blocks.append(current)
    if not blocks:
        return

    sorted_lines: List[str] = []
    for block in sorted(blocks, key=_conference_block_sort_key):
        sorted_lines.extend(block)
    lines[block_start:block_end] = prefix + sorted_lines


def update_sidebar_with_conference(
    sidebar_path: Path,
    result_path: Path,
    limit: int = 80,
    docs_dir: Path = DEFAULT_DOCS_DIR,
    deep_min_score: float = CONFERENCE_DEEP_MIN_SCORE,
    display_min_score: float = CONFERENCE_DISPLAY_MIN_SCORE,
) -> None:
    sidebar_path.parent.mkdir(parents=True, exist_ok=True)
    conference, years = parse_conference_result_name(result_path)
    marker = build_conference_marker(conference, years)

    block = build_conference_block(
        result_path,
        docs_dir=docs_dir,
        limit=limit,
        deep_min_score=deep_min_score,
        display_min_score=display_min_score,
    )

    lock_path = sidebar_path.parent / ".sidebar.lock"
    with open(lock_path, "w") as lock_fd:
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            lines = sidebar_path.read_text(encoding="utf-8").splitlines(keepends=True) if sidebar_path.exists() else []
            existing_paper_lines = extract_conference_paper_lines(lines, marker)
            remove_existing_conference_block(lines, marker)
            heading_idx = ensure_conference_heading(lines)
            block = merge_conference_paper_lines(block, existing_paper_lines, conference, years)
            lines[heading_idx + 1:heading_idx + 1] = block
            sort_conference_blocks(lines)
            sidebar_path.write_text("".join(lines), encoding="utf-8")
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)


def choose_result_file(paths: Iterable[Path]) -> Path:
    existing = [p for p in paths if p and p.exists()]
    if not existing:
        raise FileNotFoundError("没有可用的会议结果文件。")
    priority = {".llm.json": 0, ".rerank.json": 1, ".rrf.json": 2}
    return sorted(
        existing,
        key=lambda p: next((rank for suffix, rank in priority.items() if p.name.endswith(suffix)), 9),
    )[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="更新 docs/_sidebar.md 的 Conference Papers 分组。")
    parser.add_argument("--result", action="append", default=[], help="会议结果 JSON，优先 llm，其次 rerank/rrf。可重复传入。")
    parser.add_argument("--sidebar", default=str(DEFAULT_SIDEBAR_PATH))
    parser.add_argument("--docs-dir", default=str(DEFAULT_DOCS_DIR))
    parser.add_argument("--limit", type=int, default=80)
    parser.add_argument(
        "--deep-min-score",
        type=float,
        default=CONFERENCE_DEEP_MIN_SCORE,
        help="兼容旧参数；会议链路现在会为所有展示论文生成精读全文和图表。",
    )
    parser.add_argument(
        "--display-min-score",
        type=float,
        default=CONFERENCE_DISPLAY_MIN_SCORE,
        help="会议论文进入 sidebar 和 docs 的最低 LLM 分数；默认只展示 4 分及以上。",
    )
    args = parser.parse_args()

    result_path = choose_result_file(Path(item) for item in args.result)
    update_sidebar_with_conference(
        Path(args.sidebar),
        result_path,
        limit=max(int(args.limit or 0), 0),
        docs_dir=Path(args.docs_dir),
        deep_min_score=float(args.deep_min_score),
        display_min_score=float(args.display_min_score),
    )
    print(f"[INFO] Conference sidebar updated: {args.sidebar} <- {result_path}", flush=True)


if __name__ == "__main__":
    main()
