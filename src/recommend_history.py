from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Set


CARRYOVER_UNTAGGED = "untagged"


def load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"missing file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return payload if isinstance(payload, dict) else {}


def list_date_dirs(archive_root: str) -> List[str]:
    if not os.path.isdir(archive_root):
        return []
    result: List[str] = []
    for name in os.listdir(archive_root):
        if re.match(r"^\d{8}$", name) or re.match(r"^\d{8}-\d{8}$", name):
            result.append(name)
    return sorted(result)


def normalize_tags(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    cleaned: List[str] = []
    seen: Set[str] = set()
    for item in raw:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


def normalize_recommendation_tag(tag: Any) -> str:
    text = str(tag or "").strip()
    if not text:
        return ""
    if ":" in text:
        prefix, suffix = text.split(":", 1)
        if prefix in {"query", "keyword"} and suffix.strip():
            text = suffix.strip()
    return text


def resolve_recommendation_tags(
    item: Dict[str, Any],
    fallback_tags: List[str] | None = None,
) -> List[str]:
    collected: List[str] = []

    matched_query_tag = normalize_recommendation_tag(item.get("matched_query_tag"))
    if matched_query_tag:
        collected.append(matched_query_tag)

    for raw_tag in normalize_tags(item.get("tags")):
        normalized = normalize_recommendation_tag(raw_tag)
        if normalized:
            collected.append(normalized)

    for raw_tag in normalize_tags(item.get("llm_tags")):
        normalized = normalize_recommendation_tag(raw_tag)
        if normalized:
            collected.append(normalized)

    if not collected and fallback_tags:
        for raw_tag in fallback_tags:
            normalized = normalize_recommendation_tag(raw_tag)
            if normalized:
                collected.append(normalized)

    cleaned: List[str] = []
    seen: Set[str] = set()
    for tag in collected:
        if not tag or tag in seen:
            continue
        seen.add(tag)
        cleaned.append(tag)
    return cleaned or [CARRYOVER_UNTAGGED]


def collect_seen_ids(
    archive_root: str,
    today_str: str,
    active_tags: List[str] | None = None,
) -> Set[str]:
    active_tag_keys = {
        normalize_recommendation_tag(tag).lower()
        for tag in (active_tags or [])
        if normalize_recommendation_tag(tag)
    }

    seen: Set[str] = set()
    for day in list_date_dirs(archive_root):
        if day == today_str:
            continue
        rec_dir = os.path.join(archive_root, day, "recommend")
        if not os.path.isdir(rec_dir):
            continue
        for name in os.listdir(rec_dir):
            if not name.endswith(".json"):
                continue
            if not name.startswith(f"arxiv_papers_{day}."):
                continue
            rec_path = os.path.join(rec_dir, name)
            try:
                payload = load_json(rec_path)
            except Exception:
                continue
            for key in ("deep_dive", "quick_skim"):
                for item in payload.get(key) or []:
                    if not isinstance(item, dict):
                        continue
                    pid = str(item.get("id") or item.get("paper_id") or "").strip()
                    if not pid:
                        continue
                    if active_tag_keys:
                        item_tag_keys = {
                            normalize_recommendation_tag(tag).lower()
                            for tag in resolve_recommendation_tags(item)
                            if normalize_recommendation_tag(tag)
                        }
                        if not item_tag_keys.intersection(active_tag_keys):
                            continue
                    seen.add(pid)
    return seen
