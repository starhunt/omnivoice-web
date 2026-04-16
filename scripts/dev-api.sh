#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

cd apps/api
exec ./.venv/bin/uvicorn app.main:app \
  --host "${API_HOST:-127.0.0.1}" \
  --port "${API_PORT:-8320}" \
  --reload
