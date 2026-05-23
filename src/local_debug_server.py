#!/usr/bin/env python3
"""本地调试后端：静态托管前端，并把工作流触发映射成本地子进程。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None

ROOT_DIR = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT_DIR / ".local-runs"
CONFIG_PATH = ROOT_DIR / "config.yaml"
SECRET_PATH = ROOT_DIR / "secret.private"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def norm_text(value: Any) -> str:
    return str(value or "").strip()


def build_secret_env(secret: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(secret, dict):
        return {}
    summarized = secret.get("summarizedLLM") if isinstance(secret.get("summarizedLLM"), dict) else {}
    chat_llms = secret.get("chatLLMs") if isinstance(secret.get("chatLLMs"), list) else []
    first_chat = chat_llms[0] if chat_llms and isinstance(chat_llms[0], dict) else {}

    api_key = norm_text(summarized.get("apiKey") or first_chat.get("apiKey"))
    base_url = norm_text(summarized.get("baseUrl") or first_chat.get("baseUrl"))
    model = norm_text(summarized.get("model"))
    if not model and isinstance(first_chat.get("models"), list) and first_chat.get("models"):
        model = norm_text(first_chat.get("models")[0])

    env: dict[str, str] = {}
    if api_key:
        env["SUMMARY_API_KEY"] = api_key
        env["DEEPSEEK_API_KEY"] = api_key
    if base_url:
        env["SUMMARY_BASE_URL"] = base_url
        env["DEEPSEEK_BASE_URL"] = base_url
        env["LLM_PRIMARY_BASE_URL"] = base_url
    if model:
        env["SUMMARY_MODEL"] = model
        env["DEEPSEEK_MODEL"] = model

    reranker = secret.get("rerankerLLM") if isinstance(secret.get("rerankerLLM"), dict) else {}
    rerank_profile = norm_text(reranker.get("profile"))
    rerank_provider = norm_text(reranker.get("provider") or reranker.get("type"))
    rerank_model = norm_text(reranker.get("model"))
    rerank_key = norm_text(reranker.get("apiKey"))
    rerank_base = norm_text(reranker.get("baseUrl"))
    if rerank_profile:
        env["RERANK_PROFILE"] = rerank_profile
    if rerank_provider:
        env["RERANK_PROVIDER"] = rerank_provider
    if rerank_model:
        env["RERANK_MODEL"] = rerank_model
    if rerank_key:
        env["RERANK_API_KEY"] = rerank_key
        if rerank_provider == "public_zwwen":
            env["PUBLIC_RERANK_API_KEY"] = rerank_key
        if rerank_provider == "siliconflow":
            env["SILICONFLOW_API_KEY"] = rerank_key
    if rerank_base:
        env["RERANK_API_BASE_URL"] = rerank_base
        if rerank_provider == "public_zwwen":
            env["PUBLIC_RERANK_API_BASE_URL"] = rerank_base
        if rerank_provider == "siliconflow":
            env["SILICONFLOW_RERANK_URL"] = rerank_base
    return env


class RunStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}

    def create(
        self,
        workflow_key: str,
        workflow_file: str,
        inputs: dict[str, str],
        command: list[str],
        config: dict[str, Any] | None = None,
        secret: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        run_id = uuid.uuid4().hex[:12]
        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        config_path = ""
        if config:
            if yaml is None:
                raise RuntimeError("本地调试后端缺少 PyYAML，无法写入浏览器缓存配置。")
            config_path = str(run_dir / "config.yaml")
            Path(config_path).write_text(
                yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=10**9),
                encoding="utf-8",
            )
        run = {
            "id": run_id,
            "run_number": len(self._runs) + 1,
            "workflow_key": workflow_key,
            "workflow_file": workflow_file,
            "inputs": inputs,
            "command": command,
            "status": "queued",
            "conclusion": None,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "started_at": None,
            "completed_at": None,
            "log_path": str(run_dir / "run.log"),
            "config_path": config_path,
            "secret_env": build_secret_env(secret),
        }
        with self._lock:
            self._runs[run_id] = run
        thread = threading.Thread(target=self._run_process, args=(run_id,), daemon=True)
        thread.start()
        return self._public_run(run)

    def _public_run(self, run: dict[str, Any]) -> dict[str, Any]:
        public = dict(run)
        public.pop("secret_env", None)
        return public

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return sorted((self._public_run(item) for item in self._runs.values()), key=lambda r: r["created_at"], reverse=True)

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            return self._public_run(run) if run else None

    def _get_private(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            return dict(run) if run else None

    def log(self, run_id: str) -> str:
        run = self.get(run_id)
        if not run:
            return ""
        path = Path(str(run.get("log_path") or ""))
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")[-20000:]

    def _update(self, run_id: str, **patch: Any) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            run.update(patch)
            run["updated_at"] = utc_now()

    def _run_process(self, run_id: str) -> None:
        run = self._get_private(run_id)
        if not run:
            return
        log_path = Path(str(run["log_path"]))
        self._update(run_id, status="in_progress", started_at=utc_now())
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("MKL_THREADING_LAYER", "GNU")
        config_path = str(run.get("config_path") or "")
        if config_path:
            env["DPR_CONFIG_FILE"] = config_path
        secret_env = run.get("secret_env") if isinstance(run.get("secret_env"), dict) else {}
        for key, value in secret_env.items():
            text = norm_text(value)
            if text:
                env[str(key)] = text
        try:
            with log_path.open("w", encoding="utf-8") as log:
                log.write(f"[local-debug] started_at={utc_now()}\n")
                log.write(f"[local-debug] cwd={ROOT_DIR}\n")
                if config_path:
                    log.write(f"[local-debug] config={config_path}\n")
                if secret_env:
                    log.write("[local-debug] secret_env=SUMMARY/DEEPSEEK/RERANK variables injected\n")
                log.write(f"[local-debug] command={' '.join(run['command'])}\n\n")
                log.flush()
                proc = subprocess.run(
                    run["command"],
                    cwd=str(ROOT_DIR),
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                    check=False,
                )
                conclusion = "success" if proc.returncode == 0 else "failure"
                log.write(f"\n[local-debug] completed_at={utc_now()} returncode={proc.returncode}\n")
            self._update(run_id, status="completed", conclusion=conclusion, completed_at=utc_now(), returncode=proc.returncode)
        except Exception as exc:
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"\n[local-debug] exception={exc!r}\n")
            self._update(run_id, status="completed", conclusion="failure", completed_at=utc_now(), error=repr(exc))


RUN_STORE = RunStore()


def as_bool(value: Any, default: bool = False) -> bool:
    text = str(value if value is not None else "").strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "y", "on"}


def build_command(workflow_key: str, workflow_file: str, inputs: dict[str, str]) -> list[str]:
    python = sys.executable
    if workflow_file == "daily-paper-reader.yml" or workflow_key == "daily-now":
        cmd = [python, "src/main.py"]
        if as_bool(inputs.get("run_enrich"), False):
            cmd.append("--run-enrich")
        if inputs.get("fetch_days"):
            cmd.extend(["--fetch-days", str(inputs["fetch_days"])])
        if inputs.get("fetch_mode"):
            cmd.extend(["--fetch-mode", str(inputs["fetch_mode"])])
        if inputs.get("profile_tag"):
            cmd.extend(["--profile-tag", str(inputs["profile_tag"])])
        cmd.extend(["--embedding-device", "cpu", "--embedding-batch-size", "8"])
        return cmd

    if workflow_file == "conference-paper-retrieval.yml" or workflow_key == "conference-retrieval":
        cmd = [
            python,
            "src/conference_pipeline.py",
            "--conferences",
            str(inputs.get("conference") or "ICML"),
            "--years",
            str(inputs.get("years") or "2025"),
            "--top-k",
            str(inputs.get("top_k") or "50"),
            "--rrf-top-n",
            str(inputs.get("rrf_top_n") or "200"),
            "--output-dir",
            f"archive/{datetime.now(timezone.utc).strftime('%Y%m%d')}/filtered",
            "--embedding-device",
            "cpu",
            "--embedding-batch-size",
            "8",
        ]
        if as_bool(inputs.get("run_rerank"), True) or as_bool(inputs.get("run_llm_refine"), True):
            cmd.extend(["--run-rerank", "--rerank-device", "cpu", "--rerank-batch-size", "4"])
        if as_bool(inputs.get("run_llm_refine"), True):
            cmd.extend(["--run-llm-refine", "--llm-min-star", str(inputs.get("llm_min_star") or "4"), "--llm-filter-concurrency", "2"])
        return cmd

    if workflow_file == "reset-content.yml" or workflow_key == "reset-content":
        return [python, "-c", "import shutil, pathlib; root=pathlib.Path('.'); shutil.rmtree(root/'docs', ignore_errors=True); shutil.copytree(root/'docs_init', root/'docs'); print('docs reset from docs_init')"]

    if workflow_file == "sync.yml" or workflow_key == "sync":
        return ["git", "status", "--short"]

    raise ValueError(f"本地调试后端暂不支持 workflow: {workflow_key or workflow_file}")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(ROOT_DIR), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/local/health":
            return self._json({"ok": True, "mode": "local-debug", "time": utc_now()})
        if parsed.path == "/api/local/config":
            return self._json({
                "ok": True,
                "path": str(CONFIG_PATH),
                "content": CONFIG_PATH.read_text(encoding="utf-8") if CONFIG_PATH.exists() else "",
            })
        if parsed.path == "/api/local/secret":
            return self._json({
                "ok": True,
                "exists": SECRET_PATH.exists(),
                "path": str(SECRET_PATH),
                "payload": json.loads(SECRET_PATH.read_text(encoding="utf-8")) if SECRET_PATH.exists() else None,
            })
        if parsed.path == "/api/local/runs":
            return self._json({"ok": True, "runs": RUN_STORE.list()})
        if parsed.path.startswith("/api/local/runs/"):
            parts = parsed.path.strip("/").split("/")
            run_id = parts[3] if len(parts) >= 4 else ""
            run = RUN_STORE.get(run_id)
            if not run:
                return self._json({"ok": False, "error": "run not found"}, status=404)
            if len(parts) >= 5 and parts[4] == "log":
                return self._json({"ok": True, "run": run, "log": RUN_STORE.log(run_id)})
            return self._json({"ok": True, "run": run})
        return super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/local/config":
            return self._save_local_config()
        if parsed.path == "/api/local/secret":
            return self._save_local_secret()
        if parsed.path != "/api/local/workflows/dispatch":
            return self._json({"ok": False, "error": "not found"}, status=404)
        try:
            length = int(self.headers.get("Content-Length") or "0")
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            workflow_key = str(payload.get("workflowKey") or "")
            workflow_file = str(payload.get("workflowFile") or "")
            inputs = payload.get("inputs") if isinstance(payload.get("inputs"), dict) else {}
            inputs = {str(k): str(v) for k, v in inputs.items() if v is not None}
            config = payload.get("config") if isinstance(payload.get("config"), dict) else None
            secret = payload.get("secret") if isinstance(payload.get("secret"), dict) else None
            cmd = build_command(workflow_key, workflow_file, inputs)
            run = RUN_STORE.create(workflow_key, workflow_file, inputs, cmd, config=config, secret=secret)
            return self._json({"ok": True, "run": run})
        except Exception as exc:
            return self._json({"ok": False, "error": str(exc)}, status=400)

    def _save_local_secret(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or "0")
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            secret_payload = payload.get("payload")
            if not isinstance(secret_payload, dict):
                return self._json({"ok": False, "error": "payload must be an object"}, status=400)
            SECRET_PATH.write_text(
                json.dumps(secret_payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            return self._json({"ok": True, "path": str(SECRET_PATH), "savedAt": utc_now()})
        except Exception as exc:
            return self._json({"ok": False, "error": str(exc)}, status=400)

    def _save_local_config(self) -> None:
        if yaml is None:
            return self._json({"ok": False, "error": "本地调试后端缺少 PyYAML，无法写入 config.yaml。"}, status=500)
        try:
            length = int(self.headers.get("Content-Length") or "0")
            payload = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            config = payload.get("config")
            if not isinstance(config, dict):
                return self._json({"ok": False, "error": "config must be an object"}, status=400)
            content = yaml.safe_dump(config, allow_unicode=True, sort_keys=False, width=10**9)
            CONFIG_PATH.write_text(content, encoding="utf-8")
            return self._json({"ok": True, "path": str(CONFIG_PATH), "savedAt": utc_now()})
        except Exception as exc:
            return self._json({"ok": False, "error": str(exc)}, status=400)

    def _json(self, payload: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily Paper Reader 本地调试后端")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8567)
    args = parser.parse_args()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    display_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    print(f"[local-debug] serving http://{display_host}:{args.port}", flush=True)
    if display_host != args.host:
        print(f"[local-debug] listening on {args.host}:{args.port}", flush=True)
    print("[local-debug] 前端在 localhost 下触发任务会调用本地 /api/local/workflows/dispatch", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
