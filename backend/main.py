"""
Veridocs — FastAPI Application
Enterprise-grade document intelligence platform.

Endpoints:
- POST /api/upload          — Upload and process documents
- POST /api/query           — Query documents (JSON response)
- POST /api/query/stream    — Query with SSE streaming
- GET  /api/documents/{id}/pdf       — Serve uploaded PDF
- GET  /api/documents/{id}/insights  — Document insights
- GET  /api/sessions/{id}/history    — Conversation history
- GET  /api/health          — Health check
"""

import os
# Constrain thread pools to 1 thread to avoid OOM crashes on free-tier cloud containers
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
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Dict, Optional, Union, Any

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, BackgroundTasks, Depends, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import get_settings, get_model_registry
from auth import get_current_user, create_access_token, verify_access_token, UserContext
from pdf_processor import (
    extract_text_from_file,
    chunk_text,
)
from vector_store import VectorStore
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
    DocumentInsights,
    RagTriadMetrics,
    CrossDocAuditRequest,
)
from insights_engine import generate_document_insights
from verification import calculate_grounding_score, calculate_rag_triad_metrics, extract_citations_from_answer
from contradiction_engine import run_cross_document_audit, AuditDiffReport

# ──────────────────────────────────────────────
# Setup
# ──────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

async def _retention_cleanup_loop():
    """Background lifecycle task executing periodic retention pruning."""
    logger.info(
        f"Automated retention worker initialized (interval: {settings.CLEANUP_INTERVAL_MINUTES}m, "
        f"retention: {settings.RETENTION_HOURS}h)"
    )
    while True:
        try:
            await asyncio.sleep(settings.CLEANUP_INTERVAL_MINUTES * 60)
            res = cleanup_expired_sessions(max_age_hours=settings.RETENTION_HOURS)
            if res.get("purged_sessions", 0) > 0 or res.get("purged_files", 0) > 0:
                logger.info(
                    f"Automated retention cleanup cycle: {res['purged_sessions']} sessions, "
                    f"{res['purged_files']} files purged."
                )
        except asyncio.CancelledError:
            logger.info("Automated retention worker received shutdown signal.")
            break
        except Exception as e:
            logger.error(f"Error during automated retention cycle: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Enforce strict security validation on production startup
    settings.validate_production_configuration()

    logger.info(
        f"Starting {settings.APP_NAME} v{settings.APP_VERSION} "
        f"[env: {settings.ENVIRONMENT}, auth_mode: {settings.AUTH_MODE}]"
    )

    # 2. Warm up models in RAM so first query is instantaneous
    import threading
    def _warmup():
        reg = get_model_registry()
        _ = reg.embedding_model
        if settings.RERANKER_ENABLED:
            _ = reg.reranker_model
    threading.Thread(target=_warmup, daemon=True).start()

    # 3. Launch automatic retention cleanup background task
    cleanup_task = None
    if settings.AUTO_CLEANUP_ENABLED:
        cleanup_task = asyncio.create_task(_retention_cleanup_loop())

    yield

    # Graceful shutdown
    if cleanup_task:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise AI Document Intelligence Platform",
    lifespan=lifespan
)

# CORS: Configured whitelist from environment
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
)

# Ensure upload directory exists
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────
# Authentication Models & Endpoints
# ──────────────────────────────────────────────

class DemoTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    expires_in: int
    mode: str = "demo"
    warning: str

@app.post("/api/auth/demo-token", response_model=DemoTokenResponse)
@app.post("/api/auth/token", response_model=DemoTokenResponse)
async def generate_demo_token(x_api_key: Optional[str] = Header(None)):
    """
    Issue an ephemeral, single-user demo access token for local development.
    Client-chosen identities and roles are rejected. In production/gateway mode,
    this endpoint is disabled to ensure identity must be asserted via trusted gateways.
    """
    if settings.ENVIRONMENT == "production" or settings.AUTH_MODE == "gateway":
        raise HTTPException(
            status_code=403,
            detail="Demo token issuance is disabled in production/gateway mode. "
                   "Authentication must be provided by your trusted upstream identity provider or API gateway."
        )

    if settings.REQUIRE_API_KEY:
        if not x_api_key or x_api_key != settings.API_KEY:
            raise HTTPException(status_code=401, detail="Invalid API key")

    # Generate a random, server-assigned demo user ID (clients cannot pick their own ID or role)
    demo_uid = f"demo_usr_{secrets.token_hex(6)}"
    token = create_access_token(user_id=demo_uid, role="user")
    user_ctx = verify_access_token(token)

    return DemoTokenResponse(
        access_token=token,
        token_type="bearer",
        user_id=user_ctx.user_id,
        expires_in=int(settings.TOKEN_EXPIRE_HOURS * 3600),
        mode="demo",
        warning="Local demo token only. For multi-tenant production, configure AUTH_MODE=gateway with a trusted identity provider."
    )

# ──────────────────────────────────────────────
# In-Memory Session Storage
# ──────────────────────────────────────────────

sessions: Dict[str, Dict] = {}
# Each session: {
#   "vector_store": VectorStore,
#   "chunks": List[Dict],
#   "file_paths": List[str],
#   "file_names": List[str],
#   "metadata": List[Dict],
#   "insights": Optional[DocumentInsights],
#   "created_at": float,
#   "owner_id": str,
# }


def _generate_insights_background(session_id: str, chunks_by_file: Dict, doc_metadata: List[Dict], provider: str):
    """Generate insights asynchronously in the background so upload returns in sub-second time."""
    try:
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

            logger.info(f"Background generating insights for {fn} ({len(file_chunks)} chunks)...")
            doc_insights = generate_document_insights(
                session_id=session_id,
                chunks=file_chunks,
                llm_service=llm,
                total_pages=pages_count
            )
            insights_dict[fn] = doc_insights

        session_data["insights"] = insights_dict
        logger.info(f"Background insights complete for session {session_id}")
    except Exception as e:
        logger.error(f"Background insights generation failed: {e}", exc_info=True)


# ──────────────────────────────────────────────
# Upload Endpoint
# ──────────────────────────────────────────────

@app.post("/api/upload", response_model=UploadResponse)
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Form(None),
    current_user: UserContext = Depends(get_current_user)
):
    """
    Upload and process documents (PDF, DOCX, TXT).
    Returns session_id and processing results.
    """
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
            contents = await file.read()

            # Validate file size
            if len(contents) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
                failed_files.append(f"{filename} (exceeds {settings.MAX_FILE_SIZE_MB}MB limit)")
                continue

            logger.info(f"Processing upload for user {current_user.user_id}: {filename} ({len(contents)} bytes)")

            # Save file to disk for PDF viewer
            session_file_id = str(uuid.uuid4())
            save_path = Path(settings.UPLOAD_DIR) / f"{session_file_id}{ext}"
            save_path.write_bytes(contents)
            saved_paths.append(str(save_path))
            file_names.append(filename)

            # Extract text (single pass)
            pages = extract_text_from_file(contents, filename)

            if not pages:
                failed_files.append(f"{filename} (no extractable text)")
                continue

            metadata = {
                "filename": filename,
                "file_size_bytes": len(contents),
                "num_pages": len(pages),
                "is_encrypted": False,
                "metadata": {}
            }

            # Chunk the text with table detection and document breadcrumbs
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

                logger.info(f"Processed {filename}: {len(chunks)} chunks")
            else:
                failed_files.append(f"{filename} (chunking failed)")

        except ValueError as e:
            failed_files.append(f"{filename}: {str(e)}")
            logger.warning(f"ValueError processing {filename}: {str(e)}")
        except Exception as e:
            failed_files.append(f"{filename}: Unexpected error")
            logger.error(f"Error processing {filename}: {str(e)}", exc_info=True)

    if not all_chunks:
        error_msg = "No files could be processed. "
        if failed_files:
            error_msg += f"Issues: {'; '.join(failed_files[:3])}"
        raise HTTPException(status_code=400, detail=error_msg)

    try:
        # If we have an existing session, verify ownership before merging
        existing_insights = {}
        if session_id:
            existing_session = _get_session(session_id, current_user)
            saved_paths = existing_session.get("file_paths", []) + saved_paths
            file_names = existing_session.get("file_names", []) + file_names
            doc_metadata = existing_session.get("metadata", []) + doc_metadata
            all_chunks = existing_session.get("chunks", []) + all_chunks
            existing_insights = existing_session.get("insights", {})

        # Create vector store and index with all combined chunks
        vector_store = VectorStore()
        vector_store.add_documents(all_chunks)

        # Generate session ID if not existing
        if not session_id or session_id not in sessions:
            session_id = str(uuid.uuid4())

        # Group chunks by filename
        from collections import defaultdict
        chunks_by_file = defaultdict(list)
        for chunk in all_chunks:
            fn = chunk.get("source_file", "unknown")
            chunks_by_file[fn].append(chunk)

        # Store session immediately so client gets sub-second response
        sessions[session_id] = {
            "vector_store": vector_store,
            "chunks": all_chunks,
            "file_paths": saved_paths,
            "file_names": file_names,
            "metadata": doc_metadata,
            "insights": existing_insights,
            "created_at": time.time(),
            "owner_id": current_user.user_id,
        }

        # Persist session to disk so documents survive Render server restarts
        try:
            session_dir = Path(settings.UPLOAD_DIR) / "sessions" / session_id
            vector_store.save_to_disk(session_dir)
            session_meta = {
                "session_id": session_id,
                "file_paths": saved_paths,
                "file_names": file_names,
                "metadata": doc_metadata,
                "created_at": time.time(),
                "owner_id": current_user.user_id,
            }
            with open(session_dir / "session.json", "w", encoding="utf-8") as f:
                json.dump(session_meta, f)
            logger.info(f"Persisted session {session_id} to disk at {session_dir} for owner {current_user.user_id}")
        except Exception as e:
            logger.warning(f"Could not persist session {session_id} to disk: {e}")

        # Dispatch background insights generation without blocking the upload response
        background_tasks.add_task(
            _generate_insights_background,
            session_id=session_id,
            chunks_by_file=dict(chunks_by_file),
            doc_metadata=doc_metadata,
            provider=settings.LLM_PROVIDER
        )

        # Evict old sessions
        if len(sessions) > settings.MAX_SESSIONS:
            oldest_key = min(sessions, key=lambda k: sessions[k]["created_at"])
            _cleanup_session(oldest_key)

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


# ──────────────────────────────────────────────
# Query Endpoint (JSON response)
# ──────────────────────────────────────────────

@app.post("/api/query", response_model=QueryResponse)
async def answer_query(
    request: QueryRequest,
    current_user: UserContext = Depends(get_current_user)
):
    """Answer a question using uploaded documents. Returns full JSON response."""
    session_data = _get_session(request.session_id, current_user)
    vector_store = session_data["vector_store"]
    question = request.question.strip()

    _validate_question(question)

    conversation = get_conversation_manager()

    try:
        # 1. Retrieve candidates (hybrid search)
        candidates = vector_store.search(question, k=settings.RETRIEVAL_INITIAL_K)

        if request.active_files is not None:
            candidates = [c for c in candidates if c.get("source_file") in request.active_files]

        if not candidates:
            return QueryResponse(
                answer="I couldn't find any relevant information in the uploaded documents to answer your question.",
                sources=[],
                confidence_score=0.0
            )

        # 2. Re-rank
        relevant_chunks = rerank_chunks(question, candidates, top_k=settings.RETRIEVAL_FINAL_K)

        # 3. Get conversation history
        history = None
        if request.history:
            history = request.history
        else:
            history = conversation.get_history_for_prompt(request.session_id)

        # 4. Generate answer
        llm = FreeLLMService(provider=settings.LLM_PROVIDER)
        answer = llm.generate_answer(question, relevant_chunks, history=history)

        # 5. Verify grounding
        grounding = calculate_grounding_score(answer, relevant_chunks)
        confidence_score = grounding["confidence_score"]

        # 6. Extract structured citations
        citations_data = extract_citations_from_answer(answer, relevant_chunks)
        citations = [CitationInfo(**c) for c in citations_data]

        # 7. Build sources with detailed retriever observability
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

        # 8. Compute RAG Triad observability scores
        triad_dict = calculate_rag_triad_metrics(
            question=question,
            answer=answer,
            source_chunks=relevant_chunks,
            grounding_result=grounding
        )
        rag_triad = RagTriadMetrics(**triad_dict)

        # 9. Store in conversation history
        conversation.add_message(request.session_id, MessageRole.USER, question)
        conversation.add_message(
            request.session_id,
            MessageRole.ASSISTANT,
            answer,
            citations=citations,
            confidence_score=confidence_score
        )

        # 10. Generate follow-up suggestions
        followups = _generate_followups(question, answer)

        logger.info(
            f"Query answered for session {request.session_id[:8]}: "
            f"{len(sources)} sources, confidence={confidence_score:.2f}, "
            f"groundedness={rag_triad.groundedness:.2f}, answer_relevance={rag_triad.answer_relevance:.2f}"
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


# ──────────────────────────────────────────────
# Streaming Query Endpoint (SSE)
# ──────────────────────────────────────────────

@app.post("/api/query/stream")
async def stream_query(
    request: StreamQueryRequest,
    current_user: UserContext = Depends(get_current_user)
):
    """
    Stream answer tokens via Server-Sent Events.
    Emits: token, citation, confidence, done events.
    """
    session_data = _get_session(request.session_id, current_user)
    vector_store = session_data["vector_store"]
    question = request.question.strip()

    _validate_question(question)

    async def event_generator():
        conversation = get_conversation_manager()

        try:
            # 1. Retrieve and re-rank
            candidates = vector_store.search(question, k=settings.RETRIEVAL_INITIAL_K)

            if request.active_files is not None:
                candidates = [c for c in candidates if c.get("source_file") in request.active_files]

            if not candidates:
                yield _sse_event("token", {
                    "text": "I couldn't find any relevant information in the uploaded documents to answer your question."
                })
                yield _sse_event("done", {"total_tokens": 0})
                return

            relevant_chunks = rerank_chunks(question, candidates, top_k=settings.RETRIEVAL_FINAL_K)

            # 2. Send citations early
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

            # 3. Stream answer
            history = None
            if request.history:
                history = request.history
            else:
                history = conversation.get_history_for_prompt(request.session_id)

            llm = FreeLLMService(provider=settings.LLM_PROVIDER)
            full_answer = ""
            token_count = 0
            start_time = time.time()

            async for token in llm.generate_answer_stream(question, relevant_chunks, history=history):
                full_answer += token
                token_count += 1
                yield _sse_event("token", {"text": token})

            # 4. Grounding verification with 3-state claim analysis
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

            # 5. Store conversation
            conversation.add_message(request.session_id, MessageRole.USER, question)
            conversation.add_message(
                request.session_id,
                MessageRole.ASSISTANT,
                full_answer,
                confidence_score=grounding["confidence_score"]
            )

            # 6. Done
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
    request: StreamQueryRequest,
    current_user: UserContext = Depends(get_current_user)
):
    """
    Alias endpoint for /api/query/stream for high-speed SSE streaming.
    Provides sub-400ms Time-To-First-Token (TTFT) and citation grounding.
    """
    return await stream_query(request, current_user=current_user)


# ──────────────────────────────────────────────
# Document Serving
# ──────────────────────────────────────────────

@app.get("/api/documents/{session_id}/pdf")
async def get_document_pdf(
    session_id: str,
    file_index: int = 0,
    document_name: Optional[str] = None,
    current_user: UserContext = Depends(get_current_user)
):
    """Serve the uploaded PDF for the viewer."""
    session_data = _get_session(session_id, current_user)
    file_paths = session_data.get("file_paths", [])
    file_names = session_data.get("file_names", [])

    if document_name:
        try:
            file_index = file_names.index(document_name)
        except ValueError:
            raise HTTPException(status_code=404, detail="Document file not found in session")

    if not file_paths or file_index >= len(file_paths):
        raise HTTPException(status_code=404, detail="Document file not found")

    file_path = Path(file_paths[file_index])
    if not file_path.exists():
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


# ──────────────────────────────────────────────
# Insights Endpoint
# ──────────────────────────────────────────────

@app.get("/api/documents/{session_id}/insights")
async def get_document_insights(
    session_id: str,
    document_name: Optional[str] = None,
    current_user: UserContext = Depends(get_current_user)
):
    """Get pre-generated document insights (summary, questions, entities)."""
    session_data = _get_session(session_id, current_user)
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


# ──────────────────────────────────────────────
# Forensic Contradiction Audit Endpoint
# ──────────────────────────────────────────────

@app.post("/api/audit/contradictions", response_model=AuditDiffReport)
async def audit_contradictions(
    req: CrossDocAuditRequest,
    current_user: UserContext = Depends(get_current_user)
):
    """
    Forensic Cross-Document Contradiction & Diff Engine.
    Compares two documents within a session and detects conflicting clauses,
    altered numerical values, and risk discrepancies with exact citations.
    """
    # Demo session handler for instant evaluation
    if req.session_id == "demo-session":
        return AuditDiffReport(
            doc_a_name=req.doc_a or "SaaS_Agreement_2024_v1.pdf",
            doc_b_name=req.doc_b or "SaaS_Agreement_2025_Amended.pdf",
            alignment_score=0.68,
            summary="Forensic cross-document analysis identified 3 critical discrepancies: Payment terms extended from 30 to 60 days, liability cap reduced by 75%, and SLA uptime commitment downgraded.",
            critical_count=2,
            warning_count=1,
            conflicts=[
                {
                    "id": "diff-1",
                    "topic": "Payment Terms & Late Penalties",
                    "severity": "critical",
                    "conflict_type": "contradiction",
                    "explanation": "Doc A requires payment within 30 days with a 1.5% monthly late fee. Doc B extends payment to 60 days and deletes all late penalty clauses.",
                    "risk_analysis": "Increases working capital cycle and removes financial incentive for timely invoice settlement.",
                    "doc_a": {
                        "filename": req.doc_a or "SaaS_Agreement_2024_v1.pdf",
                        "page": 1,
                        "snippet": "Invoices are payable within 30 days of receipt. Overdue balances shall accrue interest at 1.5% per month.",
                        "section": "4.1 Payment Terms"
                    },
                    "doc_b": {
                        "filename": req.doc_b or "SaaS_Agreement_2025_Amended.pdf",
                        "page": 1,
                        "snippet": "Customer shall remit payment within 60 calendar days from invoice date without late fees or interest charges.",
                        "section": "4.1 Settlement"
                    }
                },
                {
                    "id": "diff-2",
                    "topic": "Limitation of Liability Cap",
                    "severity": "critical",
                    "conflict_type": "numeric_mismatch",
                    "explanation": "Aggregate liability cap was slashed from $1,000,000 in Doc A down to $250,000 in Doc B.",
                    "risk_analysis": "Significantly impairs recovery rights in the event of gross negligence, data breaches, or major system failure.",
                    "doc_a": {
                        "filename": req.doc_a or "SaaS_Agreement_2024_v1.pdf",
                        "page": 2,
                        "snippet": "The total aggregate liability of either party shall not exceed $1,000,000 under any circumstances.",
                        "section": "8. Liability Limitation"
                    },
                    "doc_b": {
                        "filename": req.doc_b or "SaaS_Agreement_2025_Amended.pdf",
                        "page": 2,
                        "snippet": "Maximum cumulative liability arising out of this agreement is capped at $250,000 or the fees paid in the prior 3 months.",
                        "section": "8. Damages Cap"
                    }
                },
                {
                    "id": "diff-3",
                    "topic": "Service Level Agreement (SLA) & Uptime",
                    "severity": "warning",
                    "conflict_type": "modification",
                    "explanation": "Guaranteed uptime threshold decreased from 99.95% to 99.5%, allowing an extra 3.6 hours of uncredited downtime per month.",
                    "risk_analysis": "Reduces operational reliability guarantees for production workflows.",
                    "doc_a": {
                        "filename": req.doc_a or "SaaS_Agreement_2024_v1.pdf",
                        "page": 3,
                        "snippet": "Provider guarantees monthly service availability of at least 99.95% excluding scheduled maintenance windows.",
                        "section": "Schedule B: SLA"
                    },
                    "doc_b": {
                        "filename": req.doc_b or "SaaS_Agreement_2025_Amended.pdf",
                        "page": 3,
                        "snippet": "Service availability commitment is target 99.5% with service credits capped at 5% of monthly recurring revenue.",
                        "section": "Schedule B: Availability"
                    }
                }
            ]
        )

    session_data = _get_session(req.session_id, current_user)
    chunks = session_data.get("chunks", [])

    doc_a_chunks = [c for c in chunks if c.get("source_file") == req.doc_a]
    doc_b_chunks = [c for c in chunks if c.get("source_file") == req.doc_b]

    # Fallback to file index if document names don't match exactly
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
        logger.warning(f"Could not initialize LLM for audit: {e}. Will use deterministic engine.")
        llm = None

    report = run_cross_document_audit(
        doc_a_chunks=doc_a_chunks,
        doc_b_chunks=doc_b_chunks,
        doc_a_name=req.doc_a,
        doc_b_name=req.doc_b,
        llm_service=llm
    )

    return report


# ──────────────────────────────────────────────
# Conversation History
# ──────────────────────────────────────────────

@app.get("/api/sessions/{session_id}/history")
async def get_conversation_history(
    session_id: str,
    current_user: UserContext = Depends(get_current_user)
):
    """Get conversation history for a session."""
    _get_session(session_id, current_user)  # Validate session exists
    conversation = get_conversation_manager()
    messages = conversation.get_history(session_id)

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


# ──────────────────────────────────────────────
# Health Check
# ──────────────────────────────────────────────

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check with model and provider status."""
    registry = get_model_registry()
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        active_sessions=len(sessions),
        models_loaded={
            "embedding": registry._embedding_model is not None,
            "reranker": registry._reranker_model is not None,
        },
        providers_available={
            "google": bool(settings.GOOGLE_API_KEY),
            "groq": bool(settings.GROQ_API_KEY),
            "openrouter": bool(settings.OPENROUTER_API_KEY),
            "github": bool(settings.GITHUB_TOKEN),
        }
    )


# ──────────────────────────────────────────────
# Session Info
# ──────────────────────────────────────────────

@app.get("/api/sessions/{session_id}")
async def get_session_info(
    session_id: str,
    current_user: UserContext = Depends(get_current_user)
):
    """Get session metadata."""
    session_data = _get_session(session_id, current_user)
    return {
        "session_id": session_id,
        "file_names": session_data.get("file_names", []),
        "chunk_count": len(session_data.get("chunks", [])),
        "metadata": session_data.get("metadata", []),
        "created_at": session_data.get("created_at"),
        "has_insights": session_data.get("insights") is not None,
    }


# ──────────────────────────────────────────────
# Data Lifecycle & Deletion Endpoints
# ──────────────────────────────────────────────

@app.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: UserContext = Depends(get_current_user)
):
    """
    Securely delete an active session, its uploaded files, persisted vector indices,
    and conversation history with path traversal protection.
    """
    session_data = _get_session(session_id, current_user)
    deleted_files = 0

    # 1. Delete associated uploaded files
    for path_str in session_data.get("file_paths", []):
        if _safe_delete_file(path_str):
            deleted_files += 1

    # 2. Delete persisted session directory on disk
    session_dir = Path(settings.UPLOAD_DIR) / "sessions" / session_id
    _safe_delete_file(session_dir)

    # 3. Clear conversation manager
    conversation = get_conversation_manager()
    conversation.clear_history(session_id)

    # 4. Remove from in-memory sessions
    if session_id in sessions:
        del sessions[session_id]

    logger.info(f"User {current_user.user_id} deleted session {session_id} ({deleted_files} files purged)")
    return {
        "status": "success",
        "session_id": session_id,
        "deleted_files_count": deleted_files,
        "message": "Session, documents, vector indices, and conversation history permanently deleted."
    }


@app.delete("/api/sessions/{session_id}/documents/{document_name}")
async def delete_document_from_session(
    session_id: str,
    document_name: str,
    current_user: UserContext = Depends(get_current_user)
):
    """Delete a single document from an active session and update the index."""
    session_data = _get_session(session_id, current_user)
    file_names = session_data.get("file_names", [])
    file_paths = session_data.get("file_paths", [])

    if document_name not in file_names:
        raise HTTPException(status_code=404, detail=f"Document '{document_name}' not found in session.")

    idx = file_names.index(document_name)
    target_path = file_paths[idx] if idx < len(file_paths) else None
    if target_path:
        _safe_delete_file(target_path)

    # Remove from lists
    file_names.pop(idx)
    if idx < len(file_paths):
        file_paths.pop(idx)

    # Filter chunks
    remaining_chunks = [c for c in session_data.get("chunks", []) if c.get("source_file") != document_name]
    session_data["chunks"] = remaining_chunks
    session_data["file_names"] = file_names
    session_data["file_paths"] = file_paths
    session_data.get("insights", {}).pop(document_name, None)

    # Re-index remaining chunks
    vector_store = VectorStore()
    if remaining_chunks:
        vector_store.add_documents(remaining_chunks)
    session_data["vector_store"] = vector_store

    # Persist updated session to disk
    session_dir = Path(settings.UPLOAD_DIR) / "sessions" / session_id
    if session_dir.exists():
        vector_store.save_to_disk(session_dir)

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
    current_user: UserContext = Depends(get_current_user)
):
    """
    Trigger retention policy cleanup of expired sessions and orphaned files.
    Restricted to administrator role or admin key. Rejects arbitrary or out-of-bound cleanup ages.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Access denied: Administrator privileges required for retention cleanup."
        )

    target_max_age = max_age_hours if max_age_hours is not None else settings.RETENTION_HOURS
    if target_max_age < 1 or target_max_age > 720:
        raise HTTPException(
            status_code=400,
            detail="Invalid max_age_hours: Must be between 1 and 720 hours (up to 30 days)."
        )

    result = cleanup_expired_sessions(max_age_hours=target_max_age)
    return {
        "status": "success",
        "retention_hours": target_max_age,
        **result
    }


# ──────────────────────────────────────────────
# Static Files & Root
# ──────────────────────────────────────────────

# Serve the Next.js frontend build (production)
try:
    frontend_path = Path(__file__).parent.parent / "frontend" / "out"
    if frontend_path.exists():
        app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="frontend")
except Exception as e:
    logger.warning(f"Frontend static files not mounted: {e}")


@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    """Root redirect and health ping."""
    return {"message": f"Welcome to {settings.APP_NAME} API v{settings.APP_VERSION}. Visit /docs for API documentation."}


# ──────────────────────────────────────────────
# Helper Functions & Retention Cleanup
# ──────────────────────────────────────────────

def _safe_delete_file(file_path: Union[str, Path]) -> bool:
    """
    Safely delete a file or directory with path traversal protection.
    Verifies that the target path resolves strictly within settings.UPLOAD_DIR.
    """
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


def _get_session(session_id: str, current_user: UserContext) -> Dict:
    """Get session data from memory or restore from disk, verifying user ownership."""
    session_data = None
    if session_id in sessions:
        session_data = sessions[session_id]
    else:
        # Try restoring session from disk if backend restarted
        try:
            session_dir = Path(settings.UPLOAD_DIR) / "sessions" / session_id
            session_meta_file = session_dir / "session.json"
            if session_dir.exists() and session_meta_file.exists():
                with open(session_meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)

                vector_store = VectorStore.load_from_disk(session_dir)
                if vector_store:
                    restored_session = {
                        "vector_store": vector_store,
                        "chunks": vector_store.chunks,
                        "file_paths": meta.get("file_paths", []),
                        "file_names": meta.get("file_names", []),
                        "metadata": meta.get("metadata", []),
                        "insights": meta.get("insights", {}),
                        "created_at": meta.get("created_at", time.time()),
                        "owner_id": meta.get("owner_id"),
                    }
                    sessions[session_id] = restored_session
                    session_data = restored_session
                    logger.info(f"Successfully restored session {session_id} from disk")
        except Exception as e:
            logger.error(f"Error restoring session {session_id} from disk: {e}")

    if not session_data:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired. Please upload documents again."
        )

    # Ownership enforcement: require explicit ownership on every session
    owner_id = session_data.get("owner_id")
    if not owner_id:
        logger.warning(f"Access denied: Session {session_id} has missing or unknown ownership.")
        raise HTTPException(
            status_code=403,
            detail="Access denied: Session ownership is missing or unverified."
        )

    if owner_id != current_user.user_id and current_user.role != "admin":
        logger.warning(
            f"Access denied: user {current_user.user_id} attempted access to session {session_id} owned by {owner_id}"
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied: You do not have permission to access this session or document."
        )

    return session_data


def _validate_question(question: str):
    """Validate question input."""
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if len(question) > 1000:
        raise HTTPException(status_code=400, detail="Question is too long (max 1000 characters).")


def _cleanup_session(session_id: str):
    """Clean up session data including saved files, vector indices, and history."""
    if session_id in sessions:
        session_data = sessions[session_id]
        for path in session_data.get("file_paths", []):
            _safe_delete_file(path)
        _safe_delete_file(Path(settings.UPLOAD_DIR) / "sessions" / session_id)
        get_conversation_manager().clear_history(session_id)
        del sessions[session_id]
        logger.info(f"Cleaned up session {session_id[:8]}")


def cleanup_expired_sessions(max_age_hours: Optional[int] = None) -> Dict[str, int]:
    """
    Purge expired sessions, persisted vector indices, and orphaned files older than RETENTION_HOURS.
    Protects against disk exhaustion and enforces strict privacy data retention.
    Safe against missing files and partial writes.
    """
    ttl_hours = max_age_hours if max_age_hours is not None else (settings.RETENTION_HOURS or 24)
    cutoff_time = time.time() - (ttl_hours * 3600)
    purged_sessions = 0
    purged_files = 0

    # 1. Purge expired in-memory sessions
    expired_session_ids = [
        sid for sid, data in list(sessions.items())
        if data.get("created_at", 0) < cutoff_time
    ]
    for sid in expired_session_ids:
        session_data = sessions.get(sid, {})
        for p in session_data.get("file_paths", []):
            if _safe_delete_file(p):
                purged_files += 1
        _safe_delete_file(Path(settings.UPLOAD_DIR) / "sessions" / sid)
        get_conversation_manager().clear_history(sid)
        sessions.pop(sid, None)
        purged_sessions += 1

    # 2. Purge expired persisted sessions on disk
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
                    except Exception:
                        pass
                if mtime < cutoff_time:
                    for fp in file_paths_to_delete:
                        if _safe_delete_file(fp):
                            purged_files += 1
                    _safe_delete_file(session_folder)
                    get_conversation_manager().clear_history(session_folder.name)
                    sessions.pop(session_folder.name, None)
                    purged_sessions += 1

    # 3. Purge orphaned uploaded files older than cutoff
    upload_root = Path(settings.UPLOAD_DIR)
    if upload_root.exists():
        for f in list(upload_root.iterdir()):
            if f.is_file() and f.suffix.lower() in settings.ALLOWED_EXTENSIONS:
                if f.stat().st_mtime < cutoff_time:
                    if _safe_delete_file(f):
                        purged_files += 1

    logger.info(f"Retention cleanup completed: {purged_sessions} sessions, {purged_files} files purged.")
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