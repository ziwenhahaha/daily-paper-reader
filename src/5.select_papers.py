#!/usr/bin/env python
# Step 5：基于 LLM 评分结果，生成“精读区 + 速览区”的三种模式输出。

import argparse
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from subscription_plan import count_subscription_tags

SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
ARCHIVE_ROOT = os.path.join(ROOT_DIR, "archive")
TODAY_STR = str(os.getenv("DPR_RUN_DATE") or "").strip() or datetime.now(timezone.utc).strftime("%Y%m%d")
ARCHIVE_DIR = os.path.join(ARCHIVE_ROOT, TODAY_STR)
RANKED_DIR = os.path.join(ARCHIVE_DIR, "rank")
RECOMMEND_DIR = os.path.join(ARCHIVE_DIR, "recommend")
CARRYOVER_PATH = os.path.join(ARCHIVE_ROOT, "carryover.json")
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
    # 回溯窗口（days）专用：>=8 分全量输出，全部进入速览区
    "skims": {
        "all_quick_min_score": 8.0,
    },
}

CARRYOVER_DAYS = 5
CARRYOVER_RATIO = 0.5


def log(message: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {message}", flush=True)

def log_substep(code: str, name: str, phase: str) -> None:
    """
    用于前端解析的子步骤标记。
    格式： [SUBSTEP] 5.1 - xxx START/END
    """
    phase = str(phase or "").strip().upper()
    if phase not in ("START", "END"):
        phase = "INFO"
    log(f"[SUBSTEP] {code} - {name} {phase}")


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


def parse_date_str(date_str: str) -> date:
    s = str(date_str or "").strip()
    if re.fullmatch(r"\d{8}-\d{8}", s):
        # 区间 token 用结束日期参与“今日/最近N天”逻辑
        s = s.split("-", 1)[1]
    return datetime.strptime(s, "%Y%m%d").date()


def list_date_dirs(archive_root: str) -> List[str]:
    if not os.path.isdir(archive_root):
        return []
    result: List[str] = []
    for name in os.listdir(archive_root):
        if re.match(r"^\d{8}$", name) or re.match(r"^\d{8}-\d{8}$", name):
            result.append(name)
    return sorted(result)


def collect_seen_ids(archive_root: str, today_str: str) -> set:
    seen = set()
    for day in list_date_dirs(archive_root):
        if day == today_str:
            continue
        rec_dir = os.path.join(archive_root, day, "recommend")
        if not os.path.isdir(rec_dir):
            continue
        for name in os.listdir(rec_dir):
            if not name.endswith(".json"):
                continue
            # 兼容单日与区间 token 的文件名前缀
            if not name.startswith(f"arxiv_papers_{day}."):
                continue
            rec_path = os.path.join(rec_dir, name)
            try:
                payload = load_json(rec_path)
            except Exception:
                continue
            for key in ("deep_dive", "quick_skim"):
                for item in payload.get(key) or []:
                    pid = str(item.get("id") or item.get("paper_id") or "").strip()
                    if pid:
                        seen.add(pid)
    return seen


def parse_payload_date(payload: Dict[str, Any]) -> date | None:
    date_str = str(payload.get("updated_date") or "").strip()
    if date_str:
        try:
            return parse_date_str(date_str)
        except Exception:
            return None
    generated_at = str(payload.get("generated_at") or "").strip()
    if generated_at:
        try:
            return datetime.fromisoformat(generated_at.replace("Z", "+00:00")).date()
        except Exception:
            return None
    return None


def load_recent_carryover(
    carryover_path: str,
    today_date: date,
    max_days: int,
) -> Tuple[List[Dict[str, Any]], int]:
    if not os.path.exists(carryover_path):
        return [], 0
    try:
        payload = load_json(carryover_path)
    except Exception:
        return [], 0

    items = payload.get("items") or []
    if not isinstance(items, list):
        items = []

    base_date = parse_payload_date(payload)
    delta = 0
    if base_date:
        delta = (today_date - base_date).days
        if delta < 0:
            delta = 0

    updated: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        carry_days = int(item.get("carry_days") or 1)
        if delta > 0:
            carry_days += delta
        if carry_days > max_days:
            continue
        copied = dict(item)
        copied["carry_days"] = carry_days
        updated.append(copied)

    return updated, delta


def load_config_tag_count() -> Tuple[int, List[str]]:
    """读取订阅配置中的 tag 数量（优先新结构 intent_profiles）。"""
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
    return count_subscription_tags(data if isinstance(data, dict) else {})


def load_arxiv_paper_setting() -> Dict[str, Any]:
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        import yaml  # type: ignore
    except Exception:
        log("[WARN] PyYAML not installed, skip arxiv_paper_setting.")
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except Exception as exc:
        log(f"[WARN] failed to read config.yaml: {exc}")
        return {}
    setting = (data or {}).get("arxiv_paper_setting") or {}
    return setting if isinstance(setting, dict) else {}


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
        evidence_cn = str(item.get("evidence_cn") or "").strip()
        evidence_en = str(item.get("evidence_en") or "").strip()
        tldr_cn = str(item.get("tldr_cn") or "").strip()
        tldr_en = str(item.get("tldr_en") or "").strip()
        legacy = str(item.get("evidence") or "").strip()
        # 优先保存中英双语；同时保留 llm_evidence 作为“默认展示”字段（优先中文）
        paper["llm_evidence_en"] = evidence_en or legacy
        paper["llm_evidence_cn"] = evidence_cn or (evidence_en or legacy)
        paper["llm_evidence"] = paper["llm_evidence_cn"]
        paper["llm_tldr_en"] = tldr_en
        paper["llm_tldr_cn"] = tldr_cn or tldr_en
        paper["llm_tldr"] = paper["llm_tldr_cn"]
        paper["llm_tags"] = normalize_tags(item.get("tags"))
        merged[pid] = paper

    return list(merged.values())


def build_candidates(
    scored_papers: List[Dict[str, Any]],
    carryover_items: List[Dict[str, Any]],
    seen_ids: set,
) -> List[Dict[str, Any]]:
    merged: Dict[str, Dict[str, Any]] = {}

    for item in carryover_items:
        pid = str(item.get("id") or item.get("paper_id") or "").strip()
        if not pid or pid in seen_ids:
            continue
        copied = dict(item)
        copied["id"] = pid
        copied["_source"] = "carryover"
        merged[pid] = copied

    for item in scored_papers:
        pid = str(item.get("id") or "").strip()
        if not pid or pid in seen_ids:
            continue
        copied = dict(item)
        copied["_source"] = "new"
        merged[pid] = copied

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


def sanitize_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        copied = dict(item)
        copied.pop("_source", None)
        copied.pop("carry_days", None)
        cleaned.append(copied)
    return cleaned


def select_deep_with_carryover(
    candidates: List[Dict[str, Any]],
    cap: int,
    carryover_ratio: float,
) -> List[Dict[str, Any]]:
    if cap <= 0:
        return []
    new_items = [p for p in candidates if p.get("_source") != "carryover"]
    carry_items = [p for p in candidates if p.get("_source") == "carryover"]

    max_carry = int(cap * carryover_ratio) if carryover_ratio > 0 else 0
    cap_new = max(cap - max_carry, 0)

    selected: List[Dict[str, Any]] = []
    selected_ids = set()

    if new_items:
        pick_new = round_robin_select(new_items, min(cap_new, len(new_items)))
        selected.extend(pick_new)
        selected_ids.update(p.get("id") for p in pick_new)

    remaining = cap - len(selected)
    if remaining > 0 and carry_items:
        pick_carry = round_robin_select(carry_items, min(remaining, len(carry_items)))
        selected.extend(pick_carry)
        selected_ids.update(p.get("id") for p in pick_carry)
        remaining = cap - len(selected)

    if remaining > 0 and new_items:
        extra_new = [p for p in new_items if p.get("id") not in selected_ids]
        if extra_new:
            pick_extra = round_robin_select(extra_new, min(remaining, len(extra_new)))
            selected.extend(pick_extra)

    return selected


def build_carryover_out(
    candidates: List[Dict[str, Any]],
    recommended_ids: set,
    carryover_days: int,
) -> List[Dict[str, Any]]:
    carryover_out: List[Dict[str, Any]] = []
    for item in candidates:
        pid = str(item.get("id") or "").strip()
        if not pid or pid in recommended_ids:
            continue
        if float(item.get("llm_score", 0)) < 8.0:
            continue
        carry_days = int(item.get("carry_days") or 1)
        if carry_days > carryover_days:
            continue
        copied = dict(item)
        copied.pop("_source", None)
        copied["paper_id"] = copied.get("id")
        copied["carry_days"] = carry_days
        carryover_out.append(copied)
    return carryover_out


def process_mode(
    candidates: List[Dict[str, Any]],
    tag_count: int,
    mode: str,
    cfg: Dict[str, Any],
    carryover_ratio: float,
) -> Dict[str, Any]:
    if cfg.get("all_quick_min_score") is not None:
        return process_mode_all_quick_min_score(
            candidates=candidates,
            mode=mode,
            min_score=float(cfg.get("all_quick_min_score") or 0),
        )

    deep_candidates = [p for p in candidates if float(p.get("llm_score", 0)) >= 8.0]
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
                deep_selected = select_deep_with_carryover(
                    deep_candidates,
                    cap,
                    carryover_ratio,
                )

    selected_ids = {p.get("id") for p in deep_selected}
    deep_overflow = [p for p in deep_candidates if p.get("id") not in selected_ids]

    quick_candidates = [
        p
        for p in candidates
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
        "deep_divecandidates": len(deep_candidates),
        "deep_cap": cap,
        "deep_selected": len(deep_selected),
        "quick_candidates": len(quick_candidates),
        "quick_skim_target": quick_target,
        "quick_selected": len(quick_selected),
    }

    return {
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "deep_dive": sanitize_items(deep_selected),
        "quick_skim": sanitize_items(quick_selected),
    }


def process_mode_all_quick_min_score(
    candidates: List[Dict[str, Any]],
    mode: str,
    min_score: float,
) -> Dict[str, Any]:
    """
    回溯窗口（days）场景：不再做“精读/速览配额分配”，而是将达到阈值的论文全部输出到速览区。
    """
    threshold = float(min_score)
    picked = [p for p in candidates if float(p.get("llm_score", 0)) >= threshold]
    picked = sort_by_score(picked)

    stats = {
        "mode": mode,
        "forced_all_quick": True,
        "min_score": threshold,
        "deep_divecandidates": len(picked),
        "deep_cap": None,
        "deep_selected": 0,
        "quick_candidates": len(picked),
        "quick_skim_target": None,
        "quick_selected": len(picked),
    }

    return {
        "mode": mode,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
        "deep_dive": [],
        "quick_skim": sanitize_items(picked),
    }

def force_all_into_quick(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    将精读区合并进速览区，确保所有论文都归入 quick_skim。
    规则：保留“精读优先”（高分在前）的顺序：deep_dive 在前，quick_skim 在后；按 id 去重。
    """
    deep = result.get("deep_dive") or []
    quick = result.get("quick_skim") or []
    merged: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for item in list(deep) + list(quick):
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or item.get("paper_id") or "").strip()
        if not pid or pid in seen:
            continue
        seen.add(pid)
        merged.append(item)

    copied = dict(result)
    copied["deep_dive"] = []
    copied["quick_skim"] = merged

    stats = dict((copied.get("stats") or {}))
    stats["deep_selected"] = 0
    stats["quick_selected"] = len(merged)
    stats["forced_all_quick"] = True
    copied["stats"] = stats
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Step 5: select papers for deep dive + quick skim (standard/extend/spark).",
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
        default=None,
        help="comma separated modes (standard,extend,spark,skims). default: config arxiv_paper_setting.mode",
    )
    parser.add_argument(
        "--carryover-only",
        action="store_true",
        help="只使用 archive/carryover.json 作为候选集（忽略输入文件与 seen_ids 过滤）。",
    )
    parser.add_argument(
        "--preserve-carryover",
        action="store_true",
        help="运行完成后不覆盖写入 archive/carryover.json（默认会按本次推荐结果更新）。",
    )
    parser.add_argument(
        "--all-quick",
        action="store_true",
        help="Force all selected papers into quick_skim (deep_dive will be empty).",
    )
    parser.add_argument(
        "--all-quick-min-score",
        type=float,
        default=None,
        help="When set, output ALL candidates with llm_score >= min_score into quick_skim (no caps).",
    )

    args = parser.parse_args()

    input_path = args.input
    if not os.path.isabs(input_path):
        input_path = os.path.abspath(os.path.join(ROOT_DIR, input_path))

    output_dir = args.output_dir
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(os.path.join(ROOT_DIR, output_dir))

    setting = load_arxiv_paper_setting()
    carryover_days = int(setting.get("days_window") or CARRYOVER_DAYS)
    mode_text = args.modes
    if not mode_text:
        mode_text = setting.get("mode") or "standard,extend,spark"

    modes = [m.strip() for m in str(mode_text or "").split(",") if m.strip()]
    modes = [m for m in modes if m in MODES]
    if not modes:
        raise ValueError("modes must include at least one of: standard, extend, spark, skims")

    # skims 模式用于“回溯窗口/批量重跑”：默认不做历史 seen_ids 过滤，
    # 否则会因为之前推荐过而导致输出数量偏少。
    ignore_seen_ids = False
    if modes and all((MODES.get(m) or {}).get("all_quick_min_score") is not None for m in modes):
        ignore_seen_ids = True

    log_substep("5.1", "加载输入数据", "START")
    try:
        if args.carryover_only:
            log("[INFO] carryover-only=true：将忽略输入文件，仅使用 carryover 作为候选集。")
            papers = []
            llm_ranked = []
        else:
            # 检查输入文件是否存在，如果不存在则只使用 carryover
            if not os.path.exists(input_path):
                log(f"[INFO] 输入文件不存在：{input_path}（今天没有新论文，将只使用 carryover）")
                papers = []
                llm_ranked = []
            else:
                data = load_json(input_path)
                papers = data.get("papers") or []
                llm_ranked = data.get("llm_ranked") or []
    finally:
        log_substep("5.1", "加载输入数据", "END")

    if not papers or not llm_ranked:
        log("[INFO] 今天没有新论文，将只使用 carryover 生成推荐。")

    tag_count, tag_list = load_config_tag_count()
    log(f"[INFO] config tags={tag_count} | {tag_list}")
    log(f"[INFO] arxiv_paper_setting mode={mode_text} days_window={carryover_days}")

    group_start(f"Step 5 - select {os.path.basename(input_path)}")
    log_substep("5.2", "构建评分论文列表", "START")
    try:
        scored_papers = build_scored_papers(papers, llm_ranked)
        log(f"[INFO] scored_papers={len(scored_papers)}")
    finally:
        log_substep("5.2", "构建评分论文列表", "END")

    archive_root = os.path.join(ROOT_DIR, "archive")
    today_date = parse_date_str(TODAY_STR)
    if args.carryover_only or ignore_seen_ids:
        seen_ids = set()
        if ignore_seen_ids:
            log("[INFO] skims/backfill 模式：已关闭历史 seen_ids 过滤（输出数量更完整）。")
    else:
        seen_ids = collect_seen_ids(archive_root, TODAY_STR)
    log_substep("5.3", "加载 carryover 并构建候选集", "START")
    try:
        carryover_items, _delta = load_recent_carryover(
            CARRYOVER_PATH,
            today_date,
            carryover_days,
        )
        if args.carryover_only:
            candidates = []
            for item in carryover_items:
                pid = str(item.get("id") or item.get("paper_id") or "").strip()
                if not pid:
                    continue
                copied = dict(item)
                copied["id"] = pid
                copied["_source"] = "carryover"
                candidates.append(copied)
        else:
            candidates = build_candidates(scored_papers, carryover_items, seen_ids)
    finally:
        log_substep("5.3", "加载 carryover 并构建候选集", "END")

    if not candidates:
        log("[INFO] 没有候选论文（新论文=0 且 carryover=0），将写入空推荐结果并更新 carryover。")
        os.makedirs(output_dir, exist_ok=True)
        for mode in modes:
            output_path = os.path.join(output_dir, f"arxiv_papers_{TODAY_STR}.{mode}.json")
            empty = {
                "mode": mode,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "stats": {
                    "mode": mode,
                    "tag_count": tag_count,
                    "deep_divecandidates": 0,
                    "deep_cap": None,
                    "deep_selected": 0,
                    "quick_candidates": 0,
                    "quick_skim_target": int((MODES.get(mode) or {}).get("quick_base") or 0) + tag_count,
                    "quick_selected": 0,
                },
                "deep_dive": [],
                "quick_skim": [],
            }
            save_json(empty, output_path)

        carryover_payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "updated_date": TODAY_STR,
            "carryover_days": carryover_days,
            "items": [],
        }
        save_json(carryover_payload, CARRYOVER_PATH)
        group_end()
        return

    recommended_ids: set = set()

    log_substep("5.4", "按模式生成推荐结果", "START")
    for mode in modes:
        cfg = MODES.get(mode) or {}
        if args.all_quick_min_score is not None:
            result = process_mode_all_quick_min_score(
                candidates=candidates,
                mode=mode,
                min_score=float(args.all_quick_min_score),
            )
        else:
            result = process_mode(
                candidates,
                tag_count,
                mode,
                cfg,
                carryover_ratio=CARRYOVER_RATIO,
            )
            if args.all_quick:
                result = force_all_into_quick(result)
        output_path = os.path.join(output_dir, f"arxiv_papers_{TODAY_STR}.{mode}.json")
        stats = result.get("stats") or {}
        log(f"[STATS] {json.dumps(stats, ensure_ascii=False)}")
        save_json(result, output_path)
        log(
            f"[INFO] mode={mode} deep={stats.get('deep_selected')} quick={stats.get('quick_selected')} "
            f"cap={stats.get('deep_cap')} target={stats.get('quick_skim_target')}"
        )

        for key in ("deep_dive", "quick_skim"):
            for item in result.get(key) or []:
                pid = str(item.get("id") or item.get("paper_id") or "").strip()
                if pid:
                    recommended_ids.add(pid)
    log_substep("5.4", "按模式生成推荐结果", "END")

    log_substep("5.5", "写入 carryover 状态", "START")
    if args.preserve_carryover:
        log("[INFO] preserve-carryover=true：跳过写入 carryover.json")
    else:
        carryover_out = build_carryover_out(candidates, recommended_ids, carryover_days)
        carryover_payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "updated_date": TODAY_STR,
            "carryover_days": carryover_days,
            "items": carryover_out,
        }
        save_json(carryover_payload, CARRYOVER_PATH)
    log_substep("5.5", "写入 carryover 状态", "END")

    group_end()


if __name__ == "__main__":
    main()
