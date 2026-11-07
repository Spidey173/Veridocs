"""
Question Answering, RAG Triad Telemetry, and Server-Sent Events (SSE) Streaming Endpoints.
"""

import json
import time
import uuid
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any
import numpy as np
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse

from config import get_settings
from auth import get_current_user, UserContext
from models import (
    QueryRequest,
    QueryResponse,
    StreamQueryRequest,
    SourceInfo,
    CitationInfo,
    RagTriadMetrics,
    ClaimVerification,
    MessageRole,
)
from vector_store import get_query_embedding
from reranker import rerank_chunks
from llm_service import FreeLLMService
from verification import (
    calculate_grounding_score,
    extract_citations_from_answer,
    calculate_rag_triad_metrics,
)
from conversation import get_conversation_manager
import database
from rate_limiter import enforce_rate_limit
from session_store import _get_session, _validate_question

logger = logging.getLogger(__name__)

router = APIRouter(tags=["query"])


def _generate_followups(question: str, answer: str) -> List[str]:
    """Generate intelligent follow-up question suggestions."""
    followups = []
    q_lower = question.lower()
    if "summary" not in q_lower:
        followups.append("Can you summarize the key points?")
    if "detail" not in q_lower and "explain" not in q_lower:
        followups.append("Can you provide more details on this topic?")
    if "compare" not in q_lower:
        followups.append("Are there any contrasting views or data?")
    if "risk" not in q_lower:
        followups.append("What are the potential risks or limitations?")
    return followups[:3]


def _sse_event(event_type: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


@router.post("/api/query", response_model=QueryResponse)
async def answer_query(
    http_request: Request,
    request: QueryRequest,
    current_user: UserContext = Depends(get_current_user)
):
    """Answer a user query with hybrid retrieval, cross-encoder reranking, and RAG Triad evaluation."""
    settings = get_settings()
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

        # Re-rank chunks using cross-encoder
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


@router.post("/api/query/stream")
async def stream_query(
    http_request: Request,
    request: StreamQueryRequest,
    current_user: UserContext = Depends(get_current_user)
):
    """Stream answer tokens as Server-Sent Events with continuous grounding verification."""
    settings = get_settings()
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


@router.post("/api/chat/stream")
async def chat_stream(
    http_request: Request,
    request: StreamQueryRequest,
    current_user: UserContext = Depends(get_current_user)
):
    """Alias endpoint for /api/query/stream."""
    return await stream_query(http_request=http_request, request=request, current_user=current_user)


@router.get("/api/sessions/{session_id}/history")
async def get_conversation_history(
    session_id: str,
    current_user: UserContext = Depends(get_current_user)
):
    """Get persistent conversation history for a session."""
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

