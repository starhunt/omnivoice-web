"""헬스체크 엔드포인트."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..config import Settings, get_settings
from ..engine.omnivoice_adapter import engine_status

router = APIRouter(tags=["health"])


@router.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    engine = engine_status(settings)
    return {
        "status": "ok",
        "version": "0.1.0",
        "engine": engine,
        "device": settings.omnivoice_device,
    }
