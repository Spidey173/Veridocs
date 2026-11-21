"""
Health check and system status endpoints for Veridocs.
"""

from fastapi import APIRouter
from config import get_settings, get_model_registry
from models import HealthResponse
import database

router = APIRouter(tags=["system"])


@router.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check returning real status of embedding model, SQLite DB, and LLM configuration."""
    settings = get_settings()
    reg = get_model_registry()
    sessions = database.list_sessions()

    return HealthResponse(
        status="healthy",
        version="0.2.0",
        llm_configured=settings.is_llm_configured(),
        active_sessions=len(sessions),
        embedding_model_loaded=reg._embedding_model is not None,
    )


@router.get("/api/llm/status")
async def llm_status():
    """Return LLM endpoint and model status."""
    settings = get_settings()
    return {
        "configured": settings.is_llm_configured(),
        "base_url": settings.LLM_BASE_URL or "Not set",
        "model": settings.LLM_MODEL or "Not set",
    }
