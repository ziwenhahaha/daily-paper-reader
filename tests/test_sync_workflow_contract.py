from pathlib import Path


SYNC_WORKFLOW = Path(".github/workflows/sync.yml")


def test_sync_workflow_is_manual_only():
    text = SYNC_WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_dispatch:" in text, "sync.yml should still support manual dispatch"
    assert "schedule:" not in text, "sync.yml must not run automatic scheduled sync"
    assert "cron:" not in text, "sync.yml must not define cron triggers"
    assert "github.event_name == 'schedule'" not in text
    assert "shuf -i" not in text, "random delay is only needed for scheduled auto-sync"


def test_sync_workflow_does_not_request_pages_rebuild():
    text = SYNC_WORKFLOW.read_text(encoding="utf-8")

    assert "pages: write" not in text
    assert "Request GitHub Pages rebuild" not in text
    assert "/pages/builds" not in text
