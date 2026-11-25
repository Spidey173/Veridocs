"""
Contract Comparison Service for Veridocs.
Orchestrates pairwise document comparison:
- Clause segmentation and embedding persistence
- Hungarian alignment and word-level diffs
- LLM structured change summaries with risk ratings and page citations
- Quote verification on summary claims
- Markdown export generation
"""

import time
import logging
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from models_db import Document, Clause, Comparison
from comparison.clause_segmenter import ClauseSegmenter
from comparison.aligner import ClauseAligner
from extraction.extractor import verify_quote_in_page_text

logger = logging.getLogger(__name__)

VALID_CHANGE_TYPES = {"financial", "liability", "term", "termination", "confidentiality", "governing_law", "other"}

VALID_RISK_LEVELS = {"low", "medium", "high"}


def summarize_clause_change_llm(
    clause_a: Optional[Dict[str, Any]], clause_b: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Invokes LLM to analyze the contractual impact and risk of a clause modification.
    Returns: {change_type, summary, risk: low|medium|high, risk_reason, verified_quote: bool}
    """
    text_a = (clause_a.get("text", "") if clause_a else "").strip()
    text_b = (clause_b.get("text", "") if clause_b else "").strip()

    # Rule-based fallback if LLM is unavailable or offline
    def fallback_analysis() -> Dict[str, Any]:
        combined = (text_a + " " + text_b).lower()
        change_type = "other"
        risk = "low"
        risk_reason = "Standard contractual variation or wording clarification."

        if any(w in combined for w in ["$", "fee", "payment", "subtotal", "cost", "price", "rate"]):
            change_type = "financial"
            risk = "high"
            risk_reason = "Payment terms, fees, or monetary thresholds were altered."
        elif any(w in combined for w in ["liability", "indemnif", "damage", "cap", "remedy"]):
            change_type = "liability"
            risk = "high"
            risk_reason = "Liability caps or indemnification obligations were modified."
        elif any(w in combined for w in ["terminate", "termination", "cure period", "convenience"]):
            change_type = "termination"
            risk = "medium"
            risk_reason = "Termination provisions or notice periods were modified."
        elif any(w in combined for w in ["confidential", "trade secret", "disclosure", "nda"]):
            change_type = "confidentiality"
            risk = "medium"
            risk_reason = "Confidentiality terms or duration were altered."
        elif any(w in combined for w in ["term", "month", "year", "renewal", "expire"]):
            change_type = "term"
            risk = "medium"
            risk_reason = "Contract duration or renewal mechanism was changed."
        elif any(w in combined for w in ["law", "jurisdiction", "court", "venue", "arbitrat"]):
            change_type = "governing_law"
            risk = "low"
            risk_reason = "Governing jurisdiction or dispute venue was altered."

        summary = f"Clause updated from '{text_a[:60]}...' to '{text_b[:60]}...'."
        return {
            "change_type": change_type,
            "summary": summary,
            "risk": risk,
            "risk_reason": risk_reason,
            "evidence_quote": text_b[:40] if text_b else text_a[:40],
            "quote_verified": True,
        }

    try:
        from llm_service import call_llm_json

        prompt = (
            "You are a senior commercial contract counsel comparing two versions of a contractual clause.\n"
            f"VERSION A (Page {clause_a.get('page_start', 1) if clause_a else 'N/A'}):\n{text_a}\n\n"
            f"VERSION B (Page {clause_b.get('page_start', 1) if clause_b else 'N/A'}):\n{text_b}\n\n"
            "Analyze the legal and business impact of the modification. Return a strict JSON object with:\n"
            "- change_type: one of 'financial', 'liability', 'term', 'termination', 'confidentiality', 'governing_law', 'other'\n"
            "- summary: concise 1-2 sentence explanation of what changed and its practical implication\n"
            "- risk: one of 'low', 'medium', 'high'\n"
            "- risk_reason: clear reasoning justifying why this change presents low, medium, or high risk\n"
            "- evidence_quote: a short exact quote (5-15 words) from Version A or B demonstrating the change\n"
        )

        res = call_llm_json(prompt)
        if isinstance(res, dict) and "summary" in res:
            c_type = res.get("change_type", "other").lower()
            if c_type not in VALID_CHANGE_TYPES:
                c_type = "other"
            risk = res.get("risk", "low").lower()
            if risk not in VALID_RISK_LEVELS:
                risk = "low"

            quote = res.get("evidence_quote", "")
            # Quote verification against source clauses
            quote_verified = False
            if quote:
                quote_verified = verify_quote_in_page_text(quote, text_a) or verify_quote_in_page_text(quote, text_b)

            return {
                "change_type": c_type,
                "summary": res.get("summary", ""),
                "risk": risk,
                "risk_reason": res.get("risk_reason", ""),
                "evidence_quote": quote,
                "quote_verified": quote_verified,
            }
    except Exception as e:
        logger.warning(f"LLM clause summary failed: {e}; falling back to heuristic risk rules.")

    return fallback_analysis()


class ComparisonService:
    """Manages pairwise contract comparisons and clause persistence."""

    def __init__(self, db: Session):
        self.db = db
        self.segmenter = ClauseSegmenter()
        self.aligner = ClauseAligner()

    def get_or_segment_clauses(self, document: Document) -> List[Dict[str, Any]]:
        """Retrieves existing clauses for document, or segments and persists them."""
        existing = self.db.query(Clause).filter(Clause.document_id == document.id).order_by(Clause.clause_index).all()
        if existing:
            return [c.to_dict() for c in existing]

        # Segment from pages
        pages = document.pages
        if not pages:
            return []

        clauses_data = self.segmenter.segment_pages(pages, document_id=document.id)
        for c in clauses_data:
            db_clause = Clause(
                document_id=document.id,
                clause_index=c["clause_index"],
                number=c.get("number"),
                heading=c.get("heading"),
                text=c["text"],
                page_start=c["page_start"],
                page_end=c["page_end"],
                embedding=c.get("embedding"),
            )
            self.db.add(db_clause)

        self.db.commit()
        return clauses_data

    def run_comparison(self, doc_a_id: str, doc_b_id: str, comparison_id: Optional[str] = None) -> Comparison:
        """Executes full contract comparison pipeline between doc_a and doc_b."""
        doc_a = self.db.query(Document).filter(Document.id == doc_a_id).first()
        doc_b = self.db.query(Document).filter(Document.id == doc_b_id).first()

        if not doc_a or not doc_b:
            raise ValueError(f"Documents not found: doc_a={doc_a_id}, doc_b={doc_b_id}")

        # Fetch or create comparison record
        comp = None
        if comparison_id:
            comp = self.db.query(Comparison).filter(Comparison.id == comparison_id).first()

        if not comp:
            comp = Comparison(doc_a=doc_a_id, doc_b=doc_b_id, status="processing", created_at=time.time())
            self.db.add(comp)
            self.db.commit()
            self.db.refresh(comp)

        try:
            # 1. Segment & embed clauses
            clauses_a = self.get_or_segment_clauses(doc_a)
            clauses_b = self.get_or_segment_clauses(doc_b)

            # 2. Align & Diff
            aligned = self.aligner.align_and_diff(clauses_a, clauses_b)

            # 3. Analyze modified, added, removed clauses
            risk_counts = {"high": 0, "medium": 0, "low": 0}
            status_counts = {"unchanged": 0, "modified": 0, "added": 0, "removed": 0, "moved": 0}

            enriched_aligned = []
            for item in aligned:
                status = item["status"]
                status_counts[status] = status_counts.get(status, 0) + 1
                ca = item.get("clause_a")
                cb = item.get("clause_b")

                analysis = None
                if status in ("modified", "moved", "added", "removed"):
                    analysis = summarize_clause_change_llm(ca, cb)
                    r = analysis.get("risk", "low")
                    risk_counts[r] = risk_counts.get(r, 0) + 1

                enriched_aligned.append(
                    {
                        "status": status,
                        "clause_a": ca,
                        "clause_b": cb,
                        "similarity": item.get("similarity", 0.0),
                        "diff_tokens": item.get("diff_tokens", []),
                        "page_a": ca.get("page_start") if ca else None,
                        "page_b": cb.get("page_start") if cb else None,
                        "analysis": analysis,
                    }
                )

            report_json = {
                "comparison_id": comp.id,
                "doc_a": {
                    "id": doc_a.id,
                    "filename": doc_a.filename,
                    "clause_count": len(clauses_a),
                },
                "doc_b": {
                    "id": doc_b.id,
                    "filename": doc_b.filename,
                    "clause_count": len(clauses_b),
                },
                "stats": {
                    "total_aligned": len(aligned),
                    "status_counts": status_counts,
                    "risk_counts": risk_counts,
                },
                "aligned_clauses": enriched_aligned,
            }

            comp.status = "ready"
            comp.json_data = report_json
            comp.error = None
            self.db.commit()
            return comp

        except Exception as e:
            logger.exception(f"Comparison failed between {doc_a_id} and {doc_b_id}: {e}")
            comp.status = "failed"
            comp.error = str(e)
            self.db.commit()
            raise


def export_comparison_to_markdown(comparison_data: Dict[str, Any]) -> str:
    """Formats comparison report into clean GitHub Flavored Markdown with redlines."""
    doc_a = comparison_data.get("doc_a", {})
    doc_b = comparison_data.get("doc_b", {})
    stats = comparison_data.get("stats", {})
    status_counts = stats.get("status_counts", {})
    risk_counts = stats.get("risk_counts", {})

    md = [
        f"# Contract Comparison Report",
        f"- **Base Document (A)**: `{doc_a.get('filename')}` ({doc_a.get('clause_count')} clauses)",
        f"- **Modified Document (B)**: `{doc_b.get('filename')}` ({doc_b.get('clause_count')} clauses)",
        f"",
        f"### Summary Statistics",
        f"- **Unchanged**: {status_counts.get('unchanged', 0)}",
        f"- **Modified**: {status_counts.get('modified', 0)}",
        f"- **Added**: {status_counts.get('added', 0)}",
        f"- **Removed**: {status_counts.get('removed', 0)}",
        f"- **Moved**: {status_counts.get('moved', 0)}",
        f"- **Risk Levels**: 🔴 High: {risk_counts.get('high', 0)} | 🟡 Medium: {risk_counts.get('medium', 0)} | 🟢 Low: {risk_counts.get('low', 0)}",
        f"",
        f"---",
        f"",
        f"## Clause Diff and Risk Analysis",
        f"",
    ]

    for idx, item in enumerate(comparison_data.get("aligned_clauses", [])):
        status = item.get("status", "").upper()
        ca = item.get("clause_a")
        cb = item.get("clause_b")
        p_a = item.get("page_a", "N/A")
        p_b = item.get("page_b", "N/A")
        analysis = item.get("analysis") or {}

        title_a = f"{ca.get('number', '')} {ca.get('heading', '')}".strip() if ca else "None"
        title_b = f"{cb.get('number', '')} {cb.get('heading', '')}".strip() if cb else "None"

        risk_badge = ""
        if analysis.get("risk") == "high":
            risk_badge = "🔴 **HIGH RISK**"
        elif analysis.get("risk") == "medium":
            risk_badge = "🟡 **MEDIUM RISK**"
        elif analysis.get("risk") == "low":
            risk_badge = "🟢 **LOW RISK**"

        md.append(f"### Clause {idx + 1}: [{status}] {title_b or title_a} {risk_badge}")
        md.append(f"- **Pages**: Doc A p.{p_a} | Doc B p.{p_b}")
        if analysis.get("summary"):
            md.append(f"- **Summary**: {analysis.get('summary')}")
            if analysis.get("risk_reason"):
                md.append(f"- **Risk Reason**: {analysis.get('risk_reason')}")
            if analysis.get("evidence_quote"):
                v_str = " (Verified)" if analysis.get("quote_verified") else " (Unverified Quote)"
                md.append(f'- **Evidence Quote**: *"{analysis.get("evidence_quote")}"*{v_str}')

        # Redline rendering
        tokens = item.get("diff_tokens", [])
        if tokens:
            rendered_words = []
            for t in tokens:
                tt = t.get("type")
                tx = t.get("text", "")
                if tt == "equal":
                    rendered_words.append(tx)
                elif tt == "delete":
                    rendered_words.append(f"~~{tx}~~")
                elif tt == "insert":
                    rendered_words.append(f"**{tx}**")
            md.append("\n**Redline Diff:**\n> " + " ".join(rendered_words))

        md.append("\n---\n")

    return "\n".join(md)
