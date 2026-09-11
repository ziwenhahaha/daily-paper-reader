"""发布入门包进度和有来源导读；复用现有docsify与论文阅读路径。"""

from __future__ import annotations
from datetime import datetime, timezone
import gzip
import html
import json
import os
from pathlib import Path
import re

from long_range_review import write_json


def render_catalog(papers, prepared):
    from starter_pack_guide import _date, _escape, _link, _url

    routes = {p.get("canonical_id", p["id"]): p.get("route") for p in prepared}
    groups = {
        "已确认在时间窗口内": [],
        "公布日期边界待核实": [],
        "仅元数据：相关性待确认": [],
    }
    for paper in papers:
        if paper.get("bucket") == "excluded":
            continue
        versions = paper.get("versions") or [paper]
        if paper.get("bucket") == "notice":
            group = "仅元数据：相关性待确认"
        elif any(v.get("publication_window_status") == "included" for v in versions):
            group = "已确认在时间窗口内"
        else:
            group = "公布日期边界待核实"
        dates = [v for v in versions if v.get("publication_date")]
        latest = max(dates, key=lambda p: p["publication_date"]) if dates else paper
        groups[group].append((latest, paper))
    lines = [
        "# 入门包结果 · 公布时间降序",
        "",
        "日期精度为年的记录只能粗排；仅元数据与边界不确定项单独列出，不冒充已确认相关论文。",
        "",
    ]
    for title, rows in groups.items():
        lines += ["## " + title, ""]
        rows.sort(
            key=lambda pair: (
                pair[0].get("publication_date", ""),
                float(pair[1].get("score") or 0),
            ),
            reverse=True,
        )
        for date_info, paper in rows:
            route = routes.get(paper.get("canonical_id", paper["id"]))
            target = (
                _url(route, local=True)
                if route
                else _url(paper.get("pdf_url") or paper.get("link"))
            )
            lines.append(
                "- "
                + _link(paper.get("title") or paper["id"], target)
                + " · "
                + _escape(_date(date_info))
                + " · "
                + _escape(paper.get("bucket"))
                + " · 分数 "
                + str(
                    paper.get("score") if paper.get("score") is not None else "未评审"
                )
            )
        if not rows:
            lines.append("暂无。")
        lines.append("")
    return "\n".join(lines)


def rebuild_pack_index(root):
    folder = Path(root) / "docs/starter-pack"
    packs = []
    for path in folder.glob("*/pack.json"):
        item = json.loads(path.read_text(encoding="utf-8"))
        if re.fullmatch(r"\d{8}-[a-f0-9]{12}", str(item.get("run_id", ""))):
            packs.append(item)
    packs.sort(
        key=lambda p: (p.get("as_of", ""), p.get("updated_at", "")), reverse=True
    )
    write_json(folder / "index.json", {"version": 1, "packs": packs})
    return packs


def publish_pack(root, manifest, content_limit=12):
    root = Path(root).resolve()
    if root == Path(__file__).resolve().parents[1] and os.getenv(
        "GITHUB_REPOSITORY", ""
    ).lower() in ("", "ziwenhahaha/daily-paper-reader"):
        raise ValueError("主仓库不发布个性化运行数据；请指定独立--root或在Fork运行")
    run_id = manifest["run_id"]
    if not re.fullmatch(r"\d{8}-[a-f0-9]{12}", run_id):
        raise ValueError("非法入门包运行标识")
    if not 1 <= content_limit <= 20:
        raise ValueError("精选内容上限必须是1–20")
    cached = root / ".local-runs/starter-pack-cache/runs" / run_id
    folder = root / "docs/starter-pack" / run_id
    folder.mkdir(parents=True, exist_ok=True)
    tag = str(manifest["profile"]["tag"])
    record = {
        "run_id": run_id,
        "tag": tag,
        "status": "needs_resume",
        "paper_count": 0,
        "as_of": manifest["windows"]["arxiv"]["end_exclusive"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    if manifest["status"] not in ("reviewed", "complete"):
        if manifest["status"] == "failed":
            record["status"] = "failed"
        status_label = "失败，待续跑" if record["status"] == "failed" else "待续跑"
        text = (
            f"# {html.escape(tag)} · 入门包进度\n\n"
            f"本轮状态：{status_label}，尚未生成完整导读。\n\n"
            f'- 已召回记录：{manifest.get("retrieved_records",0)}\n'
            f'- 去重后论文：{manifest.get("unique_papers",0)}\n'
            f'- 尚待评审：{manifest.get("remaining","待确认")}\n\n'
            f'请保持同一专题、会议范围和截止日期 {record["as_of"]}，再次运行以续跑。已完成检查点会复用。\n'
        )
        previous_path = folder / "pack.json"
        previous = (
            json.loads(previous_path.read_text(encoding="utf-8"))
            if previous_path.exists()
            else {}
        )
        readme = folder / "README.md"
        if (
            previous.get("run_id") == run_id
            and (
                previous.get("status") == "complete"
                or previous.get("has_complete_snapshot") is True
            )
            and readme.is_file()
        ):
            # 缓存淘汰不等于已发布内容失效：重跑状态与旧完整快照分开记录。
            record.update(
                paper_count=previous.get("paper_count", 0),
                has_complete_snapshot=True,
                complete_snapshot_updated_at=previous.get(
                    "complete_snapshot_updated_at"
                )
                or previous.get("updated_at"),
            )
            for field in ("coverage", "unavailable_count"):
                if field in previous:
                    record[field] = previous[field]
            (folder / "progress.md").write_text(
                text + f"\n[查看上次完整导读](#/starter-pack/{run_id}/README)\n",
                encoding="utf-8",
            )
            old_text = readme.read_text(encoding="utf-8")
            old_text = re.sub(
                r"\A<!-- starter-pack-refresh:start -->.*?<!-- starter-pack-refresh:end -->\n\n",
                "",
                old_text,
                count=1,
                flags=re.S,
            )
            text = (
                "<!-- starter-pack-refresh:start -->\n"
                f"> 本轮更新{status_label}，尚未完成。下方保留上次完整导读及下载，"
                "不是本轮完成结果；论文数量为上次完整快照数量。"
                f"[查看本轮进度](#/starter-pack/{run_id}/progress)。\n"
                "<!-- starter-pack-refresh:end -->\n\n" + old_text
            )
    else:
        from starter_pack_reading import prepare_reading
        from starter_pack_guide import (
            generate_guide,
            validate_guide,
            render_guide,
            guide_cache_key,
        )
        from llm import DeepSeekClient

        reviews = json.loads((cached / "reviewed.json").read_text(encoding="utf-8"))
        prepared = prepare_reading(
            reviews["papers"],
            root,
            tag,
            run_id,
            manifest["windows"]["arxiv"]["start"],
            record["as_of"],
            content_limit,
        )
        selected = [p for p in prepared if p.get("reading_status") == "complete"]
        unavailable = [
            p.get("canonical_id") or p["id"]
            for p in prepared
            if p.get("reading_status") != "complete"
        ]
        model = os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-flash"
        endpoint = os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
        key = guide_cache_key(manifest["profile"], selected, model, endpoint)
        guide_path = root / ".local-runs/starter-pack-cache/guides" / (key + ".json")
        if guide_path.exists():
            guide = validate_guide(
                json.loads(guide_path.read_text(encoding="utf-8")), selected
            )
        else:
            client = None
            if selected:
                if not os.getenv("DEEPSEEK_API_KEY"):
                    raise RuntimeError("缺少导读生成模型凭据")
                client = DeepSeekClient(os.environ["DEEPSEEK_API_KEY"], model, endpoint)
                client.kwargs.update(max_tokens=10000, thinking={"type": "disabled"})
            guide = generate_guide(manifest["profile"], selected, client)
            write_json(guide_path, guide)
        windows = manifest["windows"]
        window = (
            f'arXiv {windows["arxiv"]["start"]} 至 {windows["arxiv"]["end_exclusive"]}；'
            f'会议 {windows["conference"]["start"]} 至 {windows["conference"]["end_exclusive"]}（结束日均不含）'
        )
        text = render_guide(guide, selected, {"topic": tag, "window": window})
        text += f"\n[查看全部结果（公布时间降序）](#/starter-pack/{run_id}/catalog)\n"
        (folder / "catalog.md").write_text(
            render_catalog(reviews["papers"], prepared), encoding="utf-8"
        )
        counts = {
            bucket: sum(p.get("bucket") == bucket for p in reviews["papers"])
            for bucket in ("core", "related", "review", "notice", "excluded")
        }
        text += (
            "\n## 本次检索范围与限制\n\n"
            f'- 原始召回 {manifest["retrieved_records"]} 条，去重后 {manifest["unique_papers"]} 篇。\n'
            f'- 核心 {counts["core"]}，补充 {counts["related"]}，待复核 {counts["review"]}，仅元数据 {counts["notice"]}。\n'
            f"- 本页精选 {len(selected)} 篇；另有 {len(unavailable)} 篇精选候选全文不可用，未冒充已完成精读。\n"
            "- arXiv关键词按配置分片召回，向量每查询每30天Top100；会议每查询每届每路Top50。不是全部相关论文的证明。\n"
            "- 年份精度跨越边界的论文保留日期待确认标记，不计入本页精选。\n"
            f'- [下载完整合并结果（Gzip JSON）](docs/starter-pack/{run_id}/papers.json.gz ":ignore") / [下载去重待核对项](docs/starter-pack/{run_id}/possible-duplicates.json ":ignore")\n'
        )
        coverage = manifest.get("coverage") or {}
        missing = coverage.get("missing_inventory") or []
        if missing:
            text += (
                "- 尚无库存，未纳入："
                + "、".join(f'{p["conference"]} {p["year"]}' for p in missing)
                + "。\n"
            )
        record["coverage"] = coverage
        merged = json.loads((cached / "merged.json").read_text(encoding="utf-8"))
        # 全量候选含多个原始版本；无损压缩避免宽领域结果突破GitHub单文件限制。
        # 固定mtime，重复发布相同结果时不会产生二进制噪音变更。
        serialized = json.dumps(
            reviews["papers"], ensure_ascii=False, separators=(",", ":")
        )
        (folder / "papers.json.gz").write_bytes(
            gzip.compress(serialized.encode("utf-8"), mtime=0)
        )
        write_json(folder / "possible-duplicates.json", merged["possible_duplicates"])
        write_json(folder / "guide.json", guide)
        write_json(folder / "reading.json", prepared)
        record.update(
            status="complete",
            paper_count=len(selected),
            unavailable_count=len(unavailable),
        )
        manifest.update(
            status="complete",
            guide_papers=len(selected),
            unavailable_reading=unavailable,
        )
        write_json(cached / "manifest.json", manifest)
        if (folder / "progress.md").exists():
            (folder / "progress.md").write_text(
                f"# 入门包进度\n\n本轮已完成。\n\n"
                f"[查看最新完整导读](#/starter-pack/{run_id}/README)\n",
                encoding="utf-8",
            )
    (folder / "README.md").write_text(text, encoding="utf-8")
    write_json(folder / "pack.json", record)
    rebuild_pack_index(root)
    return record
