"""Pydantic 요청/응답 스키마."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------- TTS ----------

AudioFormat = Literal["wav", "mp3"]


class TTSParams(BaseModel):
    num_step: int = Field(default=32, ge=1, le=128)
    guidance_scale: float = Field(default=2.0, ge=0.0, le=4.0)
    denoise: bool = True
    speed: float | None = Field(default=None, ge=0.25, le=2.0)
    duration: float | None = Field(default=None, ge=0.0, le=600.0)
    t_shift: float = Field(default=0.1)
    position_temperature: float = Field(default=5.0)
    class_temperature: float = Field(default=0.0)
    layer_penalty_factor: float = Field(default=5.0)
    preprocess_prompt: bool = True
    postprocess_output: bool = True
    audio_chunk_duration: float = Field(default=15.0)
    audio_chunk_threshold: float = Field(default=30.0)


class VoiceDesign(BaseModel):
    gender: str | None = None
    age: str | None = None
    pitch: str | None = None
    style: str | None = None
    english_accent: str | None = None
    chinese_dialect: str | None = None


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    speaker_id: str | None = None
    language: str | None = None
    instruct: str | None = None
    design: VoiceDesign | None = None
    params: TTSParams = Field(default_factory=TTSParams)
    format: AudioFormat = "wav"
    project_id: str | None = None


class GenerationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    mode: str
    text: str
    language: str | None
    speaker_id: str | None
    instruct: str | None
    params_json: dict
    audio_path: str | None
    audio_format: str
    duration_sec: float | None
    rtf: float | None
    status: str
    error: str | None
    created_at: datetime
    finished_at: datetime | None

    @property
    def audio_url(self) -> str | None:
        if not self.audio_path:
            return None
        return f"/v1/assets/{self.id}.{self.audio_format}"


class TTSResponse(BaseModel):
    generation_id: str
    audio_url: str | None
    duration_sec: float | None
    rtf: float | None
    status: str
    created_at: datetime


# ---------- Speakers ----------


class SpeakerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    tags: list[str] = Field(default_factory=list)
    note: str | None = None
    language_hint: str | None = None
    ref_transcript: str | None = None


class SpeakerUpdate(BaseModel):
    name: str | None = None
    tags: list[str] | None = None
    note: str | None = None
    is_favorite: bool | None = None


class SpeakerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    tags: list[str]
    note: str | None
    language_hint: str | None
    ref_transcript: str | None
    source_audio_path: str | None
    prompt_blob_path: str | None
    is_favorite: bool
    usage_count: int
    last_used_at: datetime | None
    created_at: datetime


# ---------- Meta ----------


class LanguageEntry(BaseModel):
    code: str
    name: str
    english_name: str | None = None


class VoiceAttributeOptions(BaseModel):
    gender: list[str]
    age: list[str]
    pitch: list[str]
    style: list[str]
    english_accent: list[str]
    chinese_dialect: list[str]
