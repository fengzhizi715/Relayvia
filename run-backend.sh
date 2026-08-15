#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
VENV_DIR="$ROOT_DIR/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"
PIP_BIN="$VENV_DIR/bin/pip"
REQUIREMENTS_FILE="$BACKEND_DIR/requirements.txt"
PREPARE_ONLY=0
CHECK_SHELL=0
REQUIRED_IMPORTS=("fastapi" "uvicorn" "sqlalchemy" "pydantic" "alembic" "httpx" "jsonschema")

while [ $# -gt 0 ]; do
  case "$1" in
    --check-shell)
      CHECK_SHELL=1
      shift
      ;;
    --prepare-only)
      PREPARE_ONLY=1
      shift
      ;;
    *)
      echo "[backend] 不支持的参数: $1" >&2
      exit 1
      ;;
  esac
done

if [ "$CHECK_SHELL" -eq 1 ]; then
  exit 0
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "[backend] 创建虚拟环境: $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "[backend] 未找到虚拟环境 Python: $PYTHON_BIN" >&2
  exit 1
fi

NEEDS_INSTALL=0
if [ ! -x "$PIP_BIN" ]; then
  NEEDS_INSTALL=1
else
  for module_name in "${REQUIRED_IMPORTS[@]}"; do
    if ! "$PYTHON_BIN" -c "import ${module_name}" >/dev/null 2>&1; then
      NEEDS_INSTALL=1
      break
    fi
  done
fi

if [ "$NEEDS_INSTALL" -eq 1 ]; then
  echo "[backend] 按 requirements.txt 安装后端依赖"
  "$PIP_BIN" install -r "$REQUIREMENTS_FILE"
fi

if [ "$PREPARE_ONLY" -eq 1 ]; then
  exit 0
fi

export PYTHONPATH="$BACKEND_DIR${PYTHONPATH:+:$PYTHONPATH}"
cd "$ROOT_DIR"

UVICORN_ARGS=(
  -m uvicorn
  app.main:app
  --host "${BACKEND_HOST:-127.0.0.1}"
  --port "${BACKEND_PORT:-8000}"
)

if [ "${RELAYVIA_RELOAD:-1}" = "1" ]; then
  UVICORN_ARGS+=(--reload)
fi

exec "$PYTHON_BIN" "${UVICORN_ARGS[@]}"

