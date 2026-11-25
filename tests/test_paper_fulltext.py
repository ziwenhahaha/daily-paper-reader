import importlib.util
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
spec = importlib.util.spec_from_file_location(
    "fulltext_generator", Path(__file__).resolve().parents[1] / "src/6.generate_docs.py"
)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)
FULLTEXT = "# Introduction\n" + "Actual paper body and proof. " * 150


def test_invalid_cache_is_replaced_by_real_fulltext(tmp_path, monkeypatch):
    target = tmp_path / "paper.txt"
    target.write_text("")
    fetch = Mock(return_value=FULLTEXT)
    monkeypatch.setattr(generator, "fetch_paper_markdown_via_jina", fetch)
    assert (
        generator.ensure_text_content("https://arxiv.org/pdf/2510.17595v1", str(target))
        == FULLTEXT
    )
    assert target.read_text() == FULLTEXT
    fetch.assert_called_once()
    generator.ensure_text_content("https://arxiv.org/pdf/2510.17595v1", str(target))
    fetch.assert_called_once()


def test_error_response_is_not_published_as_fulltext(tmp_path, monkeypatch):
    target = tmp_path / "paper.txt"
    monkeypatch.setattr(
        generator,
        "fetch_paper_markdown_via_jina",
        lambda _: "<html>Access denied</html>" * 100,
    )
    response = Mock(content=b"<html>not a pdf</html>")
    monkeypatch.setattr(generator.requests, "get", lambda *a, **k: response)
    with pytest.raises(ValueError):
        generator.ensure_text_content("https://arxiv.org/pdf/2510.17595v1", str(target))
    assert not target.exists()


def test_withdrawn_pdf_notice_is_not_a_paper(tmp_path, monkeypatch):
    notice = (
        "Title: arXiv\nWarning: Target URL returned error 404\nThis version has been withdrawn and is unavailable\n"
        + "navigation " * 200
    )
    assert not generator.is_usable_paper_text(notice)
    monkeypatch.setattr(generator, "fetch_paper_markdown_via_jina", lambda _: notice)
    monkeypatch.setattr(
        generator.requests, "get", lambda *a, **k: Mock(status_code=404)
    )
    with pytest.raises(generator.PaperFulltextUnavailable):
        generator.ensure_text_content(
            "https://arxiv.org/pdf/2509.26073v2", str(tmp_path / "paper.txt")
        )


def test_pdf_download_uses_explicit_headers_and_retries_transient_520(
    tmp_path, monkeypatch
):
    target = tmp_path / "paper.txt"
    monkeypatch.setattr(generator, "fetch_paper_markdown_via_jina", lambda _: None)
    monkeypatch.setattr(generator.time, "sleep", lambda _: None)
    monkeypatch.setattr(generator, "extract_pdf_text", lambda _: FULLTEXT)

    calls = []

    def fake_get(url, timeout=60, headers=None, **kwargs):
        calls.append({"url": url, "timeout": timeout, "headers": headers})
        if len(calls) == 1:
            return Mock(status_code=520, content=b"<html>Cloudflare 520</html>")
        resp = Mock(status_code=200, content=b"%PDF-1.7\nbody")
        resp.raise_for_status = Mock()
        return resp

    monkeypatch.setattr(generator.requests, "get", fake_get)
    result = generator.ensure_text_content(
        "https://ojs.aaai.org/index.php/AAAI/article/download/33456/35611",
        str(target),
    )
    assert result == FULLTEXT
    assert target.read_text() == FULLTEXT
    assert len(calls) == 2
    assert calls[0]["headers"]["User-Agent"].startswith("DailyPaperReader/")
    assert "application/pdf" in calls[0]["headers"]["Accept"]


def test_pdf_download_does_not_retry_403_or_404(tmp_path, monkeypatch):
    monkeypatch.setattr(generator, "fetch_paper_markdown_via_jina", lambda _: None)
    monkeypatch.setattr(generator.time, "sleep", lambda _: None)
    for code in (403, 404):
        calls = []

        def fake_get(url, timeout=60, headers=None, **kwargs):
            calls.append(url)
            resp = Mock(status_code=code, content=b"")
            resp.raise_for_status.side_effect = generator.requests.HTTPError(
                f"HTTP {code}", response=resp
            )
            return resp

        monkeypatch.setattr(generator.requests, "get", fake_get)
        with pytest.raises(generator.requests.HTTPError):
            generator.ensure_text_content(
                f"https://example.invalid/{code}.pdf",
                str(tmp_path / f"paper-{code}.txt"),
            )
        assert len(calls) == 1
