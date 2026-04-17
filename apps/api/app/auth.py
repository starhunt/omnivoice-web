"""API Key 인증 (단일 키 MVP)."""

from __future__ import annotations

import hmac

from fastapi import Depends, Header, HTTPException, status

from .config import Settings, get_settings


def verify_api_key(
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None),
    xi_api_key: str | None = Header(default=None, alias="xi-api-key"),
    x_goog_api_key: str | None = Header(default=None, alias="x-goog-api-key"),
    settings: Settings = Depends(get_settings),
) -> None:
    """
    두 헤더 모두 허용:
      Authorization: Bearer <key>
      X-API-Key: <key>
      xi-api-key: <key>  # ElevenLabs 호환
      x-goog-api-key: <key>  # Gemini 호환
    """
    provided: str | None = None
    if authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            provided = parts[1].strip()
    if provided is None and x_api_key:
        provided = x_api_key.strip()
    if provided is None and xi_api_key:
        provided = xi_api_key.strip()
    if provided is None and x_goog_api_key:
        provided = x_goog_api_key.strip()

    expected = settings.omnivoice_api_key
    if not provided or not expected or not hmac.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_api_key",
            headers={"WWW-Authenticate": "Bearer"},
        )
