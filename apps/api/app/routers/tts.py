"""TTS 동기 합성 엔드포인트."""

from __future__ import annotations

import hashlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import verify_api_key
from ..config import Settings, get_settings
from ..db import get_session
from ..engine.omnivoice_adapter import (
    EngineError,
    build_instruct_from_design,
    prepare_voice_clone_prompt,
    synthesize,
    transcribe_ref_audio,
)
from ..models import Generation, Speaker
from ..schemas import TTSRequest, TTSResponse
from ..storage import audio_path_for, relpath

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tts"], dependencies=[Depends(verify_api_key)])


def _prompt_cache_path(
    settings: Settings,
    speaker: Speaker,
    ref_abs: Path,
    *,
    preprocess_prompt: bool,
) -> Path:
    """Return a cache path tied to the current reference audio and transcript."""
    stat = ref_abs.stat()
    ref_text = (speaker.ref_transcript or "").strip()
    key = "\n".join(
        [
            str(ref_abs),
            str(stat.st_size),
            str(stat.st_mtime_ns),
            ref_text,
            f"preprocess={int(preprocess_prompt)}",
        ]
    )
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return settings.speakers_dir / speaker.id / f"prompt-{digest}.pt"


def _resolve_mode(req: TTSRequest) -> str:
    if req.speaker_id:
        return "tts"
    if req.design:
        return "design"
    if req.instruct:
        return "design"
    return "auto"


def ensure_speaker_voice_prompt(
    *,
    settings: Settings,
    session: Session,
    speaker: Speaker | None,
    preprocess_prompt: bool,
) -> tuple[Path | None, Path | None]:
    """Ensure transcript/prompt cache for a speaker and return ref/prompt paths."""
    if not speaker:
        return None, None

    prompt_abs = settings.data_dir / speaker.prompt_blob_path if speaker.prompt_blob_path else None
    if prompt_abs and prompt_abs.exists() and not speaker.source_audio_path:
        return None, prompt_abs

    if not speaker.source_audio_path:
        return None, None

    ref_abs = settings.data_dir / speaker.source_audio_path
    if prompt_abs and prompt_abs.exists() and "omnivoice-demo" in (speaker.tags or []):
        return ref_abs if ref_abs.exists() else None, prompt_abs

    if not ref_abs.exists():
        return ref_abs, prompt_abs if prompt_abs and prompt_abs.exists() else None

    # 참조 오디오만 있고 transcript가 없으면 합성 전에 Whisper로 한 번만 전사해 저장한다.
    # 합성 subprocess와 Whisper subprocess를 분리해 MPS 메모리 피크를 낮추는 것이 목적.
    if not (speaker.ref_transcript or "").strip():
        try:
            logger.info("speaker %s has no ref_transcript — transcribing once", speaker.id)
            tr = transcribe_ref_audio(settings, ref_abs)
            if tr:
                speaker.ref_transcript = tr
                session.commit()
                session.refresh(speaker)
                logger.info("speaker %s transcript saved (%d chars)", speaker.id, len(tr))
            # transcribe subprocess 종료 후 MPS pool이 OS에 회수될 시간 확보
            time.sleep(2)
        except EngineError as exc:
            # 전사 실패해도 합성은 시도 — 기존 동작 유지 (Whisper가 합성 중 실행됨)
            logger.warning("pre-transcribe failed for speaker %s: %s", speaker.id, exc)

    # 등록 화자는 참조 오디오를 매 합성/매 청크마다 다시 토큰화하지 않고, OmniVoice의
    # 재사용 가능한 VoiceClonePrompt를 파일로 캐시한다. 장문 화자복제에서는 이 캐시가
    # 메모리 피크를 낮추고 모든 청크가 같은 화자 prompt를 쓰도록 보장한다.
    prompt_abs = _prompt_cache_path(
        settings,
        speaker,
        ref_abs,
        preprocess_prompt=preprocess_prompt,
    )
    prompt_rel = str(prompt_abs.relative_to(settings.data_dir))
    if speaker.prompt_blob_path != prompt_rel or not prompt_abs.exists():
        try:
            logger.info("preparing voice clone prompt for speaker %s", speaker.id)
            ref_text = prepare_voice_clone_prompt(
                settings,
                ref_audio_path=ref_abs,
                ref_transcript=speaker.ref_transcript,
                out_path=prompt_abs,
                preprocess_prompt=preprocess_prompt,
            )
            speaker.prompt_blob_path = prompt_rel
            if ref_text and not (speaker.ref_transcript or "").strip():
                speaker.ref_transcript = ref_text
            session.commit()
            session.refresh(speaker)
            logger.info("speaker %s prompt cached: %s", speaker.id, speaker.prompt_blob_path)
            time.sleep(2)
        except EngineError as exc:
            # 캐시 생성 실패 시에도 기존 ref_audio 경로로 합성 시도. 실패 원인은 generation에 기록된다.
            logger.warning("prepare prompt failed for speaker %s: %s", speaker.id, exc)
            return ref_abs, None

    return ref_abs, prompt_abs if prompt_abs.exists() else None


@router.post("/tts", response_model=TTSResponse)
def post_tts(
    req: TTSRequest,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> TTSResponse:
    # 화자 조회
    speaker: Speaker | None = None
    if req.speaker_id:
        speaker = session.get(Speaker, req.speaker_id)
        if not speaker or speaker.deleted_at is not None:
            raise HTTPException(status_code=404, detail="speaker_not_found")

    ref_audio_path, voice_prompt_path = ensure_speaker_voice_prompt(
        settings=settings,
        session=session,
        speaker=speaker,
        preprocess_prompt=req.params.preprocess_prompt,
    )

    instruct = req.instruct or (
        build_instruct_from_design(req.design.model_dump(exclude_none=True))
        if req.design
        else None
    )

    gen = Generation(
        project_id=req.project_id,
        mode=_resolve_mode(req),
        text=req.text,
        language=req.language,
        speaker_id=req.speaker_id,
        instruct=instruct,
        params_json=req.params.model_dump(exclude_none=False),
        audio_format=req.format,
        status="running",
    )
    session.add(gen)
    session.commit()
    session.refresh(gen)

    out_path: Path = audio_path_for(settings, gen.id, req.format)
    started = time.perf_counter()
    try:
        duration_sec = synthesize(
            settings=settings,
            text=req.text,
            language=req.language,
            instruct=instruct,
            ref_audio_path=ref_audio_path,
            ref_transcript=speaker.ref_transcript if speaker else None,
            voice_prompt_path=voice_prompt_path,
            params=req.params,
            out_path=out_path,
        )
    except EngineError as exc:
        gen.status = "failed"
        gen.error = str(exc)
        gen.finished_at = datetime.now(timezone.utc)
        session.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    elapsed = time.perf_counter() - started
    gen.audio_path = relpath(settings, out_path)
    gen.duration_sec = duration_sec
    gen.rtf = (elapsed / duration_sec) if duration_sec and duration_sec > 0 else None
    gen.status = "succeeded"
    gen.finished_at = datetime.now(timezone.utc)

    if speaker:
        speaker.usage_count = (speaker.usage_count or 0) + 1
        speaker.last_used_at = gen.finished_at

    session.commit()
    session.refresh(gen)

    return TTSResponse(
        generation_id=gen.id,
        audio_url=f"/v1/assets/{gen.id}.{req.format}",
        duration_sec=gen.duration_sec,
        rtf=gen.rtf,
        status=gen.status,
        created_at=gen.created_at,
    )
