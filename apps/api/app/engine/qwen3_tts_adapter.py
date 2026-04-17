"""Qwen3-TTS engine adapter.

Supports two deployment shapes:
- vLLM-Omni/OpenAI-compatible HTTP server (`QWEN3_TTS_BASE_URL`)
- direct Python subprocess bridge (`QWEN3_TTS_PYTHON`)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
import wave
from pathlib import Path
from typing import Any

from ..config import Settings
from ..schemas import TTSParams
from .omnivoice_adapter import EngineError

SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "qwen3_tts_cli.py"
DEFAULT_TIMEOUT_SEC = int(os.environ.get("QWEN3_TTS_TIMEOUT_SEC", "1800"))
PROBE_TIMEOUT_SEC = float(os.environ.get("QWEN3_TTS_PROBE_TIMEOUT_SEC", "3"))

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
    base_url = _base_url(settings)
    api_ok = False
    api_reason: str | None = None
    if enabled and base_url:
        try:
            _api_get(settings, "/health", timeout=PROBE_TIMEOUT_SEC)
            api_ok = True
        except Exception as exc:  # noqa: BLE001 - status endpoint should never raise to callers.
            api_reason = f"QWEN3_TTS_BASE_URL unavailable: {exc}"

    if not enabled:
        reason = "QWEN3_TTS_ENABLED=false"
    elif base_url and api_ok:
        reason = None
    elif base_url and not api_ok:
        reason = api_reason
    elif not python_ok:
        reason = "QWEN3_TTS_PYTHON missing"
    elif not script_ok:
        reason = "qwen3_tts_cli.py missing"
    else:
        reason = None
    return {
        "enabled": enabled,
        "base_url": base_url,
        "api_available": api_ok,
        "engine_python_exists": python_ok,
        "bridge_script_exists": script_ok,
        "mode": "live" if enabled and ((base_url and api_ok) or (python_ok and script_ok)) else "stub",
        "backend": "openai-compatible" if base_url else "python-cli",
        "reason": reason,
    }


def requires_ref_audio(settings: Settings) -> bool:
    """The direct CLI can clone a supplied speaker; the OpenAI Speech API uses named voices."""
    return not bool(_base_url(settings))


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


def _base_url(settings: Settings) -> str:
    return (settings.qwen3_tts_base_url or "").strip().rstrip("/")


def _api_url(settings: Settings, path: str) -> str:
    return f"{_base_url(settings)}{path}"


def _api_headers(settings: Settings) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.qwen3_tts_api_key:
        headers["Authorization"] = f"Bearer {settings.qwen3_tts_api_key}"
    return headers


def _api_get(settings: Settings, path: str, *, timeout: float) -> bytes:
    req = urllib.request.Request(_api_url(settings, path), headers=_api_headers(settings), method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310 - URL is operator-configured.
        return res.read()


def _api_post_json(settings: Settings, path: str, payload: dict[str, Any], *, timeout: float) -> bytes:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        _api_url(settings, path),
        data=body,
        headers=_api_headers(settings),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:  # noqa: S310 - URL is operator-configured.
            return res.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise EngineError(f"qwen3_tts_api_failed ({exc.code}): {detail[-1000:]}") from exc


def _wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
    return frames / float(rate) if rate else 0.0


def _synthesize_openai_compatible(
    *,
    settings: Settings,
    text: str,
    params: TTSParams,
    out_path: Path,
) -> float:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = out_path.suffix.lower()
    if suffix in {".wav", ".mp3"}:
        response_format = suffix.lstrip(".")
        api_out = out_path
    else:
        response_format = "wav"
        api_out = out_path.with_suffix(".wav")
    payload: dict[str, Any] = {
        "model": settings.qwen3_tts_model,
        "input": text,
        "voice": settings.qwen3_tts_default_speaker.strip().lower(),
        "response_format": response_format,
    }
    if params.speed:
        payload["speed"] = params.speed
    audio = _api_post_json(
        settings,
        "/v1/audio/speech",
        payload,
        timeout=float(DEFAULT_TIMEOUT_SEC),
    )
    if not audio:
        raise EngineError("qwen3_tts_api_empty_audio")
    api_out.write_bytes(audio)
    if response_format == "wav":
        duration = _wav_duration(api_out)
        _convert_to_mp3_if_needed(api_out, out_path)
    else:
        duration = 0.0
    return duration


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
    if _base_url(settings):
        return _synthesize_openai_compatible(
            settings=settings,
            text=text,
            params=params,
            out_path=out_path,
        )

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
