#!/usr/bin/env python
"""Fetch public-paper metadata for OSDI, SOSP, IEEE S&P, and NDSS."""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup


USER_AGENT = "daily-paper-reader/1.0 (+https://github.com/ziwenhahaha/daily-paper-reader)"
DEFAULT_TIMEOUT = 30

OSDI_LIST_URL = "https://www.usenix.org/conference/osdi{short_year}/technical-sessions"
NDSS_LIST_URL = "https://www.ndss-symposium.org/ndss{year}/accepted-papers/"
SOSP_ACCEPTED_URL = "https://sigops.org/s/conferences/sosp/{year}/accepted.html"
IEEE_SP_ACCEPTED_URL = "https://sp{year}.ieee-security.org/accepted-papers.html"
IEEE_SP_PROCEEDINGS = {
    2024: "1RjE8VKKk1y",
    2025: "21B7ONGXzZ6",
}
IEEE_SP_GRAPHQL_URL = "https://www.computer.org/csdl/api/v1/graphql"
SEMANTIC_SCHOLAR_BATCH_URL = "https://api.semanticscholar.org/graph/v1/paper/batch"
ARXIV_API_URL = "https://export.arxiv.org/api/query"
ARXIV_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", html.unescape(str(value or ""))).strip()


def _slugify(value: Any, fallback: str = "paper") -> str:
    text = _norm(value).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    return text[:120] or fallback


def _title_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _norm(value).lower())


def _title_prefix(value: Any) -> str:
    title = _norm(value)
    if ":" not in title:
        return ""
    prefix = title.split(":", 1)[0]
    return _title_key(prefix) if len(prefix) >= 3 else ""


def _title_without_prefix_key(value: Any) -> str:
    title = _norm(value)
    if ":" not in title:
        return _title_key(title)
    suffix = title.split(":", 1)[1]
    return _title_key(suffix) or _title_key(title)


def _title_matches(a: Any, b: Any) -> bool:
    ak = _title_key(a)
    bk = _title_key(b)
    if not ak or not bk:
        return False
    if ak == bk:
        return True
    return _title_without_prefix_key(a) == bk or _title_without_prefix_key(b) == ak


def _absolute_url(url: str, base: str) -> str:
    return urljoin(base, _norm(url))


def _published_iso(year: int, month: int = 1, day: int = 1) -> str:
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d}T00:00:00Z"


def _parse_meta_date(value: str, fallback_year: int) -> str:
    text = _norm(value)
    match = re.search(r"((?:19|20)\d{2})[-/](\d{1,2})[-/](\d{1,2})", text)
    if match:
        return _published_iso(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    match = re.search(r"((?:19|20)\d{2})", text)
    if match:
        return _published_iso(int(match.group(1)))
    return _published_iso(fallback_year)


def _split_authors(value: Any) -> List[str]:
    text = _norm(value)
    if not text:
        return []
    parenthesized = [
        _norm(match.group(1))
        for match in re.finditer(r"([^,;()]+?)\s*\([^)]*\)(?=\s*(?:,|;|$))", text)
        if _norm(match.group(1))
    ]
    if parenthesized:
        authors: List[str] = []
        for item in parenthesized:
            if item not in authors:
                authors.append(item)
        return authors
    text = re.sub(r"\s+and\s+", ", ", text)
    parts = re.split(r"\)\s*,|\s*;\s*", text)
    if len(parts) <= 1:
        parts = text.split(",")
    authors: List[str] = []
    for part in parts:
        item = _norm(part)
        item = re.sub(r"\s*\([^)]*\)\s*$", "", item).strip()
        if item and item not in authors:
            authors.append(item)
    return authors


def _request_text(url: str) -> str:
    last_exc: Exception | None = None
    for attempt in range(3):
        try:
            res = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=DEFAULT_TIMEOUT)
            res.raise_for_status()
            if not res.encoding or res.encoding.lower() == "iso-8859-1":
                res.encoding = res.apparent_encoding or "utf-8"
            return res.text
        except Exception as exc:
            last_exc = exc
            if attempt < 2:
                time.sleep(1.5 * (attempt + 1))
    assert last_exc is not None
    raise last_exc


def _write_json(path: str, rows: List[Dict[str, Any]]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
        f.write("\n")


def _paper_id(prefix: str, year: int, title: str) -> str:
    return f"{prefix}-{int(year)}-{_slugify(title)}"


def _clean_paper(row: Dict[str, Any]) -> Dict[str, Any]:
    row["title"] = _norm(row.get("title"))
    row["abstract"] = _norm(row.get("abstract"))
    row["authors"] = [a for a in (_norm(x) for x in row.get("authors") or []) if a]
    row["categories"] = [c for c in (_norm(x) for x in row.get("categories") or []) if c]
    if not row.get("primary_category"):
        row["primary_category"] = row["categories"][0] if row["categories"] else "conference"
    return row


def parse_osdi_paper_page(html_text: str, *, year: int, page_url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html_text, "html.parser")
    title = _norm((soup.find("meta", attrs={"name": "citation_title"}) or {}).get("content"))
    if not title:
        title = _norm(soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "")
    authors = [
        _norm(meta.get("content"))
        for meta in soup.find_all("meta", attrs={"name": "citation_author"})
        if _norm(meta.get("content"))
    ]
    pdf_url = _norm((soup.find("meta", attrs={"name": "citation_pdf_url"}) or {}).get("content"))
    abstract = _norm((soup.find("meta", attrs={"name": "citation_abstract"}) or {}).get("content"))
    if not abstract:
        abstract_node = (
            soup.select_one(".field-name-field-paper-description")
            or soup.select_one(".field--name-field-paper-description")
            or soup.select_one(".field-name-body")
        )
        abstract = _norm(abstract_node.get_text(" ", strip=True) if abstract_node else "")
    published = _parse_meta_date(
        _norm((soup.find("meta", attrs={"name": "citation_publication_date"}) or {}).get("content")),
        year,
    )
    return _clean_paper(
        {
            "id": _paper_id("osdi", year, title or page_url),
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "published": published,
            "link": page_url,
            "pdf_url": pdf_url,
            "source": f"OSDI-{int(year)}-USENIX",
            "primary_category": "osdi",
            "categories": ["osdi", "systems"],
        }
    )


def iter_osdi_presentation_urls(index_html: str, *, year: int, base_url: str) -> List[str]:
    soup = BeautifulSoup(index_html, "html.parser")
    short_year = str(int(year))[-2:]
    urls: List[str] = []
    seen = set()
    pattern = f"/conference/osdi{short_year}/presentation/"
    for a in soup.find_all("a", href=True):
        href = _absolute_url(a.get("href"), base_url)
        if pattern not in href:
            continue
        href = href.split("#", 1)[0]
        if href in seen:
            continue
        seen.add(href)
        urls.append(href)
    return urls


def fetch_osdi(years: Iterable[int], *, workers: int = 8, require_pdf: bool = True) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for year in years:
        url = OSDI_LIST_URL.format(short_year=str(int(year))[-2:])
        try:
            urls = iter_osdi_presentation_urls(_request_text(url), year=int(year), base_url=url)
        except Exception as exc:
            log(f"[WARN] OSDI {year} list fetch failed: {exc}")
            continue
        with ThreadPoolExecutor(max_workers=max(int(workers or 1), 1)) as pool:
            future_map = {pool.submit(_request_text, paper_url): paper_url for paper_url in urls}
            parsed: List[Dict[str, Any]] = []
            for future in as_completed(future_map):
                page_url = future_map[future]
                try:
                    paper = parse_osdi_paper_page(future.result(), year=int(year), page_url=page_url)
                except Exception as exc:
                    log(f"[WARN] OSDI paper parse failed {page_url}: {exc}")
                    continue
                if paper.get("title"):
                    parsed.append(paper)
        if require_pdf:
            missing = [paper for paper in parsed if not _norm(paper.get("pdf_url"))]
            if missing:
                arxiv_entries = fetch_arxiv_title_matches(missing)
                parsed = apply_arxiv_pdf_candidates(parsed, arxiv_entries)
            parsed = [paper for paper in parsed if _norm(paper.get("pdf_url"))]
        rows.extend(parsed)
    return rows


def iter_ndss_paper_urls(index_html: str, *, base_url: str) -> List[str]:
    soup = BeautifulSoup(index_html, "html.parser")
    urls: List[str] = []
    seen = set()
    for a in soup.find_all("a", href=True):
        href = _absolute_url(a.get("href"), base_url)
        if "/ndss-paper/" not in href:
            continue
        href = href.split("#", 1)[0]
        if href in seen:
            continue
        seen.add(href)
        urls.append(href)
    return urls


def _extract_ndss_authors_and_abstract(soup: BeautifulSoup) -> tuple[List[str], str]:
    paper_node = soup.select_one(".paper-data") or soup.select_one(".entry-content")
    if paper_node:
        paragraphs = [
            _norm(node.get_text(" ", strip=True))
            for node in paper_node.find_all("p")
            if _norm(node.get_text(" ", strip=True))
        ]
        deduped: List[str] = []
        for paragraph in paragraphs:
            if paragraph not in deduped:
                deduped.append(paragraph)
        if deduped:
            authors = _split_authors(deduped[0])
            abstract = _norm(" ".join(deduped[1:]))
            if abstract:
                return authors, abstract

    text = soup.get_text("\n", strip=True)
    authors: List[str] = []
    match = re.search(r"Authors?:\s*(.+?)(?:\n\s*\n|Abstract:|Paper|Slides|$)", text, flags=re.I | re.S)
    if match:
        authors = _split_authors(match.group(1))
    abstract = ""
    match = re.search(r"Abstract:?\s*(.+?)(?:\n\s*(?:Paper|Slides|BibTeX|View More Papers)|$)", text, flags=re.I | re.S)
    if match:
        abstract = _norm(match.group(1))
    return authors, abstract


def parse_ndss_paper_page(html_text: str, *, year: int, page_url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html_text, "html.parser")
    title = _norm(soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else "")
    if title.endswith(" - NDSS Symposium"):
        title = title[: -len(" - NDSS Symposium")].strip()
    pdf_url = ""
    for a in soup.find_all("a", href=True):
        text = _norm(a.get_text(" ", strip=True)).lower()
        href = _absolute_url(a.get("href"), page_url)
        if text == "paper" or href.lower().endswith("-paper.pdf") or "/wp-content/uploads/" in href and href.lower().endswith(".pdf"):
            pdf_url = href
            break
    authors, abstract = _extract_ndss_authors_and_abstract(soup)
    return _clean_paper(
        {
            "id": _paper_id("ndss", year, title or page_url),
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "published": _published_iso(year),
            "link": page_url,
            "pdf_url": pdf_url,
            "source": f"NDSS-{int(year)}-Accepted",
            "primary_category": "ndss",
            "categories": ["ndss", "security"],
        }
    )


def fetch_ndss(years: Iterable[int], *, workers: int = 8, require_pdf: bool = True) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for year in years:
        url = NDSS_LIST_URL.format(year=int(year))
        try:
            urls = iter_ndss_paper_urls(_request_text(url), base_url=url)
        except Exception as exc:
            log(f"[WARN] NDSS {year} list fetch failed: {exc}")
            continue
        with ThreadPoolExecutor(max_workers=max(int(workers or 1), 1)) as pool:
            future_map = {pool.submit(_request_text, paper_url): paper_url for paper_url in urls}
            for future in as_completed(future_map):
                page_url = future_map[future]
                try:
                    paper = parse_ndss_paper_page(future.result(), year=int(year), page_url=page_url)
                except Exception as exc:
                    log(f"[WARN] NDSS paper parse failed {page_url}: {exc}")
                    continue
                if require_pdf and not _norm(paper.get("pdf_url")):
                    continue
                if paper.get("title"):
                    rows.append(paper)
    return rows


def parse_sosp_accepted_page(html_text: str, *, year: int) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html_text, "html.parser")
    out: List[Dict[str, Any]] = []
    for li in soup.select("ul.paperlist li"):
        title_node = li.find("b")
        if not title_node:
            continue
        title = _norm(title_node.get_text(" ", strip=True))
        authors_node = li.find("em")
        authors = _split_authors(authors_node.get_text(" ", strip=True) if authors_node else "")
        out.append(
            _clean_paper(
                {
                    "id": _paper_id("sosp", year, title),
                    "title": title,
                    "abstract": "",
                    "authors": authors,
                    "published": _published_iso(year),
                    "link": SOSP_ACCEPTED_URL.format(year=int(year)),
                    "pdf_url": "",
                    "source": f"SOSP-{int(year)}-ACM",
                    "primary_category": "sosp",
                    "categories": ["sosp", "systems"],
                }
            )
        )
    return out


def build_acm_pdf_url(doi: str) -> str:
    return f"https://dl.acm.org/doi/pdf/{_norm(doi)}"


def _sosp_container_title(year: int) -> str:
    ordinal = {2024: "30th", 2025: "31st"}.get(int(year), "")
    if ordinal:
        return f"Proceedings of the ACM SIGOPS {ordinal} Symposium on Operating Systems Principles"
    return "Proceedings of the ACM SIGOPS Symposium on Operating Systems Principles"


def _crossref_sosp_items(*, year: int) -> List[Dict[str, Any]]:
    container_title = _sosp_container_title(year)
    params = {
        "query.container-title": container_title,
        "filter": f"prefix:10.1145,type:proceedings-article,from-pub-date:{int(year)}-01-01,until-pub-date:{int(year)}-12-31",
        "rows": "100",
    }
    res = requests.get("https://api.crossref.org/works", params=params, headers={"User-Agent": USER_AGENT}, timeout=DEFAULT_TIMEOUT)
    res.raise_for_status()
    return (((res.json() or {}).get("message") or {}).get("items") or [])


def _crossref_query_by_title(title: str, *, year: int) -> Dict[str, Any] | None:
    container_title = _sosp_container_title(year).lower()
    params = {
        "query.title": _norm(title),
        "filter": "prefix:10.1145,type:proceedings-article",
        "rows": "5",
    }
    res = requests.get("https://api.crossref.org/works", params=params, headers={"User-Agent": USER_AGENT}, timeout=DEFAULT_TIMEOUT)
    res.raise_for_status()
    items = (((res.json() or {}).get("message") or {}).get("items") or [])
    wanted = _norm(title).lower()
    for item in items:
        item_title = _norm((item.get("title") or [""])[0]).lower()
        container = _norm((item.get("container-title") or [""])[0]).lower()
        if _title_matches(item_title, wanted) and (container == container_title or ("sigops" in container and "symposium on operating systems principles" in container)):
            return item
    return None


def enrich_sosp_with_crossref(papers: List[Dict[str, Any]], *, year: int, workers: int = 4) -> List[Dict[str, Any]]:
    try:
        crossref_items = _crossref_sosp_items(year=year)
    except Exception as exc:
        log(f"[WARN] SOSP Crossref batch lookup failed for {year}: {exc}")
        crossref_items = []
    item_by_title = {}
    item_by_prefix: Dict[str, List[Dict[str, Any]]] = {}
    item_by_suffix: Dict[str, List[Dict[str, Any]]] = {}
    for item in crossref_items:
        title = _norm((item.get("title") or [""])[0])
        if not title:
            continue
        item_by_title[_title_key(title)] = item
        prefix = _title_prefix(title)
        if prefix:
            item_by_prefix.setdefault(prefix, []).append(item)
        suffix = _title_without_prefix_key(title)
        if suffix and suffix != _title_key(title):
            item_by_suffix.setdefault(suffix, []).append(item)

    def enrich(paper: Dict[str, Any]) -> Dict[str, Any]:
        item = item_by_title.get(_title_key(paper.get("title")))
        if not item:
            prefix_items = item_by_prefix.get(_title_prefix(paper.get("title"))) or []
            if len(prefix_items) == 1:
                item = prefix_items[0]
        if not item:
            suffix_items = item_by_suffix.get(_title_key(paper.get("title"))) or []
            if len(suffix_items) == 1:
                item = suffix_items[0]
        if not item:
            try:
                item = _crossref_query_by_title(str(paper.get("title") or ""), year=year)
            except Exception as exc:
                log(f"[WARN] SOSP Crossref title lookup failed for {paper.get('title')}: {exc}")
        if not item:
            return paper
        doi = _norm(item.get("DOI"))
        if doi:
            paper["doi"] = doi
            paper["link"] = f"https://dl.acm.org/doi/{doi}"
            paper["pdf_url"] = build_acm_pdf_url(doi)
        date_parts = ((item.get("published") or {}).get("date-parts") or [[year]])[0]
        if date_parts:
            paper["published"] = _published_iso(int(date_parts[0]), int(date_parts[1]) if len(date_parts) > 1 else 1, int(date_parts[2]) if len(date_parts) > 2 else 1)
        return paper

    return [enrich(paper) for paper in papers]


def apply_semantic_scholar_abstracts(papers: List[Dict[str, Any]], items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    abstract_by_doi: Dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        external_ids = item.get("externalIds") if isinstance(item.get("externalIds"), dict) else {}
        doi = _norm(external_ids.get("DOI")).lower()
        abstract = _norm(item.get("abstract"))
        if doi and abstract:
            abstract_by_doi[doi] = abstract
    for paper in papers:
        if _norm(paper.get("abstract")):
            continue
        doi = _norm(paper.get("doi")).lower()
        if doi and doi in abstract_by_doi:
            paper["abstract"] = abstract_by_doi[doi]
    return papers


def _arxiv_query_for_titles(titles: Iterable[str]) -> str:
    clauses = []
    for title in titles:
        cleaned = _norm(title).replace('"', "").replace(":", " ")
        if cleaned:
            clauses.append(f'ti:"{cleaned}"')
    return " OR ".join(clauses)


def parse_arxiv_feed_entries(feed_text: str) -> List[Dict[str, Any]]:
    try:
        root = ET.fromstring(feed_text or "")
    except Exception:
        return []
    entries: List[Dict[str, Any]] = []
    for node in root.findall("atom:entry", ARXIV_ATOM_NS):
        title = _norm(node.findtext("atom:title", "", ARXIV_ATOM_NS))
        abs_url = _norm(node.findtext("atom:id", "", ARXIV_ATOM_NS))
        if not title or not abs_url:
            continue
        arxiv_id = abs_url.rstrip("/").rsplit("/", 1)[-1]
        authors = [
            _norm(author.findtext("atom:name", "", ARXIV_ATOM_NS))
            for author in node.findall("atom:author", ARXIV_ATOM_NS)
            if _norm(author.findtext("atom:name", "", ARXIV_ATOM_NS))
        ]
        entries.append(
            {
                "title": title,
                "abstract": _norm(node.findtext("atom:summary", "", ARXIV_ATOM_NS)),
                "authors": authors,
                "published": _norm(node.findtext("atom:published", "", ARXIV_ATOM_NS)),
                "abs_url": abs_url,
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
            }
        )
    return entries


def apply_arxiv_pdf_candidates(papers: List[Dict[str, Any]], entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    entry_by_title: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        title = _title_key(entry.get("title"))
        pdf_url = _norm(entry.get("pdf_url"))
        if title and pdf_url and title not in entry_by_title:
            entry_by_title[title] = entry

    for paper in papers:
        if _norm(paper.get("pdf_url")):
            continue
        entry = entry_by_title.get(_title_key(paper.get("title")))
        if not entry:
            continue
        paper["pdf_url"] = _norm(entry.get("pdf_url"))
        paper["link"] = _norm(entry.get("abs_url")) or paper.get("link")
        if not _norm(paper.get("abstract")):
            paper["abstract"] = _norm(entry.get("abstract"))
        if not paper.get("authors"):
            paper["authors"] = [a for a in (_norm(x) for x in entry.get("authors") or []) if a]
    return papers


def fetch_arxiv_title_matches(
    papers: List[Dict[str, Any]],
    *,
    group_size: int = 5,
    request_delay: float = 3.0,
    retries: int = 2,
    retry_delay: float = 10.0,
) -> List[Dict[str, Any]]:
    if not papers:
        return []
    entries: List[Dict[str, Any]] = []
    safe_group_size = max(int(group_size or 1), 1)
    for start in range(0, len(papers), safe_group_size):
        chunk = papers[start : start + safe_group_size]
        query = _arxiv_query_for_titles([str(p.get("title") or "") for p in chunk])
        if not query:
            continue
        last_exc: Exception | None = None
        for attempt in range(max(int(retries or 0), 0) + 1):
            try:
                res = requests.get(
                    f"{ARXIV_API_URL}?search_query={quote(query)}&start=0&max_results={safe_group_size * 5}",
                    headers={"User-Agent": USER_AGENT},
                    timeout=DEFAULT_TIMEOUT,
                )
                res.raise_for_status()
                entries.extend(parse_arxiv_feed_entries(res.text))
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                if attempt < max(int(retries or 0), 0):
                    time.sleep(float(retry_delay))
        if last_exc:
            log(f"[WARN] arXiv title lookup failed for batch starting {start}: {last_exc}")
        if start + safe_group_size < len(papers) and request_delay > 0:
            time.sleep(float(request_delay))
    return entries


def _semantic_scholar_headers() -> Dict[str, str]:
    headers = {"User-Agent": USER_AGENT}
    api_key = _norm(os.getenv("SEMANTIC_SCHOLAR_API_KEY"))
    if api_key:
        headers["x-api-key"] = api_key
    return headers


def enrich_sosp_with_semantic_scholar(papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    doi_ids = [f"DOI:{_norm(paper.get('doi'))}" for paper in papers if _norm(paper.get("doi")) and not _norm(paper.get("abstract"))]
    if not doi_ids:
        return papers
    items: List[Dict[str, Any]] = []
    for start in range(0, len(doi_ids), 80):
        chunk = doi_ids[start : start + 80]
        payload = {"ids": chunk}
        params = {"fields": "title,abstract,externalIds"}
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                res = requests.post(
                    SEMANTIC_SCHOLAR_BATCH_URL,
                    params=params,
                    json=payload,
                    headers=_semantic_scholar_headers(),
                    timeout=DEFAULT_TIMEOUT,
                )
                if res.status_code == 429 and attempt < 2:
                    time.sleep(10 * (attempt + 1))
                    continue
                res.raise_for_status()
                data = res.json() or []
                if isinstance(data, list):
                    items.extend(item for item in data if isinstance(item, dict))
                last_exc = None
                break
            except Exception as exc:
                last_exc = exc
                if attempt < 2:
                    time.sleep(3 * (attempt + 1))
        if last_exc:
            log(f"[WARN] SOSP Semantic Scholar batch lookup partially failed: {last_exc}")
    return apply_semantic_scholar_abstracts(papers, items)


def fetch_sosp(years: Iterable[int], *, workers: int = 4, require_pdf: bool = True) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for year in years:
        url = SOSP_ACCEPTED_URL.format(year=int(year))
        try:
            papers = parse_sosp_accepted_page(_request_text(url), year=int(year))
            papers = enrich_sosp_with_crossref(papers, year=int(year), workers=workers)
            papers = enrich_sosp_with_semantic_scholar(papers)
        except Exception as exc:
            log(f"[WARN] SOSP {year} fetch failed: {exc}")
            continue
        for paper in papers:
            if require_pdf and not _norm(paper.get("pdf_url")):
                continue
            rows.append(paper)
    return rows


def build_ieee_sp_pdf_url(article_id: str) -> str:
    return f"https://www.computer.org/csdl/pds/api/csdl/proceedings/download-article/{_norm(article_id)}/pdf"


def _ieee_sp_abstract(article: Dict[str, Any]) -> str:
    for key in ("normalizedAbstract", "abstract"):
        value = _norm(article.get(key))
        if value:
            return value
    for item in article.get("abstracts") or []:
        if isinstance(item, dict):
            value = _norm(item.get("content"))
            if value:
                return value
    return ""


def normalize_ieee_sp_articles(articles: Iterable[Dict[str, Any]], *, year: int, require_public_pdf: bool = True) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for article in articles:
        authors = [_norm(a.get("fullName")) for a in (article.get("authors") or []) if isinstance(a, dict) and _norm(a.get("fullName"))]
        title = _norm(article.get("title"))
        if not title or not authors:
            continue
        has_pdf = bool(article.get("hasPdf"))
        is_open = bool(article.get("isOpenAccess"))
        if require_public_pdf and (not has_pdf or not is_open):
            continue
        article_id = _norm(article.get("id"))
        if not article_id:
            continue
        pub_date = _norm(article.get("pubDate"))
        published = _parse_meta_date(pub_date, year)
        public_pdf_url = build_ieee_sp_pdf_url(article_id) if has_pdf and is_open else ""
        out.append(
            _clean_paper(
                {
                    "id": _paper_id("ieee-sp", year, title),
                    "title": title,
                    "abstract": _ieee_sp_abstract(article),
                    "authors": authors,
                    "published": published,
                    "link": f"https://www.computer.org/csdl/proceedings-article/sp/{int(year)}/{_norm(article.get('fno'))}/{article_id}",
                    "pdf_url": public_pdf_url,
                    "doi": _norm(article.get("doi")),
                    "source": f"IEEE-SP-{int(year)}-CSDL",
                    "primary_category": "ieee_sp",
                    "categories": ["ieee_sp", "security"],
                }
            )
        )
    return out


def _extract_ieee_accepted_authors(node: Any) -> List[str]:
    if not node:
        return []
    html_text = str(node)
    author_html = re.split(r"<br\s*/?>", html_text, maxsplit=1, flags=re.I)[0]
    author_text = BeautifulSoup(author_html, "html.parser").get_text(" ", strip=True)
    author_text = re.sub(r"\d+(?:\s*,\s*\d+)*", "", author_text)
    return _split_authors(author_text)


def parse_ieee_sp_accepted_page(html_text: str, *, year: int, page_url: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html_text, "html.parser")
    rows: List[Dict[str, Any]] = []
    for item in soup.select(".list-group-item"):
        title_node = item.select_one('a[href^="#collapse-"]') or item.find("a")
        title = _norm(title_node.get_text(" ", strip=True) if title_node else item.get_text(" ", strip=True))
        if not title:
            continue
        collapse_id = _norm(title_node.get("href") if title_node else "").lstrip("#")
        authors = _extract_ieee_accepted_authors(soup.find(id=collapse_id)) if collapse_id else []
        rows.append(
            _clean_paper(
                {
                    "id": _paper_id("ieee-sp", year, title),
                    "title": title,
                    "abstract": "",
                    "authors": authors,
                    "published": _published_iso(year),
                    "link": page_url,
                    "pdf_url": "",
                    "source": f"IEEE-SP-{int(year)}-Accepted",
                    "primary_category": "ieee_sp",
                    "categories": ["ieee_sp", "security"],
                }
            )
        )
    return rows


def _fetch_ieee_sp_articles(proceeding_id: str) -> List[Dict[str, Any]]:
    query = """
    query ($proceedingId: String!, $limitResults: Int, $skipResults: Int) {
      articlesByProceeding: articlesByProceedingWithPagination(
        proceedingId: $proceedingId
        limit: $limitResults
        skip: $skipResults
      ) {
        articleResults {
          id
          pubDate
          doi
          fno
          isOpenAccess
          hasPdf
          title
          abstract
          normalizedAbstract
          abstracts { abstractType content }
          year
          authors { fullName }
        }
      }
    }
    """
    payload = {"query": query, "variables": {"proceedingId": proceeding_id, "limitResults": 0, "skipResults": 0}}
    res = requests.post(IEEE_SP_GRAPHQL_URL, json=payload, headers={"User-Agent": USER_AGENT}, timeout=DEFAULT_TIMEOUT)
    res.raise_for_status()
    data = res.json() or {}
    if data.get("errors"):
        raise RuntimeError(json.dumps(data.get("errors"), ensure_ascii=False))
    return (((data.get("data") or {}).get("articlesByProceeding") or {}).get("articleResults") or [])


def fetch_ieee_sp(years: Iterable[int], *, require_pdf: bool = True) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for year in years:
        proceeding_id = IEEE_SP_PROCEEDINGS.get(int(year))
        if not proceeding_id:
            url = IEEE_SP_ACCEPTED_URL.format(year=int(year))
            try:
                accepted_rows = parse_ieee_sp_accepted_page(_request_text(url), year=int(year), page_url=url)
                arxiv_entries = fetch_arxiv_title_matches(accepted_rows)
                accepted_rows = apply_arxiv_pdf_candidates(accepted_rows, arxiv_entries)
                rows.extend([row for row in accepted_rows if _norm(row.get("pdf_url"))] if require_pdf else accepted_rows)
            except Exception as exc:
                log(f"[WARN] IEEE S&P {year} accepted-page fallback failed: {exc}")
            continue
        try:
            articles = _fetch_ieee_sp_articles(proceeding_id)
            normalized = normalize_ieee_sp_articles(articles, year=int(year), require_public_pdf=False)
            arxiv_entries = fetch_arxiv_title_matches([row for row in normalized if not _norm(row.get("pdf_url"))])
            normalized = apply_arxiv_pdf_candidates(normalized, arxiv_entries)
            rows.extend([row for row in normalized if _norm(row.get("pdf_url"))] if require_pdf else normalized)
        except Exception as exc:
            log(f"[WARN] IEEE S&P {year} fetch failed: {exc}")
    return rows


def fetch_conference(conference: str, years: Iterable[int], *, workers: int = 8, require_pdf: bool = True) -> List[Dict[str, Any]]:
    key = _norm(conference).lower().replace("-", "_").replace("&", "")
    if key in {"sp", "s_p", "ieeesp", "ieee_sp", "ieee_s_p"}:
        key = "ieee_sp"
    if key == "osdi":
        return fetch_osdi(years, workers=workers, require_pdf=require_pdf)
    if key == "ndss":
        return fetch_ndss(years, workers=workers, require_pdf=require_pdf)
    if key == "sosp":
        return fetch_sosp(years, workers=workers, require_pdf=require_pdf)
    if key == "ieee_sp":
        return fetch_ieee_sp(years, require_pdf=require_pdf)
    raise ValueError(f"unsupported conference: {conference}")


def parse_years(value: str) -> List[int]:
    years: List[int] = []
    seen = set()
    for item in re.split(r"[,\s;]+", str(value or "")):
        token = _norm(item)
        if not token:
            continue
        year = int(token)
        if year not in seen:
            seen.add(year)
            years.append(year)
    return years


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch public OSDI/SOSP/IEEE S&P/NDSS papers.")
    parser.add_argument("--conference", required=True, choices=["OSDI", "SOSP", "IEEE_SP", "NDSS", "osdi", "sosp", "ieee_sp", "ndss"])
    parser.add_argument("--years", required=True, help="Comma-separated years, e.g. 2024,2025,2026")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output", required=True)
    parser.add_argument("--allow-missing-pdf", action="store_true")
    args = parser.parse_args()

    years = parse_years(args.years)
    if not years:
        raise SystemExit("--years is required")
    rows = fetch_conference(
        args.conference,
        years,
        workers=max(int(args.workers or 1), 1),
        require_pdf=not bool(args.allow_missing_pdf),
    )
    rows = sorted(rows, key=lambda row: (str(row.get("published") or ""), str(row.get("title") or "")), reverse=True)
    _write_json(args.output, rows)
    log(f"[INFO] wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
