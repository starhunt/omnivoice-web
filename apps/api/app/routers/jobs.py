"""비동기 생성 job API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import verify_api_key
from ..db import get_session
from ..engine.omnivoice_adapter import build_instruct_from_design
from ..job_runner import submit_job
from ..models import Generation, Job, Speaker
from ..schemas import JobCreateResponse, JobOut, PodcastJobRequest, TTSRequest

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(verify_api_key)])


def _resolve_tts_mode(req: TTSRequest) -> str:
    if req.speaker_id:
        return "tts"
    if req.design or req.instruct:
        return "design"
    return "auto"


def _resolve_tts_instruct(req: TTSRequest) -> str | None:
    return req.instruct or (
        build_instruct_from_design(req.design.model_dump(exclude_none=True))
        if req.design
        else None
    )


def _require_speaker(session: Session, speaker_id: str) -> Speaker:
    speaker = session.get(Speaker, speaker_id)
    if not speaker or speaker.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"speaker_not_found: {speaker_id}")
    return speaker


@router.post("/tts", response_model=JobCreateResponse, status_code=202)
def create_tts_job(req: TTSRequest, session: Session = Depends(get_session)) -> JobCreateResponse:
    if req.speaker_id:
        _require_speaker(session, req.speaker_id)

    gen = Generation(
        project_id=req.project_id,
        mode=_resolve_tts_mode(req),
        text=req.text,
        language=req.language,
        speaker_id=req.speaker_id,
        instruct=_resolve_tts_instruct(req),
        params_json={
            **req.params.model_dump(exclude_none=False),
            "engine": req.engine,
        },
        audio_format=req.format,
        status="pending",
    )
    session.add(gen)
    session.flush()

    job = Job(
        type="tts",
        status="queued",
        generation_id=gen.id,
        request_json=req.model_dump(mode="json"),
        progress_current=0,
        progress_total=1,
        progress_message="queued",
    )
    session.add(job)
    session.commit()

    submit_job(job.id)
    return JobCreateResponse(job_id=job.id, generation_id=gen.id, status=job.status)


@router.post("/podcast", response_model=JobCreateResponse, status_code=202)
def create_podcast_job(
    req: PodcastJobRequest,
    session: Session = Depends(get_session),
) -> JobCreateResponse:
    for seg in req.segments:
        _require_speaker(session, seg.speaker_id)

    text = "\n\n".join(
        f"{seg.label}: {seg.text}" if seg.label else seg.text
        for seg in req.segments
    )
    gen = Generation(
        project_id=req.project_id,
        mode="podcast",
        text=text,
        language=req.language,
        speaker_id=None,
        instruct=None,
        params_json={
            "params": req.params.model_dump(exclude_none=False),
            "pause_ms": req.pause_ms,
            "engine": req.engine,
            "segments": [seg.model_dump(mode="json") for seg in req.segments],
        },
        audio_format=req.format,
        status="pending",
    )
    session.add(gen)
    session.flush()

    job = Job(
        type="podcast",
        status="queued",
        generation_id=gen.id,
        request_json=req.model_dump(mode="json"),
        progress_current=0,
        progress_total=len(req.segments),
        progress_message="queued",
    )
    session.add(job)
    session.commit()

    submit_job(job.id)
    return JobCreateResponse(job_id=job.id, generation_id=gen.id, status=job.status)


@router.get("", response_model=list[JobOut])
def list_jobs(
    status: str | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[JobOut]:
    stmt = select(Job).order_by(Job.created_at.desc()).limit(limit).offset(offset)
    if status:
        stmt = stmt.where(Job.status == status)
    return list(session.scalars(stmt))


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: str, session: Session = Depends(get_session)) -> JobOut:
    job = session.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job_not_found")
    return job
