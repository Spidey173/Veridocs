"""
Authentication and Access Control module for Veridocs.
Provides tamper-proof, signed token authentication (HMAC-SHA256),
multi-tenant user isolation, and gateway API key verification.
"""

import os
import time
import json
import hmac
import base64
import secrets
import hashlib
import logging
from typing import Optional, Dict, Any
from pydantic import BaseModel
from fastapi import HTTPException, Header, Query, Request

from config import get_settings

logger = logging.getLogger(__name__)

# Fallback in-memory secret generated on server startup if not specified in env
_EPHEMERAL_SECRET: str = secrets.token_hex(32)


class UserContext(BaseModel):
    """Authenticated user context attached to request state."""
    user_id: str
    created_at: float
    expires_at: float
    role: str = "user"


def _get_signing_key() -> str:
    """
    Retrieve secret signing key from settings or fallback to ephemeral startup secret in dev/demo.
    Fails fast in production/gateway mode if secret is unconfigured.
    """
    settings = get_settings()
    if settings.AUTH_SECRET_KEY and settings.AUTH_SECRET_KEY.strip():
        return settings.AUTH_SECRET_KEY.strip()

    if settings.ENVIRONMENT == "production" or settings.AUTH_MODE == "gateway":
        raise RuntimeError(
            "FATAL SECURITY CONFIGURATION: AUTH_SECRET_KEY is required in production/gateway mode."
        )

    return _EPHEMERAL_SECRET


def _b64encode(data: bytes) -> str:
    """URL-safe base64 encoding without padding."""
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64decode(data: str) -> bytes:
    """URL-safe base64 decoding with padding restoration."""
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(
    user_id: Optional[str] = None,
    expires_in_hours: Optional[int] = None,
    role: str = "user"
) -> str:
    """
    Generate a cryptographically signed, tamper-proof user token.
    Token structure: base64url(payload).base64url(hmac_sha256_signature)
    """
    settings = get_settings()
    now = time.time()
    ttl_hours = expires_in_hours or settings.TOKEN_EXPIRE_HOURS or 24
    exp = now + (ttl_hours * 3600)

    uid = user_id or f"usr_{secrets.token_hex(10)}"

    payload = {
        "uid": uid,
        "iat": int(now),
        "exp": int(exp),
        "role": role,
    }

    payload_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = _b64encode(payload_json)

    signing_key = _get_signing_key().encode("utf-8")
    sig = hmac.new(signing_key, payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = _b64encode(sig)

    return f"{payload_b64}.{sig_b64}"


def verify_access_token(token: str) -> UserContext:
    """
    Validate HMAC-SHA256 signature and expiration of a user token.
    Raises HTTPException(401) on failure.
    """
    if not token or "." not in token:
        raise HTTPException(
            status_code=401,
            detail="Malformed authentication token."
        )

    parts = token.split(".")
    if len(parts) != 2:
        raise HTTPException(
            status_code=401,
            detail="Malformed authentication token structure."
        )

    payload_b64, sig_b64 = parts

    # Verify signature
    signing_key = _get_signing_key().encode("utf-8")
    expected_sig = hmac.new(signing_key, payload_b64.encode("utf-8"), hashlib.sha256).digest()
    expected_sig_b64 = _b64encode(expected_sig)

    if not hmac.compare_digest(sig_b64, expected_sig_b64):
        raise HTTPException(
            status_code=401,
            detail="Invalid token signature. Token may have been tampered with or issued with a different secret."
        )

    # Decode and verify payload
    try:
        payload_bytes = _b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Unable to decode token payload: {str(e)}"
        )

    # Check expiration
    exp = payload.get("exp", 0)
    if time.time() > exp:
        raise HTTPException(
            status_code=401,
            detail="Authentication token has expired. Please refresh your session."
        )

    uid = payload.get("uid")
    if not uid:
        raise HTTPException(
            status_code=401,
            detail="Token payload missing valid user identity."
        )

    return UserContext(
        user_id=uid,
        created_at=float(payload.get("iat", time.time())),
        expires_at=float(exp),
        role=payload.get("role", "user")
    )


async def get_current_user(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_user_token: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None)
) -> UserContext:
    """
    FastAPI dependency for endpoint authentication & user identity resolution.
    Accepts:
    1. Header `X-Admin-Key: <key>` for administrative tasks
    2. Trusted Gateway headers (`X-Consumer-Custom-ID` / `X-Consumer-Role`) in gateway deployment mode
    3. Header `Authorization: Bearer <token>`
    4. Header `X-User-Token: <token>`

    Notice: Query parameter tokens (?token=...) are strictly rejected to prevent
    leakage in browser history, HTTP referrers, and server access logs.
    """
    settings = get_settings()

    # 1. Admin Key verification (for administrative operations like scheduled retention pruning)
    if settings.ADMIN_API_KEY:
        admin_candidate = x_admin_key
        if not admin_candidate and authorization and authorization.startswith("AdminKey "):
            admin_candidate = authorization[9:].strip()
        if admin_candidate and hmac.compare_digest(admin_candidate.strip(), settings.ADMIN_API_KEY):
            return UserContext(
                user_id="system_admin",
                created_at=time.time(),
                expires_at=time.time() + 3600,
                role="admin"
            )

    # 2. Deployment Gateway API Key validation (if enabled)
    if settings.REQUIRE_API_KEY:
        configured_api_key = settings.API_KEY
        client_key = x_api_key
        if not client_key and authorization and authorization.startswith("ApiKey "):
            client_key = authorization[7:].strip()

        if not client_key or not hmac.compare_digest(client_key, configured_api_key):
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing API key (X-API-Key required by deployment)."
            )

    # 3. Trusted Gateway Identity Header (in gateway/multi-user mode)
    if settings.AUTH_MODE == "gateway":
        gateway_user = request.headers.get(settings.GATEWAY_USER_HEADER)
        if gateway_user and gateway_user.strip():
            # If GATEWAY_SHARED_SECRET is configured, verify that the gateway authenticated itself
            if settings.GATEWAY_SHARED_SECRET:
                provided_gw_secret = request.headers.get(settings.GATEWAY_SECRET_HEADER)
                if not provided_gw_secret or not hmac.compare_digest(
                    provided_gw_secret.strip(), settings.GATEWAY_SHARED_SECRET
                ):
                    raise HTTPException(
                        status_code=401,
                        detail="Untrusted gateway request: missing or invalid gateway authentication secret."
                    )

            gateway_role = request.headers.get(settings.GATEWAY_ROLE_HEADER, "user").strip()
            return UserContext(
                user_id=gateway_user.strip(),
                created_at=time.time(),
                expires_at=time.time() + (settings.TOKEN_EXPIRE_HOURS * 3600),
                role=gateway_role
            )

    # 4. Bearer Token Extraction
    candidate_token = None
    if authorization:
        if authorization.lower().startswith("bearer "):
            candidate_token = authorization[7:].strip()
        else:
            candidate_token = authorization.strip()
    elif x_user_token:
        candidate_token = x_user_token.strip()

    if not candidate_token:
        detail_msg = (
            "Authentication required. Provide a valid Bearer token in the Authorization header "
            "or route requests through an authenticated API gateway."
            if settings.AUTH_MODE == "gateway"
            else "Authentication required. Provide a Bearer token in the Authorization header (or acquire a demo token via POST /api/auth/demo-token)."
        )
        raise HTTPException(
            status_code=401,
            detail=detail_msg
        )

    return verify_access_token(candidate_token)
