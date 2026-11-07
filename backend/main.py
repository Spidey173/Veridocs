"""
Veridocs — Enterprise Document Intelligence & Verification Engine API.
High-throughput document extraction, hybrid vector search (RRF), cross-encoder reranking,
claim-level RAG Triad grounding verification, and cross-document contradiction auditing.
"""

import asyncio
import logging
import threading
import shutil
from pathlib import Path
from typing import Union, Dict, Any, List
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import get_settings, get_model_registry
import database

# Modular Routers
from routers import auth, documents, jobs, query, audit, system

# Re-exported domain components for backward compatibility
from session_store import (
    sessions,
    _sessions_lock,
    _get_session,
    _safe_delete_file,
    _persist_session_background,
    _generate_insights_background,
    _cleanup_session,
    cleanup_expired_sessions,
    _retention_cleanup_loop,
    _validate_question,
)
from rate_limiter import (
    _http_rate_limiter,
    InMemoryRateLimiter,
    HttpRateLimiter,
    enforce_rate_limit,
)
from routers.query import _generate_followups, _sse_event

# Aliases for existing test fixtures
_rate_limiter = _http_rate_limiter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager handling startup validation, database pool, warmup, and graceful shutdown."""
    # Validate configuration on startup
    settings.validate_production_configuration()

    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")

    # Initialize PostgreSQL + pgvector if configured
    if database.is_database_configured():
        db_ok = await database.init_db()
        if not db_ok and settings.ENVIRONMENT == "production":
            raise RuntimeError(
                "FATAL DATABASE ERROR: Could not connect to PostgreSQL database in production mode. "
                "Refusing to start in a degraded multi-worker state to prevent worker divergence."
            )
    elif settings.ENVIRONMENT == "production":
        raise RuntimeError(
            "FATAL CONFIGURATION ERROR: DATABASE_URL must be configured when ENVIRONMENT=production. "
            "Multi-worker production nodes require a shared PostgreSQL + pgvector database."
        )

    # Preload models in background thread
    def _warmup():
        reg = get_model_registry()
        _ = reg.embedding_model
        if settings.RERANKER_ENABLED:
            _ = reg.reranker_model

    threading.Thread(target=_warmup, daemon=True).start()

    # Start background cleanup task if enabled
    cleanup_task = None
    if settings.AUTO_CLEANUP_ENABLED:
        cleanup_task = asyncio.create_task(_retention_cleanup_loop())

    yield

    # Teardown
    if database.is_database_configured():
        await database.close_db()

    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Document Intelligence & Verification API",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
)

# Ensure upload directory exists
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

# Register modular sub-routers
app.include_router(auth.router)
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(query.router)
app.include_router(audit.router)
app.include_router(system.router)

# Mount static frontend build if present
try:
    frontend_path = Path(__file__).parent.parent / "frontend" / "out"
    if frontend_path.exists():
        app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
except Exception as e:
    logger.warning(f"Frontend static files not mounted: {e}")


@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"message": f"Welcome to {settings.APP_NAME} API v{settings.APP_VERSION}. Visit /docs for API documentation."}


# Re-export route handlers for test imports
generate_demo_token = auth.generate_demo_token
upload_documents = documents.upload_documents
get_document_pdf = documents.get_document_pdf
get_document_insights = documents.get_document_insights
get_session_info = documents.get_session_info
delete_session = documents.delete_session
delete_document_from_session = documents.delete_document_from_session
submit_async_document_job = jobs.submit_async_document_job
get_job_status = jobs.get_job_status
list_user_jobs = jobs.list_user_jobs
delete_or_cancel_job = jobs.delete_or_cancel_job
answer_query = query.answer_query
stream_query = query.stream_query
chat_stream = query.chat_stream
get_conversation_history = query.get_conversation_history
audit_contradictions = audit.audit_contradictions
health_check = system.health_check
list_llm_providers = system.list_llm_providers
trigger_retention_cleanup = system.trigger_retention_cleanup
