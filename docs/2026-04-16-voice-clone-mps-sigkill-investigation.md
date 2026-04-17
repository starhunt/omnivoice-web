# Voice Clone TTS — MPS SIGKILL/OOM 조사 보고서

**작성일**: 2026-04-16
**대상 독자**: 동일 코드베이스에서 추가 조사를 이어받을 다른 에이전트/개발자
**상태**: **부분 해결, 환경 의존적 한계 잔존**

---

## 0. 요약 (TL;DR)

OmniVoice 기반 TTS 플랫폼(`apps/api` FastAPI + `apps/web` Next.js)에서 **화자 복제(voice clone) 모드 + 긴 텍스트** 합성 시 subprocess가 SIGKILL(rc=-9)당하거나 PyTorch MPS OOM 예외가 발생하는 문제를 조사. 청크 분할/격리 subprocess/Whisper 1회 캐시 등 다수 개선으로 짧은 텍스트(≤139자)는 안정화되었으나, **700자 화자복제는 시스템 누적 가상 메모리(83GB+) 한계로 여전히 실패**. 코드 레벨 추가 개선 여지가 한정적이며, 시스템 차원의 메모리 회수(`sudo purge`/재부팅) 또는 디바이스 변경(CPU)이 필요할 수 있음.

---

## 1. 시스템 환경

| 항목 | 값 |
|------|----|
| OS | macOS (Apple Silicon, Darwin 25.4.0) |
| 총 RAM | **64 GB** (unified memory, page size 16384) |
| Python (API) | 3.11.x via venv `apps/api/.venv` |
| Python (엔진) | 3.11.12 via `/Users/starhunter/StudyProj/voiceproj/OmniVoice/.venv/bin/python` |
| TTS 엔진 | OmniVoice (`k2-fsa/OmniVoice`, diffusion 기반) |
| 디바이스 | **MPS** (Apple Metal, unified memory 공유) |
| API 포트 | 8320 (uvicorn `--reload`) |
| Web 포트 | 5320 (Next.js dev) |
| ref audio | `data/speakers/{id}/ref.wav`, **44.1kHz mono, 15초, 1.3MB** |

### 시스템 메모리 특성 (조사 시점 관찰)

- 일반 idle 시: free 45~50GB, compressed <1GB
- 합성 subprocess 실행 시: compressed가 **순간 30~40GB로 폭주** 후 회복
- swap_out 누적: **127~202GB+** (장시간 사용 흔적)
- jetsam level: 93 (정상은 100 — 약간의 메모리 압력 상태)

---

## 2. 핵심 코드 구조

```
apps/api/
├── app/
│   ├── main.py                    # FastAPI 엔트리, lifespan에서 stale running 정리
│   ├── routers/
│   │   ├── tts.py                 # POST /v1/tts (합성 전 ref_transcript 자동 캐싱)
│   │   └── generations.py         # GET/DELETE /v1/generations + cleanup-stale
│   └── engine/
│       └── omnivoice_adapter.py   # subprocess 래퍼, 분할/격리/transcribe 오케스트레이션
└── scripts/
    └── engine_cli.py              # OmniVoice 모델 직접 호출 (별도 venv subprocess)

apps/web/src/
├── app/history/page.tsx           # 삭제/일괄정리 UI
└── lib/api.ts                     # deleteGeneration, cleanupStaleGenerations
```

### 주요 함수 위치

| 기능 | 파일:라인 (대략) |
|------|----------------|
| 텍스트 분할 | `omnivoice_adapter.py` `split_text_for_synthesis()` |
| 격리 모드 분기 | `omnivoice_adapter.py` `_should_isolate_chunks()` |
| 청크별 subprocess 루프 | `omnivoice_adapter.py` `_run_engine_isolated_chunks()` |
| 단일 subprocess 호출 | `omnivoice_adapter.py` `_invoke_engine_once()` |
| Whisper 전사 (분리) | `omnivoice_adapter.py` `transcribe_ref_audio()` |
| 엔진 합성 본체 | `engine_cli.py` `run_synthesis()` |
| 엔진 전사 본체 | `engine_cli.py` `run_transcribe()` |
| stale running 정리 | `main.py` `_finalize_stale_running_jobs()` |
| 합성 전 ref_transcript 캐싱 | `routers/tts.py` `post_tts()` 화자 조회 직후 |

---

## 3. 적용된 수정사항 (시간순)

### 3.1 텍스트 청킹 + 청크별 격리 subprocess
- **문제**: 7~10분 분량 입력 시 단일 `model.generate()`이 메모리 폭주 → 컴퓨터 재부팅 발생 사례
- **수정**:
  - `split_text_for_synthesis()` — 문장 경계 기준 분할
  - 환경변수 `OMNIVOICE_ISOLATE_CHUNKS=auto` (MPS 기본 활성)
  - 격리 모드: 청크당 새 subprocess → 모델 로드/생성/종료, ffmpeg concat
- **결과**: ✅ **auto 모드 + 9분 분량 성공** (peak RSS 771MB)

### 3.2 메모리 해제 강제
- `engine_cli.py` 안 청크 루프에 `torch.no_grad()` + `torch.mps.empty_cache()` + `gc.collect()`
- 모델 `.to(device)` 직후에도 `_empty_device_cache()` 호출
- voice clone prompt 생성도 `with torch.no_grad()` 안에서

### 3.3 Speaker.ref_transcript 자동 저장 (Whisper 1회만)
- **문제**: `ref_transcript=None`이면 OmniVoice가 합성마다 Whisper auto-transcribe → Whisper + OmniVoice 두 모델이 같은 subprocess의 MPS에 동시 점유 → SIGKILL
- **수정**:
  - `engine_cli.py --transcribe` 모드 (Whisper만 실행, OmniVoice generate 없음)
  - `tts.py`에서 ref_audio 있고 transcript 없으면 `transcribe_ref_audio()` 별도 subprocess 호출 → DB에 저장 → 본 합성은 transcript 가진 상태로 → Whisper 전혀 안 돔
- **결과**: ✅ **Whisper 로딩 stderr 사라짐**, ref_transcript DB 영구 저장 확인

### 3.4 startup stale 정리 + DELETE/cleanup 엔드포인트 + UI
- `main.py` lifespan에서 `status='running'` 레코드를 `failed(interrupted_by_restart)`로 일괄 전환
- `DELETE /v1/generations/{id}` (오디오 파일 + DB row 삭제)
- `POST /v1/generations/cleanup-stale`
- `apps/web/src/app/history/page.tsx`에 행별 🗑 + 헤더 "찌꺼기 정리" 버튼

### 3.5 `subprocess.run(start_new_session=True)`
- **가설**: macOS jetsam이 프로세스 그룹 단위로 메모리 집계 → uvicorn worker + engine subprocess 합산되어 우선 kill 대상이 됨
- **수정**: `_invoke_engine_once`, `transcribe_ref_audio` 양쪽 subprocess 호출에 `start_new_session=True` 추가
- **결과**: ⚠️ **효과 미확정**. 일부 케이스 성공/일부 실패. 가설이 맞는지 단정 불가.

### 3.6 화자복제 모드 강제 작은 청크
- **관찰**: auto 모드는 220자 청크 OK, 화자복제는 100자 텍스트도 ref_audio 인코딩 peak + generate peak 동시에 SIGKILL
- **수정**: `_run_engine_subprocess` 진입 시 `if ref_audio_path: threshold=100, max_chars=120` 강제 적용
- **결과**: ✅ **139자 화자복제 1회 성공** (2 청크 분할, 격리 모드, 30초 소요, RTF 1.42)

### 3.7 PYTORCH_MPS_*_WATERMARK_RATIO 정책 변경
- 처음: `PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0` (상한 해제) — SIGKILL/jetsam 경향
- 나중: 명시 설정 제거하여 PyTorch 기본값(HIGH=1.4) 사용 — graceful OOM exception로 전환
- 현재 코드(`omnivoice_adapter.py`)는 명시 설정 **없음** (사용자가 환경변수로 명시한 경우만 존중)

### 3.8 stderr 전체 dump (진단)
- subprocess 실패 시 (rc != 0 또는 stdout 비어있음) `/tmp/omnivoice_engine_failures/fail_YYYYMMDD_HHMMSS_rc{N}.log`에 payload 키, params, ref 경로, stderr 원문, stdout 원문 모두 저장
- API 에러 응답에 `[full log: <path>]` hint 포함

---

## 4. 실측 데이터

### 4.1 검증 통과 케이스

| 시나리오 | 결과 | 시간 | Peak RSS | 비고 |
|---------|------|------|----------|------|
| auto 모드, 30자 | succeeded | 3초 | - | 베이스라인 |
| auto 모드, 610자 (4 청크 격리) | succeeded | 51초 | 615MB | 청크별 subprocess 4회 확인 |
| auto 모드, 3196자 (12 청크 격리) | succeeded | 3분 1초 | 771MB | 9분 분량 long-form 검증 |
| 화자복제, 49자 | succeeded | 14초 | - | 직접 FastAPI |
| 화자복제, 139자 (2 청크 격리) | succeeded | 30초 | - | 사용자 UI 동일 params |

### 4.2 실패 케이스 (현재 미해결)

| 시나리오 | 결과 | 에러 |
|---------|------|------|
| 화자복제, 593자 (8 청크 격리, WATERMARK=0.0) | **rc=-9 SIGKILL** | 첫 청크에서 jetsam, compressed 36GB peak |
| 화자복제, 593자 (WATERMARK 기본) | **PyTorch OOM exception** | "MPS allocated 4.71 GiB, other allocations 83.37 GiB, max 88.13 GiB, tried 100 MiB" |

### 4.3 결정적 stderr 로그 (실패 케이스 공통)

```
Loading weights: 100%|██████████| 313/313 [00:00<00:00, 49555.23it/s]
Fetching 13 files: 100%|██████████| 13/13 [00:00<00:00, 14009.75it/s]
Loading weights: 100%|██████████| 527/527 [00:00<00:00, 38194.61it/s]
/Users/starhunter/.pyenv/versions/3.11.12/lib/python3.11/multiprocessing/resource_tracker.py:254:
  UserWarning: resource_tracker: There appear to be 1 leaked semaphore objects to clean up at shutdown
```

- 313, 527 weights = OmniVoice main + audio_tokenizer
- 587 weights = Whisper (수정 3.3 적용 후 **사라짐** — 정상)
- `leaked semaphore`는 SIGKILL의 결과 (subprocess가 multiprocessing 자원 보유 중 강제종료) — 원인 아님

---

## 5. 확정된 사실

1. **Whisper 분리 캐싱은 작동**: 수정 3.3 이후 합성 subprocess stderr에 Whisper 로딩 로그 안 보임. ref_transcript DB 영구 저장 확인.
2. **청크 분할 + 격리 subprocess는 auto 모드에 효과적**: peak RSS 771MB로 long-form 안정.
3. **화자복제 + 100자 청크도 어느 시점엔 성공**: 시스템 메모리 상태가 좋을 때만.
4. **WATERMARK=0.0은 위험**: 시스템 jetsam에 의한 SIGKILL 유발. 기본값(1.4)이 graceful OOM으로 전환되어 안전.
5. **시스템 가상 메모리 누적이 한계 인접**: PyTorch가 보고하는 "other allocations 83GB"는 RAM이 아닌 시스템 전체 VM. 실제 free RAM 47GB여도 VM은 한계.

---

## 6. 미해결 미스터리

### 6.1 동일 코드/요청의 산발적 성공/실패

같은 코드 + 같은 요청이 시간 차이를 두고 반복 시 결과가 갈림:
- 21:32:25 화자복제 49자 → 성공
- 21:33:30 화자복제 139자 → 실패
- 21:39:44 화자복제 139자 (코드 동일, 작은 청크 적용 후) → 성공
- 22:00:24 화자복제 593자 → 실패

원인 후보:
- 시스템 VM 누적이 시간에 따라 변동
- MPS driver 내부 pool fragmentation
- 다른 프로세스의 일시적 메모리 점유

### 6.2 `start_new_session=True`의 실제 효과

가설(macOS jetsam의 프로세스 그룹 회계)이 옳은지 단정 어려움. 적용 후에도 일부 케이스 실패.

### 6.3 첫 subprocess가 모델 로드 직후 죽는 패턴

stderr에 `Loading weights: 100%` 두 번 출력 후 SIGKILL/OOM. 모델 로드는 완료된 시점인데 직후 첫 `create_voice_clone_prompt` 또는 `model.generate()`에서 추가 할당 실패.

OmniVoice 모델이 `.to('mps')` 단계에서 실제 텐서가 lazy 할당되어 첫 forward call에서 추가 메모리 요청? — 미확인.

---

## 7. 추가 조사 권장 방향

### 우선순위 높음
1. **`sudo purge` 효과 측정**
   - 명령: `sudo purge`로 inactive/cached/compressed memory 강제 회수
   - 직후 동일 700자 시나리오 재시도 → "other allocations" 수치 변화 측정
   - 효과 있으면: 시스템 정리만으로 회피 가능 → 사용자 운영 가이드에 포함
2. **OmniVoice 모델 dtype/precision 옵션 확인**
   - 위치: `/Users/starhunter/StudyProj/voiceproj/OmniVoice/omnivoice/models/omnivoice.py`
   - `OmniVoice.from_pretrained(model_id, dtype=torch.float16)` 같은 인자 지원 여부
   - 절반 정밀도면 메모리 ~50% 감소 가능
3. **CPU fallback 옵션 구현**
   - `OMNIVOICE_DEVICE=cpu` 설정 시 합성 시간 측정
   - 사용자 선택 옵션으로 노출 (안정성 우선 모드)

### 우선순위 중간
4. **engine_cli.py에서 `model.generate()` 직후 명시적 `model.cpu()` 후 재로드**
   - 청크 간 MPS 메모리 완전 비움 (격리 subprocess 안 쓰는 경로용)
5. **`audio_chunk_duration`/`audio_chunk_threshold` 파라미터 영향 측정**
   - 현재 기본 15.0/30.0. 더 작게(5.0/10.0) 했을 때 메모리 영향 확인.
6. **MPS allocation 패턴 측정**
   - `torch.mps.driver_allocated_memory()`, `torch.mps.current_allocated_memory()`로 단계별 사용량 로깅
   - engine_cli.py에 진단용 로그 추가

### 우선순위 낮음 (가설 검증)
7. **`start_new_session=True` A/B 테스트**
   - 일관된 시스템 상태에서 on/off 비교
8. **uvicorn worker를 별도 프로세스 그룹으로 띄우기 시도**
   - dev.sh에서 `setsid uvicorn ...` — 부모 bash 그룹에서 분리

---

## 8. 사용자 환경 권장 운영 방침 (현재 상태 기준)

1. **장시간 macOS 사용 후엔 재부팅 또는 `sudo purge`**: VM 누적이 200GB+ 도달 시 합성 fragile
2. **화자복제 시 짧은 텍스트 권장**: 현재 코드로는 ~150자 이내가 안전
3. **장문 합성은 auto 모드 사용**: 청크 격리로 9분 분량까지 검증됨
4. **신규 speaker 등록 후 첫 합성은 ASR 1회 추가 시간 소요**: 이후엔 빨라짐 (DB 캐시)
5. **실패 시 진단**: `/tmp/omnivoice_engine_failures/` 최신 로그 확인 → rc=-9면 SIGKILL, exception이면 PyTorch OOM

---

## 9. 관련 commit / 파일 상태

- 첫 commit: `dac087d chore: initial commit` (2026-04-16, 50 files)
- 이 commit에 위 모든 수정 포함
- 후속 commit 미생성 — 이 문서 작성 시점 working tree clean

### 환경변수 요약 (현재 기본값)

| 변수 | 기본 | 용도 |
|------|------|------|
| `OMNIVOICE_DEVICE` | `mps` | cpu/mps/cuda |
| `OMNIVOICE_TIMEOUT_SEC` | `1800` | subprocess 타임아웃 |
| `OMNIVOICE_CHUNK_THRESHOLD_CHARS` | `220` | auto 모드 분할 임계 (화자복제는 코드 내 100 강제) |
| `OMNIVOICE_CHUNK_MAX_CHARS` | `200` | auto 모드 청크 최대 (화자복제는 120 강제) |
| `OMNIVOICE_CHUNK_MIN_CHARS` | `60` | 작은 청크 병합 임계 |
| `OMNIVOICE_ISOLATE_CHUNKS` | `auto` | MPS면 격리 모드 자동 |
| `PYTORCH_MPS_HIGH_WATERMARK_RATIO` | (미설정) | PyTorch 기본 1.4 사용 |

### 진단용 명령

```bash
# 실패 로그
ls -lt /tmp/omnivoice_engine_failures/ | head

# 메모리 상태
vm_stat | awk '/Pages free/ {f=$3} /Pages occupied by compressor/ {c=$5} END {p=16384;g=1073741824; printf "free=%.1fGB comp=%.2fGB\n", f*p/g, c*p/g}'

# 시스템 메모리 압력
sysctl kern.memorystatus_level   # 100 정상, 낮을수록 압박

# DB 최근 generation 상태
curl -s -H "Authorization: Bearer dev-key-change-me" \
  "http://localhost:8320/v1/generations?limit=10" | python3 -m json.tool
```

---

**문서 끝.** 추가 조사 결과는 같은 디렉토리에 `2026-MM-DD-followup-...md`로 이어 작성 권장.
