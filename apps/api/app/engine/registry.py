"""TTS engine discovery and selection."""

from __future__ import annotations

from ..config import Settings
from ..schemas import EngineCapability, EngineInfo, EnginesResponse, EngineVoice
from .omnivoice_adapter import SCRIPT_PATH as OMNIVOICE_SCRIPT_PATH
from .omnivoice_adapter import engine_status as omnivoice_status
from .qwen3_tts_adapter import SCRIPT_PATH as QWEN3_TTS_SCRIPT_PATH
from .qwen3_tts_adapter import list_voices as qwen3_tts_voices
from .qwen3_tts_adapter import qwen3_tts_status

ENGINE_AUTO = "auto"
ENGINE_OMNIVOICE = "omnivoice"
ENGINE_QWEN3_TTS = "qwen3-tts"


def _omnivoice_info(settings: Settings) -> EngineInfo:
    status = omnivoice_status(settings)
    available = status["mode"] == "live"
    reason = None
    if not available:
        missing = []
        if not status["engine_path_exists"]:
            missing.append("OMNIVOICE_ENGINE_PATH missing")
        if not status["engine_python_exists"]:
            missing.append("OMNIVOICE_ENGINE_PYTHON missing")
        if not status["bridge_script_exists"]:
            missing.append("engine_cli.py missing")
        reason = ", ".join(missing) or "not_available"
    return EngineInfo(
        id=ENGINE_OMNIVOICE,
        name="OmniVoice",
        available=available,
        mode=status["mode"],
        reason=reason,
        python=str(settings.omnivoice_engine_python),
        path=str(settings.omnivoice_engine_path),
        model="OmniVoice local",
        capabilities=EngineCapability(
            supports_voice_clone=True,
            supports_voice_design=True,
            supports_custom_voices=False,
            supports_native_dialogue=False,
            supports_streaming=False,
            max_speakers=1,
            languages=["auto", "ko", "en", "zh", "ja", "es", "fr", "de", "it", "pt", "ru"],
        ),
        voices=[],
    )


def _qwen3_tts_info(settings: Settings) -> EngineInfo:
    status = qwen3_tts_status(settings)
    openai_compatible = status.get("backend") == "openai-compatible"
    return EngineInfo(
        id=ENGINE_QWEN3_TTS,
        name="Qwen3-TTS",
        available=status["mode"] == "live",
        mode=status["mode"],
        reason=status.get("reason"),
        python=str(settings.qwen3_tts_python),
        path=status.get("base_url") or str(QWEN3_TTS_SCRIPT_PATH),
        model=settings.qwen3_tts_model,
        capabilities=EngineCapability(
            supports_voice_clone=not openai_compatible,
            supports_voice_design=not openai_compatible,
            supports_custom_voices=True,
            supports_native_dialogue=False,
            supports_streaming=openai_compatible,
            max_speakers=1,
            languages=["auto", "ko", "en", "zh", "ja", "de", "fr", "ru", "pt", "es", "it"],
        ),
        voices=[EngineVoice(**voice) for voice in qwen3_tts_voices(settings)] if status["mode"] == "live" else [],
    )


def list_engines(settings: Settings) -> list[EngineInfo]:
    return [_omnivoice_info(settings), _qwen3_tts_info(settings)]


def _configured_default(settings: Settings) -> str:
    configured = (settings.tts_default_engine or ENGINE_AUTO).strip().lower()
    if configured in {ENGINE_AUTO, ENGINE_OMNIVOICE, ENGINE_QWEN3_TTS}:
        return configured
    return ENGINE_AUTO


def resolve_engine(
    settings: Settings,
    requested: str | None,
    *,
    speaker_has_omnivoice_prompt_only: bool = False,
) -> str:
    """Resolve requested/default engine to an installed concrete engine."""

    engine = (requested or _configured_default(settings) or ENGINE_AUTO).strip().lower()
    if engine == ENGINE_AUTO:
        engine = _configured_default(settings)
    if engine == ENGINE_AUTO:
        infos = {info.id: info for info in list_engines(settings)}
        # Qwen cannot use an OmniVoice prompt-only speaker. Keep those on OmniVoice.
        if (
            not speaker_has_omnivoice_prompt_only
            and infos.get(ENGINE_QWEN3_TTS)
            and infos[ENGINE_QWEN3_TTS].available
        ):
            return ENGINE_QWEN3_TTS
        if infos.get(ENGINE_OMNIVOICE) and infos[ENGINE_OMNIVOICE].available:
            return ENGINE_OMNIVOICE
        if infos.get(ENGINE_QWEN3_TTS) and infos[ENGINE_QWEN3_TTS].available:
            return ENGINE_QWEN3_TTS
        return ENGINE_OMNIVOICE
    return engine


def engines_response(settings: Settings) -> EnginesResponse:
    requested = _configured_default(settings)
    selected = resolve_engine(settings, requested)
    return EnginesResponse(
        default_engine=requested,
        selected_engine=selected,
        engines=list_engines(settings),
    )
