"""DB-backed TTS provider settings.

Environment variables remain the bootstrap/default source. Once provider rows
exist, enabled default rows override the in-process Settings object per request.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .config import Settings
from .models import TTSProvider

ENGINE_OMNIVOICE = "omnivoice"
ENGINE_QWEN3_TTS = "qwen3-tts"


def _clean_config(config: dict[str, Any]) -> dict[str, Any]:
    return {str(k): v for k, v in (config or {}).items() if v is not None}


def _provider_to_updates(provider: TTSProvider) -> dict[str, Any]:
    config = _clean_config(provider.config_json)
    if provider.engine == ENGINE_QWEN3_TTS:
        updates: dict[str, Any] = {"qwen3_tts_enabled": provider.enabled}
        mapping = {
            "base_url": "qwen3_tts_base_url",
            "api_key": "qwen3_tts_api_key",
            "clone_base_url": "qwen3_tts_clone_base_url",
            "clone_api_key": "qwen3_tts_clone_api_key",
            "model": "qwen3_tts_model",
            "clone_model": "qwen3_tts_clone_model",
            "design_model": "qwen3_tts_design_model",
            "default_speaker": "qwen3_tts_default_speaker",
            "python": "qwen3_tts_python",
            "device": "qwen3_tts_device",
            "dtype": "qwen3_tts_dtype",
            "attn_implementation": "qwen3_tts_attn_implementation",
        }
        for source, target in mapping.items():
            if source not in config:
                continue
            value = config[source]
            if source == "python" and value:
                value = Path(str(value))
            updates[target] = value
        return updates

    if provider.engine == ENGINE_OMNIVOICE:
        updates = {}
        if "engine_path" in config and config["engine_path"]:
            updates["omnivoice_engine_path"] = Path(str(config["engine_path"]))
        if "engine_python" in config and config["engine_python"]:
            updates["omnivoice_engine_python"] = Path(str(config["engine_python"]))
        if "device" in config and config["device"]:
            updates["omnivoice_device"] = str(config["device"])
        return updates

    return {}


def active_provider(session: Session, engine: str) -> TTSProvider | None:
    stmt = (
        select(TTSProvider)
        .where(
            TTSProvider.engine == engine,
            TTSProvider.deleted_at.is_(None),
        )
        .order_by(TTSProvider.is_default.desc(), TTSProvider.created_at.asc())
        .limit(1)
    )
    return session.scalars(stmt).first()


def effective_settings(settings: Settings, session: Session) -> Settings:
    updates: dict[str, Any] = {}
    for engine in (ENGINE_OMNIVOICE, ENGINE_QWEN3_TTS):
        provider = active_provider(session, engine)
        if provider:
            updates.update(_provider_to_updates(provider))
    if not updates:
        return settings
    result = settings.model_copy(update=updates)
    result.ensure_dirs()
    return result


def settings_for_provider(settings: Settings, provider: TTSProvider) -> Settings:
    result = settings.model_copy(update=_provider_to_updates(provider))
    result.ensure_dirs()
    return result


def make_default_provider_configs(settings: Settings) -> list[dict[str, Any]]:
    return [
        {
            "name": "OmniVoice Local",
            "engine": ENGINE_OMNIVOICE,
            "enabled": True,
            "is_default": True,
            "config_json": {
                "engine_path": str(settings.omnivoice_engine_path),
                "engine_python": str(settings.omnivoice_engine_python),
                "device": settings.omnivoice_device,
            },
        },
        {
            "name": "Qwen3-TTS A100",
            "engine": ENGINE_QWEN3_TTS,
            "enabled": settings.qwen3_tts_enabled,
            "is_default": True,
            "config_json": {
                "base_url": settings.qwen3_tts_base_url,
                "api_key": settings.qwen3_tts_api_key,
                "clone_base_url": settings.qwen3_tts_clone_base_url,
                "clone_api_key": settings.qwen3_tts_clone_api_key,
                "model": settings.qwen3_tts_model,
                "clone_model": settings.qwen3_tts_clone_model,
                "design_model": settings.qwen3_tts_design_model,
                "default_speaker": settings.qwen3_tts_default_speaker,
                "python": str(settings.qwen3_tts_python),
                "device": settings.qwen3_tts_device,
                "dtype": settings.qwen3_tts_dtype,
                "attn_implementation": settings.qwen3_tts_attn_implementation,
            },
        },
    ]


def seed_default_providers(settings: Settings, session: Session) -> int:
    existing = session.scalar(select(TTSProvider.id).limit(1))
    if existing:
        return 0
    count = 0
    for row in make_default_provider_configs(settings):
        session.add(TTSProvider(**row))
        count += 1
    session.commit()
    return count


def mark_default(session: Session, provider: TTSProvider) -> None:
    session.execute(
        update(TTSProvider)
        .where(
            TTSProvider.engine == provider.engine,
            TTSProvider.id != provider.id,
            TTSProvider.deleted_at.is_(None),
        )
        .values(is_default=False)
    )
    provider.is_default = True
