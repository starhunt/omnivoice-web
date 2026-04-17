#!/usr/bin/env python
"""Qwen3-TTS subprocess bridge.

stdin JSON payload:
{
  "mode": "custom_voice|voice_design|voice_clone",
  "model": "Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice",
  "text": "...",
  "language": "Korean",
  "speaker": "Sohee",
  "instruct": "...",
  "ref_audio_path": "/path/ref.wav",
  "ref_text": "...",
  "x_vector_only_mode": false,
  "out_path": "/tmp/out.wav",
  "device_map": "cuda:0",
  "dtype": "bfloat16",
  "attn_implementation": "flash_attention_2"
}
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path


def _json_out(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _dtype(name: str):
    import torch

    normalized = (name or "bfloat16").lower()
    if normalized in {"bf16", "bfloat16"}:
        return torch.bfloat16
    if normalized in {"fp16", "float16", "half"}:
        return torch.float16
    if normalized in {"fp32", "float32"}:
        return torch.float32
    return torch.bfloat16


def _duration(path: Path) -> float:
    import soundfile as sf

    info = sf.info(str(path))
    return float(info.frames) / float(info.samplerate)


def _load_model(req: dict):
    from qwen_tts import Qwen3TTSModel

    kwargs = {
        "device_map": req.get("device_map") or "cuda:0",
        "dtype": _dtype(str(req.get("dtype") or "bfloat16")),
    }
    attn = req.get("attn_implementation")
    if attn:
        kwargs["attn_implementation"] = str(attn)
    return Qwen3TTSModel.from_pretrained(str(req["model"]), **kwargs)


def run_health() -> None:
    import torch
    import qwen_tts  # noqa: F401

    _json_out(
        {
            "status": "ok",
            "torch": torch.__version__,
            "cuda": torch.version.cuda,
            "cuda_available": torch.cuda.is_available(),
            "device": torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
            "bf16": torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
        }
    )


def run_synthesize(req: dict) -> None:
    import soundfile as sf

    model = _load_model(req)
    mode = str(req.get("mode") or "custom_voice")
    text = req["text"]
    language = req.get("language") or "Auto"

    if mode == "voice_clone":
        kwargs = {
            "text": text,
            "language": language,
            "ref_audio": req.get("ref_audio_path"),
        }
        ref_text = req.get("ref_text")
        if ref_text:
            kwargs["ref_text"] = ref_text
        if req.get("x_vector_only_mode"):
            kwargs["x_vector_only_mode"] = True
        wavs, sr = model.generate_voice_clone(**kwargs)
    elif mode == "voice_design":
        wavs, sr = model.generate_voice_design(
            text=text,
            language=language,
            instruct=req.get("instruct") or "",
        )
    else:
        wavs, sr = model.generate_custom_voice(
            text=text,
            language=language,
            speaker=req.get("speaker") or "Sohee",
            instruct=req.get("instruct") or "",
        )

    out_path = Path(req["out_path"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_path), wavs[0], sr)
    _json_out(
        {
            "status": "ok",
            "out_path": str(out_path),
            "sample_rate": sr,
            "duration_sec": _duration(out_path),
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--health", action="store_true")
    args = parser.parse_args()

    try:
        if args.health:
            run_health()
        else:
            req = json.loads(sys.stdin.read() or "{}")
            run_synthesize(req)
        return 0
    except Exception as exc:
        _json_out(
            {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc()[-4000:],
            }
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
