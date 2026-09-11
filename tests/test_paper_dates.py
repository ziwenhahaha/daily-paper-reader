import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from paper_dates import resolve_publication_date, publication_window_status


def test_conference_placeholder_and_scrape_date_are_not_publication_day():
    result = resolve_publication_date({'published': '2025-01-01', 'updated': '2026-09-11'}, 'ICML', 2025, registry={})
    assert result['publication_date'] == '2025'
    assert result['publication_date_precision'] == 'year'
    assert result['publication_date_kind'] == 'unknown'


def test_verified_registry_and_explicit_paper_dates():
    entry = {'conference': 'ICML', 'year': 2025, 'publication_date': '2025-10-06', 'publication_date_precision': 'day', 'publication_date_kind': 'proceedings', 'publication_date_source': 'https://official.example/volume'}
    assert resolve_publication_date({}, 'icml', 2025, {'items': [entry]})['publication_date'] == '2025-10-06'
    paper = dict(entry, publication_date='2025-10-05')
    assert resolve_publication_date(paper, 'ICML', 2025, {'items': [entry]})['publication_date'] == '2025-10-05'


def test_arxiv_uses_first_submission_not_update():
    result = resolve_publication_date({'source': 'arxiv', 'published': '2025-09-10T12:00:00Z', 'updated': '2026-09-10'})
    assert result['publication_date'] == '2025-09-10'
    assert result['publication_date_kind'] == 'arxiv_first_submission'


def test_invalid_date_and_multiple_years_do_not_fabricate_day():
    assert resolve_publication_date({'publication_date': '2025-02-30', 'publication_date_precision': 'day', 'publication_date_source': 'official', 'publication_date_kind': 'proceedings'}, 'ICML', '2024,2025', {})['publication_date_precision'] == 'unknown'
    assert resolve_publication_date({'source': 'ICML-2025-Accepted'}, 'ICML', '2024,2025', {})['publication_date'] == '2025'


def test_window_boundary_uncertainty():
    assert publication_window_status({'publication_date': '2024', 'publication_date_precision': 'year'}, '2024-09-11', '2026-09-11') == 'uncertain'
    assert publication_window_status({'publication_date': '2025', 'publication_date_precision': 'year'}, '2024-09-11', '2026-09-11') == 'included'
    assert publication_window_status({'publication_date': '2026-09-11', 'publication_date_precision': 'day'}, '2024-09-11', '2026-09-11') == 'excluded'
    assert publication_window_status({}, '2024-09-11', '2026-09-11') == 'uncertain'
