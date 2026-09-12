import gzip
import json, sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from starter_pack_publish import publish_pack, render_catalog, rebuild_pack_index


def test_results_index_page_links_all_modes_with_safe_titles_and_honest_status(
    tmp_path,
):
    parent = tmp_path / "docs/starter-pack"
    for token, mode, status, count in (
        ("a", "90", "content_pending", 100),
        ("b", "365", "failed", 0),
        ("c", "starter", "complete", 12),
    ):
        run_id = "20260911-" + token * 12
        folder = parent / run_id
        folder.mkdir(parents=True)
        (folder / "pack.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "tag": "<script>bad</script>[x](evil)",
                    "mode": mode,
                    "status": status,
                    "result_count": count,
                }
            )
        )
    records = rebuild_pack_index(tmp_path)
    text = (parent / "README.md").read_text()
    assert (
        len(records) == 3
        and len(json.loads((parent / "index.json").read_text())["packs"]) == 3
    )
    assert "90天" in text and "365天" in text and "大礼包" in text
    assert "失败 · 0 篇" in text and "阅读内容/导读待补充 · 100 篇" in text
    assert "<script>" not in text and "[x](evil)" not in text
    assert text.count("#/starter-pack/") == 3


def test_catalog_date_uses_qualified_arxiv_not_unverified_newer_version():
    text = render_catalog(
        [
            {
                "id": "work",
                "title": "Verified preprint",
                "bucket": "core",
                "score": 9,
                "versions": [
                    {
                        "id": "arxiv1",
                        "abstract": "Evidence",
                        "source": "arxiv",
                        "publication_window_status": "included",
                        "publication_date": "2025-10-01",
                        "publication_date_precision": "day",
                    },
                    {
                        "id": "public1",
                        "abstract": "Evidence",
                        "source": "ICLR-2026-Public",
                        "conference_acceptance_status": "unverified",
                        "publication_window_status": "uncertain",
                        "publication_date": "2026",
                        "publication_date_precision": "year",
                    },
                ],
            }
        ],
        [],
    )
    confirmed = text.split("## 已确认在时间窗口内")[1].split("## 公布日期边界待核实")[0]
    assert "Verified preprint" in confirmed and "2025-10-01" in confirmed
    assert "2026" not in confirmed


def test_catalog_does_not_combine_acceptance_and_window_from_different_versions():
    text = render_catalog(
        [
            {
                "id": "work",
                "title": "Needs verification",
                "bucket": "core",
                "score": 9,
                "versions": [
                    {
                        "id": "public1",
                        "abstract": "Evidence",
                        "source": "ICLR-2025-Public",
                        "conference_acceptance_status": "unverified",
                        "publication_window_status": "included",
                        "publication_date": "2025",
                        "publication_date_precision": "year",
                    },
                    {
                        "id": "accepted1",
                        "abstract": "Evidence",
                        "source": "ICLR",
                        "conference_acceptance_status": "accepted",
                        "publication_window_status": "uncertain",
                        "publication_date": "2024",
                        "publication_date_precision": "year",
                    },
                ],
            }
        ],
        [],
    )
    confirmed = text.split("## 已确认在时间窗口内")[1].split("## 公布日期边界待核实")[0]
    uncertain = text.split("## 公布日期边界待核实")[1].split("## 仅元数据")[0]
    assert "Needs verification" not in confirmed
    assert "Needs verification" in uncertain


def test_refresh_retains_complete_snapshot_until_new_complete_publish(
    tmp_path, monkeypatch
):
    import starter_pack_reading

    monkeypatch.setattr(starter_pack_reading, "prepare_reading", lambda *a: [])
    manifest = {
        "run_id": "20260911-aaaaaaaaaaaa",
        "profile": {"tag": "ATSP"},
        "status": "needs_resume",
        "remaining": 9,
        "windows": {
            "arxiv": {"start": "2025-09-11", "end_exclusive": "2026-09-11"},
            "conference": {"start": "2024-09-11", "end_exclusive": "2026-09-11"},
        },
    }
    output = tmp_path / "docs/starter-pack" / manifest["run_id"]
    output.mkdir(parents=True)
    old_body = "# 旧完整导读\n\n原有正文和[下载](papers.json.gz)\n"
    (output / "README.md").write_text(old_body)
    (output / "pack.json").write_text(
        json.dumps(
            {
                "run_id": manifest["run_id"],
                "status": "complete",
                "paper_count": 12,
                "updated_at": "2026-09-11T00:00:00Z",
            }
        )
    )
    (output / "guide.json").write_text('{"old":true}')
    (output / "papers.json.gz").write_bytes(b"old download")
    for status in ("needs_resume", "needs_resume", "failed"):
        manifest["status"] = status
        result = publish_pack(tmp_path, manifest)
        assert result["status"] == status
        assert result["paper_count"] == 12
        assert result["has_complete_snapshot"] is True
        text = (output / "README.md").read_text()
        assert old_body in text
        assert text.count("<!-- starter-pack-refresh:start -->") == 1
        assert f'#/starter-pack/{manifest["run_id"]}/progress' in text
        assert (output / "guide.json").read_text() == '{"old":true}'
        assert (output / "papers.json.gz").read_bytes() == b"old download"
        progress = (output / "progress.md").read_text()
        assert "本轮" in progress and "9" in progress
        if status == "failed":
            assert "失败" in progress and "失败" in text
        index = json.loads((output.parent / "index.json").read_text())
        assert index["packs"][0]["status"] == status
    cached = tmp_path / ".local-runs/starter-pack-cache/runs" / manifest["run_id"]
    cached.mkdir(parents=True)
    (cached / "reviewed.json").write_text(json.dumps({"papers": []}))
    (cached / "merged.json").write_text(json.dumps({"possible_duplicates": []}))
    manifest.update(status="reviewed", retrieved_records=0, unique_papers=0)
    result = publish_pack(tmp_path, manifest)
    assert result["status"] == "complete" and result["paper_count"] == 0
    assert not result.get("has_complete_snapshot")
    assert "starter-pack-refresh:start" not in (output / "README.md").read_text()
    assert "本轮已完成" in (output / "progress.md").read_text()


def test_incomplete_review_publishes_only_honest_progress(tmp_path):
    manifest = {
        "run_id": "20260911-aaaaaaaaaaaa",
        "profile": {"tag": "ATSP"},
        "status": "needs_resume",
        "mode": "90",
        "windows": {"arxiv": {"start": "2025-09-11", "end_exclusive": "2026-09-11"}},
        "remaining": 9,
    }
    result = publish_pack(tmp_path, manifest)
    assert result["status"] == "needs_resume" and result["paper_count"] == 0
    assert result["mode"] == "90"
    text = (tmp_path / "docs/starter-pack/20260911-aaaaaaaaaaaa/README.md").read_text()
    assert "尚未生成完整导读" in text and "9" in text
    index = json.loads((tmp_path / "docs/starter-pack/index.json").read_text())
    assert len(index["packs"]) == 1


def test_first_failed_run_is_not_a_complete_snapshot(tmp_path):
    manifest = {
        "run_id": "20260911-bbbbbbbbbbbb",
        "profile": {"tag": "RL"},
        "status": "failed",
        "windows": {"arxiv": {"end_exclusive": "2026-09-11"}},
    }
    result = publish_pack(tmp_path, manifest)
    assert result["status"] == "failed" and result["paper_count"] == 0
    assert not result.get("has_complete_snapshot")
    output = tmp_path / "docs/starter-pack" / manifest["run_id"]
    assert "失败" in (output / "README.md").read_text()
    assert not (output / "guide.json").exists()


def test_fixed_100_selection_exports_before_content_and_never_generates_90_day_guide(
    tmp_path, monkeypatch
):
    import starter_pack_reading
    import starter_pack_guide

    papers = [
        {
            "id": str(i),
            "title": f"Original paper {i}",
            "abstract": "Research evidence",
            "score": 10 - i / 100,
            "source": "arxiv",
            "bucket": "core",
            "publication_window_status": "included",
            "publication_date": "2026-01-01",
            "publication_date_precision": "day",
            "link": f"https://arxiv.org/abs/2601.{i:05d}",
        }
        for i in range(100)
    ]
    run_id = "20260911-cccccccccccc"
    folder = tmp_path / ".local-runs/starter-pack-cache/runs" / run_id
    folder.mkdir(parents=True)
    (folder / "selected.json").write_text(
        json.dumps({"papers": papers, "selection_complete": True})
    )
    output = tmp_path / "docs/starter-pack" / run_id
    calls = []

    def prepare(rows, *args, **kwargs):
        assert len(json.loads((output / "papers.json").read_text())) == 100
        calls.append(kwargs)
        return [
            dict(
                p,
                route=f"topic/{p['id']}.md",
                reading_status="complete" if i < 10 else "pending",
            )
            for i, p in enumerate(rows)
        ]

    monkeypatch.setattr(starter_pack_reading, "prepare_reading", prepare)
    generate = Mock(side_effect=AssertionError("90天不得生成入门导读"))
    monkeypatch.setattr(starter_pack_guide, "generate_guide", generate)
    manifest = {
        "run_id": run_id,
        "profile": {"tag": "RL"},
        "mode": "90",
        "status": "selected",
        "content_batch": 10,
        "windows": {"arxiv": {"start": "2026-06-13", "end_exclusive": "2026-09-11"}},
    }
    result = publish_pack(tmp_path, manifest, content_limit=100)
    assert result["result_count"] == 100 and result["content_done"] == 10
    assert result["content_pending"] == 90 and result["status"] == "content_pending"
    assert len(result["selected_records"]) == 100
    assert result["selected_records"][0]["publication_date_precision"] == "day"
    assert result["scope"]["mode"] == "90"
    assert result["scope"]["as_of"] == "2026-09-11"
    assert calls == [{"content_limit": 100, "max_new_content": 10}]
    assert "Original paper 99" in (output / "papers.md").read_text()
    for name in ("catalog.md", "dates.md"):
        text = (output / name).read_text()
        assert text.count("data-topic-copy=") == 1
        assert text.count("Original paper 99") == 1
        assert "90天专题研究" in text and "2026-06-13" in text
    generate.assert_not_called()


def test_complete_empty_selection_never_calls_model(tmp_path, monkeypatch):
    import starter_pack_reading

    monkeypatch.setattr(starter_pack_reading, "prepare_reading", lambda *a: [])
    manifest = {
        "run_id": "20260911-aaaaaaaaaaaa",
        "profile": {"tag": "ATSP"},
        "status": "reviewed",
        "windows": {
            "arxiv": {"start": "2025-09-11", "end_exclusive": "2026-09-11"},
            "conference": {"start": "2024-09-11", "end_exclusive": "2026-09-11"},
        },
        "retrieved_records": 0,
        "unique_papers": 0,
    }
    folder = tmp_path / ".local-runs/starter-pack-cache/runs" / manifest["run_id"]
    folder.mkdir(parents=True)
    (folder / "reviewed.json").write_text(json.dumps({"papers": []}))
    (folder / "merged.json").write_text(json.dumps({"possible_duplicates": []}))
    assert publish_pack(tmp_path, manifest)["status"] == "complete"
    assert (tmp_path / "docs/starter-pack" / manifest["run_id"] / "guide.json").exists()
    output = tmp_path / "docs/starter-pack" / manifest["run_id"]
    archive = output / "papers.json.gz"
    assert json.loads(gzip.decompress(archive.read_bytes())) == []
    assert not (output / "papers.json").exists()
    assert "papers.json.gz" in (output / "README.md").read_text()
    before = archive.read_bytes()
    publish_pack(tmp_path, manifest)
    assert archive.read_bytes() == before


def test_fixed_selection_guide_cache_and_complete_snapshot_survive_pending_refresh(
    tmp_path, monkeypatch
):
    import starter_pack_reading
    import starter_pack_guide
    import llm

    paper = {
        "id": "p1",
        "title": "Original title",
        "abstract": "Fixed evidence",
        "score": 9,
        "bucket": "core",
        "source": "arxiv",
        "publication_window_status": "included",
        "publication_date": "2026-01-01",
        "publication_date_precision": "day",
        "link": "https://arxiv.org/abs/2601.00001",
    }
    run_id = "20260911-dddddddddddd"
    cached = tmp_path / ".local-runs/starter-pack-cache/runs" / run_id
    cached.mkdir(parents=True)
    (cached / "selected.json").write_text(
        json.dumps({"papers": [paper], "selection_complete": True})
    )
    manifest = {
        "run_id": run_id,
        "profile": {"tag": "RL"},
        "mode": "starter",
        "status": "selected",
        "windows": {"arxiv": {"start": "2025-09-11", "end_exclusive": "2026-09-11"}},
    }
    reading_status = ["complete"]

    def prepare(rows, *a, **k):
        return [
            dict(
                rows[0],
                route="original/p1.md",
                reading_status=reading_status[0],
                tldr="Later reading summary " + reading_status[0],
            )
        ]

    monkeypatch.setattr(starter_pack_reading, "prepare_reading", prepare)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-only")
    monkeypatch.setattr(llm, "DeepSeekClient", lambda *a: Mock(kwargs={}))
    generate = Mock(
        return_value={
            "overview": {"text": "研究问题", "paper_ids": ["p1"]},
            "sections": [{"title": "方法", "text": "依据摘要", "paper_ids": ["p1"]}],
            "reading_order": [
                {"paper_id": "p1", "reason": "先读定义", "level": "入门"}
            ],
        }
    )
    monkeypatch.setattr(starter_pack_guide, "generate_guide", generate)
    assert publish_pack(tmp_path, manifest)["status"] == "complete"
    output = tmp_path / "docs/starter-pack" / run_id
    old = (output / "README.md").read_text()
    old_export = (output / "papers.md").read_bytes()
    record = json.loads((output / "pack.json").read_text())
    key = record["guide_cache_key"]
    assert manifest["guide_cache_key"] == key
    guide_cache = tmp_path / ".local-runs/starter-pack-cache/guides" / (key + ".json")
    guide_cache.unlink()
    manifest["content_batch"] = 0
    reading_status[0] = "pending"
    for _ in range(2):
        result = publish_pack(tmp_path, manifest)
        assert (
            result["status"] == "content_pending"
            and result["guide_status"] == "complete"
        )
        assert result["has_complete_snapshot"] is True
        assert old in (output / "README.md").read_text()
        assert (output / "README.md").read_text().count(
            "starter-pack-refresh:start"
        ) == 1
        assert (output / "papers.md").read_bytes() == old_export
    assert generate.call_count == 1
    assert guide_cache.exists()
    assert generate.call_args.args[1][0].get("tldr") is None
    reading_status[0] = "complete"
    assert publish_pack(tmp_path, manifest)["status"] == "complete"
    assert "starter-pack-refresh:start" not in (output / "README.md").read_text()


def test_zero_content_budget_does_not_generate_guide_and_exports_survive_reader_failure(
    tmp_path, monkeypatch
):
    import starter_pack_reading
    import starter_pack_guide

    run_id = "20260911-eeeeeeeeeeee"
    cached = tmp_path / ".local-runs/starter-pack-cache/runs" / run_id
    cached.mkdir(parents=True)
    papers = [
        {
            "id": "p1",
            "title": "Original",
            "abstract": "Evidence",
            "score": 8,
            "bucket": "core",
            "source": "arxiv",
            "publication_window_status": "included",
            "publication_date": "2026-01-01",
            "publication_date_precision": "day",
        }
    ]
    (cached / "selected.json").write_text(
        json.dumps({"papers": papers, "selection_complete": True})
    )
    generate = Mock(side_effect=AssertionError("zero budget must not call model"))
    monkeypatch.setattr(starter_pack_guide, "generate_guide", generate)
    monkeypatch.setattr(
        starter_pack_reading,
        "prepare_reading",
        Mock(side_effect=RuntimeError("read failed")),
    )
    manifest = {
        "run_id": run_id,
        "profile": {"tag": "RL", "description": "研究离线RL"},
        "snapshot": {"refinement": "<script>机器人应用</script>"},
        "mode": "starter",
        "status": "selected",
        "content_batch": 0,
        "review_limit": 300,
        "result_limit": 100,
        "windows": {
            "arxiv": {"start": "2025-09-11", "end_exclusive": "2026-09-11"},
            "conference": {"start": "2024-09-11", "end_exclusive": "2026-09-11"},
        },
    }
    result = publish_pack(tmp_path, manifest)
    assert result["guide_status"] == "pending" and result["status"] == "content_pending"
    assert (
        result["result_count"] == 1 and result["content_error_type"] == "RuntimeError"
    )
    output = tmp_path / "docs/starter-pack" / run_id
    assert len(json.loads((output / "papers.json").read_text())) == 1
    text = (output / "README.md").read_text()
    assert "内容预算为0" in text and "研究方向大礼包" in text
    assert "2024-09-11" in text and "2025-09-11" in text
    assert "300" in text and "100" in text and "不保证找全" in text
    generate.assert_not_called()
    assert result["scope"]["description"] == "研究离线RL"
    assert "研究离线RL" in text and "&lt;script&gt;机器人应用" in text
    export = (output / "papers.md").read_text()
    assert "研究离线RL" in export and "<script>" not in export
    manifest["profile"]["description"] = "不应改变固定需求"
    manifest["snapshot"]["refinement"] = "不应改变细化"
    next_result = publish_pack(tmp_path, manifest)
    assert next_result["scope"]["description"] == "研究离线RL"
    assert next_result["scope"]["refinement"] == "<script>机器人应用</script>"
    assert (output / "papers.md").read_text() == export


def test_content_failure_restores_all_base_routes_with_zero_budget_only(
    tmp_path, monkeypatch
):
    import starter_pack_reading

    run_id = "20260911-ffffffffffff"
    cached = tmp_path / ".local-runs/starter-pack-cache/runs" / run_id
    cached.mkdir(parents=True)
    papers = [
        {
            "id": str(i),
            "title": f"Paper {i}",
            "abstract": "Evidence",
            "score": 9,
            "bucket": "core",
            "source": "arxiv",
            "publication_window_status": "included",
        }
        for i in range(100)
    ]
    (cached / "selected.json").write_text(
        json.dumps({"papers": papers, "selection_complete": True})
    )
    calls = []

    def prepare(rows, *a, **kw):
        calls.append(kw["max_new_content"])
        if len(calls) == 1:
            raise RuntimeError("reading stage failed after base pages")
        assert kw["max_new_content"] == 0
        return [
            dict(p, route=f"topic/{p['id']}.md", reading_status="pending") for p in rows
        ]

    monkeypatch.setattr(starter_pack_reading, "prepare_reading", prepare)
    manifest = {
        "run_id": run_id,
        "profile": {"tag": "RL"},
        "mode": "365",
        "status": "selected",
        "content_batch": 10,
        "windows": {"arxiv": {"start": "2025-09-11", "end_exclusive": "2026-09-11"}},
    }
    result = publish_pack(tmp_path, manifest)
    assert calls == [10, 0]
    assert result["content_error_type"] == "RuntimeError"
    assert result["content_pending"] == 100 and result["status"] == "content_pending"
    assert len(result["selected_records"]) == 100
    assert all(p["route"] for p in result["selected_records"])
    output = tmp_path / "docs/starter-pack" / run_id
    assert len(json.loads((output / "papers.json").read_text())) == 100
    assert "部分阅读内容生成失败" in (output / "README.md").read_text()
