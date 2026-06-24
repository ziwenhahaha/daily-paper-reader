#!/usr/bin/env python
"""Fetch accepted papers from IJCAI Proceedings pages.

List page : https://www.ijcai.org/proceedings/{year}/
Detail page: https://www.ijcai.org/proceedings/{year}/{paper_num}
PDF URL    : https://www.ijcai.org/proceedings/{year}/{paper_num:04d}.pdf

Each paper on the list page lives inside a `.paper_wrapper` element that
contains a `.title`, `.details` (authors), and an anchor whose href ends
with ".pdf".  An optional `.abstract` element may carry the abstract text
directly; when it is absent we fall back to scraping the individual detail
page.
"""

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

# ---------------------------------------------------------------------------
# Path bootstrapping – keeps imports working when invoked directly.
# ---------------------------------------------------------------------------
SRC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/133.0 Safari/537.36"
)

BASE_URL = "https://www.ijcai.org/proceedings"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(message: str) -> None:
    """Print a timestamped log line to stdout (unbuffered)."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def _norm(value: Any) -> str:
    """Normalise a value to a stripped string."""
    return str(value or "").strip()


def _get(url: str, timeout: int = 30, retries: int = 3) -> str:
    """GET *url* and return the response body, retrying on failure."""
    last_error: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.get(
                url, headers={"User-Agent": USER_AGENT}, timeout=timeout
            )
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            last_error = exc
            if attempt >= retries:
                break
            log(f"request retry {attempt}/{retries} url={url} error={exc}")
    raise last_error  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Paper‑number extraction
# ---------------------------------------------------------------------------

_PDF_NUM_RE = re.compile(r"/(\d+)\.pdf$", re.IGNORECASE)
_DETAIL_NUM_RE = re.compile(r"/proceedings/\d{4}/(\d+)/?$", re.IGNORECASE)


def _extract_paper_num(pdf_url: str, detail_url: Optional[str] = None) -> Optional[int]:
    """Return the integer paper number from a PDF or detail URL."""
    m = _PDF_NUM_RE.search(pdf_url)
    if m:
        return int(m.group(1))
    if detail_url:
        m = _DETAIL_NUM_RE.search(detail_url)
        if m:
            return int(m.group(1))
    return None


# ---------------------------------------------------------------------------
# Abstract fetching (detail page fallback)
# ---------------------------------------------------------------------------

def _fetch_abstract_from_detail(detail_url: str) -> str:
    """Scrape the abstract from an individual paper's detail page."""
    try:
        html = _get(detail_url)
        soup = BeautifulSoup(html, "html.parser")
        abstract_el = soup.select_one(".abstract")
        if abstract_el:
            return _norm(abstract_el.get_text(separator=" "))
    except Exception as exc:
        log(f"failed to fetch abstract from {detail_url}: {exc}")
    return ""


# ---------------------------------------------------------------------------
# Single‑paper parser
# ---------------------------------------------------------------------------

def _parse_paper(
    wrapper,
    year: int,
    fetch_abstracts: bool = True,
) -> Optional[Dict[str, Any]]:
    """Parse one `.paper_wrapper` element and return a paper dict."""

    # --- title ---------------------------------------------------------------
    title_el = wrapper.select_one(".title")
    title = _norm(title_el.get_text()) if title_el else ""
    if not title:
        return None

    # --- authors -------------------------------------------------------------
    details_el = wrapper.select_one(".details")
    raw_authors = _norm(details_el.get_text()) if details_el else ""
    # Authors are typically comma‑separated; some years use " and " as well.
    authors: List[str] = []
    if raw_authors:
        # Normalise " and " to comma so we can split uniformly.
        raw_authors = re.sub(r"\s+and\s+", ", ", raw_authors)
        authors = [a.strip() for a in raw_authors.split(",") if a.strip()]

    # --- PDF URL & paper number -----------------------------------------------
    pdf_anchor = wrapper.select_one('a[href$=".pdf"]')
    if pdf_anchor is None:
        return None

    pdf_href = pdf_anchor.get("href", "")
    if pdf_href.startswith("/"):
        pdf_url = f"https://www.ijcai.org{pdf_href}"
    elif pdf_href.startswith("http"):
        pdf_url = pdf_href
    else:
        pdf_url = f"{BASE_URL}/{year}/{pdf_href}"

    # Try to find a detail link (any anchor whose href matches /proceedings/YYYY/NUM).
    detail_url: Optional[str] = None
    for a_tag in wrapper.find_all("a", href=True):
        href = a_tag["href"]
        if _DETAIL_NUM_RE.search(href):
            detail_url = href if href.startswith("http") else f"https://www.ijcai.org{href}"
            break

    paper_num = _extract_paper_num(pdf_url, detail_url)
    if paper_num is None:
        return None

    # --- abstract (inline first, then detail page) ----------------------------
    abstract = ""
    abstract_el = wrapper.select_one(".abstract")
    if abstract_el:
        abstract = _norm(abstract_el.get_text(separator=" "))

    if not abstract and fetch_abstracts:
        target = detail_url or f"{BASE_URL}/{year}/{paper_num}"
        abstract = _fetch_abstract_from_detail(target)

    # --- build record --------------------------------------------------------
    return {
        "id": f"ijcai-{year}-{paper_num}",
        "source": f"IJCAI-{year}-Accepted",
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "primary_category": f"IJCAI-{year}",
        "categories": [f"IJCAI-{year}"],
        "published": f"{year}-08-01T00:00:00+00:00",
        "link": f"{BASE_URL}/{year}/{paper_num}",
        "pdf_url": f"{BASE_URL}/{year}/{paper_num:04d}.pdf",
    }


# ---------------------------------------------------------------------------
# Year‑level fetching
# ---------------------------------------------------------------------------

def fetch_year(
    year: int,
    workers: int = 4,
    fetch_abstracts: bool = True,
) -> List[Dict[str, Any]]:
    """Fetch all papers for a single IJCAI proceedings year."""

    list_url = f"{BASE_URL}/{year}/"
    log(f"fetching list page: {list_url}")

    try:
        html = _get(list_url)
    except Exception as exc:
        log(f"ERROR: could not fetch list page for {year}: {exc}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    wrappers = soup.select(".paper_wrapper")
    log(f"year={year}: found {len(wrappers)} paper wrappers")

    if not wrappers:
        return []

    papers: List[Dict[str, Any]] = []

    def _process(wrapper_idx: int):
        wrapper = wrappers[wrapper_idx]
        try:
            return _parse_paper(wrapper, year, fetch_abstracts=fetch_abstracts)
        except Exception as exc:
            log(f"year={year} wrapper#{wrapper_idx}: unexpected error – {exc}")
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_process, idx): idx for idx in range(len(wrappers))
        }
        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                if result is not None:
                    papers.append(result)
            except Exception as exc:
                log(f"year={year} wrapper#{idx}: future raised – {exc}")

    # Deterministic ordering by paper number.
    papers.sort(key=lambda p: p["id"])
    log(f"year={year}: collected {len(papers)} papers")
    return papers


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def save_output(
    rows: List[Dict[str, Any]],
    output_path: Optional[str],
    default_name: str,
) -> str:
    """Write *rows* to a JSON file and return the path used."""
    if output_path:
        path = output_path
    else:
        output_dir = os.path.join(ROOT_DIR, "output")
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, default_name)

    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)

    with open(path, "w", encoding="utf-8") as fh:
        json.dump(rows, fh, ensure_ascii=False, indent=2)

    log(f"saved {len(rows)} papers → {path}")
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch accepted papers from IJCAI Proceedings."
    )
    parser.add_argument(
        "--years",
        type=str,
        required=True,
        help="Comma-separated list of years to scrape, e.g. '2023,2024'.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON file path (default: output/ijcai_{years}_{date}.json).",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent threads for abstract fetching (default: 4).",
    )
    parser.add_argument(
        "--no-abstracts",
        action="store_true",
        default=False,
        help="Skip fetching abstracts from detail pages.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]
    if not years:
        log("ERROR: no valid years specified")
        sys.exit(1)

    log(f"IJCAI fetcher starting – years={years}, workers={args.workers}")

    all_papers: List[Dict[str, Any]] = []
    for year in sorted(years):
        papers = fetch_year(
            year,
            workers=args.workers,
            fetch_abstracts=not args.no_abstracts,
        )
        all_papers.extend(papers)

    if not all_papers:
        log("WARNING: no papers collected across all years")

    years_tag = "_".join(str(y) for y in sorted(years))
    default_name = f"ijcai_{years_tag}_{TODAY_STR}.json"
    save_output(all_papers, args.output, default_name)

    log(f"done – {len(all_papers)} total papers")


if __name__ == "__main__":
    main()
