"""
Document Report Generation & Export Service (Markdown, PDF, DOCX).
Combines structured summary, extracted entities/fields, anomaly flags,
and targeted risk retrieval into a cited executive intelligence report.
"""

import io
import re
import time
import logging
from typing import Dict, Any, List, Optional
from xml.sax.saxutils import escape as xml_escape
from sqlalchemy.orm import Session

from models_db import (
    Document,
    DocumentSummary,
    DocumentReport,
    Entity,
    Extraction,
)
from summarizer import DocumentSummarizer, _clean_chunk_text
from flags.checker import FlagCheckerService
from vector_store import VectorStore

logger = logging.getLogger(__name__)

RISK_QUERY = "risk liability indemnity penalty termination breach default compliance uncapped fine"


def _match_chunk_citation(
    query_text: str,
    chunks: List[Dict[str, Any]],
    preferred_page: Optional[int] = None,
    fallback_idx: int = 0,
) -> Dict[str, Any]:
    """Find the best matching chunk for a finding/risk and return a citation dict."""
    if not chunks:
        return {
            "chunk_id": None,
            "page": preferred_page or 1,
            "section_path": None,
            "quote": (query_text or "")[:180],
        }

    q_tokens = set(re.findall(r"\b[a-z0-9]{3,}\b", (query_text or "").lower()))
    best_chunk = None
    best_score = -1.0

    for ch in chunks:
        ch_page = int(ch.get("page") or ch.get("page_number") or 1)
        ch_txt = _clean_chunk_text(ch.get("text") or ch.get("content") or "")
        ch_tokens = set(re.findall(r"\b[a-z0-9]{3,}\b", ch_txt.lower()))
        overlap = len(q_tokens & ch_tokens) / max(len(q_tokens), 1) if q_tokens else 0.0
        page_bonus = 0.25 if (preferred_page is not None and ch_page == preferred_page) else 0.0
        score = overlap + page_bonus
        if score > best_score:
            best_score = score
            best_chunk = ch

    if best_chunk is None or best_score <= 0.0:
        best_chunk = chunks[fallback_idx % len(chunks)]

    raw_quote = _clean_chunk_text(best_chunk.get("text") or best_chunk.get("content") or "")
    return {
        "chunk_id": best_chunk.get("id"),
        "page": int(best_chunk.get("page") or best_chunk.get("page_number") or 1),
        "section_path": best_chunk.get("section_path") or (best_chunk.get("metadata") or {}).get("section_path"),
        "quote": raw_quote[:200],
    }


def _targeted_risk_retrieval(
    doc: Document,
    chunks: List[Dict[str, Any]],
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """Retrieve risk-relevant chunks for the document via VectorStore or local keyword scoring."""
    if doc.session_id:
        try:
            hits = VectorStore.search(
                session_id=str(doc.session_id),
                query=RISK_QUERY,
                top_k=top_k,
                active_files=[str(doc.filename)],
            )
            if hits:
                return hits
        except Exception as e:
            logger.debug(f"VectorStore risk retrieval fallback: {e}")

    risk_terms = set(RISK_QUERY.split())
    scored: List[tuple[int, Dict[str, Any]]] = []
    for ch in chunks:
        txt = _clean_chunk_text(ch.get("text") or ch.get("content") or "").lower()
        tokens = set(re.findall(r"\b[a-z0-9]+\b", txt))
        hits = len(risk_terms & tokens)
        if hits > 0:
            scored.append((hits, ch))
    scored.sort(key=lambda x: -x[0])
    return [c for _, c in scored[:top_k]]


class DocumentReportService:
    """Synthesizes comprehensive cited document reports and caches them."""

    def __init__(self, db: Session):
        self.db = db

    def generate_report(self, document_id: str) -> Dict[str, Any]:
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document '{document_id}' not found.")

        summarizer = DocumentSummarizer(self.db)
        chunks = summarizer._load_document_chunks(doc)
        if not chunks:
            raise ValueError("Document has no indexed chunks to generate a report.")

        # 1. Summary (reuse cached ready summary or generate now)
        summary_rec = self.db.query(DocumentSummary).filter(DocumentSummary.document_id == document_id).first()
        if not summary_rec or summary_rec.status != "ready" or not summary_rec.summary_json:
            summary_rec = summarizer.generate_and_save(document_id)
        summary_data = summary_rec.summary_json or {}

        # 2. Entities & Structured Extraction
        entities = [e.to_dict() for e in self.db.query(Entity).filter(Entity.document_id == document_id).all()]
        ext_rec = self.db.query(Extraction).filter(Extraction.document_id == document_id).first()
        extraction_fields = (ext_rec.json_data if ext_rec else {}) or {}

        # 3. Anomaly Flags (run checks if none exist yet)
        flag_service = FlagCheckerService(self.db)
        flags_data = flag_service.get_flags(document_id)
        if flags_data.get("total_flags", 0) == 0:
            flag_service.run_all_checks(document_id)
            flags_data = flag_service.get_flags(document_id)
        flags = flags_data.get("flags", [])

        # 4. Targeted Retrieval for Risk-Related Content
        risk_chunks = _targeted_risk_retrieval(doc, chunks, top_k=5)

        # 5. Assemble Executive Summary
        main_purpose = summary_data.get("main_purpose", "")
        conclusion = summary_data.get("conclusion", "")
        doc_type_label = (doc.doc_type or "document").replace("_", " ")
        exec_parts = [
            f"Analysis of {doc.filename} ({doc_type_label}, {doc.page_count or 1} page(s)): {main_purpose}".strip()
        ]
        if flags:
            exec_parts.append(
                f"Automated rule screening identified {len(flags)} advisory flag(s) requiring human review."
            )
        if entities:
            exec_parts.append(f"Extracted {len(entities)} named entity reference(s).")
        if conclusion and conclusion != main_purpose:
            exec_parts.append(conclusion)
        executive_summary = " ".join(p for p in exec_parts if p).strip()

        # 6. Build Important Findings (every finding must cite chunks: page + section)
        important_findings: List[Dict[str, Any]] = []
        for idx, pt in enumerate(summary_data.get("important_points") or []):
            cit = _match_chunk_citation(pt, chunks, fallback_idx=idx)
            important_findings.append(
                {
                    "title": f"Key Point {idx + 1}",
                    "detail": pt,
                    "category": "summary",
                    "citations": [cit],
                }
            )

        for idx, ki in enumerate(summary_data.get("key_information") or []):
            cit = _match_chunk_citation(ki, chunks, fallback_idx=idx)
            important_findings.append(
                {
                    "title": f"Key Detail {idx + 1}",
                    "detail": ki,
                    "category": "key_information",
                    "citations": [cit],
                }
            )

        # Add verified structured extraction fields as findings
        for field_name, field_val in extraction_fields.items():
            if isinstance(field_val, dict) and field_val.get("value") is not None and field_val.get("verified"):
                quote = field_val.get("quote") or str(field_val.get("value"))
                p_num = int(field_val.get("page") or 1)
                cit = _match_chunk_citation(quote, chunks, preferred_page=p_num)
                important_findings.append(
                    {
                        "title": field_name.replace("_", " ").title(),
                        "detail": f"Verified {field_name.replace('_', ' ')}: {field_val.get('value')}",
                        "category": "extraction",
                        "citations": [cit],
                    }
                )
                if len(important_findings) >= 12:
                    break

        if not important_findings:
            cit = _match_chunk_citation(executive_summary, chunks, fallback_idx=0)
            important_findings.append(
                {
                    "title": "Document Overview",
                    "detail": executive_summary or f"Indexed content from {doc.filename}.",
                    "category": "summary",
                    "citations": [cit],
                }
            )

        # 7. Build Risks (from anomaly flags + targeted risk retrieval)
        risks: List[Dict[str, Any]] = []
        seen_risk_texts = set()

        for fl in flags:
            ev_list = fl.get("evidence") or []
            cits: List[Dict[str, Any]] = []
            for ev in ev_list[:2]:
                ev_q = ev.get("quote") or fl.get("message", "")
                ev_p = ev.get("page")
                cits.append(_match_chunk_citation(ev_q, chunks, preferred_page=ev_p))
            if not cits:
                cits.append(_match_chunk_citation(fl.get("message", ""), chunks))

            msg = fl.get("message", "Anomaly detected")
            seen_risk_texts.add(msg.lower()[:80])
            risks.append(
                {
                    "title": fl.get("rule_id", "anomaly_flag").replace("_", " ").title(),
                    "detail": msg,
                    "severity": fl.get("severity", "medium"),
                    "category": "anomaly_flag",
                    "citations": cits,
                }
            )

        for idx, rc in enumerate(risk_chunks):
            txt = _clean_chunk_text(rc.get("text") or rc.get("content") or "")
            if not txt:
                continue
            snippet_key = txt.lower()[:80]
            if snippet_key in seen_risk_texts:
                continue
            seen_risk_texts.add(snippet_key)
            cit = {
                "chunk_id": rc.get("id"),
                "page": int(rc.get("page") or rc.get("page_number") or 1),
                "section_path": rc.get("section_path") or (rc.get("metadata") or {}).get("section_path"),
                "quote": txt[:200],
            }
            sec_title = cit["section_path"] or f"Clause on Page {cit['page']}"
            risks.append(
                {
                    "title": f"Risk Exposure: {sec_title}",
                    "detail": txt[:260] + ("..." if len(txt) > 260 else ""),
                    "severity": "medium"
                    if any(w in txt.lower() for w in ("unlimited", "indemn", "penalty", "breach", "terminate"))
                    else "low",
                    "category": "risk_clause",
                    "citations": [cit],
                }
            )
            if len(risks) >= 8:
                break

        # 8. Build Recommendations (every recommendation cites supporting chunks)
        recommendations: List[Dict[str, Any]] = []
        for r in risks[:4]:
            recommendations.append(
                {
                    "title": f"Review {r['title']}",
                    "detail": f"Verify and remediate or obtain sign-off on: {r['detail'][:180]}",
                    "severity": r.get("severity", "medium"),
                    "category": "remediation",
                    "citations": r["citations"],
                }
            )

        if not recommendations:
            cit = important_findings[0]["citations"][0]
            recommendations.append(
                {
                    "title": "Confirm Commercial & Compliance Terms",
                    "detail": "Confirm key obligations, dates, and payment terms against internal policy before execution.",
                    "severity": "low",
                    "category": "governance",
                    "citations": [cit],
                }
            )

        report_payload = {
            "document_id": doc.id,
            "filename": doc.filename,
            "executive_summary": executive_summary,
            "important_findings": important_findings,
            "risks": risks,
            "recommendations": recommendations,
        }

        # Cache in document_reports table
        existing_rep = self.db.query(DocumentReport).filter(DocumentReport.document_id == document_id).first()
        now = time.time()
        if existing_rep:
            existing_rep.report_json = report_payload
            existing_rep.updated_at = now
        else:
            existing_rep = DocumentReport(
                document_id=document_id,
                report_json=report_payload,
                created_at=now,
                updated_at=now,
            )
            self.db.add(existing_rep)
        self.db.commit()

        report_payload["generated_at"] = now
        return report_payload


def _format_citations_line(citations: List[Dict[str, Any]]) -> str:
    if not citations:
        return "No citation"
    parts = []
    for c in citations:
        sec = c.get("section_path")
        pg = c.get("page", 1)
        parts.append(f"{sec} · p.{pg}" if sec else f"p.{pg}")
    return "; ".join(parts)


def export_report_to_markdown(report: Dict[str, Any]) -> str:
    """Export structured document report to GitHub Flavored Markdown."""
    filename = report.get("filename") or report.get("document_id", "Document")
    lines = [
        f"# Document Intelligence Report: `{filename}`",
        "",
        "## Executive Summary",
        report.get("executive_summary", ""),
        "",
        "---",
        "",
        "## Important Findings",
        "",
    ]

    for idx, item in enumerate(report.get("important_findings", []), start=1):
        cit_str = _format_citations_line(item.get("citations", []))
        lines.append(f"### {idx}. {item.get('title', 'Finding')} ({cit_str})")
        lines.append(item.get("detail", ""))
        for c in item.get("citations", []):
            if c.get("quote"):
                lines.append(f'> *"{c["quote"]}"*')
        lines.append("")

    lines.extend(["---", "", "## Identified Risks & Anomaly Signals", ""])
    risks = report.get("risks", [])
    if not risks:
        lines.append("- No significant risk clauses or anomaly flags detected.")
    else:
        for idx, r in enumerate(risks, start=1):
            sev = (r.get("severity") or "low").upper()
            badge = "🔴 HIGH" if sev == "HIGH" else ("🟡 MEDIUM" if sev == "MEDIUM" else "🟢 LOW")
            cit_str = _format_citations_line(r.get("citations", []))
            lines.append(f"### {idx}. [{badge}] {r.get('title', 'Risk')} ({cit_str})")
            lines.append(r.get("detail", ""))
            for c in r.get("citations", []):
                if c.get("quote"):
                    lines.append(f'> *"{c["quote"]}"*')
            lines.append("")

    lines.extend(["---", "", "## Recommendations", ""])
    for idx, rec in enumerate(report.get("recommendations", []), start=1):
        cit_str = _format_citations_line(rec.get("citations", []))
        lines.append(f"{idx}. **{rec.get('title', 'Recommendation')}** ({cit_str}): {rec.get('detail', '')}")

    return "\n".join(lines).strip() + "\n"


def export_report_to_pdf(report: Dict[str, Any]) -> bytes:
    """Export structured document report to PDF bytes via ReportLab."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )
    styles = getSampleStyleSheet()
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = styles["BodyText"]
    quote_style = ParagraphStyle(
        "QuoteStyle",
        parent=styles["BodyText"],
        leftIndent=16,
        fontSize=9,
        textColor="#555555",
        spaceAfter=6,
    )

    filename = report.get("filename") or report.get("document_id", "Document")
    story = [
        Paragraph(f"Document Intelligence Report: {xml_escape(str(filename))}", styles["Title"]),
        Spacer(1, 10),
        Paragraph("Executive Summary", heading_style),
        Paragraph(xml_escape(report.get("executive_summary", "")), body_style),
        Spacer(1, 8),
        Paragraph("Important Findings", heading_style),
    ]

    for idx, item in enumerate(report.get("important_findings", []), start=1):
        cit_str = _format_citations_line(item.get("citations", []))
        story.append(
            Paragraph(
                f"<b>{idx}. {xml_escape(str(item.get('title', 'Finding')))}</b> <i>({xml_escape(cit_str)})</i>",
                body_style,
            )
        )
        story.append(Paragraph(xml_escape(str(item.get("detail", ""))), body_style))
        for c in item.get("citations", []):
            if c.get("quote"):
                story.append(Paragraph(f"&ldquo;{xml_escape(str(c['quote']))}&rdquo;", quote_style))

    story.append(Paragraph("Risks &amp; Anomaly Signals", heading_style))
    risks = report.get("risks", [])
    if not risks:
        story.append(Paragraph("No significant risks or anomaly flags detected.", body_style))
    else:
        for idx, r in enumerate(risks, start=1):
            sev = (r.get("severity") or "low").upper()
            cit_str = _format_citations_line(r.get("citations", []))
            story.append(
                Paragraph(
                    f"<b>[{xml_escape(sev)}] {idx}. {xml_escape(str(r.get('title', 'Risk')))}</b> "
                    f"<i>({xml_escape(cit_str)})</i>",
                    body_style,
                )
            )
            story.append(Paragraph(xml_escape(str(r.get("detail", ""))), body_style))

    story.append(Paragraph("Recommendations", heading_style))
    for idx, rec in enumerate(report.get("recommendations", []), start=1):
        cit_str = _format_citations_line(rec.get("citations", []))
        story.append(
            Paragraph(
                f"<b>{idx}. {xml_escape(str(rec.get('title', 'Recommendation')))}</b> "
                f"<i>({xml_escape(cit_str)})</i>: {xml_escape(str(rec.get('detail', '')))}",
                body_style,
            )
        )

    doc.build(story)
    return buf.getvalue()


def export_report_to_docx(report: Dict[str, Any]) -> bytes:
    """Export structured document report to DOCX bytes via python-docx."""
    from docx import Document as DocxDocument

    docx_doc = DocxDocument()
    filename = report.get("filename") or report.get("document_id", "Document")
    docx_doc.add_heading(f"Document Intelligence Report: {filename}", level=0)

    docx_doc.add_heading("Executive Summary", level=1)
    docx_doc.add_paragraph(report.get("executive_summary", ""))

    docx_doc.add_heading("Important Findings", level=1)
    for idx, item in enumerate(report.get("important_findings", []), start=1):
        cit_str = _format_citations_line(item.get("citations", []))
        docx_doc.add_heading(f"{idx}. {item.get('title', 'Finding')} ({cit_str})", level=2)
        docx_doc.add_paragraph(item.get("detail", ""))
        for c in item.get("citations", []):
            if c.get("quote"):
                p = docx_doc.add_paragraph(f'"{c["quote"]}"')
                p.italic = True

    docx_doc.add_heading("Identified Risks & Anomaly Signals", level=1)
    risks = report.get("risks", [])
    if not risks:
        docx_doc.add_paragraph("No significant risk clauses or anomaly flags detected.")
    else:
        for idx, r in enumerate(risks, start=1):
            sev = (r.get("severity") or "low").upper()
            cit_str = _format_citations_line(r.get("citations", []))
            docx_doc.add_heading(f"{idx}. [{sev}] {r.get('title', 'Risk')} ({cit_str})", level=2)
            docx_doc.add_paragraph(r.get("detail", ""))

    docx_doc.add_heading("Recommendations", level=1)
    for idx, rec in enumerate(report.get("recommendations", []), start=1):
        cit_str = _format_citations_line(rec.get("citations", []))
        docx_doc.add_paragraph(f"{idx}. {rec.get('title', 'Recommendation')} ({cit_str}): {rec.get('detail', '')}")

    buf = io.BytesIO()
    docx_doc.save(buf)
    return buf.getvalue()
