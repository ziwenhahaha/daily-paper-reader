"""Legacy config field readers for profiles generated before English localization.

Legacy key names are centralized here so the rest of the codebase stays English-only.
"""

from __future__ import annotations

from typing import Any, Mapping

LEGACY_NOTE_KEYS = (
    "note",
    "logic_cn",
    "keyword_cn",
    "query_cn",
    "keyword_zh",
    "query_zh",
    "zh",
)


def read_note(item: Any) -> str:
    if not isinstance(item, Mapping):
        return ""
    for key in LEGACY_NOTE_KEYS:
        value = item.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""
