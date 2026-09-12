import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from topic_research_budget import build_review_pool, select_final_papers


def paper(i, **extra):
    return dict(
        id=str(i),
        title=f"Paper number {i} on different research problems",
        abstract="Complete abstract",
        source="arxiv",
        authors=["Researcher"],
        publication_window_status="included",
        **extra,
    )


def factory():
    client = Mock()
    client.rerank.side_effect = lambda **kw: {
        "results": [
            {"index": i, "relevance_score": i / max(len(kw["documents"]), 1)}
            for i in range(len(kw["documents"]))
        ]
    }
    return Mock(return_value=client), client


def test_budget_bounds_and_filter_before_rerank(tmp_path):
    make, client = factory()
    rows = [paper(i) for i in range(1200)]
    rows[0]["publication_window_status"] = "uncertain"
    result = build_review_pool(
        rows, {"description": "topic"}, tmp_path, client_factory=make
    )
    assert len(result["papers"]) == 300
    assert result["coverage"]["pool_count"] == 1000
    assert sum(len(c.kwargs["documents"]) for c in client.rerank.call_args_list) == 1000
    assert all(p["publication_window_status"] == "included" for p in result["papers"])
    for kwargs in ({"pool_limit": 1001}, {"review_limit": 301}, {"pool_limit": True}):
        with pytest.raises(ValueError):
            build_review_pool([], "topic", tmp_path, **kwargs)


def test_rrf_dedup_evidence_and_stable_order(tmp_path):
    a, b = paper(1), paper(2)
    a["retrieval_evidence"] = [{"lane": "bm25", "query_text": "q", "rank": 2}] * 3
    b["retrieval_evidence"] = [{"lane": "bm25", "query_text": "q", "rank": 1}]
    one = build_review_pool([a, b], "q", tmp_path, rerank=False)
    two = build_review_pool([b, a], "q", tmp_path, rerank=False)
    assert one["papers"] == two["papers"]
    assert one["papers"][0]["id"] == "2"
    assert one["papers"][1]["rrf_score"] == pytest.approx(1 / 62)


def test_projection_uses_qualified_version_not_title_only(tmp_path):
    qualified = paper(1)
    work = paper(2)
    work.update(
        abstract="", publication_window_status="uncertain", versions=[qualified]
    )
    result = build_review_pool([work], "q", tmp_path, rerank=False)
    assert result["papers"][0]["id"] == "1"
    assert result["papers"][0]["abstract"] == "Complete abstract"


def test_rerank_cache_reuses_and_invalidates_content(tmp_path):
    make, client = factory()
    rows = [paper(1)]
    build_review_pool(rows, "q", tmp_path, client_factory=make)
    again = build_review_pool(rows, "q", tmp_path, client_factory=make)
    assert client.rerank.call_count == 1
    assert again["coverage"]["rerank_cache_hits"] == 1
    rows[0]["abstract"] += " new"
    build_review_pool(rows, "q", tmp_path, client_factory=make)
    assert client.rerank.call_count == 2


def test_rerank_cache_separates_model_endpoint_and_query(tmp_path, monkeypatch):
    make, client = factory()
    rows = [paper(1)]
    build_review_pool(rows, "q", tmp_path, client_factory=make)
    monkeypatch.setenv("RERANK_MODEL", "test-model")
    build_review_pool(rows, "q", tmp_path, client_factory=make)
    monkeypatch.setenv("PUBLIC_RERANK_API_BASE_URL", "https://rerank.example/api")
    build_review_pool(rows, "q", tmp_path, client_factory=make)
    build_review_pool(rows, "another query", tmp_path, client_factory=make)
    assert client.rerank.call_count == 4
    for cache in (tmp_path / ".local-runs/topic-research-rerank-cache").glob("*.json"):
        assert set(__import__("json").loads(cache.read_text())) == {"score"}


def test_zero_budget_never_constructs_client(tmp_path):
    make, client = factory()
    result = build_review_pool(
        [paper(1)], "q", tmp_path, review_limit=0, client_factory=make
    )
    assert result["papers"] == []
    make.assert_not_called()
    assert select_final_papers([paper(1, bucket="core", score=9)], result_limit=0) == []


@pytest.mark.parametrize(
    "results",
    [
        [{"index": 0, "relevance_score": float("nan")}],
        [{"index": 1, "relevance_score": 0.5}],
        [{"index": 0, "relevance_score": 0.5}, {"index": 0, "relevance_score": 0.7}],
    ],
)
def test_invalid_scores_not_cached(tmp_path, results):
    make, client = factory()
    client.rerank.side_effect = lambda **kw: {"results": results}
    with pytest.raises(RuntimeError, match="云端重排失败"):
        build_review_pool([paper(1)], "q", tmp_path, client_factory=make)
    assert not list(tmp_path.rglob("*.json"))


def test_canonical_versions_dedup_before_cloud(tmp_path):
    make, client = factory()
    a, b = paper(1), paper(2)
    a["arxiv_id"] = "2501.12345v1"
    b["arxiv_id"] = "2501.12345v2"
    result = build_review_pool([a, b], "q", tmp_path, client_factory=make)
    assert len(result["papers"]) == 1
    assert len(client.rerank.call_args.kwargs["documents"]) == 1


def test_rerank_uses_real_remote_factory_not_local(tmp_path, monkeypatch):
    import reranker_api

    make, client = factory()
    monkeypatch.setenv("RERANK_PROVIDER", "local")
    monkeypatch.setattr(reranker_api, "SiliconFlowReranker", make)
    build_review_pool([paper(1)], "q", tmp_path)
    make.assert_called_once()
    assert make.call_args.kwargs["base_url"].startswith("https://")


def test_remote_failure_or_incomplete_scores_are_errors(tmp_path):
    make, client = factory()
    client.rerank.side_effect = RuntimeError("sensitive error")
    with pytest.raises(RuntimeError, match="云端重排失败"):
        build_review_pool([paper(1)], "q", tmp_path, client_factory=make)
    client.rerank.side_effect = lambda **kw: {"results": []}
    with pytest.raises(RuntimeError):
        build_review_pool([paper(1)], "q", tmp_path, client_factory=make)


def test_selection_score_first_not_bucket_and_no_filling():
    rows = [
        paper(1, score=7, bucket="core"),
        paper(2, score=9, bucket="related"),
        paper(3, score=9, bucket="review"),
        paper(4, score=5, bucket="related"),
    ]
    rows.append(dict(rows[1]))
    result = select_final_papers(rows)
    assert [p["id"] for p in result] == ["2", "1"]
    with pytest.raises(ValueError):
        select_final_papers([], result_limit=101)


def test_selection_tie_rerank_date_then_stable_id():
    rows = [
        paper(
            1, score=8, bucket="core", rerank_score=0.2, publication_date="2026-01-01"
        ),
        paper(
            2, score=8, bucket="core", rerank_score=0.3, publication_date="2025-01-01"
        ),
        paper(
            3, score=8, bucket="core", rerank_score=0.2, publication_date="2026-02-01"
        ),
    ]
    assert [p["id"] for p in select_final_papers(rows)] == ["2", "3", "1"]


@pytest.mark.parametrize("score", [True, False, float("nan"), float("inf"), -float("inf"), 999, 10**1000, 10.1, 5.9, None, "bad"])
def test_selection_excludes_invalid_scores(score):
    assert select_final_papers([paper(1, score=score, bucket="core")]) == []


def test_qualified_representative_keeps_same_version():
    original = paper(1, score=9, bucket="core")
    other = paper(2)
    other["abstract"] = "Much longer complete abstract of another valid version"
    original["versions"] = [other]
    selected = select_final_papers([original])
    assert selected[0]["id"] == "1"
    assert selected[0]["abstract"] == "Complete abstract"
