"""只读核验会议录用与同版官方 PDF；不把公开投稿当作录用。"""

from __future__ import annotations

from datetime import datetime, timezone
import copy
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup
import requests


def _text(value):
    return " ".join(
        re.findall(r"\w+", unicodedata.normalize("NFKC", str(value or "")).casefold())
    )


def _names(values):
    if isinstance(values, str):
        values = re.split(r"[,;]", values)
    return {
        _text(v.get("name", "") if isinstance(v, dict) else v) for v in (values or [])
    } - {""}


def _get(url):
    response = requests.get(
        url, timeout=30, headers={"User-Agent": "DailyPaperReader/1.0"}
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def _index_url(conference, year):
    if conference == "iclr":
        return f"https://proceedings.iclr.cc/paper_files/paper/{year}"
    if conference == "neurips":
        return f"https://papers.neurips.cc/paper_files/paper/{year}"
    volume = {2024: "v235", 2025: "v267"}.get(year)
    return (
        f"https://proceedings.mlr.press/{volume}/"
        if conference == "icml" and volume
        else ""
    )


def _parse_index(soup, url, conference):
    rows = []
    if conference == "icml":
        for node in soup.select(".paper"):
            title = node.select_one(".title")
            link = next(
                (
                    a
                    for a in node.select("a[href]")
                    if a.get_text(strip=True).lower() == "abs"
                ),
                None,
            )
            authors = node.select_one(".authors")
            if title and link:
                target = urljoin(url, link["href"])
                if urlsplit(target).netloc == urlsplit(url).netloc:
                    rows.append(
                        {
                            "title": title.get_text(" ", strip=True),
                            "authors": (
                                authors.get_text(" ", strip=True) if authors else ""
                            ),
                            "url": target,
                        }
                    )
    else:
        for link in soup.select("a[href]"):
            href = urljoin(url, link["href"])
            if urlsplit(href).netloc != urlsplit(url).netloc or not re.search(
                r"-Abstract(?:-Conference)?\.html$", href
            ):
                continue
            node = link.find_parent("li")
            authors = node.select_one(".paper-authors") if node else None
            if authors is None and node:
                authors = node.find("i")
            rows.append(
                {
                    "title": link.get_text(" ", strip=True),
                    "authors": authors.get_text(" ", strip=True) if authors else "",
                    "url": href,
                }
            )
    return rows


def _load_index(conference, year, root):
    url = _index_url(conference, year)
    if not url:
        return []
    cache = (
        Path(root)
        / ".local-runs/starter-pack-cache/publications"
        / f"{conference}-{year}.json"
    )
    if cache.exists():
        try:
            saved = json.loads(cache.read_text())
            age = (
                datetime.now(timezone.utc) - datetime.fromisoformat(saved["saved_at"])
            ).total_seconds()
            if saved.get("url") == url and 0 <= age < 86400 and saved.get("rows"):
                return saved["rows"]
        except (ValueError, KeyError, TypeError, OSError):
            pass
    soup = _get(url)
    # 2025 首页只列 Creative AI，主会链接必须跟随，不能误报整届未收录。
    if conference == "neurips":
        for link in soup.select("a[href]"):
            target = urljoin(url, link["href"])
            if (
                "main conference" in link.get_text(" ", strip=True).lower()
                and urlsplit(target).netloc == urlsplit(url).netloc
                and urlsplit(target).path.startswith(f"/paper_files/paper/{year}/")
            ):
                soup = _get(target)
                break
    rows = _parse_index(soup, url, conference)
    if not rows:
        raise ValueError("官方目录尚未公开或未解析到主会论文")
    cache.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(
            {
                "url": url,
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "rows": rows,
            },
            ensure_ascii=False,
        )
    )
    temporary.replace(cache)
    return rows


def _match(paper, rows):
    title, authors = _text(paper.get("title")), _names(paper.get("authors"))
    matches = []
    for row in rows:
        if _text(row["title"]) != title or not title:
            continue
        official_authors = _names(row.get("authors"))
        if authors and official_authors and not authors.intersection(official_authors):
            continue
        # 短/常见标题不能只凭标题确认身份。
        if len(title.split()) < 5 and not authors.intersection(official_authors):
            continue
        matches.append(row)
    return matches[0] if len(matches) == 1 else None


def _pdf(url, root=None):
    cache = None
    if root is not None:
        cache = (
            Path(root)
            / ".local-runs/starter-pack-cache/publications"
            / ("pdf-" + hashlib.sha256(url.encode()).hexdigest() + ".json")
        )
        try:
            saved = json.loads(cache.read_text())
            age = (
                datetime.now(timezone.utc) - datetime.fromisoformat(saved["saved_at"])
            ).total_seconds()
            if saved.get("url") == url and 0 <= age < 86400 and saved.get("pdf"):
                return saved["pdf"]
        except (ValueError, KeyError, TypeError, OSError):
            pass
    soup = _get(url)
    meta = soup.find("meta", attrs={"name": "citation_pdf_url"})
    candidates = ([meta.get("content", "")] if meta else []) + [
        a["href"]
        for a in soup.select("a[href]")
        if a.get_text(" ", strip=True).lower() in {"paper", "pdf", "download pdf"}
    ]
    allowed = {"proceedings.iclr.cc", "papers.neurips.cc", "proceedings.mlr.press"}
    for candidate in candidates:
        target = urljoin(url, candidate)
        parsed = urlsplit(target)
        mlresearch = (
            parsed.hostname == "raw.githubusercontent.com"
            and parsed.path.startswith("/mlresearch/")
        )
        if (
            parsed.scheme == "https"
            and (parsed.hostname in allowed or mlresearch)
            and parsed.path.lower().endswith(".pdf")
        ):
            if cache is not None:
                cache.parent.mkdir(parents=True, exist_ok=True)
                temporary = cache.with_suffix(".tmp")
                temporary.write_text(
                    json.dumps(
                        {
                            "url": url,
                            "pdf": target,
                            "saved_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                )
                temporary.replace(cache)
            return target
    return ""


def _csdl_acceptance_link(paper):
    """只认抓取器生成的 IEEE S&P 同年份官方论文集记录。"""
    source = re.fullmatch(r"IEEE-SP-(20\d{2})-CSDL", str(paper.get("source") or ""))
    if not source:
        return ""
    link = str(paper.get("link") or "")
    try:
        parsed = urlsplit(link)
    except ValueError:
        return ""
    if parsed.scheme != "https" or parsed.netloc not in {
        "computer.org",
        "www.computer.org",
    }:
        return ""
    if not re.fullmatch(
        rf"/csdl/proceedings-article/sp/{source.group(1)}/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+/?",
        parsed.path,
    ):
        return ""
    return link


def verify_publications(papers, root, *, resolve_pdfs=True):
    """返回复制的记录列表；无法核验保留 unverified，不删除、不改论文日期。"""
    result, indexes = [], {}
    for original in papers:
        paper = copy.deepcopy(original)
        source = str(paper.get("source") or "")
        conference = str(
            paper.get("conference_key") or re.split(r"[-_ ]20\d{2}", source)[0]
        ).lower()
        if conference == "arxiv":
            result.append(paper)
            continue
        label = " ".join(
            str(paper.get(k) or "")
            for k in ("source", "decision", "venue", "acceptance_status")
        )
        if re.search(r"reject|withdraw|desk.?reject", label, re.I):
            paper.update(
                conference_acceptance_status="rejected",
                conference_acceptance_evidence=label,
            )
            result.append(paper)
            continue
        csdl_link = _csdl_acceptance_link(paper)
        confirmed = bool(csdl_link) or bool(
            re.search(
                r"\b(?:accepted|accept|proceedings|CVF|ECVA|USENIX|AAAI|ACL|EMNLP|NDSS|ACM)\b",
                label,
                re.I,
            )
        )
        paper["conference_acceptance_status"] = (
            "accepted" if confirmed else "unverified"
        )
        paper["conference_acceptance_evidence"] = (
            (csdl_link or label)
            if confirmed
            else "公开投稿不代表录用；尚未在官方论文集核实"
        )
        year_match = re.search(
            r"20\d{2}", str(paper.get("conference_year") or paper.get("year") or source)
        )
        if conference in {"iclr", "neurips", "icml"} and year_match:
            key = (conference, int(year_match.group()))
            if key not in indexes:
                try:
                    # 全目录仅归一化一次，避免数千候选反复扫描数千标题。
                    indexes[key] = {}
                    for row in _load_index(*key, root):
                        indexes[key].setdefault(_text(row.get("title")), []).append(row)
                except (requests.RequestException, ValueError, OSError) as error:
                    indexes[key] = {}
                    print(
                        f"[官方论文集] {conference} {key[1]} 核验未完成：{type(error).__name__}",
                        flush=True,
                    )
            match = _match(paper, indexes[key].get(_text(paper.get("title")), []))
            if match:
                paper.update(
                    conference_acceptance_status="accepted",
                    conference_acceptance_evidence=match["url"],
                    official_link=match["url"],
                )
                if resolve_pdfs:
                    try:
                        pdf = _pdf(match["url"], root)
                        if pdf:
                            paper["official_pdf_url"] = pdf
                    except (requests.RequestException, ValueError, OSError):
                        pass
        result.append(paper)
    return result
