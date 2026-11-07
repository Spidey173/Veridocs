import os
import time
import json
import hmac
import base64
import secrets
import hashlib
import tempfile
import logging
from pathlib import Path
from typing import Optional
from pydantic import BaseModel
from fastapi import HTTPException, Header, Request

from config import get_settings

logger = logging.getLogger(__name__)

# Fallback secret if not configured in environment
_EPHEMERAL_SECRET: str = secrets.token_hex(32)


def _get_dev_secret() -> str:
    """
    Get or create a local secret stored on disk for development.
    Stored outside web-accessible and upload directories with restricted (0o600) file permissions.
    """
    try:
        secret_dir = Path.home() / ".veridocs"
        try:
            secret_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            secret_file = secret_dir / ".auth_dev_secret"
        except Exception:
            secret_file = Path(tempfile.gettempdir()) / ".veridocs_auth_dev_secret"

        if secret_file.exists():
            content = secret_file.read_text(encoding="utf-8").strip()
            if len(content) >= 32:
                return content

        new_secret = secrets.token_hex(32)
        # Create with restricted permissions (read/write by owner only)
        fd = os.open(str(secret_file), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with open(fd, "w", encoding="utf-8") as f:
            f.write(new_secret)
        return new_secret
    except Exception as e:
        logger.debug(f"Could not persist dev secret on disk: {e}")
        return _EPHEMERAL_SECRET


class UserContext(BaseModel):
    """Holds information about the currently authenticated user."""
    user_id: str
    created_at: float
    expires_at: float
    role: str = "user"


def _get_signing_key() -> str:
    """Get the secret key used to sign tokens."""
    settings = get_settings()
    if settings.AUTH_SECRET_KEY and settings.AUTH_SECRET_KEY.strip():
        return settings.AUTH_SECRET_KEY.strip()

    if settings.ENVIRONMENT == "production" or settings.AUTH_MODE == "gateway":
        raise RuntimeError(
            "FATAL SECURITY CONFIGURATION: AUTH_SECRET_KEY is required in production/gateway mode."
        )

    return _get_dev_secret()


def _b64encode(data: bytes) -> str:
    """Base64 encode without padding."""
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64decode(data: str) -> bytes:
    """Base64 decode with padding restoration."""
    padding = "=" * ((4 - len(data) % 4) % 4)
    return base64.urlsafe_b64decode(data + padding)


def create_access_token(
    user_id: Optional[str] = None,
    expires_in_hours: Optional[int] = None,
    role: str = "user"
) -> str:
    """Generate an HMAC-SHA256 signed access token."""
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
    """Validate token signature and expiration."""
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

    signing_key = _get_signing_key().encode("utf-8")
    expected_sig = hmac.new(signing_key, payload_b64.encode("utf-8"), hashlib.sha256).digest()
    expected_sig_b64 = _b64encode(expected_sig)

    if not hmac.compare_digest(sig_b64, expected_sig_b64):
        raise HTTPException(
            status_code=401,
            detail="Invalid token signature."
        )

    try:
        payload_bytes = _b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        raise HTTPException(
            status_code=401,
            detail=f"Unable to decode token payload: {str(e)}"
        )

    exp = payload.get("exp", 0)
    if time.time() > exp:
        raise HTTPException(
            status_code=401,
            detail="Authentication token has expired."
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
) -> UserContext:
    """FastAPI dependency to extract and verify the current user."""
    settings = get_settings()

    # Validate API key if configured
    if settings.REQUIRE_API_KEY:
        configured_api_key = settings.API_KEY
        client_key = x_api_key
        if not client_key and authorization and authorization.startswith("ApiKey "):
            client_key = authorization[7:].strip()

        if not client_key or not hmac.compare_digest(client_key, configured_api_key):
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing API key."
            )

    # Check for gateway headers if in gateway mode
    if settings.AUTH_MODE == "gateway":
        gateway_user = request.headers.get(settings.GATEWAY_USER_HEADER)
        if gateway_user and gateway_user.strip():
            if settings.GATEWAY_SHARED_SECRET:
                provided_gw_secret = request.headers.get(settings.GATEWAY_SECRET_HEADER)
                if not provided_gw_secret or not hmac.compare_digest(
                    provided_gw_secret.strip(), settings.GATEWAY_SHARED_SECRET
                ):
                    raise HTTPException(
                        status_code=401,
                        detail="Untrusted gateway request."
                    )

            gateway_role = request.headers.get(settings.GATEWAY_ROLE_HEADER, "user").strip()
            return UserContext(
                user_id=gateway_user.strip(),
                created_at=time.time(),
                expires_at=time.time() + (settings.TOKEN_EXPIRE_HOURS * 3600),
                role=gateway_role
            )

    # Extract bearer token from header
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
            "Authentication required. Provide a valid Bearer token."
            if settings.AUTH_MODE == "gateway"
            else "Authentication required. Provide a Bearer token in the Authorization header."
        )
        raise HTTPException(
            status_code=401,
            detail=detail_msg
        )

    return verify_access_token(candidate_token)


async def require_admin_or_maintenance(
    request: Request,
    authorization: Optional[str] = Header(None),
    x_user_token: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None),
    x_admin_key: Optional[str] = Header(None),
) -> UserContext:
    """FastAPI dependency to require admin role or admin API key."""
    settings = get_settings()

    # Check for admin API key
    if settings.ADMIN_API_KEY:
        admin_candidate = x_admin_key
        if not admin_candidate and authorization and authorization.startswith("AdminKey "):
            admin_candidate = authorization[9:].strip()
        if admin_candidate and hmac.compare_digest(admin_candidate.strip(), settings.ADMIN_API_KEY):
            return UserContext(
                user_id="maintenance_worker",
                created_at=time.time(),
                expires_at=time.time() + 3600,
                role="admin"
            )

    # Check user role
    user = await get_current_user(
        request=request,
        authorization=authorization,
        x_user_token=x_user_token,
        x_api_key=x_api_key
    )
    if user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Access denied: Administrator privileges required."
        )
    return user
