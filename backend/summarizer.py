"""
Automatic Map-Reduce Document Summarization with NLI Claim Grounding Verification.
Groups chunks in section order, summarizes each section group (map), reduces into
{main_purpose, important_points[], key_information[], conclusion}, and runs the
Veridocs two-stage NLI verifier over all summary claims.
"""

import re
import time
import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from models_db import Document, Chunk, Page, DocumentSummary
from verification import verify_claim_against_chunks

logger = logging.getLogger(__name__)


def _clean_chunk_text(text: str) -> str:
    """Strip synthetic [Document: ...] prefix from stored chunk text."""
    cleaned = re.sub(r"^\[Document:\s*[^\]]+\]\s*", "", (text or "").strip())
    return cleaned.strip()


def _group_chunks_by_section(chunks: List[Dict[str, Any]], max_group_chars: int = 2400) -> List[Dict[str, Any]]:
    """Group ordered chunks into coherent section-ordered batches for map-reduce."""
    groups: List[Dict[str, Any]] = []
    current_chunks: List[Dict[str, Any]] = []
    current_section: Optional[str] = None
    current_chars = 0

    for ch in chunks:
        sec = ch.get("section_path") or (ch.get("metadata") or {}).get("section_path")
        txt = _clean_chunk_text(ch.get("text") or ch.get("content") or "")
        if not txt:
            continue

        sec_changed = bool(sec and current_section and sec != current_section and current_chars >= 600)
        if current_chunks and (sec_changed or current_chars + len(txt) > max_group_chars):
            groups.append(
                {
                    "section_path": current_section,
                    "chunks": current_chunks,
                    "text": "\n\n".join(
                        _clean_chunk_text(c.get("text") or c.get("content") or "") for c in current_chunks
                    ),
                    "pages": sorted({int(c.get("page") or c.get("page_number") or 1) for c in current_chunks}),
                }
            )
            current_chunks = []
            current_chars = 0

        if sec:
            current_section = sec
        current_chunks.append(ch)
        current_chars += len(txt)

    if current_chunks:
        groups.append(
            {
                "section_path": current_section,
                "chunks": current_chunks,
                "text": "\n\n".join(_clean_chunk_text(c.get("text") or c.get("content") or "") for c in current_chunks),
                "pages": sorted({int(c.get("page") or c.get("page_number") or 1) for c in current_chunks}),
            }
        )

    return groups


def _heuristic_map_group(group: Dict[str, Any]) -> str:
    """Deterministic extractive summary for a chunk group when LLM is unavailable."""
    raw = group.get("text", "")
    # Split into sentences and pick the most informative sentences
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", raw) if len(s.strip()) >= 20]
    if not sents:
        return raw[:300].strip()

    # Prefer sentences with numbers, dates, monetary values, or key obligations
    scored: List[tuple[float, int, str]] = []
    for idx, s in enumerate(sents[:20]):
        score = 0.0
        if re.search(r"(\$[\d,]+|\d+%|\b\d{4}\b|\b\d+\s+days?\b)", s, re.IGNORECASE):
            score += 2.0
        if re.search(
            r"\b(shall|must|agree|require|liability|payment|term|terminate|confidential|total|due)\b", s, re.IGNORECASE
        ):
            score += 1.5
        if idx == 0:
            score += 1.0
        scored.append((score, idx, s))

    scored.sort(key=lambda x: (-x[0], x[1]))
    top = sorted(scored[:3], key=lambda x: x[1])
    sec_label = f"[{group['section_path']}] " if group.get("section_path") else ""
    return sec_label + " ".join(item[2] for item in top)


def _heuristic_reduce_summaries(
    mapped_notes: List[Dict[str, Any]],
    chunks: List[Dict[str, Any]],
    filename: str,
) -> Dict[str, Any]:
    """Deterministic structured JSON reduction when LLM is unavailable."""
    all_sents: List[str] = []
    for note in mapped_notes:
        txt = note["summary"]
        clean_note = re.sub(r"^\[[^\]]+\]\s*", "", txt).strip()
        for s in re.split(r"(?<=[.!?])\s+", clean_note):
            s = s.strip()
            if len(s) >= 20 and s not in all_sents:
                all_sents.append(s)

    if not all_sents:
        for ch in chunks[:4]:
            t = _clean_chunk_text(ch.get("text") or ch.get("content") or "")
            if t:
                all_sents.append(t[:240])

    main_purpose = (
        all_sents[0] if all_sents else f"Document '{filename}' provides structured records and operational details."
    )

    # Important points: top factual sentences from sections
    important_points = all_sents[1:6] if len(all_sents) > 1 else [main_purpose]

    # Key information: extract sentences containing quantities, dates, currency, percentages, or parties
    key_info: List[str] = []
    for s in all_sents:
        if re.search(r"(\$[\d,]+|\d+%|\b\d+\s+days?\b|\b20\d{2}\b|Net\s+\d+)", s, re.IGNORECASE):
            if s not in key_info:
                key_info.append(s)
        if len(key_info) >= 5:
            break
    if not key_info:
        key_info = all_sents[:3] if all_sents else [main_purpose]

    conclusion = all_sents[-1] if len(all_sents) > 1 else main_purpose

    return {
        "main_purpose": main_purpose,
        "important_points": important_points,
        "key_information": key_info,
        "conclusion": conclusion,
    }


def _map_reduce_llm(
    groups: List[Dict[str, Any]],
    filename: str,
) -> Optional[Dict[str, Any]]:
    """Execute map-reduce summarization via configured OpenAI-compatible LLM."""
    from llm_service import get_llm_service, call_llm_json

    llm = get_llm_service()
    if not llm.is_configured() or not llm.client:
        return None

    mapped_notes: List[Dict[str, Any]] = []
    for idx, grp in enumerate(groups):
        sec = grp.get("section_path") or f"Part {idx + 1}"
        pages_str = ", ".join(str(p) for p in grp.get("pages", [1]))
        prompt = (
            f"Summarize the following section from '{filename}' (Section: {sec}, Pages: {pages_str}) "
            "in 2-4 factual bullet points preserving exact numbers, dates, parties, and obligations. "
            "Do not invent facts.\n\n"
            f"{grp['text'][:3000]}"
        )
        try:
            resp = llm.client.chat.completions.create(
                model=llm.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=300,
            )
            note_txt = (resp.choices[0].message.content or "").strip()
            if note_txt:
                mapped_notes.append({"section_path": sec, "pages": grp.get("pages", [1]), "summary": note_txt})
        except Exception as e:
            logger.debug(f"LLM map step failed on group {idx}: {e}")
            mapped_notes.append(
                {
                    "section_path": sec,
                    "pages": grp.get("pages", [1]),
                    "summary": _heuristic_map_group(grp),
                }
            )

    if not mapped_notes:
        return None

    combined_notes = "\n\n".join(
        f"## {n['section_path']} (Pages {', '.join(map(str, n['pages']))})\n{n['summary']}" for n in mapped_notes
    )[:8000]

    reduce_prompt = (
        f"Synthesize the section summaries below for '{filename}' into a strict JSON object with keys:\n"
        "- main_purpose: string (1-2 factual sentences describing the document's primary purpose)\n"
        "- important_points: array of 3-6 concise factual bullet strings\n"
        "- key_information: array of 2-6 key facts (dates, dollar amounts, SLAs, parties, obligations)\n"
        "- conclusion: string (1-2 factual sentences summarizing the overall takeaway/obligations)\n\n"
        "Every statement must stay strictly faithful to the notes.\n\n"
        f"SECTION SUMMARIES:\n{combined_notes}"
    )
    reduced = call_llm_json(reduce_prompt)
    if isinstance(reduced, dict) and reduced.get("main_purpose"):
        return {
            "main_purpose": str(reduced.get("main_purpose", "")).strip(),
            "important_points": [str(x).strip() for x in (reduced.get("important_points") or []) if str(x).strip()],
            "key_information": [str(x).strip() for x in (reduced.get("key_information") or []) if str(x).strip()],
            "conclusion": str(reduced.get("conclusion", "")).strip(),
        }
    return None


def verify_summary_claims(
    summary_payload: Dict[str, Any],
    chunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Run NLI verification over all claims in the structured summary."""
    claims_to_check: List[tuple[str, str]] = []
    if summary_payload.get("main_purpose"):
        claims_to_check.append(("main_purpose", str(summary_payload["main_purpose"])))
    for pt in summary_payload.get("important_points") or []:
        if pt:
            claims_to_check.append(("important_points", str(pt)))
    for ki in summary_payload.get("key_information") or []:
        if ki:
            claims_to_check.append(("key_information", str(ki)))
    if summary_payload.get("conclusion"):
        claims_to_check.append(("conclusion", str(summary_payload["conclusion"])))

    claim_results: List[Dict[str, Any]] = []
    supported_count = 0
    contradicted_count = 0

    for field_name, claim_text in claims_to_check:
        res = verify_claim_against_chunks(claim_text, chunks)
        res["field"] = field_name
        if res["status"] == "supported":
            supported_count += 1
        elif res["status"] == "contradicted":
            contradicted_count += 1
        claim_results.append(res)

    total = len(claim_results)
    grounding_score = round(supported_count / max(total, 1), 2) if total > 0 else 0.0

    return {
        "grounding_score": grounding_score,
        "total_claims": total,
        "supported_claims": supported_count,
        "contradicted_claims": contradicted_count,
        "claims": claim_results,
    }


class DocumentSummarizer:
    """Generates and caches structured document summaries with NLI grounding."""

    def __init__(self, db: Session):
        self.db = db

    def _load_document_chunks(self, doc: Document) -> List[Dict[str, Any]]:
        chunk_rows = self.db.query(Chunk).filter(Chunk.document_id == doc.id).order_by(Chunk.chunk_index.asc()).all()
        if chunk_rows:
            return [c.to_dict() for c in chunk_rows]

        # Fallback: load by session_id + filename if chunks weren't linked with document_id
        if doc.session_id:
            chunk_rows = (
                self.db.query(Chunk)
                .filter(Chunk.session_id == doc.session_id, Chunk.filename == doc.filename)
                .order_by(Chunk.chunk_index.asc())
                .all()
            )
            if chunk_rows:
                return [c.to_dict() for c in chunk_rows]

        # Last fallback: synthesize chunks from pages table
        page_rows = self.db.query(Page).filter(Page.document_id == doc.id).order_by(Page.page_number.asc()).all()
        return [
            {
                "id": p.id,
                "document_id": doc.id,
                "source_file": doc.filename,
                "filename": doc.filename,
                "page": p.page_number,
                "page_number": p.page_number,
                "text": p.text,
                "content": p.text,
                "chunk_type": "text",
                "section_path": None,
                "metadata": {},
            }
            for p in page_rows
            if (p.text or "").strip()
        ]

    def generate_and_save(self, document_id: str) -> DocumentSummary:
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise ValueError(f"Document '{document_id}' not found.")

        record = self.db.query(DocumentSummary).filter(DocumentSummary.document_id == document_id).first()
        if not record:
            record = DocumentSummary(
                document_id=document_id,
                status="processing",
                created_at=time.time(),
                updated_at=time.time(),
            )
            self.db.add(record)
            self.db.commit()
            self.db.refresh(record)
        else:
            record.status = "processing"
            record.error = None
            record.updated_at = time.time()
            self.db.commit()

        try:
            chunks = self._load_document_chunks(doc)
            if not chunks:
                raise ValueError("Document has no indexed text chunks to summarize.")

            groups = _group_chunks_by_section(chunks)
            summary_payload = _map_reduce_llm(groups, doc.filename)

            if not summary_payload:
                mapped_notes = [
                    {
                        "section_path": g.get("section_path") or f"Part {idx + 1}",
                        "pages": g.get("pages", [1]),
                        "summary": _heuristic_map_group(g),
                    }
                    for idx, g in enumerate(groups)
                ]
                summary_payload = _heuristic_reduce_summaries(mapped_notes, chunks, doc.filename)

            verification = verify_summary_claims(summary_payload, chunks)

            record.status = "ready"
            record.summary_json = summary_payload
            record.verification_json = verification
            record.grounding_score = verification["grounding_score"]
            record.error = None
            record.updated_at = time.time()
            self.db.commit()
            self.db.refresh(record)
            return record
        except Exception as e:
            logger.exception(f"Summary generation failed for {document_id}: {e}")
            record.status = "failed"
            record.error = str(e)
            record.updated_at = time.time()
            self.db.commit()
            self.db.refresh(record)
            raise
