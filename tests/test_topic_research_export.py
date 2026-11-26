import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from topic_research_export import export_records, render_export, external_url


def test_verified_official_link_precedes_openreview():
    assert (
        external_url(
            {
                "id": "a",
                "link": "https://openreview.net/forum?id=a",
                "official_link": "https://proceedings.mlr.press/v200/a.html",
            }
        )
        == "https://proceedings.mlr.press/v200/a.html"
    )


def test_author_github_pdf_is_allowed():
    assert (
        external_url(
            {"id": "a", "official_pdf_url": "https://researcher.github.io/papers/a.pdf"}
        )
        == "https://researcher.github.io/papers/a.pdf"
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://5-xj.github.io/daily-paper-reader/#/topic/a",
        "https://5-xj.github.io/daily-paper-reader/docs/a.md",
        "http://localhost/paper.pdf",
        "http://127.0.0.1/paper.pdf",
        "http://192.168.1.2/paper.pdf",
        "http://[::1]/paper.pdf",
        "#/topic/a",
        "docs/a.md",
    ],
)
def test_site_reader_and_private_addresses_are_rejected(url):
    assert external_url({"id": "a", "link": url}) == ""


def test_known_arxiv_pdf_uses_same_id_abstract_page():
    assert (
        external_url(
            {"id": "unrelated", "pdf_url": "https://arxiv.org/pdf/2601.12345v2.pdf"}
        )
        == "https://arxiv.org/abs/2601.12345v2"
    )
    assert external_url({"id": "2601.12345"}) == ""


def test_export_preserves_full_titles_and_uses_external_links_only():
    papers = [
        {
            "id": "a",
            "title": "<script>Title</script> [x](javascript:evil)",
            "route": "local/paper.md",
            "link": "javascript:evil",
            "score": 8,
        },
        {
            "id": "b",
            "title": "Full Original Title",
            "doi": "10.1234/example",
            "score": 7,
        },
    ]
    records = export_records(papers)
    assert records[0]["title"] == papers[0]["title"] and records[0]["url"] == ""
    assert records[1]["url"] == "https://doi.org/10.1234/example"
    text = render_export(records)
    assert "<script>" not in text and "local/paper" not in text
    assert "原文链接缺失" in text


def test_export_rejects_oversize_or_duplicate_lists():
    with pytest.raises(ValueError):
        export_records([{"id": "a"}] * 2)
    with pytest.raises(ValueError):
        export_records([{"id": str(i)} for i in range(101)])


def test_optional_export_scope_is_safe_and_preserves_paper_order():
    records = export_records(
        [{"id": "a", "title": "Original A"}, {"id": "b", "title": "Original B"}]
    )
    text = render_export(
        records,
        "RL",
        {
            "description": "<script>bad</script>",
            "refinement": "[x](javascript:bad)",
            "window": "2025-09-11 至 2026-09-11",
        },
    )
    assert "研究需求" in text and "本次细化" in text and "2025-09-11" in text
    assert "<script>" not in text and "[x](" not in text
    assert text.index("Original A") < text.index("Original B")


def test_export_renders_grouped_sections_with_venue_and_chinese_title():
    papers = [
        {
            "id": "2603.14334v1",
            "title": "Better Approximation for ATSP",
            "zh_title": "更优的非对称旅行商近似算法",
            "canonical_evidence": "将 ATSP 近似比改进至新界",
            "link": "https://arxiv.org/abs/2603.14334v1",
            "score": 9.5,
            "_export_section": "deep",
        },
        {
            "id": "iclr-2025-1",
            "title": "Neural Solver for ATSP",
            "zh_title": "基于神经网络的 ATSP 求解器",
            "conference": "iclr",
            "conference_year": 2025,
            "official_link": "https://openreview.net/forum?id=1",
            "score": 7.2,
            "_export_section": "quick",
        },
    ]
    records = export_records(papers)
    assert records[0]["venue"] == "Arxiv2603"
    assert records[1]["venue"] == "ICLR25"
    text = render_export(records, "ATSP · 大礼包")
    assert "## 精读区（1 篇）" in text
    assert "## 速读区（1 篇）" in text
    assert "`Arxiv2603`" in text and "`ICLR25`" in text
    assert "更优的非对称旅行商近似算法" in text
    assert "将 ATSP 近似比改进至新界" in text
