"""애플리케이션 설정 (환경변수 → Pydantic)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
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
