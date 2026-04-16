# OmniVoice-Web PRD

상용 수준 자체 호스팅 음성 합성 플랫폼 — OmniVoice 엔진 래퍼

---

## 0. 메타

| 항목 | 값 |
|------|-----|
| 문서 버전 | 0.1 (Draft) |
| 작성일 | 2026-04-16 |
| 작성자 / Owner | starhunter |
| 대상 독자 | 본인 (개발·운영 겸직) |
| 대상 배포 | 단일 사용자, 자체 호스팅 (Apple M4 Max 64GB) |
| 상위 엔진 | [OmniVoice](https://github.com/k2-fsa/OmniVoice) (Apache 2.0) |
| 엔진 경로 | `/Users/starhunter/StudyProj/voiceproj/OmniVoice` |
| 모델 | HuggingFace `k2-fsa/OmniVoice` (snapshot `29cde0e...`) |
| 현재 엔진 실행 상태 | `omnivoice-demo` Gradio, `127.0.0.1:8001`, CPU 모드 |

---

## 1. Executive Summary

OmniVoice는 646개 언어를 지원하는 고품질 제로샷 TTS 엔진이지만, 공식 배포는 **Gradio 단일 세션 데모와 Python CLI뿐**이다. REST API, 인증, 화자 영속화, 배치 큐, 모니터링, 관리자 콘솔은 전무하며 상용 워크플로에 직접 투입할 수 없다.

**OmniVoice-Web**은 이 엔진 위에 상용 음성 플랫폼(예: ElevenLabs, Play.ht 스타일)에서 기대하는 **운영·관리 레이어 전체**를 자체 호스팅 형태로 제공한다. 브라우저 스튜디오 UI, REST API + API Key, 화자 라이브러리, 프로젝트/히스토리, 배치·스트리밍, 웹훅, 관측성까지 포함한다.

**단독 사용자** 전제로 결제·팀·RBAC·퍼블릭 SaaS 기능은 전면 제외한다. 그 대신 "혼자 쓰지만 기능 깊이는 상용급"이라는 축으로 최적화하여 개발 오버헤드를 절반 이하로 유지한다.

---

## 2. Background & Problem

### 2.1 현행 OmniVoice 데모의 한계

| 영역 | Gradio 데모의 문제 | OmniVoice-Web에서 해결 |
|------|-------------------|----------------------|
| 세션 | 탭 새로고침 시 상태 소실 | DB 기반 영속 세션/히스토리 |
| 인증 | 없음 (로컬 바인딩만으로 방어) | 단일 사용자 패스워드 + JWT + API Key |
| 화자 | `~/.omnivoice_speakers/*.pt` 파일 목록만 | CRUD·태그·즐겨찾기·원본 보존·버전 |
| API | 없음 | REST v1 + OpenAPI + 웹훅 |
| 배치 | `omnivoice-infer-batch` CLI(JSONL) | 웹 업로드 + 큐 + 진행률 + 결과 ZIP |
| 모니터링 | print 로그 | Prometheus/Loki, 큐 깊이, RTF |
| 대량 생성 | 동기 호출로 UI 블로킹 | Celery 비동기 + 상태 폴링/스트리밍 |
| 오디오 자산 | 임시 경로 | 프로젝트/파일 구조, 포맷 변환 |
| 스트리밍 | 생성 완료 후 전송 | 청크 단위 `audio/mpeg` 스트림 |

### 2.2 왜 지금 만드는가

- OmniVoice 엔진은 Apache 2.0 및 RTF 0.025 수준으로 실사용 준비 완료.
- 본인 워크플로(오디오북, 다국어 더빙, 콘텐츠 프로토타이핑)에 **반복 사용** 패턴이 확립되어 단발 CLI로는 비효율.
- 향후 가족/지인 공유 또는 소수 베타로 확장하려면 **API·화자 자산의 영속화**가 선결 조건.

---

## 3. Goals / Non-Goals

### 3.1 Goals

1. **풀기능 음성 플랫폼 경험을 단일 호스트에 구축**: TTS·화자복제·보이스디자인·오토보이스·음성→음성 캐스케이드·배치·스트리밍·히스토리·API·웹훅.
2. **OmniVoice 능력 내에서만 제품 정의** (§5 Feature Map이 유일한 진실 원본).
3. **Docker Compose 1회 명령으로 기동**하며, 사용자는 브라우저만 있으면 완전한 UI와 REST API를 이용할 수 있다.
4. **관측 가능성**: 모든 생성 요청의 파라미터·입력·결과·소요·에러가 재현 가능하게 저장된다.
5. **한국어 기본 UI, 다국어(i18n) 확장 가능한 구조**.

### 3.2 Non-Goals

- 결제·구독·과금·인보이스
- 팀·역할·권한(RBAC)·조직(Tenant)
- 공개 SaaS, 고객 SLA, 데이터 거주지·GDPR 감사
- 모바일 네이티브 앱 (반응형 웹은 포함)
- 감정 전이·스타일 전이·음성 편집기·음악/SFX 생성
- 진성 A→B 음성변환 (OmniVoice 미지원 — 캐스케이드로 대체)
- OmniVoice 엔진 자체 포크·커스터마이징 (외부 의존 유지)

---

## 4. Personas & Scenarios

### 4.1 페르소나 (단일)

**개발자-크리에이터 (본인)**
- M4 Max 64GB, macOS, Docker Desktop 사용
- 용도: 오디오북 제작, 다국어 콘텐츠, API로 외부 앱 연동, 화자 실험
- 숙련도: TTS 파라미터 이해, Python/REST 친숙
- 기대: CLI보다 빠른 반복, 화자 자산 영속, 동시 작업 가능, 결과 재현 가능

### 4.2 대표 시나리오

| # | 시나리오 | 핵심 기능 | 성공 기준 |
|---|---------|----------|----------|
| S1 | **오디오북 장문 배치**: 12시간 분량 원고를 한 화자로 연속 합성 후 챕터별 WAV/MP3 저장 | §6.6 배치, §7.1 화자 | 중단 없이 완료, 챕터별 단일 파일, RTF ≤ 0.1 |
| S2 | **외부 앱 API 연동**: 개인 봇/서비스에서 `POST /v1/tts` 호출 | §8 API, §6.7 스트리밍 | 첫 청크 TTFB ≤ 2s, 웹훅 수신 가능 |
| S3 | **화자 등록/재사용**: 20s 레퍼런스 업로드 → 자동 전사 → 라이브러리 저장 → 이후 재호출 | §6.2, §7.1 | 등록 ≤ 5초, 재호출 시 재업로드 불필요 |
| S4 | **음성→음성 캐스케이드**: 기존 음성 파일을 Whisper로 전사 → 등록한 본인 화자로 재합성 | §6.5 | 단일 버튼으로 end-to-end, 중간 전사 편집 가능 |
| S5 | **다국어 더빙**: 한국어 뉴스 원고 → 같은 화자로 영/중/일 생성 | §6.1, §6.2 | 화자 동일성 유지, 언어 자동 감지 또는 수동 지정 |
| S6 | **비언어 태그 실험**: `[laughter]`, `[sigh]`, `[surprise-oh]` 등 13종 태그 A/B 비교 | §6.1, §7.3 | 같은 파라미터로 재현 생성, A/B 파형 플레이어 |

---

## 5. Feature Map (OmniVoice 매핑)

> 본 표가 **유일한 기능 진실 원본**이다. OmniVoice 엔진이 직접 제공하지 않는 기능은 원칙적으로 범위 외로 간주한다.

| 제품 기능 | OmniVoice 지원 | 엔진 경로 / 근거 | 제품 구현 전략 |
|-----------|:-------------:|------------------|---------------|
| 텍스트→음성 (단일) | ✅ | `omnivoice/models/omnivoice.py:458` `OmniVoice.generate(text, ...)` | 직접 호출 |
| 화자 복제 (Zero-shot) | ✅ | 같은 파일 `create_voice_clone_prompt(ref_audio, ref_text)` — `VoiceClonePrompt` 객체 캐싱 | 서버가 래핑, DB에 프롬프트 매핑 저장 |
| 보이스 디자인 (파라메트릭) | ✅ | `docs/voice-design.md` (gender/age/pitch/style/accent/dialect) | 폼 → `instruct` 문자열 생성기 |
| 오토 보이스 | ✅ | 참조 오디오·instruct 생략 시 모델이 랜덤 화자 선택 | `generate(text=...)` 단독 호출 |
| 다국어 646개 | ✅ | `docs/languages.md` | UI에 상위 30개 노출 + 전체 검색 |
| 비언어 태그 (13종) | ✅ | `omnivoice/models/omnivoice.py:1494` `_NONVERBAL_PATTERN` | 에디터에 삽입 버튼 |
| 발음 교정 (핀인/음소) | ✅ | README.md:184+ 핀인 성조, CMU 음소 대괄호 | 에디터 구문 툴팁 |
| 속도 제어 | ✅ | `generation-parameters.md` `speed` (0.5~1.5 권장, 기본 None=1.0) | 슬라이더 0.5–1.5 |
| 고정 시간 제어 | ✅ | 같은 문서 `duration` (초, priority > speed) | 토글형 입력 |
| 가이던스 스케일 (CFG) | ✅ | `guidance_scale` 기본 2.0 | 슬라이더 0–4 |
| 디코딩 스텝 | ✅ | `num_step` 기본 32 (16이면 빠름) | 프리셋 "Fast(16)/Balanced(32)/Quality(64)" |
| 노이즈 토큰 | ✅ | `denoise` 기본 True | 토글 |
| 샘플링 온도 | ✅ | `position_temperature`(5.0), `class_temperature`(0.0), `layer_penalty_factor`(5.0) | 고급 설정 접이식 |
| 전·후처리 토글 | ✅ | `preprocess_prompt`, `postprocess_output` 기본 True | 고급 설정 |
| 장문 자동 분할 | ✅ | `audio_chunk_duration`(15s), `audio_chunk_threshold`(30s) | 스트리밍 청크 경계로 활용 |
| 배치 (다중 프로세스) | ✅ | `omnivoice/cli/demo.py` 및 `omnivoice-infer-batch` JSONL + ProcessPoolExecutor | Celery 워커에서 라이브러리로 재사용 |
| 자동 전사(ASR) 보조 | ✅ (보조 용도) | 데모의 `--asr` 옵션; Whisper로 레퍼런스 전사 | 화자 등록·음성변환 양쪽에 재활용 |
| 스트리밍 출력 | ⚠ 부분 | 전체 생성 후 Tensor 반환. **청크 경계는 모델이 내부에서 생성** | 청크별 인코딩→HTTP chunked 전송으로 **의사 스트리밍** 제공 |
| 진성 A→B 음성변환 | ❌ | OmniVoice는 audio-to-audio 변환 기능 없음 | **STT(Whisper) → TTS(화자 복제) 캐스케이드**로 대체 |
| 감정/스타일 전이 | ❌ | 비언어 태그 13종 외 감정 API 없음 | **범위 외** |
| 오디오 편집 | ❌ | 파형 편집·노이즈 제거는 엔진 책임 아님 | **범위 외** |
| 음악/효과음 생성 | ❌ | 음성 전용 | **범위 외** |

---

## 6. Core Features (Phase 1)

### 6.1 TTS 합성 스튜디오

**입력**
- 텍스트 (최대 10,000자, 소프트 리밋)
- 언어 (자동감지 또는 수동 지정, 상위 30개 프리셋 + 검색)
- 발음 교정 문법 허용 (핀인 성조, CMU 음소 대괄호)
- 비언어 태그 삽입 버튼(13종)

**파라미터 폼** (기본값은 `generation-parameters.md` 준수)

| 필드 | 타입 | 기본 | UI 위치 |
|------|------|-----|---------|
| num_step | int | 32 | Basic — 프리셋(16/32/64) |
| guidance_scale | float | 2.0 | Basic — 슬라이더 0–4 |
| denoise | bool | true | Basic — 토글 |
| speed | float | null(=1.0) | Basic — 슬라이더 0.5–1.5 |
| duration | float? | null | Basic — 토글 + 숫자 입력 |
| t_shift | float | 0.1 | Advanced |
| position_temperature | float | 5.0 | Advanced |
| class_temperature | float | 0.0 | Advanced |
| layer_penalty_factor | float | 5.0 | Advanced |
| preprocess_prompt | bool | true | Advanced |
| postprocess_output | bool | true | Advanced |
| audio_chunk_duration | float | 15.0 | Advanced |
| audio_chunk_threshold | float | 30.0 | Advanced |

**출력**
- 기본 24kHz WAV (엔진 원본)
- 선택 변환: MP3 192k / OGG / FLAC (서버에서 ffmpeg 변환)
- 파형 플레이어 + 다운로드 버튼
- 결과는 `generations` 테이블에 파라미터·입력 전체 저장 (재현 가능)

**수용 기준 (binary)**
- [ ] 텍스트만 입력하여 "오토 보이스"로 합성 가능
- [ ] 화자 선택 시 해당 프롬프트가 `generate()`에 전달됨
- [ ] Basic 파라미터 변경이 요청에 실제로 반영됨 (히스토리로 검증)
- [ ] 재현 버튼 1회 클릭으로 동일 결과 재생성
- [ ] 모든 비언어 태그 13종이 에디터에서 1클릭 삽입 가능

### 6.2 화자 복제 (Zero-shot Cloning)

**업로드**
- 지원 포맷: WAV/MP3/FLAC/OGG/M4A (엔진 `omnivoice/utils/audio.py` 기준)
- 권장 길이: 3–10초 (UI에 표시)
- 24kHz 자동 리샘플 (엔진 내부 처리)

**전사**
- 기본: Whisper ASR로 자동 전사 (엔진 `--asr` 재활용)
- 편집: 사용자가 전사 결과 수동 수정 가능 (오타/발음 보정)
- 미사용 옵션: `ref_text` 비운 채 저장 시 엔진이 내부 전사

**등록**
- 화자 이름, 태그(한국어·남성·차분 등), 노트(자유 텍스트), 예시 문장
- `create_voice_clone_prompt()` 결과 `VoiceClonePrompt`를 **이진 블롭**으로 DB/MinIO에 저장 (엔진이 `torch.save`로 직렬화 — 포맷 호환성은 §15 리스크로 추적)
- 원본 업로드 오디오도 원형 보존 (재추출 대비)

**수용 기준**
- [ ] 20초 이하 오디오 업로드 → 전사 → 편집 → 등록까지 5분 이내 UI 흐름
- [ ] 등록 후 페이지 새로고침/재기동에도 화자 목록 유지
- [ ] 동일 화자로 이후 합성 시 재업로드 불필요, ≤ 500ms 내 프롬프트 로드

### 6.3 보이스 디자인 (파라메트릭)

**폼 필드** (`voice-design.md` 기준)
- Gender: male / female
- Age: child / teenager / young adult / middle-aged / elderly
- Pitch: very low / low / moderate / high / very high
- Style: whisper (옵션)
- English Accent: american / british / australian / canadian / indian / chinese / korean / japanese / portuguese / russian
- Chinese Dialect: 河南话 / 陕西话 / 四川话 / 贵州话 / 云南话 / 桂林话 / 济南话 / 石家庄话 / 甘肃话 / 宁夏话 / 青岛话 / 东北话

**동작**
- 서버가 선택 값을 쉼표 구분 `instruct` 문자열로 조립 → `generate(text=..., instruct=...)` 호출
- 언어 자동 정규화 (문서상 양방향 쉼표 오류 허용)
- 빈 필드는 모델이 자율 결정 (문서 명시)

**수용 기준**
- [ ] 모든 6개 카테고리의 모든 속성이 UI에서 선택 가능
- [ ] Accent는 영어 텍스트, Dialect는 중국어 텍스트에만 효과 있음을 UI에 명시
- [ ] "이 설계를 화자로 저장"은 Phase 3으로 이월(프롬프트 저장 포맷 부재)

### 6.4 오토 보이스

- 텍스트만 입력, 화자·instruct 공란
- 실행마다 다른 화자 가능 (재현 목적이면 seed 고정 옵션 Phase 3)

### 6.5 음성→음성 (STT→TTS 캐스케이드)

> OmniVoice는 진성 VC를 제공하지 않으므로 **Whisper 전사 → 본인 화자 TTS**로 대체한다.

**흐름**
1. 입력 오디오 업로드 (포맷 동일)
2. Whisper로 전사 (언어 자동감지, 사용자 수동 수정 가능)
3. 타깃 화자 선택 (라이브러리 또는 오토 보이스)
4. 파라미터(속도/듀레이션/CFG) 조정
5. `generate()` 호출 → 재합성 오디오 반환

**수용 기준**
- [ ] 업로드 → 전사 → 재합성까지 하나의 페이지에서 완결
- [ ] 전사 텍스트 수동 편집 가능
- [ ] 원본 오디오와 결과 오디오 A/B 재생 비교

### 6.6 배치 작업

**입력 방식**
- 웹 폼 다중 행 (텍스트 + 화자/instruct/파라미터, 행당 1건)
- JSONL 업로드 (엔진 `omnivoice-infer-batch` 포맷과 호환)
- CSV 업로드 (열: text, speaker_id, language, speed, duration, ...)

**처리**
- Celery 큐로 비동기 처리 (동시성 = GPU/CPU 슬롯 수, 기본 1)
- 진행률·현재 항목·ETA 표시
- 실패 항목 재시도 (항목 단위)

**출력**
- 개별 WAV/MP3 + ZIP 번들
- 매니페스트 JSON (각 파일의 생성 파라미터)

**수용 기준**
- [ ] 100문장 배치가 중단 없이 완료
- [ ] 도중 취소/일시정지 가능
- [ ] 결과 ZIP 다운로드, 실패 로그 별도 조회

### 6.7 실시간(의사) 스트리밍

> 엔진이 청크 단위로 반환하지 않더라도, 내부 자동 분할(30s 임계) 결과 청크를 즉시 인코딩·flush하여 HTTP chunked 전송한다.

**엔드포인트**: `POST /v1/tts/stream` → `Transfer-Encoding: chunked`, `Content-Type: audio/mpeg`

**동작**
- 엔진이 `audio_chunk_duration=15s` 단위로 분할 생성
- 각 청크를 MP3 LAME으로 인코딩, `yield` 로 전송
- 클라이언트는 `MediaSource`/`<audio>` 태그 또는 curl로 즉시 재생 가능

**수용 기준**
- [ ] 첫 청크 TTFB ≤ 3s (M4 Max MPS, RTF 0.1 가정)
- [ ] 10분 길이 텍스트도 중단 없이 스트림 종료
- [ ] 네트워크 단절 시 부분 재시작 가능 (Phase 3)

---

## 7. Management Features

### 7.1 화자 라이브러리

| 항목 | 설명 |
|------|------|
| 목록 | 이름·태그·생성일·마지막 사용일·사용 횟수 정렬 |
| 상세 | 원본 오디오 재생, 전사 텍스트, 노트, 샘플 생성(프리셋 5개) |
| 편집 | 이름·태그·노트 수정 (프롬프트 재추출은 "재업로드"로만) |
| 즐겨찾기 | 즐겨찾기한 화자는 TTS 스튜디오 드롭다운 상단 노출 |
| 삭제 | 소프트 삭제 + 30일 보관 (실수 복구) |
| 가져오기 | 엔진 기본 경로 `~/.omnivoice_speakers/*.pt` 일괄 임포트 |
| 내보내기 | `.pt` + 메타JSON 번들 ZIP |

### 7.2 프로젝트 / 폴더

- 프로젝트 = 생성물의 논리적 묶음 (예: "오디오북_12장")
- 각 생성은 반드시 프로젝트에 귀속 (기본 프로젝트 "Inbox")
- 프로젝트별 대시보드: 총 길이, 소요 시간, 사용 화자 목록

### 7.3 생성 히스토리

| 기능 | 설명 |
|------|------|
| 검색 | 텍스트·화자·프로젝트·태그·기간 복합 |
| 재현 | 과거 생성의 파라미터·입력을 새 생성으로 1클릭 복사 |
| 재생성 | 같은 파라미터로 다시 실행 (샘플링 온도 > 0이면 결과 상이) |
| A/B 비교 | 두 건을 선택하면 좌우 파형 + 동기 재생 |
| 공유 | 로컬 URL (기본 localhost) 복사, 선택적 내보내기 |

### 7.4 API Key 관리

- 단일 사용자 기준, 개인 키 N개 발급 (외부 앱용 분리)
- 키별 라벨, 발급일, 마지막 사용, 사용량(요청수/오디오초)
- 폐기·회전 기능
- 스코프는 `tts`, `speakers:read`, `speakers:write`, `batch`, `admin`의 5개로 한정 (팀/조직 개념 없음)

### 7.5 관리자 콘솔

| 섹션 | 기능 |
|------|------|
| 엔진 | 모델 로드/언로드, 디바이스 전환(CPU/MPS/CUDA), 현재 VRAM/RAM |
| 큐 | Redis 큐 길이, 진행/대기/실패 수, 워커 상태 |
| 스토리지 | 오디오 자산 용량, 화자 파일 수, 디스크 남은 용량 |
| 로그 | 최근 100건 에러·경고, JSON 뷰어 |
| 환경 | 버전 정보, HF 모델 SHA, 업데이트 체크 링크 |

---

## 8. API Design (REST v1)

### 8.1 공통 규격

- Base URL: `http://localhost:8320/v1` (기본 API 포트 8320), 배포 시 환경변수로 변경
- 웹 UI: `http://localhost:5320` (기본 Web 포트 5320)
- 인증: `Authorization: Bearer <API_KEY>` (UI는 세션 JWT, 동일 백엔드 공유)
- 콘텐츠: `application/json`, 오디오 응답은 `audio/wav` 또는 `audio/mpeg`
- Rate limit: 본인 전용이므로 글로벌 상한만 (초당 10요청, 기본값, 변경 가능)
- OpenAPI 3.1 스펙 자동 생성 (FastAPI)

### 8.2 엔드포인트 목록

| Method | Path | 설명 | 관련 기능 |
|--------|------|------|----------|
| POST | `/tts` | 동기 합성 (짧은 텍스트) | §6.1, §6.3, §6.4 |
| POST | `/tts/stream` | 스트리밍 합성 | §6.7 |
| POST | `/voice-convert` | STT→TTS 캐스케이드 | §6.5 |
| POST | `/speakers` | 화자 등록 (multipart: audio + JSON meta) | §6.2 |
| GET | `/speakers` | 화자 목록 (페이지네이션) | §7.1 |
| GET | `/speakers/{id}` | 화자 상세 | §7.1 |
| PATCH | `/speakers/{id}` | 이름·태그·노트 수정 | §7.1 |
| DELETE | `/speakers/{id}` | 소프트 삭제 | §7.1 |
| POST | `/batch` | 배치 작업 생성 | §6.6 |
| GET | `/jobs/{id}` | 작업 상태 | §6.6 |
| GET | `/jobs/{id}/stream` | 작업 진행 SSE | §6.6 |
| GET | `/generations` | 히스토리 검색 | §7.3 |
| GET | `/generations/{id}` | 생성 상세 (파라미터·오디오 URL) | §7.3 |
| POST | `/generations/{id}/replay` | 재현 생성 | §7.3 |
| POST | `/webhooks` | 웹훅 등록 | §8.3 |
| GET | `/usage` | 사용량 통계 | §7.4 |
| POST | `/transcribe` | Whisper 단독 전사 (편의) | §6.5 |
| GET | `/languages` | 지원 언어 목록 | §6.1 |
| GET | `/voice-attributes` | 보이스 디자인 선택지 | §6.3 |
| GET | `/health` | 헬스체크 | §11 |
| GET | `/metrics` | Prometheus 노출 (인증 면제 옵션) | §9 |

### 8.3 요청/응답 예시

**POST /v1/tts** (동기)
```json
{
  "text": "안녕하세요, 오늘 날씨가 좋네요.",
  "speaker_id": "spk_01HXX...",
  "language": "ko",
  "params": {
    "num_step": 32,
    "guidance_scale": 2.0,
    "speed": 1.0,
    "denoise": true
  },
  "format": "mp3",
  "project_id": "prj_01HXX..."
}
```

응답 (200)
```json
{
  "generation_id": "gen_01HXX...",
  "audio_url": "http://localhost:8320/assets/gen_01HXX....mp3",
  "duration_sec": 3.2,
  "rtf": 0.041,
  "created_at": "2026-04-16T17:52:10Z"
}
```

**POST /v1/voice-convert** (캐스케이드)
```http
POST /v1/voice-convert
Content-Type: multipart/form-data

--boundary
Content-Disposition: form-data; name="meta"
Content-Type: application/json

{
  "target_speaker_id": "spk_01HXX...",
  "source_language": "auto",
  "params": { "speed": 1.0 }
}
--boundary
Content-Disposition: form-data; name="audio"; filename="source.wav"
Content-Type: audio/wav

<binary>
--boundary--
```

응답 (200)
```json
{
  "transcription": "원본에서 전사된 텍스트",
  "generation_id": "gen_01HXX...",
  "audio_url": "...",
  "duration_sec": 4.1
}
```

**웹훅 Payload** (`job.completed`)
```json
{
  "event": "job.completed",
  "job_id": "job_01HXX...",
  "status": "succeeded",
  "items": [
    { "index": 0, "generation_id": "gen_01HXX...", "audio_url": "..." }
  ],
  "finished_at": "2026-04-16T18:05:22Z"
}
```

### 8.4 에러 규격

- HTTP 4xx: 클라이언트 오류 (`code`, `message`, `details`)
- HTTP 5xx: 서버 오류 (내부 trace_id 포함)
- 에러 코드 네임스페이스: `invalid_input`, `speaker_not_found`, `engine_busy`, `unsupported_language`, `audio_too_long`, `internal_error`

---

## 9. Non-Functional Requirements

### 9.1 성능

| SLI | 목표 | 측정 방식 |
|-----|------|----------|
| 첫 청크 TTFB (스트리밍) | ≤ 3s | `/v1/tts/stream` 응답 헤더 수신 시점 |
| RTF (CPU) | ≤ 0.5 | 전체 생성 오디오초 ÷ 경과초 |
| RTF (MPS/CUDA) | ≤ 0.1 | 동일 |
| API p95 latency (짧은 문장 ≤ 50자) | ≤ 5s (CPU), ≤ 1s (MPS) | 미들웨어 계측 |
| 큐 대기 p95 | ≤ 3s (동시 작업 ≤ 2) | Celery 이벤트 |

### 9.2 가용성·신뢰성

- 단일 호스트, Docker Compose `restart: unless-stopped`
- 크래시 시 Celery 작업 재큐
- 모델 프리로드 (첫 요청에서 대기 ≤ 90s, 이후 0.5s 이내)

### 9.3 보안

- 기본 바인딩: `127.0.0.1` (localhost)
- 선택: Cloudflare Tunnel 또는 Caddy 리버스 프록시 + basic auth + HTTPS
- 단일 사용자 패스워드 + JWT 24h
- API Key는 해시 저장 (argon2id)
- 업로드 파일 MIME/확장자 화이트리스트 + ffmpeg 프로빙
- 입력 텍스트 길이 제한 10,000자, 배치 최대 10,000행
- 시크릿은 `.env` (gitignore), 컨테이너 환경변수만 사용

### 9.4 접근성 / 국제화

- WCAG 2.1 AA (대비, 키보드 포커스, aria-label)
- i18next + ICU MessageFormat, 한국어/영어 번들 초기 제공
- 키보드 단축키: `⌘↵` 생성, `⌘S` 저장, `⌘/` 검색

### 9.5 관측성

- 로그: 구조화 JSON, Loki로 수집 (선택), stdout 기본
- 메트릭: Prometheus `/metrics` (큐 길이, 생성 시간, RTF, 에러수)
- 추적: OpenTelemetry 계측 (선택 활성화)
- 감사 로그: API Key 발급/폐기, 화자 등록/삭제 이벤트

---

## 10. Data Model

### 10.1 엔티티 (PostgreSQL)

| 테이블 | 주요 컬럼 | 비고 |
|--------|----------|------|
| `users` | id, username, password_hash, created_at | 본인 1행 (초기 마이그레이션으로 생성) |
| `api_keys` | id, user_id, label, hash, scopes[], last_used_at, revoked_at | argon2id 해시 |
| `speakers` | id, name, tags[], note, prompt_blob_ref, source_audio_ref, language_hint, created_at, deleted_at | 소프트 삭제 |
| `speaker_versions` | id, speaker_id, prompt_blob_ref, created_at | 재업로드 시 버전 증가 |
| `projects` | id, name, description, created_at | 기본 "Inbox" |
| `generations` | id, project_id, mode(tts/design/auto/convert), text, speaker_id, instruct, params_json, audio_ref, duration_sec, rtf, created_at | 모든 생성 단건 |
| `jobs` | id, type(batch/stream), status, total, completed, failed, created_at, finished_at | 비동기 작업 |
| `job_items` | id, job_id, index, input_json, generation_id, status, error | 배치 항목 |
| `audio_assets` | id, kind(source/result), path, bytes, mime, sha256, created_at | 파일시스템 메타 |
| `webhook_endpoints` | id, url, secret, events[], created_at | 웹훅 등록 |
| `webhook_deliveries` | id, endpoint_id, event, payload_json, status, attempts, next_retry_at | 재시도 큐 |

### 10.2 저장소 분리

| 자산 | 저장 위치 | 이유 |
|------|----------|------|
| 메타 | PostgreSQL | 관계 쿼리, 트랜잭션 |
| 오디오 원본·결과 | MinIO (로컬) 또는 `./data/audio/` 볼륨 | 대용량, 스트리밍, 해시 검증 |
| 화자 프롬프트 `.pt` | MinIO + DB 참조 | 엔진 포맷 그대로 (호환성) |
| 큐 | Redis | Celery 백엔드 |
| 로그 | stdout → Loki (선택) | 수평 이동 가능 |

### 10.3 보존 정책

- 생성 오디오: 무제한 (디스크 경고 > 80% 시 UI 경고)
- 소프트 삭제: 30일 후 하드 삭제 배치 작업
- 감사 로그: 90일

---

## 11. Architecture

### 11.1 블록 다이어그램 (텍스트)

```
┌────────────────────────────────────────────────────────────────┐
│ Browser (Next.js SPA, ko/en, shadcn/ui, Tailwind, wavesurfer)  │
└──────────┬─────────────────────────────────────┬───────────────┘
           │ JSON/JWT                             │ audio/mpeg (stream)
           ▼                                      ▼
┌──────────────────────────┐           ┌────────────────────────┐
│ FastAPI Gateway (Python) │◄──────────┤ (SSE / Chunked)        │
│  - Auth (JWT/API Key)    │           └────────────────────────┘
│  - Validation (Pydantic) │
│  - OpenAPI / Docs        │
└──────────┬───────────────┘
           │ enqueue / sync call
    ┌──────┴──────┐
    ▼             ▼
┌─────────┐  ┌─────────────────────────────┐
│ Redis   │  │ OmniVoice Worker (Celery)   │
│ (Queue) │  │  - imports omnivoice pkg    │
└─────────┘  │  - GPU/MPS/CPU selectable   │
             │  - chunk-by-chunk yield     │
             └─────┬───────────────────────┘
                   │
                   ▼
        ┌──────────────────────┐
        │ OmniVoice Model      │
        │ (HF snapshot cache)  │
        └──────────────────────┘

사이드카:
- PostgreSQL (메타)
- MinIO (오디오/프롬프트 블롭)
- Prometheus (메트릭, 선택)
- Loki (로그, 선택)
```

### 11.2 기술 스택

| 레이어 | 선택 | 근거 |
|--------|------|------|
| 프론트 | Next.js 15 (App Router), TypeScript, shadcn/ui, Tailwind, wavesurfer.js | 본인 친숙, 한국어 UI, 파형 시각화 |
| 백엔드 | Python 3.11 + FastAPI + Pydantic v2 | OmniVoice 동일 런타임, 비동기 지원 |
| 큐 | Celery + Redis | 프로세스 격리, 배치/스트리밍 지원 |
| DB | PostgreSQL 16 | 관계·JSONB·전문검색 |
| 블롭 | MinIO (S3 호환) | 미래 S3 이관 용이, 오디오 직접 스트림 |
| 리버스 프록시 | Caddy (선택) | HTTPS 자동, basic auth 추가 쉬움 |
| 컨테이너 | Docker Compose v2 | 단일 호스트 원커맨드 기동 |

### 11.3 컨테이너 구성 (Compose)

| 서비스 | 이미지 | 포트 | 볼륨 |
|--------|--------|------|------|
| web | `omnivoice-web/web:latest` | **5320** | — |
| api | `omnivoice-web/api:latest` | **8320** | `./data/hf_cache`, `./data/audio` |
| worker | `omnivoice-web/worker:latest` | — | 위와 공유 + GPU device passthrough |
| redis | `redis:7` | 6379 | `./data/redis` |
| postgres | `postgres:16` | 5432 | `./data/pg` |
| minio | `minio/minio` | 9000/9001 | `./data/minio` |

### 11.4 M4 Max 단일 호스트 고려

- 디바이스: `MPS` 기본, 실패 시 `CPU` 폴백 (설정에서 변경)
- 모델 메모리: 프리로드 시 RAM ~8GB 점유 (첫 요청 지연 방지)
- 동시성: worker concurrency = 1 (단일 모델 인스턴스), Celery prefetch = 1
- HF 캐시: `~/.cache/huggingface` 바인드 마운트 (이미 받아둔 스냅샷 재사용)

---

## 12. UX / UI Requirements

### 12.1 사이트맵

```
/                         대시보드 (최근 생성, 큐, 사용량)
/studio                   TTS 스튜디오 (탭: TTS / Clone / Design / Auto / VC)
/speakers                 화자 라이브러리
/speakers/[id]            화자 상세
/batch                    배치
/batch/[id]               배치 상세
/history                  히스토리
/history/[id]             생성 상세
/projects                 프로젝트 목록
/api-keys                 API Key 관리
/settings                 환경/디바이스/언어
/admin                    관리자 콘솔
/login                    로그인
```

### 12.2 디자인 시스템

- shadcn/ui 컴포넌트, Tailwind v4, Geist 폰트
- 다크 모드 기본 (토글), 라이트 모드 지원
- 접근성: focus ring, aria-live for 큐 상태 변동
- 아이콘: lucide-react

### 12.3 스튜디오 와이어프레임 (ASCII)

```
┌──────────────────────────────────────────────────────────────────┐
│ OmniVoice Studio                               [프로젝트▼] [저장]│
├──────────────────┬───────────────────────────────────────────────┤
│ [TTS] Clone Des. │ 텍스트                                        │
│ Auto  VC         │ ┌───────────────────────────────────────────┐ │
│                  │ │ 안녕하세요, [laughter] 오늘은...           │ │
│ 화자 [spk_01 ▼]  │ │                                           │ │
│ 언어 [ko ▼]      │ └───────────────────────────────────────────┘ │
│                  │ [+ 비언어 태그] [핀인] [음소]   자수: 42     │
│ Basic            │                                               │
│  속도     [1.0]  │ ─────────────── 미리보기 ───────────────      │
│  품질 Fast/Bal*/Q│ ▶ 00:00 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 00:03    │
│  CFG      [2.0]  │ ╿╿┄┊┄╿╿┄┊┄╿╿┄┊┄╿╿ (파형)                     │
│  Denoise  [ON]   │ [다운로드 WAV] [MP3] [재현] [A/B에 추가]      │
│                  │                                               │
│ Advanced ▼       │                                               │
│                  │                                               │
│ [▶ 생성]         │                                               │
└──────────────────┴───────────────────────────────────────────────┘
```

### 12.4 화자 라이브러리 와이어프레임

```
┌──────────────────────────────────────────────────────────────────┐
│ 화자 라이브러리     [+ 신규 등록] [일괄 임포트]  검색: [_______] │
├──────────────────────────────────────────────────────────────────┤
│ ★ | 이름        | 태그         | 샘플       | 마지막 사용 | ⋮   │
│ ★ | 내 기본 한국어 | ko,남성,차분 | ▶ 3s      | 2분 전       | ⋮   │
│   | 영어 나레이터 | en,여성,밝음 | ▶ 5s      | 1일 전       | ⋮   │
│   | 뉴스 앵커    | ko,남성,톤다운| ▶ 4s     | 지난주       | ⋮   │
└──────────────────────────────────────────────────────────────────┘
```

### 12.5 배치 와이어프레임

```
┌──────────────────────────────────────────────────────────────────┐
│ 배치 #12   상태: 진행 중 (37 / 100)   ETA: 4분  [일시정지] [취소]│
├──────────────────────────────────────────────────────────────────┤
│ ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░  37%                            │
│                                                                   │
│ 항목  텍스트                 화자     상태    소요                │
│ 001   안녕하세요, 첫 번째...   spk_01   ✓ 완료  2.1s               │
│ 002   두 번째 문장입니다.      spk_01   ✓ 완료  1.8s               │
│ ...                                                               │
│ 037   진행 중...               spk_01   ▶ 중    ----               │
│ 038   대기 중                  spk_01   ⏳ 대기  ----               │
└──────────────────────────────────────────────────────────────────┘
```

### 12.6 반응형

- 데스크톱 우선, 태블릿(≥768px)까지 기능 동등
- 모바일은 읽기/재생만 (생성 파라미터는 접이식)

---

## 13. Phased Roadmap

> 일정 추정은 본 문서 범위 외. 각 Phase 진입/완료 기준만 정의.

### Phase 1 — Core (필수)
- [ ] §6.1 TTS 스튜디오 (오토 보이스 + 화자 선택)
- [ ] §6.2 화자 등록/리스트 기본 CRUD
- [ ] §6.3 보이스 디자인 폼
- [ ] §8 `/tts`, `/speakers*`, `/health`, `/languages`, `/voice-attributes`
- [ ] §11 Docker Compose로 기동 가능
- [ ] §10 PostgreSQL/MinIO 스키마 마이그레이션
- [ ] 단일 사용자 로그인 + 1개 API Key 발급

### Phase 2 — Operations
- [ ] §6.5 음성→음성 캐스케이드
- [ ] §6.6 배치 (CSV/JSONL/폼)
- [ ] §6.7 스트리밍
- [ ] §7.2 프로젝트, §7.3 히스토리
- [ ] §7.5 관리자 콘솔
- [ ] §9.5 메트릭 `/metrics` 노출
- [ ] 에러 규격 및 재시도

### Phase 3 — Polish
- [ ] §7.3 A/B 비교 플레이어
- [ ] §8 웹훅 + 재시도 큐
- [ ] §12 i18n (영어 번들)
- [ ] 키보드 단축키 전체
- [ ] 히스토리 전문검색
- [ ] seed 고정 (오토 보이스 재현)
- [ ] 외부 노출용 Caddy 리버스 프록시 레시피

### Phase 4 (선택) — Ecosystem
- [ ] Python/TypeScript SDK 생성 (FastAPI `openapi.json` → `openapi-generator`)
- [ ] CLI (`ovweb tts`, `ovweb speakers list`)
- [ ] OpenTelemetry 통합

---

## 14. Success Metrics

### 14.1 기능 도달 체크리스트 (Binary)

| # | 기준 | 검증 |
|---|------|------|
| 1 | 브라우저에서 5분 이내에 첫 TTS 출력 가능 | 수동 시연 |
| 2 | 동일 화자로 10개 생성 → 전부 재생 가능 | UI 동작 |
| 3 | `/v1/tts` cURL 호출 성공 | 쉘 스크립트 |
| 4 | 배치 100건 중단 없이 완료 | 자동 테스트 |
| 5 | 스트리밍 TTFB ≤ 3s (MPS) | 성능 테스트 |
| 6 | Docker Compose 단일 명령 기동 | README 스크립트 |
| 7 | 재기동 후 화자/히스토리 유지 | 수동 확인 |
| 8 | API Key 폐기 후 401 반환 | 자동 테스트 |

### 14.2 기술 SLI

| 지표 | 목표 | 수집 |
|------|------|------|
| `/tts` p95 (≤ 50자) | ≤ 5s (CPU) / ≤ 1s (MPS) | API 미들웨어 |
| 스트리밍 TTFB p95 | ≤ 3s | SSE 최초 청크 타임스탬프 |
| RTF 중앙값 | ≤ 0.5 (CPU) / ≤ 0.1 (MPS) | 워커 계측 |
| 에러율 | < 1% | 4xx/5xx 카운트 |
| 큐 대기 p95 | ≤ 3s | Celery 이벤트 |
| 재기동 후 첫 요청 | ≤ 90s | 모델 워밍업 포함 |

---

## 15. Risks & Mitigations

| # | 리스크 | 영향 | 대응 |
|---|--------|------|------|
| R1 | OmniVoice 모델 업데이트로 `VoiceClonePrompt` 포맷 호환성 깨짐 | 화자 전면 재등록 필요 | 원본 오디오 + 전사 텍스트 보존 → 재추출 스크립트 제공 |
| R2 | Apache 2.0 이지만 상용 재배포 시 고지 의무 | 라이선스 준수 | NOTICE/LICENSE 포함, 문서 하단 고지 |
| R3 | 모델 로드 시 5~10GB VRAM/RAM 요구 | M4 Max에서도 타 앱과 경쟁 | 언로드 옵션, 유휴 N분 후 자동 언로드 설정 |
| R4 | 장문 생성 중 OOM | 결과 손실 | `audio_chunk_threshold` 준수 + 청크 결과 임시 저장 |
| R5 | ffmpeg/pydub 외부 의존 | 포맷 변환 실패 | 컨테이너에 명시 설치, 업로드 mime 화이트리스트 |
| R6 | Whisper 전사 품질 저하 (소음·짧은 샘플) | 화자 복제 품질 하락 | 사용자 수동 편집 강제 허용 |
| R7 | 스트리밍 청크 경계에서 음소 끊김 | 음질 이슈 | 청크 말미 교차 페이드(100ms) 또는 설정 옵션 |
| R8 | 로컬 노출(외부 공개) 시 보안 취약 | 의도치 않은 접근 | 기본 127.0.0.1 바인딩, 외부 노출은 별도 Phase |
| R9 | 단일 디스크 고장 | 화자/히스토리 영구 손실 | `./data` 타임머신/별도 NAS 백업 가이드 (운영 문서 별도) |
| R10 | 엔진 성능(`num_step` 고품질) 설정 시 RTF 악화 | 배치 지연 | 프리셋으로 강제 선택, 관리자 콘솔에서 기본 프리셋 지정 |

---

## 16. Out of Scope

본 제품은 다음을 **의도적으로 제공하지 않는다.** 요구가 들어오면 범위 외로 기각한다.

- 결제·구독·청구·인보이스·쿠폰
- 팀·조직·RBAC·SSO·감사 리포트
- 공개 SaaS 서비스, SLA, 24/7 온콜, 고객 지원 채널
- 모바일 네이티브 앱 (iOS/Android)
- **진성 A→B 음성변환** (OmniVoice 미지원 — STT→TTS 캐스케이드로만 제공, §6.5)
- 감정/스타일 전이 (엔진에 API 부재)
- 오디오 편집기 (컷·페이드·EQ·노이즈 제거 등)
- 음악·효과음·환경음 생성
- 실시간 대화형 양방향 합성 (응답형 대기)
- Fine-tuning·어댑터 학습 (엔진 자체 수정 범위)

---

## 17. Open Questions

1. **화자 공유 포맷**: `.pt` 직접 교환(엔진 버전 결합) vs 원본 오디오+메타 번들(재추출 필요)? — 초기엔 **후자 기본, 전자 옵션**.
2. **오디오 저장 포맷**: WAV 24kHz 원본만 vs WAV+MP3 병행? — 디스크 비용 vs 재생 편의. **MP3 생성 시 on-demand 변환**으로 타협.
3. **외부 노출 지원 여부**: Phase 3에서 Caddy 프리셋을 제공할지, 수동 가이드만 둘지?
4. **모델 업데이트 채널**: HF 최신 자동 폴링 vs 수동 버튼? — 수동 버튼 + 변경로그 표시 권장.
5. **비언어 태그 UI**: 13종을 모두 평면 버튼 vs 카테고리(laughter/sigh/question/surprise/dissatisfaction) 토글? — 후자 권장.
6. **다국어 생성 히스토리 검색**: PostgreSQL 전문검색 vs Meilisearch 별도? — Phase 2 결정.
7. **Whisper 모델 크기**: 엔진 기본 ASR은 경량 모델인지, 별도 Whisper-large 임베드할지? — Phase 2 검증.

---

## 18. References

### 엔진 (Apache 2.0)
- Repo (로컬): `/Users/starhunter/StudyProj/voiceproj/OmniVoice`
- 핵심 API: `omnivoice/models/omnivoice.py:458` `OmniVoice.generate(...)`, `create_voice_clone_prompt(...)`
- 비언어 태그 정의: `omnivoice/models/omnivoice.py:1494` `_NONVERBAL_PATTERN`
- Gradio 데모 (화자 저장 로직 참고): `omnivoice/cli/demo.py`
- 배치 도구 참고: `omnivoice-infer-batch` 엔트리 (pyproject console_scripts)

### 엔진 문서
- 생성 파라미터: `OmniVoice/docs/generation-parameters.md`
- 보이스 디자인 속성: `OmniVoice/docs/voice-design.md`
- 지원 언어 (646): `OmniVoice/docs/languages.md`, `lang_id_name_map.tsv`
- 학습/평가: `OmniVoice/docs/training.md`, `evaluation.md`

### 외부
- OmniVoice 논문: arXiv:2604.00688
- HuggingFace 모델: `k2-fsa/OmniVoice`
- 참고 UX: ElevenLabs, Play.ht, OpenAI TTS (기능군 벤치마크 목적)

### 본 제품 관련
- 계획 문서: `/Users/starhunter/.claude/plans/vectorized-discovering-peacock.md`
- 작성일 현행 실행 상태: `omnivoice-demo` @ `127.0.0.1:8001` (CPU)

---

## 19. MVP Implementation Decisions (v0.2)

> PRD §11의 풀 아키텍처는 프로덕션 타겟. 아래는 Phase 1 MVP에서 **즉시 구동 가능**하도록 단순화한 결정. 인터페이스는 유지하여 추후 교체 가능.

| 영역 | 풀 스펙 (§11) | **MVP 구현** | 교체 시점 |
|------|--------------|-------------|----------|
| DB | PostgreSQL 16 | **SQLite 3** (`./data/app.db`) | Phase 2 — 운영 데이터 누적 시 |
| 블롭 스토리지 | MinIO | **로컬 FS** (`./data/audio/`, `./data/speakers/`) | Phase 2 — 외부 백업 필요 시 |
| 큐 | Celery + Redis | **FastAPI BackgroundTasks** (in-process) | Phase 2 — 배치/스트리밍 본격 도입 시 |
| 엔진 호출 | 동일 프로세스 import | **`subprocess` CLI 래퍼** (엔진 `.venv` 재사용) | Phase 2 — Celery 워커로 이식 |
| 인증 | JWT + API Key (argon2id) | **API Key 고정 헤더** (`.env`의 `OMNIVOICE_API_KEY`) + 단순 세션 쿠키 | Phase 2 — 다중 키/로그인 |
| 관측성 | Prometheus/Loki | **구조화 JSON stdout** | Phase 3 — 외부 공개 시 |
| 리버스 프록시 | Caddy | 없음 (localhost) | Phase 3 |

### 19.1 포트

| 서비스 | 포트 | 용도 |
|--------|------|------|
| Web (Next.js) | **5320** | 브라우저 UI |
| API (FastAPI) | **8320** | REST + OpenAPI (`/docs`) |
| (Phase 2) Redis | 6379 | 큐 |
| (Phase 2) PostgreSQL | 5432 | 메타 |

### 19.2 환경변수 (`.env`)

```env
# 공통
OMNIVOICE_ENGINE_PATH=/Users/starhunter/StudyProj/voiceproj/OmniVoice
OMNIVOICE_ENGINE_PYTHON=/Users/starhunter/StudyProj/voiceproj/OmniVoice/.venv/bin/python
OMNIVOICE_DEVICE=mps           # cpu | mps | cuda
OMNIVOICE_API_KEY=dev-key-change-me

# API
API_HOST=127.0.0.1
API_PORT=8320
DATABASE_URL=sqlite:///./data/app.db
DATA_DIR=./data
CORS_ORIGINS=http://localhost:5320

# Web
NEXT_PUBLIC_API_BASE=http://localhost:8320
```

### 19.3 Phase 1 MVP 스코프 (필수)

- [x] §6.1 TTS 스튜디오 — 텍스트 + 화자 선택 + 기본 파라미터
- [x] §6.2 화자 등록 (오디오 업로드 + 전사 스텁, 수동 편집)
- [x] §6.3 보이스 디자인 폼
- [x] §6.4 오토 보이스
- [x] §7.1 화자 라이브러리 (목록/상세/삭제)
- [x] §7.3 생성 히스토리 (목록/상세/재현)
- [x] §8 엔드포인트: `/health`, `/tts`, `/speakers`, `/generations`, `/languages`, `/voice-attributes`, `/api-keys` (읽기만)
- [x] §10 SQLite 기반 최소 스키마 (users, api_keys, speakers, generations, projects)
- [x] §12 사이트맵 최소: `/`, `/studio`, `/speakers`, `/history`, `/settings`

### 19.4 MVP 제외 (Phase 2 이후)

- §6.5 VC 캐스케이드, §6.6 배치, §6.7 스트리밍
- §7.4 API Key 발급/회전 UI (MVP는 `.env`의 고정 키 1개)
- §7.5 관리자 콘솔
- §8.3 웹훅
- §9.5 Prometheus/OTel
- 다국어 UI (ko 단일)

---

## 20. Repository Layout

```
omnivoice-web/
├── README.md
├── package.json                # pnpm workspace 루트 (scripts: dev, build, start)
├── pnpm-workspace.yaml
├── .env.example
├── .gitignore
├── docs/
│   └── PRD.md
├── data/                       # gitignored (런타임 생성물)
│   ├── app.db                  # SQLite
│   ├── audio/                  # 생성 오디오
│   ├── speakers/               # 화자 원본 + .pt 블롭
│   └── uploads/                # 임시 업로드
├── apps/
│   ├── api/                    # Python FastAPI (포트 8320)
│   │   ├── pyproject.toml
│   │   ├── app/
│   │   │   ├── main.py         # FastAPI entrypoint
│   │   │   ├── config.py       # 설정 로딩
│   │   │   ├── db.py           # SQLAlchemy + SQLite
│   │   │   ├── auth.py         # API Key 의존성
│   │   │   ├── schemas.py      # Pydantic 모델
│   │   │   ├── models.py       # ORM 모델
│   │   │   ├── storage.py      # 로컬 파일 스토어
│   │   │   ├── engine/
│   │   │   │   ├── __init__.py
│   │   │   │   └── omnivoice_adapter.py   # subprocess 어댑터
│   │   │   └── routers/
│   │   │       ├── health.py
│   │   │       ├── tts.py
│   │   │       ├── speakers.py
│   │   │       ├── generations.py
│   │   │       ├── meta.py     # languages, voice-attributes
│   │   │       └── assets.py   # 오디오 서빙
│   │   └── scripts/
│   │       └── engine_cli.py   # OmniVoice 엔진 .venv에서 실행될 브리지
│   └── web/                    # Next.js 15 (포트 5320)
│       ├── package.json
│       ├── next.config.ts
│       ├── tsconfig.json
│       ├── tailwind.config.ts
│       ├── postcss.config.mjs
│       ├── src/
│       │   ├── app/
│       │   │   ├── layout.tsx
│       │   │   ├── page.tsx             # 대시보드
│       │   │   ├── studio/page.tsx
│       │   │   ├── speakers/page.tsx
│       │   │   ├── history/page.tsx
│       │   │   └── settings/page.tsx
│       │   ├── components/
│       │   │   ├── ui/                  # shadcn 컴포넌트
│       │   │   ├── sidebar.tsx
│       │   │   ├── studio-form.tsx
│       │   │   ├── speakers-table.tsx
│       │   │   └── audio-player.tsx
│       │   ├── lib/
│       │   │   ├── api.ts               # API 클라이언트
│       │   │   └── types.ts
│       │   └── styles/globals.css
│       └── public/
└── scripts/
    ├── dev.sh                  # api + web 동시 기동
    └── bootstrap.sh            # 초기 .env/data 디렉토리 생성
```

---

*End of Document — Draft v0.2 (MVP 구현 스펙 포함)*
