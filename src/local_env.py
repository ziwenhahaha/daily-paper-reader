from __future__ import annotations

import os
from pathlib import Path


def _strip_inline_comment(value: str) -> str:
    quote: str | None = None
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in {"'", '"'}:
            quote = char
            continue
        if char == "#" and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.strip()


def _unquote(value: str) -> str:
    text = _strip_inline_comment(value)
    quote = text[:1]
    if len(text) >= 2 and text[0] == text[-1] and quote in {"'", '"'}:
        text = text[1:-1]
        if quote == '"':
            text = text.replace(r"\n", "\n").replace(r"\t", "\t")
    return text


def _valid_env_key(key: str) -> bool:
    return bool(key) and not key[0].isdigit() and key.replace("_", "").isalnum()


def load_local_env() -> None:
    if str(os.getenv("DPR_DISABLE_DOTENV") or "").strip().lower() in {"1", "true", "yes", "on"}:
        return

    root = Path(__file__).resolve().parent.parent
    env_path = Path(os.getenv("DPR_DOTENV_PATH") or root / ".env").expanduser()
    try:
        lines = env_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not _valid_env_key(key):
            continue
        os.environ.setdefault(key, _unquote(value.strip()))
