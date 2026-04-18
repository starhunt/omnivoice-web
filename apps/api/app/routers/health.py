"""헬스체크 엔드포인트."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_session
from ..engine.omnivoice_adapter import engine_status
from ..provider_settings import effective_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health(
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> dict:
    settings = effective_settings(settings, session)
    engine = engine_status(settings)
    return {
        "status": "ok",
        "version": "0.1.0",
        "engine": engine,
        "device": settings.omnivoice_device,
    }
