"""TTS provider management endpoints."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import verify_api_key
from ..config import Settings, get_settings
from ..db import get_session
from ..engine.omnivoice_adapter import engine_status as omnivoice_status
from ..engine.qwen3_tts_adapter import qwen3_tts_status
from ..models import TTSProvider
from ..provider_settings import ENGINE_OMNIVOICE, ENGINE_QWEN3_TTS, mark_default, settings_for_provider
from ..schemas import TTSProviderCreate, TTSProviderOut, TTSProviderTestResult, TTSProviderUpdate

router = APIRouter(prefix="/providers", tags=["providers"], dependencies=[Depends(verify_api_key)])


def _provider_out(provider: TTSProvider) -> TTSProviderOut:
    return TTSProviderOut(
        id=provider.id,
        name=provider.name,
        engine=provider.engine,
        enabled=provider.enabled,
        is_default=provider.is_default,
        config=provider.config_json or {},
        created_at=provider.created_at,
        updated_at=provider.updated_at,
    )


def _get_provider(session: Session, provider_id: str) -> TTSProvider:
    provider = session.get(TTSProvider, provider_id)
    if not provider or provider.deleted_at is not None:
        raise HTTPException(status_code=404, detail="provider_not_found")
    return provider


@router.get("", response_model=list[TTSProviderOut])
def list_providers(session: Session = Depends(get_session)) -> list[TTSProviderOut]:
    stmt = (
        select(TTSProvider)
        .where(TTSProvider.deleted_at.is_(None))
        .order_by(TTSProvider.engine.asc(), TTSProvider.is_default.desc(), TTSProvider.created_at.asc())
    )
    return [_provider_out(provider) for provider in session.scalars(stmt)]


@router.post("", response_model=TTSProviderOut, status_code=status.HTTP_201_CREATED)
def create_provider(req: TTSProviderCreate, session: Session = Depends(get_session)) -> TTSProviderOut:
    provider = TTSProvider(
        name=req.name.strip(),
        engine=req.engine,
        enabled=req.enabled,
        is_default=req.is_default,
        config_json=req.config,
    )
    session.add(provider)
    session.flush()
    if provider.is_default:
        mark_default(session, provider)
    session.commit()
    session.refresh(provider)
    return _provider_out(provider)


@router.patch("/{provider_id}", response_model=TTSProviderOut)
def update_provider(
    provider_id: str,
    req: TTSProviderUpdate,
    session: Session = Depends(get_session),
) -> TTSProviderOut:
    provider = _get_provider(session, provider_id)
    data = req.model_dump(exclude_unset=True)
    if "name" in data and data["name"] is not None:
        provider.name = data["name"].strip()
    if "enabled" in data and data["enabled"] is not None:
        provider.enabled = bool(data["enabled"])
    if "config" in data and data["config"] is not None:
        provider.config_json = data["config"]
    if data.get("is_default"):
        mark_default(session, provider)
    elif "is_default" in data and data["is_default"] is False:
        provider.is_default = False
    provider.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(provider)
    return _provider_out(provider)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(provider_id: str, session: Session = Depends(get_session)) -> None:
    provider = _get_provider(session, provider_id)
    provider.deleted_at = datetime.now(timezone.utc)
    provider.updated_at = provider.deleted_at
    session.commit()


@router.post("/{provider_id}/test", response_model=TTSProviderTestResult)
def test_provider(
    provider_id: str,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> TTSProviderTestResult:
    provider = _get_provider(session, provider_id)
    test_settings = settings_for_provider(settings, provider)
    if provider.engine == ENGINE_QWEN3_TTS:
        status_payload = qwen3_tts_status(test_settings)
        ok = status_payload.get("mode") == "live"
        return TTSProviderTestResult(
            provider_id=provider.id,
            ok=ok,
            mode=str(status_payload.get("mode")),
            reason=status_payload.get("reason"),
            detail=status_payload,
        )
    if provider.engine == ENGINE_OMNIVOICE:
        status_payload = omnivoice_status(test_settings)
        ok = status_payload.get("mode") == "live"
        reason = None
        if not ok:
            missing = []
            if not status_payload.get("engine_path_exists"):
                missing.append("OMNIVOICE_ENGINE_PATH missing")
            if not status_payload.get("engine_python_exists"):
                missing.append("OMNIVOICE_ENGINE_PYTHON missing")
            if not status_payload.get("bridge_script_exists"):
                missing.append("engine_cli.py missing")
            reason = ", ".join(missing) or "not_available"
        return TTSProviderTestResult(
            provider_id=provider.id,
            ok=ok,
            mode=str(status_payload.get("mode")),
            reason=reason,
            detail=status_payload,
        )
    raise HTTPException(status_code=400, detail="unsupported_provider_engine")
