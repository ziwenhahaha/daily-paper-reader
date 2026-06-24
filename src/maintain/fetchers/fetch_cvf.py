#!/usr/bin/env python
"""Fetch accepted papers from CVF Open Access (CVPR) and ECVA (ECCV).

CVPR list page : https://openaccess.thecvf.com/CVPR{year}?day=all
ECCV list page : https://www.ecva.net/papers.php

List-page structure
-------------------
    <dt class="ptitle">
      <a href="...html">Paper Title</a>
    </dt>
    <dd>
      <a href="...paper.pdf">pdf</a>   ← first <a> whose href ends with ".pdf"
      ...
    </dd>

Detail pages carry the abstract in
    <meta name="citation_abstract" content="...">
or inside a <div id="abstract"> block.
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
# Path helpers (same convention as the AAAI fetcher)
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

# ---------------------------------------------------------------------------
# Conference base URLs
# ---------------------------------------------------------------------------
CVF_BASE = "https://openaccess.thecvf.com"
ECVA_BASE = "https://www.ecva.net"

# ECCV is biennial – valid years are even numbers starting from 2018
ECCV_FIRST_YEAR = 2018

# Rough opening dates (month-day) used as the ``published`` timestamp when the
# exact date is unknown.  We fall back to June 1 for CVPR and October 1 for
# ECCV.
_CONF_MONTH: Dict[str, int] = {"CVPR": 6, "ECCV": 10}


# ── Logging ────────────────────────────────────────────────────────────────
def log(msg: str) -> None:
    """Print a timestamped log line to *stderr*."""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stderr, flush=True)


# ── Text helpers ───────────────────────────────────────────────────────────
def _norm(text: str) -> str:
    """Collapse whitespace and strip surrounding blanks."""
    return re.sub(r"\s+", " ", text).strip()


def _slugify(text: str) -> str:
    """Turn a title or URL fragment into a lowercase slug suitable for IDs."""
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text)
    return text.strip("-").lower()


# ── HTTP helper with retries ──────────────────────────────────────────────
def _get(
    url: str,
    *,
    retries: int = 3,
    timeout: int = 30,
    session: Optional[requests.Session] = None,
) -> requests.Response:
    """GET *url* with automatic retries on transient failures."""
    requester = session or requests
    for attempt in range(1, retries + 1):
        try:
            resp = requester.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            )
            resp.raise_for_status()
            return resp
        except requests.RequestException as exc:
            if attempt == retries:
                raise
            log(f"  retry {attempt}/{retries} for {url}: {exc}")
    # Unreachable, but keeps mypy happy.
    raise RuntimeError("unreachable")


# ── Save output ───────────────────────────────────────────────────────────
def save_output(papers: List[Dict[str, Any]], path: str) -> None:
    """Write *papers* list as pretty-printed JSON to *path*."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(papers, fh, indent=2, ensure_ascii=False)
    log(f"Saved {len(papers)} papers → {path}")


# =====================================================================
#  CVPR helpers
# =====================================================================

def _cvpr_list_url(year: int) -> str:
    return f"{CVF_BASE}/CVPR{year}?day=all"


def _parse_cvpr_list(html: str, year: int) -> List[Dict[str, str]]:
    """Return ``[{title, detail_url, pdf_url}, ...]`` from the CVPR list page."""
    soup = BeautifulSoup(html, "html.parser")
    entries: List[Dict[str, str]] = []

    for dt in soup.find_all("dt", class_="ptitle"):
        a_title = dt.find("a")
        if not a_title:
            continue
        title = _norm(a_title.get_text())
        href = a_title.get("href", "")
        detail_url = href if href.startswith("http") else f"{CVF_BASE}/{href.lstrip('/')}"

        # The next <dd> sibling contains the PDF link.
        dd = dt.find_next_sibling("dd")
        pdf_url = ""
        if dd:
            pdf_a = dd.find("a", href=re.compile(r"\.pdf$", re.I))
            if pdf_a:
                pdf_href = pdf_a["href"]
                pdf_url = (
                    pdf_href
                    if pdf_href.startswith("http")
                    else f"{CVF_BASE}/{pdf_href.lstrip('/')}"
                )

        entries.append(
            {"title": title, "detail_url": detail_url, "pdf_url": pdf_url}
        )

    return entries


# =====================================================================
#  ECCV helpers
# =====================================================================

def _eccv_list_url() -> str:
    return f"{ECVA_BASE}/papers.php"


def _parse_eccv_list(html: str, year: int) -> List[Dict[str, str]]:
    """Return ``[{title, detail_url, pdf_url}, ...]`` for a specific ECCV *year*.

    The ECVA papers page lists *all* years on one page.  We filter entries by
    checking whether the PDF URL or detail URL contains the target year string.
    """
    soup = BeautifulSoup(html, "html.parser")
    entries: List[Dict[str, str]] = []
    year_str = str(year)

    for dt in soup.find_all("dt", class_="ptitle"):
        a_title = dt.find("a")
        if not a_title:
            continue

        href = a_title.get("href", "")
        # Filter for the requested year.
        if year_str not in href:
            continue

        title = _norm(a_title.get_text())
        detail_url = href if href.startswith("http") else f"{ECVA_BASE}/{href.lstrip('/')}"

        dd = dt.find_next_sibling("dd")
        pdf_url = ""
        if dd:
            pdf_a = dd.find("a", href=re.compile(r"\.pdf$", re.I))
            if pdf_a:
                pdf_href = pdf_a["href"]
                pdf_url = (
                    pdf_href
                    if pdf_href.startswith("http")
                    else f"{ECVA_BASE}/{pdf_href.lstrip('/')}"
                )

        entries.append(
            {"title": title, "detail_url": detail_url, "pdf_url": pdf_url}
        )

    return entries


# =====================================================================
#  Detail-page parser (shared by both conferences)
# =====================================================================

def _fetch_detail(
    url: str,
    session: requests.Session,
) -> Dict[str, Any]:
    """Scrape a detail / HTML page and return abstract + authors."""
    resp = _get(url, session=session)
    soup = BeautifulSoup(resp.text, "html.parser")

    # -- abstract ----------------------------------------------------------
    abstract = ""
    meta_abs = soup.find("meta", attrs={"name": "citation_abstract"})
    if meta_abs and meta_abs.get("content"):
        abstract = _norm(meta_abs["content"])

    if not abstract:
        div_abs = soup.find("div", id="abstract")
        if div_abs:
            abstract = _norm(div_abs.get_text())

    # -- authors -----------------------------------------------------------
    authors: List[str] = []
    for meta_a in soup.find_all("meta", attrs={"name": "citation_author"}):
        name = meta_a.get("content", "").strip()
        if name:
            authors.append(name)

    # Fallback: look for an <i> element right after the title heading
    if not authors:
        author_i = soup.find("div", id="authors")
        if author_i:
            raw = _norm(author_i.get_text())
            authors = [a.strip() for a in raw.split(",") if a.strip()]

    return {"abstract": abstract, "authors": authors}


# =====================================================================
#  Build a single paper record
# =====================================================================

def _slug_from_url(url: str) -> str:
    """Extract a slug from the paper URL (last path component minus extension)."""
    basename = url.rstrip("/").rsplit("/", 1)[-1]
    basename = re.sub(r"\.(html|pdf)$", "", basename, flags=re.I)
    return _slugify(basename)


def _build_paper(
    entry: Dict[str, str],
    conf: str,
    year: int,
    session: requests.Session,
) -> Optional[Dict[str, Any]]:
    """Fetch the detail page and assemble the final paper dict.

    Returns *None* on unrecoverable per-paper errors so the caller can skip it
    without aborting the whole run.
    """
    title = entry["title"]
    detail_url = entry["detail_url"]
    pdf_url = entry["pdf_url"]
    conf_upper = conf.upper()
    conf_lower = conf.lower()

    slug = _slug_from_url(detail_url) or _slug_from_url(pdf_url) or _slugify(title)

    try:
        detail = _fetch_detail(detail_url, session)
    except Exception as exc:
        log(f"  ✗ detail page failed for \"{title}\": {exc}")
        detail = {"abstract": "", "authors": []}

    month = _CONF_MONTH.get(conf_upper, 1)
    published = f"{year}-{month:02d}-01T00:00:00+00:00"

    return {
        "id": f"{conf_lower}-{year}-{slug}",
        "source": f"{conf_upper}-{year}-Accepted",
        "title": title,
        "abstract": detail["abstract"],
        "authors": detail["authors"],
        "primary_category": f"{conf_upper}-{year}",
        "categories": [f"{conf_upper}-{year}"],
        "published": published,
        "link": detail_url,
        "pdf_url": pdf_url,
    }


# =====================================================================
#  Per-conference fetch entry points
# =====================================================================

def fetch_cvpr(year: int, workers: int) -> List[Dict[str, Any]]:
    """Fetch all CVPR papers for *year*."""
    url = _cvpr_list_url(year)
    log(f"Fetching CVPR {year} list: {url}")

    resp = _get(url)
    entries = _parse_cvpr_list(resp.text, year)
    log(f"  Found {len(entries)} papers on list page")

    if not entries:
        return []

    papers: List[Dict[str, Any]] = []
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_build_paper, e, "CVPR", year, session): e
            for e in entries
        }
        for i, future in enumerate(as_completed(futures), 1):
            try:
                paper = future.result()
                if paper is not None:
                    papers.append(paper)
            except Exception as exc:
                entry = futures[future]
                log(f"  ✗ [{i}/{len(entries)}] {entry['title']}: {exc}")
                continue
            if i % 50 == 0 or i == len(entries):
                log(f"  progress: {i}/{len(entries)}")

    log(f"  Collected {len(papers)} CVPR-{year} papers")
    return papers


def fetch_eccv(year: int, workers: int) -> List[Dict[str, Any]]:
    """Fetch all ECCV papers for *year*.

    ECCV is biennial.  If *year* is odd the function returns an empty list and
    prints a warning.
    """
    if year % 2 != 0:
        log(f"ECCV {year}: skipped (ECCV is biennial; only even years)")
        return []

    url = _eccv_list_url()
    log(f"Fetching ECCV {year} list: {url}")

    resp = _get(url)
    entries = _parse_eccv_list(resp.text, year)
    log(f"  Found {len(entries)} papers for ECCV {year}")

    if not entries:
        return []

    papers: List[Dict[str, Any]] = []
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_build_paper, e, "ECCV", year, session): e
            for e in entries
        }
        for i, future in enumerate(as_completed(futures), 1):
            try:
                paper = future.result()
                if paper is not None:
                    papers.append(paper)
            except Exception as exc:
                entry = futures[future]
                log(f"  ✗ [{i}/{len(entries)}] {entry['title']}: {exc}")
                continue
            if i % 50 == 0 or i == len(entries):
                log(f"  progress: {i}/{len(entries)}")

    log(f"  Collected {len(papers)} ECCV-{year} papers")
    return papers


# =====================================================================
#  CLI
# =====================================================================

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch accepted papers from CVF (CVPR) or ECVA (ECCV).",
    )
    parser.add_argument(
        "--conference",
        type=str,
        required=True,
        choices=["CVPR", "ECCV"],
        help="Conference to fetch: CVPR or ECCV.",
    )
    parser.add_argument(
        "--years",
        type=str,
        required=True,
        help="Comma-separated list of years, e.g. '2023,2024,2025'.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Output JSON path.  Defaults to <ROOT>/data/<conf>_<years>_<date>.json",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="Number of concurrent workers for detail-page fetches (default: 8).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)
    conf: str = args.conference.upper()
    years = [int(y.strip()) for y in args.years.split(",") if y.strip()]
    workers: int = args.workers

    all_papers: List[Dict[str, Any]] = []

    for year in sorted(years):
        if conf == "CVPR":
            papers = fetch_cvpr(year, workers)
        else:
            papers = fetch_eccv(year, workers)
        all_papers.extend(papers)

    # Determine output path
    output = args.output
    if not output:
        years_tag = "_".join(str(y) for y in sorted(years))
        output = os.path.join(
            ROOT_DIR, "data", f"{conf.lower()}_{years_tag}_{TODAY_STR}.json"
        )

    save_output(all_papers, output)
    log("Done.")


if __name__ == "__main__":
    main()
