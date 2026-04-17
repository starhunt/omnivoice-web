#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"
exec .venv/bin/uvicorn app.main:app --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8320}"
