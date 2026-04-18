# Provider 등록 관리

작성일: 2026-04-18

## 목적

Qwen3-TTS와 OmniVoice를 다른 서버/프로세스에서 호출하는 경우 `.env`를 직접 수정하고 API를 재시작하는 방식만으로는 운영이 불편하다. 이번 변경으로 설정 화면과 API에서 Provider를 등록/수정/테스트할 수 있게 했다.

## 동작 방식

- 서버 시작 시 현재 `.env` 값을 읽어 기본 Provider 2개를 DB에 seed한다.
  - `OmniVoice Local`
  - `Qwen3-TTS A100`
- 이후 요청 처리 시 DB의 기본 Provider 설정이 `.env`보다 우선한다.
- 같은 엔진에 Provider를 여러 개 등록할 수 있고, `is_default=true`인 Provider가 해당 엔진의 활성 Provider가 된다.
- Provider를 비활성화하면 해당 엔진은 사용할 수 없는 상태로 평가된다.

## API

```http
GET /v1/providers
POST /v1/providers
PATCH /v1/providers/{provider_id}
DELETE /v1/providers/{provider_id}
POST /v1/providers/{provider_id}/test
```

Qwen3-TTS Provider 예:

```json
{
  "name": "Qwen3-TTS A100",
  "engine": "qwen3-tts",
  "enabled": true,
  "is_default": true,
  "config": {
    "base_url": "http://168.131.216.36:8001",
    "clone_base_url": "http://168.131.216.36:8002",
    "model": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
    "clone_model": "Qwen/Qwen3-TTS-12Hz-0.6B-Base",
    "default_speaker": "sohee"
  }
}
```

OmniVoice Provider 예:

```json
{
  "name": "OmniVoice Local",
  "engine": "omnivoice",
  "enabled": true,
  "is_default": true,
  "config": {
    "engine_path": "/Users/starhunter/StudyProj/voiceproj/OmniVoice",
    "engine_python": "/Users/starhunter/StudyProj/voiceproj/OmniVoice/.venv/bin/python",
    "device": "mps"
  }
}
```

## UI

설정 페이지에서 다음 작업을 할 수 있다.

- Qwen Provider 추가
- OmniVoice Provider 추가
- URL/API key/model/device 수정
- 저장
- 연결 테스트
- 삭제
- 같은 엔진의 기본 Provider 지정

## 검증

로컬에서 다음을 확인했다.

- 새 DB 테이블 생성 및 `.env` 기반 Provider seed
- `GET /v1/providers` 정상 응답
- `POST /v1/providers/{id}/test`로 Qwen3-TTS Provider live 확인
- `/v1/engines`가 DB Provider 값을 적용해 Qwen 서버를 감지
- `/v1/tts`가 DB Provider 설정을 통해 Qwen 기본 voice 합성 성공

## 주의점

- Provider 설정 변경은 새 요청부터 즉시 반영된다. API 프로세스 재시작은 필요하지 않다.
- DB가 비어 있는 최초 실행에만 `.env` 값이 seed된다. 이후 `.env`를 바꿔도 기존 Provider row가 자동 갱신되지는 않는다.
- Provider의 API key는 현재 DB에 평문 저장된다. 다중 사용자/외부 노출 운영 전에는 암호화 또는 secret store 연동이 필요하다.
