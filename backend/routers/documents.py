"""
Document management and ingestion routes for Veridocs.
Handles real file uploads, text extraction, chunking, Fastembed vector embeddings, and PDF serving.
"""

import uuid
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import FileResponse

from config import get_settings, get_model_registry
from models import UploadResponse, SessionInfo
import database
from pdf_processor import extract_text_from_file, chunk_text, get_document_metadata
from session_store import save_upload_file_stream, safe_delete_file
from rate_limiter import check_rate_limit

logger = logging.getLogger(__name__)
router = APIRouter(tags=["documents"])


def generate_suggested_questions(document_name: str, chunks: List[dict]) -> List[str]:
    """Generate 3 relevant suggested questions based on the document type and content."""
    # 1. Sample agreement questions only show for sample agreement
    if "sample_agreement" in document_name.lower():
        return [
            "What are the payment terms in this agreement?",
            "What is the limitation of liability and uptime SLA?",
            "What data protection and encryption standards are required?",
        ]

    # 2. Dynamic generation via LLM if configured
    settings = get_settings()
    if settings.is_llm_configured() and chunks:
        try:
            from llm_service import get_llm_service
            llm = get_llm_service()
            if llm.client:
                # Use top chunk excerpts for dynamic generation
                sample_text = "\n\n".join([c["text"][:350] for c in chunks[:3]])
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
                    l.strip().lstrip("0123456789.-*•) ")
                    for l in raw.strip().split("\n")
                    if l.strip() and "?" in l
                ]
                if len(lines) >= 3:
                    return lines[:3]
                elif lines:
                    return lines
        except Exception as e:
            logger.warning(f"Could not generate dynamic suggestions via LLM: {e}")

    # 3. Clean generic fallback for any other document (e.g. resume, policy, report)
    return [
        "Summarize this document",
        "What are the key points?",
        "What are the main requirements and dates?",
    ]


@router.post("/api/upload", response_model=UploadResponse)
async def upload_documents(
    request: Request,
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Form(None),
):
    """Upload documents (PDF, TXT), extract text, compute Fastembed embeddings, and persist to SQLite."""
    settings = get_settings()

    # Abuse protection: per-IP rate limiting
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
            failed_files.append(f"{filename} (unsupported format; use .pdf or .txt)")
            continue

        try:
            max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
            # Keep original filename prefixed with session_id to allow serving
            file_unique_id = f"{sid}_{filename}"
            save_path, total_read, file_too_large = await save_upload_file_stream(
                file=file,
                max_bytes=max_bytes,
                file_id=file_unique_id,
                ext="",  # ext already in filename
            )

            if file_too_large:
                failed_files.append(f"{filename} (exceeds {settings.MAX_FILE_SIZE_MB}MB limit)")
                safe_delete_file(save_path)
                continue

            # Extract pages from the saved file
            pages = extract_text_from_file(save_path, filename=filename)
            if not pages:
                failed_files.append(f"{filename} (no extractable text)")
                safe_delete_file(save_path)
                continue

            if len(pages) > settings.MAX_PDF_PAGES:
                failed_files.append(f"{filename} (exceeds {settings.MAX_PDF_PAGES} page limit; has {len(pages)} pages)")
                safe_delete_file(save_path)
                continue

            # Chunk text
            chunks = chunk_text(
                pages,
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP,
                document_name=filename,
            )

            if chunks:
                all_chunks.extend(chunks)
                processed_files += 1
                saved_file_names.append(filename)
                doc_metadata.append({
                    "filename": filename,
                    "file_size_bytes": total_read,
                    "num_pages": len(pages),
                })
            else:
                failed_files.append(f"{filename} (chunking produced no text)")
                safe_delete_file(save_path)

        except Exception as e:
            logger.error(f"Error processing {filename}: {e}", exc_info=True)
            failed_files.append(f"{filename}: {str(e)}")

    if not all_chunks:
        error_msg = "No files could be processed. "
        if failed_files:
            error_msg += "; ".join(failed_files)
        raise HTTPException(status_code=400, detail=error_msg)

    # Compute embeddings with Fastembed
    try:
        reg = get_model_registry()
        chunk_texts = [c["text"] for c in all_chunks]
        embeddings = list(reg.embedding_model.embed(chunk_texts))

        # Persist session and chunks in SQLite with dynamic suggestions
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


@router.get("/api/documents/{session_id}/pdf")
async def get_document_pdf(session_id: str, document_name: str):
    """Serve the raw PDF file for in-browser PDF.js rendering."""
    settings = get_settings()
    # Check matching file on disk
    file_unique_id = f"{session_id}_{document_name}"
    target = (settings.UPLOAD_DIR / file_unique_id).resolve()

    if not target.exists() or not target.is_file():
        # Fallback check without session prefix
        target_direct = (settings.UPLOAD_DIR / document_name).resolve()
        if target_direct.exists() and target_direct.is_file():
            target = target_direct
        else:
            raise HTTPException(status_code=404, detail="Document file not found.")

    return FileResponse(
        path=str(target),
        media_type="application/pdf" if target.suffix.lower() == ".pdf" else "text/plain",
        filename=document_name,
    )


@router.get("/api/sessions/{session_id}", response_model=SessionInfo)
async def get_session_info(session_id: str):
    """Retrieve session details and document list from SQLite."""
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
    """Delete an active session and purge its files and SQLite records."""
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
