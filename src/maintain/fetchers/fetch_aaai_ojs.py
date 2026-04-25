#!/usr/bin/env python

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import requests
from bs4 import BeautifulSoup

SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
ARCHIVE_URL = "https://ojs.aaai.org/index.php/AAAI/issue/archive"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0 Safari/537.36"
ISSUE_TITLE_RE = re.compile(r"\bAAAI-(\d{2})\b", re.IGNORECASE)
ARTICLE_ID_RE = re.compile(r"/article/view/(\d+)")


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def build_target_years(year_end: int, year_count: int) -> List[int]:
    safe_count = max(int(year_count or 1), 1)
    end_year = int(year_end)
    start_year = end_year - safe_count + 1
    return list(range(start_year, end_year + 1))


def build_source_label(year: int) -> str:
    return f"AAAI-{int(year)}-Accepted"


def _get(url: str, timeout: int = 30, retries: int = 3) -> str:
    last_error: Exception | None = None
    for attempt in range(1, max(int(retries or 1), 1) + 1):
        try:
            resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=max(int(timeout or 1), 1))
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            last_error = exc
            if attempt >= max(int(retries or 1), 1):
                break
            log(f"[AAAI] request retry {attempt}/{retries} url={url} error={exc}")
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"request failed without explicit error: {url}")


def extract_issue_year(title: str) -> Optional[int]:
    match = ISSUE_TITLE_RE.search(_norm(title))
    if not match:
        return None
    return 2000 + int(match.group(1))


def is_target_issue_title(title: str, target_years: Iterable[int]) -> bool:
    year = extract_issue_year(title)
    if year is None:
        return False
    if year not in set(int(y) for y in target_years):
        return False
    return "technical tracks" in _norm(title).lower()


def collect_target_issue_urls(target_years: Iterable[int], max_pages: int = 12) -> List[Dict[str, Any]]:
    wanted_years = {int(y) for y in target_years}
    min_wanted_year = min(wanted_years) if wanted_years else 0
    page_index = 1
    next_url = ARCHIVE_URL
    collected: List[Dict[str, Any]] = []
    seen_urls = set()

    while next_url and page_index <= max(int(max_pages or 1), 1):
        log(f"[AAAI] archive page={page_index} url={next_url}")
        soup = BeautifulSoup(_get(next_url), "html.parser")
        issues = soup.select("div.obj_issue_summary")
        if not issues:
            break
        page_years = []
        for issue in issues:
            title_node = issue.select_one("a.title")
            title = _norm(title_node.get_text(" ", strip=True) if title_node else "")
            href = _norm(title_node.get("href") if title_node else "")
            year = extract_issue_year(title)
            if not href or href in seen_urls or year is None:
                continue
            page_years.append(year)
            if not is_target_issue_title(title, wanted_years):
                continue
            seen_urls.add(href)
            collected.append({"title": title, "url": href, "year": year})

        next_link = None
        for anchor in soup.select("a[href]"):
            if _norm(anchor.get_text(" ", strip=True)).lower() == "next":
                next_link = _norm(anchor.get("href"))
                break
        if page_years and max(page_years) < min_wanted_year:
            break
        next_url = next_link
        page_index += 1

    collected.sort(key=lambda item: (int(item.get("year") or 0), _norm(item.get("title"))))
    return collected


def _extract_article_id(url: str) -> str:
    match = ARTICLE_ID_RE.search(_norm(url))
    return _norm(match.group(1) if match else "")


def _parse_authors_text(text: str) -> List[str]:
    raw = _norm(text)
    if not raw:
        return []
    return [_norm(item) for item in raw.split(",") if _norm(item)]


def collect_issue_article_summaries(issue: Dict[str, Any]) -> List[Dict[str, Any]]:
    issue_url = _norm(issue.get("url"))
    issue_title = _norm(issue.get("title"))
    year = int(issue.get("year") or 0)
    if not issue_url or not year:
        return []

    soup = BeautifulSoup(_get(issue_url), "html.parser")
    summaries: List[Dict[str, Any]] = []
    for item in soup.select("div.obj_article_summary"):
        title_node = item.select_one("h3.title a")
        article_url = _norm(title_node.get("href") if title_node else "")
        article_id = _extract_article_id(article_url)
        title = _norm(title_node.get_text(" ", strip=True) if title_node else "")
        authors_node = item.select_one(".authors")
        authors = _parse_authors_text(authors_node.get_text(" ", strip=True) if authors_node else "")
        pdf_node = item.select_one("a.obj_galley_link.pdf")
        pdf_url = _norm(pdf_node.get("href") if pdf_node else "")
        if not article_id or not article_url or not title:
            continue
        summaries.append(
            {
                "article_id": article_id,
                "article_url": article_url,
                "issue_title": issue_title,
                "year": year,
                "title": title,
                "authors": authors,
                "pdf_url": pdf_url,
            }
        )
    return summaries


def _meta_contents(soup: BeautifulSoup, name: str) -> List[str]:
    return [_norm(node.get("content")) for node in soup.select(f'meta[name="{name}"]') if _norm(node.get("content"))]


def _normalize_date_to_iso(value: str) -> str:
    text = _norm(value)
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).isoformat()
        except ValueError:
            continue
    return ""


def fetch_article_detail(summary: Dict[str, Any]) -> Dict[str, Any] | None:
    article_url = _norm(summary.get("article_url"))
    article_id = _norm(summary.get("article_id"))
    year = int(summary.get("year") or 0)
    issue_title = _norm(summary.get("issue_title"))
    if not article_url or not article_id or not year:
        return None

    soup = BeautifulSoup(_get(article_url), "html.parser")
    title = (_meta_contents(soup, "citation_title") or [_norm(summary.get("title"))])[0]
    if not title:
        return None
    authors = _meta_contents(soup, "citation_author") or list(summary.get("authors") or [])
    abstract = ""
    for key in ("DC.Description", "dc.Description", "description"):
        values = _meta_contents(soup, key)
        if values:
            abstract = values[0]
            break
    if not abstract:
        abs_node = soup.select_one(".item.abstract") or soup.select_one(".article-details-abstract")
        abstract = _norm(abs_node.get_text(" ", strip=True) if abs_node else "")
        if abstract.lower().startswith("abstract "):
            abstract = abstract[9:].strip()

    published = ""
    for key in ("DC.Date.issued", "citation_date", "DC.Date.created"):
        values = _meta_contents(soup, key)
        if values:
            published = _normalize_date_to_iso(values[0])
            if published:
                break
    if not published:
        published = datetime(year, 1, 1, tzinfo=timezone.utc).isoformat()

    pdf_url = (_meta_contents(soup, "citation_pdf_url") or [_norm(summary.get("pdf_url"))])[0]
    doi = (_meta_contents(soup, "citation_doi") or [""])[0]
    source = build_source_label(year)
    return {
        "id": f"aaai-{year}-{article_id}",
        "source": source,
        "source_paper_id": article_id,
        "doi": doi,
        "version": "",
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "primary_category": issue_title or f"AAAI-{year}",
        "categories": [f"AAAI-{year}", issue_title] if issue_title else [f"AAAI-{year}"],
        "published": published,
        "link": article_url,
        "pdf_url": pdf_url,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_aaai_ojs_papers(years: Iterable[int], workers: int = 12) -> List[Dict[str, Any]]:
    issue_items = collect_target_issue_urls(years)
    if not issue_items:
        return []
    log(f"[AAAI] issues={len(issue_items)} target_years={list(years)}")

    summaries: List[Dict[str, Any]] = []
    seen_article_ids = set()
    for issue in issue_items:
        items = collect_issue_article_summaries(issue)
        log(
            f"[AAAI] issue={issue['title']} year={issue['year']} "
            f"articles={len(items)}"
        )
        for item in items:
            aid = _norm(item.get("article_id"))
            if not aid or aid in seen_article_ids:
                continue
            seen_article_ids.add(aid)
            summaries.append(item)

    if not summaries:
        return []

    papers: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(int(workers or 1), 1)) as executor:
        future_map = {
            executor.submit(fetch_article_detail, summary): summary
            for summary in summaries
        }
        completed = 0
        total = len(future_map)
        for future in as_completed(future_map):
            completed += 1
            paper = future.result()
            if paper:
                papers.append(paper)
            if completed == 1 or completed % 200 == 0 or completed == total:
                log(f"[AAAI] article details progress={completed}/{total}")

    papers.sort(key=lambda item: (_norm(item.get("published")), _norm(item.get("id"))))
    return papers


def save_output(rows: List[Dict[str, Any]], output_path: str) -> str:
    out_path = _norm(output_path)
    if out_path:
        if not os.path.isabs(out_path):
            out_path = os.path.abspath(os.path.join(ROOT_DIR, out_path))
    else:
        out_path = os.path.join(ROOT_DIR, "archive", TODAY_STR, "raw", f"aaai_papers_{TODAY_STR}.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 AAAI 官方 OJS proceedings 论文（accepted only）。")
    parser.add_argument("--year-end", type=int, default=datetime.now(timezone.utc).year)
    parser.add_argument("--year-count", type=int, default=3)
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    years = build_target_years(args.year_end, args.year_count)
    log(f"[AAAI] start years={years}")
    rows = fetch_aaai_ojs_papers(years=years, workers=args.workers)
    out_path = save_output(rows, args.output)
    log(f"[OK] AAAI OJS 结果已写入：{out_path} count={len(rows)}")


if __name__ == "__main__":
    main()
