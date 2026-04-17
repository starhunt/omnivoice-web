"""Import bundled/local OmniVoice demo speakers into the app library."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from sqlalchemy import select

from .config import Settings
from .db import SessionLocal
from .models import Speaker

logger = logging.getLogger(__name__)


_DEMO_SPEAKER_META = {
    "korean_demo_speaker": {
        "name": "OmniVoice Korean Demo",
        "tags": ["omnivoice-demo", "default", "ko"],
        "note": "OmniVoice demo speaker imported from the local engine speaker store.",
        "language_hint": "ko",
    },
    "korean_demo_speaker_kr": {
        "name": "OmniVoice Korean Demo KR",
        "tags": ["omnivoice-demo", "default", "ko"],
        "note": "OmniVoice demo speaker imported from the local engine speaker store.",
        "language_hint": "ko",
    },
}


def _find_preview_audio(source_dir: Path, stem: str) -> Path | None:
    for path in sorted(source_dir.glob(f"{stem}__ref.*")):
        if path.is_file():
            return path
    return None


def sync_omnivoice_demo_speakers(settings: Settings) -> int:
    """Copy local OmniVoice demo speaker prompts into app data once.

    The upstream demo stores user/demo speakers under ``.omnivoice_speakers``.
    Those prompt blobs are already compatible with our engine subprocess, but
    they are outside the web app DB until imported here.
    """

    source_dir = settings.omnivoice_engine_path / ".omnivoice_speakers"
    if not source_dir.exists():
        return 0

    imported = 0
    with SessionLocal() as session:
        existing_names = set(session.scalars(select(Speaker.name)).all())

        for prompt_src in sorted(source_dir.glob("*.pt")):
            meta = _DEMO_SPEAKER_META.get(prompt_src.stem)
            if not meta:
                continue
            if meta["name"] in existing_names:
                continue

            speaker = Speaker(
                name=meta["name"],
                tags=list(meta["tags"]),
                note=meta["note"],
                language_hint=meta["language_hint"],
                is_favorite=False,
            )
            session.add(speaker)
            session.flush()

            speaker_dir = settings.speakers_dir / speaker.id
            speaker_dir.mkdir(parents=True, exist_ok=True)

            prompt_dst = speaker_dir / "prompt-imported.pt"
            shutil.copy2(prompt_src, prompt_dst)
            speaker.prompt_blob_path = str(prompt_dst.relative_to(settings.data_dir))

            preview_src = _find_preview_audio(source_dir, prompt_src.stem)
            if preview_src:
                ref_dst = speaker_dir / f"ref{preview_src.suffix.lower()}"
                shutil.copy2(preview_src, ref_dst)
                speaker.source_audio_path = str(ref_dst.relative_to(settings.data_dir))

            existing_names.add(speaker.name)
            imported += 1

        session.commit()

    if imported:
        logger.info("imported %d OmniVoice demo speaker(s)", imported)
    return imported
