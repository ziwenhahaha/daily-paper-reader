import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from maintain.fetchers.fetch_openreview import normalize_neurips_program_events
from scripts.sync_conference_year_stats import build_conference_year_stats


def official_events():
    path = ROOT_DIR / "tests" / "fixtures" / "neurips_2026_program_sample.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_official_program_filters_main_track_and_deduplicates_presentations():
    papers = normalize_neurips_program_events(official_events(), {}, year=2026)
    assert len(papers) == 1
    paper = papers[0]
    assert paper["id"] == "openreview-neurips-2026-4ca3tomjpr"
    assert paper["source_paper_id"] == "4CA3Tomjpr"
    assert paper["source"] == "NeurIPS-2026-Accepted"
    assert paper["authors"] == ["Yuming Huang", "Haoran Yin", "Wu"]
    assert paper["link"] == "https://openreview.net/forum?id=4CA3Tomjpr"
    assert paper["official_url"] == "https://neurips.cc/virtual/2026/poster/155623"
    assert paper["pdf_url"] == ""


def test_event_schedule_does_not_supply_publication_day():
    paper = normalize_neurips_program_events(official_events(), {}, year=2026)[0]
    assert paper["publication_date"] == "2026"
    assert paper["publication_date_precision"] == "year"
    assert paper["publication_date_kind"] == "accepted_notice"
    assert paper["published"] == "2026-01-01T00:00:00Z"


def test_program_source_must_match_requested_year():
    assert normalize_neurips_program_events(official_events(), {}, year=2025) == []


def test_unknown_official_total_remains_distinct_from_public_inventory():
    papers = normalize_neurips_program_events(official_events(), {}, year=2026)
    stats = build_conference_year_stats({"neurips_openreview_papers": papers})
    assert stats[0]["stored_accepted_count"] == 1
    assert stats[0]["official_accepted_count"] == 0
