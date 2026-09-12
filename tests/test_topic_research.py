import copy
import json
from pathlib import Path
import sys
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import topic_research as research


def config():
    return {
        "subscriptions": {
            "intent_profiles": [
                {
                    "tag": "ATSP",
                    "description": "asymmetric traveling salesman",
                    "keywords": ["ATSP"],
                    "intent_queries": [],
                    "paused": True,
                }
            ]
        }
    }


def test_snapshot_isolated_window_and_query_constraints():
    source = config()
    old = copy.deepcopy(source)
    snapshot = {
        "tag": "ATSP",
        "keywords": ["reinforcement learning"],
        "intent_queries": [],
        "description": "robot control",
        "refinement": "机器人",
        "constraint_groups": [["reinforcement learning", "RL"], ["robot", "robotics"]],
        "api_key": "must-not-persist",
    }
    plan, scoped = research.research_plan(source, "ATSP", "90", "2026-09-12", snapshot)
    assert source == old and "api_key" not in plan["snapshot"]
    assert plan["windows"]["arxiv"]["start"] == "2026-06-14"
    assert plan["conferences"] == []
    assert "conference" not in plan["windows"]
    keywords = [t["query"]["query_text"] for t in plan["tasks"] if t["lane"] == "bm25"]
    assert set(keywords) == {
        "reinforcement learning robot",
        "reinforcement learning robotics",
        "RL robot",
        "RL robotics",
    }
    assert all(t["bounded"] for t in plan["tasks"])
    assert all(t["limit"] <= 100 for t in plan["tasks"])
    assert scoped["subscriptions"]["intent_profiles"][0]["paused"] is False


def test_refinement_cannot_be_only_ui_text():
    with pytest.raises(ValueError):
        research.safe_profile({"tag": "ATSP", "refinement": "robot"}, "ATSP")


def test_keyword_and_semantic_rewrite_keep_existing_lane_semantics():
    from topic_preview import english_groups

    cfg = {
        "subscriptions": {
            "intent_profiles": [
                {
                    "tag": "test",
                    "keywords": [
                        {"keyword": "RL", "query": "offline reinforcement learning"},
                        {"keyword": "ignored", "enabled": "false"},
                    ],
                    "intent_queries": [],
                }
            ]
        }
    }
    plan, _ = research.research_plan(cfg, "test", "90", "2026-09-12")
    assert english_groups(plan["snapshot"]) == [["RL"]]
    queries = [t["query"]["query_text"] for t in plan["tasks"] if t["lane"] == "bm25"]
    assert queries == ["RL"]
    assert plan["profile"]["review_keywords"] == ["RL"]
    assert all(
        t["query"]["query_text"] == "offline reinforcement learning"
        for t in plan["tasks"]
        if t["lane"] == "embedding"
    )


def test_bounded_pipeline_and_content_resume_never_retrieves(tmp_path, monkeypatch):
    rows = [
        {
            "id": str(i),
            "title": "ATSP",
            "abstract": "ATSP",
            "source": "arxiv",
            "publication_window_status": "included",
        }
        for i in range(400)
    ]
    recall = Mock(return_value={"papers": rows, "tasks": [], "coverage": {}})
    monkeypatch.setattr(research, "run_retrieval", recall)
    monkeypatch.setattr(research, "verify_publications", lambda p, *a, **k: p)
    monkeypatch.setattr(
        research,
        "deduplicate_papers",
        lambda p: {"papers": p, "possible_duplicates": []},
    )
    pool = Mock(return_value={"papers": rows[:300], "coverage": {"review_count": 300}})
    monkeypatch.setattr(research, "build_review_pool", pool)

    def review(p, *a, **kw):
        assert len(p) == 300 and kw["max_new_reviews"] == 300
        return {
            "papers": [{**r, "bucket": "core", "score": 8} for r in p],
            "remaining": 0,
            "new_reviews": 300,
            "cached_reviews": 0,
        }

    reviewer = Mock(side_effect=review)
    monkeypatch.setattr(research, "review_candidates", reviewer)
    import starter_pack_publish

    publisher = Mock(return_value={"status": "content_pending"})
    monkeypatch.setattr(starter_pack_publish, "publish_pack", publisher)
    result = research.run_research(config(), "ATSP", "90", "2026-09-12", tmp_path)
    assert result["selected_count"] == 100
    selection = json.loads(
        (
            tmp_path
            / ".local-runs/starter-pack-cache/runs"
            / result["run_id"]
            / "selected.json"
        ).read_text()
    )
    assert len(selection["papers"]) == 100
    research.run_research(
        {},
        "",
        "starter",
        "2026-10-01",
        tmp_path,
        action="continue-content",
        run_id=result["run_id"],
    )
    continued = json.loads(
        (
            tmp_path
            / ".local-runs/starter-pack-cache/runs"
            / result["run_id"]
            / "manifest.json"
        ).read_text()
    )
    assert (
        continued["new_reviews"] == 0 and continued["last_action"] == "continue-content"
    )
    assert recall.call_count == pool.call_count == reviewer.call_count == 1
    assert publisher.call_count == 2
    # 模拟检查点缓存被淘汰，但站点固定名单仍在：不重新调用检索/评分。
    folder = tmp_path / ".local-runs/starter-pack-cache/runs" / result["run_id"]
    (folder / "selected.json").unlink()
    (folder / "manifest.json").unlink()
    research.run_research(
        {},
        "",
        "90",
        "2026-09-12",
        tmp_path,
        action="continue-content",
        run_id=result["run_id"],
    )
    assert recall.call_count == reviewer.call_count == 1 and publisher.call_count == 3


def test_repeated_run_uses_frozen_selection(tmp_path, monkeypatch):
    plan, _ = research.research_plan(config(), "ATSP", "365", "2026-09-12")
    folder = tmp_path / ".local-runs/starter-pack-cache/runs" / plan["run_id"]
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_text(
        json.dumps(
            {
                "run_id": plan["run_id"],
                "research_version": research.VERSION,
                "mode": "365",
            }
        )
    )
    (folder / "selected.json").write_text(
        json.dumps({"selection_complete": True, "papers": []})
    )
    monkeypatch.setattr(
        research, "run_retrieval", Mock(side_effect=AssertionError("不重跑"))
    )
    result = research.run_research(
        config(), "ATSP", "365", "2026-09-12", tmp_path, publish=False
    )
    assert result["status"] == "selection_ready"


def test_workflow_safe_inputs_and_saved_checkpoints():
    text = (
        Path(__file__).resolve().parents[1] / ".github/workflows/topic-research.yml"
    ).read_text()
    assert "continue-content" in text and "topic-research-rerank-cache" in text
    assert "TOPIC_SNAPSHOT: ${{ inputs.profile_snapshot }}" in text
    assert "subprocess.run(args, check=True)" in text
    assert (
        "scripts/request_pages_build.py" in text
        and "include-hidden-files: true" in text
    )


def test_legacy_90_365_dispatch_to_budgeted_engine_without_local_models(monkeypatch):
    import long_range_review

    for name in ("torch", "sentence_transformers", "transformers"):
        monkeypatch.setitem(sys.modules, name, None)
    plan = {
        "profiles": [{"tag": "ATSP"}],
        "bm25_queries": [{"query_text": "ATSP"}],
        "embedding_queries": [],
    }
    monkeypatch.setattr(long_range_review, "build_pipeline_inputs", lambda _: plan)
    run = Mock(return_value={"selected_count": 100})
    monkeypatch.setattr(research, "run_research", run)
    for days in (90, 365):
        long_range_review.run_review(
            config(), days, "/tmp/topic-test", "20250912-20260911"
        )
        assert run.call_args.args[2:4] == (str(days), "2026-09-12")
