"""统一专题研究流水线回归测试（标准 Step 2→3→4→5→6 + 单轨侧边栏）。"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import topic_research as tr  # noqa: E402


def _base_config():
    return {
        "subscriptions": {
            "intent_profiles": [
                {
                    "tag": "user-sim",
                    "description": "LLM user simulation for interactive agents",
                    "enabled": True,
                    "paused": False,
                    "keywords": [
                        {"keyword": "user simulation", "query": "LLM-based user simulator", "enabled": True}
                    ],
                    "intent_queries": [
                        {"query": "simulating realistic users with LLMs", "enabled": True}
                    ],
                    "paper_sources": ["arxiv"],
                }
            ]
        }
    }


def test_safe_profile_strips_secrets_and_validates_constraints():
    raw = {
        "tag": "user-sim",
        "description": "User sim",
        "keywords": [{"keyword": "user sim", "query": "user simulator", "api_key": "SECRET"}],
        "intent_queries": [{"query": "simulating users", "token": "SECRET"}],
        "api_key": "SECRET",
    }
    cleaned = tr.safe_profile(raw, "user-sim")
    assert "SECRET" not in json.dumps(cleaned)
    assert cleaned["keywords"][0]["keyword"] == "user sim"
    assert cleaned["keywords"][0]["query"] == "user simulator"
    with pytest.raises(ValueError):
        tr.safe_profile({**raw, "refinement": "narrow only"}, "user-sim")
    refined = tr.safe_profile(
        {**raw, "refinement": "dialogue only", "constraint_groups": [["user sim"], ["dialogue"]]},
        "user-sim",
    )
    assert refined["constraint_groups"] == [["user sim"], ["dialogue"]]


def test_build_topic_token_and_backtrack_shape():
    token = tr.build_topic_token("2025-11-25", "2026-11-25", "starter", "user-sim", {})
    assert token == "20251125-20261124-starter-user-sim"
    refined = tr.build_topic_token(
        "2025-11-25",
        "2026-11-25",
        "starter",
        "user-sim",
        {"refinement": "dialogue only", "constraint_groups": [["dialogue"]]},
    )
    assert refined.startswith("20251125-20261124-starter-user-sim-")
    assert refined != token
    cn_token = tr.build_topic_token("2025-11-25", "2026-11-25", "90", "用户模拟", {})
    assert cn_token.startswith("20251125-20261124-90-t")


def test_build_standard_rrf_payload_filters_unqualified_and_preserves_lanes():
    plan, _ = tr.research_plan(_base_config(), "user-sim", "starter", "2026-11-25", conferences=["iclr"])
    works = [
        {
            "id": "2611.00001v1",
            "canonical_id": "arxiv:2611.00001",
            "title": "Simulating Users with LLMs",
            "abstract": "Detailed abstract about LLM user simulation.",
            "source": "arxiv",
            "published": "2026-11-01",
            "publication_date": "2026-11-01",
            "publication_date_precision": "day",
            "publication_window_status": "in_window",
            "retrieval_evidence": [
                {"lane": "bm25", "query_text": "user simulation", "rank": 1},
                {"lane": "embedding", "query_text": "simulating realistic users with LLMs", "rank": 2},
            ],
            "versions": [
                {
                    "id": "2611.00001v1",
                    "title": "Simulating Users with LLMs",
                    "abstract": "Detailed abstract about LLM user simulation.",
                    "source": "arxiv",
                    "published": "2026-11-01",
                    "publication_date": "2026-11-01",
                    "publication_date_precision": "day",
                    "publication_window_status": "in_window",
                    "retrieval_evidence": [
                        {"lane": "bm25", "query_text": "user simulation", "rank": 1},
                        {"lane": "embedding", "query_text": "simulating realistic users with LLMs", "rank": 2},
                    ],
                }
            ],
        },
        {
            # 未核实录用的会议版，无合格回退版 → 必须排除
            "id": "openreview-unverified",
            "canonical_id": "openreview-unverified",
            "title": "Unverified Public Submission",
            "abstract": "Some abstract.",
            "source": "ICLR-2026-Public",
            "conference": "iclr",
            "conference_year": 2026,
            "conference_acceptance_status": "unverified",
            "publication_window_status": "in_window",
            "versions": [
                {
                    "id": "openreview-unverified",
                    "title": "Unverified Public Submission",
                    "abstract": "Some abstract.",
                    "source": "ICLR-2026-Public",
                    "conference": "iclr",
                    "conference_year": 2026,
                    "conference_acceptance_status": "unverified",
                    "publication_window_status": "in_window",
                }
            ],
        },
        {
            # 无摘要的候选 → 必须排除
            "id": "2611.00002v1",
            "canonical_id": "arxiv:2611.00002",
            "title": "Missing Abstract",
            "abstract": "",
            "source": "arxiv",
            "publication_window_status": "in_window",
        },
    ]
    payload, works_by_id, stats = tr.build_standard_rrf_payload(works, plan)
    assert stats["eligible_count"] == 1
    assert stats["excluded_unqualified_count"] == 2
    assert list(works_by_id) == ["2611.00001v1"]
    q_types = {q["type"] for q in payload["queries"]}
    assert q_types == {"keyword", "intent_query"}
    assert set(payload["papers"][0]["tags"]) == {"keyword:user-sim", "query:user-sim"}


def test_build_standard_rrf_payload_synthesizes_intent_query_for_keyword_only_profile():
    cfg = _base_config()
    cfg["subscriptions"]["intent_profiles"][0]["keywords"] = [{"keyword": "user sim", "enabled": True}]
    cfg["subscriptions"]["intent_profiles"][0]["intent_queries"] = []
    plan, _ = tr.research_plan(cfg, "user-sim", "90", "2026-11-25")
    works = [
        {
            "id": "2611.00003v1",
            "title": "Keyword Hit Paper",
            "abstract": "Abstract text.",
            "source": "arxiv",
            "publication_window_status": "in_window",
            "versions": [
                {
                    "id": "2611.00003v1",
                    "title": "Keyword Hit Paper",
                    "abstract": "Abstract text.",
                    "source": "arxiv",
                    "publication_window_status": "in_window",
                    "retrieval_evidence": [{"lane": "bm25", "query_text": "user sim", "rank": 1}],
                }
            ],
        }
    ]
    payload, _, _ = tr.build_standard_rrf_payload(works, plan)
    assert any(q["type"] == "intent_query" for q in payload["queries"])


def test_end_to_end_standard_pipeline_publishes_single_track_sidebar_and_media(tmp_path):
    config = _base_config()
    before_config = copy.deepcopy(config)
    arxiv_paper = {
        "id": "2611.10001v1",
        "title": "Realistic LLM User Simulators",
        "abstract": "We study realistic LLM-based user simulators for multi-turn evaluation.",
        "authors": ["Alice Smith", "Bob Jones"],
        "source": "arxiv",
        "published": "2026-11-10",
        "publication_date": "2026-11-10",
        "publication_date_precision": "day",
        "publication_date_source": "arXiv",
        "publication_date_kind": "preprint",
        "publication_window_status": "in_window",
        "link": "https://arxiv.org/abs/2611.10001v1",
        "pdf_url": "https://arxiv.org/pdf/2611.10001v1",
        "retrieval_source": "arxiv",
        "retrieval_evidence": [
            {"lane": "bm25", "query_text": "user simulation", "rank": 1},
            {"lane": "embedding", "query_text": "simulating realistic users with LLMs", "rank": 1},
        ],
    }
    conf_paper = {
        "id": "iclr-2026-abc",
        "title": "Benchmarking Conversational User Simulators",
        "abstract": "A comprehensive benchmark for conversational user simulators.",
        "authors": ["Carol Lee"],
        "source": "ICLR-2026-Accepted",
        "conference": "iclr",
        "conference_year": 2026,
        "conference_acceptance_status": "accepted",
        "published": "2026-04-20",
        "publication_date": "2026-04-20",
        "publication_date_precision": "day",
        "publication_date_source": "proceedings",
        "publication_date_kind": "proceedings",
        "publication_window_status": "in_window",
        "link": "https://openreview.net/forum?id=abc",
        "pdf_url": "https://openreview.net/pdf?id=abc",
        "retrieval_source": "iclr",
        "retrieval_evidence": [
            {"lane": "embedding", "query_text": "simulating realistic users with LLMs", "rank": 2},
        ],
    }

    # 预先放一个已有 arXiv 历史页（含用户笔记），验证同版本路由复用且不丢失用户笔记
    existing_doc = tmp_path / "docs/202611/10/2611.10001v1-realistic-llm-user-simulators.md"
    existing_doc.parent.mkdir(parents=True, exist_ok=True)
    existing_doc.write_text(
        "---\n"
        'id: "2611.10001v1"\n'
        'title: "Realistic LLM User Simulators"\n'
        'title_zh: "真实的大模型用户模拟器"\n'
        'evidence: "直接研究大模型用户模拟"\n'
        'tldr: "提出真实的大模型用户模拟器。"\n'
        'motivation: "现有评估缺乏真实用户反馈。"\n'
        'method: "构建多轮对话模拟器。"\n'
        'result: "显著提升评估一致性。"\n'
        'conclusion: "适合作为对话代理评测基准。"\n'
        'paper_media_checked: true\n'
        "---\n\n## 摘要\n已有中文摘要。\n\n## Abstract\nOriginal abstract.\n\n## 我的笔记\n用户手写笔记必须保留。\n",
        encoding="utf-8",
    )

    executed_steps = []

    def fake_step_runner(label, cmd, env):
        executed_steps.append((label, cmd))
        script_name = Path(cmd[1]).name
        out_path = Path(cmd[cmd.index("--output") + 1])
        in_path = Path(cmd[cmd.index("--input") + 1])
        data = json.loads(in_path.read_text(encoding="utf-8"))
        if script_name == "3.rank_papers.py":
            assert "--rerank-global-pool-limit" in cmd
            for q in data["queries"]:
                if q["type"] == "intent_query":
                    q["ranked"] = [
                        {"paper_id": "2611.10001v1", "score": 0.95, "star_rating": 5},
                        {"paper_id": "iclr-2026-abc", "score": 0.72, "star_rating": 4},
                    ]
            tr.write_json(out_path, data)
        elif script_name == "4.llm_refine_papers.py":
            assert "--config" in cmd
            data["llm_ranked"] = [
                {
                    "paper_id": "2611.10001v1",
                    "score": 9.0,
                    "evidence_cn": "核心研究大模型用户模拟",
                    "evidence_en": "Core LLM user simulation",
                    "tldr_cn": "本文提出多轮真实大模型用户模拟器，提升代理评估一致性。",
                    "title_zh": "真实的大模型用户模拟器",
                    "motivation_cn": "现有代理评测缺少真实用户交互。",
                    "method_cn": "采用多轮意图建模与反馈模拟器。",
                    "result_cn": "在多项基准上贴近人类评测。",
                    "conclusion_cn": "证明大模型用户模拟可行有效。",
                    "matched_query_tag": "query:user-sim",
                },
                {
                    "paper_id": "iclr-2026-abc",
                    "score": 7.0,
                    "evidence_cn": "提出对话用户模拟评测基准",
                    "evidence_en": "Conversational user simulator benchmark",
                    "tldr_cn": "构建对话用户模拟综合评测集，分析主流模型局限。",
                    "title_zh": "对话用户模拟器评测基准",
                    "motivation_cn": "缺少统一的用户模拟评测标准。",
                    "method_cn": "设计多场景对话评估协议与指标。",
                    "result_cn": "揭示多款模型在长程一致性上的短板。",
                    "conclusion_cn": "为后续用户模拟研究提供基准。",
                    "matched_query_tag": "query:user-sim",
                },
            ]
            tr.write_json(out_path, data)
        else:
            raise AssertionError(f"Unexpected script: {script_name}")

    class FakeGuideClient:
        def chat_structured(self, messages, *args, **kwargs):
            payload = json.loads(messages[1]["content"])
            ids = [p["canonical_id"] for p in payload["papers"]]
            return {
                "parsed": {
                    "overview": {
                        "text": "本方向聚焦大模型用户模拟与评测。",
                        "paper_ids": ids,
                    },
                    "sections": [
                        {
                            "title": "核心方法与评测",
                            "text": "涵盖模拟器构建与基准测试。",
                            "paper_ids": ids,
                        }
                    ],
                    "reading_order": [
                        {"paper_id": ids[0], "reason": "核心框架", "level": "入门"},
                        {"paper_id": ids[1], "reason": "评测基准", "level": "进阶"},
                    ],
                },
                "parse_error": None,
            }

    generator = tr._load_step_module("6.generate_docs.py", "dpr_generate_docs_for_topic")
    media_calls = []

    def fake_media(paper, *, docs_dir, paper_id, pdf_url):
        media_calls.append((paper_id, pdf_url))
        return ([{"path": "assets/figures/demo/fig1.png", "caption": "Fig 1"}], [])

    def fake_ensure_text(pdf_url, txt_path):
        Path(txt_path).parent.mkdir(parents=True, exist_ok=True)
        Path(txt_path).write_text("Full text " + ("content " * 300), encoding="utf-8")
        return "Full text"

    with patch.object(
        tr,
        "run_retrieval",
        return_value={
            "papers": [arxiv_paper, conf_paper],
            "tasks": [],
            "coverage": {"missing_inventory": []},
        },
    ), patch.object(
        tr, "verify_publications", side_effect=lambda papers, root, resolve_pdfs=True: copy.deepcopy(papers)
    ), patch.object(
        generator, "ensure_text_content", side_effect=fake_ensure_text
    ), patch.object(
        generator, "maybe_generate_paper_media", side_effect=fake_media
    ), patch.object(
        generator, "translate_title_and_abstract_to_zh", return_value=("对话用户模拟器评测基准", "这是中文摘要。")
    ), patch.object(
        generator, "generate_deep_summary", return_value="### 核心贡献\n精读长总结。（完）"
    ), patch.object(
        generator, "generate_glance_overview", side_effect=AssertionError("复用 Step 4 速览字段时不该重复调 glance LLM")
    ), patch.dict(
        os.environ, {"SUMMARY_API_KEY": "test-summary-key", "DEEPSEEK_API_KEY": "test-key"}
    ):
        manifest = tr.run_research(
            config,
            "user-sim",
            "starter",
            "2026-11-25",
            tmp_path,
            conferences=["iclr"],
            max_papers=50,
            publish=True,
            step_runner=fake_step_runner,
            guide_client_factory=FakeGuideClient,
        )

    assert config == before_config
    assert [Path(cmd[1]).name for _, cmd in executed_steps] == ["3.rank_papers.py", "4.llm_refine_papers.py"]
    assert manifest["status"] == "complete"
    assert manifest["deep_count"] == 1
    assert manifest["quick_count"] == 1
    token = manifest["topic_token"]
    assert token == "20251125-20261124-starter-user-sim"

    # 1. 验证完全没有旧的双轨 docs/starter-pack/ 与巨型 task-state.json / reading.json
    assert not (tmp_path / "docs/starter-pack").exists()

    # 2. 验证会议论文通过标准 process_paper 生成，包含图表 figures_json、中文摘要、Step 4 速览
    conf_route = "conference/iclr-2026/iclr-2026-abc-benchmarking-conversational-user-simulators"
    conf_md = (tmp_path / "docs" / f"{conf_route}.md").read_text(encoding="utf-8")
    assert "figures_json:" in conf_md
    assert "## 摘要" in conf_md
    assert "对话用户模拟器评测基准" in conf_md
    assert "设计多场景对话评估协议与指标" in conf_md
    assert any(pid == conf_route for pid, _ in media_calls)

    # 3. 验证已有 arXiv 历史页同版本复用：保留用户笔记并补齐精读长总结
    reused_md = existing_doc.read_text(encoding="utf-8")
    assert "用户手写笔记必须保留" in reused_md
    assert "精读长总结。（完）" in reused_md

    # 4. 验证标准单轨侧边栏 + _daily_state.json + papers.meta.json + 导读 + 清单导出
    sidebar = (tmp_path / "docs/_sidebar.md").read_text(encoding="utf-8")
    assert f"<!--dpr-date:{token}-->" in sidebar
    assert "<!--dpr-topic:" in sidebar
    assert "顶会近 24 个月" in sidebar
    assert "核心研究大模型用户模拟" in sidebar
    assert "提出对话用户模拟评测基准" in sidebar
    assert (tmp_path / f"docs/{token}/_daily_state.json").exists()
    assert (tmp_path / f"docs/{token}/papers.meta.json").exists()
    assert (tmp_path / f"docs/{token}/papers.md").exists()
    assert (tmp_path / f"docs/{token}/papers.json").exists()
    readme = (tmp_path / f"docs/{token}/README.md").read_text(encoding="utf-8")
    assert "data-topic-copy=\"docs/20251125-20261124-starter-user-sim/papers.md\"" in readme
    assert "方向概览" in readme
    assert "建议阅读路线" in readme
    assert "## 完整论文目录" in readme
    assert "# 日报" not in readme
    assert readme.startswith("# user-sim · 入门导读\n")


def test_pdf_failure_isolated_and_still_generates_chinese_quick_page(tmp_path):
    config = _base_config()
    paper = {
        "id": "aaai-2025-33456",
        "title": "Blocked PDF Conference Paper",
        "abstract": "An important paper whose PDF returns HTTP 520.",
        "authors": ["Dan Wu"],
        "source": "AAAI-2025-Accepted",
        "conference": "aaai",
        "conference_year": 2025,
        "conference_acceptance_status": "accepted",
        "publication_date": "2025-04-11",
        "publication_date_precision": "day",
        "publication_window_status": "in_window",
        "link": "https://ojs.aaai.org/index.php/AAAI/article/view/33456",
        "pdf_url": "https://ojs.aaai.org/index.php/AAAI/article/download/33456/35611",
        "retrieval_source": "aaai",
        "retrieval_evidence": [{"lane": "embedding", "query_text": "simulating realistic users with LLMs", "rank": 1}],
    }
    generator = tr._load_step_module("6.generate_docs.py", "dpr_generate_docs_for_topic")

    def fake_step_runner(_label, cmd, _env):
        script_name = Path(cmd[1]).name
        out_path = Path(cmd[cmd.index("--output") + 1])
        in_path = Path(cmd[cmd.index("--input") + 1])
        data = json.loads(in_path.read_text(encoding="utf-8"))
        if script_name == "3.rank_papers.py":
            for q in data["queries"]:
                if q["type"] == "intent_query":
                    q["ranked"] = [{"paper_id": "aaai-2025-33456", "score": 0.9, "star_rating": 5}]
        else:
            data["llm_ranked"] = [
                {
                    "paper_id": "aaai-2025-33456",
                    "score": 8.5,
                    "evidence_cn": "相关论文",
                    "tldr_cn": "中文 TLDR。",
                    "title_zh": "被挡PDF的会议论文",
                    "motivation_cn": "动机。",
                    "method_cn": "方法。",
                    "result_cn": "结果。",
                    "conclusion_cn": "结论。",
                    "matched_query_tag": "query:user-sim",
                }
            ]
        tr.write_json(out_path, data)

    import requests

    with patch.object(
        tr,
        "run_retrieval",
        return_value={"papers": [paper], "tasks": [], "coverage": {"missing_inventory": []}},
    ), patch.object(
        tr, "verify_publications", side_effect=lambda papers, root, resolve_pdfs=True: copy.deepcopy(papers)
    ), patch.object(
        generator, "ensure_text_content", side_effect=requests.HTTPError("520 Server Error")
    ), patch.object(
        generator, "maybe_generate_paper_media", return_value=([], [])
    ), patch.object(
        generator, "translate_title_and_abstract_to_zh", return_value=("被挡PDF的会议论文", "这是中文摘要。")
    ), patch.dict(
        os.environ, {"SUMMARY_API_KEY": "test-summary-key"}
    ):
        manifest = tr.run_research(
            config,
            "user-sim",
            "90",
            "2026-11-25",
            tmp_path,
            publish=True,
            step_runner=fake_step_runner,
        )

    assert manifest["status"] == "complete"
    assert manifest["result"]["failed_count"] == 0
    md_files = list((tmp_path / "docs/conference/aaai-2025").glob("*.md"))
    assert len(md_files) == 1
    content = md_files[0].read_text(encoding="utf-8")
    assert "被挡PDF的会议论文" in content
    assert "## 摘要" in content
    assert "这是中文摘要。" in content
    assert "论文详细总结（自动生成）" not in content


def test_refuses_writing_to_upstream_main_repo():
    plan, _ = tr.research_plan(_base_config(), "user-sim", "90", "2026-11-25")
    with patch.dict(os.environ, {"GITHUB_REPOSITORY": "ziwenhahaha/daily-paper-reader"}):
        with pytest.raises(ValueError, match="主仓库"):
            tr.publish_topic_results(ROOT, plan, [], [], {})


def test_select_topic_papers_deduplicates_case_variant_tags():
    llm_data = {
        "papers": [
            {
                "id": "2603.14334v1",
                "canonical_id": "arxiv:2603.14334",
                "title": "Better approximation guarantee for Asymmetric TSP",
                "abstract": "Abstract",
                "tags": ["query:ATSP", "keyword:atsp"],
            }
        ],
        "queries": [],
        "llm_ranked": [
            {
                "paper_id": "2603.14334v1",
                "score": 9.5,
                "matched_query_tag": "query:atsp",
                "evidence_cn": "证据",
                "tldr_cn": "速览",
                "title_zh": "中文标题",
            }
        ],
    }
    deep, quick = tr.select_topic_papers(
        llm_data,
        {"2603.14334v1": llm_data["papers"][0]},
        profile_tag="ATSP",
        max_papers=50,
    )
    assert len(deep) == 1 and len(quick) == 0
    assert [t.lower() for t in deep[0]["llm_tags"]] == ["query:atsp"]
    assert len(deep[0]["llm_tags"]) == 1


def test_select_topic_papers_orders_conference_before_newest_arxiv_within_same_score():
    papers = [
        {
            "id": "2603.26564v1",
            "canonical_id": "arxiv:2603.26564",
            "title": "Arxiv Old 9",
            "source": "arxiv",
            "publication_date": "2026-03-27",
        },
        {
            "id": "2611.26180v1",
            "canonical_id": "arxiv:2611.26180",
            "title": "Arxiv New 9",
            "source": "arxiv",
            "publication_date": "2026-11-19",
        },
        {
            "id": "neurips-2025-1",
            "canonical_id": "neurips:2025:1",
            "title": "NeurIPS 2025 9",
            "source": "NeurIPS-2025-Accepted",
            "conference": "neurips",
            "conference_year": 2025,
            "publication_date": "2025",
        },
        {
            "id": "2603.14334v1",
            "canonical_id": "arxiv:2603.14334",
            "title": "Arxiv 10",
            "source": "arxiv",
            "publication_date": "2026-03-15",
        },
    ]
    llm_data = {
        "papers": papers,
        "queries": [],
        "llm_ranked": [
            {"paper_id": "2603.26564v1", "score": 9.0, "matched_query_tag": "query:ATSP"},
            {"paper_id": "2611.26180v1", "score": 9.0, "matched_query_tag": "query:ATSP"},
            {"paper_id": "neurips-2025-1", "score": 9.0, "matched_query_tag": "query:ATSP"},
            {"paper_id": "2603.14334v1", "score": 10.0, "matched_query_tag": "query:ATSP"},
        ],
    }
    deep, quick = tr.select_topic_papers(
        llm_data,
        {p["id"]: p for p in papers},
        profile_tag="ATSP",
        max_papers=50,
    )
    assert quick == []
    assert [p["title"] for p in deep] == [
        "NeurIPS 2025 9",
        "Arxiv New 9",
        "Arxiv Old 9",
        "Arxiv 10",
    ]
