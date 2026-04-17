"""In-process async job runner for long TTS/podcast generation.

This is an MVP runner: one worker thread per API process. The public API and DB
shape are intentionally close to a future Celery/RQ worker so it can be replaced
without changing clients.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import time
import wave
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings, get_settings
from .db import SessionLocal
from .engine.omnivoice_adapter import EngineError, build_instruct_from_design, synthesize
from .engine.qwen3_tts_adapter import synthesize as synthesize_qwen3_tts
from .engine.registry import ENGINE_QWEN3_TTS, resolve_engine
from .models import Generation, Job, Speaker
from .routers.tts import ensure_speaker_voice_prompt
from .schemas import PodcastJobRequest, TTSParams, TTSRequest
from .storage import audio_path_for, relpath

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="omnivoice-job")


def submit_job(job_id: str) -> None:
    _executor.submit(_run_job, job_id)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _set_job_progress(
    session,
    job: Job,
    *,
    current: int | None = None,
    total: int | None = None,
    message: str | None = None,
) -> None:
    if current is not None:
        job.progress_current = current
    if total is not None:
        job.progress_total = total
    if message is not None:
        job.progress_message = message
    session.commit()


def _fail_job(session, job: Job, gen: Generation | None, error: str) -> None:
    job.status = "failed"
    job.error = error
    job.finished_at = _now()
    if gen:
        gen.status = "failed"
        gen.error = error
        gen.finished_at = job.finished_at
    session.commit()


def _run_job(job_id: str) -> None:
    settings = get_settings()
    with SessionLocal() as session:
        job = session.get(Job, job_id)
        if not job:
            logger.warning("job %s not found", job_id)
            return
        gen = session.get(Generation, job.generation_id) if job.generation_id else None
        try:
            job.status = "running"
            job.started_at = _now()
            if gen:
                gen.status = "running"
            session.commit()

            if job.type == "tts":
                _run_tts_job(settings, session, job, gen)
            elif job.type == "podcast":
                _run_podcast_job(settings, session, job, gen)
            else:
                raise RuntimeError(f"unsupported_job_type: {job.type}")
        except Exception as exc:
            logger.exception("job %s failed", job_id)
            _fail_job(session, job, gen, f"{type(exc).__name__}: {exc}")


def _resolve_speaker(session, speaker_id: str | None) -> Speaker | None:
    if not speaker_id:
        return None
    speaker = session.get(Speaker, speaker_id)
    if not speaker or speaker.deleted_at is not None:
        raise RuntimeError(f"speaker_not_found: {speaker_id}")
    return speaker


def _run_tts_job(settings: Settings, session, job: Job, gen: Generation | None) -> None:
    if gen is None:
        raise RuntimeError("generation_missing")

    req = TTSRequest.model_validate(job.request_json)
    speaker = _resolve_speaker(session, req.speaker_id)
    speaker_prompt_only = bool(speaker and speaker.prompt_blob_path and not speaker.source_audio_path)
    engine_id = resolve_engine(
        settings,
        req.engine,
        speaker_has_omnivoice_prompt_only=speaker_prompt_only,
    )
    ref_audio_path: Path | None = None
    voice_prompt_path: Path | None = None
    if engine_id == ENGINE_QWEN3_TTS:
        if speaker and not speaker.source_audio_path:
            raise RuntimeError("qwen3_tts_requires_speaker_ref_audio")
        ref_audio_path = settings.data_dir / speaker.source_audio_path if speaker and speaker.source_audio_path else None
    else:
        ref_audio_path, voice_prompt_path = ensure_speaker_voice_prompt(
            settings=settings,
            session=session,
            speaker=speaker,
            preprocess_prompt=req.params.preprocess_prompt,
        )
    instruct = req.instruct or (
        build_instruct_from_design(req.design.model_dump(exclude_none=True))
        if req.design
        else None
    )

    _set_job_progress(session, job, current=0, total=1, message="synthesizing")
    out_path = audio_path_for(settings, gen.id, req.format)
    started = time.perf_counter()
    if engine_id == ENGINE_QWEN3_TTS:
        duration_sec = synthesize_qwen3_tts(
            settings=settings,
            text=req.text,
            language=req.language,
            instruct=instruct,
            ref_audio_path=ref_audio_path,
            ref_transcript=speaker.ref_transcript if speaker else None,
            params=req.params,
            out_path=out_path,
        )
    else:
        duration_sec = synthesize(
            settings=settings,
            text=req.text,
            language=req.language,
            instruct=instruct,
            ref_audio_path=ref_audio_path,
            ref_transcript=speaker.ref_transcript if speaker else None,
            voice_prompt_path=voice_prompt_path,
            params=req.params,
            out_path=out_path,
        )
    elapsed = time.perf_counter() - started

    gen.audio_path = relpath(settings, out_path)
    gen.duration_sec = duration_sec
    gen.rtf = (elapsed / duration_sec) if duration_sec and duration_sec > 0 else None
    gen.status = "succeeded"
    gen.finished_at = _now()
    if speaker:
        speaker.usage_count = (speaker.usage_count or 0) + 1
        speaker.last_used_at = gen.finished_at
    job.status = "succeeded"
    job.progress_current = 1
    job.progress_total = 1
    job.progress_message = "done"
    job.finished_at = gen.finished_at
    session.commit()


def _write_silence(path: Path, duration_ms: int, sample_rate: int = 24_000) -> None:
    frames = int(sample_rate * max(0, duration_ms) / 1000)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"\x00\x00" * frames)


def _concat_wavs(wavs: list[Path], out_path: Path) -> None:
    if not wavs:
        raise RuntimeError("concat_no_input")
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg_not_found")
    concat_list = out_path.parent / f"{out_path.stem}_concat.txt"
    concat_list.write_text("".join(f"file '{w.resolve()}'\n" for w in wavs))
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    concat_list.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg_concat_failed: {proc.stderr[-500:]}")


def _convert_wav(wav_path: Path, out_path: Path) -> None:
    if out_path.suffix.lower() == ".wav":
        if wav_path != out_path:
            shutil.copyfile(wav_path, out_path)
        return
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg_not_found")
    cmd = ["ffmpeg", "-y", "-i", str(wav_path), "-b:a", "192k", str(out_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg_convert_failed: {proc.stderr[-500:]}")


def _podcast_text(req: PodcastJobRequest) -> str:
    lines = []
    if req.title:
        lines.append(f"# {req.title}")
    for seg in req.segments:
        prefix = f"{seg.label}: " if seg.label else ""
        lines.append(f"{prefix}{seg.text}")
    return "\n\n".join(lines)


ProgressCallback = Callable[[int, int, str], None]


def synthesize_podcast_request(
    *,
    settings: Settings,
    session,
    gen: Generation,
    req: PodcastJobRequest,
    progress: ProgressCallback | None = None,
) -> tuple[Path, float, float]:
    """Synthesize a PodcastJobRequest immediately and update the Generation."""
    total = len(req.segments)
    if progress:
        progress(0, total, "starting")

    with tempfile.TemporaryDirectory(prefix=f"omnivoice_podcast_{gen.id}_") as tmpd:
        tmp_root = Path(tmpd)
        wav_parts: list[Path] = []
        total_duration = 0.0
        started = time.perf_counter()

        for idx, seg in enumerate(req.segments):
            speaker = _resolve_speaker(session, seg.speaker_id)
            speaker_prompt_only = bool(speaker and speaker.prompt_blob_path and not speaker.source_audio_path)
            engine_id = resolve_engine(
                settings,
                req.engine,
                speaker_has_omnivoice_prompt_only=speaker_prompt_only,
            )
            ref_audio_path: Path | None = None
            voice_prompt_path: Path | None = None
            if engine_id == ENGINE_QWEN3_TTS:
                if speaker and not speaker.source_audio_path:
                    raise RuntimeError("qwen3_tts_requires_speaker_ref_audio")
                ref_audio_path = settings.data_dir / speaker.source_audio_path if speaker.source_audio_path else None
            else:
                ref_audio_path, voice_prompt_path = ensure_speaker_voice_prompt(
                    settings=settings,
                    session=session,
                    speaker=speaker,
                    preprocess_prompt=req.params.preprocess_prompt,
                )
            label = seg.label or speaker.name
            if progress:
                progress(idx, total, f"{label} segment {idx + 1}/{total}")

            seg_wav = tmp_root / f"segment_{idx:04d}.wav"
            if engine_id == ENGINE_QWEN3_TTS:
                dur = synthesize_qwen3_tts(
                    settings=settings,
                    text=seg.text,
                    language=seg.language or req.language,
                    instruct=None,
                    ref_audio_path=ref_audio_path,
                    ref_transcript=speaker.ref_transcript if speaker else None,
                    params=req.params,
                    out_path=seg_wav,
                )
            else:
                dur = synthesize(
                    settings=settings,
                    text=seg.text,
                    language=seg.language or req.language,
                    instruct=None,
                    ref_audio_path=ref_audio_path,
                    ref_transcript=speaker.ref_transcript if speaker else None,
                    voice_prompt_path=voice_prompt_path,
                    params=req.params,
                    out_path=seg_wav,
                )
            total_duration += dur
            wav_parts.append(seg_wav)

            if req.pause_ms > 0 and idx < total - 1:
                pause_wav = tmp_root / f"pause_{idx:04d}.wav"
                _write_silence(pause_wav, req.pause_ms)
                total_duration += req.pause_ms / 1000.0
                wav_parts.append(pause_wav)

        final_wav = tmp_root / "podcast.wav"
        if progress:
            progress(total, total, "concatenating")
        _concat_wavs(wav_parts, final_wav)

        out_path = audio_path_for(settings, gen.id, req.format)
        _convert_wav(final_wav, out_path)
        elapsed = time.perf_counter() - started

    gen.audio_path = relpath(settings, out_path)
    gen.duration_sec = total_duration
    gen.rtf = (elapsed / total_duration) if total_duration > 0 else None
    gen.status = "succeeded"
    gen.finished_at = _now()
    session.commit()
    return out_path, total_duration, elapsed


def _run_podcast_job(settings: Settings, session, job: Job, gen: Generation | None) -> None:
    if gen is None:
        raise RuntimeError("generation_missing")

    req = PodcastJobRequest.model_validate(job.request_json)

    def progress(current: int, total: int, message: str) -> None:
        _set_job_progress(session, job, current=current, total=total, message=message)

    synthesize_podcast_request(
        settings=settings,
        session=session,
        gen=gen,
        req=req,
        progress=progress,
    )
    total = len(req.segments)
    job.status = "succeeded"
    job.progress_current = total
    job.progress_total = total
    job.progress_message = "done"
    job.finished_at = gen.finished_at
    session.commit()
