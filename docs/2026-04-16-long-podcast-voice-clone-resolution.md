# 장문 팟캐스트 화자복제 안정화 조치 내역

**작성일**: 2026-04-16  
**최종 갱신**: 2026-04-17  
**대상**: OmniVoice Web `화자 복제` 모드, Starhunter 등록 화자, 5분 이상 장문 팟캐스트 생성  
**상태**: Starhunter 화자복제 장문 생성 성공, 스튜디오 UI 경로 정상화 확인

---

## 1. 결론

최초 문서의 MPS OOM/SIGKILL 분석은 일부 맞았지만, 실제로는 애플리케이션 레벨에서 고칠 수 있는 문제가 더 컸다.

확정된 직접 원인은 다음 세 가지다.

1. `engine_cli.py`가 OmniVoice 공식 CLI와 달리 accelerator 추론 dtype을 명시하지 않았다.
2. 등록 화자의 `VoiceClonePrompt`를 영구 캐시하지 않아 장문 청크 합성에서 참조 오디오 처리 비용과 메모리 피크가 반복될 수 있었다.
3. 스튜디오 화면은 Next.js rewrite 프록시(`/api/v1`)를 통해 긴 동기 TTS 요청을 보내고 있었고, FastAPI 합성은 성공했는데 브라우저 쪽에는 `500 Internal Server Error`가 먼저 표시될 수 있었다.

추가로, 조치 중 한 번 잘못 생성한 `prompt.pt`에 임시 문구가 들어가 음성 생성 중 반복 발화되는 문제가 있었다. 이 문제는 해시 기반 prompt 캐시 경로로 재발 방지 처리했다.

---

## 2. 수정된 파일

### 2.1 `apps/api/scripts/engine_cli.py`

적용 내용:

- accelerator(`mps`, `cuda`)에서는 `float16`, CPU에서는 `float32`로 모델을 로드하도록 `_get_inference_dtype()` 추가.
- MPS에서는 `device_map="mps"`가 현재 환경에서 Transformers allocator warmup 오류를 내므로, `dtype=float16`으로 로드 후 기존처럼 `.to("mps")`를 유지.
- `VoiceClonePrompt` 저장/로드 유틸 추가.
- `--prepare-prompt` CLI 모드 추가.
- 합성 payload에 `voice_prompt_path`가 있으면 raw `ref_audio`보다 우선 사용.

핵심 효과:

- MPS 추론 메모리 사용량 감소.
- 화자복제 장문 청크마다 참조 오디오를 다시 토큰화하지 않고, 캐시된 prompt를 재사용.

### 2.2 `apps/api/app/engine/omnivoice_adapter.py`

적용 내용:

- `prepare_voice_clone_prompt()` 추가.
- `synthesize()`와 내부 `_invoke_engine_once()` payload에 `voice_prompt_path` 전달.
- 실패 로그에 `voice_prompt_path`도 함께 기록.
- `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0` 강제 설정 제거 상태 유지.

핵심 효과:

- FastAPI 프로세스는 모델을 직접 로드하지 않고, 별도 engine subprocess에서 prompt 생성/합성을 수행.
- MPS watermark 상한 해제에 따른 OS SIGKILL 위험을 피하고, PyTorch 기본 watermark 정책을 사용.

### 2.3 `apps/api/app/routers/tts.py`

적용 내용:

- 등록 화자 요청 시 `Speaker.prompt_blob_path`가 없거나 현재 참조 정보와 맞지 않으면 prompt 캐시를 생성.
- `_prompt_cache_path()` 추가.
- prompt 캐시 파일명을 고정 `prompt.pt`가 아니라 참조 오디오와 transcript 상태에 묶인 해시 파일명으로 변경.

해시 입력값:

```text
ref_audio absolute path
ref_audio file size
ref_audio mtime_ns
speaker.ref_transcript
preprocess_prompt
```

현재 Starhunter 캐시:

```text
speakers/6c160441dced4f4ca59ca8bd0c588edb/prompt-7f704faa0406b02f.pt
```

핵심 효과:

- transcript가 바뀌었는데 예전 prompt 캐시가 계속 사용되는 문제 방지.
- 잘못된 prompt 문구가 생성 결과에 반복 삽입되는 문제 방지.

### 2.4 `apps/web/src/lib/api.ts`

적용 내용:

- 브라우저에서도 `NEXT_PUBLIC_API_BASE`가 있으면 Next.js rewrite(`/api/v1`) 대신 FastAPI를 직접 호출.
- 오디오 URL과 speaker ref URL도 직접 API base를 사용하도록 보정.

기존 문제:

```text
Browser -> Next.js /api/v1/tts rewrite -> FastAPI
```

긴 동기 요청에서 Next dev proxy가 먼저 `500`을 표시할 수 있었다. 실제 FastAPI는 뒤에서 합성을 계속했고, DB에는 `succeeded`로 남았다.

변경 후:

```text
Browser -> http://localhost:8320/v1/tts
```

핵심 효과:

- 스튜디오에서 긴 합성 요청이 Next.js dev proxy timeout/500에 걸리는 상황을 회피.

---

## 3. Starhunter 화자 상태

DB 기준 현재 Starhunter:

```text
speaker_id: 6c160441dced4f4ca59ca8bd0c588edb
name: Starhunter
source_audio_path: speakers/6c160441dced4f4ca59ca8bd0c588edb/ref.wav
prompt_blob_path: speakers/6c160441dced4f4ca59ca8bd0c588edb/prompt-7f704faa0406b02f.pt
```

현재 `prompt-7f704faa0406b02f.pt` 안의 `ref_text`:

```text
기존의 $200 프로 요금제는 여전히 가장 높은 사용량 옵션을 제공합니다. $200 프로 요금제를 이용하고 계신 기존 고객 여러분께 감사의 마음을 담아.
```

잘못 생성됐던 이전 캐시:

```text
speakers/6c160441dced4f4ca59ca8bd0c588edb/prompt.pt
```

이 파일에는 다음 임시 문구가 들어가 있었다.

```text
안녕하세요. 저는 스타헌터입니다. 옴니보이스 웹에서 사용할 화자 복제용 참조 음성입니다.
```

이 문구가 실제 합성 내용 중 반복되어 나왔던 원인은 `VoiceClonePrompt.ref_text`가 모델 조건에 포함되기 때문이다. 현재 DB는 더 이상 이 캐시를 가리키지 않는다.

---

## 4. 검증 결과

### 4.1 짧은 cached prompt smoke test

```text
out_path: apps/api/data/audio/prompt_smoke.wav
duration_sec: 14.10
status: ok
```

### 4.2 장문 Starhunter 화자복제

`data/podcast_script.txt`를 실제 `synthesize()` adapter 경로로 실행했다. 청크 분할, 청크별 isolated subprocess, ffmpeg concat까지 포함한 검증이다.

```text
chars: 2735
out_path: apps/api/data/audio/starhunter_podcast_long.wav
duration_sec: 745.08
elapsed_sec: 540.77
rtf: 0.726
```

`ffprobe` 결과:

```text
duration=745.080000
size=35763918
```

약 12분 25초 결과물이므로 5분 이상 장문 팟캐스트 조건을 충족한다.

### 4.3 HTTP endpoint smoke test

임시 API 포트 `8331`에서 실제 `POST /v1/tts` 요청을 검증했다.

```text
speaker_id: 6c160441dced4f4ca59ca8bd0c588edb
status: succeeded
generation_id: 610d5cc94ff345b4b6dd5447b423a714
duration_sec: 8.77
rtf: 1.043
```

### 4.4 Studio 경로 확인

스튜디오에서 562자 입력 테스트 중 프론트에는 `500 Internal Server Error`가 표시됐지만, FastAPI는 뒤에서 합성을 완료했다.

```text
generation_id: dc6d3be76e29417ba5cc788d72c445c2
status: succeeded
duration_sec: 146.19
rtf: 0.777
audio_path: audio/dc6d3be76e29417ba5cc788d72c445c2.wav
```

이후 `apps/web/src/lib/api.ts`를 수정해 브라우저가 FastAPI를 직접 호출하도록 변경했다.

### 4.5 수정 후 Studio 재테스트

스튜디오에서 동일 계열 562자 입력을 재시도했다.

```text
generation_id: 897fd0a877254ea6a2b2e1fb25c4ac8f
status: succeeded
duration_sec: 147.26
audio_path: audio/897fd0a877254ea6a2b2e1fb25c4ac8f.wav
```

서버 로그상 청크 처리:

```text
long text (562 chars) -> 7 chunks, isolated-subprocess mode
isolated chunk 1/7
...
isolated chunk 7/7
POST /v1/tts HTTP/1.1 200 OK
```

---

## 5. 운영 방침

### 권장 모드

장문에서 동일 화자 유지가 필요하면 반드시 다음 경로를 사용한다.

```text
Studio -> 화자 복제 -> Starhunter
```

Auto 모드는 장문 생성 자체는 가능하지만, isolated subprocess 모드에서는 청크마다 voice characteristics가 독립적으로 잡힐 수 있다. 따라서 같은 화자 유지 용도에는 적합하지 않다.

### 서버 실행

개발 서버:

```bash
pnpm dev
```

정상 URL:

```text
Frontend: http://localhost:5320/studio
API: http://localhost:8320
```

확인 명령:

```bash
curl http://127.0.0.1:8320/v1/health \
  -H "Authorization: Bearer dev-key-change-me"
```

### 실패 시 확인 순서

1. 브라우저 에러와 DB 상태를 분리해서 본다. 브라우저가 500을 표시해도 DB에서는 `succeeded`일 수 있다.
2. 최신 generation 확인:

```bash
sqlite3 apps/api/data/app.db \
  "select id,status,round(duration_sec,2),round(rtf,3),substr(coalesce(error,''),1,300),audio_path,created_at from generations order by created_at desc limit 5;"
```

3. 실패 로그 확인:

```bash
ls -lt /tmp/omnivoice_engine_failures | head
```

4. Starhunter prompt 캐시 확인:

```bash
sqlite3 apps/api/data/app.db \
  "select id,name,ref_transcript,prompt_blob_path from speakers where name='Starhunter';"
```

---

## 6. 남은 주의점

- 현재 `/v1/tts`는 동기 요청이다. 장문 생성은 수 분 이상 걸릴 수 있으므로, 장기적으로는 job queue + polling 방식이 더 적합하다.
- cached `VoiceClonePrompt`는 transcript와 참조 오디오 상태에 민감하다. 이제 해시 경로로 방지했지만, 화자 오디오를 수동으로 교체한 경우 DB 상태와 파일 상태를 함께 확인해야 한다.
- `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0`을 기본값으로 강제하지 않는다. 이 값은 graceful OOM 대신 OS SIGKILL을 유발할 수 있다.
- `device_map="mps"`는 현재 로컬 환경에서 allocator warmup 오류가 나므로 사용하지 않는다. MPS는 `dtype=float16`으로 로드 후 `.to("mps")` 경로를 사용한다.

---

## 7. 한 줄 요약

장문 화자복제 안정화의 핵심은 `float16` MPS 추론, registered speaker의 `VoiceClonePrompt` 캐시, 해시 기반 prompt invalidation, 그리고 브라우저의 FastAPI 직접 호출이다.
