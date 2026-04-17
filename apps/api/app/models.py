"""ORM 모델 (SQLite 기준, PostgreSQL 이관 호환)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, Float, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ulid() -> str:
    # ULID 없이 uuid4 hex (26자 ≈ ULID와 유사 길이) — MVP 단순화
    return uuid.uuid4().hex


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_ulid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Speaker(Base):
    __tablename__ = "speakers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_ulid)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    language_hint: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ref_transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 파일시스템 경로 (상대 경로, DATA_DIR 기준)
    source_audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    prompt_blob_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_ulid)
    project_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("projects.id"), nullable=True
    )
    mode: Mapped[str] = mapped_column(String(20), nullable=False)  # tts | design | auto
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str | None] = mapped_column(String(10), nullable=True)
    speaker_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("speakers.id"), nullable=True
    )
    instruct: Mapped[str | None] = mapped_column(Text, nullable=True)
    params_json: Mapped[dict] = mapped_column(JSON, default=dict)
    audio_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audio_format: Mapped[str] = mapped_column(String(10), default="wav")
    duration_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    rtf: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|succeeded|failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    speaker = relationship("Speaker", lazy="joined")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_ulid)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # tts | podcast
    status: Mapped[str] = mapped_column(String(20), default="queued")
    generation_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("generations.id"), nullable=True
    )
    request_json: Mapped[dict] = mapped_column(JSON, default=dict)
    progress_current: Mapped[int] = mapped_column(Integer, default=0)
    progress_total: Mapped[int] = mapped_column(Integer, default=0)
    progress_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    generation = relationship("Generation", lazy="joined")
