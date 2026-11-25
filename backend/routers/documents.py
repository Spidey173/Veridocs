"""
Document management and ingestion routes for Veridocs.
Handles asynchronous and synchronous uploads, SSE live progress events, status polling,
table inspections, raw/converted PDF serving, summaries, and report exports.
"""

import uuid
import json
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Body, Query
from fastapi.responses import FileResponse, StreamingResponse, Response

from config import get_settings, get_model_registry
from models import (
    UploadResponse,
    SessionInfo,
    SummaryRequest,
    DocumentSummaryResponse,
    DocumentReportResponse,
)
import database
from pdf_processor import extract_text_from_file, chunk_text, save_upload_file_stream, safe_delete_file
from ingestion.docx_backend import find_libreoffice_bin
from rate_limiter import check_rate_limit
from queue_service import enqueue_task, subscribe_status_events
from tasks import process_document_pipeline, process_summary_task

logger = logging.getLogger(__name__)
router = APIRouter(tags=["documents"])


def generate_suggested_questions(document_name: str, chunks: List[dict]) -> List[str]:
    """Generate 3 relevant suggested questions based on the document type and content."""
    if "sample_agreement" in document_name.lower():
        return [
            "What are the payment terms in this agreement?",
            "What is the limitation of liability and uptime SLA?",
            "What data protection and encryption standards are required?",
        ]

    settings = get_settings()
    if settings.is_llm_configured() and chunks:
        try:
            from llm_service import get_llm_service

            llm = get_llm_service()
            if llm.client:
                sample_text = "\n\n".join([c.get("text", c.get("content", ""))[:350] for c in chunks[:3]])
                prompt = (
                    "Based on the following excerpts from an uploaded document, generate exactly 3 short, relevant questions "
                    "a user would ask about this document.\n"
                    "Output ONLY the 3 questions, one per line. Do not number them or include bullets.\n\n"
                    f"EXCERPTS:\n{sample_text}"
                )
                response = llm.client.chat.completions.create(
                    model=llm.model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=120,
                    temperature=0.2,
                )
                raw = response.choices[0].message.content or ""
                lines = [
                    l.strip().lstrip("0123456789.-*•) ") for l in raw.strip().split("\n") if l.strip() and "?" in l
                ]
                if len(lines) >= 3:
                    return lines[:3]
                elif lines:
                    return lines
        except Exception as e:
            logger.warning(f"Could not generate dynamic suggestions via LLM: {e}")

    return [
        "Summarize this document",
        "What are the key points?",
        "What are the main requirements and dates?",
    ]


# ----------------------------------------------------------------------
# Asynchronous Ingestion & Live SSE Status Endpoints
# ----------------------------------------------------------------------


@router.post("/documents/upload")
@router.post("/api/documents/upload")
async def upload_document_async(
    request: Request,
    file: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
):
    """
    POST /documents/upload: Stores file, creates Document record with status='queued',
    enqueues background task, and returns immediately with document_id and status.
    """
    settings = get_settings()
    client_ip = request.client.host if request.client else "127.0.0.1"
    limit_err = check_rate_limit(client_ip, action="upload")
    if limit_err:
        raise HTTPException(status_code=429, detail=limit_err)

    filename = file.filename or "uploaded_document.pdf"
    ext = Path(filename).suffix.lower()

    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format '{ext}'. Supported formats: PDF, DOCX, DOC, PNG, JPG, JPEG, TIFF, TXT.",
        )

    if ext == ".doc" and not find_libreoffice_bin():
        raise HTTPException(
            status_code=400,
            detail="Legacy .doc files require LibreOffice headless conversion, which is not available on this server. Please convert to .docx or .pdf.",
        )

    sid = session_id or str(uuid.uuid4())
    doc_record = database.create_document(
        filename=filename,
        mime_type=file.content_type or "application/octet-stream",
        session_id=sid,
        status="queued",
    )
    doc_id = doc_record["id"]

    try:
        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        file_unique_id = f"{sid}_{filename}"
        save_path, total_read, file_too_large = await save_upload_file_stream(
            file=file,
            max_bytes=max_bytes,
            file_id=file_unique_id,
            ext="",
        )

        if file_too_large:
            safe_delete_file(save_path)
            database.update_document_status(doc_id, status="failed", error="File size exceeds limit")
            raise HTTPException(status_code=400, detail=f"File exceeds maximum size of {settings.MAX_FILE_SIZE_MB}MB.")

        # Enqueue background pipeline task
        enqueue_task(process_document_pipeline, doc_id, str(save_path), sid)

        return {
            "document_id": doc_id,
            "session_id": sid,
            "filename": filename,
            "status": "queued",
            "message": "Document accepted and queued for background ingestion.",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling upload for {filename}: {e}", exc_info=True)
        database.update_document_status(doc_id, status="failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to queue document: {str(e)}")


@router.get("/documents/{document_id}/status")
@router.get("/api/documents/{document_id}/status")
async def get_document_status(document_id: str):
    """Retrieve current processing status and metadata for a document."""
    doc = database.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    return {
        "document_id": doc["id"],
        "session_id": doc["session_id"],
        "filename": doc["filename"],
        "status": doc["status"],
        "page_count": doc["page_count"],
        "doc_type": doc["doc_type"],
        "error": doc["error"],
        "created_at": doc["created_at"],
        "updated_at": doc["updated_at"],
    }


@router.get("/documents/{document_id}/events")
@router.get("/api/documents/{document_id}/events")
async def stream_document_events(document_id: str):
    """
    SSE stream of live progress events for document ingestion:
    queued -> parsing -> ocr -> chunking -> embedding -> ready | failed.
    """
    doc = database.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    def event_stream():
        for event in subscribe_status_events(document_id):
            yield f"event: status\ndata: {json.dumps(event)}\n\n"
            if event.get("status") in ("ready", "failed"):
                yield f"event: done\ndata: {json.dumps(event)}\n\n"
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/documents/{document_id}/retry")
@router.post("/api/documents/{document_id}/retry")
async def retry_document_processing(document_id: str):
    """Retry processing for a failed document."""
    settings = get_settings()
    doc = database.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    file_unique_id = f"{doc['session_id']}_{doc['filename']}"
    file_path = settings.UPLOAD_DIR / file_unique_id
    if not file_path.exists():
        file_path = settings.UPLOAD_DIR / doc["filename"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document file not found on server disk for retry.")

    database.update_document_status(document_id, status="queued", error=None)
    enqueue_task(process_document_pipeline, document_id, str(file_path), doc["session_id"])

    return {
        "document_id": document_id,
        "status": "queued",
        "message": "Document re-queued for processing.",
    }


@router.get("/documents/{document_id}/tables")
@router.get("/api/documents/{document_id}/tables")
async def get_document_extracted_tables(document_id: str):
    """Return all extracted tables for a document (Markdown and structured JSON)."""
    doc = database.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    tables = database.get_document_tables(document_id)
    return {
        "document_id": document_id,
        "filename": doc["filename"],
        "tables": tables,
    }


@router.get("/documents/{document_id}/vision")
@router.get("/api/documents/{document_id}/vision")
async def get_document_vision(document_id: str):
    """Retrieve multimodal vision analyses for flagged pages of a document."""
    doc = database.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    vision_records = database.get_page_vision(document_id)
    return {
        "document_id": document_id,
        "filename": doc["filename"],
        "pages": vision_records,
    }


@router.get("/documents/{document_id}/entities")
@router.get("/api/documents/{document_id}/entities")
async def get_document_entities(document_id: str, label: Optional[str] = None):
    """Retrieve normalized entities extracted from a document, optionally filtered by label."""
    doc = database.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    entities = database.get_entities(document_id, label=label)
    return {
        "document_id": document_id,
        "filename": doc["filename"],
        "entities": entities,
    }


@router.get("/documents/{document_id}/extraction")
@router.get("/api/documents/{document_id}/extraction")
async def get_document_extraction(document_id: str):
    """Retrieve structured schema extraction and field evidence for a document."""
    doc = database.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    ext = database.get_extraction(document_id)
    if not ext:
        return {
            "document_id": document_id,
            "filename": doc["filename"],
            "schema_type": doc.get("doc_type") or "other",
            "fields": {},
            "verified_ratio": 0.0,
            "user_edits": {},
        }

    return {
        "document_id": document_id,
        "filename": doc["filename"],
        "schema_type": ext.get("schema_type") or doc.get("doc_type") or "other",
        "fields": ext.get("fields", {}),
        "verified_ratio": ext.get("verified_ratio", 0.0),
        "user_edits": ext.get("user_edits", {}),
    }


@router.put("/documents/{document_id}/extraction")
@router.put("/api/documents/{document_id}/extraction")
async def update_document_extraction(document_id: str, payload: Dict[str, Any] = Body(...)):
    """Save user manual edits on extracted fields without overwriting model output."""
    doc = database.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    user_edits = payload.get("user_edits") or payload
    updated = database.update_extraction_user_edits(document_id, user_edits)
    if not updated:
        # If no extraction record exists yet, create one
        updated = database.save_extraction(
            document_id=document_id,
            schema_type=doc.get("doc_type") or "other",
            json_data={},
            verified_ratio=0.0,
            user_edits=user_edits,
        )

    return {
        "document_id": document_id,
        "status": "updated",
        "user_edits": updated.get("user_edits", {}),
    }


@router.patch("/documents/{document_id}/type")
@router.patch("/api/documents/{document_id}/type")
async def override_document_type(document_id: str, payload: Dict[str, Any] = Body(...)):
    """Allow user to manually override classified document type (e.g. invoice, contract)."""
    doc = database.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    new_type = payload.get("doc_type", "").lower().strip()
    if not new_type:
        raise HTTPException(status_code=400, detail="Missing 'doc_type' in payload.")

    database.update_document_classification(document_id, doc_type=new_type, confidence=1.0)
    return {
        "document_id": document_id,
        "doc_type": new_type,
        "message": f"Document classified type overridden to '{new_type}'.",
    }


@router.get("/documents/{document_id}/flags")
@router.get("/api/documents/{document_id}/flags")
async def get_document_flags_endpoint(document_id: str):
    """
    Retrieve rule-based anomaly flags for human reviewer auditing.
    Includes plain-language disclaimer ('signals for human review, not accusations'),
    severity breakdown, and evidence quotes with page numbers.
    """
    doc = database.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    with database.get_db() as db:
        from flags.checker import FlagCheckerService

        checker = FlagCheckerService(db)
        data = checker.get_flags(document_id)
        if data.get("total_flags", 0) == 0:
            checker.run_all_checks(document_id)
            data = checker.get_flags(document_id)

    return {
        "document_id": document_id,
        "filename": doc["filename"],
        **data,
    }


@router.post("/documents/{document_id}/summary", response_model=DocumentSummaryResponse)
@router.post("/api/documents/{document_id}/summary", response_model=DocumentSummaryResponse)
async def create_document_summary(
    document_id: str,
    force: bool = False,
    payload: Optional[SummaryRequest] = Body(default=None),
):
    """
    POST /documents/{id}/summary: Enqueues map-reduce structured summarization job
    (or returns cached ready summary unless force=True).
    """
    import time as _time
    from models_db import DocumentSummary

    doc = database.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    should_force = force or (payload.force if payload else False)

    with database.get_db() as db:
        existing = db.query(DocumentSummary).filter(DocumentSummary.document_id == document_id).first()
        if existing and existing.status == "ready" and existing.summary_json and not should_force:
            return DocumentSummaryResponse(
                document_id=document_id,
                filename=doc["filename"],
                status=existing.status,
                summary=existing.summary_json,
                verification=existing.verification_json,
                grounding_score=existing.grounding_score,
                error=existing.error,
                created_at=existing.created_at,
                updated_at=existing.updated_at,
            )

        if not existing:
            existing = DocumentSummary(
                document_id=document_id,
                status="queued",
                created_at=_time.time(),
                updated_at=_time.time(),
            )
            db.add(existing)
        else:
            existing.status = "queued"
            existing.error = None
            existing.updated_at = _time.time()
        db.commit()
        db.refresh(existing)
        snap = existing.to_dict()

    enqueue_task(process_summary_task, document_id)

    return DocumentSummaryResponse(
        document_id=document_id,
        filename=doc["filename"],
        status=snap["status"],
        summary=snap.get("summary"),
        verification=snap.get("verification"),
        grounding_score=snap.get("grounding_score"),
        error=snap.get("error"),
        created_at=snap.get("created_at"),
        updated_at=snap.get("updated_at"),
    )


@router.get("/documents/{document_id}/summary", response_model=DocumentSummaryResponse)
@router.get("/api/documents/{document_id}/summary", response_model=DocumentSummaryResponse)
async def get_document_summary(document_id: str):
    """GET /documents/{id}/summary: Fetch cached summary status and result."""
    from models_db import DocumentSummary

    doc = database.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    with database.get_db() as db:
        existing = db.query(DocumentSummary).filter(DocumentSummary.document_id == document_id).first()
        if not existing:
            return DocumentSummaryResponse(
                document_id=document_id,
                filename=doc["filename"],
                status="not_generated",
            )
        return DocumentSummaryResponse(
            document_id=document_id,
            filename=doc["filename"],
            status=existing.status,
            summary=existing.summary_json,
            verification=existing.verification_json,
            grounding_score=existing.grounding_score,
            error=existing.error,
            created_at=existing.created_at,
            updated_at=existing.updated_at,
        )


@router.post("/documents/{document_id}/report", response_model=DocumentReportResponse)
@router.post("/api/documents/{document_id}/report", response_model=DocumentReportResponse)
async def generate_document_report(document_id: str):
    """
    POST /documents/{id}/report: Generates a comprehensive cited report from summary,
    entities/extraction, anomaly flags, and targeted risk retrieval.
    """
    from report_generator import DocumentReportService

    doc = database.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    try:
        with database.get_db() as db:
            service = DocumentReportService(db)
            report = service.generate_report(document_id)
        return DocumentReportResponse(**report)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.exception(f"Report generation failed for {document_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Report generation failed: {str(e)}")


@router.get("/documents/{document_id}/report", response_model=DocumentReportResponse)
@router.get("/api/documents/{document_id}/report", response_model=DocumentReportResponse)
async def get_document_report(document_id: str):
    """GET /documents/{id}/report: Fetch cached report if previously generated."""
    from models_db import DocumentReport

    doc = database.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    with database.get_db() as db:
        rep = db.query(DocumentReport).filter(DocumentReport.document_id == document_id).first()
        if not rep:
            raise HTTPException(status_code=404, detail="Report has not been generated yet.")
        return DocumentReportResponse(**rep.to_dict())


@router.get("/documents/{document_id}/report/export")
@router.get("/api/documents/{document_id}/report/export")
async def export_document_report(
    document_id: str,
    format: str = Query("md", pattern="^(md|pdf|docx)$"),
):
    """
    GET /documents/{id}/report/export?format=md|pdf|docx:
    Export the generated report as Markdown, PDF, or DOCX.
    """
    from models_db import DocumentReport
    from report_generator import (
        DocumentReportService,
        export_report_to_markdown,
        export_report_to_pdf,
        export_report_to_docx,
    )

    doc = database.get_document(document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    with database.get_db() as db:
        rep = db.query(DocumentReport).filter(DocumentReport.document_id == document_id).first()
        if rep and rep.report_json:
            report_data = rep.to_dict()
        else:
            report_data = DocumentReportService(db).generate_report(document_id)

    stem = Path(doc["filename"]).stem or "document"
    safe_stem = "".join(c if c.isalnum() or c in "-_" else "_" for c in stem)

    if format == "md":
        md_text = export_report_to_markdown(report_data)
        return Response(
            content=md_text.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{safe_stem}_report.md"'},
        )
    elif format == "pdf":
        pdf_bytes = export_report_to_pdf(report_data)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{safe_stem}_report.pdf"'},
        )
    else:
        docx_bytes = export_report_to_docx(report_data)
        return Response(
            content=docx_bytes,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{safe_stem}_report.docx"'},
        )


# ----------------------------------------------------------------------
# Synchronous Batch Upload Endpoint
# ----------------------------------------------------------------------


@router.post("/api/upload", response_model=UploadResponse)
async def upload_documents(
    request: Request,
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Form(None),
):
    """
    Synchronous batch upload for immediate document indexing.
    """
    settings = get_settings()

    client_ip = request.client.host if request.client else "127.0.0.1"
    limit_err = check_rate_limit(client_ip, action="upload")
    if limit_err:
        raise HTTPException(status_code=429, detail=limit_err)

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    sid = session_id or str(uuid.uuid4())
    all_chunks = []
    processed_files = 0
    failed_files = []
    doc_metadata = []
    saved_file_names = []

    for file in files:
        filename = file.filename or "unknown.pdf"
        ext = Path(filename).suffix.lower()

        if ext not in settings.ALLOWED_EXTENSIONS:
            failed_files.append(f"{filename} (unsupported format; use .pdf, .docx, .doc, .txt, .png, etc.)")
            continue

        if ext == ".doc" and not find_libreoffice_bin():
            failed_files.append(
                f"{filename} (legacy .doc requires LibreOffice, which is not available; please convert to .docx or .pdf)"
            )
            continue

        try:
            max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
            file_unique_id = f"{sid}_{filename}"
            save_path, total_read, file_too_large = await save_upload_file_stream(
                file=file,
                max_bytes=max_bytes,
                file_id=file_unique_id,
                ext="",
            )

            if file_too_large:
                failed_files.append(f"{filename} (exceeds {settings.MAX_FILE_SIZE_MB}MB limit)")
                safe_delete_file(save_path)
                continue

            # Process synchronously via ingestion pipeline logic
            doc_record = database.create_document(
                filename=filename,
                mime_type=file.content_type or "application/octet-stream",
                session_id=sid,
                status="parsing",
            )
            doc_id = doc_record["id"]

            pages = extract_text_from_file(save_path, filename=filename)
            if not pages:
                failed_files.append(f"{filename} (no extractable text)")
                safe_delete_file(save_path)
                database.update_document_status(doc_id, status="failed", error="No extractable text")
                continue

            if len(pages) > settings.MAX_PDF_PAGES:
                failed_files.append(f"{filename} (exceeds {settings.MAX_PDF_PAGES} page limit; has {len(pages)} pages)")
                safe_delete_file(save_path)
                database.update_document_status(doc_id, status="failed", error="Exceeds page limit")
                continue

            # Save pages & tables
            database.save_document_pages(doc_id, pages)
            tables_to_save = []
            for p in pages:
                for t in p.get("tables", []):
                    tables_to_save.append(
                        {
                            "page_number": p.get("page_number", 1),
                            "markdown": t.get("markdown", ""),
                            "json": t.get("json_data", {}),
                            "bbox": t.get("bbox"),
                        }
                    )
            if tables_to_save:
                database.save_document_tables(doc_id, tables_to_save)

            # Chunk text
            chunks = chunk_text(
                pages,
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP,
                document_name=filename,
                document_id=doc_id,
            )

            if chunks:
                all_chunks.extend(chunks)
                processed_files += 1
                saved_file_names.append(filename)
                doc_metadata.append(
                    {
                        "filename": filename,
                        "file_size_bytes": total_read,
                        "num_pages": len(pages),
                        "document_id": doc_id,
                    }
                )
                database.update_document_status(doc_id, status="ready", page_count=len(pages))
            else:
                failed_files.append(f"{filename} (chunking produced no text)")
                safe_delete_file(save_path)
                database.update_document_status(doc_id, status="failed", error="Chunking produced no text")

        except Exception as e:
            logger.error(f"Error processing {filename}: {e}", exc_info=True)
            failed_files.append(f"{filename}: {str(e)}")

    if not all_chunks:
        error_msg = "No files could be processed. "
        if failed_files:
            error_msg += "; ".join(failed_files)
        raise HTTPException(status_code=400, detail=error_msg)

    # Compute Fastembed embeddings and persist
    try:
        reg = get_model_registry()
        chunk_texts = [c["text"] for c in all_chunks]
        embeddings = list(reg.embedding_model.embed(chunk_texts))

        suggestions = generate_suggested_questions(saved_file_names[0], all_chunks)
        database.save_session(sid, saved_file_names, suggested_questions=suggestions)
        database.save_chunks(sid, all_chunks, embeddings)

    except Exception as e:
        logger.error(f"Failed to generate embeddings or persist session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to compute embeddings for documents.")

    return UploadResponse(
        session_id=sid,
        chunk_count=len(all_chunks),
        processed_files=processed_files,
        failed_files=failed_files,
        message=f"Successfully indexed {processed_files} document(s).",
        suggested_questions=suggestions,
        document_metadata=doc_metadata,
    )


# ----------------------------------------------------------------------
# Serving and Session Endpoints
# ----------------------------------------------------------------------


@router.get("/api/documents/{session_id}/pdf")
@router.get("/documents/{session_id}/pdf")
async def get_document_pdf(session_id: str, document_name: str):
    """Serve the raw or converted PDF file for in-browser PDF.js rendering."""
    settings = get_settings()
    file_unique_id = f"{session_id}_{document_name}"
    target = (settings.UPLOAD_DIR / file_unique_id).resolve()

    if not target.exists() or not target.is_file():
        target_direct = (settings.UPLOAD_DIR / document_name).resolve()
        if target_direct.exists() and target_direct.is_file():
            target = target_direct
        else:
            raise HTTPException(status_code=404, detail="Document file not found.")

    # If the file is an image or Word document, serve the converted PDF if present
    if target.suffix.lower() in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".docx", ".doc"):
        converted_pdf = target.parent / f"{target.stem}_converted.pdf"
        if converted_pdf.exists():
            target = converted_pdf
        elif target.suffix.lower() in (".docx", ".doc"):
            raise HTTPException(
                status_code=404, detail="Converted PDF preview is unavailable for this Word document; use text viewer."
            )

    return FileResponse(
        path=str(target),
        media_type="application/pdf" if target.suffix.lower() == ".pdf" else "text/plain",
        filename=document_name,
    )


@router.get("/api/documents/{session_id}/text")
@router.get("/documents/{session_id}/text")
async def get_document_text_pages(session_id: str, document_name: str):
    """Serve extracted page text for fallback text viewer when PDF rendering is unavailable."""
    from models_db import Document as DbDocument

    settings = get_settings()

    pages_out: List[Dict[str, Any]] = []
    with database.get_db() as db:
        doc = (
            db.query(DbDocument)
            .filter(DbDocument.session_id == session_id, DbDocument.filename == document_name)
            .first()
        )
        if not doc:
            doc = db.query(DbDocument).filter(DbDocument.filename == document_name).first()
        if doc:
            pages_out = database.get_document_pages(doc.id)

    if not pages_out:
        file_unique_id = f"{session_id}_{document_name}"
        target = (settings.UPLOAD_DIR / file_unique_id).resolve()
        if not target.exists():
            target = (settings.UPLOAD_DIR / document_name).resolve()
        if target.exists() and target.is_file():
            pages_out = extract_text_from_file(target, filename=document_name)

    if not pages_out:
        raise HTTPException(status_code=404, detail="Document text pages not found.")

    return {
        "session_id": session_id,
        "document_name": document_name,
        "viewer_mode": "text",
        "pages": [
            {
                "page_number": p.get("page_number") or p.get("page", 1),
                "text": p.get("text", ""),
            }
            for p in pages_out
        ],
    }


@router.get("/api/sessions/{session_id}", response_model=SessionInfo)
async def get_session_info(session_id: str):
    """Retrieve session details and document list."""
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")

    return SessionInfo(
        session_id=session["session_id"],
        created_at=session["created_at"],
        file_names=session["file_names"],
        chunk_count=session["chunk_count"],
        suggested_questions=session.get("suggested_questions", []),
    )


@router.get("/api/sessions/{session_id}/suggestions")
async def get_session_suggestions_endpoint(session_id: str):
    """Retrieve suggested questions for the active session."""
    session = database.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"suggestions": session.get("suggested_questions", [])}


@router.delete("/api/sessions/{session_id}")
async def delete_session_endpoint(session_id: str):
    """Delete an active session and purge its files and DB records."""
    settings = get_settings()
    session = database.get_session(session_id)
    if session:
        for fname in session["file_names"]:
            safe_delete_file(settings.UPLOAD_DIR / f"{session_id}_{fname}")
    database.delete_session(session_id)
    return {"status": "ok", "message": "Session deleted."}


@router.delete("/api/sessions/{session_id}/documents/{document_name}")
async def delete_document_endpoint(session_id: str, document_name: str):
    """Delete a single document from session."""
    settings = get_settings()
    safe_delete_file(settings.UPLOAD_DIR / f"{session_id}_{document_name}")
    database.delete_document(session_id, document_name)
    return {"status": "ok", "removed_document": document_name}
