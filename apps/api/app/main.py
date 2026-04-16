"""FastAPI 엔트리포인트."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from .config import get_settings
from .db import SessionLocal, init_db
from .models import Generation
from .routers import assets, generations, health, meta, speakers, tts

logger = logging.getLogger("omnivoice-web")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)


def _finalize_stale_running_jobs() -> int:
    """이전 프로세스에서 running 상태로 남은 job들을 interrupted 처리.

    서버가 합성 도중 OOM/재부팅/크래시로 중단되면 status='running'이 DB에 남는다.
    이 시점에 그 prcoess는 이미 죽었으므로 안전하게 failed로 확정한다.
    """
    with SessionLocal() as session:
        stmt = (
            update(Generation)
            .where(Generation.status == "running")
            .values(
                status="failed",
                error="interrupted_by_restart",
                finished_at=datetime.now(timezone.utc),
            )
        )
        result = session.execute(stmt)
        session.commit()
        return int(result.rowcount or 0)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.ensure_dirs()
    init_db()
    stale = _finalize_stale_running_jobs()
    if stale:
        logger.warning("finalized %d stale running job(s) → failed(interrupted)", stale)
    logger.info("omnivoice-web api started (device=%s)", settings.omnivoice_device)
    yield
    logger.info("omnivoice-web api stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="OmniVoice-Web API",
        version="0.1.0",
        description="단일 사용자 OmniVoice TTS 플랫폼 REST API.",
        lifespan=lifespan,
        openapi_url="/v1/openapi.json",
        docs_url="/docs",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # /v1 프리픽스
    for r in (health.router, meta.router, speakers.router, tts.router, generations.router, assets.router):
        app.include_router(r, prefix="/v1")

    @app.get("/", include_in_schema=False)
    def root() -> dict:
        return {
            "name": "omnivoice-web-api",
            "version": "0.1.0",
            "docs": "/docs",
            "openapi": "/v1/openapi.json",
        }

    return app


app = create_app()
