"""公布日期及其证据契约；不把会议年份占位或抓取时间当作发布日期。"""
from __future__ import annotations

import calendar
import json
import re
from datetime import date, timedelta
from pathlib import Path

DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / 'app' / 'conference-release-dates.json'
FIELDS = ('publication_date', 'publication_date_precision', 'publication_date_source', 'publication_date_kind')
KINDS = {'proceedings', 'accepted_notice', 'arxiv_first_submission', 'unknown'}


def _bounds(value, precision):
    text = str(value or '')
    try:
        if precision == 'day' and re.fullmatch(r'\d{4}-\d{2}-\d{2}', text):
            start = date.fromisoformat(text)
            return start, start + timedelta(days=1)
        if precision == 'month' and re.fullmatch(r'\d{4}-\d{2}', text):
            start = date.fromisoformat(text + '-01')
            return start, start + timedelta(days=calendar.monthrange(start.year, start.month)[1])
        if precision == 'year' and re.fullmatch(r'\d{4}', text):
            return date(int(text), 1, 1), date(int(text) + 1, 1, 1)
    except (ValueError, OverflowError):
        pass
    return None


def _explicit(record):
    result = {key: str(record.get(key) or '').strip() for key in FIELDS}
    precision = result['publication_date_precision']
    if not result['publication_date_source'] or result['publication_date_kind'] not in KINDS:
        return None
    if precision in {'day','month'} and result['publication_date_kind']=='unknown':
        return None
    if precision in {'day', 'month'} and result['publication_date_kind'] == 'unknown':
        return None
    if _bounds(result['publication_date'], precision):
        return result
    return None


def _conference_key(value):
    return re.sub(r'[^A-Z0-9]', '', str(value or '').upper())


def resolve_publication_date(paper, conference='', year=None, registry=None):
    """优先显式有证据日期，再官方登记表，最后只保留可确认年份。"""
    explicit = _explicit(paper)
    if explicit and not (conference and explicit['publication_date_kind'] == 'arxiv_first_submission'):
        return explicit
    source = str(paper.get('source') or '')
    is_arxiv = not conference and (source.lower() == 'arxiv' or str(paper.get('id') or '').startswith('arxiv:'))
    if is_arxiv:
        published = str(paper.get('published') or '')[:10]
        if _bounds(published, 'day'):
            return dict(zip(FIELDS, (published, 'day', str(paper.get('link') or 'arXiv published (first submission)'), 'arxiv_first_submission')))

    # 多年份检索必须从单篇 source/year 确认，不取整个批次的第一年。
    paper_year = str(paper.get('year') or paper.get('conference_year') or '')
    source_year = re.search(r'(?<!\d)(20\d{2})(?!\d)', source)
    if not re.fullmatch(r'20\d{2}', paper_year):
        paper_year = source_year.group(1) if source_year else str(year or '')
    if not re.fullmatch(r'20\d{2}', paper_year):
        paper_year = ''
    if registry is None:
        try:
            registry = json.loads(DEFAULT_REGISTRY.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            registry = {}
    conf = _conference_key(conference or re.split(r'[-_ ]20\d{2}', source)[0])
    for entry in registry.get('items', []) if isinstance(registry, dict) else []:
        if not isinstance(entry, dict):
            continue
        if _conference_key(entry.get('conference')) == conf and str(entry.get('year')) == paper_year:
            verified = _explicit(entry)
            if verified:
                return verified
    return dict(zip(FIELDS, (paper_year, 'year' if paper_year else 'unknown', 'conference year only; exact release date unverified' if paper_year else '', 'unknown')))


def publication_window_status(metadata, start, end_exclusive):
    """返回 included/excluded/uncertain；边界交叠不冒称精确入窗。"""
    lower, upper = date.fromisoformat(str(start)), date.fromisoformat(str(end_exclusive))
    if lower >= upper:
        raise ValueError('发布时间窗口的开始必须早于结束')
    bounds = _bounds(metadata.get('publication_date'), metadata.get('publication_date_precision'))
    if not bounds:
        return 'uncertain'
    first, after = bounds
    if after <= lower or first >= upper:
        return 'excluded'
    if first >= lower and after <= upper:
        return 'included'
    return 'uncertain'
