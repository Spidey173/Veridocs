"""
Query and streaming QA endpoints for Veridocs.
Retrieves top document chunks, streams token-by-token answers from OpenAI/Ollama,
emits real page citations, and performs citation check.
"""

import json
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from config import get_settings
from models import QueryRequest, StreamQueryRequest, QueryResponse, SourceInfo, CitationInfo, CitationCheckResult
from vector_store import VectorStore
from llm_service import get_llm_service
from verification import extract_citations_from_answer, check_citations
from session_store import validate_question
from rate_limiter import check_rate_limit
import database

logger = logging.getLogger(__name__)
router = APIRouter(tags=["query"])


def _sse_event(event_type: str, data: Dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


@router.post("/api/query", response_model=QueryResponse)
async def query_documents(request: Request, body: QueryRequest):
    """Answer a question based on uploaded documents using vector search and LLM."""
    validate_question(body.question)
    session = database.get_session(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Please upload documents first.")

    # Abuse protection: Rate limit per IP unless custom key is provided
    client_ip = request.client.host if request.client else "127.0.0.1"
    x_api_key = request.headers.get("X-LLM-API-Key") or request.headers.get("X-OpenAI-Key")
    x_base_url = request.headers.get("X-LLM-Base-Url")
    x_model = request.headers.get("X-LLM-Model")

    limit_err = check_rate_limit(client_ip, action="query", has_custom_key=bool(x_api_key))
    if limit_err:
        raise HTTPException(status_code=429, detail=limit_err)

    # 1. Retrieve top chunks
    chunks = VectorStore.search(
        session_id=body.session_id,
        query=body.question,
        active_files=body.active_files,
    )

    if not chunks:
        return QueryResponse(
            answer="No relevant content found in the uploaded documents to answer your question.",
            sources=[],
            citations=[],
        )

    # 2. Generate answer
    llm = get_llm_service(base_url=x_base_url, api_key=x_api_key, model=x_model)
    try:
        answer = llm.generate_answer(body.question, chunks, history=body.history)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"LLM query failed: {e}")
        raise HTTPException(status_code=500, detail=f"LLM request error: {str(e)}")

    # 3. Extract citations and check grounding
    citations = extract_citations_from_answer(answer, chunks)
    check_result = check_citations(answer, chunks)

    sources = [
        SourceInfo(
            page=c["page"],
            snippet=c["text"][:250],
            source_file=c.get("source_file", "Document"),
            relevance_score=c.get("relevance_score"),
        )
        for c in chunks
    ]

    return QueryResponse(
        answer=answer,
        sources=sources,
        citations=[CitationInfo(**c) for c in citations],
        citation_check=CitationCheckResult(**check_result),
    )


@router.post("/api/query/stream")
async def stream_query_endpoint(request: Request, body: StreamQueryRequest):
    """Stream answer tokens via Server-Sent Events with citations and citation check."""
    validate_question(body.question)
    session = database.get_session(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Please upload documents first.")

    # Abuse protection: Rate limit per IP unless custom key is provided
    client_ip = request.client.host if request.client else "127.0.0.1"
    x_api_key = request.headers.get("X-LLM-API-Key") or request.headers.get("X-OpenAI-Key")
    x_base_url = request.headers.get("X-LLM-Base-Url")
    x_model = request.headers.get("X-LLM-Model")

    limit_err = check_rate_limit(client_ip, action="query", has_custom_key=bool(x_api_key))

    async def event_generator():
        if limit_err:
            yield _sse_event("token", {
                "text": f"⚠️ **Rate Limit Reached**: {limit_err}"
            })
            yield _sse_event("done", {})
            return

        try:
            chunks = VectorStore.search(
                session_id=body.session_id,
                query=body.question,
                active_files=body.active_files,
            )

            if not chunks:
                yield _sse_event("token", {
                    "text": "I could not find any relevant information in the uploaded documents to answer your question."
                })
                yield _sse_event("done", {})
                return

            # Send top citations to client upfront
            citations = extract_citations_from_answer(body.question, chunks)
            for c in citations:
                yield _sse_event("citation", c)

            # Stream LLM tokens (using custom user key if supplied, or server key)
            llm = get_llm_service(base_url=x_base_url, api_key=x_api_key, model=x_model)
            full_answer = ""
            async for token in llm.generate_answer_stream(body.question, chunks, history=body.history):
                full_answer += token
                yield _sse_event("token", {"text": token})

            # Check citations against retrieved context
            if full_answer:
                check_result = check_citations(full_answer, chunks)
                yield _sse_event("citation_check", check_result)

            yield _sse_event("done", {})

        except Exception as e:
            logger.error(f"Error during query stream: {e}", exc_info=True)
            yield _sse_event("error", {"message": str(e)})
            yield _sse_event("done", {})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )
