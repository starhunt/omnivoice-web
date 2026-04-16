# OmniVoice Web

OmniVoice 엔진을 래핑한 단일 사용자 자체 호스팅 음성 합성 플랫폼. 브라우저 스튜디오 UI + REST API.

- **Web**: http://localhost:**5320**
- **API**: http://localhost:**8320** (OpenAPI: `/docs`)
- **엔진**: [OmniVoice](https://github.com/k2-fsa/OmniVoice) (Apache 2.0)

상세 스펙은 [docs/PRD.md](./docs/PRD.md) 참조.

---

## 사전 요구사항

- Node 20+, pnpm 9+
- Python 3.11+
- (선택) ffmpeg — MP3 출력 시 필요 (`brew install ffmpeg`)
- OmniVoice 엔진 로컬 설치 (선택 — 없으면 stub 모드로 동작)

## 빠른 시작

```bash
# 1) 환경 부트스트랩 (.env 생성, API venv 구성, web deps 설치)
pnpm bootstrap         # 또는 bash scripts/bootstrap.sh

# 2) .env 편집 — 엔진 경로, API 키 등 확인
$EDITOR .env

# 3) 개발 모드 기동 (api + web 동시)
pnpm dev               # 또는 bash scripts/dev.sh
```

기동 후:

- 브라우저: http://localhost:5320
- API 헬스: `curl http://localhost:8320/v1/health -H "Authorization: Bearer dev-key-change-me"`
- OpenAPI 문서: http://localhost:8320/docs

## 환경변수 (`.env`)

| 키 | 기본값 | 설명 |
|----|--------|------|
| `OMNIVOICE_ENGINE_PATH` | `/Users/.../OmniVoice` | 엔진 리포 루트 (sys.path 추가) |
| `OMNIVOICE_ENGINE_PYTHON` | `.../OmniVoice/.venv/bin/python` | 엔진 추론용 Python |
| `OMNIVOICE_DEVICE` | `mps` | `cpu` / `mps` / `cuda` |
| `OMNIVOICE_API_KEY` | `dev-key-change-me` | 단일 API Key (Bearer) |
| `API_HOST` / `API_PORT` | `127.0.0.1` / `8320` | FastAPI 바인딩 |
| `DATABASE_URL` | `sqlite:///./data/app.db` | SQLite 경로 |
| `DATA_DIR` | `./data` | 오디오/화자/업로드 루트 |
| `CORS_ORIGINS` | `http://localhost:5320` | 쉼표 구분 |
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8320` | Web→API 엔드포인트 |
| `NEXT_PUBLIC_API_KEY` | `dev-key-change-me` | Web에서 API 호출 시 사용 |

## 사용 예 (cURL)

```bash
# 헬스체크
curl http://localhost:8320/v1/health \
  -H "Authorization: Bearer dev-key-change-me"

# 오토 보이스 TTS (동기)
curl -X POST http://localhost:8320/v1/tts \
  -H "Authorization: Bearer dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "안녕하세요, OmniVoice 테스트입니다.",
    "language": "ko",
    "format": "wav",
    "params": { "num_step": 32, "guidance_scale": 2.0 }
  }'

# 오디오 다운로드
curl http://localhost:8320/v1/assets/<generation_id>.wav -o out.wav
```

## 디렉토리 구조

```
omnivoice-web/
├── apps/
│   ├── api/           # FastAPI 백엔드 (포트 8320)
│   │   ├── app/       # 애플리케이션 코드
│   │   └── scripts/
│   │       └── engine_cli.py   # OmniVoice 엔진 브리지 (엔진 .venv에서 실행)
│   └── web/           # Next.js 15 프론트엔드 (포트 5320)
├── data/              # 런타임 생성물 (gitignored)
├── docs/PRD.md        # 제품 스펙
└── scripts/           # bootstrap.sh, dev.sh, dev-api.sh
```

## 기능 범위 (Phase 1 MVP)

구현 완료:

- TTS 스튜디오 (텍스트 + 화자 복제 + 보이스 디자인 + 오토 보이스)
- 화자 라이브러리 (업로드 / 메타 편집 / 즐겨찾기 / 소프트 삭제)
- 생성 히스토리 (검색 / 재생)
- 파라미터 제어 (num_step / guidance_scale / speed / denoise 등)
- 비언어 태그 13종 1클릭 삽입
- REST API + OpenAPI (`/docs`)
- API Key 인증 (Bearer 또는 X-API-Key)

MVP 제외 (Phase 2 이후):

- 배치 업로드 / Celery 큐
- 실시간 스트리밍 (청크 단위 전송)
- STT→TTS 캐스케이드
- 웹훅
- 관리자 콘솔
- i18n / 다중 API Key 발급 / 로그인

## 엔진 모드

`/v1/health` 응답의 `engine.mode`가 두 가지 상태를 가진다:

- **`live`** — `OMNIVOICE_ENGINE_PATH` + `OMNIVOICE_ENGINE_PYTHON` + 브리지 스크립트가 모두 존재하여 실제 합성이 가능.
- **`stub`** — 환경이 없을 때. API 계층은 모두 동작하며 무음 사인파 WAV가 생성됨 (UI/통합 검증용).

## 트러블슈팅

| 증상 | 원인 / 조치 |
|------|------------|
| `engine_path_exists: false` | `.env`의 `OMNIVOICE_ENGINE_PATH` 확인 |
| `engine_timeout` | 장문 생성 시 기본 900s 타임아웃. `OMNIVOICE_TIMEOUT_SEC` 환경변수로 연장 |
| MP3 포맷 요청 시 `ffmpeg_not_found` | `brew install ffmpeg` 또는 WAV 사용 |
| 401 `invalid_api_key` | Authorization 헤더의 Bearer 토큰이 `.env`의 `OMNIVOICE_API_KEY`와 일치하는지 확인 |

## 라이선스

- 본 프로젝트: MIT (TBD)
- OmniVoice 엔진: Apache 2.0 (별도 NOTICE 준수)
