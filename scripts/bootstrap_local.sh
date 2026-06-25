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

command -v "$PYTHON_BIN" >/dev/null 2>&1 || fail "Python not found: $PYTHON_BIN"

if [ ! -d "$VENV_DIR" ]; then
  log "Creating virtual environment: $VENV_DIR"
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

log "Using Python: $(python -c 'import sys; print(sys.executable)')"

if [ "$SKIP_INSTALL" != "1" ] && [ "$INSTALL_MODE" = "full" ]; then
  log "Installing/updating full dependencies: requirements-local-models.txt"
  log "Using CPU PyTorch by default: $TORCH_INDEX_URL"
  python -m pip install --upgrade pip
  python -m pip install --index-url "$TORCH_INDEX_URL" torch
  python -m pip install -r requirements-local-models.txt
elif [ "$SKIP_INSTALL" != "1" ] && [ "$INSTALL_MODE" = "remote" ]; then
  log "Installing/updating remote-service dependencies: requirements.txt"
  log "Skipping torch / sentence-transformers; defaulting to zwwen embedding/rerank service"
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
elif [ "$SKIP_INSTALL" != "1" ]; then
  log "Quick-deploy mode: skipping full dependency install"
  log "To install remote-service dependencies, run: scripts/bootstrap_local.sh or DPR_INSTALL_MODE=remote scripts/bootstrap_local.sh"
  log "For local model fallback only, run: DPR_INSTALL_MODE=full scripts/bootstrap_local.sh"
else
  log "Skipping dependency install: DPR_SKIP_INSTALL=1"
fi

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  log "Created .env from .env.example; fill in API keys as needed"
elif [ -f .env ]; then
  log "Found existing .env"
else
  log ".env.example not found; skipping .env initialization"
fi

if command -v lsof >/dev/null 2>&1; then
  if lsof -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    fail "Port $PORT is already in use; set DPR_LOCAL_PORT to another port and retry"
  fi
elif command -v ss >/dev/null 2>&1; then
  if ss -ltn | awk '{print $4}' | grep -Eq "(^|:)${PORT}$"; then
    fail "Port $PORT is already in use; set DPR_LOCAL_PORT to another port and retry"
  fi
fi

log "Starting local debug backend: http://${HOST}:${PORT}"
log "Workflow triggers run locally and do not call GitHub Actions"
exec python src/local_debug_server.py --host "$HOST" --port "$PORT"
