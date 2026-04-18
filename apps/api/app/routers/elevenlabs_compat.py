"""ElevenLabs-compatible REST shim.

This is not a full ElevenLabs clone. It implements the common endpoints used by
many clients when only a base URL/API key/voice ID can be configured.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import verify_api_key
from ..config import Settings, get_settings
from ..db import get_session
from ..engine.omnivoice_adapter import EngineError, synthesize
from ..engine.qwen3_tts_adapter import synthesize as synthesize_qwen3_tts
from ..engine.registry import ENGINE_QWEN3_TTS, resolve_engine
from ..job_runner import synthesize_podcast_request
from ..models import Generation, Speaker
from ..provider_settings import effective_settings
from ..schemas import PodcastJobRequest, PodcastSegment, TTSParams
from ..storage import audio_path_for, relpath
from .tts import ensure_speaker_voice_prompt

router_v1 = APIRouter(tags=["elevenlabs-compat"], dependencies=[Depends(verify_api_key)])
router_v2 = APIRouter(tags=["elevenlabs-compat"], dependencies=[Depends(verify_api_key)])


class ElevenLabsVoiceSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    stability: float | None = None
    similarity_boost: float | None = None
    style: float | None = None
    use_speaker_boost: bool | None = None
    speed: float | None = Field(default=None, ge=0.25, le=2.0)


class ElevenLabsTTSRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = Field(min_length=1, max_length=10_000)
    model_id: str | None = None
    language_code: str | None = None
    voice_settings: ElevenLabsVoiceSettings | None = None
    seed: int | None = None
    previous_text: str | None = None
    next_text: str | None = None


class ElevenLabsDialogueInput(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = Field(min_length=1, max_length=4_000)
    voice_id: str = Field(min_length=1)


class ElevenLabsDialogueRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    inputs: list[ElevenLabsDialogueInput] = Field(min_length=1, max_length=200)
    model_id: str | None = "eleven_v3"
    language_code: str | None = None
    settings: dict[str, Any] | None = None
    seed: int | None = None
    apply_text_normalization: str | None = "auto"


def _audio_format(output_format: str | None) -> str:
    if output_format and output_format.startswith("wav"):
        return "wav"
    # ElevenLabs defaults to MP3, so keep compatibility default as MP3.
    return "mp3"


def _media_type(fmt: str) -> str:
    return "audio/mpeg" if fmt == "mp3" else "audio/wav"


def _voice_settings_to_params(settings_in: ElevenLabsVoiceSettings | None) -> TTSParams:
    params = TTSParams()
    if settings_in and settings_in.speed is not None:
        params.speed = settings_in.speed
    return params


def _preview_url(request: Request, speaker: Speaker) -> str | None:
    if not speaker.source_audio_path:
        return None
    return str(request.url_for("get_speaker_ref", speaker_id=speaker.id))


def _voice_payload(request: Request, speaker: Speaker) -> dict[str, Any]:
    labels = {
        "language": speaker.language_hint or "",
        "source": "omnivoice-web",
    }
    for tag in speaker.tags or []:
        labels[str(tag)] = "true"
    return {
        "voice_id": speaker.id,
        "name": speaker.name,
        "samples": [],
        "category": "cloned" if speaker.source_audio_path else "generated",
        "fine_tuning": {"state": "fine_tuned"},
        "labels": labels,
        "description": speaker.note,
        "preview_url": _preview_url(request, speaker),
        "available_for_tiers": [],
        "settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.0,
            "use_speaker_boost": True,
            "speed": 1.0,
        },
        "sharing": None,
        "high_quality_base_model_ids": ["eleven_multilingual_v2"],
        "safety_control": None,
        "voice_verification": None,
        "permission_on_resource": "admin",
        "is_owner": True,
        "is_legacy": False,
        "is_mixed": False,
        "created_at_unix": int(speaker.created_at.timestamp()) if speaker.created_at else None,
    }


def _list_speaker_rows(session: Session) -> list[Speaker]:
    stmt = (
        select(Speaker)
        .where(Speaker.deleted_at.is_(None))
        .order_by(Speaker.is_favorite.desc(), Speaker.created_at.desc())
    )
    return list(session.scalars(stmt))


def _synthesize_audio_file(
    *,
    voice_id: str,
    req: ElevenLabsTTSRequest,
    output_format: str | None,
    settings: Settings,
    session: Session,
) -> tuple[Path, str, Generation]:
    settings = effective_settings(settings, session)
    speaker = session.get(Speaker, voice_id)
    if not speaker or speaker.deleted_at is not None:
        raise HTTPException(status_code=404, detail={"status": "voice_not_found", "message": "Voice not found"})

    fmt = _audio_format(output_format)
    params = _voice_settings_to_params(req.voice_settings)
    speaker_prompt_only = bool(speaker.prompt_blob_path and not speaker.source_audio_path)
    engine_id = resolve_engine(
        settings,
        "auto",
        speaker_has_omnivoice_prompt_only=speaker_prompt_only,
    )
    ref_audio_path: Path | None = None
    voice_prompt_path: Path | None = None
    if engine_id == ENGINE_QWEN3_TTS:
        if not speaker.source_audio_path:
            raise HTTPException(status_code=400, detail="qwen3_tts_requires_speaker_ref_audio")
        ref_audio_path = settings.data_dir / speaker.source_audio_path if speaker.source_audio_path else None
    else:
        ref_audio_path, voice_prompt_path = ensure_speaker_voice_prompt(
            settings=settings,
            session=session,
            speaker=speaker,
            preprocess_prompt=params.preprocess_prompt,
        )

    gen = Generation(
        mode="tts",
        text=req.text,
        language=req.language_code,
        speaker_id=speaker.id,
        params_json={
            **params.model_dump(exclude_none=False),
            "elevenlabs_model_id": req.model_id,
            "elevenlabs_output_format": output_format,
            "engine": engine_id,
        },
        audio_format=fmt,
        status="running",
    )
    session.add(gen)
    session.commit()
    session.refresh(gen)

    out_path = audio_path_for(settings, gen.id, fmt)
    started = time.perf_counter()
    try:
        if engine_id == ENGINE_QWEN3_TTS:
            duration_sec = synthesize_qwen3_tts(
                settings=settings,
                text=req.text,
                language=req.language_code,
                instruct=None,
                ref_audio_path=ref_audio_path,
                ref_transcript=speaker.ref_transcript,
                params=params,
                out_path=out_path,
            )
        else:
            duration_sec = synthesize(
                settings=settings,
                text=req.text,
                language=req.language_code,
                instruct=None,
                ref_audio_path=ref_audio_path,
                ref_transcript=speaker.ref_transcript,
                voice_prompt_path=voice_prompt_path,
                params=params,
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
    speaker.usage_count = (speaker.usage_count or 0) + 1
    speaker.last_used_at = gen.finished_at
    session.commit()
    session.refresh(gen)
    return out_path, fmt, gen


def _synthesize_dialogue_file(
    *,
    req: ElevenLabsDialogueRequest,
    output_format: str | None,
    settings: Settings,
    session: Session,
) -> tuple[Path, str, Generation, str]:
    settings = effective_settings(settings, session)
    fmt = _audio_format(output_format)
    segments: list[PodcastSegment] = []
    for item in req.inputs:
        speaker = session.get(Speaker, item.voice_id)
        if not speaker or speaker.deleted_at is not None:
            raise HTTPException(
                status_code=404,
                detail={"status": "voice_not_found", "message": f"Voice not found: {item.voice_id}"},
            )
        segments.append(
            PodcastSegment(
                speaker_id=speaker.id,
                label=speaker.name,
                text=item.text,
                language=req.language_code,
            )
        )

    podcast_req = PodcastJobRequest(
        title=None,
        segments=segments,
        language=req.language_code,
        params=TTSParams(),
        format=fmt,  # type: ignore[arg-type]
        pause_ms=250,
    )
    text = "\n\n".join(f"{seg.label}: {seg.text}" if seg.label else seg.text for seg in segments)
    gen = Generation(
        mode="podcast",
        text=text,
        language=req.language_code,
        speaker_id=None,
        params_json={
            "elevenlabs_model_id": req.model_id,
            "elevenlabs_dialogue": req.model_dump(mode="json"),
            "format": fmt,
        },
        audio_format=fmt,
        status="running",
    )
    session.add(gen)
    session.commit()
    session.refresh(gen)
    out_path, _duration, _elapsed = synthesize_podcast_request(
        settings=settings,
        session=session,
        gen=gen,
        req=podcast_req,
    )
    return out_path, fmt, gen, text


def _audio_response(path: Path, fmt: str, gen: Generation, text: str) -> FileResponse:
    return FileResponse(
        path,
        media_type=_media_type(fmt),
        filename=path.name,
        headers={
            "request-id": gen.id,
            "x-request-id": gen.id,
            "x-character-count": str(len(text)),
        },
    )


@router_v1.get("/voices")
def list_voices_v1(request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    voices = [_voice_payload(request, speaker) for speaker in _list_speaker_rows(session)]
    return {"voices": voices}


@router_v2.get("/voices")
def list_voices_v2(
    request: Request,
    page_size: int = Query(default=10, ge=1, le=100),
    search: str | None = None,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = _list_speaker_rows(session)
    if search:
        needle = search.lower()
        rows = [speaker for speaker in rows if needle in speaker.name.lower()]
    selected = rows[:page_size]
    return {
        "voices": [_voice_payload(request, speaker) for speaker in selected],
        "has_more": len(rows) > len(selected),
        "total_count": len(rows),
        "next_page_token": None,
    }


@router_v1.get("/voices/{voice_id}")
def get_voice(request: Request, voice_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    speaker = session.get(Speaker, voice_id)
    if not speaker or speaker.deleted_at is not None:
        raise HTTPException(status_code=404, detail={"status": "voice_not_found", "message": "Voice not found"})
    return _voice_payload(request, speaker)


@router_v1.get("/models")
def list_models() -> list[dict[str, Any]]:
    return [
        {
            "model_id": "eleven_multilingual_v2",
            "name": "OmniVoice compatibility model",
            "can_do_text_to_speech": True,
            "can_do_voice_conversion": False,
            "can_use_style": False,
            "can_use_speaker_boost": True,
            "serves_pro_voices": True,
            "token_cost_factor": 1.0,
            "description": "Mapped to the local OmniVoice engine.",
        },
        {
            "model_id": "eleven_flash_v2_5",
            "name": "OmniVoice compatibility model",
            "can_do_text_to_speech": True,
            "can_do_voice_conversion": False,
            "can_use_style": False,
            "can_use_speaker_boost": True,
            "serves_pro_voices": True,
            "token_cost_factor": 1.0,
            "description": "Mapped to the local OmniVoice engine.",
        },
        {
            "model_id": "eleven_v3",
            "name": "OmniVoice compatibility model",
            "can_do_text_to_speech": True,
            "can_do_voice_conversion": False,
            "can_use_style": False,
            "can_use_speaker_boost": True,
            "serves_pro_voices": True,
            "token_cost_factor": 1.0,
            "description": "Mapped to the local OmniVoice engine.",
        },
    ]


@router_v1.post("/text-to-speech/{voice_id}")
def text_to_speech(
    voice_id: str,
    req: ElevenLabsTTSRequest,
    output_format: str | None = Query(default="mp3_44100_128"),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> FileResponse:
    path, fmt, gen = _synthesize_audio_file(
        voice_id=voice_id,
        req=req,
        output_format=output_format,
        settings=settings,
        session=session,
    )
    return _audio_response(path, fmt, gen, req.text)


@router_v1.post("/text-to-speech/{voice_id}/stream")
def text_to_speech_stream(
    voice_id: str,
    req: ElevenLabsTTSRequest,
    output_format: str | None = Query(default="mp3_44100_128"),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> FileResponse:
    # Current engine is batch-oriented. Return the generated audio bytes through
    # the streaming-compatible path after synthesis completes.
    path, fmt, gen = _synthesize_audio_file(
        voice_id=voice_id,
        req=req,
        output_format=output_format,
        settings=settings,
        session=session,
    )
    return _audio_response(path, fmt, gen, req.text)


@router_v1.post("/text-to-dialogue")
def text_to_dialogue(
    req: ElevenLabsDialogueRequest,
    output_format: str | None = Query(default="mp3_44100_128"),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> FileResponse:
    path, fmt, gen, text = _synthesize_dialogue_file(
        req=req,
        output_format=output_format,
        settings=settings,
        session=session,
    )
    return _audio_response(path, fmt, gen, text)


@router_v1.post("/text-to-dialogue/stream")
def text_to_dialogue_stream(
    req: ElevenLabsDialogueRequest,
    output_format: str | None = Query(default="mp3_44100_128"),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> FileResponse:
    path, fmt, gen, text = _synthesize_dialogue_file(
        req=req,
        output_format=output_format,
        settings=settings,
        session=session,
    )
    return _audio_response(path, fmt, gen, text)
