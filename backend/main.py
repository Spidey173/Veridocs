"""
Veridocs — FastAPI Backend
Endpoints for uploading documents, querying with citations, and document comparison.
"""

import os
# Limit thread pools to prevent high memory usage
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["VECLIB_MAXIMUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["ONNXRUNTIME_INTER_OP_NUM_THREADS"] = "1"
os.environ["ONNXRUNTIME_INTRA_OP_NUM_THREADS"] = "1"

import json
import time
import shutil
import logging
import uuid
import secrets
import asyncio
import threading
import numpy as np
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Union

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, BackgroundTasks, Depends, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import get_settings, get_model_registry
from auth import get_current_user, require_admin_or_maintenance, create_access_token, verify_access_token, UserContext
from pdf_processor import (
    extract_text_from_file,
    chunk_text,
)
import database
from vector_store import get_query_embedding
from reranker import rerank_chunks
from llm_service import FreeLLMService
from conversation import get_conversation_manager
from models import (
    QueryRequest,
    QueryResponse,
    StreamQueryRequest,
    SourceInfo,
    CitationInfo,
    ClaimVerification,
    MessageRole,
    UploadResponse,
    HealthResponse,
    RagTriadMetrics,
    CrossDocAuditRequest,
    JobStatus,
    JobProgress,
    JobResponse,
    JobDetailResponse,
    JobListResponse,
)
from job_tracker import get_job_tracker
from tasks import dispatch_document_job
from insights_engine import generate_document_insights
from verification import calculate_grounding_score, calculate_rag_triad_metrics, extract_citations_from_answer
from contradiction_engine import run_cross_document_audit, AuditDiffReport

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

async def _retention_cleanup_loop():
    """Periodic task to clean up old sessions."""
    logger.info(
        f"Retention cleaner started (interval: {settings.CLEANUP_INTERVAL_MINUTES}m, "
        f"retention: {settings.RETENTION_HOURS}h)"
    )
    while True:
        try:
            await asyncio.sleep(settings.CLEANUP_INTERVAL_MINUTES * 60)
            res = cleanup_expired_sessions(max_age_hours=settings.RETENTION_HOURS)
            if res.get("purged_sessions", 0) > 0 or res.get("purged_files", 0) > 0:
                logger.info(
                    f"Cleaned up {res['purged_sessions']} sessions, {res['purged_files']} files."
                )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error during retention cleanup: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
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

    # Preload models in background
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
    description="Document Intelligence API",
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

class InMemoryRateLimiter:
    """Sliding window rate limiter to prevent request flooding."""
    def __init__(self):
        self._lock = threading.Lock()
        self._history: Dict[str, List[float]] = {}
        self._last_cleanup = time.time()

    def check(self, key: str, max_requests: int, window_seconds: int = 60) -> bool:
        now = time.time()
        with self._lock:
            if now - self._last_cleanup > 300:
                expired_threshold = now - 3600
                keys_to_delete = [
                    k for k, timestamps in self._history.items()
                    if not timestamps or timestamps[-1] < expired_threshold
                ]
                for k in keys_to_delete:
                    del self._history[k]
                self._last_cleanup = now

            timestamps = self._history.setdefault(key, [])
            cutoff = now - window_seconds
            valid_timestamps = [t for t in timestamps if t > cutoff]
            self._history[key] = valid_timestamps

            if len(valid_timestamps) >= max_requests:
                return False

            valid_timestamps.append(now)
            return True

    def clear(self):
        """Reset rate limiter state (used in test fixtures)."""
        with self._lock:
            self._history.clear()


_rate_limiter = InMemoryRateLimiter()


def enforce_rate_limit(request: Request, key_suffix: str, max_requests: int = 60, window_seconds: int = 60):
    """Check that the request rate is within limits."""
    if not settings.RATE_LIMITING_ENABLED:
        return
    client_ip = request.client.host if request.client else "unknown_client"
    limiter_key = f"{client_ip}:{key_suffix}"
    if not _rate_limiter.check(limiter_key, max_requests=max_requests, window_seconds=window_seconds):
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded ({max_requests} requests per {window_seconds}s).",
            headers={"Retry-After": str(window_seconds)}
        )


class DemoTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    expires_in: int
    mode: str = "demo"
    warning: str

@app.post("/api/auth/demo-token", response_model=DemoTokenResponse)
@app.post("/api/auth/token", response_model=DemoTokenResponse)
async def generate_demo_token(request: Request, x_api_key: Optional[str] = Header(None)):
    """Generate a demo user token for development."""
    enforce_rate_limit(request, "auth_token", max_requests=60, window_seconds=60)
    if settings.ENVIRONMENT == "production" or settings.AUTH_MODE == "gateway":
        raise HTTPException(
            status_code=403,
            detail="Demo tokens are disabled in production mode."
        )

    if settings.REQUIRE_API_KEY:
        if not x_api_key or x_api_key != settings.API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")

    demo_uid = f"demo_usr_{secrets.token_hex(6)}"
    token = create_access_token(user_id=demo_uid, role="user")
    user_ctx = verify_access_token(token)

    return DemoTokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user_ctx.user_id,
        expires_in=int(settings.TOKEN_EXPIRE_HOURS * 3600),
        mode="demo",
        warning="Local demo token."
    )


# In-memory sessions storage
sessions: Dict[str, Dict] = {}
_sessions_lock = threading.Lock()


def _generate_insights_background(session_id: str, chunks_by_file: Dict, doc_metadata: List[Dict], provider: str):
    """Generate summary and questions in the background."""
    try:
        with _sessions_lock:
            session_data = sessions.get(session_id)
        if not session_data:
            return
        llm = FreeLLMService(provider=provider)
        insights_dict = session_data.get("insights", {})

        for fn, file_chunks in chunks_by_file.items():
            if fn in insights_dict:
                continue

            matching_meta = next((m for m in doc_metadata if m.get("filename") == fn), {})
            pages_count = matching_meta.get("num_pages", 0)

            logger.info(f"Generating background insights for {fn}...")
            doc_insights = generate_document_insights(
                session_id=session_id,
                chunks=file_chunks,
                llm_service=llm,
                total_pages=pages_count
            )
            with _sessions_lock:
                if session_id in sessions:
                    sessions[session_id].setdefault("insights", {})[fn] = doc_insights

        logger.info(f"Background insights complete for session {session_id}")
    except Exception as e:
        logger.error(f"Background insights generation failed: {e}", exc_info=True)


def _persist_session_background(session_id: str, saved_paths: List[str], file_names: List[str], doc_metadata: List[Dict], owner_id: str):
    """Save session metadata to disk for file management."""
    try:
        session_dir = Path(settings.UPLOAD_DIR) / "sessions" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        session_meta = {
            "session_id": session_id,
            "file_paths": saved_paths,
            "file_names": file_names,
            "metadata": doc_metadata,
            "created_at": time.time(),
            "owner_id": owner_id,
        }
        with open(session_dir / "session.json", "w", encoding="utf-8") as f:
            json.dump(session_meta, f, indent=2)
        logger.info(f"Saved session {session_id} to disk")
    except Exception as e:
        logger.warning(f"Could not persist session {session_id} to disk: {e}")


@app.post("/api/upload", response_model=UploadResponse)
async def upload_documents(
    request: Request,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Form(None),
    current_user: UserContext = Depends(get_current_user)
):
    """Upload and process document files (PDF, DOCX, TXT)."""
    enforce_rate_limit(request, "upload", max_requests=settings.UPLOAD_RATE_LIMIT, window_seconds=60)
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    all_chunks = []
    processed_files = 0
    failed_files = []
    doc_metadata = []
    saved_paths = []
    file_names = []

    for file in files:
        filename = file.filename or "unknown"
        ext = Path(filename).suffix.lower()

        # Validate extension
        if ext not in settings.ALLOWED_EXTENSIONS:
            failed_files.append(f"{filename} (unsupported type: {ext})")
            continue

        try:
            # Stream read file in 1MB chunks to prevent memory spikes
            max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
            chunk_bytes_list = []
            total_read = 0
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_read += len(chunk)
                if total_read > max_bytes:
                    failed_files.append(f"{filename} (exceeds {settings.MAX_FILE_SIZE_MB}MB limit)")
                    break
                chunk_bytes_list.append(chunk)

            if total_read > max_bytes:
                continue

            contents = b"".join(chunk_bytes_list)

            logger.info(f"Processing upload for user {current_user.user_id}: {filename} ({len(contents)} bytes)")

            # Save file to disk for PDF viewer
            session_file_id = str(uuid.uuid4())
            save_path = Path(settings.UPLOAD_DIR) / f"{session_file_id}{ext}"
            save_path.write_bytes(contents)

            # Stream extract text from disk to avoid in-memory byte duplication
            pages = extract_text_from_file(save_path, filename=filename)

            if not pages:
                failed_files.append(f"{filename} (no extractable text)")
                _safe_delete_file(save_path)
                continue

            metadata = {
                "filename": filename,
                "file_size_bytes": len(contents),
                "num_pages": len(pages),
                "is_encrypted": False,
                "metadata": {}
            }

            # Split text into chunks
            chunks = chunk_text(
                pages,
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP,
                document_name=filename
            )

            if chunks:
                for chunk in chunks:
                    chunk["source_file"] = filename

                all_chunks.extend(chunks)
                processed_files += 1
                doc_metadata.append(metadata)
                saved_paths.append(str(save_path))
                file_names.append(filename)

                logger.info(f"Processed {filename}: {len(chunks)} chunks")
            else:
                failed_files.append(f"{filename} (chunking failed)")
                _safe_delete_file(save_path)

        except ValueError as e:
            failed_files.append(f"{filename}: {str(e)}")
            logger.warning(f"ValueError processing {filename}: {str(e)}")
            if 'save_path' in locals() and save_path:
                _safe_delete_file(save_path)
        except Exception as e:
            failed_files.append(f"{filename}: Unexpected error")
            logger.error(f"Error processing {filename}: {str(e)}", exc_info=True)
            if 'save_path' in locals() and save_path:
                _safe_delete_file(save_path)

    if not all_chunks:
        error_msg = "No files could be processed. "
        if failed_files:
            error_msg += f"Issues: {'; '.join(failed_files[:3])}"
        raise HTTPException(status_code=400, detail=error_msg)

    try:
        # Generate embeddings only for newly uploaded chunks to keep incremental ingestion O(k)
        new_chunks = list(all_chunks)
        reg = get_model_registry()
        new_chunk_texts = [c["text"] for c in new_chunks]
        new_embeddings = reg.embedding_model.encode(
            new_chunk_texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            batch_size=settings.EMBEDDING_BATCH_SIZE
        )

        existing_insights = {}
        if session_id:
            existing_session = await _get_session(session_id, current_user)
            saved_paths = existing_session.get("file_paths", []) + saved_paths
            file_names = existing_session.get("file_names", []) + file_names
            doc_metadata = existing_session.get("metadata", []) + doc_metadata
            existing_chunks = existing_session.get("chunks", [])
            existing_embeddings = existing_session.get("embeddings")
            existing_insights = existing_session.get("insights", {})

            all_chunks = existing_chunks + new_chunks
            if (
                isinstance(existing_embeddings, np.ndarray)
                and len(existing_embeddings) == len(existing_chunks)
            ):
                embeddings = np.vstack([existing_embeddings, new_embeddings])
            else:
                # Fallback if in-memory embeddings were missing/deserialized
                embeddings = reg.embedding_model.encode(
                    [c["text"] for c in all_chunks],
                    convert_to_numpy=True,
                    show_progress_bar=False,
                    batch_size=settings.EMBEDDING_BATCH_SIZE
                )
        else:
            all_chunks = new_chunks
            embeddings = new_embeddings

        with _sessions_lock:
            if not session_id or session_id not in sessions:
                session_id = str(uuid.uuid4())

            from collections import defaultdict
            chunks_by_file = defaultdict(list)
            for chunk in all_chunks:
                fn = chunk.get("source_file", "unknown")
                chunks_by_file[fn].append(chunk)

            sessions[session_id] = {
                "chunks": all_chunks,
                "embeddings": embeddings,
                "file_paths": saved_paths,
                "file_names": file_names,
                "metadata": doc_metadata,
                "insights": existing_insights,
                "created_at": time.time(),
                "owner_id": current_user.user_id,
            }

            if len(sessions) > settings.MAX_SESSIONS:
                oldest_key = min(sessions, key=lambda k: sessions[k]["created_at"])
                _cleanup_session(oldest_key)

        # Save session to PostgreSQL if configured (only insert newly added chunks)
        if database.is_database_configured():
            try:
                saved_sess = await database.save_session(
                    session_id=session_id,
                    owner_id=current_user.user_id,
                    file_names=file_names,
                    file_paths=saved_paths,
                    metadata=doc_metadata,
                    insights=existing_insights,
                    created_at=time.time()
                )
                if not saved_sess and settings.ENVIRONMENT == "production":
                    raise HTTPException(
                        status_code=503,
                        detail="Failed to persist session to database in production mode. Aborting to prevent worker divergence."
                    )
                saved_chk = await database.save_chunks(session_id, new_chunks, new_embeddings)
                if not saved_chk and settings.ENVIRONMENT == "production":
                    raise HTTPException(
                        status_code=503,
                        detail="Failed to persist document chunks to database in production mode. Aborting to prevent worker divergence."
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to persist session {session_id} to PostgreSQL: {e}")
                if settings.ENVIRONMENT == "production":
                    raise HTTPException(
                        status_code=503,
                        detail=f"Database persistence failure in production: {str(e)}"
                    )
        elif settings.ENVIRONMENT == "production":
            raise HTTPException(
                status_code=503,
                detail="PostgreSQL database is required for uploads in production mode."
            )

        # Save session to disk in background
        background_tasks.add_task(
            _persist_session_background,
            session_id=session_id,
            saved_paths=saved_paths,
            file_names=file_names,
            doc_metadata=doc_metadata,
            owner_id=current_user.user_id,
        )

        # Generate summary and questions in background
        background_tasks.add_task(
            _generate_insights_background,
            session_id=session_id,
            chunks_by_file=dict(chunks_by_file),
            doc_metadata=doc_metadata,
            provider=settings.LLM_PROVIDER
        )

        message = f"Successfully processed {processed_files} file(s) with {len(all_chunks)} text chunks"
        if failed_files:
            message += f". {len(failed_files)} file(s) skipped."

        logger.info(f"Created session {session_id}: {message}")

        return UploadResponse(
            session_id=session_id,
            chunk_count=len(all_chunks),
            processed_files=processed_files,
            failed_files=failed_files,
            message=message,
            document_metadata=doc_metadata
        )

    except Exception as e:
        logger.error(f"Error creating vector store: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error indexing documents: {str(e)}")


@app.post("/api/jobs/upload", response_model=JobResponse, status_code=202)
@app.post("/api/upload/async", response_model=JobResponse, status_code=202)
async def submit_async_document_job(
    request: Request,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Form(None),
    current_user: UserContext = Depends(get_current_user)
):
    """
    Submit heavy documents (such as 100-300+ page SEC 10-K filings or scanned PDFs)
    for asynchronous background processing via Celery and Redis.
    Immediately returns HTTP 202 Accepted with a job_id for non-blocking polling.
    """
    enforce_rate_limit(request, "async_upload", max_requests=settings.UPLOAD_RATE_LIMIT, window_seconds=60)
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    saved_paths = []
    file_names = []
    failed_files = []

    for file in files:
        filename = file.filename or "unknown"
        ext = Path(filename).suffix.lower()

        if ext not in settings.ALLOWED_EXTENSIONS:
            failed_files.append(f"{filename} (unsupported type: {ext})")
            continue

        try:
            contents = await file.read()
            if len(contents) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
                failed_files.append(f"{filename} (exceeds {settings.MAX_FILE_SIZE_MB}MB limit)")
                continue

            session_file_id = str(uuid.uuid4())
            save_path = Path(settings.UPLOAD_DIR) / f"{session_file_id}{ext}"
            save_path.write_bytes(contents)

            saved_paths.append(str(save_path))
            file_names.append(filename)
        except Exception as e:
            failed_files.append(f"{filename}: {str(e)}")

    if not saved_paths:
        err = "No valid files could be accepted for processing."
        if failed_files:
            err += f" Issues: {'; '.join(failed_files)}"
        raise HTTPException(status_code=400, detail=err)

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    tracker = get_job_tracker()
    tracker.create_job(
        job_id=job_id,
        file_names=file_names,
        file_paths=saved_paths,
        owner_id=current_user.user_id,
        session_id=session_id
    )

    dispatch_document_job(
        job_id=job_id,
        file_paths=saved_paths,
        file_names=file_names,
        owner_id=current_user.user_id,
        session_id=session_id,
        background_tasks=background_tasks
    )

    logger.info(f"Accepted job {job_id} for user {current_user.user_id} with {len(file_names)} file(s)")

    msg = f"Document queued for processing. Track progress via GET /api/jobs/{job_id}"
    if failed_files:
        msg += f" Note: {len(failed_files)} file(s) skipped."

    return JobResponse(
        job_id=job_id,
        status=JobStatus.QUEUED,
        created_at=time.time(),
        file_names=file_names,
        message=msg
    )


@app.get("/api/jobs/{job_id}", response_model=JobDetailResponse)
async def get_job_status(
    job_id: str,
    current_user: UserContext = Depends(get_current_user)
):
    """Check the status of a background processing job."""
    tracker = get_job_tracker()
    job = tracker.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    # Check job ownership
    if job.get("owner_id") != current_user.user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied: You do not have permission to view this job.")

    session_id = job.get("session_id")
    if session_id and session_id not in sessions:
        try:
            await _get_session(session_id, current_user)
        except Exception as e:
            logger.debug(f"Session {session_id} not available yet for job {job_id}: {e}")

    prog = job.get("progress", {})
    progress_obj = JobProgress(
        current_page=prog.get("current_page", 0),
        total_pages=prog.get("total_pages", 0),
        percent=prog.get("percent", 0.0),
        stage=prog.get("stage", ""),
        scanned_pages=prog.get("scanned_pages", 0),
        chunks_created=prog.get("chunks_created", 0),
    )

    return JobDetailResponse(
        job_id=job["job_id"],
        status=job.get("status", JobStatus.QUEUED),
        owner_id=job.get("owner_id", "unknown"),
        created_at=job.get("created_at", time.time()),
        updated_at=job.get("updated_at", time.time()),
        file_names=job.get("file_names", []),
        progress=progress_obj,
        session_id=session_id,
        error=job.get("error"),
        result_summary=job.get("result_summary")
    )


@app.get("/api/jobs", response_model=JobListResponse)
async def list_user_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: UserContext = Depends(get_current_user)
):
    """List asynchronous processing jobs for the authenticated user."""
    tracker = get_job_tracker()
    raw_jobs = tracker.list_jobs(owner_id=current_user.user_id, limit=limit)
    job_responses = []

    for j in raw_jobs:
        prog = j.get("progress", {})
        progress_obj = JobProgress(
            current_page=prog.get("current_page", 0),
            total_pages=prog.get("total_pages", 0),
            percent=prog.get("percent", 0.0),
            stage=prog.get("stage", ""),
            scanned_pages=prog.get("scanned_pages", 0),
            chunks_created=prog.get("chunks_created", 0),
        )
        job_responses.append(JobDetailResponse(
            job_id=j["job_id"],
            status=j.get("status", JobStatus.QUEUED),
            owner_id=j.get("owner_id", "unknown"),
            created_at=j.get("created_at", time.time()),
            updated_at=j.get("updated_at", time.time()),
            file_names=j.get("file_names", []),
            progress=progress_obj,
            session_id=j.get("session_id"),
            error=j.get("error"),
            result_summary=j.get("result_summary")
        ))

    return JobListResponse(jobs=job_responses, total=len(job_responses))


@app.delete("/api/jobs/{job_id}")
async def delete_or_cancel_job(
    job_id: str,
    current_user: UserContext = Depends(get_current_user)
):
    """Cancel or delete a background job and clean up its staging files."""
    tracker = get_job_tracker()
    job = tracker.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    if job.get("owner_id") != current_user.user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Access denied: Cannot delete jobs owned by other users.")

    for p in job.get("file_paths", []):
        try:
            Path(p).unlink(missing_ok=True)
        except Exception as e:
            logger.debug(f"Could not remove staged file {p}: {e}")

    tracker.delete_job(job_id)
    return {"status": "deleted", "job_id": job_id}


@app.post("/api/query", response_model=QueryResponse)
async def answer_query(
    http_request: Request,
    request: QueryRequest,
    current_user: UserContext = Depends(get_current_user)
):
    """Answer a question using uploaded documents."""
    enforce_rate_limit(http_request, "query", max_requests=settings.QUERY_RATE_LIMIT, window_seconds=60)
    session_data = await _get_session(request.session_id, current_user)
    question = request.question.strip()

    _validate_question(question)

    conversation = get_conversation_manager()

    try:
        # Retrieve candidates via PostgreSQL pgvector hybrid search
        q_emb = get_query_embedding(question)
        candidates = []

        if database.is_database_configured():
            if not database.is_database_ready():
                if settings.ENVIRONMENT == "production":
                    logger.error("PostgreSQL connection pool is down during query retrieval in production.")
                    raise HTTPException(
                        status_code=503,
                        detail="Database connection is unavailable. In-memory fallback is disabled in production to prevent worker state divergence."
                    )
                logger.warning("PostgreSQL pool offline; falling back to in-memory cosine similarity for development.")
            else:
                candidates = await database.hybrid_search_postgres(
                    session_id=request.session_id,
                    query=question,
                    query_embedding=q_emb,
                    k=settings.RETRIEVAL_INITIAL_K,
                    dense_weight=settings.DENSE_WEIGHT,
                    bm25_weight=settings.BM25_WEIGHT,
                    active_files=request.active_files or None
                )
        elif settings.ENVIRONMENT == "production":
            raise HTTPException(
                status_code=503,
                detail="PostgreSQL database is required for queries in production mode. Ephemeral fallback is disabled."
            )

        # Fallback for local development / testing when PostgreSQL is not configured
        if not candidates and not database.is_database_configured():
            if "chunks" in session_data and session_data["chunks"]:
                session_chunks = session_data["chunks"]
                session_embs = session_data.get("embeddings")
                if session_embs is not None and len(session_embs) == len(session_chunks):
                    q_norm = np.linalg.norm(q_emb)
                    q_unit = q_emb / (q_norm if q_norm > 0 else 1.0)
                    emb_norms = np.linalg.norm(session_embs, axis=1, keepdims=True)
                    emb_norms[emb_norms == 0] = 1.0
                    normed_embs = session_embs / emb_norms
                    scores = np.dot(normed_embs, q_unit)
                    ranked_indices = np.argsort(scores)[::-1][:settings.RETRIEVAL_INITIAL_K]
                    for idx in ranked_indices:
                        chunk_copy = dict(session_chunks[idx])
                        chunk_copy["relevance_score"] = float(round(scores[idx], 4))
                        chunk_copy["dense_score"] = float(round(scores[idx], 4))
                        chunk_copy["bm25_score"] = 0.0
                        candidates.append(chunk_copy)
                else:
                    candidates = list(session_chunks[:settings.RETRIEVAL_INITIAL_K])

        if request.active_files is not None:
            candidates = [c for c in candidates if c.get("source_file") in request.active_files]

        if not candidates:
            return QueryResponse(
                answer="I couldn't find any relevant information in the uploaded documents to answer your question.",
                sources=[],
                confidence_score=0.0
            )

        # Re-rank chunks
        relevant_chunks = rerank_chunks(question, candidates, top_k=settings.RETRIEVAL_FINAL_K)

        history = None
        if request.history:
            history = request.history
        else:
            history = conversation.get_history_for_prompt(request.session_id)

        # Generate answer using requested or auto-detected LLM
        llm = FreeLLMService(
            provider=request.provider,
            model=request.model,
            api_key=request.api_key,
            base_url=request.base_url
        )
        answer = llm.generate_answer(question, relevant_chunks, history=history)

        # Check grounding against sources
        grounding = calculate_grounding_score(answer, relevant_chunks)
        confidence_score = grounding["confidence_score"]

        # Extract citations
        citations_data = extract_citations_from_answer(answer, relevant_chunks)
        citations = [CitationInfo(**c) for c in citations_data]

        # Build list of source passages
        sources = []
        seen_pages = set()
        for c in relevant_chunks:
            page_key = (c.get("source_file", "Unknown"), c["page"])
            if page_key not in seen_pages:
                snippet = c["text"][:200] + "..." if len(c["text"]) > 200 else c["text"]
                sources.append(SourceInfo(
                    page=c["page"],
                    snippet=snippet,
                    source_file=c.get("source_file", "Uploaded PDF"),
                    section=c.get("section"),
                    relevance_score=c.get("rerank_score") or c.get("relevance_score"),
                    bm25_score=c.get("bm25_score"),
                    dense_score=c.get("dense_score"),
                    rerank_score=c.get("rerank_score")
                ))
                seen_pages.add(page_key)

        # Calculate evaluation metrics
        triad_dict = calculate_rag_triad_metrics(
            question=question,
            answer=answer,
            source_chunks=relevant_chunks,
            grounding_result=grounding
        )
        rag_triad = RagTriadMetrics(**triad_dict)

        # Save to conversation history
        conversation.add_message(request.session_id, MessageRole.USER, question)
        conversation.add_message(
            request.session_id,
            MessageRole.ASSISTANT,
            answer,
            citations=citations,
            confidence_score=confidence_score
        )

        if database.is_database_configured():
            try:
                await database.save_chat_message(request.session_id, str(uuid.uuid4()), "user", question)
                await database.save_chat_message(
                    request.session_id,
                    str(uuid.uuid4()),
                    "assistant",
                    answer,
                    {"confidence_score": confidence_score, "citations": [c.model_dump() if hasattr(c, 'model_dump') else c.dict() for c in citations]}
                )
            except Exception as e:
                logger.debug(f"Failed to persist chat message to database: {e}")

        # Generate suggested follow-ups
        followups = _generate_followups(question, answer)

        logger.info(
            f"Query answered for session {request.session_id[:8]}: "
            f"{len(sources)} sources, confidence={confidence_score:.2f}"
        )

        claim_verifications = [
            ClaimVerification(**cd) for cd in grounding.get("claim_details", [])
        ] if grounding.get("claim_details") else None

        return QueryResponse(
            answer=answer,
            sources=sources,
            citations=citations,
            confidence_score=confidence_score,
            rag_triad=rag_triad,
            suggested_followups=followups,
            claim_verifications=claim_verifications
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Query error: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="An unexpected error occurred. Please try again.")


@app.post("/api/query/stream")
async def stream_query(
    http_request: Request,
    request: StreamQueryRequest,
    current_user: UserContext = Depends(get_current_user)
):
    """Stream answer tokens as Server-Sent Events."""
    enforce_rate_limit(http_request, "stream_query", max_requests=settings.QUERY_RATE_LIMIT, window_seconds=60)
    session_data = await _get_session(request.session_id, current_user)
    question = request.question.strip()

    _validate_question(question)

    async def event_generator():
        conversation = get_conversation_manager()

        try:
            # Search relevant chunks via PostgreSQL pgvector hybrid search
            q_emb = get_query_embedding(question)
            candidates = []

            if database.is_database_configured():
                if not database.is_database_ready():
                    if settings.ENVIRONMENT == "production":
                        logger.error("PostgreSQL connection pool is down during stream retrieval in production.")
                        yield _sse_event("error", {"detail": "Database connection is unavailable in production."})
                        return
                    logger.warning("PostgreSQL pool offline; falling back to in-memory cosine similarity for development.")
                else:
                    candidates = await database.hybrid_search_postgres(
                        session_id=request.session_id,
                        query=question,
                        query_embedding=q_emb,
                        k=settings.RETRIEVAL_INITIAL_K,
                        dense_weight=settings.DENSE_WEIGHT,
                        bm25_weight=settings.BM25_WEIGHT,
                        active_files=request.active_files or None
                    )
            elif settings.ENVIRONMENT == "production":
                yield _sse_event("error", {"detail": "PostgreSQL database is required in production mode."})
                return

            # Fallback for local development / testing when PostgreSQL is not configured
            if not candidates and not database.is_database_configured():
                if "chunks" in session_data and session_data["chunks"]:
                    session_chunks = session_data["chunks"]
                    session_embs = session_data.get("embeddings")
                    if session_embs is not None and len(session_embs) == len(session_chunks):
                        q_norm = np.linalg.norm(q_emb)
                        q_unit = q_emb / (q_norm if q_norm > 0 else 1.0)
                        emb_norms = np.linalg.norm(session_embs, axis=1, keepdims=True)
                        emb_norms[emb_norms == 0] = 1.0
                        normed_embs = session_embs / emb_norms
                        scores = np.dot(normed_embs, q_unit)
                        ranked_indices = np.argsort(scores)[::-1][:settings.RETRIEVAL_INITIAL_K]
                        for idx in ranked_indices:
                            chunk_copy = dict(session_chunks[idx])
                            chunk_copy["relevance_score"] = float(round(scores[idx], 4))
                            chunk_copy["dense_score"] = float(round(scores[idx], 4))
                            chunk_copy["bm25_score"] = 0.0
                            candidates.append(chunk_copy)
                    else:
                        candidates = list(session_chunks[:settings.RETRIEVAL_INITIAL_K])

            if request.active_files is not None:
                candidates = [c for c in candidates if c.get("source_file") in request.active_files]

            if not candidates:
                yield _sse_event("token", {
                    "text": "I couldn't find any relevant information in the uploaded documents to answer your question."
                })
                yield _sse_event("done", {"total_tokens": 0})
                return

            relevant_chunks = rerank_chunks(question, candidates, top_k=settings.RETRIEVAL_FINAL_K)

            # Send citations
            seen_pages = set()
            citation_id = 1
            for c in relevant_chunks:
                page_key = (c.get("source_file", "Unknown"), c["page"])
                if page_key not in seen_pages:
                    yield _sse_event("citation", {
                        "citation_id": citation_id,
                        "page": c["page"],
                        "text": c["text"][:200],
                        "source_file": c.get("source_file", "Document"),
                        "section": c.get("section"),
                    })
                    citation_id += 1
                    seen_pages.add(page_key)

            # Stream answer
            history = None
            if request.history:
                history = request.history
            else:
                history = conversation.get_history_for_prompt(request.session_id)

            llm = FreeLLMService(
                provider=request.provider,
                model=request.model,
                api_key=request.api_key,
                base_url=request.base_url
            )
            full_answer = ""
            token_count = 0
            start_time = time.time()

            async for token in llm.generate_answer_stream(question, relevant_chunks, history=history):
                full_answer += token
                token_count += 1
                yield _sse_event("token", {"text": token})

            # Check grounding
            grounding = calculate_grounding_score(full_answer, relevant_chunks)
            elapsed_ms = (time.time() - start_time) * 1000

            triad_dict = calculate_rag_triad_metrics(
                question=question,
                answer=full_answer,
                source_chunks=relevant_chunks,
                grounding_result=grounding,
                latency_ms=elapsed_ms
            )

            yield _sse_event("confidence", {
                "score": grounding["confidence_score"],
                "supported_claims": grounding["supported_claims"],
                "total_claims": grounding["total_claims"],
                "verified_claims": grounding.get("verified_claims", grounding["supported_claims"]),
                "inferred_claims": grounding.get("inferred_claims", 0),
                "hallucinated_claims": grounding.get("hallucinated_claims", 0),
            })
            yield _sse_event("verification", {
                "claim_details": grounding.get("claim_details", []),
                "unsupported_claims": grounding.get("unsupported_claims", [])
            })
            yield _sse_event("audit_metrics", triad_dict)

            # Store conversation
            conversation.add_message(request.session_id, MessageRole.USER, question)
            conversation.add_message(
                request.session_id,
                MessageRole.ASSISTANT,
                full_answer,
                confidence_score=grounding["confidence_score"]
            )

            if database.is_database_configured():
                try:
                    await database.save_chat_message(request.session_id, str(uuid.uuid4()), "user", question)
                    await database.save_chat_message(
                        request.session_id,
                        str(uuid.uuid4()),
                        "assistant",
                        full_answer,
                        {"confidence_score": grounding["confidence_score"]}
                    )
                except Exception as e:
                    logger.debug(f"Failed to persist chat message to database: {e}")

            elapsed_ms = (time.time() - start_time) * 1000
            yield _sse_event("done", {
                "total_tokens": token_count,
                "latency_ms": round(elapsed_ms, 1)
            })

        except Exception as e:
            logger.error(f"Streaming error: {e}", exc_info=True)
            yield _sse_event("error", {"message": str(e)})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.post("/api/chat/stream")
async def chat_stream(
    http_request: Request,
    request: StreamQueryRequest,
    current_user: UserContext = Depends(get_current_user)
):
    """Alias for /api/query/stream."""
    return await stream_query(http_request=http_request, request=request, current_user=current_user)


@app.get("/api/documents/{session_id}/pdf")
async def get_document_pdf(
    session_id: str,
    file_index: int = Query(0, ge=0),
    document_name: Optional[str] = None,
    current_user: UserContext = Depends(get_current_user)
):
    """Serve the uploaded PDF for the viewer."""
    session_data = await _get_session(session_id, current_user)
    file_paths = session_data.get("file_paths", [])
    file_names = session_data.get("file_names", [])

    if document_name:
        try:
            file_index = file_names.index(document_name)
        except ValueError:
            raise HTTPException(status_code=404, detail="Document file not found in session")

    if not file_paths or file_index < 0 or file_index >= len(file_paths):
        raise HTTPException(status_code=404, detail="Document file not found")

    file_path = Path(file_paths[file_index]).resolve()
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    if not file_path.is_relative_to(upload_root) or not file_path.exists():
        raise HTTPException(status_code=404, detail="Document file not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=file_names[file_index] if file_index < len(file_names) else "document.pdf",
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "Accept-Ranges": "bytes",
        }
    )


@app.get("/api/documents/{session_id}/insights")
async def get_document_insights(
    session_id: str,
    document_name: Optional[str] = None,
    current_user: UserContext = Depends(get_current_user)
):
    """Get document summary, questions, and entities."""
    session_data = await _get_session(session_id, current_user)
    insights_dict = session_data.get("insights", {})

    if not isinstance(insights_dict, dict):
        insights_dict = {}

    # Default to first document if no document name specified
    if not document_name:
        file_names = session_data.get("file_names", [])
        if file_names:
            document_name = file_names[0]

    if not document_name:
        raise HTTPException(status_code=400, detail="No active document in session")

    # If already generated, return it
    if document_name in insights_dict:
        insights = insights_dict[document_name]
        return insights.model_dump() if hasattr(insights, 'model_dump') else insights.dict()

    # Generate on-demand if not available
    try:
        chunks = [c for c in session_data.get("chunks", []) if c.get("source_file") == document_name]
        llm = FreeLLMService(provider=settings.LLM_PROVIDER)
        matching_meta = next((m for m in session_data.get("metadata", []) if m.get("filename") == document_name), {})
        total_pages = matching_meta.get("num_pages", 0)

        insights = generate_document_insights(
            session_id=session_id,
            chunks=chunks,
            llm_service=llm,
            total_pages=total_pages
        )
        insights_dict[document_name] = insights
        session_data["insights"] = insights_dict
        return insights.model_dump() if hasattr(insights, 'model_dump') else insights.dict()
    except Exception as e:
        logger.error(f"Insights generation failed for {document_name}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate insights for {document_name}")


@app.post("/api/audit/contradictions", response_model=AuditDiffReport)
async def audit_contradictions(
    http_request: Request,
    req: CrossDocAuditRequest,
    current_user: UserContext = Depends(get_current_user)
):
    """Compare two documents to find differences and conflicting clauses."""
    enforce_rate_limit(http_request, "audit", max_requests=getattr(settings, "AUDIT_RATE_LIMIT", 30), window_seconds=60)
    # Demo session handler
    if req.session_id == "demo-session":
        return AuditDiffReport(
            doc_a_name=req.doc_a or "SaaS_Agreement_2024_v1.pdf",
            doc_b_name=req.doc_b or "SaaS_Agreement_2025_Amended.pdf",
            alignment_score=0.68,
            summary="Identified 3 discrepancies: Payment terms changed, liability cap reduced, and SLA uptime changed.",
            critical_count=2,
            warning_count=1,
            conflicts=[
                {
                    "id": "diff-1",
                    "topic": "Payment Terms & Late Penalties",
                    "severity": "critical",
                    "conflict_type": "contradiction",
                    "explanation": "Doc A requires payment within 30 days. Doc B extends payment to 60 days.",
                    "risk_analysis": "Increases payment delay.",
                    "doc_a": {
                        "filename": req.doc_a or "SaaS_Agreement_2024_v1.pdf",
                        "page": 1,
                        "snippet": "Invoices are payable within 30 days of receipt.",
                        "section": "4.1 Payment Terms"
                    },
                    "doc_b": {
                        "filename": req.doc_b or "SaaS_Agreement_2025_Amended.pdf",
                        "page": 1,
                        "snippet": "Customer shall remit payment within 60 calendar days from invoice date.",
                        "section": "4.1 Settlement"
                    }
                },
                {
                    "id": "diff-2",
                    "topic": "Limitation of Liability Cap",
                    "severity": "critical",
                    "conflict_type": "numeric_mismatch",
                    "explanation": "Liability cap changed from $1,000,000 to $250,000.",
                    "risk_analysis": "Reduces liability coverage.",
                    "doc_a": {
                        "filename": req.doc_a or "SaaS_Agreement_2024_v1.pdf",
                        "page": 2,
                        "snippet": "The total aggregate liability of either party shall not exceed $1,000,000.",
                        "section": "8. Liability Limitation"
                    },
                    "doc_b": {
                        "filename": req.doc_b or "SaaS_Agreement_2025_Amended.pdf",
                        "page": 2,
                        "snippet": "Maximum cumulative liability arising out of this agreement is capped at $250,000.",
                        "section": "8. Damages Cap"
                    }
                },
                {
                    "id": "diff-3",
                    "topic": "Service Level Agreement (SLA) & Uptime",
                    "severity": "warning",
                    "conflict_type": "modification",
                    "explanation": "Uptime threshold decreased from 99.95% to 99.5%.",
                    "risk_analysis": "Decreases uptime guarantee.",
                    "doc_a": {
                        "filename": req.doc_a or "SaaS_Agreement_2024_v1.pdf",
                        "page": 3,
                        "snippet": "Provider guarantees monthly service availability of at least 99.95%.",
                        "section": "Schedule B: SLA"
                    },
                    "doc_b": {
                        "filename": req.doc_b or "SaaS_Agreement_2025_Amended.pdf",
                        "page": 3,
                        "snippet": "Service availability commitment is target 99.5%.",
                        "section": "Schedule B: Availability"
                    }
                }
            ]
        )

    session_data = await _get_session(req.session_id, current_user)
    chunks = session_data.get("chunks", [])

    doc_a_chunks = [c for c in chunks if c.get("source_file") == req.doc_a]
    doc_b_chunks = [c for c in chunks if c.get("source_file") == req.doc_b]

    # Match by order if names don't match directly
    if not doc_a_chunks or not doc_b_chunks:
        file_names = session_data.get("file_names", [])
        if len(file_names) >= 2:
            if not doc_a_chunks:
                doc_a_chunks = [c for c in chunks if c.get("source_file") == file_names[0]]
            if not doc_b_chunks:
                doc_b_chunks = [c for c in chunks if c.get("source_file") == file_names[1]]

    if not doc_a_chunks or not doc_b_chunks:
        raise HTTPException(
            status_code=400,
            detail=f"Both documents ('{req.doc_a}' and '{req.doc_b}') must have indexed chunks in session {req.session_id}"
        )

    try:
        llm = FreeLLMService(provider=settings.LLM_PROVIDER)
    except Exception as e:
        logger.warning(f"Could not initialize LLM for audit: {e}")
        llm = None

    report = run_cross_document_audit(
        doc_a_chunks=doc_a_chunks,
        doc_b_chunks=doc_b_chunks,
        doc_a_name=req.doc_a,
        doc_b_name=req.doc_b,
        llm_service=llm
    )

    return report


@app.get("/api/sessions/{session_id}/history")
async def get_conversation_history(
    session_id: str,
    current_user: UserContext = Depends(get_current_user)
):
    """Get conversation history for a session."""
    await _get_session(session_id, current_user)
    conversation = get_conversation_manager()
    messages = conversation.get_history(session_id)

    if not messages and database.is_database_configured():
        try:
            db_msgs = await database.get_chat_history(session_id)
            if db_msgs:
                return {
                    "session_id": session_id,
                    "messages": [
                        {
                            "id": m["id"],
                            "role": m["role"],
                            "content": m["content"],
                            "citations": m.get("metadata", {}).get("citations", []),
                            "confidence_score": m.get("metadata", {}).get("confidence_score"),
                            "timestamp": datetime.fromtimestamp(m["created_at"]).isoformat()
                        }
                        for m in db_msgs
                    ]
                }
        except Exception as e:
            logger.debug(f"Error loading chat history from database: {e}")

    return {
        "session_id": session_id,
        "messages": [
            {
                "id": msg.id,
                "role": msg.role.value,
                "content": msg.content,
                "citations": [c.model_dump() if hasattr(c, 'model_dump') else c.dict() for c in (msg.citations or [])],
                "confidence_score": msg.confidence_score,
                "timestamp": msg.timestamp.isoformat()
            }
            for msg in messages
        ]
    }


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check returning model, database, and service status."""
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


@app.get("/api/llm/providers")
async def list_llm_providers():
    """Return available LLM providers, active selection, and configuration status."""
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


@app.get("/api/sessions/{session_id}")
async def get_session_info(
    session_id: str,
    current_user: UserContext = Depends(get_current_user)
):
    """Get session metadata and document list."""
    session_data = await _get_session(session_id, current_user)
    return {
        "session_id": session_id,
        "file_names": session_data.get("file_names", []),
        "chunk_count": len(session_data.get("chunks", [])),
        "metadata": session_data.get("metadata", []),
        "created_at": session_data.get("created_at"),
        "has_insights": session_data.get("insights") is not None,
    }


@app.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: UserContext = Depends(get_current_user)
):
    """Delete a session, its files, and conversation history."""
    session_data = await _get_session(session_id, current_user)
    deleted_files = 0

    # Delete uploaded files
    for path_str in session_data.get("file_paths", []):
        if _safe_delete_file(path_str):
            deleted_files += 1

    # Delete session directory on disk
    session_dir = Path(settings.UPLOAD_DIR) / "sessions" / session_id
    _safe_delete_file(session_dir)

    # Clear conversation history
    conversation = get_conversation_manager()
    conversation.clear_history(session_id)

    # Remove from memory
    with _sessions_lock:
        sessions.pop(session_id, None)

    # Delete from PostgreSQL if configured
    if database.is_database_configured():
        try:
            await database.delete_session(session_id)
        except Exception as e:
            logger.error(f"Error deleting session {session_id} from database: {e}")

    logger.info(f"User {current_user.user_id} deleted session {session_id}")
    return {
        "status": "success",
        "session_id": session_id,
        "deleted_files_count": deleted_files,
        "message": "Session permanently deleted."
    }


@app.delete("/api/sessions/{session_id}/documents/{document_name}")
async def delete_document_from_session(
    session_id: str,
    document_name: str,
    current_user: UserContext = Depends(get_current_user)
):
    """Delete a single document from an active session and update the index."""
    session_data = await _get_session(session_id, current_user)
    file_names = session_data.get("file_names", [])
    file_paths = session_data.get("file_paths", [])

    if document_name not in file_names:
        raise HTTPException(status_code=404, detail=f"Document '{document_name}' not found in session.")

    idx = file_names.index(document_name)
    target_path = file_paths[idx] if idx < len(file_paths) else None
    if target_path:
        _safe_delete_file(target_path)

    file_names.pop(idx)
    if idx < len(file_paths):
        file_paths.pop(idx)

    old_chunks = session_data.get("chunks", [])
    remaining_chunks = [c for c in old_chunks if c.get("source_file") != document_name]
    session_data["chunks"] = remaining_chunks
    session_data["file_names"] = file_names
    session_data["file_paths"] = file_paths
    session_data.get("insights", {}).pop(document_name, None)

    # Filter in-memory embeddings if present
    if "embeddings" in session_data and session_data["embeddings"] is not None:
        kept_indices = [i for i, c in enumerate(old_chunks) if c.get("source_file") != document_name]
        if kept_indices:
            session_data["embeddings"] = session_data["embeddings"][kept_indices]
        else:
            session_data["embeddings"] = None

    session_dir = Path(settings.UPLOAD_DIR) / "sessions" / session_id
    if session_dir.exists():
        raw_insights = session_data.get("insights", {})
        serializable_insights = {
            k: (v.model_dump() if hasattr(v, "model_dump") else (v.dict() if hasattr(v, "dict") else v))
            for k, v in raw_insights.items()
        }
        session_meta = {
            "session_id": session_id,
            "file_paths": file_paths,
            "file_names": file_names,
            "metadata": session_data.get("metadata", []),
            "insights": serializable_insights,
            "owner_id": current_user.user_id,
        }
        with open(session_dir / "session.json", "w", encoding="utf-8") as f:
            json.dump(session_meta, f, indent=2, default=str)

    # Delete chunks for this document from PostgreSQL if configured
    if database.is_database_configured():
        try:
            await database.delete_document_from_session(session_id, document_name)
            await database.save_session(
                session_id=session_id,
                owner_id=current_user.user_id,
                file_names=file_names,
                file_paths=file_paths,
                metadata=session_data.get("metadata", []),
                insights=session_data.get("insights", {}),
            )
        except Exception as e:
            logger.error(f"Error updating PostgreSQL after document deletion: {e}")

    return {
        "status": "success",
        "session_id": session_id,
        "removed_document": document_name,
        "remaining_documents": file_names,
        "remaining_chunks": len(remaining_chunks)
    }


@app.post("/api/admin/cleanup")
async def trigger_retention_cleanup(
    max_age_hours: Optional[int] = None,
    admin_user: UserContext = Depends(require_admin_or_maintenance)
):
    """Clean up expired sessions and orphaned files."""
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


# Static frontend files for production
try:
    frontend_path = Path(__file__).parent.parent / "frontend" / "out"
    if frontend_path.exists():
        app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
except Exception as e:
    logger.warning(f"Frontend static files not mounted: {e}")


@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"message": f"Welcome to {settings.APP_NAME} API v{settings.APP_VERSION}. Visit /docs for API documentation."}


def _safe_delete_file(file_path: Union[str, Path]) -> bool:
    """Safely delete a file ensuring it is within the upload directory."""
    try:
        target = Path(file_path).resolve()
        base = Path(settings.UPLOAD_DIR).resolve()
        if base not in target.parents and target != base:
            logger.warning(f"Security Alert: Prevented deletion outside upload directory: {target}")
            return False

        if target.is_file() or target.is_symlink():
            target.unlink(missing_ok=True)
            return True
        elif target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            return True
    except Exception as e:
        logger.warning(f"Error during safe deletion of {file_path}: {e}")
    return False


async def _get_session(session_id: str, current_user: UserContext) -> Dict:
    """Retrieve session from memory, disk, or PostgreSQL, checking user ownership."""
    session_data = None
    with _sessions_lock:
        if session_id in sessions:
            session_data = sessions[session_id]

    if not session_data:
        try:
            session_dir = Path(settings.UPLOAD_DIR) / "sessions" / session_id
            session_meta_file = session_dir / "session.json"
            if session_dir.exists() and session_meta_file.exists():
                with open(session_meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)

                restored_session = {
                    "chunks": [],
                    "file_paths": meta.get("file_paths", []),
                    "file_names": meta.get("file_names", []),
                    "metadata": meta.get("metadata", []),
                    "insights": meta.get("insights", {}),
                    "created_at": meta.get("created_at", time.time()),
                    "owner_id": meta.get("owner_id"),
                }
                with _sessions_lock:
                    sessions[session_id] = restored_session
                session_data = restored_session
                logger.info(f"Loaded session {session_id} from disk")
        except Exception as e:
            logger.error(f"Error loading session {session_id} from disk: {e}")

    # Fallback to PostgreSQL if configured
    if not session_data and database.is_database_configured():
        try:
            db_session = await database.get_session(session_id)
            if db_session:
                chunks = await database.get_chunks_for_session(session_id, include_embeddings=True)
                embeddings = None
                if chunks and all("embedding" in c and c["embedding"] is not None for c in chunks):
                    embeddings = np.array([c.pop("embedding") for c in chunks], dtype=np.float32)

                restored_session = {
                    "chunks": chunks,
                    "embeddings": embeddings,
                    "file_paths": db_session.get("file_paths", []),
                    "file_names": db_session.get("file_names", []),
                    "metadata": db_session.get("metadata", []),
                    "insights": db_session.get("insights", {}),
                    "created_at": db_session.get("created_at", time.time()),
                    "owner_id": db_session.get("owner_id"),
                }
                with _sessions_lock:
                    sessions[session_id] = restored_session
                session_data = restored_session
                logger.info(f"Loaded session {session_id} from PostgreSQL")
        except Exception as e:
            logger.error(f"Error loading session {session_id} from PostgreSQL: {e}")

    if not session_data:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired. Please upload documents again."
        )

    owner_id = session_data.get("owner_id")
    if not owner_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied: Session ownership is missing or unverified."
        )

    if owner_id != current_user.user_id and current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Access denied: You do not have permission to access this session."
        )

    return session_data


def _validate_question(question: str):
    """Validate question input."""
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if len(question) > 1000:
        raise HTTPException(status_code=400, detail="Question is too long (max 1000 characters).")


def _cleanup_session(session_id: str):
    """Delete session data, files, and conversation history."""
    session_data = None
    with _sessions_lock:
        if session_id in sessions:
            session_data = sessions.pop(session_id, None)

    if session_data:
        for path in session_data.get("file_paths", []):
            _safe_delete_file(path)
        _safe_delete_file(Path(settings.UPLOAD_DIR) / "sessions" / session_id)
        get_conversation_manager().clear_history(session_id)
        logger.info(f"Cleaned up session {session_id[:8]}")


def cleanup_expired_sessions(max_age_hours: Optional[int] = None) -> Dict[str, int]:
    """Delete expired sessions and files older than retention limit."""
    ttl_hours = max_age_hours if max_age_hours is not None else (settings.RETENTION_HOURS or 24)
    cutoff_time = time.time() - (ttl_hours * 3600)
    purged_sessions = 0
    purged_files = 0

    # Purge expired in-memory sessions
    with _sessions_lock:
        expired_session_ids = [
            sid for sid, data in list(sessions.items())
            if data.get("created_at", 0) < cutoff_time
        ]
        for sid in expired_session_ids:
            session_data = sessions.pop(sid, None)
            if session_data:
                for path in session_data.get("file_paths", []):
                    if _safe_delete_file(path):
                        purged_files += 1
                _safe_delete_file(Path(settings.UPLOAD_DIR) / "sessions" / sid)
                get_conversation_manager().clear_history(sid)
                purged_sessions += 1

    # Purge expired sessions on disk
    sessions_root = Path(settings.UPLOAD_DIR) / "sessions"
    if sessions_root.exists():
        for session_folder in list(sessions_root.iterdir()):
            if session_folder.is_dir():
                meta_file = session_folder / "session.json"
                mtime = session_folder.stat().st_mtime
                file_paths_to_delete = []
                if meta_file.exists():
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                            mtime = meta.get("created_at", mtime)
                            file_paths_to_delete = meta.get("file_paths", [])
                    except Exception as e:
                        logger.debug(f"Failed to read session metadata {meta_file}: {e}")
                if mtime < cutoff_time:
                    for fp in file_paths_to_delete:
                        if _safe_delete_file(fp):
                            purged_files += 1
                    _safe_delete_file(session_folder)
                    get_conversation_manager().clear_history(session_folder.name)
                    sessions.pop(session_folder.name, None)
                    purged_sessions += 1

    # Purge orphaned uploaded files
    upload_root = Path(settings.UPLOAD_DIR)
    if upload_root.exists():
        for f in list(upload_root.iterdir()):
            if f.is_file() and f.suffix.lower() in settings.ALLOWED_EXTENSIONS:
                if f.stat().st_mtime < cutoff_time:
                    if _safe_delete_file(f):
                        purged_files += 1

    # Purge expired job files
    jobs_root = Path(settings.UPLOAD_DIR) / "jobs"
    if jobs_root.exists():
        for jf in list(jobs_root.glob("*.json")):
            if jf.stat().st_mtime < cutoff_time:
                _safe_delete_file(jf)

    logger.info(f"Retention cleanup: {purged_sessions} sessions, {purged_files} files removed.")
    return {"purged_sessions": purged_sessions, "purged_files": purged_files}


def _generate_followups(question: str, answer: str) -> List[str]:
    """Generate simple follow-up question suggestions."""
    followups = []

    if "summary" not in question.lower():
        followups.append("Can you summarize the key points?")
    if "detail" not in question.lower() and "explain" not in question.lower():
        followups.append("Can you provide more details on this topic?")
    if "compare" not in question.lower():
        followups.append("Are there any contrasting views or data?")
    if "risk" not in question.lower():
        followups.append("What are the potential risks or limitations?")

    return followups[:3]


def _sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"