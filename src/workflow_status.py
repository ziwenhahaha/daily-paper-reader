#!/usr/bin/env python
"""轻量级公共 Supabase 工作流运行状态与步骤进度上报器（失败静默降级，绝不阻塞主流程）。"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
import re
import threading
import time
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests


DEFAULT_PUBLIC_SUPABASE_URL = "https://lyucdwgefyfbmaiopjbk.supabase.co"
DEFAULT_PUBLIC_SUPABASE_KEY = "sb_publishable_lX-oi64Uxyd7SIVv3_w2Uw_MTOojeKq"
TABLE_NAME = "workflow_run_status"
VALID_STATUSES = {"queued", "in_progress", "completed"}
VALID_CONCLUSIONS = {"", "success", "failure", "cancelled", "skipped"}
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MIN_PROGRESS_INTERVAL_SECONDS = 2.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clip(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 1)].rstrip() + "…"


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        n = int(value)
        return max(n, 0)
    except (TypeError, ValueError):
        return default


def normalize_conclusion(raw_status: str) -> str:
    val = str(raw_status or "").strip().lower()
    if val in {"success", "succeeded", "ok"}:
        return "success"
    if val in {"failure", "failed", "error", "timed_out"}:
        return "failure"
    if val in {"cancelled", "canceled"}:
        return "cancelled"
    if val in {"skipped"}:
        return "skipped"
    return ""


def _resolve_supabase_credentials() -> tuple[str, str]:
    url = (
        str(os.getenv("DPR_WORKFLOW_STATUS_SUPABASE_URL") or "").strip()
        or DEFAULT_PUBLIC_SUPABASE_URL
    ).rstrip("/")
    key = (
        str(os.getenv("DPR_WORKFLOW_STATUS_SUPABASE_KEY") or "").strip()
        or DEFAULT_PUBLIC_SUPABASE_KEY
    )
    return url, key


def _is_disabled() -> bool:
    return str(os.getenv("DPR_WORKFLOW_STATUS_DISABLE") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class WorkflowStatusReporter:
    """线程安全的工作流进度上报器；仅在 GitHub Actions 运行态激活，异常全部吞掉。"""

    def __init__(
        self,
        *,
        workflow_key: str = "",
        workflow_file: str = "",
        display_label: str = "",
        repo_full_name: str = "",
        run_id: Optional[int] = None,
        run_number: Optional[int] = None,
        supabase_url: str = "",
        supabase_key: str = "",
        timeout: float = 5.0,
    ) -> None:
        self.workflow_key = _clip(workflow_key or os.getenv("DPR_WORKFLOW_KEY") or "", 64)
        self.workflow_file = _clip(workflow_file or os.getenv("DPR_WORKFLOW_FILE") or "", 100)
        self.display_label = _clip(display_label or os.getenv("DPR_WORKFLOW_LABEL") or "", 160)
        self.repo_full_name = str(
            repo_full_name or os.getenv("GITHUB_REPOSITORY") or ""
        ).strip()
        raw_run_id = run_id if run_id is not None else os.getenv("GITHUB_RUN_ID")
        try:
            self.run_id: Optional[int] = int(raw_run_id) if raw_run_id not in (None, "") else None
        except (TypeError, ValueError):
            self.run_id = None
        raw_run_number = run_number if run_number is not None else os.getenv("GITHUB_RUN_NUMBER")
        try:
            self.run_number: Optional[int] = (
                int(raw_run_number) if raw_run_number not in (None, "") else None
            )
        except (TypeError, ValueError):
            self.run_number = None

        default_url, default_key = _resolve_supabase_credentials()
        self.supabase_url = (supabase_url or default_url).rstrip("/")
        self.supabase_key = supabase_key or default_key
        self.timeout = float(timeout)
        self.started_at = _now_iso()
        self._lock = threading.Lock()
        self._last_sent_at = 0.0
        self._last_step_code = ""
        self._pending_cleaned = False

    def is_enabled(self) -> bool:
        if _is_disabled():
            return False
        if not self.supabase_url or not self.supabase_key:
            return False
        if not self.repo_full_name or not REPO_RE.fullmatch(self.repo_full_name):
            return False
        if self.run_id is None or self.run_id <= 0:
            return False
        return True

    @property
    def run_key(self) -> str:
        return f"gh:{self.run_id}" if self.run_id else ""

    @property
    def run_url(self) -> str:
        if not self.repo_full_name or not self.run_id:
            return ""
        return f"https://github.com/{self.repo_full_name}/actions/runs/{self.run_id}"

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        if extra:
            headers.update(extra)
        return headers

    def _cleanup_pending_rows(self) -> None:
        if self._pending_cleaned or not self.workflow_file:
            return
        self._pending_cleaned = True
        try:
            endpoint = (
                f"{self.supabase_url}/rest/v1/{TABLE_NAME}"
                f"?repo_full_name=eq.{quote(self.repo_full_name, safe='')}"
                f"&workflow_file=eq.{quote(self.workflow_file, safe='')}"
                f"&run_key=like.{quote('pending:*', safe='*')}"
            )
            requests.delete(
                endpoint,
                headers=self._headers({"Prefer": "return=minimal"}),
                timeout=self.timeout,
            )
        except Exception:
            pass

    def report(
        self,
        *,
        status: str = "in_progress",
        conclusion: str = "",
        step_code: str = "",
        step_label: str = "",
        progress_current: int = 0,
        progress_total: int = 0,
        detail: str = "",
        display_label: str = "",
        force: bool = False,
    ) -> bool:
        if not self.is_enabled():
            return False

        safe_status = status if status in VALID_STATUSES else "in_progress"
        safe_conclusion = conclusion if conclusion in VALID_CONCLUSIONS else normalize_conclusion(conclusion)
        safe_step_code = _clip(step_code, 64)
        safe_step_label = _clip(step_label, 120)
        cur = _safe_int(progress_current)
        tot = _safe_int(progress_total)
        now_mono = time.monotonic()

        with self._lock:
            if display_label:
                self.display_label = _clip(display_label, 160)
            step_changed = safe_step_code != self._last_step_code
            terminal = safe_status == "completed" or (tot > 0 and cur >= tot)
            if (
                not force
                and not step_changed
                and not terminal
                and (now_mono - self._last_sent_at) < MIN_PROGRESS_INTERVAL_SECONDS
            ):
                return False
            self._last_sent_at = now_mono
            self._last_step_code = safe_step_code
            label_to_send = self.display_label

        now_iso = _now_iso()
        payload: Dict[str, Any] = {
            "repo_full_name": self.repo_full_name,
            "run_key": self.run_key,
            "workflow_key": self.workflow_key,
            "workflow_file": self.workflow_file,
            "display_label": label_to_send,
            "run_id": self.run_id,
            "run_number": self.run_number,
            "run_url": self.run_url,
            "status": safe_status,
            "conclusion": safe_conclusion,
            "step_code": safe_step_code,
            "step_label": safe_step_label,
            "progress_current": cur,
            "progress_total": tot,
            "detail": _clip(detail, 240),
            "updated_at": now_iso,
        }
        if safe_status == "completed":
            payload["completed_at"] = now_iso

        try:
            self._cleanup_pending_rows()
            endpoint = f"{self.supabase_url}/rest/v1/{TABLE_NAME}?on_conflict=repo_full_name,run_key"
            resp = requests.post(
                endpoint,
                headers=self._headers(),
                json=payload,
                timeout=self.timeout,
            )
            return 200 <= resp.status_code < 300
        except Exception:
            return False


def reporter_from_env(
    *,
    workflow_key: str = "",
    workflow_file: str = "",
    display_label: str = "",
) -> WorkflowStatusReporter:
    return WorkflowStatusReporter(
        workflow_key=workflow_key,
        workflow_file=workflow_file,
        display_label=display_label,
    )


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="上报当前 GitHub Actions 工作流状态到公共 Supabase。")
    parser.add_argument("--workflow-key", default="")
    parser.add_argument("--workflow-file", default="")
    parser.add_argument("--label", default="")
    parser.add_argument("--status", default="in_progress", choices=sorted(VALID_STATUSES))
    parser.add_argument("--conclusion", default="")
    parser.add_argument("--step-code", default="")
    parser.add_argument("--step-label", default="")
    parser.add_argument("--current", type=int, default=0)
    parser.add_argument("--total", type=int, default=0)
    parser.add_argument("--detail", default="")
    args = parser.parse_args(argv)

    reporter = WorkflowStatusReporter(
        workflow_key=args.workflow_key,
        workflow_file=args.workflow_file,
        display_label=args.label,
    )
    if not reporter.is_enabled():
        return 0
    reporter.report(
        status=args.status,
        conclusion=normalize_conclusion(args.conclusion),
        step_code=args.step_code,
        step_label=args.step_label,
        progress_current=args.current,
        progress_total=args.total,
        detail=args.detail,
        force=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
