# A100 Qwen3-TTS vLLM-Omni 검증 기록

날짜: 2026-04-18

## 확인 대상

SSH 대상:

```bash
ssh -p 12022 jnuadmin@168.131.216.36
```

서버:

```text
hostname: gpu07
GPU: NVIDIA A100 80GB PCIe
```

Docker 컨테이너:

```text
name: qwen3-tts
image: vllm/vllm-omni:v0.18.0
port: 0.0.0.0:8001 -> 8091/tcp
status: healthy
model: Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice
```

## 실제 API 형태

현재 A100의 Qwen3-TTS는 `qwen_tts` Python 패키지를 직접 import하는 형태가 아니라 `vllm-omni`의 OpenAI 호환 Speech API로 떠 있다.

사용 가능한 주요 엔드포인트:

```text
GET  /health
GET  /v1/models
GET  /v1/audio/voices
POST /v1/audio/speech
```

voice 목록:

```json
{
  "voices": ["aiden", "dylan", "eric", "ono_anna", "ryan", "serena", "sohee", "uncle_fu", "vivian"],
  "uploaded_voices": []
}
```

## 직접 합성 테스트

요청:

```bash
curl -X POST http://127.0.0.1:8001/v1/audio/speech \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "input": "안녕하세요. Qwen3 TTS 서버에서 한국어 음성 합성 테스트를 진행합니다.",
    "voice": "sohee",
    "response_format": "wav"
  }' \
  --output /tmp/qwen3_tts_test.wav
```

결과:

```text
HTTP 200
content-type: audio/wav
size: 314,924 bytes
format: RIFF WAVE, PCM 16-bit, mono, 24000 Hz
duration: 6.56 sec
```

## 프로젝트 API 연동 검증

이번 수정으로 `QWEN3_TTS_BASE_URL`을 설정하면 Python CLI 대신 vLLM-Omni API를 우선 사용한다.

검증 환경:

```env
QWEN3_TTS_BASE_URL=http://168.131.216.36:8001
API_PORT=8331
```

`/v1/engines` 결과:

```text
selected_engine: qwen3-tts
qwen3-tts.available: true
qwen3-tts.mode: live
qwen3-tts.path: http://168.131.216.36:8001
```

`/v1/tts` 결과:

```text
engine: qwen3-tts
status: succeeded
duration_sec: 4.16
audio_url: /v1/assets/8deabcd1867a4ec9baa4ab8e1df4c7a9.wav
rtf: 0.227
```

## 결론

A100 서버의 Qwen3-TTS 자체는 정상 동작한다. 문제는 설치 형태가 Python 패키지 직접 실행이 아니라 `vllm-omni` API 서버였다는 점이다. 따라서 프로젝트는 다음 두 방식을 모두 지원하도록 수정했다.

1. `QWEN3_TTS_BASE_URL`이 있으면 OpenAI 호환 Speech API로 합성한다.
2. `QWEN3_TTS_BASE_URL`이 없으면 기존 `QWEN3_TTS_PYTHON` CLI 브리지를 사용한다.

운영 서버에서 Qwen3-TTS를 붙일 때는 다음 설정이 우선 권장된다.

```env
TTS_DEFAULT_ENGINE=auto
QWEN3_TTS_ENABLED=true
QWEN3_TTS_BASE_URL=http://127.0.0.1:8001
QWEN3_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice
QWEN3_TTS_DEFAULT_SPEAKER=sohee
```
