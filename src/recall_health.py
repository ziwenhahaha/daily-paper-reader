"""Distinguish healthy empty recall from an unavailable backend."""

import os
from dataclasses import dataclass
from typing import Callable


# The daily orchestrator treats these two outcomes specially; all other
# nonzero exit codes still abort the run immediately.
RECALL_UNAVAILABLE = 75
RECALL_NOT_RUN = 76
REPORT_RECALL_STATUS = "DPR_REPORT_RECALL_STATUS"


@dataclass
class RecallHealth:
  succeeded: bool = False
  failed: bool = False

  def record_remote(self, result: dict) -> None:
    self.succeeded |= bool(result.get("recall_succeeded"))
    self.failed |= bool(result.get("recall_failed"))

  def finish(self, label: str, log: Callable[[str], None]) -> None:
    if self.failed and not self.succeeded:
      log(f"[ERROR] {label}：所有尝试的 Supabase 召回均失败，且没有可用的本地回退。")
      raise SystemExit(RECALL_UNAVAILABLE)
    if not self.succeeded and os.getenv(REPORT_RECALL_STATUS) == "1":
      raise SystemExit(RECALL_NOT_RUN)
