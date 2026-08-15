#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then
  exec bash "$0" "$@"
fi

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_SCRIPT="$ROOT_DIR/run-backend.sh"
FRONTEND_SCRIPT="$ROOT_DIR/run-frontend.sh"
PREPARE_ONLY=0
CHECK_SHELL=0

while [ $# -gt 0 ]; do
  case "$1" in
    --prepare-only)
      PREPARE_ONLY=1
      shift
      ;;
    --check-shell)
      CHECK_SHELL=1
      shift
      ;;
    *)
      echo "[run-all] 不支持的参数: $1" >&2
      exit 1
      ;;
  esac
done

cleanup() {
  if [ -n "${BACKEND_PID:-}" ] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [ -n "${FRONTEND_PID:-}" ] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT INT TERM

if [ "$CHECK_SHELL" -eq 1 ]; then
  exit 0
fi

"$BACKEND_SCRIPT" --prepare-only

if [ "$PREPARE_ONLY" -eq 1 ]; then
  exit 0
fi

"$BACKEND_SCRIPT" &
BACKEND_PID=$!

"$FRONTEND_SCRIPT" &
FRONTEND_PID=$!

echo "Backend:  http://${BACKEND_HOST:-127.0.0.1}:${BACKEND_PORT:-8000}"
echo "Frontend: http://${FRONTEND_HOST:-127.0.0.1}:${FRONTEND_PORT:-5173}"
echo "Press Ctrl+C to stop both services."

wait "$BACKEND_PID" "$FRONTEND_PID"

