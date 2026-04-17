"""애플리케이션 설정 (환경변수 → Pydantic)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # TTS 엔진 선택
    tts_default_engine: str = Field(
        default="auto",
        description="auto | omnivoice | qwen3-tts",
    )

    # OmniVoice 엔진
    omnivoice_engine_path: Path = Field(
        default=Path("/Users/starhunter/StudyProj/voiceproj/OmniVoice"),
        description="OmniVoice 리포지토리 루트",
    )
    omnivoice_engine_python: Path = Field(
        default=Path("/Users/starhunter/StudyProj/voiceproj/OmniVoice/.venv/bin/python"),
        description="엔진 실행용 Python 인터프리터",
    )
    omnivoice_device: str = Field(default="mps", description="cpu | mps | cuda")

    # Qwen3-TTS 엔진 (별도 venv/subprocess 사용)
    qwen3_tts_enabled: bool = Field(default=True)
    qwen3_tts_python: Path = Field(
        default=Path("/opt/engines/qwen3-tts/.venv/bin/python"),
        description="Qwen3-TTS 실행용 Python 인터프리터",
    )
    qwen3_tts_model: str = Field(default="Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice")
    qwen3_tts_clone_model: str = Field(default="Qwen/Qwen3-TTS-12Hz-1.7B-Base")
    qwen3_tts_design_model: str = Field(default="Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign")
    qwen3_tts_device: str = Field(default="cuda:0")
    qwen3_tts_dtype: str = Field(default="bfloat16")
    qwen3_tts_attn_implementation: str = Field(default="flash_attention_2")
    qwen3_tts_default_speaker: str = Field(default="Sohee")

    # 인증
    omnivoice_api_key: str = Field(default="dev-key-change-me")

    # API 서버
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8320)
    database_url: str = Field(default="sqlite:///./data/app.db")
    data_dir: Path = Field(default=Path("./data"))
    cors_origins: str = Field(default="http://localhost:5320")

    model_config = SettingsConfigDict(
        env_file=[".env", "../../.env"],
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def audio_dir(self) -> Path:
        return self.data_dir / "audio"

    @property
    def speakers_dir(self) -> Path:
        return self.data_dir / "speakers"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.audio_dir, self.speakers_dir, self.uploads_dir):
            p.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    s.ensure_dirs()
    return s
