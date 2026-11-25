"""
Analytics and Cross-Document Search endpoints for Veridocs.
- GET /analytics: counts of documents uploaded/analyzed, questions asked, flags found,
  avg verification score, and daily breakdown.
- POST /search: cross-document library search (or session-scoped search) returning
  ranked chunks grouped by document with section + page.
"""

from datetime import datetime, timezone
from collections import defaultdict
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException

import database
from models_db import Document, Flag, QueryLog
from models import (
    AnalyticsResponse,
    DailyAnalyticsBucket,
    CrossDocSearchRequest,
    CrossDocSearchResponse,
    SearchDocumentGroup,
    SearchChunkMatch,
)
from vector_store import VectorStore

router = APIRouter(tags=["analytics_and_search"])


def _ts_to_day(ts: Optional[float]) -> str:
    if not ts:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%d")


@router.get("/analytics", response_model=AnalyticsResponse)
@router.get("/api/analytics", response_model=AnalyticsResponse)
async def get_analytics():
    """Return workspace-wide document, QA verification, and anomaly flag metrics by day."""
    with database.get_db() as db:
        docs = db.query(Document.status, Document.created_at).all()
        flags = db.query(Flag.created_at).all()
        queries = db.query(QueryLog.citation_score, QueryLog.created_at).all()

    docs_uploaded = len(docs)
    docs_analyzed = sum(1 for d in docs if d.status == "ready")
    questions_asked = len(queries)
    flags_found = len(flags)

    scores = [float(q.citation_score) for q in queries if q.citation_score is not None]
    avg_score = round(sum(scores) / len(scores), 3) if scores else 0.0

    day_buckets: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "documents_uploaded": 0,
            "documents_analyzed": 0,
            "questions_asked": 0,
            "flags_found": 0,
            "scores": [],
        }
    )

    for d in docs:
        day = _ts_to_day(d.created_at)
        day_buckets[day]["documents_uploaded"] += 1
        if d.status == "ready":
            day_buckets[day]["documents_analyzed"] += 1

    for q in queries:
        day = _ts_to_day(q.created_at)
        day_buckets[day]["questions_asked"] += 1
        if q.citation_score is not None:
            day_buckets[day]["scores"].append(float(q.citation_score))

    for fl in flags:
        day = _ts_to_day(fl.created_at)
        day_buckets[day]["flags_found"] += 1

    by_day: List[DailyAnalyticsBucket] = []
    for day in sorted(day_buckets.keys()):
        b = day_buckets[day]
        day_scores = b["scores"]
        day_avg = round(sum(day_scores) / len(day_scores), 3) if day_scores else None
        by_day.append(
            DailyAnalyticsBucket(
                date=day,
                documents_uploaded=b["documents_uploaded"],
                documents_analyzed=b["documents_analyzed"],
                questions_asked=b["questions_asked"],
                flags_found=b["flags_found"],
                avg_verification_score=day_avg,
            )
        )

    return AnalyticsResponse(
        documents_uploaded=docs_uploaded,
        documents_analyzed=docs_analyzed,
        questions_asked=questions_asked,
        flags_found=flags_found,
        avg_verification_score=avg_score,
        by_day=by_day,
    )


@router.post("/search", response_model=CrossDocSearchResponse)
@router.post("/api/search", response_model=CrossDocSearchResponse)
async def cross_document_search(body: CrossDocSearchRequest):
    """
    Cross-document hybrid search across the entire document library (when scope='library'
    or session_id is omitted) or scoped to a single session. Returns ranked chunks
    grouped by document with section_path and page number.
    """
    q = (body.query or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Search query cannot be empty.")

    effective_scope = "library" if (not body.session_id or body.scope == "library") else "session"
    target_session = None if effective_scope == "library" else body.session_id

    raw_hits = VectorStore.search(
        session_id=target_session,
        query=q,
        top_k=body.top_k,
    )

    # Resolve Document records for clean original filenames and document_id lookup
    doc_lookup: Dict[tuple, str] = {}
    doc_name_by_id: Dict[str, str] = {}
    with database.get_db() as db:
        for d in db.query(Document).all():
            doc_lookup[(d.session_id, d.filename)] = d.id
            doc_name_by_id[d.id] = d.filename

    groups_map: Dict[str, Dict[str, Any]] = {}
    for hit in raw_hits:
        raw_fname = hit.get("source_file") or hit.get("filename") or "Document"
        sid = hit.get("session_id")
        doc_id = hit.get("document_id") or doc_lookup.get((sid, raw_fname))
        fname = doc_name_by_id.get(doc_id, raw_fname) if doc_id else raw_fname
        group_key = doc_id or f"{sid or 'global'}::{fname}"
        score = float(hit.get("relevance_score") or hit.get("rrf_score") or 0.0)

        if group_key not in groups_map:
            groups_map[group_key] = {
                "document_id": doc_id,
                "filename": fname,
                "session_id": sid,
                "max_score": score,
                "matches": [],
            }
        else:
            groups_map[group_key]["max_score"] = max(groups_map[group_key]["max_score"], score)

        groups_map[group_key]["matches"].append(
            SearchChunkMatch(
                chunk_id=hit.get("id"),
                content=(hit.get("text") or hit.get("content") or "")[:400],
                page=int(hit.get("page") or hit.get("page_number") or 1),
                section_path=hit.get("section_path") or (hit.get("metadata") or {}).get("section_path"),
                chunk_type=hit.get("chunk_type") or "text",
                score=round(score, 4),
            )
        )

    sorted_groups = sorted(groups_map.values(), key=lambda g: g["max_score"], reverse=True)
    return CrossDocSearchResponse(
        query=q,
        scope=effective_scope,
        total_matches=len(raw_hits),
        documents=[SearchDocumentGroup(**g) for g in sorted_groups],
    )
