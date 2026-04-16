#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> 1/4 .env 생성"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "    .env 생성 완료 — 필요 시 편집하세요."
else
  echo "    .env 이미 존재 — 스킵"
fi

echo "==> 2/4 data 디렉토리"
mkdir -p data/audio data/speakers data/uploads
echo "    data/{audio,speakers,uploads} 준비 완료"

echo "==> 3/4 API 가상환경 (.venv)"
cd apps/api
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip
  ./.venv/bin/pip install -e .
  echo "    .venv 생성 및 의존성 설치 완료"
else
  echo "    .venv 이미 존재 — 스킵"
fi
cd "$ROOT"

echo "==> 4/4 Web 의존성"
cd apps/web
if [[ ! -d node_modules ]]; then
  pnpm install
else
  echo "    node_modules 이미 존재 — 스킵"
fi
cd "$ROOT"

echo ""
echo "✅ Bootstrap 완료."
echo ""
echo "다음: ./scripts/dev.sh 로 api + web 동시 기동"
