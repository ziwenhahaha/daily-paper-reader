import copy
import json
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from starter_pack_guide import (
    generate_guide,
    guide_cache_key,
    render_guide,
    validate_guide,
)


@pytest.fixture
def papers():
    return [
        {
            "canonical_id": "arxiv:1",
            "id": "1",
            "title": "Asymmetric TSP",
            "abstract": "An approximation algorithm.",
            "route": "20250911/paper.md",
            "publication_date": "2025-09-11",
            "publication_date_precision": "day",
            "versions": [
                {
                    "source": "arxiv",
                    "publication_date": "2025-09-11",
                    "publication_date_precision": "day",
                    "pdf_url": "https://arxiv.org/pdf/1",
                    "doi": "10.1234/paper",
                }
            ],
        }
    ]


@pytest.fixture
def guide():
    return {
        "overview": {"text": "研究非对称路径问题。", "paper_ids": ["arxiv:1"]},
        "sections": [
            {
                "title": "近似方法",
                "text": "本篇提供近似算法。",
                "paper_ids": ["arxiv:1"],
            }
        ],
        "reading_order": [
            {"paper_id": "arxiv:1", "reason": "先理解问题定义。", "level": "入门"}
        ],
    }


def test_small_pool_only_uses_available_paper(papers, guide):
    client = Mock()
    client.chat_structured.return_value = {"parsed": guide}
    assert generate_guide("ATSP", papers, client) == guide
    payload = json.loads(client.chat_structured.call_args.args[0][1]["content"])
    assert [p["canonical_id"] for p in payload["papers"]] == ["arxiv:1"]
    text = render_guide(guide, papers, {"topic": "ATSP", "window": "近365天"})
    assert "[Asymmetric TSP](/20250911/paper.md)" in text
    assert "2025-09-11（日精度）" in text
    assert "[PDF](https://arxiv.org/pdf/1)" in text
    assert "[DOI](https://doi.org/10.1234/paper)" in text
    assert "不是完整领域史" in text


def test_empty_pool_never_calls_model():
    client = Mock()
    result = generate_guide("ATSP", [], client)
    client.chat_structured.assert_not_called()
    assert "没有符合精选条件" in render_guide(result, [])


@pytest.mark.parametrize("target", ["overview", "sections", "reading_order"])
def test_unknown_references_are_rejected(papers, guide, target):
    if target == "overview":
        guide[target]["paper_ids"] = ["invented"]
    elif target == "sections":
        guide[target][0]["paper_ids"] = ["invented"]
    else:
        guide[target][0]["paper_id"] = "invented"
    with pytest.raises(ValueError):
        validate_guide(guide, papers)


@pytest.mark.parametrize("refs", [[], ["arxiv:1", "arxiv:1"], [None]])
def test_empty_duplicate_malformed_references_rejected(papers, guide, refs):
    guide["overview"]["paper_ids"] = refs
    with pytest.raises(ValueError):
        validate_guide(guide, papers)


@pytest.mark.parametrize(
    "injection",
    ["<script>alert(1)</script>", "[link](javascript:alert(1))", "https://evil.test"],
)
def test_model_markup_and_links_rejected(papers, guide, injection):
    guide["sections"][0]["text"] = injection
    with pytest.raises(ValueError):
        render_guide(guide, papers)


def test_metadata_does_not_inject_html_or_links(papers, guide):
    papers[0]["title"] = "<img src=x onerror=alert(1)> [bad](https://evil.test)"
    papers[0]["route"] = "javascript:alert(1)"
    papers[0]["versions"][0]["pdf_url"] = "javascript:alert(1)"
    text = render_guide(guide, papers, {"topic": "<script>bad</script>"})
    assert "<script>" not in text and "<img" not in text
    assert "[bad](" not in text and "(javascript:" not in text


@pytest.mark.parametrize(
    "route",
    [
        "//evil.test/a",
        "../secret.private",
        "%2e%2e/secret.private",
        "https://evil.test",
    ],
)
def test_untrusted_routes_are_not_links(papers, guide, route):
    papers[0]["route"] = route
    text = render_guide(guide, papers)
    assert "[Asymmetric TSP](" not in text


def test_invalid_response_and_duplicate_inputs_fail(papers, guide):
    client = Mock()
    client.chat_structured.return_value = {"parse_error": "bad", "parsed": guide}
    with pytest.raises(ValueError):
        generate_guide("ATSP", papers, client)
    with pytest.raises(ValueError):
        generate_guide("ATSP", papers * 2, client)


def test_cache_key_covers_evidence_and_model(papers):
    key = guide_cache_key("ATSP", papers, "model", "endpoint")
    changed = copy.deepcopy(papers)
    changed[0]["abstract"] += " New result."
    assert key == guide_cache_key("ATSP", papers, "model", "endpoint")
    assert key != guide_cache_key("ATSP", changed, "model", "endpoint")
    assert key != guide_cache_key("ATSP", papers, "model2", "endpoint")
    assert key != guide_cache_key("ATSP", papers, "model", "endpoint2")
