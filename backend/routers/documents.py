"""
Document management and ingestion routes for Veridocs.
Handles real file uploads, text extraction, chunking, Fastembed vector embeddings, and PDF serving.
"""

import uuid
import logging
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse

from config import get_settings, get_model_registry
from models import UploadResponse, SessionInfo
import database
from pdf_processor import extract_text_from_file, chunk_text, get_document_metadata
from session_store import save_upload_file_stream, safe_delete_file

logger = logging.getLogger(__name__)
router = APIRouter(tags=["documents"])


@router.post("/api/upload", response_model=UploadResponse)
async def upload_documents(
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Form(None),
):
    """Upload documents (PDF, TXT), extract text, compute Fastembed embeddings, and persist to SQLite."""
    settings = get_settings()
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

        # Persist session and chunks in SQLite
        database.save_session(sid, saved_file_names)
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
    )


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
