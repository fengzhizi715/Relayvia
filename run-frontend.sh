#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
CHECK_SHELL=0

while [ $# -gt 0 ]; do
  case "$1" in
    --check-shell)
      CHECK_SHELL=1
      shift
      ;;
    *)
      echo "[frontend] 不支持的参数: $1" >&2
      exit 1
      ;;
  esac
done

if [ "$CHECK_SHELL" -eq 1 ]; then
  exit 0
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[frontend] 未找到 npm，请先安装 Node.js" >&2
  exit 1
fi

cd "$FRONTEND_DIR"

if [ ! -d "node_modules" ]; then
  echo "[frontend] 安装前端依赖"
  npm install
fi

exec npm run dev -- --host "${FRONTEND_HOST:-127.0.0.1}" --port "${FRONTEND_PORT:-5173}"

