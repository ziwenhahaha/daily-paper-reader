#!/usr/bin/env python

from __future__ import annotations

import argparse
import os
import sys

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

try:
    from source_config import migrate_source_config_inplace, save_config
except Exception:  # pragma: no cover - 兼容 package 导入路径
    from src.source_config import migrate_source_config_inplace, save_config


SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
DEFAULT_CONFIG_FILE = os.path.join(ROOT_DIR, "config.yaml")


def main() -> None:
    parser = argparse.ArgumentParser(description="迁移 config.yaml 中的多源配置并回填缺失的 paper_sources。")
    parser.add_argument("--config", type=str, default=DEFAULT_CONFIG_FILE, help="待迁移的 config.yaml 路径。")
    parser.add_argument("--check", action="store_true", help="仅检查，不写回文件。")
    args = parser.parse_args()

    path = os.path.abspath(args.config)
    if yaml is None:
        raise RuntimeError("未安装 PyYAML，无法迁移 config.yaml。")
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    if not isinstance(config, dict):
        raise RuntimeError("config.yaml 顶层结构必须为对象。")
    changed, notes = migrate_source_config_inplace(config)
    if changed and not args.check:
        save_config(config, path)

    if notes:
        for note in notes:
            print(note, flush=True)
    else:
        print("配置无需迁移。", flush=True)
    if args.check and changed:
        sys.exit(10)


if __name__ == "__main__":
    main()
