"""화자 관리 라우터."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shutil
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import verify_api_key
from ..config import Settings, get_settings
from ..db import get_session
from ..models import Speaker
from ..schemas import SpeakerOut, SpeakerUpdate
from ..storage import safe_ext

router = APIRouter(prefix="/speakers", tags=["speakers"], dependencies=[Depends(verify_api_key)])


MAX_AUDIO_BYTES = 50 * 1024 * 1024  # 50MB


@router.get("", response_model=list[SpeakerOut])
def list_speakers(
    include_deleted: bool = False,
    session: Session = Depends(get_session),
) -> list[SpeakerOut]:
    stmt = select(Speaker).order_by(Speaker.is_favorite.desc(), Speaker.created_at.desc())
    if not include_deleted:
        stmt = stmt.where(Speaker.deleted_at.is_(None))
    return list(session.scalars(stmt))


@router.get("/{speaker_id}", response_model=SpeakerOut)
def get_speaker(speaker_id: str, session: Session = Depends(get_session)) -> SpeakerOut:
    spk = session.get(Speaker, speaker_id)
    if not spk or spk.deleted_at is not None:
        raise HTTPException(status_code=404, detail="speaker_not_found")
    return spk


@router.post("", response_model=SpeakerOut, status_code=status.HTTP_201_CREATED)
async def create_speaker(
    name: str = Form(..., min_length=1, max_length=200),
    tags: str = Form(""),
    note: str | None = Form(None),
    language_hint: str | None = Form(None),
    ref_transcript: str | None = Form(None),
    audio: UploadFile = File(...),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> SpeakerOut:
    ext = safe_ext(audio.filename)
    if not ext:
        raise HTTPException(status_code=400, detail="unsupported_audio_format")

    # 임시 저장 후 크기 검증
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        total = 0
        while True:
            chunk = await audio.read(1 << 20)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_AUDIO_BYTES:
                tmp.close()
                Path(tmp.name).unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="audio_too_large")
            tmp.write(chunk)
        tmp_path = Path(tmp.name)

    spk = Speaker(
        name=name.strip(),
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        note=note,
        language_hint=language_hint,
        ref_transcript=ref_transcript,
    )
    session.add(spk)
    session.flush()  # id 발급

    # 영구 저장: data/speakers/<id>/ref<ext>
    dst_dir = settings.speakers_dir / spk.id
    dst_dir.mkdir(parents=True, exist_ok=True)
    final_audio = dst_dir / f"ref{ext}"
    shutil.move(str(tmp_path), str(final_audio))

    spk.source_audio_path = str(final_audio.relative_to(settings.data_dir))
    session.commit()
    session.refresh(spk)
    return spk


@router.patch("/{speaker_id}", response_model=SpeakerOut)
def update_speaker(
    speaker_id: str,
    patch: SpeakerUpdate,
    session: Session = Depends(get_session),
) -> SpeakerOut:
    spk = session.get(Speaker, speaker_id)
    if not spk or spk.deleted_at is not None:
        raise HTTPException(status_code=404, detail="speaker_not_found")
    data = patch.model_dump(exclude_unset=True)
    for key, val in data.items():
        setattr(spk, key, val)
    session.commit()
    session.refresh(spk)
    return spk


@router.delete("/{speaker_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_speaker(speaker_id: str, session: Session = Depends(get_session)) -> None:
    spk = session.get(Speaker, speaker_id)
    if not spk or spk.deleted_at is not None:
        raise HTTPException(status_code=404, detail="speaker_not_found")
    spk.deleted_at = datetime.now(timezone.utc)
    session.commit()
