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
except Exception:  # pragma: no cover - compatibility for package import path
    from src.source_config import migrate_source_config_inplace, save_config


SCRIPT_DIR = os.path.dirname(__file__)
ROOT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, ".."))
DEFAULT_CONFIG_FILE = os.path.join(ROOT_DIR, "config.yaml")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate multi-source configurations in config.yaml and backfill missing paper_sources.")
    parser.add_argument("--config", type=str, default=DEFAULT_CONFIG_FILE, help="Path to config.yaml to migrate.")
    parser.add_argument("--check", action="store_true", help="Only check, do not write back to file.")
    args = parser.parse_args()

    path = os.path.abspath(args.config)
    if yaml is None:
        raise RuntimeError("PyYAML not installed; cannot migrate config.yaml.")
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f) or {}
    if not isinstance(config, dict):
        raise RuntimeError("config.yaml top-level structure must be an object.")
    changed, notes = migrate_source_config_inplace(config)
    if changed and not args.check:
        save_config(config, path)

    if notes:
        for note in notes:
            print(note, flush=True)
    else:
        print("Config does not need to be migrated.", flush=True)
    if args.check and changed:
        print("Config needs to be migrated; run without --check to apply changes.", flush=True)
        sys.exit(10)

if __name__ == "__main__":
    main()
