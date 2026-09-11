import copy
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from paper_dedupe import deduplicate_papers


def paper(id, **kwargs):
    return dict(
        id=id,
        title="Approximation algorithms for asymmetric travelling salesman",
        authors=["Ada Lovelace"],
        abstract="",
        source="icml",
        **kwargs
    )


def test_arxiv_versions_preserve_full_provenance_and_choose_content():
    first = paper("2501.12345v1", route="old/a", published="2025-01-01")
    second = paper(
        "conference-id",
        arxiv_id="https://arxiv.org/abs/2501.12345v2",
        pdf_url="https://example.org/p.pdf",
        route="old/b",
    )
    second["abstract"] = "Full abstract"
    second["source"] = "neurips"
    original = copy.deepcopy([first, second])
    merged = deduplicate_papers(original)["papers"][0]
    assert merged["canonical_id"] == "arxiv:2501.12345"
    assert merged["id"] == "conference-id"
    assert merged["abstract"] == "Full abstract"
    assert merged["route_aliases"] == ["old/a", "old/b"]
    assert merged["sources"] == ["icml", "neurips"]
    assert len(merged["versions"]) == 2
    assert original == [first, second]


def test_doi_normalization_and_authorless_strong_match():
    a, b = paper("a", doi="https://doi.org/10.1234/ABC"), paper(
        "b", doi="doi:10.1234/abc"
    )
    a["authors"] = b["authors"] = []
    assert len(deduplicate_papers([a, b])["papers"]) == 1


def test_doi_carrier_urls_match_explicit_doi_without_author_evidence():
    urls = [
        "https://doi.org/10.1234/ABC",
        "https://dx.doi.org/10.1234/ABC",
        "https://dl.acm.org/doi/10.1234/ABC",
        "https://dl.acm.org/doi/pdf/10.1234/ABC?download=true",
        "https://dl.acm.org/doi/abs/10.1234/ABC#abstract",
        "https://dl.acm.org/doi/full/10.1234/ABC",
    ]
    for field, url in itertools.product(("link", "pdf_url"), urls):
        a, b = paper("a", doi="10.1234/abc"), paper("b", **{field: url})
        a["authors"] = b["authors"] = []
        result = deduplicate_papers([a, b])
        assert len(result["papers"]) == 1, (field, url)
        assert result["papers"][0]["canonical_id"] == "doi:10.1234/abc"


def test_untrusted_urls_do_not_supply_strong_doi_evidence():
    for url in (
        "https://example.com/10.1234/abc",
        "https://doi.org.evil.example/10.1234/abc",
        "https://dl.acm.org.evil.example/doi/pdf/10.1234/abc",
        "https://example.com/?url=https://doi.org/10.1234/abc",
    ):
        a, b = paper("a", doi="10.1234/abc"), paper("b", link=url)
        a["authors"] = b["authors"] = []
        assert len(deduplicate_papers([a, b])["papers"]) == 2


def test_title_author_match_and_normalization():
    a, b = paper("a"), paper("b")
    b["title"] = "Approximation Algorithms for Asymmetric Travelling Salesman!"
    b["authors"] = [{"name": "Ada Lovelace"}]
    assert len(deduplicate_papers([a, b])["papers"]) == 1


def test_title_without_authors_is_only_possible_duplicate():
    a, b = paper("a"), paper("b")
    b["authors"] = []
    result = deduplicate_papers([a, b])
    assert len(result["papers"]) == 2
    assert len(result["possible_duplicates"]) == 1
    assert len({p["id"] for p in result["papers"]}) == 2


def test_conflicting_doi_blocks_weak_match():
    result = deduplicate_papers(
        [paper("a", doi="10.1234/a"), paper("b", doi="10.1234/b")]
    )
    assert len(result["papers"]) == 2
    assert result["possible_duplicates"][0]["reason"] == "conflicting_identifiers"


def test_short_or_only_similar_titles_not_merged():
    a, b = paper("a"), paper("b")
    a["title"] = b["title"] = "Learning"
    result = deduplicate_papers([a, b])
    assert len(result["papers"]) == 2
    assert len({p["canonical_id"] for p in result["papers"]}) == 2
    b["title"] = "Learning better"
    assert len(deduplicate_papers([a, b])["papers"]) == 2


def test_chain_order_stability_and_idempotence():
    a = paper("a", doi="10.1234/a")
    b = paper("b", doi="10.1234/a", arxiv_id="2501.12345v1")
    c = paper("2501.12345v2")
    expected = deduplicate_papers([a, b, c])
    assert len(expected["papers"]) == 1
    for order in itertools.permutations([a, b, c]):
        assert deduplicate_papers(order) == expected
    assert deduplicate_papers(expected["papers"]) == expected


def test_weak_bridge_does_not_join_conflicting_dois():
    inputs = [paper("a", doi="10.1234/a"), paper("bridge"), paper("z", doi="10.1234/z")]
    result = deduplicate_papers(inputs)
    assert len(result["papers"]) == 2
    assert result["possible_duplicates"]
    assert deduplicate_papers(result["papers"]) == result


def test_duplicate_input_and_empty_input():
    a = paper("a")
    assert len(deduplicate_papers([a, a])["papers"][0]["versions"]) == 1
    assert deduplicate_papers([]) == {"papers": [], "possible_duplicates": []}


def test_original_dates_routes_and_extra_metadata_are_kept_per_version():
    a = paper(
        "a",
        doi="10.1234/a",
        publication_date="2025-01",
        publication_date_precision="month",
        route="conference/a",
        extra={"x": 1},
    )
    b = paper(
        "b",
        doi="10.1234/a",
        publication_date="2026-05-17",
        publication_date_precision="day",
        route="daily/b",
    )
    output = deduplicate_papers([a, b])["papers"][0]
    assert {p["publication_date_precision"] for p in output["versions"]} == {
        "day",
        "month",
    }
    assert next(p for p in output["versions"] if p["id"] == "a")["extra"] == {"x": 1}
    assert output["route_aliases"] == ["conference/a", "daily/b"]


def test_old_style_arxiv_urls_and_no_fuzzy_matching():
    a, b = paper("a", arxiv_id="math.CO/0501234v1"), paper(
        "b", pdf_url="https://arxiv.org/pdf/math.CO/0501234v3.pdf"
    )
    b["title"] = "A revised title"
    result = deduplicate_papers([a, b])
    assert len(result["papers"]) == 1
    assert result["papers"][0]["canonical_id"] == "arxiv:math.co/0501234"
    a, b = paper("a"), paper("b")
    b["title"] += " problems"
    assert len(deduplicate_papers([a, b])["papers"]) == 2
