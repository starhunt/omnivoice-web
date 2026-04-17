# OmniVoice Web

단일 사용자 자체 호스팅 음성 합성 플랫폼. 브라우저 스튜디오 UI + REST API + ElevenLabs/OpenAI/Gemini 스타일 호환 API를 제공한다.

- **Web**: http://localhost:**5320**
- **API**: http://localhost:**8320** (OpenAPI: `/docs`)
- **엔진**: OmniVoice, Qwen3-TTS를 설치 상태에 따라 선택

상세 스펙은 [docs/PRD.md](./docs/PRD.md) 참조.

---

## 사전 요구사항

- Node 20+, pnpm 9+
- Python 3.11+
- (선택) ffmpeg — MP3 출력 시 필요 (`brew install ffmpeg`)
- (선택) OmniVoice 엔진 로컬 설치
- (선택) Qwen3-TTS 전용 Python 환경

OmniVoice와 Qwen3-TTS는 같은 Python 환경에 섞어 설치하지 않는 것을 권장한다. API 서버는 각 엔진을 subprocess로 호출하므로 엔진별 venv를 분리할 수 있다.

```text
/opt/engines/omnivoice/.venv
/opt/engines/qwen3-tts/.venv
```

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
- 엔진 감지: `curl http://localhost:8320/v1/engines -H "Authorization: Bearer dev-key-change-me"`
- OpenAPI 문서: http://localhost:8320/docs

## 환경변수 (`.env`)

| 키 | 기본값 | 설명 |
|----|--------|------|
| `TTS_DEFAULT_ENGINE` | `auto` | `auto` / `omnivoice` / `qwen3-tts` |
| `OMNIVOICE_ENGINE_PATH` | `/Users/.../OmniVoice` | 엔진 리포 루트 (sys.path 추가) |
| `OMNIVOICE_ENGINE_PYTHON` | `.../OmniVoice/.venv/bin/python` | 엔진 추론용 Python |
| `OMNIVOICE_DEVICE` | `mps` | `cpu` / `mps` / `cuda` |
| `QWEN3_TTS_ENABLED` | `true` | Qwen3-TTS 감지 활성화 |
| `QWEN3_TTS_BASE_URL` | 빈 값 | vLLM-Omni/OpenAI Speech API base URL. 설정하면 이 방식이 우선 |
| `QWEN3_TTS_API_KEY` | 빈 값 | Qwen3-TTS API에 Bearer 인증이 필요할 때 사용 |
| `QWEN3_TTS_PYTHON` | `/opt/engines/qwen3-tts/.venv/bin/python` | Qwen3-TTS 전용 Python |
| `QWEN3_TTS_MODEL` | `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` | Qwen custom voice 모델 |
| `QWEN3_TTS_CLONE_MODEL` | `Qwen/Qwen3-TTS-12Hz-1.7B-Base` | Qwen voice clone 모델 |
| `QWEN3_TTS_DESIGN_MODEL` | `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` | Qwen voice design 모델 |
| `QWEN3_TTS_DEVICE` | `cuda:0` | Qwen 실행 디바이스 |
| `QWEN3_TTS_DTYPE` | `bfloat16` | `bfloat16` / `float16` / `float32` |
| `QWEN3_TTS_ATTN_IMPLEMENTATION` | `flash_attention_2` | Qwen attention 구현 |
| `QWEN3_TTS_DEFAULT_SPEAKER` | `Sohee` | Qwen custom voice 기본 speaker |
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

# 엔진 감지
curl http://localhost:8320/v1/engines \
  -H "Authorization: Bearer dev-key-change-me"

# 오토 보이스 TTS (동기)
curl -X POST http://localhost:8320/v1/tts \
  -H "Authorization: Bearer dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "안녕하세요, OmniVoice 테스트입니다.",
    "language": "ko",
    "format": "wav",
    "engine": "auto",
    "params": { "num_step": 32, "guidance_scale": 2.0 }
  }'

# 비동기 TTS Job
curl -X POST http://localhost:8320/v1/jobs/tts \
  -H "Authorization: Bearer dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "비동기 합성 테스트입니다.",
    "language": "ko",
    "format": "wav",
    "engine": "auto",
    "params": { "num_step": 32, "guidance_scale": 2.0 }
  }'

# OpenAI Audio Speech 호환
curl -X POST http://localhost:8320/v1/audio/speech \
  -H "Authorization: Bearer dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tts-1",
    "voice": "Starhunter",
    "input": "OpenAI 호환 음성 생성 테스트입니다.",
    "response_format": "mp3"
  }' \
  -o speech.mp3

# ElevenLabs TTS 호환
curl -X POST "http://localhost:8320/v1/text-to-speech/<speaker_id>?output_format=mp3_44100_128" \
  -H "xi-api-key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "ElevenLabs 호환 음성 생성 테스트입니다.",
    "model_id": "eleven_multilingual_v2",
    "language_code": "ko"
  }' \
  -o eleven.mp3

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
│   │       └── qwen3_tts_cli.py # Qwen3-TTS 엔진 브리지 (Qwen 전용 venv에서 실행)
│   └── web/           # Next.js 15 프론트엔드 (포트 5320)
├── data/              # 런타임 생성물 (gitignored)
├── docs/PRD.md        # 제품 스펙
└── scripts/           # bootstrap.sh, dev.sh, dev-api.sh
```

## 기능 범위

구현 완료:

- TTS 스튜디오 (텍스트 + 화자 복제 + 보이스 디자인 + 오토 보이스)
- 엔진 선택 (`auto` / `omnivoice` / `qwen3-tts`)
- 화자 라이브러리 (업로드 / 메타 편집 / 즐겨찾기 / 소프트 삭제)
- 생성 히스토리 (검색 / 재생 / 페이징)
- 비동기 Job API (`/v1/jobs/tts`, `/v1/jobs/podcast`)
- 다중 화자 팟캐스트 Job
- 파라미터 제어 (num_step / guidance_scale / speed / denoise 등)
- 비언어 태그 13종 1클릭 삽입
- REST API + OpenAPI (`/docs`)
- API Key 인증 (Bearer 또는 X-API-Key 또는 xi-api-key)
- ElevenLabs 호환 API
- OpenAI Audio Speech 호환 API
- Gemini-style generateContent 호환 API
- OmniVoice 데모 기본 화자 import

남은 개선 과제:

- 배치 업로드 / Celery 큐
- true 실시간 스트리밍 (현재 `/stream` 경로는 batch 합성 후 오디오 반환)
- STT→TTS 캐스케이드
- 웹훅
- 관리자 콘솔
- i18n / 다중 API Key 발급 / 로그인
- Qwen3-TTS 실제 A100 smoke test 및 prompt cache 최적화

## 엔진 라우팅

`/v1/engines`는 설치된 엔진과 선택 결과를 반환한다.

```json
{
  "default_engine": "auto",
  "selected_engine": "omnivoice",
  "engines": [
    { "id": "omnivoice", "available": true, "mode": "live" },
    { "id": "qwen3-tts", "available": false, "reason": "QWEN3_TTS_PYTHON missing" }
  ]
}
```

`engine=auto` 선택 정책:

```text
1. 요청에 engine이 명시되면 해당 엔진 사용
2. engine=auto이면 TTS_DEFAULT_ENGINE 확인
3. 설치된 Qwen3-TTS가 있고 speaker가 OmniVoice prompt-only가 아니면 qwen3-tts 우선
4. 아니면 OmniVoice 사용
```

Qwen3-TTS는 두 형태를 지원한다.

- `QWEN3_TTS_BASE_URL` 설정: A100 서버의 `vllm-omni` 같은 OpenAI 호환 Speech API를 호출한다.
- `QWEN3_TTS_BASE_URL` 미설정: `QWEN3_TTS_PYTHON`으로 별도 Python 브리지를 실행한다.

A100에서 vLLM-Omni로 이미 떠 있는 경우:

```bash
curl http://A100_SERVER:8001/v1/models
curl http://A100_SERVER:8001/v1/audio/voices
```

`.env` 예:

```env
QWEN3_TTS_ENABLED=true
QWEN3_TTS_BASE_URL=http://A100_SERVER:8001
QWEN3_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice
QWEN3_TTS_DEFAULT_SPEAKER=sohee
```

Python 브리지 방식으로 설치한 경우:

```bash
$QWEN3_TTS_PYTHON apps/api/scripts/qwen3_tts_cli.py --health
```

## 트러블슈팅

| 증상 | 원인 / 조치 |
|------|------------|
| `engine_path_exists: false` | `.env`의 `OMNIVOICE_ENGINE_PATH` 확인 |
| `/v1/engines`에서 `qwen3-tts.available=false` | `QWEN3_TTS_BASE_URL`의 `/health` 또는 `QWEN3_TTS_PYTHON` 경로 확인 |
| `qwen3_tts_unavailable` | Qwen CLI 또는 venv가 없거나 `QWEN3_TTS_ENABLED=false` |
| `qwen3_tts_requires_speaker_ref_audio` | Python 브리지 방식에서 OmniVoice prompt-only 화자를 직접 사용할 수 없음. `source_audio_path`가 있는 화자 사용 |
| `engine_timeout` | 장문 생성 시 기본 900s 타임아웃. `OMNIVOICE_TIMEOUT_SEC` 환경변수로 연장 |
| MP3 포맷 요청 시 `ffmpeg_not_found` | `brew install ffmpeg` 또는 WAV 사용 |
| 401 `invalid_api_key` | Authorization 헤더의 Bearer 토큰이 `.env`의 `OMNIVOICE_API_KEY`와 일치하는지 확인 |

## 라이선스

- 본 프로젝트: MIT (TBD)
- OmniVoice 엔진: 해당 프로젝트 라이선스/NOTICE 준수
- Qwen3-TTS: 해당 프로젝트 라이선스/NOTICE 준수
