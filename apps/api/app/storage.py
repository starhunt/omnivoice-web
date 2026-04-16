"""로컬 파일 스토리지 헬퍼."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from .config import Settings


ALLOWED_AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


class AudioTooLarge(ValueError):
    pass


class UnsupportedAudioFormat(ValueError):
    pass


def safe_ext(filename: str | None) -> str:
    if not filename:
        return ""
    ext = Path(filename).suffix.lower()
    return ext if ext in ALLOWED_AUDIO_EXTS else ""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def save_upload(
    settings: Settings,
    src_path: Path,
    target_subdir: str,
    target_name: str,
) -> Path:
    """임시 경로에서 영구 위치로 이동."""
    dst_dir = settings.data_dir / target_subdir
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / target_name
    shutil.move(str(src_path), str(dst))
    return dst


def audio_path_for(settings: Settings, generation_id: str, fmt: str) -> Path:
    return settings.audio_dir / f"{generation_id}.{fmt}"


def relpath(settings: Settings, abs_path: Path) -> str:
    try:
        return str(abs_path.resolve().relative_to(settings.data_dir.resolve()))
    except ValueError:
        return str(abs_path)
