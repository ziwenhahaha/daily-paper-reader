import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from starter_pack import review_candidates


def test_review_budget_resumes_without_duplicate_model_calls(tmp_path):
    papers = [
        {
            "id": str(i),
            "canonical_id": "work:" + str(i),
            "title": "ATSP " + str(i),
            "abstract": "asymmetric traveling salesman problem",
            "versions": [],
        }
        for i in range(3)
    ]
    client = Mock()

    def response(messages, **kwargs):
        import json

        data = json.loads(messages[-1]["content"])
        return {
            "parsed": {
                "papers": [
                    {
                        "id": p["id"],
                        "score": 8,
                        "scope_match": True,
                        "evidence": p["title"],
                        "reason": "test",
                    }
                    for p in data["papers"]
                ]
            }
        }

    client.chat_structured.side_effect = response
    factory = lambda: client
    topic = {
        "tag": "ATSP",
        "description": "asymmetric traveling salesman problem",
        "queries": [],
        "keywords": [],
    }
    one = review_candidates(
        papers, topic, tmp_path, 1, client_factory=factory, model_key=["test", "test"]
    )
    assert one["remaining"] == 2 and one["new_reviews"] == 1
    two = review_candidates(
        papers, topic, tmp_path, 10, client_factory=factory, model_key=["test", "test"]
    )
    assert two["remaining"] == 0 and two["new_reviews"] == 2
    three = review_candidates(
        papers, topic, tmp_path, 10, client_factory=factory, model_key=["test", "test"]
    )
    assert three["new_reviews"] == 0 and three["remaining"] == 0
    assert len(three["papers"]) == 3
    assert client.chat_structured.call_count == 2


def test_metadata_only_is_notice_not_fake_core(tmp_path):
    factory = Mock(side_effect=AssertionError("不得调用模型"))
    result = review_candidates(
        [{"id": "notice", "title": "ATSP", "abstract": ""}],
        {},
        tmp_path,
        10,
        client_factory=factory,
        model_key=["x"],
    )
    assert result["papers"][0]["bucket"] == "notice"
    assert result["new_reviews"] == 0


def test_wire_aliases_preserve_arxiv_version_ids(tmp_path):
    import json

    client = Mock()

    def response(messages, **kwargs):
        payload = json.loads(messages[-1]["content"])
        assert payload["papers"][0]["id"] == "p0"
        return {
            "parsed": {
                "papers": [
                    {
                        "id": "p0",
                        "score": 8,
                        "scope_match": True,
                        "evidence": "ATSP",
                        "reason": "版本明确",
                    }
                ]
            }
        }

    client.chat_structured.side_effect = response
    result = review_candidates(
        [
            {
                "id": "2512.19321v2",
                "title": "ATSP",
                "abstract": "asymmetric traveling salesman",
            }
        ],
        {"tag": "ATSP"},
        tmp_path,
        1,
        client_factory=lambda: client,
        model_key=["test"],
    )
    assert result["papers"][0]["id"] == "2512.19321v2"
