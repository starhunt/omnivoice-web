"""Gemini-style generateContent TTS compatibility endpoint."""

from __future__ import annotations

import base64
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import verify_api_key
from ..config import Settings, get_settings
from ..db import get_session
from ..job_runner import synthesize_podcast_request
from ..models import Generation, Speaker
from ..provider_settings import effective_settings
from ..schemas import PodcastJobRequest, PodcastSegment, TTSParams

router = APIRouter(tags=["gemini-compat"], dependencies=[Depends(verify_api_key)])

_LABEL_RE = re.compile(r"^\s*([A-Za-z0-9가-힣 _.-]{1,60})\s*[:：]\s*(.*)$")


class GeminiGenerateContentRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    contents: Any
    config: dict[str, Any] | None = None
    generationConfig: dict[str, Any] | None = None


def _speaker_rows(session: Session) -> list[Speaker]:
    stmt = (
        select(Speaker)
        .where(Speaker.deleted_at.is_(None))
        .order_by(Speaker.is_favorite.desc(), Speaker.created_at.desc())
    )
    return list(session.scalars(stmt))


def _speaker_by_ref(session: Session, ref: str | None, fallback_index: int = 0) -> Speaker:
    rows = _speaker_rows(session)
    if not rows:
        raise HTTPException(status_code=404, detail="voice_not_found")
    if ref:
        needle = ref.strip().lower()
        for speaker in rows:
            if speaker.id == ref or speaker.name.lower() == needle:
                return speaker
        for speaker in rows:
            if needle and needle in speaker.name.lower():
                return speaker
    return rows[min(fallback_index, len(rows) - 1)]


def _extract_text(contents: Any) -> str:
    if isinstance(contents, str):
        return contents
    if isinstance(contents, dict):
        if "text" in contents and isinstance(contents["text"], str):
            return contents["text"]
        parts = contents.get("parts")
        if isinstance(parts, list):
            return "\n".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
    if isinstance(contents, list):
        chunks: list[str] = []
        for item in contents:
            extracted = _extract_text(item)
            if extracted:
                chunks.append(extracted)
        return "\n".join(chunks)
    return str(contents or "")


def _voice_ref_from_config(config: dict[str, Any], index: int) -> str | None:
    if "speakerId" in config:
        return str(config.get("speakerId"))
    voice_config = config.get("voiceConfig") or config.get("voice_config") or {}
    if isinstance(voice_config, dict):
        prebuilt = voice_config.get("prebuiltVoiceConfig") or voice_config.get("prebuilt_voice_config") or {}
        if isinstance(prebuilt, dict):
            voice_name = prebuilt.get("voiceName") or prebuilt.get("voice_name")
            if voice_name:
                # Gemini prebuilt names are not local speaker IDs. If they do not
                # match a local speaker name, fallback by position below.
                return str(voice_name)
    return None


def _speaker_config_map(session: Session, request_config: dict[str, Any] | None) -> dict[str, Speaker]:
    speech_config = (request_config or {}).get("speechConfig") or (request_config or {}).get("speech_config") or {}
    multi = speech_config.get("multiSpeakerVoiceConfig") or speech_config.get("multi_speaker_voice_config") or {}
    configs = multi.get("speakerVoiceConfigs") or multi.get("speaker_voice_configs") or []
    result: dict[str, Speaker] = {}
    if isinstance(configs, list):
        for idx, cfg in enumerate(configs):
            if not isinstance(cfg, dict):
                continue
            alias = cfg.get("speaker") or cfg.get("speakerAlias") or cfg.get("speaker_alias") or f"Speaker{idx + 1}"
            ref = _voice_ref_from_config(cfg, idx)
            try:
                speaker = _speaker_by_ref(session, ref, fallback_index=idx)
            except HTTPException:
                speaker = _speaker_by_ref(session, None, fallback_index=idx)
            result[str(alias).upper()] = speaker
    return result


def _segments_from_prompt(
    *,
    session: Session,
    prompt: str,
    speaker_map: dict[str, Speaker],
) -> list[PodcastSegment]:
    segments: list[PodcastSegment] = []
    current_label: str | None = None
    current_lines: list[str] = []

    def speaker_for(label: str, index: int = 0) -> Speaker:
        return speaker_map.get(label.upper()) or _speaker_by_ref(session, label, fallback_index=index)

    def flush() -> None:
        nonlocal current_label, current_lines
        if not current_label:
            return
        text = "\n".join(current_lines).strip()
        if text:
            speaker = speaker_for(current_label, len(segments))
            segments.append(PodcastSegment(speaker_id=speaker.id, label=current_label, text=text))
        current_label = None
        current_lines = []

    for raw_line in prompt.splitlines():
        match = _LABEL_RE.match(raw_line)
        if match:
            flush()
            current_label = match.group(1).strip()
            current_lines = [match.group(2)]
        elif current_label:
            current_lines.append(raw_line)
    flush()

    if segments:
        return segments
    speaker = _speaker_by_ref(session, None)
    return [PodcastSegment(speaker_id=speaker.id, label=speaker.name, text=prompt.strip())]


@router.post("/models/{model}:generateContent")
def generate_content_tts(
    model: str,
    req: GeminiGenerateContentRequest,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    settings = effective_settings(settings, session)
    prompt = _extract_text(req.contents).strip()
    if not prompt:
        raise HTTPException(status_code=422, detail="contents_text_required")

    request_config = req.config or req.generationConfig or {}
    speaker_map = _speaker_config_map(session, request_config)
    segments = _segments_from_prompt(session=session, prompt=prompt, speaker_map=speaker_map)

    gen = Generation(
        mode="podcast" if len(segments) > 1 else "tts",
        text=prompt,
        language=None,
        speaker_id=segments[0].speaker_id if len(segments) == 1 else None,
        params_json={
            "gemini_model": model,
            "gemini_config": request_config,
            "segments": [seg.model_dump(mode="json") for seg in segments],
        },
        audio_format="wav",
        status="running",
    )
    session.add(gen)
    session.commit()
    session.refresh(gen)

    podcast_req = PodcastJobRequest(
        title=None,
        segments=segments,
        language=None,
        params=TTSParams(),
        format="wav",
        pause_ms=250,
    )
    out_path, _duration, _elapsed = synthesize_podcast_request(
        settings=settings,
        session=session,
        gen=gen,
        req=podcast_req,
    )
    data = base64.b64encode(out_path.read_bytes()).decode("ascii")
    return {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "inlineData": {
                                "mimeType": "audio/wav",
                                "data": data,
                            }
                        }
                    ],
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {
            "promptTokenCount": max(1, len(prompt) // 4),
            "candidatesTokenCount": 0,
            "totalTokenCount": max(1, len(prompt) // 4),
        },
        "modelVersion": model,
    }
