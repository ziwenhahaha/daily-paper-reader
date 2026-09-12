"""固定最终名单的确定性、安全外部引用导出。"""

import ipaddress
import re
from urllib.parse import urlsplit, unquote
from starter_pack_guide import _escape, _link, _url, _paper_id


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
    return [
        {
            "id": _paper_id(p),
            "title": str(p.get("title") or ""),
            "score": p.get("score"),
            "url": external_url(p),
        }
        for p in papers
    ]


def render_export(records, title="专题论文清单", metadata=None):
    lines = [
        "# " + _escape(title),
        "",
        "以下为本次固定最终名单，按相关性评分降序；不代表全部相关论文。",
        "",
    ]
    for field, label in (
        ("description", "研究需求"),
        ("refinement", "本次细化"),
        ("window", "固定窗口"),
    ):
        value = (metadata or {}).get(field)
        if value:
            lines.extend([label + "：" + _escape(value), ""])
    for index, paper in enumerate(records, 1):
        lines.append(
            f"{index}. "
            + _link(paper["title"], paper["url"])
            + ("" if paper["url"] else "（原文链接缺失）")
            + " · 分数 "
            + _escape(paper.get("score"))
        )
    return "\n".join(lines) + "\n"
