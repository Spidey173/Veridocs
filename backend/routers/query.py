"""
Query and streaming QA endpoints for Veridocs.
Retrieves top document chunks, streams token-by-token answers from OpenAI/Groq/Ollama,
rewrites follow-up questions, detects small talk, emits real citations, and performs citation check.
"""

import re
import json
import logging
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from config import get_settings
from models import QueryRequest, StreamQueryRequest, QueryResponse, SourceInfo, CitationInfo, CitationCheckResult
from vector_store import VectorStore
from llm_service import get_llm_service, LLMService
from verification import extract_citations_from_answer, check_citations
from session_store import validate_question
from rate_limiter import check_rate_limit
import database

logger = logging.getLogger(__name__)
router = APIRouter(tags=["query"])

SMALL_TALK_RESPONSES = {
    "hi": "Hello! How can I help you analyze your document today?",
    "hello": "Hello! How can I help you analyze your document today?",
    "hey": "Hey there! Ask me any question about your uploaded document.",
    "ok thanks": "You're welcome! Let me know if you need anything else from the document.",
    "ok thank you": "You're welcome! Let me know if you need anything else from the document.",
    "thanks": "You're welcome! Happy to help.",
    "thank you": "You're welcome! Happy to help.",
    "cool thanks": "Glad to help! Let me know if you have more questions.",
    "great thanks": "You're welcome! Let me know if you need any more details.",
    "bye": "Goodbye! Feel free to return whenever you need document verification.",
    "goodbye": "Goodbye! Have a great day.",
}


def detect_small_talk(question: str) -> Optional[str]:
    """Check if question is conversational small talk that doesn't need document retrieval."""
    clean = re.sub(r'[^\w\s]', '', question.strip().lower())
    clean = " ".join(clean.split())
    if clean in SMALL_TALK_RESPONSES:
        return SMALL_TALK_RESPONSES[clean]
    if re.match(r'^(?:ok\s+)?(?:thanks|thank\s+you|thx)(?:\s+(?:very\s+much|a\s+lot|so\s+much))?$', clean):
        return "You're welcome! Let me know if you need anything else from the document."
    if re.match(r'^(?:hi|hello|hey|greetings)(?:\s+there)?$', clean):
        return "Hello! How can I help you analyze your document today?"
    return None


def rewrite_query_for_retrieval(
    question: str,
    history: Optional[List[Dict[str, str]]],
    llm: LLMService
) -> str:
    """Rewrite follow-up questions referencing previous turns into a standalone retrieval query."""
    if not history or len(history) == 0:
        return question

    PRONOUN_OR_FOLLOWUP_RE = re.compile(
        r'\b(it|its|they|their|them|he|him|his|she|her|this|that|these|those|first\s+one|second\s+one|last\s+one|former|latter)\b|^(what\s+about|how\s+about|tell\s+me\s+more|elaborate|explain\s+more|why\?|when\?|where\?|which\s+one\?)\b',
        re.IGNORECASE
    )

    clean_q = question.strip()
    if not PRONOUN_OR_FOLLOWUP_RE.search(clean_q) and len(clean_q.split()) >= 6:
        return question

    if not llm.is_configured() or not llm.client:
        return question

    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a search query rewriter for document retrieval. "
                    "Given the conversation history, rewrite the user's latest follow-up question "
                    "into a single self-contained document search query that preserves specific entity names and keywords. "
                    "Do NOT answer the question. Output ONLY the rewritten search query in 1 short line with no extra text."
                ),
            }
        ]
        for h in history[-4:]:
            role = h.get("role", "user")
            if role in ("user", "assistant"):
                messages.append({"role": role, "content": h.get("content", "")})
        messages.append({"role": "user", "content": clean_q})

        extra_body = {}
        if "groq.com" in llm.base_url and "gpt-oss" in llm.model:
            extra_body["reasoning_format"] = "hidden"

        res = llm.client.chat.completions.create(
            model=llm.model,
            messages=messages,
            temperature=0.0,
            max_tokens=40,
            extra_body=extra_body if extra_body else None,
        )
        rewritten = res.choices[0].message.content.strip()
        rewritten = re.sub(r'^(Rewritten\s*Query|Standalone\s*Query|Query):\s*', '', rewritten, flags=re.IGNORECASE).strip('"\n ')
        if rewritten and len(rewritten) > 3:
            logger.info(f"[Query Rewrite] Original: '{question}' -> Standalone: '{rewritten}'")
            return rewritten
    except Exception as e:
        logger.warning(f"Query rewrite fallback to original: {e}")

    return question


def _sse_event(event_type: str, data: Dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"


@router.post("/api/query", response_model=QueryResponse)
async def query_documents(request: Request, body: QueryRequest):
    """Answer a question based on uploaded documents using vector search and LLM."""
    validate_question(body.question)
    session = database.get_session(body.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found. Please upload documents first.")

    # 1. Check for conversational small talk: bypass retrieval and citation check
    small_talk_reply = detect_small_talk(body.question)
    if small_talk_reply:
        return QueryResponse(
            answer=small_talk_reply,
            sources=[],
            citations=[],
            citation_check=None,
        )

    # Abuse protection: Rate limit per IP unless custom key is provided
    client_ip = request.client.host if request.client else "127.0.0.1"
    x_api_key = request.headers.get("X-LLM-API-Key") or request.headers.get("X-OpenAI-Key")
    x_base_url = request.headers.get("X-LLM-Base-Url")
    x_model = request.headers.get("X-LLM-Model")

    limit_err = check_rate_limit(client_ip, action="query", has_custom_key=bool(x_api_key))
    if limit_err:
        raise HTTPException(status_code=429, detail=limit_err)

    llm = get_llm_service(base_url=x_base_url, api_key=x_api_key, model=x_model)

    # 2. Rewrite follow-ups into standalone retrieval query if needed
    search_query = rewrite_query_for_retrieval(body.question, body.history, llm)

    # 3. Retrieve top chunks
    chunks = VectorStore.search(
        session_id=body.session_id,
        query=search_query,
        active_files=body.active_files,
    )

    if not chunks:
        return QueryResponse(
            answer="Not found in the document.",
            sources=[],
            citations=[],
            citation_check=None,
        )

    # 4. Generate answer
    try:
        answer = llm.generate_answer(body.question, chunks, history=body.history)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"LLM query failed: {e}")
        raise HTTPException(status_code=500, detail=f"LLM request error: {str(e)}")

    # 5. Extract citations and check grounding
    is_system_notice = (
        not llm.is_configured()
        or answer.strip().startswith("⚠️")
        or "No LLM is configured" in answer
        or "not found in the document" in answer.lower()
    )
    citations = extract_citations_from_answer(answer, chunks) if not is_system_notice else []
    check_result = check_citations(answer, chunks) if not is_system_notice else None

    sources = [
        SourceInfo(
            page=c["page"],
            snippet=c["text"][:300],
            source_file=c.get("source_file", "Document"),
            relevance_score=c.get("relevance_score"),
        )
        for c in chunks
    ]

    return QueryResponse(
        answer=answer,
        sources=sources,
        citations=[CitationInfo(**c) for c in citations],
        citation_check=CitationCheckResult(**check_result) if check_result else None,
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

        # 1. Handle small talk directly: skip retrieval and citation check
        small_talk_reply = detect_small_talk(body.question)
        if small_talk_reply:
            yield _sse_event("token", {"text": small_talk_reply})
            yield _sse_event("done", {})
            return

        try:
            llm = get_llm_service(base_url=x_base_url, api_key=x_api_key, model=x_model)

            # 2. Rewrite follow-ups into standalone query for retrieval
            search_query = rewrite_query_for_retrieval(body.question, body.history, llm)

            # 3. Retrieve top chunks
            chunks = VectorStore.search(
                session_id=body.session_id,
                query=search_query,
                active_files=body.active_files,
            )

            if not chunks:
                yield _sse_event("token", {
                    "text": "Not found in the document."
                })
                yield _sse_event("done", {})
                return

            # 4. Stream LLM tokens
            full_answer = ""
            async for token in llm.generate_answer_stream(body.question, chunks, history=body.history):
                full_answer += token
                yield _sse_event("token", {"text": token})

            # 5. Extract citations and check grounding ONLY on real answers
            is_system_notice = (
                not llm.is_configured()
                or full_answer.strip().startswith("⚠️")
                or "No LLM is configured" in full_answer
                or "Rate Limit Reached" in full_answer
                or "not found in the document" in full_answer.lower()
            )

            if full_answer and not is_system_notice:
                citations = extract_citations_from_answer(full_answer, chunks)
                for c in citations:
                    yield _sse_event("citation", c)

                check_result = check_citations(full_answer, chunks)
                if check_result.get("total_claims", 0) > 0:
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
