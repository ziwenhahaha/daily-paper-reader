"""固定最终名单的确定性、安全外部引用导出。"""

import ipaddress
import re
from urllib.parse import urlsplit, unquote
from starter_pack_guide import _escape, _link, _url, _paper_id, format_venue_time_badge


def _external_safe(value):
    try:
        url = _url(value)
        parts = urlsplit(url)
        host = (parts.hostname or "").lower().rstrip(".")
        if (
            not host
            or host == "localhost"
            or host.endswith((".localhost", ".local", ".internal"))
        ):
            return ""
        try:
            if not ipaddress.ip_address(host).is_global:
                return ""
        except ValueError:
            if "." not in host or re.fullmatch(r"[\d.]+", host):
                return ""
        path = unquote(parts.path).lower()
        if (
            parts.fragment.startswith("/")
            or "/daily-paper-reader/" in path
            or (path.startswith("/docs/") and path.endswith(".md"))
        ):
            return ""
        return url
    except ValueError:
        return ""


def external_url(paper):
    candidates = []
    for version in [paper] + list(paper.get("versions") or []):
        if version.get("conference_acceptance_status") in (
            "unverified",
            "rejected",
            "withdrawn",
        ):
            continue
        if version.get("publication_window_status") in ("excluded", "uncertain"):
            continue
        for field in (
            "official_link",
            "official_url",
            "url",
            "link",
            "official_pdf_url",
            "pdf_url",
        ):
            url = _external_safe(version.get(field))
            if url:
                parts = urlsplit(url)
                host = parts.hostname or ""
                rank = (
                    0
                    if field in ("official_link", "official_url")
                    else (
                        3
                        if field in ("official_pdf_url", "pdf_url")
                        or parts.path.endswith(".pdf")
                        else 2
                    )
                )
                if host in ("arxiv.org", "www.arxiv.org"):
                    match = re.fullmatch(
                        r"/(?:pdf|abs)/(\d{4}\.\d{4,5}(?:v\d+)?|[a-z-]+(?:\.[A-Z]{2})?/\d{7}(?:v\d+)?)(?:\.pdf)?",
                        parts.path,
                    )
                    if match:
                        url = "https://arxiv.org/abs/" + match.group(1)
                        rank = min(rank, 1)
                elif host in ("doi.org", "dx.doi.org"):
                    rank = min(rank, 1)
                candidates.append((rank, url))
        doi = str(version.get("doi") or "")
        if re.fullmatch(r"10\.\d{4,9}/\S+", doi):
            url = _external_safe("https://doi.org/" + doi)
            if url:
                candidates.append((1, url))
    return min(candidates, key=lambda item: item[0])[1] if candidates else ""


def export_records(papers):
    if len(papers) > 100:
        raise ValueError("最终论文名单不得超过100篇")
    ids = [_paper_id(p) for p in papers]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError("最终名单ID缺失或重复")
    out = []
    for p in papers:
        record = {
            "id": _paper_id(p),
            "title": str(p.get("title") or ""),
            "score": p.get("llm_score", p.get("score")),
            "url": external_url(p),
        }
        zh = str(p.get("zh_title") or p.get("title_zh") or "").strip()
        if zh:
            record["title_zh"] = zh
        venue = format_venue_time_badge(p)
        if venue:
            record["venue"] = venue
        evidence = str(
            p.get("canonical_evidence") or p.get("llm_evidence_cn") or p.get("evidence") or ""
        ).strip()
        if evidence:
            record["evidence"] = evidence
        section = str(p.get("_export_section") or "").strip()
        if section in ("deep", "quick"):
            record["section"] = section
        out.append(record)
    return out


def _format_export_item(index, paper):
    venue = str(paper.get("venue") or "").strip()
    zh = str(paper.get("title_zh") or "").strip()
    evidence = str(paper.get("evidence") or "").strip()
    score = paper.get("score")
    meta_parts = []
    if venue:
        meta_parts.append(f"`{_escape(venue)}`")
    if score is not None and str(score) != "":
        meta_parts.append(f"分数 {_escape(score)}")
    suffix = (" · " + " · ".join(meta_parts)) if meta_parts else ""
    line = (
        f"{index}. "
        + _link(paper["title"], paper["url"])
        + ("" if paper["url"] else "（原文链接缺失）")
        + suffix
    )
    sub_lines = []
    if zh:
        sub_lines.append(f"   - 中文标题：{_escape(zh)}")
    if evidence:
        sub_lines.append(f"   - 核心亮点：{_escape(evidence)}")
    return "\n".join([line] + sub_lines)


def render_export(records, title="专题论文清单", metadata=None):
    lines = [
        "# " + _escape(title),
        "",
        "以下为本次精选论文最终清单，按相关性评分降序排列。",
        "",
    ]
    for field, label in (
        ("description", "研究需求"),
        ("refinement", "本次细化"),
        ("window", "覆盖范围"),
    ):
        value = (metadata or {}).get(field)
        if value:
            lines.extend([f"- **{label}**：{_escape(value)}"])
    if any((metadata or {}).get(f) for f in ("description", "refinement", "window")):
        lines.append("")

    has_sections = any(r.get("section") in ("deep", "quick") for r in records)
    if has_sections:
        deep_list = [r for r in records if r.get("section") == "deep"]
        quick_list = [r for r in records if r.get("section") != "deep"]
        if deep_list:
            lines += [f"## 精读区（{len(deep_list)} 篇）", ""]
            for idx, paper in enumerate(deep_list, 1):
                lines.append(_format_export_item(idx, paper))
            lines.append("")
        if quick_list:
            lines += [f"## 速读区（{len(quick_list)} 篇）", ""]
            for idx, paper in enumerate(quick_list, 1):
                lines.append(_format_export_item(idx, paper))
            lines.append("")
    else:
        for index, paper in enumerate(records, 1):
            lines.append(_format_export_item(index, paper))
    return "\n".join(lines).rstrip() + "\n"
