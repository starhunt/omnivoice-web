# 비동기 Job API 및 다중 화자 Podcast API 구현 내역

**작성일**: 2026-04-17  
**대상**: OmniVoice Web API, 장문 TTS, 다중 화자 팟캐스트 생성  
**상태**: MVP 구현 및 로컬 검증 완료

---

## 1. 목적

기존 `/v1/tts`는 동기 API라서 장문 합성이나 다중 화자 팟캐스트처럼 오래 걸리는 작업에 적합하지 않았다. 브라우저, Next.js dev proxy, 원격 서버 프록시, 로드밸런서 timeout에 영향을 받기 때문이다.

이번 작업은 다음 구조를 추가하는 것이 목적이다.

```text
POST /v1/jobs/tts
POST /v1/jobs/podcast
        |
        v
즉시 job_id 반환
        |
        v
백그라운드 worker에서 합성
        |
        v
GET /v1/jobs/{job_id} 로 상태/진행률 확인
        |
        v
완료 후 /v1/assets/{generation_id}.wav 재생/다운로드
```

---

## 2. 수정된 파일

### 2.1 `apps/api/app/models.py`

`Job` ORM 모델 추가.

주요 필드:

```text
id
type: tts | podcast
status: queued | running | succeeded | failed
generation_id
request_json
progress_current
progress_total
progress_message
error
created_at
started_at
finished_at
```

`init_db()`의 `Base.metadata.create_all()`로 `jobs` 테이블이 생성된다.

### 2.2 `apps/api/app/schemas.py`

추가된 스키마:

```text
JobProgress
JobOut
JobCreateResponse
PodcastSegment
PodcastJobRequest
```

`JobOut.audio_url`은 job이 성공한 경우 `request_json.format` 기준으로 `/v1/assets/{generation_id}.{fmt}`를 반환한다.

### 2.3 `apps/api/app/job_runner.py`

in-process background runner 추가.

현재 구현:

```text
ThreadPoolExecutor(max_workers=1)
```

의도:

- Mac/MPS에서는 동시 합성 1개가 가장 안전하다.
- A100/CUDA 서버로 옮길 때도 처음에는 worker concurrency 1부터 시작하는 것이 안전하다.
- 구조는 나중에 Celery/RQ/Redis worker로 교체 가능하게 job_id 기반으로 분리했다.

지원 작업:

```text
tts job
podcast job
```

podcast job 처리 흐름:

```text
1. segment별 speaker 확인
2. speaker별 VoiceClonePrompt 캐시 준비
3. segment별 임시 wav 생성
4. segment 사이 pause wav 삽입
5. ffmpeg concat
6. 최종 generation audio_path 저장
```

### 2.4 `apps/api/app/routers/jobs.py`

신규 API router 추가.

```text
POST /v1/jobs/tts
POST /v1/jobs/podcast
GET  /v1/jobs
GET  /v1/jobs/{job_id}
```

### 2.5 `apps/api/app/main.py`

- `jobs.router` 등록.
- 서버 재시작 시 `queued`/`running` job과 `pending`/`running` generation을 `failed(interrupted_by_restart)`로 정리하도록 보강.
- OmniVoice 로컬 데모 화자 저장소(`.omnivoice_speakers`)의 기본 데모 화자를 앱 DB에 1회 import하도록 보강.

### 2.6 `apps/api/app/routers/tts.py`

기존 동기 TTS와 async job worker가 같은 prompt 준비 로직을 쓰도록 다음 함수를 분리했다.

```text
ensure_speaker_voice_prompt()
```

이 함수는 다음을 수행한다.

```text
1. speaker ref_audio 확인
2. ref_transcript가 없으면 Whisper 전사 후 DB 저장
3. ref_audio + ref_transcript + preprocess_prompt 기반 해시 prompt 경로 계산
4. VoiceClonePrompt 캐시 생성 또는 재사용
5. ref_audio_path, voice_prompt_path 반환
```

추가 보강:

- `source_audio_path`가 없는 화자라도 `prompt_blob_path`가 있으면 해당 VoiceClonePrompt를 직접 사용한다.
- `omnivoice-demo` 태그가 있는 import 화자는 원본 데모 prompt를 우선 사용한다.

### 2.7 `apps/web/src/lib/api.ts`, `apps/web/src/lib/types.ts`

프론트 클라이언트 타입과 API wrapper 추가.

```text
createTtsJob()
createPodcastJob()
listJobs()
getJob()
```

Studio UI에서 단일 TTS job과 Podcast job을 생성하고 polling으로 진행률/결과를 확인할 수 있다.

### 2.8 `apps/api/app/default_speakers.py`

OmniVoice 엔진 루트의 `.omnivoice_speakers`에 있는 데모 화자를 앱 화자 라이브러리로 가져온다.

현재 로컬에서 import된 화자:

```text
OmniVoice Korean Demo
OmniVoice Korean Demo KR
```

특징:

- `.pt` VoiceClonePrompt를 `apps/api/data/speakers/<speaker_id>/prompt-imported.pt`로 복사한다.
- `__ref.*` 미리듣기 파일이 있으면 `ref.*`로 복사해 화자 목록에서 재생할 수 있게 한다.
- 이미 같은 이름의 화자 레코드가 있으면 중복 생성하지 않는다.
- 사용자가 삭제한 같은 이름의 화자는 다시 자동 생성하지 않는다.

---

## 3. API 사용 예시

### 3.1 단일 TTS 비동기 생성

요청:

```bash
curl -X POST http://127.0.0.1:8320/v1/jobs/tts \
  -H "Authorization: Bearer dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "비동기 잡 API 테스트입니다.",
    "speaker_id": "6c160441dced4f4ca59ca8bd0c588edb",
    "language": "ko",
    "format": "wav",
    "params": {
      "num_step": 16,
      "guidance_scale": 2.0,
      "denoise": true,
      "t_shift": 0.1,
      "position_temperature": 5.0,
      "class_temperature": 0.0,
      "layer_penalty_factor": 5.0,
      "preprocess_prompt": true,
      "postprocess_output": true,
      "audio_chunk_duration": 15.0,
      "audio_chunk_threshold": 30.0
    }
  }'
```

응답:

```json
{
  "job_id": "2c277184f9a94b1291a63ac7c4339a05",
  "generation_id": "3c43570b909a4952839f9e06890d1fc6",
  "status": "queued"
}
```

상태 조회:

```bash
curl http://127.0.0.1:8320/v1/jobs/2c277184f9a94b1291a63ac7c4339a05 \
  -H "Authorization: Bearer dev-key-change-me"
```

완료 응답 예:

```json
{
  "id": "2c277184f9a94b1291a63ac7c4339a05",
  "type": "tts",
  "status": "succeeded",
  "generation_id": "3c43570b909a4952839f9e06890d1fc6",
  "progress_current": 1,
  "progress_total": 1,
  "progress_message": "done",
  "audio_url": "/v1/assets/3c43570b909a4952839f9e06890d1fc6.wav"
}
```

### 3.2 다중 화자 Podcast 생성

요청:

```bash
curl -X POST http://127.0.0.1:8320/v1/jobs/podcast \
  -H "Authorization: Bearer dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "짧은 대화 테스트",
    "language": "ko",
    "format": "wav",
    "pause_ms": 350,
    "segments": [
      {
        "speaker_id": "HOST_SPEAKER_ID",
        "label": "HOST",
        "text": "오늘은 데이터베이스와 파일 저장에 대해 이야기해 보겠습니다."
      },
      {
        "speaker_id": "GUEST_SPEAKER_ID",
        "label": "GUEST",
        "text": "네, 작은 서비스에서는 파일 저장만으로도 충분한 경우가 많죠."
      }
    ],
    "params": {
      "num_step": 32,
      "guidance_scale": 2.0,
      "denoise": true,
      "t_shift": 0.1,
      "position_temperature": 5.0,
      "class_temperature": 0.0,
      "layer_penalty_factor": 5.0,
      "preprocess_prompt": true,
      "postprocess_output": true,
      "audio_chunk_duration": 15.0,
      "audio_chunk_threshold": 30.0
    }
  }'
```

작동 방식:

- 각 segment는 `speaker_id`에 해당하는 등록 화자 prompt를 사용한다.
- 각 segment를 독립 wav로 생성한다.
- segment 사이에 `pause_ms` 길이의 silence wav를 삽입한다.
- 모든 wav를 ffmpeg concat으로 이어붙인다.
- 최종 결과는 하나의 generation으로 히스토리에 저장된다.

---

## 4. 검증 결과

### 4.1 단일 TTS job

```text
job_id: 2c277184f9a94b1291a63ac7c4339a05
generation_id: 3c43570b909a4952839f9e06890d1fc6
status: succeeded
progress: 1/1 done
audio: apps/api/data/audio/3c43570b909a4952839f9e06890d1fc6.wav
duration_sec: 5.41
rtf: 1.744
```

### 4.2 Podcast job

초기 검증은 Starhunter 화자 1명만 있는 상태에서 동일 speaker_id를 HOST/GUEST 양쪽에 넣어서 runner/concat 경로를 확인했다.

```text
job_id: 78a136a2358e419198293315720899cf
generation_id: 8afe2179cc1c4bc390eabd6532b4d1d0
status: succeeded
progress: 2/2 done
audio: apps/api/data/audio/8afe2179cc1c4bc390eabd6532b4d1d0.wav
duration_sec: 9.75
rtf: 1.569
```

`ffprobe`:

```text
duration=9.750000
size=468078
```

### 4.3 기본 데모 화자 import 및 프롬프트 전용 합성 검증

OmniVoice 데모 저장소에서 import된 화자:

```text
OmniVoice Korean Demo
OmniVoice Korean Demo KR
```

프롬프트 전용 화자 합성 검증:

```text
job_id: ea5f00fab7e143f082886d36851ef998
generation_id: 6a9083f82ffc476694bbbc631b192033
speaker: OmniVoice Korean Demo
status: succeeded
progress: 1/1 done
```

Starhunter + 기본 데모 화자 2인 팟캐스트 검증:

```text
job_id: 500d24196d3640afbe63c7087f54b4bf
generation_id: 3831a0f1639345fcb5b191698d9589dd
status: succeeded
progress: 2/2 done
audio: apps/api/data/audio/3831a0f1639345fcb5b191698d9589dd.wav
duration: 14.33s
```

### 4.4 검사

```text
python -m py_compile
OK

pnpm --filter @omnivoice/web typecheck
OK
```

---

## 5. 운영 방침

### 5.1 Mac/MPS

- worker concurrency는 1로 유지.
- 장문/팟캐스트는 `/v1/jobs/*` 사용.
- 기존 `/v1/tts`는 짧은 동기 합성 또는 호환 용도로 유지.

### 5.2 A100/CUDA 서버

A100 서버로 옮길 경우 권장 설정:

```env
OMNIVOICE_DEVICE=cuda
API_HOST=0.0.0.0
API_PORT=8320
CORS_ORIGINS=http://localhost:5320,http://YOUR_WEB_HOST
NEXT_PUBLIC_API_BASE=http://A100_SERVER:8320
```

초기에는 worker concurrency 1로 시작하고, GPU 메모리와 throughput을 확인한 뒤 2 이상으로 늘리는 것이 안전하다.

### 5.3 다중 화자 품질

- 진짜 2인 팟캐스트를 만들려면 최소 2개 speaker가 등록되어 있어야 한다.
- 현재 로컬 기본값으로 Starhunter, OmniVoice Korean Demo, OmniVoice Korean Demo KR을 사용할 수 있다.
- Auto voice는 같은 화자 유지가 보장되지 않으므로 podcast segment에는 등록 speaker를 사용한다.
- 너무 짧은 segment는 음색/억양이 흔들릴 수 있다. 가능하면 2-4문장 단위로 segment를 구성하는 것이 좋다.

---

## 6. 남은 개선 과제

- job cancel API. 현재 runner는 subprocess cancel까지 관리하지 않는다.
- Celery/RQ/Redis 기반 외부 worker 전환.
- A100 서버 배포용 systemd/docker 문서.
- podcast segment별 볼륨 정규화 및 loudness normalization.

---

## 7. 한 줄 요약

이제 장문 단일 TTS와 다중 화자 podcast는 동기 요청이 아니라 `/v1/jobs/*` 비동기 job으로 생성할 수 있고, 각 job은 DB에 상태/진행률/최종 generation을 남긴다.
