#!/usr/bin/env python

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
OPENREVIEW_API2_BASE = "https://api2.openreview.net"
NEURIPS_PROGRAM_YEARS = {2026}

from maintain.common import format_years_token, resolve_target_years


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _safe_slug(value: str) -> str:
    text = _norm(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text or "item"


def _get_note_attr(note: Any, key: str, default: Any = None) -> Any:
    if isinstance(note, dict):
        return note.get(key, default)
    return getattr(note, key, default)


def _content_value(content: Dict[str, Any], key: str) -> Any:
    raw = content.get(key)
    if isinstance(raw, dict) and "value" in raw:
        return raw.get("value")
    return raw


def _normalize_timestamp_ms(value: Any) -> str:
    try:
        ms = int(value)
    except Exception:
        return ""
    if ms <= 0:
        return ""
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def _normalize_authors(content: Dict[str, Any]) -> List[str]:
    authors = _content_value(content, "authors")
    if isinstance(authors, list):
        return [_norm(item) for item in authors if _norm(item)]
    text = _norm(authors)
    if not text:
        return []
    return [_norm(item) for item in re.split(r"[;,]+", text) if _norm(item)]


def _normalize_keywords(content: Dict[str, Any]) -> List[str]:
    keywords = _content_value(content, "keywords")
    if isinstance(keywords, list):
        return [_norm(item) for item in keywords if _norm(item)]
    text = _norm(keywords)
    if not text:
        return []
    return [_norm(item) for item in re.split(r"[;,]+", text) if _norm(item)]


def _extract_replies(note: Any) -> List[Dict[str, Any]]:
    details = _get_note_attr(note, "details", {}) or {}
    replies = details.get("replies")
    if isinstance(replies, list):
        return [item for item in replies if isinstance(item, dict)]
    return []


def _reply_invitation(reply: Dict[str, Any]) -> str:
    invitations = reply.get("invitations") or []
    if isinstance(invitations, list) and invitations:
        return _norm(invitations[0])
    return _norm(reply.get("invitation"))


def _extract_decision_text(note: Any) -> str:
    for reply in _extract_replies(note):
        invitation = _reply_invitation(reply).lower()
        if not invitation.endswith("/-/decision"):
            continue
        content = reply.get("content") or {}
        decision = _content_value(content, "decision")
        recommendation = _content_value(content, "recommendation")
        text = _norm(decision) or _norm(recommendation)
        if text:
            return text
    return ""


def _extract_venue_text(note: Any) -> str:
    content = _get_note_attr(note, "content", {}) or {}
    if not isinstance(content, dict):
        return ""
    return _norm(_content_value(content, "venue"))


def _has_public_reader(note: Any) -> bool:
    readers = _get_note_attr(note, "readers", []) or []
    if not isinstance(readers, list):
        return False
    lowered = {str(item).strip().lower() for item in readers}
    return "everyone" in lowered or "openreview.net/everyone" in lowered


def classify_submission_status(note: Any) -> str:
    decision_text = _extract_decision_text(note).lower()
    if decision_text:
        if "accept" in decision_text and "reject" not in decision_text:
            return "Accepted"
        if "withdraw" in decision_text:
            return "Withdrawn-Public" if _has_public_reader(note) else "Withdrawn"
        if "reject" in decision_text:
            return "Rejected-Public" if _has_public_reader(note) else "Rejected"
    venue_text = _extract_venue_text(note).lower()
    if venue_text:
        if "accept" in venue_text or "spotlight" in venue_text or "regular" in venue_text or "oral" in venue_text:
            return "Accepted"
        if "submitted to" in venue_text or "reject" in venue_text:
            return "Rejected-Public" if _has_public_reader(note) else "Rejected"
    return "Public" if _has_public_reader(note) else "Submission"


def build_source_label(conference: str, year: int, status: str) -> str:
    return f"{_norm(conference)}-{int(year)}-{_norm(status)}"


def build_openreview_paper_id(conference: str, year: int, note_id: str) -> str:
    return f"openreview-{_safe_slug(conference)}-{int(year)}-{_safe_slug(note_id)}"


def build_venue_id(conference: str, year: int) -> str:
    conf = _norm(conference)
    mapping = {
        "neurips": "NeurIPS.cc",
        "nips": "NeurIPS.cc",
        "iclr": "ICLR.cc",
        "icml": "ICML.cc",
        "aaai": "AAAI.org",
    }
    prefix = mapping.get(conf.lower(), conf)
    return f"{prefix}/{int(year)}/Conference"


def should_keep_submission(status: str, note: Any, *, public_only: bool) -> bool:
    if status == "Accepted":
        return True
    if status in ("Rejected-Public", "Withdrawn-Public", "Public"):
        return True
    if not public_only and status in ("Rejected", "Withdrawn", "Submission"):
        return True
    return False


def normalize_openreview_submission(
    note: Any,
    *,
    conference: str,
    year: int,
    public_only: bool = True,
) -> Dict[str, Any] | None:
    note_id = _norm(_get_note_attr(note, "id"))
    forum = _norm(_get_note_attr(note, "forum")) or note_id
    content = _get_note_attr(note, "content", {}) or {}
    if not isinstance(content, dict):
        content = {}

    title = _norm(_content_value(content, "title"))
    abstract = _norm(_content_value(content, "abstract"))
    if not note_id or not title:
        return None

    status = classify_submission_status(note)
    if public_only and not _has_public_reader(note):
        return None
    if not should_keep_submission(status, note, public_only=public_only):
        return None

    pdf_field = _norm(_content_value(content, "pdf"))
    pdf_url = ""
    if pdf_field:
        if pdf_field.startswith("http://") or pdf_field.startswith("https://"):
            pdf_url = pdf_field
        else:
            pdf_url = f"https://openreview.net{pdf_field}"
    elif _has_public_reader(note):
        pdf_url = f"https://openreview.net/pdf?id={forum}"

    if public_only and not pdf_url:
        return None

    keywords = _normalize_keywords(content)
    venue = build_venue_id(conference, year)
    source = build_source_label(conference, year, status)
    primary_category = keywords[0] if keywords else venue
    published = (
        _normalize_timestamp_ms(_get_note_attr(note, "pdate"))
        or _normalize_timestamp_ms(_get_note_attr(note, "cdate"))
        or _normalize_timestamp_ms(_get_note_attr(note, "tcdate"))
    )
    return {
        "id": build_openreview_paper_id(conference, year, note_id),
        "source": source,
        "source_paper_id": note_id,
        "doi": "",
        "version": _norm(_get_note_attr(note, "number")),
        "title": title,
        "abstract": abstract,
        "authors": _normalize_authors(content),
        "primary_category": primary_category,
        "categories": keywords,
        "published": published or None,
        "link": f"https://openreview.net/forum?id={forum}",
        "pdf_url": pdf_url,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "venue_id": venue,
        "decision": _extract_decision_text(note),
    }


def normalize_neurips_program_events(
    events: List[Dict[str, Any]],
    abstracts: Dict[str, str],
    *,
    year: int,
) -> List[Dict[str, Any]]:
    venue_id = build_venue_id("NeurIPS", year)
    expected_group = f"https://openreview.net/group?id={venue_id}"
    papers: Dict[str, Dict[str, Any]] = {}
    for event in events:
        decision = _norm(event.get("decision"))
        if event.get("sourceurl") != expected_group or not decision.lower().startswith("accept"):
            continue
        if not event.get("visible") or event.get("eventtype") not in {"Poster", "Oral"}:
            continue
        official_path = _norm(event.get("virtualsite_url"))
        if not official_path.startswith(f"/virtual/{int(year)}/"):
            raise ValueError(f"NeurIPS 官方论文年份不一致：{official_path}")
        paper_url = _norm(event.get("paper_url"))
        parsed_url = urlparse(paper_url)
        note_ids = parse_qs(parsed_url.query).get("id") or []
        if parsed_url.hostname != "openreview.net" or parsed_url.path != "/forum" or len(note_ids) != 1:
            raise ValueError(f"NeurIPS 主会论文缺少有效 OpenReview 链接：{event.get('id')}")
        note_id = _norm(note_ids[0])
        title = _norm(event.get("name"))
        if not title or not note_id:
            raise ValueError(f"NeurIPS 主会论文缺少标题或 ID：{event.get('id')}")
        pid = build_openreview_paper_id("NeurIPS", year, note_id)
        abstract = _norm(abstracts.get(str(event.get("id"))))
        if pid in papers:
            if len(abstract) > len(papers[pid]["abstract"]):
                papers[pid]["abstract"] = abstract
            if not papers[pid]["pdf_url"] and _norm(event.get("paper_pdf_url")):
                papers[pid]["pdf_url"] = _norm(event.get("paper_pdf_url"))
            continue
        keywords = [_norm(value) for value in event.get("keywords") or [] if _norm(value)]
        papers[pid] = {
            "id": pid,
            "source": build_source_label("NeurIPS", year, "Accepted"),
            "source_paper_id": note_id,
            "title": title,
            "abstract": abstract,
            "authors": [_norm(author.get("fullname")) for author in event.get("authors") or [] if _norm(author.get("fullname"))],
            "primary_category": keywords[0] if keywords else venue_id,
            "categories": keywords,
            "published": f"{int(year)}-01-01T00:00:00Z",
            "publication_date": str(year),
            "publication_date_precision": "year",
            "publication_date_source": urljoin("https://neurips.cc", official_path),
            "publication_date_kind": "accepted_notice",
            "link": paper_url,
            "pdf_url": _norm(event.get("paper_pdf_url")),
            "official_url": urljoin("https://neurips.cc", official_path),
            "venue_id": venue_id,
            "decision": decision,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    return list(papers.values())


def normalize_neurips_program_abstracts(payload: List[Dict[str, Any]], *, year: int) -> Dict[str, str]:
    if not isinstance(payload, list):
        raise RuntimeError("NeurIPS 官方导出数据格式异常")
    abstracts = {}
    for row in payload:
        path = urlparse(_norm(row.get("virtualsite_url"))).path
        if not path.startswith(f"/virtual/{int(year)}/"):
            raise ValueError(f"NeurIPS 官方摘要年份不一致：{path}")
        if not path.startswith((f"/virtual/{int(year)}/poster/", f"/virtual/{int(year)}/oral/")):
            continue
        abstracts[path.rsplit("/", 1)[-1]] = _norm(row.get("abstract"))
    return abstracts


def fetch_neurips_program_abstracts(*, year: int) -> Dict[str, str]:
    url = f"https://neurips.cc/Downloads/{int(year)}"
    with requests.Session() as session:
        session.headers["User-Agent"] = "daily-paper-reader-maintain/1.0"
        response = session.get(url, timeout=60)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        token = soup.select_one('input[name="csrfmiddlewaretoken"]')
        if not token or not token.get("value"):
            raise RuntimeError("NeurIPS 官方导出表单缺少 CSRF token")
        response = session.post(
            url,
            data={
                "csrfmiddlewaretoken": token["value"],
                "format": "5",
                "posters": "on",
                "resource": "0",
                "submitaction": "Download Data",
            },
            headers={"Referer": url, "Origin": "https://neurips.cc"},
            timeout=300,
        )
        response.raise_for_status()
        payload = response.json()
    return normalize_neurips_program_abstracts(payload, year=year)


def fetch_neurips_program(*, year: int) -> List[Dict[str, Any]]:
    base = f"https://neurips.cc/static/virtual/data/neurips-{int(year)}"
    headers = {"User-Agent": "daily-paper-reader-maintain/1.0"}
    events_response = requests.get(f"{base}-orals-posters.json", headers=headers, timeout=120)
    events_response.raise_for_status()
    events_payload = events_response.json()
    events = events_payload.get("results") if isinstance(events_payload, dict) else None
    if not isinstance(events, list) or events_payload.get("next") or events_payload.get("count") != len(events):
        raise RuntimeError("NeurIPS 官方论文数据格式或数量异常")
    abstracts_response = requests.get(f"{base}-abstracts.json", headers=headers, timeout=120)
    abstracts_response.raise_for_status()
    abstracts = abstracts_response.json()
    if not isinstance(abstracts, dict):
        raise RuntimeError("NeurIPS 官方摘要数据格式异常")
    papers = normalize_neurips_program_events(events, abstracts, year=year)
    if any(not paper["abstract"] for paper in papers):
        log(f"[NeurIPS Program] year={year} downloading_complete_abstracts")
        exported_abstracts = fetch_neurips_program_abstracts(year=year)
        abstracts.update({key: value for key, value in exported_abstracts.items() if value})
        papers = normalize_neurips_program_events(events, abstracts, year=year)
    if not papers:
        raise RuntimeError(f"NeurIPS {year} 官方数据中没有已确认录用的主会论文")
    log(f"[NeurIPS Program] year={year} accepted={len(papers)}")
    log(f"[NeurIPS Program] abstract={sum(bool(paper['abstract']) for paper in papers)}/{len(papers)}")
    return papers


def iter_target_years(year_end: int, year_count: int) -> List[int]:
    safe_count = max(int(year_count or 1), 1)
    end_year = int(year_end)
    start_year = end_year - safe_count + 1
    return list(range(start_year, end_year + 1))


def fetch_openreview_submissions(
    *,
    conference: str,
    years: Iterable[int],
    username: str,
    password: str,
    public_only: bool = True,
) -> List[Dict[str, Any]]:
    try:
        import openreview  # type: ignore
    except Exception as exc:  # pragma: no cover
        log(f"[WARN] 缺少 openreview-py，切换到 OpenReview API2 REST 抓取：{exc}")
        return fetch_openreview_submissions_via_rest(
            conference=conference,
            years=years,
            username=username,
            password=password,
            public_only=public_only,
        )

    client = openreview.api.OpenReviewClient(
        baseurl="https://api2.openreview.net",
        username=username,
        password=password,
    )

    out: List[Dict[str, Any]] = []
    seen_ids = set()

    for year in years:
        venue_id = build_venue_id(conference, year)
        log(f"[OpenReview] venue={venue_id} start")
        venue_group = client.get_group(venue_id)
        submission_id = None
        if getattr(venue_group, "content", None):
            raw = venue_group.content.get("submission_id")
            if isinstance(raw, dict):
                submission_id = _norm(raw.get("value"))
        submission_invitation = submission_id or f"{venue_id}/-/Submission"
        notes = client.get_all_notes(invitation=submission_invitation, details="replies")
        log(f"[OpenReview] venue={venue_id} submissions={len(notes)}")
        for note in notes:
            paper = normalize_openreview_submission(
                note,
                conference=conference,
                year=year,
                public_only=public_only,
            )
            if not paper:
                continue
            pid = _norm(paper.get("id"))
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)
            out.append(paper)
    return out


def _rest_headers(token: str = "") -> Dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "daily-paper-reader-maintain/1.0",
    }
    safe_token = _norm(token)
    if safe_token:
        headers["Authorization"] = f"Bearer {safe_token}"
    return headers


def _login_openreview_rest_session(username: str, password: str) -> tuple[requests.Session, str]:
    session = requests.Session()
    resp = session.post(
        f"{OPENREVIEW_API2_BASE}/login",
        headers=_rest_headers(),
        json={
            "id": username,
            "password": password,
            "expiresIn": 3600,
        },
        timeout=30,
    )
    resp.raise_for_status()
    token = _norm((resp.json() or {}).get("token"))
    if not token:
        raise RuntimeError("OpenReview API2 登录成功但未返回 token。")
    return session, token


def _extract_submission_invitation_from_group(group: Dict[str, Any], venue_id: str) -> str:
    content = group.get("content") if isinstance(group, dict) else {}
    if isinstance(content, dict):
        raw = content.get("submission_id")
        if isinstance(raw, dict):
            submission_id = _norm(raw.get("value"))
            if submission_id:
                return submission_id
        submission_id = _norm(raw)
        if submission_id:
            return submission_id
    return f"{venue_id}/-/Submission"


def _fetch_openreview_group_rest(
    session: requests.Session,
    *,
    token: str,
    venue_id: str,
) -> Dict[str, Any]:
    resp = session.get(
        f"{OPENREVIEW_API2_BASE}/groups",
        headers=_rest_headers(token),
        params={"id": venue_id},
        timeout=30,
    )
    resp.raise_for_status()
    groups = (resp.json() or {}).get("groups") or []
    if not groups:
        raise RuntimeError(f"OpenReview API2 未找到 venue group：{venue_id}")
    group = groups[0]
    if not isinstance(group, dict):
        raise RuntimeError(f"OpenReview API2 venue group 格式异常：{venue_id}")
    return group


def _fetch_openreview_notes_rest(
    session: requests.Session,
    *,
    token: str,
    invitation: str,
    page_size: int,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    offset = 0
    safe_page_size = max(int(page_size or 1000), 1)
    while True:
        resp = session.get(
            f"{OPENREVIEW_API2_BASE}/notes",
            headers=_rest_headers(token),
            params={
                "invitation": invitation,
                "details": "replies",
                "limit": safe_page_size,
                "offset": offset,
            },
            timeout=120,
        )
        resp.raise_for_status()
        payload = resp.json() or {}
        notes = payload.get("notes") or []
        if not isinstance(notes, list):
            raise RuntimeError("OpenReview API2 notes 响应格式异常：notes 不是 list")
        out.extend([note for note in notes if isinstance(note, dict)])
        total = payload.get("count")
        log(
            f"[OpenReview REST] invitation={invitation} "
            f"offset={offset} fetched={len(notes)} total={total or '?'}"
        )
        if len(notes) < safe_page_size:
            break
        offset += safe_page_size
        if isinstance(total, int) and offset >= total:
            break
    return out


def fetch_openreview_submissions_via_rest(
    *,
    conference: str,
    years: Iterable[int],
    username: str,
    password: str,
    public_only: bool = True,
    page_size: int = 1000,
) -> List[Dict[str, Any]]:
    session, token = _login_openreview_rest_session(username, password)
    out: List[Dict[str, Any]] = []
    seen_ids = set()

    for year in years:
        venue_id = build_venue_id(conference, year)
        log(f"[OpenReview REST] venue={venue_id} start")
        group = _fetch_openreview_group_rest(session, token=token, venue_id=venue_id)
        submission_invitation = _extract_submission_invitation_from_group(group, venue_id)
        notes = _fetch_openreview_notes_rest(
            session,
            token=token,
            invitation=submission_invitation,
            page_size=page_size,
        )
        log(f"[OpenReview REST] venue={venue_id} submissions={len(notes)}")
        for note in notes:
            paper = normalize_openreview_submission(
                note,
                conference=conference,
                year=year,
                public_only=public_only,
            )
            if not paper:
                continue
            pid = _norm(paper.get("id"))
            if not pid or pid in seen_ids:
                continue
            seen_ids.add(pid)
            out.append(paper)
    return out


def resolve_output_path(
    conference: str,
    year_end: int,
    year_count: int,
    output: str,
    years: Iterable[int] | None = None,
) -> str:
    manual = _norm(output)
    if manual:
        if os.path.isabs(manual):
            return manual
        return os.path.abspath(os.path.join(ROOT_DIR, manual))

    target_years = list(years or iter_target_years(year_end, year_count))
    token = f"{_safe_slug(conference)}-openreview-{format_years_token(target_years)}"
    return os.path.join(ROOT_DIR, "archive", TODAY_STR, "raw", f"{token}.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 OpenReview 会议提交（支持 NeurIPS / ICLR / ICML / AAAI）。")
    parser.add_argument("--conference", type=str, default="NeurIPS", help="会议名，例如 NeurIPS / ICLR / ICML / AAAI。")
    parser.add_argument("--year-end", type=int, default=datetime.now(timezone.utc).year, help="结束年份，默认当前年。")
    parser.add_argument("--year-count", type=int, default=3, help="回溯几年，默认 3。")
    parser.add_argument("--years", type=str, default="", help="显式年份列表，例如 2024,2025；设置后优先于 year-end/year-count。")
    parser.add_argument("--username", type=str, default=os.getenv("OPENREVIEW_USERNAME", ""))
    parser.add_argument("--password", type=str, default=os.getenv("OPENREVIEW_PASSWORD", ""))
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径。")
    parser.add_argument("--include-nonpublic", action="store_true", help="是否保留非公开 submission。默认只保留公开可见稿件。")
    args = parser.parse_args()

    username = _norm(args.username)
    password = _norm(args.password)
    years = resolve_target_years(years=args.years, year_end=args.year_end, year_count=args.year_count)
    program_years = [year for year in years if _norm(args.conference).lower() in {"neurips", "nips"} and year in NEURIPS_PROGRAM_YEARS]
    openreview_years = [year for year in years if year not in program_years]
    if openreview_years and (not username or not password):
        raise RuntimeError("缺少 OpenReview 凭证，请设置 OPENREVIEW_USERNAME / OPENREVIEW_PASSWORD。")
    output_path = resolve_output_path(args.conference, args.year_end, args.year_count, args.output, years=years)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    papers = []
    for year in program_years:
        papers.extend(fetch_neurips_program(year=year))
    if openreview_years:
        papers.extend(fetch_openreview_submissions(
            conference=args.conference,
            years=openreview_years,
            username=username,
            password=password,
            public_only=not bool(args.include_nonpublic),
        ))
    if not papers:
        raise RuntimeError(f"未获取到 {args.conference} 公开论文")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)
    log(f"[OK] OpenReview 结果已写入：{output_path} count={len(papers)}")


if __name__ == "__main__":
    main()
