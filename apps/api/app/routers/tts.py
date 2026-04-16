"""TTS 동기 합성 엔드포인트."""

from __future__ import annotations

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
    synthesize,
    transcribe_ref_audio,
)
from ..models import Generation, Speaker
from ..schemas import TTSRequest, TTSResponse
from ..storage import audio_path_for, relpath

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tts"], dependencies=[Depends(verify_api_key)])


def _resolve_mode(req: TTSRequest) -> str:
    if req.speaker_id:
        return "tts"
    if req.design:
        return "design"
    if req.instruct:
        return "design"
    return "auto"


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

    # 참조 오디오만 있고 transcript가 없으면 합성 전에 Whisper로 한 번만 전사해 저장한다.
    # 합성 subprocess와 Whisper subprocess를 분리해 MPS 메모리 피크를 낮추는 것이 목적.
    if speaker and speaker.source_audio_path and not (speaker.ref_transcript or "").strip():
        ref_abs = settings.data_dir / speaker.source_audio_path
        if ref_abs.exists():
            try:
                logger.info("speaker %s has no ref_transcript — transcribing once", speaker.id)
                tr = transcribe_ref_audio(settings, ref_abs)
                if tr:
                    speaker.ref_transcript = tr
                    session.commit()
                    session.refresh(speaker)
                    logger.info("speaker %s transcript saved (%d chars)", speaker.id, len(tr))
                # transcribe subprocess 종료 후 MPS pool이 OS에 회수될 시간 확보
                # (연속 subprocess 기동 시 MPS 메모리 경합으로 인한 SIGKILL 방지)
                time.sleep(2)
            except EngineError as exc:
                # 전사 실패해도 합성은 시도 — 기존 동작 유지 (Whisper가 합성 중 실행됨)
                logger.warning("pre-transcribe failed for speaker %s: %s", speaker.id, exc)

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
        ref_audio_path: Path | None = None
        if speaker and speaker.source_audio_path:
            ref_audio_path = settings.data_dir / speaker.source_audio_path

        duration_sec = synthesize(
            settings=settings,
            text=req.text,
            language=req.language,
            instruct=instruct,
            ref_audio_path=ref_audio_path,
            ref_transcript=speaker.ref_transcript if speaker else None,
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
