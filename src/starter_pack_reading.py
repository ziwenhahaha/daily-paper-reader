"""入门包复用原生阅读页：选择、查重、逐阶段补齐和导航投影。"""

import hashlib
import html
import importlib.util
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote

from requests import HTTPError
from paper_dedupe import _arxiv, _doi
from starter_pack_publications import verify_publications

from daily_report_state import (
    bootstrap_daily_state_from_sidebar,
    daily_state_path,
    entries_from_state,
    load_daily_state,
    merge_daily_state,
    save_daily_state,
)


def select_reading_papers(papers, content_limit=12):
    """日期边界不确定及只有录用标题的论文不进入精选阅读。"""
    if (
        isinstance(content_limit, bool)
        or not isinstance(content_limit, int)
        or not 0 <= content_limit <= 20
    ):
        raise ValueError("精选内容数量必须为 0–20 的整数")
    selected = []
    for row in papers:
        versions = row.get("versions") or [row]
        if (
            row.get("bucket") not in {"core", "related"}
            or not str(row.get("abstract") or "").strip()
        ):
            continue
        if not any(
            v.get("publication_window_status") == "included"
            and (
                str(v.get("retrieval_source") or v.get("source") or "").lower()
                == "arxiv"
                or v.get("conference_acceptance_status", "accepted") == "accepted"
            )
            for v in versions
        ):
            continue
        selected.append(dict(row))
    return sorted(
        selected,
        key=lambda p: (
            p.get("bucket") != "core",
            -float(p.get("score") or 0),
            str(p.get("canonical_id") or p.get("id") or ""),
        ),
    )[:content_limit]


def _generator(root):
    spec = importlib.util.spec_from_file_location(
        "starter_reading_generator", Path(__file__).with_name("6.generate_docs.py")
    )
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    from long_range_native import cache_reading_generators

    cache_reading_generators(generator, root)
    return generator


def _identities(row):
    found = set()
    for key in ("id", "paper_id", "canonical_id", "doi", "arxiv_id", "link", "pdf_url"):
        value = unquote(str(row.get(key) or "")).strip().lower()
        if not value:
            continue
        # 阅读路由复用与版本去重使用同一身份口径，不能从任意URL子串猜ID。
        identity_field = key in {"id", "paper_id", "canonical_id"}
        arxiv = _arxiv({"id" if identity_field else key: value})
        doi = _doi({"doi" if identity_field else key: value})
        if arxiv:
            found.add("arxiv:" + arxiv)
        elif doi:
            found.add("doi:" + doi)
        elif identity_field:
            found.add("id:" + value)
    return found


def _safe_route(docs, raw):
    route = unquote(str(raw or "")).removeprefix("#/").removeprefix("/")
    route = route.removesuffix(".md")
    if not route or ":" in route or "?" in route or "#" in route:
        return None
    target = (docs / (route + ".md")).resolve()
    if not target.is_relative_to(docs.resolve()):
        return None
    return route if target.is_file() else None


def _existing_routes(docs, generator):
    """只以稳定标识符匹配；标题相同本身不足以合并不同论文。"""
    index = {}
    for state_path in sorted(docs.rglob("_daily_state.json")):
        state = json.loads(state_path.read_text(encoding="utf-8"))
        for row in state.get("papers", []):
            route = _safe_route(docs, row.get("route"))
            if route:
                for identity in _identities(row):
                    index.setdefault(identity, route)
    sidebar = docs / "_sidebar.md"
    routes = set()
    if sidebar.exists():
        for href in re.findall(
            r'href=["\']([^"\']+)', sidebar.read_text(encoding="utf-8")
        ):
            route = _safe_route(docs, html.unescape(href))
            if route:
                routes.add(route)
    # 也找回已有正文但导航尚未生成的中断任务，续跑不另建页面。
    routes.update(
        str(path.relative_to(docs).with_suffix(""))
        for path in docs.rglob("*.md")
        if not path.name.startswith("_")
    )
    for route in sorted(routes):
        text = (docs / (route + ".md")).read_text(encoding="utf-8")
        meta = generator._parse_front_matter(text)
        for identity in _identities(meta) | _identities({"id": route.split("/")[-1]}):
            index.setdefault(identity, route)
    return index


def _conference(paper):
    source = str(
        paper.get("conference")
        or paper.get("retrieval_source")
        or paper.get("source")
        or ""
    ).strip()
    return "" if source.lower() in {"", "arxiv"} else source.upper()


def _merge_existing_route_tag(docs, route, tag, generator):
    """跨专题复用同页只合并标签，不新建日期、重写笔记或增加运行次数。"""
    document = docs / (route + ".md")
    text = document.read_text(encoding="utf-8")
    metadata = generator._parse_front_matter(text)
    tags = list(metadata.get("tags") or [])
    new_tag = f"query:{tag}"
    if new_tag not in tags:
        tags.append(new_tag)
        changed, _ = generator.upsert_front_matter_field(
            text, "tags", json.dumps(tags, ensure_ascii=False)
        )
        if changed != text:
            document.write_text(changed, encoding="utf-8")
    for path in docs.rglob("_daily_state.json"):
        state = json.loads(path.read_text(encoding="utf-8"))
        changed = False
        for row in state.get("papers", []):
            if _safe_route(docs, row.get("route")) != route:
                continue
            tags = row.setdefault("tags", [])
            new_tag_record = {"kind": "query", "label": tag}
            if new_tag_record not in tags:
                tags.append(new_tag_record)
                changed = True
        if changed:
            # 不经过merge_daily_state，避免一次换专题被记作一次新日报运行。
            path.write_text(
                json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )


def _attach_navigation(docs, paper, route, metadata, tag, token, label, generator):
    """原有会议/日报合同，不另造阅读器或覆写其它日期数据。"""
    sidebar = docs / "_sidebar.md"
    old = sidebar.read_text(encoding="utf-8") if sidebar.exists() else ""
    found = False

    def refresh(match):
        nonlocal found
        anchor = match[0]
        href = re.search(r'href=["\']([^"\']+)', anchor)
        if not href or _safe_route(docs, html.unescape(href[1])) != route:
            return anchor
        found = True
        payload_match = re.search(r'data-sidebar-item=["\']([^"\']*)["\']', anchor)
        if not payload_match:
            return anchor
        payload = json.loads(html.unescape(payload_match[1]))
        previous = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        if metadata.get("evidence"):
            payload["evidence"] = metadata["evidence"]
        new_tag = {"kind": "query", "label": tag}
        if new_tag not in payload.setdefault("tags", []):
            payload["tags"].append(new_tag)
        if json.dumps(payload, sort_keys=True, ensure_ascii=False) == previous:
            return anchor
        encoded = html.escape(json.dumps(payload, ensure_ascii=False), quote=True)
        return (
            anchor[: payload_match.start(1)] + encoded + anchor[payload_match.end(1) :]
        )

    refreshed = re.sub(r"<a\b[^>]*>", refresh, old)
    for href in re.findall(r"\]\(([^)]+)\)", old):
        if _safe_route(docs, href) == route:
            found = True
    if found:
        if refreshed != old:
            sidebar.write_text(refreshed, encoding="utf-8")
        _merge_existing_route_tag(docs, route, tag, generator)
        return
    conference = _conference(paper)
    if conference:
        import conference_sidebar as cs

        years = str(paper.get("conference_year") or paper.get("year") or "")
        marker = cs.build_conference_marker(conference, years)
        ranked = {
            "score": paper.get("score"),
            "matched_query_tag": tag,
            "canonical_evidence": metadata.get("evidence", ""),
        }
        payload = cs.build_sidebar_payload(paper, ranked, conference, years)
        block = [
            f"  * {cs.build_conference_label(conference, years)} {marker}\n",
            cs.topic_line_for(conference, years, "query", tag),
        ]
        block.append(
            f'      * <a class="dpr-sidebar-item-link dpr-sidebar-item-structured" href="#/{html.escape(route, quote=True)}" data-sidebar-item="{payload}">{html.escape(paper["title"])}</a>\n'
        )
        lines = old.splitlines(keepends=True)
        existing = cs.extract_conference_paper_lines(lines, marker)
        cs.remove_existing_conference_block(lines, marker)
        position = cs.ensure_conference_heading(lines)
        lines[position + 1 : position + 1] = cs.merge_conference_paper_lines(
            block, existing, conference, years
        )
        cs.sort_conference_blocks(lines)
        sidebar.write_text("".join(lines), encoding="utf-8")
        return
    # 复用旧路径时不把同一论文复制到当前区间。
    route_token = route.split("/")[0]
    if re.fullmatch(r"\d{8}-\d{8}", route_token):
        token = route_token
    elif re.fullmatch(r"\d{8}", route_token):
        token = route_token
    elif re.match(r"^\d{6}/\d{2}/", route):
        token = "".join(route.split("/")[:2])
    path = daily_state_path(str(docs), token)
    state = load_daily_state(path) or bootstrap_daily_state_from_sidebar(
        str(sidebar), token
    )
    record = {
        "paper_id": paper["id"],
        "route": route,
        "title": paper["title"],
        "section": metadata.get("reading_section", "quick"),
        "score": paper.get("score"),
        "tags": [{"kind": "query", "label": tag}],
        "evidence": metadata.get("evidence", ""),
    }
    merged = merge_daily_state(
        state,
        token,
        [record],
        datetime.now(timezone.utc).isoformat(),
        True,
        state.get("date_label") or label,
    )
    merged["run_count"] = max(1, state.get("run_count", 0))
    save_daily_state(path, merged)
    deep, quick, evidence = entries_from_state(merged)
    generator.update_sidebar(
        str(sidebar),
        token,
        deep,
        quick,
        evidence,
        date_label=merged["date_label"],
        replace_existing=True,
    )
    generator.write_day_meta_index_json(
        str(docs),
        token,
        merged["date_label"],
        [],
        [paper],
        merged_deep_entries=deep,
        merged_quick_entries=quick,
    )


def prepare_reading(
    papers, root, profile_tag, run_id, arxiv_start, as_of, content_limit=12
):
    """生成精选原生阅读内容；可恢复失败抛错，官方缺全文明确 unavailable。"""
    root = Path(root).resolve()
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip().lower()
    if root == Path(__file__).resolve().parents[1] and repository in {
        "",
        "ziwenhahaha/daily-paper-reader",
    }:
        raise ValueError("入门包产物必须写入独立目录或 Fork，不得写主仓库 docs")
    selected = select_reading_papers(papers, content_limit)
    if not selected:
        return []
    # 只为最终小批精选解析官方PDF，避免候选池逐篇请求详情页。
    selected = verify_publications(selected, root, resolve_pdfs=True)
    docs = root / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    generator = _generator(root)
    existing = _existing_routes(docs, generator)
    start = date.fromisoformat(str(arxiv_start)[:10])
    end = date.fromisoformat(str(as_of)[:10]) - timedelta(days=1)
    token, label = f"{start:%Y%m%d}-{end:%Y%m%d}", f"{start} ～ {end}"
    client = None
    for paper in selected:
        versions = paper.get("versions") or []
        identities = _identities(paper)
        for version in versions:
            identities.update(_identities(version))
        route = next(
            (existing[key] for key in sorted(identities) if key in existing), None
        )
        if not route:
            # 外部 route_aliases 只能命中真实本地文件，不能越出 docs。
            route = next(
                (
                    _safe_route(docs, value)
                    for value in paper.get("route_aliases", [])
                    if _safe_route(docs, value)
                ),
                None,
            )
        if not route:
            conference = _conference(paper)
            if conference:
                from conference_sidebar import build_conference_paper_route

                route = build_conference_paper_route(
                    paper,
                    conference,
                    str(paper.get("conference_year") or paper.get("year") or ""),
                )
            else:
                identifier = str(paper.get("id") or "")
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,120}", identifier):
                    identifier = (
                        "paper-"
                        + hashlib.sha256(
                            str(paper.get("canonical_id") or identifier).encode()
                        ).hexdigest()[:20]
                    )
                route = f"{token}/{identifier}"
        document = docs / (route + ".md")
        if not document.resolve().is_relative_to(docs):
            raise ValueError("不安全的论文路由")
        document.parent.mkdir(parents=True, exist_ok=True)
        paper.update(
            {
                "route": route,
                "llm_score": paper.get("score"),
                "llm_tags": [f"query:{profile_tag}"],
                "selection_source": "long-range",
            }
        )
        official_pdf = ""
        official_record = paper
        if _conference(paper) and route.startswith("conference/"):
            official_pdf = paper.get("official_pdf_url") or ""
            if not official_pdf:
                # 只使用同会议、同年份、同一记录的官方PDF，不借合并后的arXiv版本。
                for version in versions:
                    if (
                        version.get("official_pdf_url")
                        and _conference(version) == _conference(paper)
                        and str(
                            version.get("conference_year") or version.get("year") or ""
                        )
                        == str(paper.get("conference_year") or paper.get("year") or "")
                        and (_identities(version) & _identities(paper))
                    ):
                        official_record, official_pdf = (
                            version,
                            version["official_pdf_url"],
                        )
                        break
        pdf = (
            official_pdf
            or paper.get("pdf_url")
            or next((v.get("pdf_url") for v in versions if v.get("pdf_url")), "")
        )
        if (
            not pdf
            and not _conference(paper)
            and re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", str(paper.get("id")))
        ):
            pdf = f'https://arxiv.org/pdf/{paper["id"]}'
        if not document.exists() and not pdf and _conference(paper):
            from conference_sidebar import resolve_conference_pdf_url

            pdf = resolve_conference_pdf_url(paper)
        paper["pdf_url"] = pdf
        if not document.exists():
            text = generator.build_markdown_content(
                paper, "quick", "", "", paper["llm_tags"]
            )
            if _conference(paper):
                from conference_sidebar import resolve_publication_date

                publication = resolve_publication_date(
                    paper,
                    _conference(paper),
                    str(paper.get("conference_year") or paper.get("year") or ""),
                )
                for key, value in {
                    **publication,
                    "date": publication.get("publication_date") or "Unknown",
                }.items():
                    text, _ = generator.upsert_front_matter_field(
                        text, key, generator.yaml_escape_value(str(value))
                    )
            for key in ("id", "doi", "canonical_id"):
                if paper.get(key):
                    text, _ = generator.upsert_front_matter_field(
                        text, key, generator.yaml_escape_value(str(paper[key]))
                    )
            document.write_text(text, encoding="utf-8")
        current_text = document.read_text(encoding="utf-8")
        metadata = generator._parse_front_matter(current_text)
        previous_pdf = metadata.get("pdf") or metadata.get("pdf_url") or ""
        if not route.startswith("conference/") and previous_pdf:
            pdf = previous_pdf
        if (
            official_pdf
            and route.startswith("conference/")
            and (not previous_pdf or "openreview.net/" in previous_pdf)
        ):
            # 只替换同会议版本的官方获取入口，保留原route、正文、笔记与阅读状态。
            fields = {
                "pdf": official_pdf,
                "official_pdf_url": official_pdf,
                "official_link": official_record.get("official_link")
                or paper.get("official_link")
                or "",
                "conference_acceptance_status": official_record.get(
                    "conference_acceptance_status"
                )
                or paper.get("conference_acceptance_status")
                or "accepted",
            }
            for key, value in fields.items():
                if value:
                    current_text, _ = generator.upsert_front_matter_field(
                        current_text, key, generator.yaml_escape_value(str(value))
                    )
            document.write_text(current_text, encoding="utf-8")
            metadata = generator._parse_front_matter(current_text)
        # 已存在的日报/会议正文沿用原语义，不强制刷新其中文关联说明。
        if metadata.get("selection_source") != "long-range":
            paper["selection_source"] = (
                metadata.get("selection_source") or "starter-pack"
            )
        pdf = pdf or metadata.get("pdf_url") or metadata.get("pdf") or ""
        if not pdf and _conference(paper):
            from conference_sidebar import resolve_conference_pdf_url

            pdf = resolve_conference_pdf_url(paper)
        paper["pdf_url"] = pdf
        txt = document.with_suffix(".txt")
        unavailable = ""
        try:
            if not pdf and not txt.exists():
                unavailable = "尚无公开 PDF 链接"
            else:
                generator.ensure_text_content(pdf, str(txt))
        except generator.PaperFulltextUnavailable as error:
            unavailable = str(error)
        except HTTPError as error:
            status = getattr(error.response, "status_code", None)
            if status not in {403, 404}:
                raise
            # 不推断撤稿，也不替换版本或绕过服务器访问限制。
            unavailable = f"论文全文服务器返回 HTTP {status}，当前公开链接不可获取"
        if unavailable:
            document.with_suffix(".fulltext.json").write_text(
                json.dumps(
                    {"status": "unavailable", "reason": unavailable}, ensure_ascii=False
                ),
                encoding="utf-8",
            )
        elif document.with_suffix(".fulltext.json").exists():
            document.with_suffix(".fulltext.json").write_text(
                json.dumps({"status": "ready", "pdf_url": pdf}, ensure_ascii=False),
                encoding="utf-8",
            )
        section = (
            "deep"
            if not unavailable
            and (
                paper.get("bucket") == "core"
                or metadata.get("reading_section") == "deep"
            )
            else "quick"
        )
        complete = (
            all(
                metadata.get(key)
                for key in (
                    "title_zh",
                    "tldr",
                    "motivation",
                    "method",
                    "result",
                    "conclusion",
                )
            )
            and "## 摘要" in current_text
        )
        complete = complete and (
            section != "deep"
            or bool(
                generator.extract_section_tail(current_text, "论文详细总结（自动生成）")
            )
        )
        if not complete:
            if client is None:
                client = generator.create_llm_client()
                if client is None:
                    raise RuntimeError("阅读总结缺少可用模型配置")
                client.kwargs["thinking"] = {"type": "disabled"}
            metadata = generator.ensure_reading_content(
                paper, section, str(document), str(txt), client, require_complete=True
            )
        paper["reading_status"] = "unavailable" if unavailable else "complete"
        paper["tldr"] = metadata.get("tldr") or ""
        paper["canonical_evidence"] = metadata.get("evidence") or ""
        paper["fulltext_status"] = "unavailable" if unavailable else "ready"
        if unavailable:
            paper["reading_reason"] = unavailable
        _attach_navigation(
            docs, paper, route, metadata, profile_tag, token, label, generator
        )
        for identity in identities:
            existing.setdefault(identity, route)
    return selected
