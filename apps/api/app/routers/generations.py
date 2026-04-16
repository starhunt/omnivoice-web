"""생성 히스토리 라우터."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from ..auth import verify_api_key
from ..config import Settings, get_settings
from ..db import get_session
from ..models import Generation
from ..schemas import GenerationOut

router = APIRouter(prefix="/generations", tags=["generations"], dependencies=[Depends(verify_api_key)])


@router.get("", response_model=list[GenerationOut])
def list_generations(
    q: str | None = Query(default=None, description="텍스트 부분 검색"),
    status: str | None = None,
    speaker_id: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[GenerationOut]:
    stmt = select(Generation).order_by(Generation.created_at.desc()).limit(limit).offset(offset)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(or_(Generation.text.ilike(like), Generation.instruct.ilike(like)))
    if status:
        stmt = stmt.where(Generation.status == status)
    if speaker_id:
        stmt = stmt.where(Generation.speaker_id == speaker_id)
    return list(session.scalars(stmt))


@router.get("/stats")
def stats(session: Session = Depends(get_session)) -> dict:
    total = session.scalar(select(func.count(Generation.id))) or 0
    succeeded = session.scalar(
        select(func.count(Generation.id)).where(Generation.status == "succeeded")
    ) or 0
    failed = session.scalar(
        select(func.count(Generation.id)).where(Generation.status == "failed")
    ) or 0
    total_duration = session.scalar(select(func.coalesce(func.sum(Generation.duration_sec), 0.0))) or 0.0
    return {
        "total": total,
        "succeeded": succeeded,
        "failed": failed,
        "total_audio_sec": float(total_duration),
    }


@router.get("/{generation_id}", response_model=GenerationOut)
def get_generation(generation_id: str, session: Session = Depends(get_session)) -> GenerationOut:
    gen = session.get(Generation, generation_id)
    if not gen:
        raise HTTPException(status_code=404, detail="generation_not_found")
    return gen


@router.delete("/{generation_id}", status_code=204)
def delete_generation(
    generation_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    """생성 레코드 + 오디오 파일 삭제. running 상태도 삭제 가능 (중단 처리로 간주)."""
    gen = session.get(Generation, generation_id)
    if not gen:
        raise HTTPException(status_code=404, detail="generation_not_found")

    # 오디오 파일 제거 (wav/mp3 모두 시도, 실패는 경고만)
    for ext in ("wav", "mp3"):
        candidate: Path = settings.audio_dir / f"{generation_id}.{ext}"
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            pass

    session.delete(gen)
    session.commit()
    return Response(status_code=204)


@router.post("/cleanup-stale", status_code=200)
def cleanup_stale_running(session: Session = Depends(get_session)) -> dict:
    """running 상태로 남은 레코드를 일괄 failed(interrupted)로 전환.

    서버가 내려가지 않은 상태에서도 수동으로 찌꺼기를 정리할 때 사용.
    """
    stmt = (
        update(Generation)
        .where(Generation.status == "running")
        .values(
            status="failed",
            error="interrupted_manual_cleanup",
            finished_at=datetime.now(timezone.utc),
        )
    )
    result = session.execute(stmt)
    session.commit()
    return {"finalized": int(result.rowcount or 0)}
