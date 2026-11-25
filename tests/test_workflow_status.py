from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import workflow_status as ws


def test_reporter_disabled_without_github_actions_env(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("GITHUB_RUN_ID", raising=False)
    monkeypatch.delenv("DPR_WORKFLOW_STATUS_DISABLE", raising=False)
    called = []
    monkeypatch.setattr(ws.requests, "post", lambda *a, **k: called.append((a, k)))

    reporter = ws.WorkflowStatusReporter(
        workflow_key="topic-research",
        workflow_file="topic-research.yml",
        display_label="专题研究 · llm",
    )
    assert reporter.is_enabled() is False
    assert reporter.report(step_code="step2", step_label="召回中") is False
    assert called == []


def test_reporter_respects_explicit_disable_env(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "alice/daily-paper-reader")
    monkeypatch.setenv("GITHUB_RUN_ID", "123456")
    monkeypatch.setenv("DPR_WORKFLOW_STATUS_DISABLE", "true")

    reporter = ws.WorkflowStatusReporter(workflow_file="topic-research.yml")
    assert reporter.is_enabled() is False


def test_reporter_rejects_invalid_repo_name(monkeypatch):
    monkeypatch.delenv("DPR_WORKFLOW_STATUS_DISABLE", raising=False)
    reporter = ws.WorkflowStatusReporter(
        repo_full_name="not a valid repo",
        run_id=42,
        workflow_file="daily-paper-reader.yml",
    )
    assert reporter.is_enabled() is False


def test_reporter_upserts_and_cleans_pending_once(monkeypatch):
    monkeypatch.delenv("DPR_WORKFLOW_STATUS_DISABLE", raising=False)
    posts = []
    deletes = []

    def fake_delete(url, headers=None, timeout=None):
        deletes.append((url, headers))
        return SimpleNamespace(status_code=204)

    def fake_post(url, headers=None, json=None, timeout=None):
        posts.append((url, headers, json))
        return SimpleNamespace(status_code=201)

    monkeypatch.setattr(ws.requests, "delete", fake_delete)
    monkeypatch.setattr(ws.requests, "post", fake_post)

    clock = {"now": 100.0}
    monkeypatch.setattr(ws.time, "monotonic", lambda: clock["now"])

    reporter = ws.WorkflowStatusReporter(
        workflow_key="topic-research",
        workflow_file="topic-research.yml",
        display_label="专题研究 · user-sim（大礼包）",
        repo_full_name="alice/daily-paper-reader",
        run_id=987654,
        run_number=12,
        supabase_url="https://example.supabase.co",
        supabase_key="test-key",
    )
    assert reporter.is_enabled() is True
    assert reporter.run_key == "gh:987654"
    assert reporter.run_url == "https://github.com/alice/daily-paper-reader/actions/runs/987654"

    ok1 = reporter.report(
        step_code="step6",
        step_label="正在生成论文文档",
        progress_current=1,
        progress_total=10,
    )
    assert ok1 is True
    assert len(deletes) == 1
    assert "repo_full_name=eq.alice%2Fdaily-paper-reader" in deletes[0][0]
    assert "workflow_file=eq.topic-research.yml" in deletes[0][0]
    assert "run_key=like.pending%3A*" in deletes[0][0]

    assert len(posts) == 1
    post_url, post_headers, payload = posts[0]
    assert post_url == "https://example.supabase.co/rest/v1/workflow_run_status?on_conflict=repo_full_name,run_key"
    assert post_headers["apikey"] == "test-key"
    assert payload["run_key"] == "gh:987654"
    assert payload["status"] == "in_progress"
    assert payload["progress_current"] == 1
    assert payload["progress_total"] == 10
    assert "completed_at" not in payload

    # Within 2s throttle window for same step -> skipped
    clock["now"] = 100.5
    assert reporter.report(
        step_code="step6",
        step_label="正在生成论文文档",
        progress_current=2,
        progress_total=10,
    ) is False
    assert len(posts) == 1

    # Terminal progress (10/10) bypasses throttle
    clock["now"] = 100.8
    assert reporter.report(
        step_code="step6",
        step_label="正在生成论文文档",
        progress_current=10,
        progress_total=10,
    ) is True
    assert len(posts) == 2
    # Pending cleanup only runs once
    assert len(deletes) == 1

    # Step change also bypasses throttle
    clock["now"] = 100.9
    assert reporter.report(
        step_code="guide",
        step_label="生成方向导读与清单",
    ) is True
    assert len(posts) == 3

    # Completed status sets completed_at and normalizes conclusion
    clock["now"] = 101.0
    assert reporter.report(
        status="completed",
        conclusion="succeeded",
        step_code="done",
        step_label="已完成",
    ) is True
    assert len(posts) == 4
    assert posts[-1][2]["status"] == "completed"
    assert posts[-1][2]["conclusion"] == "success"
    assert posts[-1][2]["completed_at"]


def test_reporter_fails_silently_on_network_errors(monkeypatch):
    monkeypatch.delenv("DPR_WORKFLOW_STATUS_DISABLE", raising=False)
    monkeypatch.setattr(
        ws.requests,
        "delete",
        lambda *a, **k: (_ for _ in ()).throw(requests.Timeout("delete timeout")),
    )
    monkeypatch.setattr(
        ws.requests,
        "post",
        lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError("post offline")),
    )

    reporter = ws.WorkflowStatusReporter(
        workflow_file="daily-paper-reader.yml",
        repo_full_name="alice/daily-paper-reader",
        run_id=555,
    )
    assert reporter.report(step_code="step2", step_label="召回中", force=True) is False


def test_cli_main_reports_final_status_and_exits_zero(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "alice/daily-paper-reader")
    monkeypatch.setenv("GITHUB_RUN_ID", "777888")
    monkeypatch.setenv("GITHUB_RUN_NUMBER", "9")
    monkeypatch.delenv("DPR_WORKFLOW_STATUS_DISABLE", raising=False)

    sent = []
    monkeypatch.setattr(ws.requests, "delete", lambda *a, **k: SimpleNamespace(status_code=204))
    monkeypatch.setattr(
        ws.requests,
        "post",
        lambda url, headers=None, json=None, timeout=None: sent.append(json) or SimpleNamespace(status_code=201),
    )

    rc = ws.main([
        "--workflow-key", "topic-research",
        "--workflow-file", "topic-research.yml",
        "--label", "专题研究 · agents（大礼包）",
        "--status", "completed",
        "--conclusion", "failure",
        "--step-code", "done",
        "--step-label", "任务失败",
    ])
    assert rc == 0
    assert len(sent) == 1
    assert sent[0]["run_key"] == "gh:777888"
    assert sent[0]["status"] == "completed"
    assert sent[0]["conclusion"] == "failure"
    assert sent[0]["display_label"] == "专题研究 · agents（大礼包）"


def test_workflow_run_status_sql_schema_contract():
    sql = (ROOT / "sql" / "create_workflow_run_status_schema.sql").read_text(encoding="utf-8")
    assert "create table if not exists public.workflow_run_status" in sql
    assert "primary key (repo_full_name, run_key)" in sql
    assert "enable row level security" in sql
    assert "run_url ~ '^https://github\\.com/" in sql
    assert "workflow_run_status_select_recent" in sql
    assert "workflow_run_status_delete_pending" in sql
    assert "using (run_key like 'pending:%')" in sql
