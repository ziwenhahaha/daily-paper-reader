#!/usr/bin/env python
# Step 5：基于 LLM 评分结果，生成“精读区 + 速览区”的三种模式输出。

import argparse
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")
ARCHIVE_DIR = os.path.join(ROOT_DIR, "archive", TODAY_STR)
RANKED_DIR = os.path.join(ARCHIVE_DIR, "rank")
RECOMMEND_DIR = os.path.join(ARCHIVE_DIR, "recommend")
CONFIG_FILE = os.path.join(ROOT_DIR, "config.yaml")

MODES = {
    "standard": {
        "quick_base": 10,
        "quick_strategy": "uniform",
        "deep_unlimited": False,
        "deep_base": 5,
        "deep_strategy": "round_robin",
    },
    "extend": {
        "quick_base": 15,
        "quick_strategy": "uniform",
        "deep_unlimited": False,
        "deep_base": 10,
        "deep_strategy": "round_robin",
    },
    "spark": {
        "quick_base": 10,
        "quick_strategy": "low_bias",
        "deep_unlimited": False,
        "deep_base": 5,
        "deep_strategy": "round_robin",
    },
}


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)


def group_start(title: str) -> None:
    print(f"::group::{title}", flush=True)


def group_end() -> None:
    print("::endgroup::", flush=True)


def load_json(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"missing file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data: Dict[str, Any], path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    log(f"[INFO] saved: {path}")


def load_config_tag_count() -> Tuple[int, List[str]]:
    """读取 config.yaml 中的 tag 数量（去重后）以及 tag 列表。"""
    if not os.path.exists(CONFIG_FILE):
        return 0, []
    try:
        import yaml  # type: ignore
    except Exception:
        log("[WARN] PyYAML not installed, tag count fallback to 0.")
        return 0, []

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as exc:
        log(f"[WARN] failed to read config.yaml: {exc}")
        return 0, []

    subs = (data or {}).get("subscriptions") or {}
    tags: List[str] = []

    def add_tag(value: Any) -> None:
        text = str(value or "").strip()
        if text:
            tags.append(text)

    cfg_keywords = subs.get("keywords") or []
    if isinstance(cfg_keywords, list):
        for item in cfg_keywords:
            if isinstance(item, dict):
                add_tag(item.get("tag") or item.get("alias") or item.get("keyword"))
            elif isinstance(item, str):
                add_tag(item)

    cfg_llm = subs.get("llm_queries") or []
    if isinstance(cfg_llm, list):
        for item in cfg_llm:
            if isinstance(item, dict):
                add_tag(item.get("tag") or item.get("alias") or item.get("query"))
            elif isinstance(item, str):
                add_tag(item)

    unique = []
    seen = set()
    for t in tags:
        if t in seen:
            continue
        seen.add(t)
        unique.append(t)
    return len(unique), unique


def normalize_tags(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []
    cleaned: List[str] = []
    seen = set()
    for item in raw:
        text = str(item or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        cleaned.append(text)
    return cleaned


def parse_score(value: Any) -> float:
    try:
        return float(value)
    except Exception:
        return 0.0


def build_scored_papers(papers: List[Dict[str, Any]], llm_ranked: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    paper_map = {}
    for p in papers:
        pid = str(p.get("id") or "").strip()
        if not pid:
            continue
        paper_map[pid] = p

    merged: Dict[str, Dict[str, Any]] = {}
    for item in llm_ranked:
        pid = str(item.get("paper_id") or item.get("id") or "").strip()
        if not pid or pid not in paper_map:
            continue
        score = parse_score(item.get("score"))
        prev = merged.get(pid)
        if prev is not None and score <= float(prev.get("llm_score", 0)):
            continue
        paper = dict(paper_map[pid])
        paper["llm_score"] = score
        paper["llm_evidence"] = str(item.get("evidence") or "").strip()
        paper["llm_tags"] = normalize_tags(item.get("tags"))
        merged[pid] = paper

    return list(merged.values())


def sort_by_score(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(items, key=lambda x: (-float(x.get("llm_score", 0)), str(x.get("id") or "")))


def build_tag_map(candidates: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    tag_map: Dict[str, List[Dict[str, Any]]] = {}
    for item in candidates:
        tags = item.get("llm_tags") or []
        if not tags:
            tags = ["untagged"]
        for tag in tags:
            tag_map.setdefault(str(tag), []).append(item)

    for tag, items in tag_map.items():
        tag_map[tag] = sort_by_score(items)
    return tag_map


def round_robin_select(candidates: List[Dict[str, Any]], cap: int) -> List[Dict[str, Any]]:
    if cap <= 0:
        return []
    tag_map = build_tag_map(candidates)
    if not tag_map:
        return []

    tag_order = sorted(
        tag_map.keys(),
        key=lambda t: (-float(tag_map[t][0].get("llm_score", 0)), t),
    )

    selected: List[Dict[str, Any]] = []
    selected_ids = set()
    indices = {tag: 0 for tag in tag_order}

    while len(selected) < cap:
        added = False
        for tag in tag_order:
            items = tag_map[tag]
            idx = indices[tag]
            while idx < len(items) and items[idx].get("id") in selected_ids:
                idx += 1
            if idx < len(items):
                item = items[idx]
                selected.append(item)
                selected_ids.add(item.get("id"))
                indices[tag] = idx + 1
                added = True
                if len(selected) >= cap:
                    break
            else:
                indices[tag] = idx
        if not added:
            break
    return selected


def split_layers(candidates: List[Dict[str, Any]]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    results: List[Tuple[str, List[Dict[str, Any]]]] = []

    high_bucket = [p for p in candidates if float(p.get("llm_score", 0)) >= 8.0]
    if high_bucket:
        results.append(("8plus", sort_by_score(high_bucket)))

    mid_bucket = [p for p in candidates if 7.0 <= float(p.get("llm_score", 0)) < 8.0]
    results.append(("7", sort_by_score(mid_bucket)))

    low_bucket = [p for p in candidates if 6.0 <= float(p.get("llm_score", 0)) < 7.0]
    results.append(("6", sort_by_score(low_bucket)))

    return results


def allocate_uniform(layers: List[Tuple[str, List[Dict[str, Any]]]], target: int) -> Dict[str, List[Dict[str, Any]]]:
    if target <= 0:
        return {name: [] for name, _ in layers}
    num_layers = len(layers)
    base = target // num_layers if num_layers else 0
    remainder = target % num_layers if num_layers else 0

    quotas: Dict[str, int] = {}
    for idx, (name, _items) in enumerate(layers):
        quotas[name] = base + (1 if idx < remainder else 0)

    selected: Dict[str, List[Dict[str, Any]]] = {name: [] for name, _ in layers}
    remaining = target
    for name, items in layers:
        take = min(len(items), quotas[name])
        selected[name] = items[:take]
        remaining -= take

    if remaining > 0:
        for name, items in layers:
            if remaining <= 0:
                break
            extra = items[len(selected[name]) :]
            if not extra:
                continue
            take = min(len(extra), remaining)
            selected[name].extend(extra[:take])
            remaining -= take

    return selected


def allocate_low_bias(
    layers: List[Tuple[str, List[Dict[str, Any]]]],
    target: int,
    low_ratio: float = 0.7,
) -> Dict[str, List[Dict[str, Any]]]:
    if target <= 0:
        return {name: [] for name, _ in layers}

    tier_names = [name for name, _ in layers]
    quotas: Dict[str, int] = {name: 0 for name in tier_names}

    if "6" in tier_names:
        low_quota = int(round(target * low_ratio))
        quotas["6"] = low_quota
        remaining = max(target - low_quota, 0)
        others = [n for n in tier_names if n != "6"]
    else:
        remaining = target
        others = tier_names[:]

    if others:
        base = remaining // len(others)
        rem = remaining % len(others)
        for idx, name in enumerate(others):
            quotas[name] += base + (1 if idx < rem else 0)

    selected: Dict[str, List[Dict[str, Any]]] = {name: [] for name, _ in layers}
    remaining = target
    for name, items in layers:
        take = min(len(items), quotas.get(name, 0))
        selected[name] = items[:take]
        remaining -= take

    if remaining > 0:
        for name, items in layers:
            if remaining <= 0:
                break
            extra = items[len(selected[name]) :]
            if not extra:
                continue
            take = min(len(extra), remaining)
            selected[name].extend(extra[:take])
            remaining -= take

    return selected


def interleave_layers(
    selected_by_layer: Dict[str, List[Dict[str, Any]]],
    order: List[str],
) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    idx = {name: 0 for name in order}
    added = True
    while added:
        added = False
        for name in order:
            items = selected_by_layer.get(name) or []
            if idx[name] < len(items):
                result.append(items[idx[name]])
                idx[name] += 1
                added = True
    return result


def select_quick_skim(
    candidates: List[Dict[str, Any]],
    target: int,
    strategy: str,
) -> List[Dict[str, Any]]:
    layers = split_layers(candidates)
    order = [name for name, _ in layers]

    if strategy == "low_bias":
        selected_by_layer = allocate_low_bias(layers, target)
    else:
        selected_by_layer = allocate_uniform(layers, target)

    # 标记分层信息，便于消费侧识别
    marked: Dict[str, List[Dict[str, Any]]] = {}
    for name, items in selected_by_layer.items():
        marked[name] = [dict(item, quick_tier=name) for item in items]

    return interleave_layers(marked, order)[:target]


def process_mode(
    scored_papers: List[Dict[str, Any]],
    tag_count: int,
    mode: str,
    cfg: Dict[str, Any],
) -> Dict[str, Any]:
    deep_candidates = [p for p in scored_papers if float(p.get("llm_score", 0)) >= 8.0]
    deep_candidates = sort_by_score(deep_candidates)

    cap = None
    deep_selected: List[Dict[str, Any]] = []
    if cfg.get("deep_unlimited"):
        deep_selected = deep_candidates
    else:
        deep_base = int(cfg.get("deep_base") or 0)
        cap = deep_base + tag_count
        if len(deep_candidates) <= cap:
            deep_selected = deep_candidates
        else:
            strategy = str(cfg.get("deep_strategy") or "round_robin")
            if strategy == "score":
                deep_selected = deep_candidates[:cap]
            else:
                deep_selected = round_robin_select(deep_candidates, cap)

    selected_ids = {p.get("id") for p in deep_selected}
    deep_overflow = [p for p in deep_candidates if p.get("id") not in selected_ids]

    quick_candidates = [
        p
        for p in scored_papers
        if p.get("id") not in selected_ids and 6.0 <= float(p.get("llm_score", 0)) < 8.0
    ]
    if deep_overflow:
        quick_map = {p.get("id"): p for p in quick_candidates}
        for item in deep_overflow:
            pid = item.get("id")
            if pid not in quick_map:
                quick_candidates.append(item)
    quick_base = int(cfg.get("quick_base") or 0)
    quick_target = quick_base + tag_count
    quick_strategy = str(cfg.get("quick_strategy") or "uniform")
    quick_selected = select_quick_skim(quick_candidates, quick_target, quick_strategy)

    stats = {
        "mode": mode,
        "tag_count": tag_count,
        "deep_dive_selected": len(deep_selected),
        "deep_dive_cap": cap,
        "deep_dive_divecandidates": len(deep_candidates),
        "quick_skim_selected": len(quick_selected),
        "quick_skim_target": quick_target,
        "quick_skim_candidates": len(quick_candidates),
    }

    return {
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "deep_dive": deep_selected,
        "quick_skim": quick_selected,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 5: select papers for deep dive + quick skim (standard/pro/spark).",
    )
    parser.add_argument(
        "--input",
        type=str,
        default=os.path.join(RANKED_DIR, f"arxiv_papers_{TODAY_STR}.llm.json"),
        help="LLM refine JSON input path.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=RECOMMEND_DIR,
        help="output directory for selection JSON.",
    )
    parser.add_argument(
        "--modes",
        type=str,
        default="standard,extend,spark",
        help="comma separated modes (standard,extend,spark).",
    )

    args = parser.parse_args()

    input_path = args.input
    if not os.path.isabs(input_path):
        input_path = os.path.abspath(os.path.join(ROOT_DIR, input_path))

    output_dir = args.output_dir
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(os.path.join(ROOT_DIR, output_dir))

    modes = [m.strip() for m in str(args.modes or "").split(",") if m.strip()]
    modes = [m for m in modes if m in MODES]
    if not modes:
        raise ValueError("modes must include at least one of: standard, extend, spark")

    data = load_json(input_path)
    papers = data.get("papers") or []
    llm_ranked = data.get("llm_ranked") or []
    if not papers or not llm_ranked:
        log("[WARN] missing papers or llm_ranked, skip.")
        return

    tag_count, tag_list = load_config_tag_count()
    log(f"[INFO] config tags={tag_count} | {tag_list}")

    scored_papers = build_scored_papers(papers, llm_ranked)
    if not scored_papers:
        log("[WARN] no scored papers found, skip.")
        return

    group_start(f"Step 5 - select {os.path.basename(input_path)}")
    log(f"[INFO] scored_papers={len(scored_papers)}")

    for mode in modes:
        cfg = MODES.get(mode) or {}
        result = process_mode(scored_papers, tag_count, mode, cfg)
        output_path = os.path.join(output_dir, f"arxiv_papers_{TODAY_STR}.{mode}.json")
        stats = result.get("stats") or {}
        log(f"[STATS] {json.dumps(stats, ensure_ascii=False)}")
        save_json(result, output_path)
        log(
            f"[INFO] mode={mode} deep={stats.get('deep_selected')} quick={stats.get('quick_selected')} "
            f"cap={stats.get('deep_cap')} target={stats.get('quick_skim_target')}"
        )

    group_end()


if __name__ == "__main__":
    main()
