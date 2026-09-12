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
    from starter_pack_reading import _qualified_version

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
        qualified = [v for v in versions if _qualified_version(v)]
        if paper.get("bucket") == "notice":
            group = "仅元数据：相关性待确认"
        elif qualified:
            group = "已确认在时间窗口内"
        else:
            group = "公布日期边界待核实"
        # 录用、摘要和窗口资格必须来自同一版本；不借较新的未核实版本置顶。
        date_versions = qualified if group == "已确认在时间窗口内" else versions
        dates = [v for v in date_versions if v.get("publication_date")]
        latest = (
            max(dates, key=lambda p: p["publication_date"])
            if dates
            else date_versions[0]
        )
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
    from starter_pack_guide import _escape

    labels = {"90": "90天", "365": "365天", "starter": "大礼包"}
    statuses = {
        "complete": "已完成",
        "selection_ready": "名单已确定",
        "content_pending": "阅读内容/导读待补充",
        "needs_resume": "待续跑",
        "failed": "失败",
        "selected": "名单已确定",
    }
    lines = [
        "# 专题研究结果",
        "",
        "任务状态与固定名单分开记录；有结果不代表全部阅读内容已生成。",
        "",
    ]
    for pack in packs:
        label = _escape(
            str(pack.get("tag") or "专题")
            + " · "
            + labels.get(str(pack.get("mode") or "starter"), "专题研究")
        )
        count = pack.get("result_count", pack.get("paper_count", 0))
        status = statuses.get(pack.get("status"), "状态待确认")
        snapshot = "；保留上次完整快照" if pack.get("has_complete_snapshot") else ""
        lines.append(
            f'- [{label}](#/starter-pack/{pack["run_id"]}/README) · {status} · {_escape(str(count))} 篇{snapshot}'
        )
    if not packs:
        lines.append("暂无已发布任务结果。")
    (folder / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return packs


def publish_pack(root, manifest, content_limit=100):
    root = Path(root).resolve()
    if root == Path(__file__).resolve().parents[1] and os.getenv(
        "GITHUB_REPOSITORY", ""
    ).lower() in ("", "ziwenhahaha/daily-paper-reader"):
        raise ValueError("主仓库不发布个性化运行数据；请指定独立--root或在Fork运行")
    run_id = manifest["run_id"]
    if not re.fullmatch(r"\d{8}-[a-f0-9]{12}", run_id):
        raise ValueError("非法入门包运行标识")
    if not 1 <= content_limit <= 100:
        raise ValueError("最终名单上限必须是1–100")
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
    if manifest.get("mode") in ("90", "365", "starter"):
        record["mode"] = manifest["mode"]
    selection_path = cached / "selected.json"
    if selection_path.exists() and manifest.get("status") != "failed":
        selection = json.loads(selection_path.read_text(encoding="utf-8"))
        if selection.get("selection_complete") is True:
            return _publish_selection(
                root, manifest, selection["papers"], record, folder, cached
            )
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


def _publish_selection(root, manifest, papers, record, folder, cached):
    from starter_pack_reading import prepare_reading
    from starter_pack_guide import (
        generate_guide,
        validate_guide,
        render_guide,
        guide_cache_key,
    )
    from topic_research_export import export_records, render_export
    from starter_pack_guide import _escape

    # 导出名单固定，不随全文预算、成功数或导读状态缩减。
    papers = sorted(papers, key=lambda p: -float(p.get("score") or 0))
    exports = export_records(papers)
    run_id = manifest["run_id"]
    tag = str(manifest["profile"]["tag"])
    mode = str(manifest.get("mode") or "starter")
    content_batch = int(manifest.get("content_batch", 10))
    task_name = {
        "90": "90天专题研究",
        "365": "365天专题研究",
        "starter": "研究方向大礼包",
    }.get(mode, "专题研究")
    window_parts = []
    for source, label in (("arxiv", "arXiv"), ("conference", "会议")):
        window = (manifest.get("windows") or {}).get(source)
        if window:
            window_parts.append(
                f'{label} [{window.get("start", "未知")}, {window.get("end_exclusive", "未知")})'
            )
    window_label = "；".join(window_parts) + "（UTC，结束日不含）"
    coverage_text = (
        f"任务：{task_name}\n\n固定窗口：{_escape(window_label)}\n\n"
        f'本次候选评审上限 {_escape(manifest.get("review_limit", 300))}，最终名单上限 {_escape(manifest.get("result_limit", 100))}；本轮内容预算 {content_batch}。\n\n'
        "覆盖限制：仅检索配置范围内已有库存与预算内候选；向量/会议Top-k召回并非全库遍历，"
        "不保证找全相关论文。未核实录用、日期边界和缺失库存不能当作已覆盖。\n\n"
    )
    missing = (manifest.get("coverage") or {}).get("missing_inventory") or []
    if missing:
        coverage_text += (
            "缺失库存："
            + "、".join(
                _escape(f'{x.get("conference", "")} {x.get("year", "")}')
                for x in missing
            )
            + "。\n\n"
        )
    export_path = f"docs/starter-pack/{run_id}/papers.md"
    prior_path = folder / "pack.json"
    prior = (
        json.loads(prior_path.read_text(encoding="utf-8"))
        if prior_path.exists()
        else {}
    )
    fixed_scope = prior.get("scope") or {}
    description = str(
        fixed_scope.get("description", manifest["profile"].get("description") or "")
    )
    refinement = str(
        fixed_scope.get(
            "refinement", (manifest.get("snapshot") or {}).get("refinement") or ""
        )
    )
    export_metadata = {
        "description": description,
        "refinement": refinement,
        "window": window_label,
    }
    if description:
        coverage_text += "研究需求：" + _escape(description) + "\n\n"
    if refinement:
        coverage_text += "本次细化：" + _escape(refinement) + "\n\n"
    keep_snapshot = (
        prior.get("status") == "complete" or prior.get("has_complete_snapshot") is True
    ) and (folder / "README.md").exists()
    snapshot = {
        name: (folder / name).read_bytes()
        for name in (
            "README.md",
            "papers.md",
            "papers.json",
            "guide.json",
            "reading.json",
            "catalog.md",
            "dates.md",
        )
        if keep_snapshot and (folder / name).exists()
    }
    if not keep_snapshot:
        (folder / "papers.md").write_text(
            render_export(exports, tag, export_metadata), encoding="utf-8"
        )
        write_json(folder / "papers.json", exports)
    record.update(
        mode=mode,
        status="selection_ready",
        result_count=len(papers),
        paper_count=len(papers),
        content_done=0,
        content_pending=len(papers),
        guide_status="pending" if mode == "starter" else "not_required",
        export_path=export_path,
        selected_records=[],
        windows=manifest.get("windows", {}),
        review_limit=manifest.get("review_limit", 300),
        result_limit=manifest.get("result_limit", 100),
        coverage=manifest.get("coverage", {}),
        scope={
            "description": description,
            "refinement": refinement,
            "as_of": record["as_of"],
            "mode": mode,
            "windows": manifest.get("windows", {}),
            "review_limit": manifest.get("review_limit", 300),
            "result_limit": manifest.get("result_limit", 100),
        },
    )
    if mode == "starter":
        model = os.getenv("DEEPSEEK_MODEL") or "deepseek-v4-flash"
        endpoint = os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"
        key = guide_cache_key(manifest["profile"], papers, model, endpoint)
        record["guide_cache_key"] = key
        manifest["guide_cache_key"] = key
    if keep_snapshot:
        record.update(
            has_complete_snapshot=True,
            paper_count=prior.get("paper_count", 0),
            complete_snapshot_updated_at=prior.get("complete_snapshot_updated_at")
            or prior.get("updated_at"),
        )
    # 在任何模型调用之前落地清单与索引，失败时仍有可读的最终名单。
    actions = (
        f'<div class="dpr-topic-result-actions"><button type="button" data-topic-copy="{export_path}">复制论文清单</button> '
        f'<a href="{export_path}" download data-no-router>下载 Markdown</a> '
        f'<a href="docs/starter-pack/{run_id}/papers.json" download data-no-router>下载 JSON</a> '
        f'<button type="button" data-topic-continue="{run_id}">继续生成阅读内容</button></div>\n\n'
    )
    text = actions + coverage_text + render_export(exports, tag)
    if not keep_snapshot:
        (folder / "README.md").write_text(text, encoding="utf-8")
    write_json(folder / "pack.json", record)
    rebuild_pack_index(root)
    try:
        prepared = prepare_reading(
            papers,
            root,
            tag,
            run_id,
            manifest["windows"]["arxiv"]["start"],
            record["as_of"],
            content_limit=100,
            max_new_content=content_batch,
        )
    except Exception as exc:
        prepared = []
        record["content_error_type"] = type(exc).__name__
        # 基础页已在昂贵阶段前落地；只做零预算本地恢复，不重试模型或PDF。
        try:
            prepared = prepare_reading(
                papers,
                root,
                tag,
                run_id,
                manifest["windows"]["arxiv"]["start"],
                record["as_of"],
                content_limit=100,
                max_new_content=0,
            )
        except Exception as recovery_exc:
            record["content_recovery_error_type"] = type(recovery_exc).__name__
    prepared_by_id = {str(p.get("canonical_id") or p["id"]): p for p in prepared}
    records = []
    for paper in papers:
        pid = str(paper.get("canonical_id") or paper["id"])
        p = prepared_by_id.get(pid, paper)
        records.append(
            {
                "id": pid,
                "title": paper.get("title", ""),
                "score": paper.get("score"),
                "route": p.get("route", ""),
                "published": p.get("publication_date", ""),
                "publication_date": p.get("publication_date", ""),
                "publication_date_precision": p.get(
                    "publication_date_precision", "unknown"
                ),
                "publication_date_source": p.get("publication_date_source", ""),
                "publication_date_kind": p.get("publication_date_kind", "unknown"),
                "zh_title": p.get("zh_title", ""),
                "summary": p.get("tldr", ""),
                "tags": p.get("tags", []),
                "reading_status": p.get("reading_status", "pending"),
            }
        )
    done = sum(p["reading_status"] == "complete" for p in records)
    record.update(
        selected_records=records,
        content_done=done,
        content_pending=len(papers) - done,
        status="content_pending" if done < len(papers) else "complete",
    )
    write_json(folder / "reading.json", prepared)
    (folder / "catalog.md").write_text(
        actions + coverage_text + render_export(exports, tag), encoding="utf-8"
    )
    (folder / "dates.md").write_text(
        actions + coverage_text + render_catalog(papers, prepared), encoding="utf-8"
    )
    text += f"\n[按公布时间查看](#/starter-pack/{run_id}/dates)\n\n阅读内容：已完成 {done}，待补充 {len(papers)-done}。\n"
    if record.get("content_error_type"):
        record["status"] = "content_pending"
        text += "\n部分阅读内容生成失败；固定名单及导出保留，可继续生成缺失内容。\n"
        if record.get("content_recovery_error_type"):
            text += "\n基础阅读页导航恢复也未完成，请检查任务日志后续跑；本轮不视为完整成功。\n"
    if mode == "starter":
        # 使用selected.json固定证据，不让后续补齐TLDR改变缓存键。
        path = root / ".local-runs/starter-pack-cache/guides" / (key + ".json")
        try:
            guide = None
            if path.exists():
                guide = validate_guide(
                    json.loads(path.read_text(encoding="utf-8")), papers
                )
            elif (
                prior.get("guide_cache_key") == key
                and prior.get("guide_status") == "complete"
                and (folder / "guide.json").exists()
            ):
                guide = validate_guide(
                    json.loads((folder / "guide.json").read_text(encoding="utf-8")),
                    papers,
                )
                write_json(path, guide)
            elif content_batch > 0:
                from llm import DeepSeekClient

                client = None
                if papers:
                    if not os.getenv("DEEPSEEK_API_KEY"):
                        raise RuntimeError("缺少导读模型凭据")
                    client = DeepSeekClient(
                        os.environ["DEEPSEEK_API_KEY"], model, endpoint
                    )
                    client.kwargs.update(
                        max_tokens=16000, thinking={"type": "disabled"}
                    )
                guide = generate_guide(manifest["profile"], papers, client)
                write_json(path, guide)
            if guide is not None:
                write_json(folder / "guide.json", guide)
                route_papers = [
                    dict(
                        p,
                        route=prepared_by_id.get(
                            str(p.get("canonical_id") or p["id"]), {}
                        ).get("route", p.get("route", "")),
                    )
                    for p in papers
                ]
                text = (
                    actions
                    + render_guide(
                        guide, route_papers, {"topic": tag, "window": window_label}
                    )
                    + "\n"
                    + text[len(actions) :]
                )
                record["guide_status"] = "complete"
            else:
                record["guide_status"] = "pending"
                record["status"] = "content_pending"
                text += "\n本轮内容预算为0，未调用模型生成导读；固定名单已可查看和导出，增加内容预算后可续跑。\n"
        except Exception as exc:
            record["guide_status"] = "failed"
            record["guide_error_type"] = type(exc).__name__
            record["status"] = "content_pending"
            text += "\n导读尚未完成，可续跑重试；上方固定论文名单及导出已可使用。\n"
    if keep_snapshot and record["status"] != "complete":
        (folder / "progress.md").write_text(text, encoding="utf-8")
        for name, content in snapshot.items():
            (folder / name).write_bytes(content)
        old = snapshot["README.md"].decode("utf-8")
        old = re.sub(
            r"\A<!-- starter-pack-refresh:start -->.*?<!-- starter-pack-refresh:end -->\n\n",
            "",
            old,
            count=1,
            flags=re.S,
        )
        text = (
            "<!-- starter-pack-refresh:start -->\n> 本轮内容更新尚未完成，下方为上次完整快照。"
            f"[查看本轮进度](#/starter-pack/{run_id}/progress)\n<!-- starter-pack-refresh:end -->\n\n"
            + old
        )
        record.update(
            has_complete_snapshot=True,
            paper_count=prior.get("paper_count", 0),
            complete_snapshot_updated_at=prior.get("complete_snapshot_updated_at")
            or prior.get("updated_at"),
        )
    elif (folder / "progress.md").exists() and record["status"] == "complete":
        (folder / "progress.md").write_text(
            f"本轮已完成。\n\n[最新结果](#/starter-pack/{run_id}/README)\n",
            encoding="utf-8",
        )
    if record["status"] == "complete":
        record.pop("has_complete_snapshot", None)
        record.pop("complete_snapshot_updated_at", None)
        (folder / "papers.md").write_text(
            render_export(exports, tag, export_metadata), encoding="utf-8"
        )
        write_json(folder / "papers.json", exports)
    (folder / "README.md").write_text(text, encoding="utf-8")
    write_json(folder / "pack.json", record)
    manifest.update(
        status=record["status"],
        guide_status=record["guide_status"],
        content_done=done,
        content_pending=len(papers) - done,
    )
    write_json(cached / "manifest.json", manifest)
    rebuild_pack_index(root)
    return record
