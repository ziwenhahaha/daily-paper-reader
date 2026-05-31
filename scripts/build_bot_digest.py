from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_DIR = REPO_ROOT / "archive"
REPORTS_DIR = REPO_ROOT / "reports"
PAGES_BASE_URL = "https://jjiaqier.github.io/daily-paper-reader/#/"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_latest_recommend_dir() -> Path:
    candidates = [p for p in ARCHIVE_DIR.glob("*/recommend") if p.is_dir()]
    if not candidates:
        raise FileNotFoundError("No recommend directory found under archive/")
    candidates.sort(key=lambda p: p.parent.name)
    return candidates[-1]


def pick_candidate_list(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if isinstance(data, dict):
        for key in ("papers", "items", "results", "recommendations", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [x for x in value if isinstance(x, dict)]

    return []


def find_recommend_items(recommend_dir: Path) -> list[dict[str, Any]]:
    json_files = sorted(recommend_dir.rglob("*.json"))
    if not json_files:
        raise FileNotFoundError(f"No json files found under {recommend_dir}")

    best_items: list[dict[str, Any]] = []

    for path in json_files:
        try:
            data = load_json(path)
        except Exception:
            continue

        items = pick_candidate_list(data)
        if not items:
            continue

        scored_items = [normalize_item(x) for x in items]
        scored_items = [x for x in scored_items if x.get("title")]

        if len(scored_items) > len(best_items):
            best_items = scored_items

    if not best_items:
        raise ValueError(f"Could not parse recommendation items from {recommend_dir}")

    return best_items


def first_non_empty(record: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = record.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def normalize_item(record: dict[str, Any]) -> dict[str, Any]:
    title = first_non_empty(
        record,
        "title",
        "paper_title",
        "name",
    )

    slug = first_non_empty(
        record,
        "slug",
        "paper_slug",
        "id",
        "paper_id",
        "arxiv_id",
    )

    summary = first_non_empty(
        record,
        "summary",
        "summary_zh",
        "ai_summary",
        "reason",
        "recommend_reason",
        "abstract",
    )

    source = first_non_empty(
        record,
        "source",
        "paper_source",
        "origin",
    ) or "unknown"

    url = first_non_empty(
        record,
        "url",
        "paper_url",
        "html_url",
        "abs_url",
        "link",
    )

    return {
        "title": title,
        "slug": slug,
        "summary": summary,
        "source": source,
        "url": url,
    }


def build_entry_url(run_window: str, featured: dict[str, Any]) -> str:
    if featured.get("slug"):
        return f"{PAGES_BASE_URL}{run_window}/{featured['slug']}"
    return PAGES_BASE_URL


def build_markdown(
    *,
    date_str: str,
    run_window: str,
    entry_url: str,
    featured: dict[str, Any],
    quick_reads: list[dict[str, Any]],
) -> str:
    lines: list[str] = []

    lines.append("# 今日论文推荐")
    lines.append("")
    lines.append("阅读入口：")
    lines.append(entry_url)
    lines.append("")
    lines.append("时间窗口：")
    lines.append(run_window)
    lines.append("")
    lines.append("精读文章：")
    lines.append(featured.get("title", "未找到精读文章"))
    lines.append("")
    lines.append("精读文章摘要：")
    lines.append(featured.get("summary", "暂无摘要"))
    lines.append("")

    for idx, item in enumerate(quick_reads, start=1):
        lines.append(f"速读文章{idx}：")
        lines.append(item.get("title", "未命名论文"))
        lines.append(f"一句话摘要：{item.get('summary', '暂无摘要')}")
        lines.append("")

    lines.append("生成日期：")
    lines.append(date_str)
    lines.append("")

    return "\n".join(lines).strip() + "\n"


def main() -> None:
    recommend_dir = find_latest_recommend_dir()
    run_window = recommend_dir.parent.name
    items = find_recommend_items(recommend_dir)

    featured = items[0]
    quick_reads = items[1:4]

    now = datetime.utcnow().strftime("%Y-%m-%d")
    entry_url = build_entry_url(run_window, featured)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    markdown = build_markdown(
        date_str=now,
        run_window=run_window,
        entry_url=entry_url,
        featured=featured,
        quick_reads=quick_reads,
    )

    latest_md = REPORTS_DIR / "bot-digest-latest.md"
    dated_md = REPORTS_DIR / f"bot-digest-{now}.md"

    latest_md.write_text(markdown, encoding="utf-8")
    dated_md.write_text(markdown, encoding="utf-8")

    print(f"Digest written to: {latest_md}")
    print(f"Digest written to: {dated_md}")


if __name__ == "__main__":
    main()
