# Qwen3-TTS CustomVoice 1.7B + Base 0.6B 라우팅

작성일: 2026-04-18

## 결론

Qwen3-TTS를 하나의 API에서 다음처럼 분리해 사용하도록 정리했다.

- `voice_id` 요청: `QWEN3_TTS_BASE_URL`의 CustomVoice 1.7B 서버로 전송
- `speaker_id` 요청: `QWEN3_TTS_CLONE_BASE_URL`의 Base 0.6B 서버로 전송
- 팟캐스트 segment는 `voice_id`와 `speaker_id`를 섞어서 사용할 수 있음
- Studio 화면은 Qwen 엔진 선택 시 기본 Voice와 등록 화자 복제를 별도로 선택할 수 있음

이 구조에서는 CustomVoice 1.7B가 제공하는 기본 voice 목록을 유지하면서, 등록된 참조음성 복제는 Base 0.6B로 처리한다. OmniVoice의 `.pt` prompt-only 화자는 Qwen clone에 직접 사용할 수 없고, `source_audio_path`가 있는 등록 화자만 Qwen clone 대상으로 사용한다.

## 환경변수

```env
QWEN3_TTS_ENABLED=true
QWEN3_TTS_BASE_URL=http://A100_SERVER:8001
QWEN3_TTS_CLONE_BASE_URL=http://A100_SERVER:8002
QWEN3_TTS_MODEL=Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice
QWEN3_TTS_CLONE_MODEL=Qwen/Qwen3-TTS-12Hz-0.6B-Base
QWEN3_TTS_DEFAULT_SPEAKER=sohee
```

## A100 배치

확인한 A100 배치:

- CustomVoice 1.7B: `qwen3-tts`, `http://127.0.0.1:8001`
- Base 0.6B: `qwen3-tts-base`, `http://127.0.0.1:8002`
- 두 컨테이너 모두 `vllm/vllm-omni:v0.18.0` 이미지 사용

0.6B Base는 기본 stage config의 메모리 예약이 커서 동시에 올릴 때 실패할 수 있었다. A100 80GB에서 CustomVoice 1.7B와 함께 구동하기 위해 Base stage config의 `gpu_memory_utilization`을 `0.18`로 낮춘 별도 config를 사용했다.

동시 구동 확인 시 VRAM 사용량은 약 57GB였고, 약 23GB 여유가 남았다. TEI embedding 컨테이너까지 함께 떠 있는 상태였다.

## API 동작

단일 TTS:

```json
{
  "engine": "qwen3-tts",
  "voice_id": "sohee",
  "text": "기본 voice 합성",
  "format": "mp3"
}
```

위 요청은 CustomVoice 1.7B 서버로 간다.

```json
{
  "engine": "qwen3-tts",
  "speaker_id": "6c160441dced4f4ca59ca8bd0c588edb",
  "text": "등록 화자 복제 합성",
  "format": "mp3"
}
```

위 요청은 등록 화자의 `source_audio_path`와 `ref_transcript`를 Base 0.6B 서버의 `/v1/audio/speech`로 전송한다. `ref_transcript`가 있으면 `ref_text`를 함께 보내고, 없으면 `x_vector_only_mode=true`로 보낸다.

팟캐스트:

```json
{
  "engine": "qwen3-tts",
  "segments": [
    { "label": "HOST", "voice_id": "sohee", "text": "기본 voice 발화" },
    { "label": "GUEST", "speaker_id": "6c160441dced4f4ca59ca8bd0c588edb", "text": "등록 화자 복제 발화" }
  ]
}
```

segment마다 `voice_id` 또는 `speaker_id`를 선택할 수 있다.

## 검증 결과

로컬 API에서 다음을 확인했다.

- `/v1/engines`: `qwen3-tts.available=true`, `supports_voice_clone=true`
- Qwen `voice_id=sohee` 단일 TTS: 성공
- Qwen `speaker_id=Starhunter` 단일 TTS: 성공
- Qwen 팟캐스트에서 `HOST=sohee`, `GUEST=Starhunter speaker_id` 혼합 job: 성공

직접 A100 엔드포인트 검증:

- `http://168.131.216.36:8001/v1/audio/speech` CustomVoice 1.7B 기본 voice: 성공
- `http://168.131.216.36:8002/v1/audio/speech` Base 0.6B 참조음성 복제: 성공

## 주의점

- `QWEN3_TTS_CLONE_BASE_URL`이 없는데 Qwen `speaker_id` 합성을 요청하면 `qwen3_tts_clone_base_url_required`가 발생한다.
- Qwen clone은 참조 오디오 파일이 필요하다. OmniVoice prompt-only 화자는 `qwen3_tts_requires_speaker_ref_audio`로 막는다.
- MP3 응답은 vLLM-Omni가 직접 반환할 수 있으므로 duration은 일부 경로에서 `0.0`으로 기록될 수 있다. WAV는 `wave`로 duration을 계산한다.
