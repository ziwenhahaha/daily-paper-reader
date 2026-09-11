from unittest.mock import patch
from pathlib import Path
import sys

from bs4 import BeautifulSoup
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import starter_pack_publications as publications


TITLE = "A new reliable method for asymmetric traveling salesman problems"
URL = "https://proceedings.iclr.cc/paper_files/paper/2025/hash/abc-Abstract-Conference.html"
PDF = "https://proceedings.iclr.cc/paper_files/paper/2025/file/abc-Paper-Conference.pdf"


def paper(**kwargs):
    return {
        "id": "x",
        "source": "ICLR-2025-Public",
        "title": TITLE,
        "authors": ["Ada Lovelace"],
        **kwargs,
    }


def test_public_is_not_accepted_and_failure_is_not_cached(tmp_path):
    with patch.object(publications, "_get", side_effect=requests.HTTPError()):
        out = publications.verify_publications([paper()], tmp_path)
    assert out[0]["conference_acceptance_status"] == "unverified"
    assert not list(tmp_path.rglob("*.json"))


def test_official_match_pdf_and_dates_unchanged(tmp_path):
    index = BeautifulSoup(
        f'<li><a href="{URL}">{TITLE}</a><span class="paper-authors">Ada Lovelace</span></li>',
        "html.parser",
    )
    detail = BeautifulSoup(
        f'<meta name="citation_pdf_url" content="{PDF}">', "html.parser"
    )
    original = paper(
        publication_date="2025",
        publication_date_precision="year",
        publication_date_source="year only",
        publication_date_kind="unknown",
    )
    with patch.object(publications, "_get", side_effect=[index, detail]):
        out = publications.verify_publications([original], tmp_path)[0]
    assert out["conference_acceptance_status"] == "accepted"
    assert out["official_link"] == URL and out["official_pdf_url"] == PDF
    assert all(out[k] == original[k] for k in original)
    assert "official_pdf_url" not in original
    with patch.object(publications, "_get", return_value=detail) as get:
        publications.verify_publications([original], tmp_path)
        get.assert_not_called()


def test_resolve_pdfs_false_uses_index_only(tmp_path):
    index = BeautifulSoup(
        f'<li><a href="{URL}">{TITLE}</a><span class="paper-authors">Ada Lovelace</span></li>',
        "html.parser",
    )
    with patch.object(publications, "_get", return_value=index) as get:
        out = publications.verify_publications([paper()], tmp_path, resolve_pdfs=False)[
            0
        ]
    assert out["conference_acceptance_status"] == "accepted"
    assert out["official_link"] == URL
    assert "official_pdf_url" not in out
    get.assert_called_once_with("https://proceedings.iclr.cc/paper_files/paper/2025")


def test_pdf_errors_or_empty_results_are_not_cached(tmp_path):
    with patch.object(
        publications,
        "_get",
        return_value=BeautifulSoup("<p>Unavailable</p>", "html.parser"),
    ):
        assert publications._pdf(URL, tmp_path) == ""
    assert not list(tmp_path.rglob("pdf-*.json"))
    with patch.object(publications, "_get", side_effect=requests.HTTPError()):
        try:
            publications._pdf(URL, tmp_path)
        except requests.HTTPError:
            pass
        else:
            raise AssertionError("Expected request failure")
    assert not list(tmp_path.rglob("pdf-*.json"))


def test_rejection_overrides_source_and_unknown_stays_unknown(tmp_path):
    out = publications.verify_publications(
        [
            paper(source="ICLR-2025-Accepted", decision="Withdrawn"),
            {"id": "n", "title": TITLE},
            paper(source="SOSP-2026-ACM-Accepted"),
        ],
        tmp_path,
    )
    assert [p["conference_acceptance_status"] for p in out] == [
        "rejected",
        "unverified",
        "accepted",
    ]


def test_short_titles_authors_and_ambiguous_matches():
    rows = [{"title": "A method", "authors": "Ada Lovelace", "url": URL}]
    assert publications._match({"title": "A method"}, rows) is None
    assert (
        publications._match({"title": "A method", "authors": ["Someone Else"]}, rows)
        is None
    )
    assert publications._match({"title": "A method", "authors": ["Ada Lovelace"]}, rows)
    assert (
        publications._match(
            {"title": "A method", "authors": ["Ada Lovelace"]}, rows * 2
        )
        is None
    )


def test_neurips_main_track_followed(tmp_path):
    home = BeautifulSoup(
        '<a href="/paper_files/paper/2025/vol38-main-conference">Main Conference</a>',
        "html.parser",
    )
    main = BeautifulSoup(
        f'<li><a href="/paper_files/paper/2025/hash/abc-Abstract-Conference.html">{TITLE}</a></li>',
        "html.parser",
    )
    with patch.object(publications, "_get", side_effect=[home, main]) as get:
        rows = publications._load_index("neurips", 2025, tmp_path)
    assert len(rows) == 1
    assert get.call_args_list[1].args[0].endswith("/2025/vol38-main-conference")


def test_icml_index_and_no_guessed_2026_volume():
    soup = BeautifulSoup(
        f'<div class="paper"><p class="title">{TITLE}</p><span class="authors">Ada Lovelace</span><a href="sample.html">abs</a></div>',
        "html.parser",
    )
    rows = publications._parse_index(
        soup, "https://proceedings.mlr.press/v267/", "icml"
    )
    assert rows[0]["url"] == "https://proceedings.mlr.press/v267/sample.html"
    assert not publications._index_url("icml", 2026)


def test_arxiv_unchanged_and_nonofficial_pdf_rejected(tmp_path):
    original = paper(source="arxiv")
    assert publications.verify_publications([original], tmp_path) == [original]
    with patch.object(
        publications,
        "_get",
        return_value=BeautifulSoup(
            '<a href="https://arxiv.org/pdf/2501.00001">PDF</a>', "html.parser"
        ),
    ):
        assert publications._pdf(URL) == ""
