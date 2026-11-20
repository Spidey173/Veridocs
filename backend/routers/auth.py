"""
Authentication and token generation endpoints for Veridocs.
"""

import os
import secrets
import logging
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, Header, Request

from config import get_settings
from auth import create_access_token, create_demo_token, verify_access_token
from rate_limiter import enforce_rate_limit

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class DemoTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    expires_in: int
    mode: str = "demo"
    warning: str


@router.post("/demo-token", response_model=DemoTokenResponse)
@router.post("/token", response_model=DemoTokenResponse)
async def generate_demo_token(request: Request, x_api_key: Optional[str] = Header(None)):
    """Generate a demo user token for local development and demonstration."""
    settings = get_settings()
    enforce_rate_limit(request, "auth_token", max_requests=60, window_seconds=60)
    raw_env = (os.getenv("ENV") or os.getenv("ENVIRONMENT") or settings.ENVIRONMENT).strip().lower()
    if raw_env == "production" or settings.AUTH_MODE == "gateway":
        raise HTTPException(
            status_code=403,
            detail="Demo tokens are disabled in production mode."
        )

    if settings.REQUIRE_API_KEY:
        if not x_api_key or x_api_key != settings.API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")

    token = create_demo_token()
    user_ctx = verify_access_token(token)

    return DemoTokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user_ctx.user_id,
        expires_in=int(user_ctx.expires_at - user_ctx.created_at),
        mode="demo",
        warning="Local ephemeral demo token. Low-privilege demo role. Maximum 15 minutes lifetime."
    )

