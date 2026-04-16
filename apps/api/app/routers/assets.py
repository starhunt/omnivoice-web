"""오디오 자산 서빙 (화자 원본 + 생성 결과)."""

from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_session
from ..models import Generation, Speaker

router = APIRouter(prefix="/assets", tags=["assets"])


_MIME = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".m4a": "audio/mp4",
}


def _resolve_mime(path: Path) -> str:
    ext = path.suffix.lower()
    return _MIME.get(ext) or mimetypes.guess_type(str(path))[0] or "application/octet-stream"


def _safe_under(root: Path, candidate: Path) -> Path:
    """candidate가 root 아래에 있도록 강제. 경로 탈출 방어."""
    root = root.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid_path") from exc
    return resolved


@router.get("/{generation_id}.{fmt}")
def get_generation_audio(
    generation_id: str,
    fmt: str,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> FileResponse:
    gen = session.get(Generation, generation_id)
    if not gen or not gen.audio_path:
        raise HTTPException(status_code=404, detail="audio_not_found")
    path = _safe_under(settings.data_dir, settings.data_dir / gen.audio_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="audio_missing_on_disk")
    return FileResponse(path, media_type=_resolve_mime(path), filename=path.name)


@router.get("/speaker/{speaker_id}/ref")
def get_speaker_ref(
    speaker_id: str,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> FileResponse:
    spk = session.get(Speaker, speaker_id)
    if not spk or not spk.source_audio_path or spk.deleted_at is not None:
        raise HTTPException(status_code=404, detail="speaker_audio_not_found")
    path = _safe_under(settings.data_dir, settings.data_dir / spk.source_audio_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="audio_missing_on_disk")
    return FileResponse(path, media_type=_resolve_mime(path), filename=path.name)
