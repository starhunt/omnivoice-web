#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# .env 자동 로드
if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

API_PORT="${API_PORT:-8320}"
WEB_PORT=5320

cleanup() {
  echo ""
  echo "==> 종료 신호 수신, 자식 프로세스 종료"
  kill 0 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "==> API: http://localhost:${API_PORT}"
(
  cd apps/api
  ./.venv/bin/uvicorn app.main:app --host "${API_HOST:-127.0.0.1}" --port "${API_PORT}" --reload
) &

echo "==> Web: http://localhost:${WEB_PORT}"
(
  cd apps/web
  PORT="${WEB_PORT}" pnpm dev
) &

wait
