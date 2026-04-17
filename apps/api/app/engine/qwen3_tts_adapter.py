"""Qwen3-TTS engine adapter (subprocess based)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..config import Settings
from ..schemas import TTSParams
from .omnivoice_adapter import EngineError

SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "qwen3_tts_cli.py"
DEFAULT_TIMEOUT_SEC = int(os.environ.get("QWEN3_TTS_TIMEOUT_SEC", "1800"))

_LANGUAGE_MAP = {
    None: "Auto",
    "": "Auto",
    "auto": "Auto",
    "ko": "Korean",
    "kor": "Korean",
    "korean": "Korean",
    "en": "English",
    "eng": "English",
    "english": "English",
    "zh": "Chinese",
    "cn": "Chinese",
    "chinese": "Chinese",
    "ja": "Japanese",
    "jp": "Japanese",
    "japanese": "Japanese",
    "de": "German",
    "fr": "French",
    "ru": "Russian",
    "pt": "Portuguese",
    "es": "Spanish",
    "it": "Italian",
}


def qwen3_tts_status(settings: Settings) -> dict[str, Any]:
    script_ok = SCRIPT_PATH.exists()
    python_ok = settings.qwen3_tts_python.exists()
    enabled = settings.qwen3_tts_enabled
    if not enabled:
        reason = "QWEN3_TTS_ENABLED=false"
    elif not python_ok:
        reason = "QWEN3_TTS_PYTHON missing"
    elif not script_ok:
        reason = "qwen3_tts_cli.py missing"
    else:
        reason = None
    return {
        "enabled": enabled,
        "engine_python_exists": python_ok,
        "bridge_script_exists": script_ok,
        "mode": "live" if enabled and python_ok and script_ok else "stub",
        "reason": reason,
    }


def _language(language: str | None) -> str:
    key = (language or "auto").strip().lower()
    return _LANGUAGE_MAP.get(key, language or "Auto")


def _mode(*, instruct: str | None, ref_audio_path: Path | None) -> str:
    if ref_audio_path:
        return "voice_clone"
    if instruct:
        return "voice_design"
    return "custom_voice"


def _model_for_mode(settings: Settings, mode: str) -> str:
    if mode == "voice_clone":
        return settings.qwen3_tts_clone_model
    if mode == "voice_design":
        return settings.qwen3_tts_design_model
    return settings.qwen3_tts_model


def _convert_to_mp3_if_needed(wav_path: Path, target_path: Path) -> None:
    if target_path == wav_path:
        return
    if shutil.which("ffmpeg") is None:
        raise EngineError("ffmpeg_not_found: MP3 변환에는 ffmpeg 필요")
    proc = subprocess.run(
        ["ffmpeg", "-y", "-i", str(wav_path), "-b:a", "192k", str(target_path)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise EngineError(f"ffmpeg_failed: {proc.stderr[-500:]}")
    wav_path.unlink(missing_ok=True)


def synthesize(
    *,
    settings: Settings,
    text: str,
    language: str | None,
    instruct: str | None,
    ref_audio_path: Path | None,
    ref_transcript: str | None,
    params: TTSParams,
    out_path: Path,
) -> float:
    status = qwen3_tts_status(settings)
    if status["mode"] != "live":
        raise EngineError(f"qwen3_tts_unavailable: {status.get('reason') or 'not_available'}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wav_out = out_path.with_suffix(".wav")
    mode = _mode(instruct=instruct, ref_audio_path=ref_audio_path)
    payload = {
        "mode": mode,
        "model": _model_for_mode(settings, mode),
        "text": text,
        "language": _language(language),
        "speaker": settings.qwen3_tts_default_speaker,
        "instruct": instruct,
        "ref_audio_path": str(ref_audio_path) if ref_audio_path else None,
        "ref_text": ref_transcript,
        "x_vector_only_mode": not bool((ref_transcript or "").strip()),
        "out_path": str(wav_out),
        "device_map": settings.qwen3_tts_device,
        "dtype": settings.qwen3_tts_dtype,
        "attn_implementation": settings.qwen3_tts_attn_implementation,
        "speed": params.speed,
    }
    env = os.environ.copy()
    env.update({"PYTHONUNBUFFERED": "1"})
    try:
        proc = subprocess.run(
            [str(settings.qwen3_tts_python), str(SCRIPT_PATH)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=DEFAULT_TIMEOUT_SEC,
            env=env,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise EngineError("qwen3_tts_timeout") from exc

    stdout = (proc.stdout or "").strip()
    if not stdout:
        raise EngineError(f"qwen3_tts_no_output (rc={proc.returncode}): {(proc.stderr or '')[-1000:]}")
    try:
        result = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError as exc:
        raise EngineError(f"qwen3_tts_bad_output: {stdout[-1000:]}") from exc
    if result.get("status") != "ok":
        raise EngineError(f"qwen3_tts_failed: {result.get('error')}")

    _convert_to_mp3_if_needed(wav_out, out_path)
    return float(result.get("duration_sec") or 0.0)
