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
import logging
import uuid
import asyncio
from pathlib import Path
from typing import List, Dict, Optional

from fastapi import FastAPI, UploadFile, File, HTTPException, Request, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from config import get_settings, get_model_registry
from pdf_processor import (
    extract_text_from_file,
    get_document_metadata,
    chunk_text,
    get_pdf_metadata,
    extract_text_from_pdf,
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
)
from insights_engine import generate_document_insights, extract_entities
from verification import calculate_grounding_score, extract_citations_from_answer

# ──────────────────────────────────────────────
# Setup
# ──────────────────────────────────────────────

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise AI Document Intelligence Platform"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure upload directory exists
Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

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
# }


# ──────────────────────────────────────────────
# Startup Events
# ──────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    """Startup event logic."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    # Warm up embedding model in background thread so it's loaded in RAM and instant for uploads
    import threading
    threading.Thread(target=lambda: get_model_registry().embedding_model, daemon=True).start()


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
    session_id: Optional[str] = Form(None)
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

            logger.info(f"Processing upload: {filename} ({len(contents)} bytes)")

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
        # If we have an existing session, merge files, paths, metadata, and chunks
        if session_id and session_id in sessions:
            existing_session = sessions[session_id]
            saved_paths = existing_session.get("file_paths", []) + saved_paths
            file_names = existing_session.get("file_names", []) + file_names
            doc_metadata = existing_session.get("metadata", []) + doc_metadata
            all_chunks = existing_session.get("chunks", []) + all_chunks

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

        # Existing insights if appending to session
        existing_insights = {}
        if session_id and session_id in sessions:
            existing_insights = sessions[session_id].get("insights", {})

        # Store session immediately so client gets sub-second response
        sessions[session_id] = {
            "vector_store": vector_store,
            "chunks": all_chunks,
            "file_paths": saved_paths,
            "file_names": file_names,
            "metadata": doc_metadata,
            "insights": existing_insights,
            "created_at": time.time(),
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
            }
            with open(session_dir / "session.json", "w", encoding="utf-8") as f:
                json.dump(session_meta, f)
            logger.info(f"Persisted session {session_id} to disk at {session_dir}")
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
async def answer_query(request: QueryRequest):
    """Answer a question using uploaded documents. Returns full JSON response."""
    session_data = _get_session(request.session_id)
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

        # 7. Build sources
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
                    relevance_score=c.get("rerank_score") or c.get("relevance_score")
                ))
                seen_pages.add(page_key)

        # 8. Store in conversation history
        conversation.add_message(request.session_id, MessageRole.USER, question)
        conversation.add_message(
            request.session_id,
            MessageRole.ASSISTANT,
            answer,
            citations=citations,
            confidence_score=confidence_score
        )

        # 9. Generate follow-up suggestions
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
async def stream_query(request: StreamQueryRequest):
    """
    Stream answer tokens via Server-Sent Events.
    Emits: token, citation, confidence, done events.
    """
    session_data = _get_session(request.session_id)
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
                # Small delay for smooth rendering
                await asyncio.sleep(0.01)

            # 4. Grounding verification with 3-state claim analysis
            grounding = calculate_grounding_score(full_answer, relevant_chunks)
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
async def chat_stream(request: StreamQueryRequest):
    """
    Alias endpoint for /api/query/stream for high-speed SSE streaming.
    Provides sub-400ms Time-To-First-Token (TTFT) and citation grounding.
    """
    return await stream_query(request)


# ──────────────────────────────────────────────
# Document Serving
# ──────────────────────────────────────────────

@app.get("/api/documents/{session_id}/pdf")
async def get_document_pdf(
    session_id: str,
    file_index: int = 0,
    document_name: Optional[str] = None
):
    """Serve the uploaded PDF for the viewer."""
    session_data = _get_session(session_id)
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
async def get_document_insights(session_id: str, document_name: Optional[str] = None):
    """Get pre-generated document insights (summary, questions, entities)."""
    session_data = _get_session(session_id)
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
# Conversation History
# ──────────────────────────────────────────────

@app.get("/api/sessions/{session_id}/history")
async def get_conversation_history(session_id: str):
    """Get conversation history for a session."""
    _get_session(session_id)  # Validate session exists
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
async def get_session_info(session_id: str):
    """Get session metadata."""
    session_data = _get_session(session_id)
    return {
        "session_id": session_id,
        "file_names": session_data.get("file_names", []),
        "chunk_count": len(session_data.get("chunks", [])),
        "metadata": session_data.get("metadata", []),
        "created_at": session_data.get("created_at"),
        "has_insights": session_data.get("insights") is not None,
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
# Helper Functions
# ──────────────────────────────────────────────

def _get_session(session_id: str) -> Dict:
    """Get session data from memory or restore from disk."""
    if session_id in sessions:
        return sessions[session_id]

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
                }
                sessions[session_id] = restored_session
                logger.info(f"Successfully restored session {session_id} from disk")
                return restored_session
    except Exception as e:
        logger.error(f"Error restoring session {session_id} from disk: {e}")

    raise HTTPException(
        status_code=404,
        detail="Session not found or expired. Please upload documents again."
    )


def _validate_question(question: str):
    """Validate question input."""
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if len(question) > 1000:
        raise HTTPException(status_code=400, detail="Question is too long (max 1000 characters).")


def _cleanup_session(session_id: str):
    """Clean up session data including saved files."""
    if session_id in sessions:
        session_data = sessions[session_id]
        # Delete saved files
        for path in session_data.get("file_paths", []):
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass
        del sessions[session_id]
        logger.info(f"Cleaned up session {session_id[:8]}")


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