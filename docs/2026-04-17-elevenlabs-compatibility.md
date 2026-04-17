# ElevenLabs 호환 API 및 경쟁력 개선 방향

**작성일**: 2026-04-17  
**상태**: MVP 호환 레이어 구현 및 로컬 검증 완료  
**추가 업데이트**: OpenAI TTS 호환, ElevenLabs Dialogue, Gemini-style multi-speaker, SSML-lite 추가

---

## 1. 결론

현재 OmniVoice-Web의 네이티브 API 주소만 ElevenLabs API 주소 대신 넣는 방식으로는 일반 ElevenLabs 호환 클라이언트가 바로 동작하지 않는다.

이유:

- ElevenLabs는 `xi-api-key` 헤더를 사용한다.
- 대표 TTS 경로가 `/v1/text-to-speech/{voice_id}`이다.
- 응답이 JSON 메타데이터가 아니라 오디오 바이트 자체이다.
- 화자 목록도 `/v1/voices` 또는 `/v2/voices` 형태를 기대한다.

따라서 별도 compatibility shim이 필요하며, 이번 작업에서 최소 호환 레이어를 추가했다.

---

## 2. 구현된 호환 범위

### 2.1 인증

기존:

```text
Authorization: Bearer <key>
X-API-Key: <key>
```

추가:

```text
xi-api-key: <key>
x-goog-api-key: <key>
```

수정 파일:

```text
apps/api/app/auth.py
```

### 2.2 화자 목록

```text
GET /v1/voices
GET /v2/voices
GET /v1/voices/{voice_id}
```

OmniVoice-Web의 `Speaker`를 ElevenLabs의 `voice` 형태로 변환한다.

주요 매핑:

```text
Speaker.id              -> voice_id
Speaker.name            -> name
Speaker.source_audio    -> preview_url
Speaker.tags            -> labels
Speaker.note            -> description
```

### 2.3 모델 목록

```text
GET /v1/models
```

일반 ElevenLabs 클라이언트가 모델 목록을 조회할 때 깨지지 않도록 다음 model_id를 반환한다.

```text
eleven_multilingual_v2
eleven_flash_v2_5
eleven_v3
```

실제 내부 엔진은 모두 로컬 OmniVoice로 매핑된다.

### 2.4 TTS

```text
POST /v1/text-to-speech/{voice_id}
POST /v1/text-to-speech/{voice_id}/stream
```

요청 예:

```bash
curl -X POST "http://127.0.0.1:8320/v1/text-to-speech/SPEAKER_ID?output_format=mp3_44100_128" \
  -H "xi-api-key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "일레븐랩스 호환 API 테스트입니다.",
    "model_id": "eleven_multilingual_v2",
    "language_code": "ko",
    "voice_settings": { "speed": 1.0 }
  }' \
  -o out.mp3
```

응답:

```text
HTTP 200
content-type: audio/mpeg
request-id: <generation_id>
x-request-id: <generation_id>
x-character-count: <text length>
body: audio bytes
```

현재 `/stream` 경로는 경로 호환용이다. 내부 OmniVoice 엔진이 batch 합성 구조이므로 true chunk streaming은 아니고, 합성이 완료된 뒤 오디오 바이트를 반환한다.

### 2.5 ElevenLabs Dialogue

```text
POST /v1/text-to-dialogue
POST /v1/text-to-dialogue/stream
```

요청 예:

```bash
curl -X POST "http://127.0.0.1:8320/v1/text-to-dialogue?output_format=mp3_44100_128" \
  -H "xi-api-key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "eleven_v3",
    "language_code": "ko",
    "inputs": [
      { "voice_id": "6c160441dced4f4ca59ca8bd0c588edb", "text": "안녕하세요. 저는 진행자입니다." },
      { "voice_id": "2540d7bd58ab4982bc944ff789ae396d", "text": "반갑습니다. 저는 게스트입니다." }
    ]
  }' \
  -o dialogue.mp3
```

내부적으로 `inputs[]`를 `PodcastJobRequest.segments[]`로 변환한 뒤 segment별 합성, silence 삽입, ffmpeg concat을 수행한다.

### 2.6 OpenAI Audio Speech 호환

```text
POST /v1/audio/speech
```

요청 예:

```bash
curl -X POST http://127.0.0.1:8320/v1/audio/speech \
  -H "Authorization: Bearer dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "tts-1",
    "voice": "Starhunter",
    "input": "OpenAI 호환 음성 생성 테스트입니다.",
    "response_format": "mp3",
    "speed": 1.0
  }' \
  -o speech.mp3
```

매핑:

```text
voice            -> Speaker.id 또는 Speaker.name
input            -> text
response_format  -> mp3 | wav
speed            -> TTSParams.speed
```

`input`에 SSML-lite를 넣으면 `<voice name="...">` 단위로 다중 화자 podcast 합성 경로를 사용한다.

```xml
<speak>
  <voice name="Starhunter">안녕하세요. 진행자입니다.</voice>
  <break time="300ms"/>
  <voice name="OmniVoice Korean Demo KR">네. 게스트입니다.</voice>
</speak>
```

현재 `<break>`의 개별 길이는 정밀 반영하지 않고 segment 사이 기본 pause로 처리한다.

### 2.7 Gemini-style generateContent 호환

```text
POST /v1beta/models/{model}:generateContent
```

요청 예:

```bash
curl -X POST "http://127.0.0.1:8320/v1beta/models/gemini-2.5-flash-preview-tts:generateContent" \
  -H "x-goog-api-key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "contents": "Joe: 안녕하세요.\nJane: 네, 반갑습니다.",
    "config": {
      "responseModalities": ["AUDIO"],
      "speechConfig": {
        "multiSpeakerVoiceConfig": {
          "speakerVoiceConfigs": [
            { "speaker": "Joe", "voiceConfig": { "prebuiltVoiceConfig": { "voiceName": "Starhunter" } } },
            { "speaker": "Jane", "voiceConfig": { "prebuiltVoiceConfig": { "voiceName": "OmniVoice Korean Demo KR" } } }
          ]
        }
      }
    }
  }'
```

응답은 Gemini 스타일로 `candidates[0].content.parts[0].inlineData.data`에 base64 WAV를 넣어 반환한다.

```text
inlineData.mimeType: audio/wav
inlineData.data: base64 encoded wav
```

---

## 3. 검증 결과

### 3.1 화자 목록

```bash
curl http://127.0.0.1:8320/v1/voices \
  -H "xi-api-key: dev-key-change-me"
```

결과:

```text
200 OK
voices: Starhunter, OmniVoice Korean Demo, OmniVoice Korean Demo KR
```

### 3.2 모델 목록

```bash
curl http://127.0.0.1:8320/v1/models \
  -H "xi-api-key: dev-key-change-me"
```

결과:

```text
200 OK
model_id: eleven_multilingual_v2, eleven_flash_v2_5, eleven_v3
```

### 3.3 TTS 오디오 응답

```text
endpoint: POST /v1/text-to-speech/2540d7bd58ab4982bc944ff789ae396d
status: 200
content-type: audio/mpeg
duration: 3.08s
size: 63,404 bytes
```

### 3.4 OpenAI Audio Speech

```text
endpoint: POST /v1/audio/speech
status: 200
content-type: audio/mpeg
duration: 3.12s
size: 63,884 bytes
```

### 3.5 ElevenLabs Dialogue

```text
endpoint: POST /v1/text-to-dialogue
status: 200
content-type: audio/mpeg
duration: 5.57s
size: 113,324 bytes
```

### 3.6 Gemini-style generateContent

```text
endpoint: POST /v1beta/models/gemini-2.5-flash-preview-tts:generateContent
status: 200
inlineData.mimeType: audio/wav
decoded wav header: RIFF
duration: 9.54s
size: 457,998 bytes
```

### 3.7 SSML-lite

```text
endpoint: POST /v1/audio/speech
input: <speak><voice name="Starhunter">...</voice><voice name="OmniVoice Korean Demo KR">...</voice></speak>
status: 200
content-type: audio/wav
duration: 6.35s
size: 304,878 bytes
```

---

## 4. 일반 ElevenLabs 호환 사이트에서의 사용 가능성

가능한 경우:

- 사용자가 API Base URL을 직접 지정할 수 있다.
- API key 헤더가 `xi-api-key`로 전송된다.
- 기본 기능이 voice list + text-to-speech 중심이다.
- 응답 오디오 바이트를 그대로 재생하거나 저장한다.

실패할 수 있는 경우:

- WebSocket 실시간 입력 스트리밍을 요구한다.
- true chunk streaming 응답을 요구한다. `/v1/text-to-dialogue/stream` 경로는 지원하지만 현재는 batch 합성 후 오디오를 반환한다.
- pronunciation dictionary, history, user subscription, usage, dubbing, agents 등 ElevenLabs 전용 API를 요구한다.
- 낮은 지연시간의 chunk streaming을 전제로 구현되어 있다.

OpenAI TTS 호환 클라이언트는 `/v1/audio/speech`와 `Authorization: Bearer`만 사용한다면 붙을 가능성이 높다. 다만 `response_format=opus/flac/aac/pcm`처럼 현재 미지원 포맷을 요구하면 실패한다.

Gemini SDK 호환은 제한적이다. HTTP 경로와 응답 형태는 맞췄지만, 실제 Google SDK가 요구하는 세부 transport, query key, typed response 전체를 100% 복제한 것은 아니다. 직접 REST 호출 또는 base URL 커스터마이즈 가능한 클라이언트에서 우선 사용한다.

---

## 5. ElevenLabs 대비 경쟁력 강화 방향

### 5.1 단기

- ElevenLabs 호환 endpoint 확대:
  - `GET /v1/user/subscription`
  - `GET /v1/history`
- OpenAI 호환 확대:
  - `GET /v1/models` OpenAI model object 형태 옵션
  - `response_format=opus/flac/pcm` 변환
- Gemini 호환 확대:
  - `/v1/models/{model}:generateContent`
  - voiceName 프리셋과 로컬 speaker preset 매핑 관리
- 외부 클라이언트용 “호환 모드” 문서와 샘플 제공.
- 긴 텍스트 자동 chunking, 실패 chunk 재시도, 이어붙이기 품질 개선.
- 기본 화자 프리셋 확장.

### 5.2 중기

- A100 서버용 배포 패키지:
  - Dockerfile
  - systemd unit
  - persistent worker
  - Redis/RQ 또는 Celery queue
- true streaming에 가까운 chunk-first 응답 구조.
- podcast script parser 고도화:
  - `HOST:`, `GUEST:` 라벨 자동 인식
  - Markdown 대본 파싱
  - LLM으로 대본을 발화 단위로 자동 정리
- loudness normalization, silence trimming, segment crossfade.

### 5.3 차별화 포인트

- 로컬/자가호스팅 가능.
- 자체 화자 데이터와 생성 이력 통제 가능.
- 장문 팟캐스트와 다중 화자 생성에 특화 가능.
- A100 서버를 붙이면 비용 구조를 ElevenLabs 종량제와 다르게 가져갈 수 있다.

---

## 6. 한 줄 요약

이제 단순히 기존 OmniVoice-Web API 주소를 바꾸는 수준은 아니지만, ElevenLabs 호환 endpoint가 추가되어 `voices` 조회와 `text-to-speech` 중심의 일반 클라이언트는 base URL/API key/voice_id 변경만으로 붙을 가능성이 높아졌다.
