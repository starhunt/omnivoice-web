# 엔진 라우터 및 Qwen3-TTS 통합 기반

**작성일**: 2026-04-17  
**상태**: OmniVoice-only 환경 검증 완료, Qwen3-TTS subprocess CLI 골격 추가

---

## 1. 목적

하나의 OmniVoice-Web API 서버가 다음 설치 조합을 모두 커버하도록 기반을 추가했다.

```text
OmniVoice만 설치됨
Qwen3-TTS만 설치됨
OmniVoice + Qwen3-TTS 둘 다 설치됨
```

상위 API는 그대로 유지한다.

```text
/v1/tts
/v1/jobs/tts
/v1/jobs/podcast
/v1/audio/speech
/v1/text-to-speech/{voice_id}
/v1/text-to-dialogue
/v1beta/models/{model}:generateContent
```

요청 내부에 `engine`을 추가해 실제 엔진만 선택하도록 했다.

```json
{
  "engine": "auto"
}
```

지원 값:

```text
auto
omnivoice
qwen3-tts
```

---

## 2. 설정값

`.env.example`에 다음 항목을 추가했다.

```env
TTS_DEFAULT_ENGINE=auto

QWEN3_TTS_ENABLED=true
QWEN3_TTS_BASE_URL=
QWEN3_TTS_API_KEY=
QWEN3_TTS_PYTHON=/opt/engines/qwen3-tts/.venv/bin/python
QWEN3_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice
QWEN3_TTS_CLONE_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-Base
QWEN3_TTS_DESIGN_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign
QWEN3_TTS_DEVICE=cuda:0
QWEN3_TTS_DTYPE=bfloat16
QWEN3_TTS_ATTN_IMPLEMENTATION=flash_attention_2
QWEN3_TTS_DEFAULT_SPEAKER=Sohee
```

Qwen3-TTS는 두 설치 형태를 지원한다.

1. `QWEN3_TTS_BASE_URL`을 설정해 vLLM-Omni/OpenAI Speech API를 호출한다.
2. `QWEN3_TTS_BASE_URL`을 비워두고 별도 venv의 Python 브리지를 실행한다.

Python 브리지 방식에서는 OmniVoice와 같은 Python 환경에 설치하지 않고 별도 venv로 격리한다.

```text
/opt/engines/omnivoice/.venv
/opt/engines/qwen3-tts/.venv
```

---

## 3. 엔진 감지 API

추가 endpoint:

```text
GET /v1/engines
```

현재 로컬 검증 결과:

```json
{
  "default_engine": "auto",
  "selected_engine": "omnivoice",
  "engines": [
    {
      "id": "omnivoice",
      "available": true,
      "mode": "live"
    },
    {
      "id": "qwen3-tts",
      "available": false,
      "mode": "stub",
      "reason": "QWEN3_TTS_PYTHON missing"
    }
  ]
}
```

현재 로컬은 OmniVoice만 설치된 상태이므로 `auto`는 `omnivoice`로 해석된다.

---

## 4. Qwen3-TTS subprocess CLI

추가 파일:

```text
apps/api/scripts/qwen3_tts_cli.py
```

이 CLI는 FastAPI 서버와 다른 Python venv에서 실행된다.

Health check:

```bash
/opt/engines/qwen3-tts/.venv/bin/python apps/api/scripts/qwen3_tts_cli.py --health
```

합성 payload 예:

```json
{
  "mode": "custom_voice",
  "model": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
  "text": "안녕하세요. 큐웬 티티에스 테스트입니다.",
  "language": "Korean",
  "speaker": "Sohee",
  "out_path": "/tmp/qwen_smoke.wav",
  "device_map": "cuda:0",
  "dtype": "bfloat16",
  "attn_implementation": "flash_attention_2"
}
```

voice clone payload 예:

```json
{
  "mode": "voice_clone",
  "model": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
  "text": "안녕하세요. 이 목소리로 합성합니다.",
  "language": "Korean",
  "ref_audio_path": "/data/speakers/id/ref.wav",
  "ref_text": "참조 음성의 정확한 문장",
  "out_path": "/tmp/qwen_clone.wav"
}
```

`ref_text`가 없으면 `x_vector_only_mode=true`로 넘기지만, 품질은 정확한 ref transcript가 있을 때가 더 안정적이다.

---

## 5. Auto 선택 정책

현재 정책:

```text
1. 요청에 engine이 명시되면 해당 엔진 사용
2. engine=auto이면 TTS_DEFAULT_ENGINE 확인
3. 설치된 Qwen3-TTS가 있고 speaker가 OmniVoice prompt-only가 아니면 qwen3-tts 우선
4. 아니면 OmniVoice 사용
5. 둘 다 없으면 OmniVoice stub/failure 경로
```

중요한 예외:

```text
source_audio_path 없이 OmniVoice prompt_blob_path만 있는 화자는 Qwen3-TTS에서 사용할 수 없다.
```

이런 화자는 `engine=auto`에서도 OmniVoice로 라우팅한다.

---

## 6. 현재 검증

### 6.1 문법/타입

```text
apps/api/.venv/bin/python -m py_compile ...
OK

pnpm --filter @omnivoice/web typecheck
OK
```

### 6.2 엔진 감지

```text
GET /v1/engines
status: 200
selected_engine: omnivoice
qwen3-tts reason: QWEN3_TTS_PYTHON missing
```

### 6.3 기존 합성 경로

```text
POST /v1/jobs/tts
engine: auto
status: succeeded
duration: 3.04s
size: 145,964 bytes
```

### 6.4 Studio

```text
GET /studio
status: 200
```

---

## 7. A100 서버에서 다음 확인 순서

1. Qwen3-TTS 전용 venv 설치

```bash
conda create -n qwen3-tts python=3.12 -y
conda activate qwen3-tts
pip install -U qwen-tts
pip install -U flash-attn --no-build-isolation
```

2. `.env` 설정

```env
TTS_DEFAULT_ENGINE=auto
QWEN3_TTS_PYTHON=/opt/engines/qwen3-tts/.venv/bin/python
QWEN3_TTS_DEVICE=cuda:0
```

3. CLI health

```bash
$QWEN3_TTS_PYTHON apps/api/scripts/qwen3_tts_cli.py --health
```

4. API health

```bash
curl http://A100_SERVER:8320/v1/engines \
  -H "Authorization: Bearer $OMNIVOICE_API_KEY"
```

5. 짧은 TTS

```json
{
  "engine": "qwen3-tts",
  "text": "안녕하세요. 큐웬 티티에스 테스트입니다.",
  "language": "ko",
  "format": "wav"
}
```

---

## 8. 남은 과제

- Qwen3-TTS가 실제 설치된 A100에서 smoke test.
- Qwen3-TTS model variant별 함수명/파라미터가 현재 CLI와 일치하는지 검증.
- Qwen voice clone prompt/cache 최적화.
- 엔진별 speaker prompt cache 테이블 분리.
- 실패 시 fallback engine 옵션.

---

## 9. 한 줄 요약

이제 API 서버 하나에서 설치된 TTS 엔진을 감지하고 `engine=auto|omnivoice|qwen3-tts`로 라우팅할 수 있는 기반이 생겼다. 현재 로컬은 OmniVoice-only로 정상 동작하며, A100 서버의 Qwen3-TTS는 별도 venv 경로만 설정하면 `/v1/engines`와 CLI로 우선 검증할 수 있다.
