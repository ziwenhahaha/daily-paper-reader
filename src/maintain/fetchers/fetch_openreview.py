#!/usr/bin/env python

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")


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
        raise RuntimeError("缺少 openreview-py，请先执行 `pip install openreview-py`。") from exc

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


def resolve_output_path(conference: str, year_end: int, year_count: int, output: str) -> str:
    manual = _norm(output)
    if manual:
        if os.path.isabs(manual):
            return manual
        return os.path.abspath(os.path.join(ROOT_DIR, manual))

    token = f"{_safe_slug(conference)}-openreview-{year_end - year_count + 1}-{year_end}"
    return os.path.join(ROOT_DIR, "archive", TODAY_STR, "raw", f"{token}.json")


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 OpenReview 会议提交（支持 NeurIPS / ICLR / ICML / AAAI）。")
    parser.add_argument("--conference", type=str, default="NeurIPS", help="会议名，例如 NeurIPS / ICLR / ICML / AAAI。")
    parser.add_argument("--year-end", type=int, default=datetime.now(timezone.utc).year, help="结束年份，默认当前年。")
    parser.add_argument("--year-count", type=int, default=3, help="回溯几年，默认 3。")
    parser.add_argument("--username", type=str, default=os.getenv("OPENREVIEW_USERNAME", ""))
    parser.add_argument("--password", type=str, default=os.getenv("OPENREVIEW_PASSWORD", ""))
    parser.add_argument("--output", type=str, default="", help="输出 JSON 文件路径。")
    parser.add_argument("--include-nonpublic", action="store_true", help="是否保留非公开 submission。默认只保留公开可见稿件。")
    args = parser.parse_args()

    username = _norm(args.username)
    password = _norm(args.password)
    if not username or not password:
        raise RuntimeError("缺少 OpenReview 凭证，请设置 OPENREVIEW_USERNAME / OPENREVIEW_PASSWORD。")

    years = iter_target_years(args.year_end, args.year_count)
    output_path = resolve_output_path(args.conference, args.year_end, args.year_count, args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    papers = fetch_openreview_submissions(
        conference=args.conference,
        years=years,
        username=username,
        password=password,
        public_only=not bool(args.include_nonpublic),
    )
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(papers, f, ensure_ascii=False, indent=2)
    log(f"[OK] OpenReview 结果已写入：{output_path} count={len(papers)}")


if __name__ == "__main__":
    main()
