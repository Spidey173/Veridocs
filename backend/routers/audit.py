"""
Cross-Document Contradiction and Comparative Audit Endpoints.
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Request, Depends

from config import get_settings
from auth import get_current_user, UserContext
from models import CrossDocAuditRequest
from contradiction_engine import AuditDiffReport, run_cross_document_audit
from llm_service import FreeLLMService
from rate_limiter import enforce_rate_limit
from session_store import _get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.post("/contradictions", response_model=AuditDiffReport)
async def audit_contradictions(
    http_request: Request,
    req: CrossDocAuditRequest,
    current_user: UserContext = Depends(get_current_user)
):
    """Compare two documents to identify conflicting clauses, altered terms, and numerical discrepancies."""
    settings = get_settings()
    enforce_rate_limit(http_request, "audit", max_requests=getattr(settings, "AUDIT_RATE_LIMIT", 30), window_seconds=60)

    # Demo session handler for immediate preview
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
