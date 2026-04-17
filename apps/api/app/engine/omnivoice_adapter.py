"""OmniVoice 엔진 어댑터 (subprocess 기반).

핵심 설계:
  - FastAPI 프로세스는 엔진 모델을 직접 로드하지 않는다.
  - 엔진 리포의 .venv Python으로 engine_cli.py를 subprocess 호출.
  - 엔진 미설치/실패 시 stub 모드로 폴백(무음 WAV 생성) — 프론트/API 통합 검증용.

Phase 2:
  - Celery 워커에서 모델을 상주시키고 RPC 호출로 이식.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any

from ..config import Settings
from ..schemas import TTSParams

logger = logging.getLogger(__name__)


class EngineError(RuntimeError):
    pass


SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "engine_cli.py"
DEFAULT_TIMEOUT_SEC = int(os.environ.get("OMNIVOICE_TIMEOUT_SEC", "1800"))
# 장문 분할 임계/최대 글자 수 (한글/영문 혼용 기준)
# MPS(통합 메모리) 환경에서 엔진이 한 청크를 처리할 때 수 GB 단위 peak 할당이 발생하므로
# 기본값을 보수적으로 잡는다. 고사양/여유 메모리 환경에서는 환경변수로 상향 가능.
CHUNK_THRESHOLD_CHARS = int(os.environ.get("OMNIVOICE_CHUNK_THRESHOLD_CHARS", "220"))
CHUNK_MAX_CHARS = int(os.environ.get("OMNIVOICE_CHUNK_MAX_CHARS", "200"))
CHUNK_MIN_MERGE_CHARS = int(os.environ.get("OMNIVOICE_CHUNK_MIN_CHARS", "60"))
# 청크별 subprocess 격리 모드
#   "1"   → 강제 사용 (청크마다 새 subprocess, MPS 메모리 완전 회수)
#   "0"   → 사용 안 함 (단일 subprocess에서 청크 순회)
#   "auto"→ MPS 환경에서만 자동 사용 (기본값)
# 트레이드오프: 청크별 모델 로딩 오버헤드(~10초) vs. 메모리 누수 제거
ISOLATE_CHUNKS_MODE = os.environ.get("OMNIVOICE_ISOLATE_CHUNKS", "auto").lower()

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?。！？])\s+|\n+")


def _split_long_sentence(sentence: str, max_chars: int) -> list[str]:
    """문장 자체가 너무 길 때 쉼표/공백 기준으로 재분할. 최후엔 강제 자르기."""
    if len(sentence) <= max_chars:
        return [sentence]
    out: list[str] = []
    remaining = sentence
    while len(remaining) > max_chars:
        # max_chars의 50%~100% 구간에서 가장 뒤쪽 경계 찾기
        window_start = int(max_chars * 0.5)
        cut = -1
        for sep in (", ", "、", ", ", ",", " "):
            idx = remaining.rfind(sep, window_start, max_chars)
            if idx > cut:
                cut = idx + len(sep)
        if cut <= 0:
            cut = max_chars  # 경계 없으면 강제 절단
        piece = remaining[:cut].strip()
        if piece:
            out.append(piece)
        remaining = remaining[cut:].strip()
    if remaining:
        out.append(remaining)
    return out


def split_text_for_synthesis(
    text: str,
    *,
    threshold: int = CHUNK_THRESHOLD_CHARS,
    max_chars: int = CHUNK_MAX_CHARS,
    min_merge: int = CHUNK_MIN_MERGE_CHARS,
) -> list[str]:
    """합성용 텍스트 분할.

    - threshold 이하 → 단일 청크 반환 (분할 없음)
    - 초과 시 문장 경계(., !, ?, 。, ！, ？, 줄바꿈)로 1차 분할
    - 긴 문장은 쉼표/공백으로 2차 분할
    - 너무 작은 인접 청크는 max_chars 이내에서 병합 (문맥 보존)
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= threshold:
        return [text]

    # 1차: 문장 경계 분할
    raw = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s and s.strip()]
    if not raw:
        raw = [text]

    # 2차: 긴 문장 재분할
    pieces: list[str] = []
    for s in raw:
        if len(s) <= max_chars:
            pieces.append(s)
        else:
            pieces.extend(_split_long_sentence(s, max_chars))

    # 3차: 인접 작은 청크 병합 (TTS 억양 자연스러움 확보)
    merged: list[str] = []
    cur = ""
    for p in pieces:
        if not cur:
            cur = p
            continue
        if len(cur) < min_merge and len(cur) + 1 + len(p) <= max_chars:
            cur = f"{cur} {p}"
        elif len(cur) + 1 + len(p) <= max_chars and len(p) < min_merge:
            cur = f"{cur} {p}"
        else:
            merged.append(cur)
            cur = p
    if cur:
        merged.append(cur)
    return merged


def engine_status(settings: Settings) -> dict:
    engine_ok = settings.omnivoice_engine_path.exists()
    python_ok = settings.omnivoice_engine_python.exists()
    script_ok = SCRIPT_PATH.exists()
    return {
        "engine_path_exists": engine_ok,
        "engine_python_exists": python_ok,
        "bridge_script_exists": script_ok,
        "mode": "live" if (engine_ok and python_ok and script_ok) else "stub",
    }


def build_instruct_from_design(design: dict[str, Any]) -> str | None:
    """보이스 디자인 폼 값을 쉼표 구분 instruct 문자열로."""
    order = ["gender", "age", "pitch", "style", "english_accent", "chinese_dialect"]
    parts: list[str] = []
    for key in order:
        val = design.get(key)
        if val:
            parts.append(str(val).strip())
    return ", ".join(parts) if parts else None


def _stub_wav(out_path: Path, text: str) -> float:
    """엔진 없이 사인파 WAV 생성 (UX 개발용)."""
    sample_rate = 24_000
    # 텍스트 길이에 비례한 초 단위 (1초 최소)
    seconds = max(1.0, min(20.0, len(text) * 0.06))
    n_samples = int(sample_rate * seconds)
    freq = 220.0 + (len(text) % 7) * 30.0
    amp = 0.2

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        data_bytes_len = n_samples * 2
        # WAV 헤더
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_bytes_len))
        f.write(b"WAVE")
        f.write(b"fmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16))
        f.write(b"data")
        f.write(struct.pack("<I", data_bytes_len))
        for i in range(n_samples):
            v = amp * math.sin(2.0 * math.pi * freq * i / sample_rate)
            f.write(struct.pack("<h", int(v * 32767)))
    return seconds


def _convert_to_mp3_if_needed(wav_path: Path, target_path: Path) -> None:
    if target_path == wav_path:
        return
    if shutil.which("ffmpeg") is None:
        raise EngineError(
            "ffmpeg_not_found: MP3 변환에는 ffmpeg 필요. 'brew install ffmpeg' 또는 WAV 포맷 사용."
        )
    cmd = ["ffmpeg", "-y", "-i", str(wav_path), "-b:a", "192k", str(target_path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise EngineError(f"ffmpeg_failed: {proc.stderr[-500:]}")
    wav_path.unlink(missing_ok=True)


def transcribe_ref_audio(settings: Settings, ref_audio_path: Path) -> str:
    """참조 오디오를 Whisper로 전사. 별도 subprocess라 합성과 메모리 공존 안 함.

    한 번만 실행하여 Speaker.ref_transcript에 저장하고 재사용하는 것이 권장 사용법.
    """
    payload = {"ref_audio_path": str(ref_audio_path)}
    env = os.environ.copy()
    env.update({
        "OMNIVOICE_ENGINE_PATH": str(settings.omnivoice_engine_path),
        "OMNIVOICE_DEVICE": settings.omnivoice_device,
        "PYTHONUNBUFFERED": "1",
    })
    # PYTORCH_MPS_*_WATERMARK_RATIO는 의도적으로 설정하지 않는다.
    # 0.0(상한 해제)으로 두면 OS 한계까지 무제한 할당 시도 → jetsam이 SIGKILL.
    # PyTorch 기본값(HIGH=1.4)은 RAM × 1.4 도달 시 자체 OOM exception을 던져 graceful 실패.
    # 환경변수로 명시 설정한 경우만 존중.

    cmd = [str(settings.omnivoice_engine_python), str(SCRIPT_PATH), "--transcribe"]
    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=300,
            env=env,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise EngineError("transcribe_timeout") from exc

    stdout = (proc.stdout or "").strip()
    if not stdout:
        raise EngineError(f"transcribe_no_output (rc={proc.returncode}): {(proc.stderr or '')[-500:]}")
    try:
        result = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError as exc:
        raise EngineError(f"transcribe_bad_output: {stdout[-500:]}") from exc
    if result.get("status") != "ok":
        raise EngineError(f"transcribe_failed: {result.get('error')}")
    return str(result.get("transcript") or "").strip()


def prepare_voice_clone_prompt(
    settings: Settings,
    *,
    ref_audio_path: Path,
    ref_transcript: str | None,
    out_path: Path,
    preprocess_prompt: bool = True,
) -> str:
    """Create a reusable OmniVoice VoiceClonePrompt blob in an engine subprocess."""
    payload = {
        "ref_audio_path": str(ref_audio_path),
        "ref_transcript": ref_transcript,
        "out_path": str(out_path),
        "preprocess_prompt": preprocess_prompt,
    }
    env = os.environ.copy()
    env.update({
        "OMNIVOICE_ENGINE_PATH": str(settings.omnivoice_engine_path),
        "OMNIVOICE_DEVICE": settings.omnivoice_device,
        "PYTHONUNBUFFERED": "1",
    })

    cmd = [str(settings.omnivoice_engine_python), str(SCRIPT_PATH), "--prepare-prompt"]
    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=600,
            env=env,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise EngineError("prepare_prompt_timeout") from exc

    stdout = (proc.stdout or "").strip()
    if not stdout:
        raise EngineError(
            f"prepare_prompt_no_output (rc={proc.returncode}): {(proc.stderr or '')[-500:]}"
        )
    try:
        result = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError as exc:
        raise EngineError(f"prepare_prompt_bad_output: {stdout[-500:]}") from exc
    if result.get("status") != "ok":
        raise EngineError(f"prepare_prompt_failed: {result.get('error')}")
    return str(result.get("ref_text") or "").strip()


def synthesize(
    *,
    settings: Settings,
    text: str,
    language: str | None,
    instruct: str | None,
    ref_audio_path: Path | None,
    ref_transcript: str | None,
    voice_prompt_path: Path | None,
    params: TTSParams,
    out_path: Path,
) -> float:
    """동기 합성. duration_sec를 반환. 실패 시 EngineError."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # 엔진은 항상 .wav로 먼저 산출 후 필요 시 MP3로 변환
    wav_out = out_path.with_suffix(".wav")

    status = engine_status(settings)
    if status["mode"] == "stub":
        logger.warning("engine in stub mode: %s", status)
        duration = _stub_wav(wav_out, text)
    else:
        duration = _run_engine_subprocess(
            settings=settings,
            text=text,
            language=language,
            instruct=instruct,
            ref_audio_path=ref_audio_path,
            ref_transcript=ref_transcript,
            voice_prompt_path=voice_prompt_path,
            params=params,
            wav_out=wav_out,
        )

    _convert_to_mp3_if_needed(wav_out, out_path)
    return duration


def _should_isolate_chunks(settings: Settings) -> bool:
    if ISOLATE_CHUNKS_MODE == "1":
        return True
    if ISOLATE_CHUNKS_MODE == "0":
        return False
    # auto: MPS 환경에선 기본 격리 (프로세스 종료 전까지 MPS 메모리 회수가 불확실)
    return settings.omnivoice_device == "mps"


def _run_engine_subprocess(
    *,
    settings: Settings,
    text: str,
    language: str | None,
    instruct: str | None,
    ref_audio_path: Path | None,
    ref_transcript: str | None,
    voice_prompt_path: Path | None,
    params: TTSParams,
    wav_out: Path,
) -> float:
    # 화자 복제 모드는 ref_audio 인코딩 peak + generate peak가 동시에 MPS를 요구해
    # 짧은 단일 청크여도 SIGKILL이 발생. 임계/최대치를 더 타이트하게 적용하여 반드시
    # 분할 + 격리 subprocess 경로로 보낸다.
    if ref_audio_path is not None or voice_prompt_path is not None:
        chunks = split_text_for_synthesis(
            text,
            threshold=min(100, CHUNK_THRESHOLD_CHARS),
            max_chars=min(120, CHUNK_MAX_CHARS),
            min_merge=min(40, CHUNK_MIN_MERGE_CHARS),
        )
    else:
        chunks = split_text_for_synthesis(text)
    if len(chunks) <= 1:
        # 단일 청크: 격리 의미 없음
        return _invoke_engine_once(
            settings=settings,
            chunks=chunks or [text],
            language=language,
            instruct=instruct,
            ref_audio_path=ref_audio_path,
            ref_transcript=ref_transcript,
            voice_prompt_path=voice_prompt_path,
            params=params,
            wav_out=wav_out,
            pass_duration=True,
        )

    if _should_isolate_chunks(settings):
        logger.info(
            "long text (%d chars) → %d chunks, isolated-subprocess mode",
            len(text),
            len(chunks),
        )
        return _run_engine_isolated_chunks(
            settings=settings,
            chunks=chunks,
            language=language,
            instruct=instruct,
            ref_audio_path=ref_audio_path,
            ref_transcript=ref_transcript,
            voice_prompt_path=voice_prompt_path,
            params=params,
            wav_out=wav_out,
        )

    logger.info(
        "long text (%d chars) → %d chunks, shared-subprocess mode",
        len(text),
        len(chunks),
    )
    return _invoke_engine_once(
        settings=settings,
        chunks=chunks,
        language=language,
        instruct=instruct,
        ref_audio_path=ref_audio_path,
        ref_transcript=ref_transcript,
        voice_prompt_path=voice_prompt_path,
        params=params,
        wav_out=wav_out,
        pass_duration=False,
    )


def _invoke_engine_once(
    *,
    settings: Settings,
    chunks: list[str],
    language: str | None,
    instruct: str | None,
    ref_audio_path: Path | None,
    ref_transcript: str | None,
    voice_prompt_path: Path | None,
    params: TTSParams,
    wav_out: Path,
    pass_duration: bool,
) -> float:
    """한 번의 subprocess 호출로 chunks 리스트를 처리."""
    payload: dict[str, Any] = {
        "chunks": chunks,
        "language": language,
        "instruct": instruct,
        "ref_audio_path": str(ref_audio_path) if ref_audio_path else None,
        "ref_transcript": ref_transcript,
        "voice_prompt_path": str(voice_prompt_path) if voice_prompt_path else None,
        "speed": params.speed,
        "params": params.model_dump(exclude_none=True),
        "out_path": str(wav_out),
        "sample_rate": 24_000,
    }
    if pass_duration:
        payload["duration"] = params.duration

    env = os.environ.copy()
    env.update({
        "OMNIVOICE_ENGINE_PATH": str(settings.omnivoice_engine_path),
        "OMNIVOICE_DEVICE": settings.omnivoice_device,
        "PYTHONUNBUFFERED": "1",
    })
    # MPS watermark는 시스템 전체 VM 사용량("other allocations")을 포함해 계산되어
    # 실사용량이 낮아도 상한에 걸려 할당이 거부될 수 있다. 청킹으로 실제 엔진 메모리가
    # 바운드되어 있으므로 상한을 해제한다. 사용자가 명시적으로 설정했으면 그 값을 존중.
    # PYTORCH_MPS_*_WATERMARK_RATIO는 의도적으로 설정하지 않는다.
    # 0.0(상한 해제)으로 두면 OS 한계까지 무제한 할당 시도 → jetsam이 SIGKILL.
    # PyTorch 기본값(HIGH=1.4)은 RAM × 1.4 도달 시 자체 OOM exception을 던져 graceful 실패.
    # 환경변수로 명시 설정한 경우만 존중.

    cmd = [str(settings.omnivoice_engine_python), str(SCRIPT_PATH)]
    try:
        proc = subprocess.run(
            cmd,
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            timeout=DEFAULT_TIMEOUT_SEC,
            env=env,
            # macOS jetsam은 프로세스 그룹 단위로 메모리를 집계할 수 있다. uvicorn
            # worker(수백 MB) + engine subprocess(MPS peak ~GB)가 같은 그룹이면 jetsam이
            # 가장 큰 소비자인 engine 쪽을 우선 kill 대상으로 삼는다. 새 세션으로 분리해
            # 독립 프로세스로 회계되게 한다.
            start_new_session=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise EngineError(f"engine_timeout: {DEFAULT_TIMEOUT_SEC}s 초과") from exc

    stdout = (proc.stdout or "").strip()
    stderr_full = proc.stderr or ""

    # 실패 시 전체 stderr를 파일에 덤프 (SIGKILL 등 원인 분석용)
    if proc.returncode != 0 or not stdout:
        try:
            import time as _time
            dump_dir = Path("/tmp/omnivoice_engine_failures")
            dump_dir.mkdir(parents=True, exist_ok=True)
            ts = _time.strftime("%Y%m%d_%H%M%S")
            dump_path = dump_dir / f"fail_{ts}_rc{proc.returncode}.log"
            dump_path.write_text(
                f"# engine_cli subprocess failure\n"
                f"# rc={proc.returncode}\n"
                f"# payload keys: {sorted(payload.keys())}\n"
                f"# text chars: {len(payload.get('text') or '')} | chunks: {len(payload.get('chunks') or [])}\n"
                f"# ref_audio: {payload.get('ref_audio_path')}\n"
                f"# ref_transcript set: {bool(payload.get('ref_transcript'))}\n"
                f"# voice_prompt: {payload.get('voice_prompt_path')}\n"
                f"# params: {payload.get('params')}\n"
                f"# ---- stderr full ----\n{stderr_full}\n"
                f"# ---- stdout full ----\n{stdout}\n"
            )
            hint = f" [full log: {dump_path}]"
        except Exception as dump_exc:
            hint = f" [dump failed: {dump_exc}]"
        logger.error("engine subprocess failed (rc=%d)%s", proc.returncode, hint)

    if not stdout:
        raise EngineError(
            f"engine_no_output (rc={proc.returncode}): {stderr_full[-500:]}{hint if 'hint' in dir() else ''}"
        )
    try:
        result = json.loads(stdout.splitlines()[-1])
    except json.JSONDecodeError as exc:
        raise EngineError(f"engine_bad_output: {stdout[-500:]}") from exc

    if result.get("status") != "ok":
        err = result.get("error") or "unknown"
        raise EngineError(f"engine_failed: {err}")

    return float(result.get("duration_sec") or 0.0)


def _run_engine_isolated_chunks(
    *,
    settings: Settings,
    chunks: list[str],
    language: str | None,
    instruct: str | None,
    ref_audio_path: Path | None,
    ref_transcript: str | None,
    voice_prompt_path: Path | None,
    params: TTSParams,
    wav_out: Path,
) -> float:
    """청크마다 새 subprocess를 띄워 합성한 뒤 ffmpeg로 연결.

    장점: 각 청크 후 subprocess가 종료되어 MPS 메모리가 OS에 완전 반환.
    비용: 청크당 모델 로딩(~10초) 발생.
    """
    import tempfile

    total_duration = 0.0
    with tempfile.TemporaryDirectory(prefix="omnivoice_chunks_") as tmpd:
        tmp_root = Path(tmpd)
        chunk_wavs: list[Path] = []
        for idx, chunk_text in enumerate(chunks):
            chunk_wav = tmp_root / f"chunk_{idx:04d}.wav"
            logger.info(
                "isolated chunk %d/%d (%d chars)",
                idx + 1,
                len(chunks),
                len(chunk_text),
            )
            dur = _invoke_engine_once(
                settings=settings,
                chunks=[chunk_text],
                language=language,
                instruct=instruct,
                ref_audio_path=ref_audio_path,
                ref_transcript=ref_transcript,
                voice_prompt_path=voice_prompt_path,
                params=params,
                wav_out=chunk_wav,
                pass_duration=False,
            )
            total_duration += dur
            chunk_wavs.append(chunk_wav)

        _concat_wavs_ffmpeg(chunk_wavs, wav_out)

    return total_duration


def _concat_wavs_ffmpeg(wavs: list[Path], out_path: Path) -> None:
    """ffmpeg concat demuxer로 청크 WAV들을 무손실 연결.

    청크는 문장 경계에서 쪼개져 있어 경계의 오디오가 대부분 무음에 가까움 → 단순 접합으로 충분.
    """
    if not wavs:
        raise EngineError("concat_no_input: 청크 wav가 없습니다")
    if len(wavs) == 1:
        shutil.copyfile(wavs[0], out_path)
        return
    if shutil.which("ffmpeg") is None:
        raise EngineError(
            "ffmpeg_not_found: 청크 격리 모드는 ffmpeg 필요. 'brew install ffmpeg' 또는 "
            "OMNIVOICE_ISOLATE_CHUNKS=0 으로 공유 모드 사용."
        )
    concat_list = wavs[0].parent / "concat.txt"
    concat_list.write_text("".join(f"file '{w.resolve()}'\n" for w in wavs))
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list),
        "-c", "copy",
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise EngineError(f"ffmpeg_concat_failed: {proc.stderr[-500:]}")
