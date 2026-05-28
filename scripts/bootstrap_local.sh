#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

HOST="${DPR_LOCAL_HOST:-127.0.0.1}"
PORT="${DPR_LOCAL_PORT:-8567}"
VENV_DIR="${DPR_LOCAL_VENV:-.venv}"
PYTHON_BIN="${PYTHON:-python3}"
INSTALL_MODE="${DPR_INSTALL_MODE:-remote}"
SKIP_INSTALL="${DPR_SKIP_INSTALL:-0}"
TORCH_INDEX_URL="${DPR_TORCH_INDEX_URL:-https://download.pytorch.org/whl/cpu}"

log() {
  printf '[bootstrap-local] %s\n' "$*"
}

fail() {
  printf '[bootstrap-local] ERROR: %s\n' "$*" >&2
  exit 1
}

command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail "未找到 Python：$PYTHON_BIN"

if [ ! -d "$VENV_DIR" ]; then
  log "创建虚拟环境：$VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

log "使用 Python：$(python -c 'import sys; print(sys.executable)')"

if [ "$SKIP_INSTALL" != "1" ] && [ "$INSTALL_MODE" = "full" ]; then
  log "安装/更新完整依赖：requirements-local-models.txt"
  log "默认使用 CPU PyTorch：$TORCH_INDEX_URL"
  python -m pip install --upgrade pip
  python -m pip install --index-url "$TORCH_INDEX_URL" torch
  python -m pip install -r requirements-local-models.txt
elif [ "$SKIP_INSTALL" != "1" ] && [ "$INSTALL_MODE" = "remote" ]; then
  log "安装/更新远程服务模式依赖：requirements.txt"
  log "不会安装 torch / sentence-transformers；默认使用 zwwen embedding/rerank 服务"
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
elif [ "$SKIP_INSTALL" != "1" ]; then
  log "快速部署模式：跳过完整依赖安装"
  log "如需补齐远程服务模式依赖，请执行：scripts/bootstrap_local.sh 或 DPR_INSTALL_MODE=remote scripts/bootstrap_local.sh"
  log "仅当需要本地模型 fallback 时，再执行：DPR_INSTALL_MODE=full scripts/bootstrap_local.sh"
else
  log "跳过依赖安装：DPR_SKIP_INSTALL=1"
fi

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  log "已从 .env.example 生成 .env，请按需填写 API Key"
elif [ -f .env ]; then
  log "检测到已有 .env"
else
  log "未找到 .env.example，跳过 .env 初始化"
fi

if command -v lsof >/dev/null 2>&1; then
  if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    fail "端口 $PORT 已被占用，请设置 DPR_LOCAL_PORT=其它端口后重试"
  fi
elif command -v ss >/dev/null 2>&1; then
  if ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${PORT}$"; then
    fail "端口 $PORT 已被占用，请设置 DPR_LOCAL_PORT=其它端口后重试"
  fi
fi

log "启动本地调试后端：http://${HOST}:${PORT}"
log "触发 workflow 将在本机执行，不会上 GitHub Actions"
exec python src/local_debug_server.py --host "$HOST" --port "$PORT"
