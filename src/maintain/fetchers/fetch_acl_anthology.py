#!/usr/bin/env python

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import requests
from bs4 import BeautifulSoup


SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0 Safari/537.36"


ACL_VOLUME_SPECS: Sequence[Tuple[str, str]] = (
    ("acl-long", "Long"),
    ("acl-short", "Short"),
    ("findings-acl", "Findings"),
)

EMNLP_VOLUME_SPECS: Sequence[Tuple[str, str]] = (
    ("emnlp-main", "Main"),
    ("findings-emnlp", "Findings"),
)


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _get(url: str, timeout: int = 60, retries: int = 3) -> str:
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
            log(f"[Anthology] retry {attempt}/{retries} url={url} error={exc}")
            time.sleep(float(attempt))
    if last_error is not None:
        raise last_error
    raise RuntimeError(f"request failed without explicit error: {url}")


def _meta_contents(soup: BeautifulSoup, name: str) -> List[str]:
    return [_norm(node.get("content")) for node in soup.select(f'meta[name="{name}"]') if _norm(node.get("content"))]


def _strip_abstract_prefix(text: str) -> str:
    raw = _norm(text)
    if raw.lower().startswith("abstract "):
        return raw[9:].strip()
    if raw.lower().startswith("abstract"):
        return raw[8:].strip()
    return raw


def iter_target_years(year_end: int, year_count: int) -> List[int]:
    safe_count = max(int(year_count or 1), 1)
    end_year = int(year_end)
    start_year = end_year - safe_count + 1
    return list(range(start_year, end_year + 1))


def _volume_url(volume_key: str, year: int) -> str:
    return f"https://aclanthology.org/volumes/{year}.{volume_key}/"


def _paper_url(href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return f"https://aclanthology.org{href}"


def collect_volume_paper_urls(volume_key: str, year: int) -> List[str]:
    url = _volume_url(volume_key, year)
    html = _get(url)
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    out: List[str] = []
    pattern = re.compile(rf"^/{year}\.{re.escape(volume_key)}\.(\d+)/?$")
    for a in soup.select("a[href]"):
        href = _norm(a.get("href"))
        match = pattern.match(href)
        if not match:
            continue
        paper_index = int(match.group(1))
        if paper_index <= 0:
            continue
        full_url = _paper_url(href)
        if full_url in seen:
            continue
        seen.add(full_url)
        out.append(full_url)
    return out


def _parse_publication_date(value: str) -> str:
    text = _norm(value)
    if not text:
        return ""
    for fmt in ("%Y/%m", "%Y/%m/%d", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return dt.isoformat()
        except ValueError:
            continue
    return ""


def fetch_anthology_paper(paper_url: str, *, source_label: str, primary_category: str) -> Dict[str, Any] | None:
    html = _get(paper_url)
    soup = BeautifulSoup(html, "html.parser")

    title_values = _meta_contents(soup, "citation_title")
    title = title_values[0] if title_values else _norm(soup.title.get_text(" ", strip=True) if soup.title else "")
    if title.endswith(" - ACL Anthology"):
        title = title[: -len(" - ACL Anthology")].strip()
    if not title:
        return None

    authors = _meta_contents(soup, "citation_author")
    published = ""
    for name in ("citation_publication_date", "citation_date", "DC.Date.issued", "DC.Date.created"):
        values = _meta_contents(soup, name)
        if values:
            published = _parse_publication_date(values[0])
            if published:
                break

    pdf_values = _meta_contents(soup, "citation_pdf_url")
    pdf_url = pdf_values[0] if pdf_values else ""
    abs_node = soup.select_one("#abstract") or soup.select_one(".acl-abstract") or soup.select_one("div.card-body.acl-abstract")
    abstract = _strip_abstract_prefix(abs_node.get_text(" ", strip=True) if abs_node else "")

    source_paper_id = paper_url.rstrip("/").split("/")[-1]
    return {
        "id": f"anthology-{source_paper_id}",
        "source": source_label,
        "source_paper_id": source_paper_id,
        "doi": "",
        "version": "",
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "primary_category": primary_category,
        "categories": [primary_category],
        "published": published or None,
        "link": paper_url,
        "pdf_url": pdf_url or None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def fetch_anthology_conference(
    *,
    conference: str,
    year_end: int,
    year_count: int,
    volume_specs: Sequence[Tuple[str, str]],
    output: str,
    workers: int = 32,
) -> None:
    years = iter_target_years(year_end, year_count)
    all_papers: List[Dict[str, Any]] = []
    seen_ids = set()
    log(f"[Anthology] conference={conference} years={years}")
    for year in years:
        for volume_key, label in volume_specs:
            volume_url = _volume_url(volume_key, year)
            log(f"[Anthology] volume={volume_url}")
            paper_urls = collect_volume_paper_urls(volume_key, year)
            log(f"[Anthology] volume papers={len(paper_urls)}")
            source_label = f"{conference}-{year}-{label}"
            primary_category = f"{conference}-{year}-{label}"
            completed = 0
            with ThreadPoolExecutor(max_workers=max(int(workers or 1), 1)) as executor:
                futures = {
                    executor.submit(
                        fetch_anthology_paper,
                        paper_url,
                        source_label=source_label,
                        primary_category=primary_category,
                    ): paper_url
                    for paper_url in paper_urls
                }
                for future in as_completed(futures):
                    completed += 1
                    paper = future.result()
                    if paper:
                        pid = _norm(paper.get("id"))
                        if pid and pid not in seen_ids:
                            seen_ids.add(pid)
                            all_papers.append(paper)
                    if completed == 1 or completed % 200 == 0 or completed == len(paper_urls):
                        log(f"[Anthology] {conference} {year} {label} progress={completed}/{len(paper_urls)}")

    out_path = _norm(output)
    if not out_path:
        token = f"{conference.lower()}-anthology-{year_end - year_count + 1}-{year_end}"
        out_path = os.path.join(ROOT_DIR, "archive", TODAY_STR, "raw", f"{token}.json")
    elif not os.path.isabs(out_path):
        out_path = os.path.abspath(os.path.join(ROOT_DIR, out_path))
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_papers, f, ensure_ascii=False, indent=2)
    log(f"[OK] Anthology 结果已写入：{out_path} count={len(all_papers)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取 ACL Anthology accepted 论文。")
    parser.add_argument("--conference", type=str, choices=["ACL", "EMNLP"], default="ACL")
    parser.add_argument("--year-end", type=int, default=datetime.now(timezone.utc).year)
    parser.add_argument("--year-count", type=int, default=3)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    conference = _norm(args.conference).upper()
    if conference == "ACL":
        volume_specs = ACL_VOLUME_SPECS
    else:
        volume_specs = EMNLP_VOLUME_SPECS
    fetch_anthology_conference(
        conference=conference,
        year_end=args.year_end,
        year_count=args.year_count,
        volume_specs=volume_specs,
        output=args.output,
        workers=args.workers,
    )


if __name__ == "__main__":
    main()
