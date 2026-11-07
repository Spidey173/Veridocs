"""
Health checks, LLM provider registry inspection, and administrative maintenance endpoints.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Depends

from config import get_settings, get_model_registry
from auth import require_admin_or_maintenance, UserContext
from models import HealthResponse
import database
from session_store import sessions, cleanup_expired_sessions

logger = logging.getLogger(__name__)

router = APIRouter(tags=["system"])


@router.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check returning model, database, and service status."""
    settings = get_settings()
    registry = get_model_registry()
    db_configured = database.is_database_configured()
    db_connected = database.is_database_ready() if db_configured else False

    status = "healthy"
    if settings.ENVIRONMENT == "production":
        if not db_configured or not db_connected:
            status = "degraded"

    return HealthResponse(
        status=status,
        version=settings.APP_VERSION,
        active_sessions=len(sessions),
        models_loaded={
            "embedding": registry._embedding_model is not None,
            "reranker": registry._reranker_model is not None,
        },
        providers_available=settings.get_available_llm_providers(),
        database_connected=db_connected if db_configured else None
    )


@router.get("/api/llm/providers")
async def list_llm_providers():
    """Return available LLM providers, active selection, and configuration status."""
    settings = get_settings()
    available = settings.get_available_llm_providers()
    return {
        "active_provider": settings.LLM_PROVIDER,
        "available_providers": available,
        "supported_providers": [
            "openai", "anthropic", "deepseek", "groq", "google",
            "mistral", "openrouter", "github", "ollama", "custom", "offline"
        ],
        "default_configured": any(available.values())
    }


@router.post("/api/admin/cleanup")
async def trigger_retention_cleanup(
    max_age_hours: Optional[int] = None,
    admin_user: UserContext = Depends(require_admin_or_maintenance)
):
    """Trigger manual data retention purge of expired sessions and orphaned files."""
    settings = get_settings()
    target_max_age = max_age_hours if max_age_hours is not None else settings.RETENTION_HOURS
    if target_max_age < 1 or target_max_age > 720:
        raise HTTPException(
            status_code=400,
            detail="Invalid max_age_hours: Must be between 1 and 720 hours."
        )

    result = cleanup_expired_sessions(max_age_hours=target_max_age)
    return {
        "status": "success",
        "retention_hours": target_max_age,
        **result
    }
