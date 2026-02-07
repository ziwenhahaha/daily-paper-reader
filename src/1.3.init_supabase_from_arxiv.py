#!/usr/bin/env python
# 初始化 Supabase 公共论文库：
# 1) 使用 1.fetch_paper_arxiv.py 进行长时间窗口分片抓取（避免深分页 500）
# 2) 使用 1.2.sync_supabase_public.py 生成 embedding 并 upsert 到 Supabase

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone


SCRIPT_DIR = os.path.dirname(__file__)
TODAY_STR = datetime.now(timezone.utc).strftime("%Y%m%d")


def run_step(label: str, args: list[str]) -> None:
    print(f"[INFO] {label}: {' '.join(args)}", flush=True)
    subprocess.run(args, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="抓取近 N 天 arXiv 并初始化同步到 Supabase（含 embedding）。",
    )
    parser.add_argument("--days", type=int, default=30, help="回溯抓取天数，默认 30。")
    parser.add_argument("--chunk-days", type=int, default=7, help="抓取分片窗口天数，默认 7。")
    parser.add_argument(
        "--ignore-seen",
        action="store_true",
        default=True,
        help="抓取时忽略 seen/crawl_state，严格按 days 回溯（默认开启）。",
    )
    parser.add_argument(
        "--use-seen",
        dest="ignore_seen",
        action="store_false",
        help="抓取时使用 seen/crawl_state 增量状态（关闭 ignore-seen）。",
    )
    parser.add_argument("--date", type=str, default=TODAY_STR, help="同步日期目录，默认今天 YYYYMMDD。")
    parser.add_argument(
        "--raw-input",
        type=str,
        default="",
        help="可选：直接指定原始 JSON 文件路径（优先于 --date 目录推导）。",
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="跳过抓取步骤，直接复用 archive/<date>/raw/arxiv_papers_<date>.json 做同步。",
    )
    parser.add_argument("--embed-model", type=str, default="", help="embedding 模型（空=按 config/default）。")
    parser.add_argument("--embed-device", type=str, default="cpu", help="单设备模式（如 cpu/cuda:0）。")
    parser.add_argument("--embed-devices", type=str, default="", help="多设备列表，如 cuda:0,cuda:1。")
    parser.add_argument("--embed-batch-size", type=int, default=8, help="embedding batch size。")
    parser.add_argument("--embed-max-length", type=int, default=0, help="embedding max length，<=0 表示不限制。")
    parser.add_argument("--upsert-batch-size", type=int, default=200, help="Supabase upsert 批大小。")
    parser.add_argument("--upsert-timeout", type=int, default=120, help="Supabase upsert 超时（秒）。")
    parser.add_argument("--upsert-retries", type=int, default=5, help="Supabase upsert 每批重试次数。")
    parser.add_argument("--upsert-retry-wait", type=float, default=2.0, help="Supabase upsert 重试基准等待秒数。")
    parser.add_argument("--no-embeddings", action="store_true", help="仅同步元数据，不生成 embedding。")
    args = parser.parse_args()

    python = sys.executable

    date_str = str(args.date or TODAY_STR)
    raw_input = str(args.raw_input or "").strip()
    if raw_input:
        if os.path.isabs(raw_input):
            raw_path = raw_input
        else:
            raw_path = os.path.abspath(os.path.join(os.path.abspath(os.path.join(SCRIPT_DIR, "..")), raw_input))
    else:
        raw_path = os.path.join(
            os.path.abspath(os.path.join(SCRIPT_DIR, "..")),
            "archive",
            date_str,
            "raw",
            f"arxiv_papers_{date_str}.json",
        )

    if not args.skip_fetch:
        fetch_cmd = [
            python,
            os.path.join(SCRIPT_DIR, "1.fetch_paper_arxiv.py"),
            "--days",
            str(max(int(args.days or 1), 1)),
            "--chunk-days",
            str(max(int(args.chunk_days or 1), 1)),
            "--disable-supabase-read",
        ]
        if args.ignore_seen:
            fetch_cmd.append("--ignore-seen")
        run_step("Step 1 - fetch arXiv", fetch_cmd)
    else:
        if not os.path.exists(raw_path):
            raise FileNotFoundError(
                f"--skip-fetch 已指定，但未找到原始文件：{raw_path}"
            )
        print(f"[INFO] Step 1 已跳过，复用原始文件：{raw_path}", flush=True)

    sync_cmd = [
        python,
        os.path.join(SCRIPT_DIR, "1.2.sync_supabase_public.py"),
        "--date",
        date_str,
        "--embed-batch-size",
        str(max(int(args.embed_batch_size or 1), 1)),
        "--embed-max-length",
        str(int(args.embed_max_length or 0)),
        "--upsert-batch-size",
        str(max(int(args.upsert_batch_size or 1), 1)),
        "--upsert-timeout",
        str(max(int(args.upsert_timeout or 1), 1)),
        "--upsert-retries",
        str(max(int(args.upsert_retries or 0), 0)),
        "--upsert-retry-wait",
        str(max(float(args.upsert_retry_wait or 0.0), 0.0)),
    ]
    if raw_input:
        sync_cmd += ["--raw-input", raw_path]
    if args.embed_model:
        sync_cmd += ["--embed-model", str(args.embed_model)]
    if args.embed_devices:
        sync_cmd += ["--embed-devices", str(args.embed_devices)]
    else:
        sync_cmd += ["--embed-device", str(args.embed_device or "cpu")]
    if args.no_embeddings:
        sync_cmd.append("--no-embeddings")
    run_step("Step 2 - sync Supabase", sync_cmd)


if __name__ == "__main__":
    main()
