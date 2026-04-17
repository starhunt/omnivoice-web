#!/usr/bin/env python
"""OmniVoice 엔진 브리지 CLI.

OmniVoice 리포의 .venv Python에서 실행되어야 한다. FastAPI 프로세스에서
subprocess로 호출되며, 결과는 stdout에 단일 JSON 라인으로 반환한다.

환경변수:
  OMNIVOICE_ENGINE_PATH  엔진 루트 (sys.path 추가용)
  OMNIVOICE_DEVICE       cpu | mps | cuda (기본 mps)

stdin:
  단일 JSON 객체(요청). schema는 --schema 플래그로 출력 가능.
  - text (str) 단일 텍스트 — 하위 호환
  - chunks (list[str]) 장문 분할 합성용. 설정되면 text는 무시.

stdout:
  {"status": "ok", "out_path": "...", "duration_sec": 3.2, "sample_rate": 24000, "chunk_count": 1}
  or
  {"status": "error", "error": "..."}
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import traceback
from pathlib import Path


def _get_inference_dtype(device: str):
    """Match OmniVoice's official CLIs: fp16 on accelerators, fp32 on CPU."""
    import torch  # noqa: WPS433

    if str(device).startswith("cpu"):
        return torch.float32
    return torch.float16


def _ensure_engine_importable() -> None:
    engine_path = os.environ.get("OMNIVOICE_ENGINE_PATH")
    if engine_path:
        p = Path(engine_path)
        if p.exists() and str(p) not in sys.path:
            sys.path.insert(0, str(p))


def _empty_device_cache(device: str) -> None:
    """디바이스별 캐시 해제 (실패해도 무시)."""
    try:
        import torch  # noqa: WPS433
    except ImportError:
        return
    try:
        if device.startswith("cuda"):
            torch.cuda.empty_cache()
        elif device == "mps":
            if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                torch.mps.empty_cache()
    except Exception:
        pass


def _to_mono_f32(tensor):
    """torch tensor 또는 numpy를 float32 mono numpy로 변환 + [-1,1] 클리핑."""
    import numpy as np

    arr = tensor
    if hasattr(arr, "detach"):
        arr = arr.detach().cpu().numpy()
    arr = np.asarray(arr, dtype=np.float32)
    if arr.ndim > 1:
        arr = arr.mean(axis=0) if arr.shape[0] < arr.shape[-1] else arr[:, 0]
    return np.clip(arr, -1.0, 1.0)


def _concat_with_crossfade(arrays, sample_rate: int, crossfade_ms: int = 30):
    """인접 청크 사이에 선형 crossfade로 합치기 (경계 클릭 방지)."""
    import numpy as np

    if not arrays:
        return np.zeros(0, dtype=np.float32)
    if len(arrays) == 1:
        return arrays[0]

    fade_n = int(sample_rate * crossfade_ms / 1000)
    result = arrays[0].astype(np.float32, copy=True)
    for nxt in arrays[1:]:
        nxt = nxt.astype(np.float32, copy=False)
        if fade_n > 0 and len(result) >= fade_n and len(nxt) >= fade_n:
            tail = result[-fade_n:]
            head = nxt[:fade_n]
            fade_out = np.linspace(1.0, 0.0, fade_n, dtype=np.float32)
            fade_in = np.linspace(0.0, 1.0, fade_n, dtype=np.float32)
            mixed = tail * fade_out + head * fade_in
            result = np.concatenate([result[:-fade_n], mixed, nxt[fade_n:]])
        else:
            result = np.concatenate([result, nxt])
    return result


def _write_wav(arr, sample_rate: int, out_path: Path) -> float:
    import numpy as np
    import soundfile as sf

    arr = np.clip(arr, -1.0, 1.0).astype(np.float32)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    target = out_path if out_path.suffix.lower() == ".wav" else out_path.with_suffix(".wav")
    sf.write(str(target), arr, sample_rate, subtype="PCM_16")
    return float(len(arr)) / float(sample_rate)


def _load_voice_clone_prompt(path: str):
    import torch
    from omnivoice.models.omnivoice import VoiceClonePrompt  # type: ignore

    payload = torch.load(path, map_location="cpu")
    return VoiceClonePrompt(
        ref_audio_tokens=payload["ref_audio_tokens"].detach().cpu(),
        ref_text=str(payload["ref_text"]),
        ref_rms=float(payload["ref_rms"]),
    )


def _save_voice_clone_prompt(prompt, out_path: Path) -> None:
    import torch

    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "ref_audio_tokens": prompt.ref_audio_tokens.detach().cpu(),
            "ref_text": prompt.ref_text,
            "ref_rms": float(prompt.ref_rms),
        },
        out_path,
    )


def _load_model(model_id: str, device: str):
    from omnivoice.models.omnivoice import OmniVoice  # type: ignore

    dtype = _get_inference_dtype(device)
    if str(device).startswith("mps"):
        # device_map="mps" can trip Transformers allocator warmup on some macOS/PyTorch
        # combinations. Loading fp16 on CPU first and then moving to MPS keeps the
        # memory win while preserving the code path that already works here.
        return OmniVoice.from_pretrained(model_id, dtype=dtype).to(device).eval()
    return OmniVoice.from_pretrained(model_id, device_map=device, dtype=dtype).eval()


def run_synthesis(req: dict) -> dict:
    _ensure_engine_importable()
    import torch
    from omnivoice.models.omnivoice import OmniVoiceGenerationConfig  # type: ignore

    device = os.environ.get("OMNIVOICE_DEVICE", "mps")
    model_id = req.get("model_id") or "k2-fsa/OmniVoice"

    model = _load_model(model_id, device)
    # 모델 .to(device) 과정에서 남은 임시 할당을 즉시 해제 — voice clone prompt
    # 생성/generate 단계의 peak 여유 확보 목적.
    gc.collect()
    _empty_device_cache(device)

    params: dict = req.get("params") or {}
    gen_cfg = OmniVoiceGenerationConfig.from_dict(params)

    # Voice clone prompt: 청크 전체에 공통으로 재사용 (한 번만 생성)
    # 참조 오디오 전처리는 GPU peak 메모리가 크므로 반드시 no_grad 컨텍스트에서 실행하고
    # 직후 캐시를 비워서 이후 model.generate()의 할당 여유를 확보한다.
    voice_clone_prompt = None
    voice_prompt_path = req.get("voice_prompt_path")
    ref_audio = req.get("ref_audio_path")
    ref_text = req.get("ref_transcript")
    if voice_prompt_path:
        voice_clone_prompt = _load_voice_clone_prompt(str(voice_prompt_path))
    elif ref_audio:
        with torch.no_grad():
            voice_clone_prompt = model.create_voice_clone_prompt(
                ref_audio=ref_audio,
                ref_text=ref_text,
                preprocess_prompt=gen_cfg.preprocess_prompt,
            )
        gc.collect()
        _empty_device_cache(device)

    # 청크 리스트 구성 (chunks 우선, 없으면 text 단일로)
    chunks = [str(c) for c in (req.get("chunks") or []) if str(c).strip()]
    if not chunks:
        single = req.get("text")
        if not single:
            raise RuntimeError("missing_input: text or chunks required")
        chunks = [str(single)]

    sample_rate = int(req.get("sample_rate") or 24_000)
    out_path = Path(req["out_path"])
    single_chunk = len(chunks) == 1

    audio_arrays: list = []
    try:
        for idx, chunk_text in enumerate(chunks):
            kw = dict(text=chunk_text, generation_config=gen_cfg)
            if req.get("language"):
                kw["language"] = req["language"]
            if req.get("instruct"):
                kw["instruct"] = req["instruct"]
            if req.get("speed") is not None:
                kw["speed"] = req["speed"]
            # duration은 길이 타겟팅용 — 장문 분할에서는 청크별로 적용하면 왜곡되므로 단일 청크일 때만 전달
            if single_chunk and req.get("duration") is not None:
                kw["duration"] = req["duration"]
            if voice_clone_prompt is not None:
                kw["voice_clone_prompt"] = voice_clone_prompt

            with torch.no_grad():
                audio_list = model.generate(**kw)
            if not audio_list:
                raise RuntimeError(
                    f"empty audio output from engine (chunk={idx + 1}/{len(chunks)})"
                )

            audio_arrays.append(_to_mono_f32(audio_list[0]))

            # 청크 간 메모리 해제 — 장문에서 피크 메모리 바운드 유지
            del audio_list
            gc.collect()
            _empty_device_cache(device)
    finally:
        # 모델 언로드 (subprocess 종료 직전이지만 명시적으로)
        del model
        gc.collect()
        _empty_device_cache(device)

    final = _concat_with_crossfade(audio_arrays, sample_rate, crossfade_ms=30)
    duration = _write_wav(final, sample_rate, out_path)

    return {
        "status": "ok",
        "out_path": str(out_path),
        "duration_sec": duration,
        "sample_rate": sample_rate,
        "chunk_count": len(chunks),
    }


def run_prepare_prompt(req: dict) -> dict:
    """Create and persist a reusable voice clone prompt for registered speakers."""
    _ensure_engine_importable()
    import torch

    device = os.environ.get("OMNIVOICE_DEVICE", "mps")
    model_id = req.get("model_id") or "k2-fsa/OmniVoice"
    ref_audio = req["ref_audio_path"]
    ref_text = req.get("ref_transcript")
    out_path = Path(req["out_path"])
    preprocess_prompt = bool(req.get("preprocess_prompt", True))

    model = _load_model(model_id, device)
    try:
        with torch.no_grad():
            prompt = model.create_voice_clone_prompt(
                ref_audio=ref_audio,
                ref_text=ref_text,
                preprocess_prompt=preprocess_prompt,
            )
        _save_voice_clone_prompt(prompt, out_path)
    finally:
        del model
        gc.collect()
        _empty_device_cache(device)

    return {
        "status": "ok",
        "out_path": str(out_path),
        "ref_text": str(prompt.ref_text),
    }


def run_transcribe(req: dict) -> dict:
    """참조 오디오를 Whisper로 전사만 수행. OmniVoice 메인 모델은 로드하지 않음."""
    _ensure_engine_importable()
    import torch

    device = os.environ.get("OMNIVOICE_DEVICE", "mps")
    model_id = req.get("model_id") or "k2-fsa/OmniVoice"
    ref_audio = req["ref_audio_path"]

    # OmniVoice의 from_pretrained은 audio_tokenizer/asr_model 포함. ASR만 사용.
    model = _load_model(model_id, device)
    try:
        with torch.no_grad():
            # ref_text 없이 create_voice_clone_prompt → Whisper 자동 실행
            vcp = model.create_voice_clone_prompt(
                ref_audio=ref_audio,
                ref_text=None,
                preprocess_prompt=True,
            )
        transcript = getattr(vcp, "ref_text", None) or getattr(vcp, "text", None)
        if not transcript:
            raise RuntimeError("transcribe_no_text: Whisper 결과를 추출하지 못함")
    finally:
        del model
        gc.collect()
        _empty_device_cache(device)

    return {"status": "ok", "transcript": str(transcript)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", action="store_true", help="입력 스키마 출력")
    parser.add_argument("--transcribe", action="store_true", help="참조 오디오만 Whisper로 전사")
    parser.add_argument("--prepare-prompt", action="store_true", help="화자 복제 prompt를 생성/저장")
    args = parser.parse_args()

    if args.prepare_prompt:
        try:
            raw = sys.stdin.read()
            req = json.loads(raw) if raw.strip() else {}
            result = run_prepare_prompt(req)
            sys.stdout.write(json.dumps(result))
            return 0
        except Exception as exc:
            sys.stdout.write(json.dumps({
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc()[-4000:],
            }))
            return 1

    if args.transcribe:
        try:
            raw = sys.stdin.read()
            req = json.loads(raw) if raw.strip() else {}
            result = run_transcribe(req)
            sys.stdout.write(json.dumps(result))
            return 0
        except Exception as exc:
            sys.stdout.write(json.dumps({
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "trace": traceback.format_exc()[-4000:],
            }))
            return 1

    if args.schema:
        print(json.dumps({
            "text": "str (chunks 비었을 때 사용)",
            "chunks": "list[str] (장문 분할 합성; 우선 적용)",
            "language": "str|null",
            "instruct": "str|null",
            "ref_audio_path": "str|null",
            "ref_transcript": "str|null",
            "voice_prompt_path": "str|null (ref_audio보다 우선)",
            "speed": "float|null",
            "duration": "float|null (단일 청크에서만 적용)",
            "params": "dict (OmniVoiceGenerationConfig keys)",
            "out_path": "str",
            "sample_rate": "int (default 24000)",
            "model_id": "str (default k2-fsa/OmniVoice)",
        }))
        return 0

    try:
        raw = sys.stdin.read()
        req = json.loads(raw) if raw.strip() else {}
        result = run_synthesis(req)
        sys.stdout.write(json.dumps(result))
        return 0
    except Exception as exc:
        sys.stdout.write(json.dumps({
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "trace": traceback.format_exc()[-4000:],
        }))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
