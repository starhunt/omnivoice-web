"""OpenAI-compatible audio speech endpoint."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import verify_api_key
from ..config import Settings, get_settings
from ..db import get_session
from ..job_runner import synthesize_podcast_request
from ..models import Generation, Speaker
from ..schemas import PodcastJobRequest, PodcastSegment, TTSParams
from .elevenlabs_compat import (
    ElevenLabsTTSRequest,
    ElevenLabsVoiceSettings,
    _audio_response,
    _synthesize_audio_file,
)

router = APIRouter(tags=["openai-compat"], dependencies=[Depends(verify_api_key)])


OpenAIFormat = Literal["mp3", "wav"]


class OpenAISpeechRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str = "tts-1"
    input: str = Field(min_length=1, max_length=10_000)
    voice: str = "alloy"
    response_format: OpenAIFormat = "mp3"
    speed: float = Field(default=1.0, ge=0.25, le=2.0)


def _list_speakers(session: Session) -> list[Speaker]:
    stmt = (
        select(Speaker)
        .where(Speaker.deleted_at.is_(None))
        .order_by(Speaker.is_favorite.desc(), Speaker.created_at.desc())
    )
    return list(session.scalars(stmt))


def _resolve_voice(session: Session, voice: str | None) -> Speaker:
    rows = _list_speakers(session)
    if not rows:
        raise HTTPException(status_code=404, detail="voice_not_found")
    if voice:
        needle = voice.strip().lower()
        for speaker in rows:
            if speaker.id == voice or speaker.name.lower() == needle:
                return speaker
        for speaker in rows:
            if needle and needle in speaker.name.lower():
                return speaker
    return rows[0]


def _xml_text(node: ET.Element) -> str:
    parts: list[str] = []
    if node.text:
        parts.append(node.text)
    for child in node:
        if child.tag.endswith("break"):
            parts.append(" ")
        else:
            parts.append(_xml_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _strip_ssml(text: str) -> str:
    if "<" not in text:
        return text
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return re.sub(r"<[^>]+>", "", text)
    return _xml_text(root).strip()


def _ssml_voice_segments(session: Session, ssml: str) -> list[PodcastSegment]:
    if "<voice" not in ssml:
        return []
    try:
        root = ET.fromstring(ssml)
    except ET.ParseError:
        return []
    segments: list[PodcastSegment] = []
    default_speaker = _resolve_voice(session, None)
    for node in root.iter():
        if not node.tag.endswith("voice"):
            continue
        voice_name = node.attrib.get("name") or node.attrib.get("speaker") or default_speaker.name
        speaker = _resolve_voice(session, voice_name)
        text = _xml_text(node).strip()
        if text:
            segments.append(PodcastSegment(speaker_id=speaker.id, label=voice_name, text=text))
    return segments


def _synthesize_openai_ssml(
    *,
    req: OpenAISpeechRequest,
    segments: list[PodcastSegment],
    settings: Settings,
    session: Session,
) -> tuple[Path, Generation]:
    gen_text = "\n\n".join(f"{seg.label}: {seg.text}" for seg in segments)
    gen = Generation(
        mode="podcast",
        text=gen_text,
        language=None,
        speaker_id=None,
        params_json={
            "openai_model": req.model,
            "voice": req.voice,
            "response_format": req.response_format,
            "speed": req.speed,
            "ssml": True,
        },
        audio_format=req.response_format,
        status="running",
    )
    session.add(gen)
    session.commit()
    session.refresh(gen)
    podcast_req = PodcastJobRequest(
        segments=segments,
        language=None,
        params=TTSParams(speed=req.speed),
        format=req.response_format,
        pause_ms=250,
    )
    out_path, _duration, _elapsed = synthesize_podcast_request(
        settings=settings,
        session=session,
        gen=gen,
        req=podcast_req,
    )
    return out_path, gen


@router.post("/audio/speech")
def create_speech(
    req: OpenAISpeechRequest,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> FileResponse:
    ssml_segments = _ssml_voice_segments(session, req.input)
    if ssml_segments:
        path, gen = _synthesize_openai_ssml(
            req=req,
            segments=ssml_segments,
            settings=settings,
            session=session,
        )
        return _audio_response(path, req.response_format, gen, gen.text)

    speaker = _resolve_voice(session, req.voice)
    text = _strip_ssml(req.input)
    eleven_req = ElevenLabsTTSRequest(
        text=text,
        model_id=req.model,
        language_code=None,
        voice_settings=ElevenLabsVoiceSettings(speed=req.speed),
    )
    path, fmt, gen = _synthesize_audio_file(
        voice_id=speaker.id,
        req=eleven_req,
        output_format=req.response_format,
        settings=settings,
        session=session,
    )
    return _audio_response(path, fmt, gen, text)
