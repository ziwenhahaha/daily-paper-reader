"""离线、保守的论文版本归并；保留原始记录，不改变任何已有文件。"""

from __future__ import annotations

import copy
import hashlib
import itertools
import json
import re
import unicodedata
from collections import defaultdict
from urllib.parse import unquote, urlsplit


def _dump(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text(value):
    return " ".join(
        re.findall(r"\w+", unicodedata.normalize("NFKC", str(value or "")).casefold())
    )


def _authors(paper):
    values = paper.get("authors") or []
    if not isinstance(values, list):
        return set()
    return {
        name
        for author in values
        if (
            name := _text(
                author.get("name", "") if isinstance(author, dict) else author
            )
        )
    }


def _doi(paper):
    for field in ("doi", "link", "pdf_url"):
        value = str(paper.get(field) or "").strip()
        if re.match(r"^https?://", value, re.IGNORECASE):
            try:
                url = urlsplit(value)
                host = (url.hostname or "").casefold()
            except ValueError:
                continue
            # 只认官方 DOI 解析器和 ACM 固定路径，不能从任意网址猜 DOI。
            path = unquote(url.path).casefold()
            if host in ("doi.org", "dx.doi.org"):
                value = path.lstrip("/")
            elif host == "dl.acm.org" and re.match(
                r"^/doi/(?:pdf/|abs/|full/)?10\.", path
            ):
                value = re.sub(r"^/doi/(?:pdf/|abs/|full/)?", "", path)
            else:
                continue
        elif field == "doi":
            value = re.sub(r"^doi:\s*", "", unquote(value).casefold())
        else:
            continue
        if re.fullmatch(r"10\.\d{4,9}/\S+", value):
            return value
    return ""


def _arxiv(paper):
    for field in ("arxiv_id", "id", "link", "pdf_url"):
        value = str(paper.get(field) or "").strip().casefold()
        value = re.sub(r"^https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/", "", value)
        value = re.sub(r"^arxiv:", "", value)
        value = re.sub(r"\.pdf$", "", value)
        match = re.fullmatch(
            r"(\d{4}\.\d{4,5}|[a-z-]+(?:\.[a-z]{2})?/\d{7})(?:v\d+)?", value
        )
        if match:
            return match[1]
    return ""


def deduplicate_papers(papers):
    """返回 papers 与 possible_duplicates；原 id 用于缓存，canonical_id 用于作品引用。

    DOI/arXiv 是强证据；长标题完全一致且有完整作者名交集是弱证据。
    冲突标识禁止弱边归并，短标题和缺作者仅提示。仅同标题构建候选对，
    不执行模糊标题自动合并。合并后的 versions 再输入会还原原记录重算，
    因此幂等、输入顺序无关，原始字段与历史 route 均不丢失。
    """
    originals = {}
    for paper in papers:
        versions = paper.get("versions")
        for version in versions if isinstance(versions, list) and versions else [paper]:
            raw = copy.deepcopy(version)
            originals[_dump(raw)] = raw
    rows = [originals[key] for key in sorted(originals)]
    parent = list(range(len(rows)))
    dois, arxivs = [_doi(p) for p in rows], [_arxiv(p) for p in rows]
    titles, authors = [_text(p.get("title")) for p in rows], [_authors(p) for p in rows]
    identifiers = [{("doi", d)} if d else set() for d in dois]
    for index, arxiv in enumerate(arxivs):
        if arxiv:
            identifiers[index].add(("arxiv", arxiv))

    def find(index):
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def join(left, right):
        left, right = sorted((find(left), find(right)))
        if left != right:
            parent[right] = left
            identifiers[left].update(identifiers[right])

    strong_index = {}
    for index in range(len(rows)):
        for key in sorted(identifiers[index]):
            if key in strong_index:
                join(index, strong_index[key])
            else:
                strong_index[key] = index

    by_title = defaultdict(list)
    for index, title in enumerate(titles):
        if title:
            by_title[title].append(index)
    possible = []
    for title in sorted(by_title):
        for left, right in itertools.combinations(by_title[title], 2):
            a, b = find(left), find(right)
            if a == b:
                continue
            conflict = any(
                (x := {v for k, v in identifiers[a] if k == kind})
                and (y := {v for k, v in identifiers[b] if k == kind})
                and not x.intersection(y)
                for kind in ("doi", "arxiv")
            )
            reason = (
                "conflicting_identifiers"
                if conflict
                else (
                    "short_title"
                    if len(title) < 25 or len(title.split()) < 4
                    else (
                        "insufficient_author_evidence"
                        if not authors[left].intersection(authors[right])
                        else ""
                    )
                )
            )
            if reason:
                possible.append((left, right, reason))
            else:
                join(left, right)

    groups = defaultdict(list)
    for index, row in enumerate(rows):
        groups[find(index)].append(row)
    output, canonical = [], {}
    for root, versions in sorted(groups.items()):
        versions.sort(key=_dump)

        # 优先有摘要且有 PDF 的版本；保留其原 id，供原有模型缓存直接复用。
        def quality(paper):
            abstract = str(paper.get("abstract") or "").strip()
            pdf = bool(paper.get("pdf_url"))
            return (
                bool(abstract) + pdf,
                bool(abstract),
                pdf,
                len(abstract),
                _dump(paper),
            )

        representative = copy.deepcopy(max(versions, key=quality))
        aids = sorted({v for p in versions if (v := _arxiv(p))})
        dids = sorted({v for p in versions if (v := _doi(p))})
        identity = sorted(
            {_dump((_text(p.get("title")), sorted(_authors(p)))) for p in versions}
        )
        # 没有作者的记录不能仅凭同名标题共享 canonical id。
        if not any(_authors(p) for p in versions) or any(
            len(_text(p.get("title"))) < 25 or len(_text(p.get("title")).split()) < 4
            for p in versions
        ):
            identity = [
                (p.get("source"), p.get("id"), _text(p.get("title"))) for p in versions
            ]
        cid = (
            "arxiv:" + aids[0]
            if aids
            else (
                "doi:" + dids[0]
                if dids
                else "work:" + hashlib.sha256(_dump(identity).encode()).hexdigest()[:24]
            )
        )
        representative.update(
            canonical_id=cid,
            versions=versions,
            sources=sorted({str(p["source"]) for p in versions if p.get("source")}),
            route_aliases=sorted({str(p["route"]) for p in versions if p.get("route")}),
        )
        canonical[root] = cid
        output.append(representative)
    warnings = set()
    for left, right, reason in possible:
        a, b = find(left), find(right)
        if a != b:
            warnings.add((*sorted((canonical[a], canonical[b])), reason))
    return {
        "papers": sorted(output, key=lambda p: (p["canonical_id"], _dump(p))),
        "possible_duplicates": [
            {"canonical_ids": [a, b], "reason": reason}
            for a, b, reason in sorted(warnings)
        ],
    }
