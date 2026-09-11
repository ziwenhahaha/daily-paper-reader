import gzip
import json, sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from starter_pack_publish import publish_pack, render_catalog


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
        "windows": {"arxiv": {"start": "2025-09-11", "end_exclusive": "2026-09-11"}},
        "remaining": 9,
    }
    result = publish_pack(tmp_path, manifest)
    assert result["status"] == "needs_resume" and result["paper_count"] == 0
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
