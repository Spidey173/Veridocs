"""
Document ingestion, PDF streaming, metadata inspection, and session deletion endpoints.
"""

import json
import time
import uuid
import logging
from pathlib import Path
from typing import List, Optional
from collections import defaultdict
import numpy as np
from fastapi import APIRouter, HTTPException, Request, Depends, UploadFile, File, Form, Query, BackgroundTasks
from fastapi.responses import FileResponse

from config import get_settings, get_model_registry
from auth import get_current_user, UserContext
from models import UploadResponse
from pdf_processor import extract_text_from_file, chunk_text
import database
from llm_service import FreeLLMService
from insights_engine import generate_document_insights
from rate_limiter import enforce_rate_limit
from conversation import get_conversation_manager
from tasks import dispatch_insights_job
from session_store import (
    sessions,
    _sessions_lock,
    _get_session,
    _safe_delete_file,
    _cleanup_session,
    persist_session_snapshot,
    save_upload_file_stream,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])


@router.post("/api/upload", response_model=UploadResponse)
async def upload_documents(
    request: Request,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Form(None),
    current_user: UserContext = Depends(get_current_user)
):
    """Upload and process document files (PDF, DOCX, TXT) with atomic table preservation."""
    settings = get_settings()
    enforce_rate_limit(request, "upload", max_requests=settings.UPLOAD_RATE_LIMIT, window_seconds=60)
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    all_chunks = []
    processed_files = 0
    failed_files = []
    doc_metadata = []
    saved_paths = []
    file_names = []

    for file in files:
        filename = file.filename or "unknown"
        ext = Path(filename).suffix.lower()

        # Validate extension
        if ext not in settings.ALLOWED_EXTENSIONS:
            failed_files.append(f"{filename} (unsupported type: {ext})")
            continue

        try:
            # Stream write directly to disk in 1MB chunks with O(1) memory
            max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
            session_file_id = str(uuid.uuid4())
            save_path, total_read, file_too_large = await save_upload_file_stream(
                file=file,
                max_bytes=max_bytes,
                session_file_id=session_file_id,
                ext=ext,
            )

            if file_too_large:
                failed_files.append(f"{filename} (exceeds {settings.MAX_FILE_SIZE_MB}MB limit)")
                _safe_delete_file(save_path)
                continue

            logger.info(f"Processing upload for user {current_user.user_id}: {filename} ({total_read} bytes)")

            # Stream extract text from disk to avoid in-memory byte duplication
            pages = extract_text_from_file(save_path, filename=filename)

            if not pages:
                failed_files.append(f"{filename} (no extractable text)")
                _safe_delete_file(save_path)
                continue

            metadata = {
                "filename": filename,
                "file_size_bytes": total_read,
                "num_pages": len(pages),
                "is_encrypted": False,
                "metadata": {}
            }

            # Split text into chunks
            chunks = chunk_text(
                pages,
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP,
                document_name=filename
            )

            if chunks:
                for chunk in chunks:
                    chunk["source_file"] = filename

                all_chunks.extend(chunks)
                processed_files += 1
                doc_metadata.append(metadata)
                saved_paths.append(str(save_path))
                file_names.append(filename)
                logger.info(f"Processed {filename}: {len(chunks)} chunks")
            else:
                failed_files.append(f"{filename} (chunking failed)")
                _safe_delete_file(save_path)

        except ValueError as e:
            failed_files.append(f"{filename}: {str(e)}")
            logger.warning(f"ValueError processing {filename}: {str(e)}")
            if 'save_path' in locals() and save_path:
                _safe_delete_file(save_path)
        except Exception as e:
            failed_files.append(f"{filename}: Unexpected error")
            logger.error(f"Error processing {filename}: {str(e)}", exc_info=True)
            if 'save_path' in locals() and save_path:
                _safe_delete_file(save_path)

    if not all_chunks:
        error_msg = "No files could be processed. "
        if failed_files:
            error_msg += f"Issues: {'; '.join(failed_files[:3])}"
        raise HTTPException(status_code=400, detail=error_msg)

    try:
        # Generate embeddings only for newly uploaded chunks to keep incremental ingestion O(k)
        new_chunks = list(all_chunks)
        reg = get_model_registry()
        new_chunk_texts = [c["text"] for c in new_chunks]
        new_embeddings = reg.embedding_model.encode(
            new_chunk_texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            batch_size=settings.EMBEDDING_BATCH_SIZE
        )

        existing_insights = {}
        if session_id:
            existing_session = await _get_session(session_id, current_user)
            saved_paths = existing_session.get("file_paths", []) + saved_paths
            file_names = existing_session.get("file_names", []) + file_names
            doc_metadata = existing_session.get("metadata", []) + doc_metadata
            existing_chunks = existing_session.get("chunks", [])
            existing_embeddings = existing_session.get("embeddings")
            existing_insights = existing_session.get("insights", {})

            all_chunks = existing_chunks + new_chunks
            if (
                isinstance(existing_embeddings, np.ndarray)
                and len(existing_embeddings) == len(existing_chunks)
            ):
                embeddings = np.vstack([existing_embeddings, new_embeddings])
            else:
                embeddings = reg.embedding_model.encode(
                    [c["text"] for c in all_chunks],
                    convert_to_numpy=True,
                    show_progress_bar=False,
                    batch_size=settings.EMBEDDING_BATCH_SIZE
                )
        else:
            all_chunks = new_chunks
            embeddings = new_embeddings

        with _sessions_lock:
            if not session_id or session_id not in sessions:
                session_id = str(uuid.uuid4())

            chunks_by_file = defaultdict(list)
            for chunk in all_chunks:
                fn = chunk.get("source_file", "unknown")
                chunks_by_file[fn].append(chunk)

            sessions[session_id] = {
                "chunks": all_chunks,
                "embeddings": embeddings,
                "file_paths": saved_paths,
                "file_names": file_names,
                "metadata": doc_metadata,
                "insights": existing_insights,
                "created_at": time.time(),
                "owner_id": current_user.user_id,
            }

            if len(sessions) > settings.MAX_SESSIONS:
                oldest_key = min(sessions, key=lambda k: sessions[k]["created_at"])
                _cleanup_session(oldest_key)

        # Save session to PostgreSQL if pool is ready
        if database.is_database_ready():
            try:
                saved_sess = await database.save_session(
                    session_id=session_id,
                    owner_id=current_user.user_id,
                    file_names=file_names,
                    file_paths=saved_paths,
                    metadata=doc_metadata,
                    insights=existing_insights,
                    created_at=time.time()
                )
                if not saved_sess and settings.ENVIRONMENT == "production":
                    raise HTTPException(
                        status_code=503,
                        detail="Failed to persist session to database in production mode. Aborting to prevent worker divergence."
                    )
                saved_chk = await database.save_chunks(session_id, new_chunks, new_embeddings)
                if not saved_chk and settings.ENVIRONMENT == "production":
                    raise HTTPException(
                        status_code=503,
                        detail="Failed to persist document chunks to database in production mode. Aborting to prevent worker divergence."
                    )
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to persist session {session_id} to PostgreSQL: {e}")
                if settings.ENVIRONMENT == "production":
                    raise HTTPException(
                        status_code=503,
                        detail=f"Database persistence failure in production: {str(e)}"
                    )
        elif settings.ENVIRONMENT == "production":
            raise HTTPException(
                status_code=503,
                detail="PostgreSQL database is required for uploads in production mode."
            )

        # Synchronously persist complete session snapshot (metadata, chunks, embeddings) to disk
        persist_session_snapshot(
            session_id=session_id,
            saved_paths=saved_paths,
            file_names=file_names,
            doc_metadata=doc_metadata,
            owner_id=current_user.user_id,
            chunks=all_chunks,
            embeddings=embeddings,
            insights=existing_insights,
        )

        # Generate summary and questions via asynchronous worker queue or background tasks
        dispatch_insights_job(
            session_id=session_id,
            chunks_by_file=dict(chunks_by_file),
            doc_metadata=doc_metadata,
            provider=settings.LLM_PROVIDER,
            background_tasks=background_tasks
        )

        message = f"Successfully processed {processed_files} file(s) with {len(all_chunks)} text chunks"
        if failed_files:
            message += f". {len(failed_files)} file(s) skipped."

        logger.info(f"Created session {session_id}: {message}")

        return UploadResponse(
            session_id=session_id,
            chunk_count=len(all_chunks),
            processed_files=processed_files,
            failed_files=failed_files,
            message=message,
            document_metadata=doc_metadata
        )

    except Exception as e:
        logger.error(f"Error creating vector store: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error indexing documents: {str(e)}")


@router.get("/api/documents/{session_id}/pdf")
async def get_document_pdf(
    session_id: str,
    file_index: int = Query(0, ge=0),
    document_name: Optional[str] = None,
    current_user: UserContext = Depends(get_current_user)
):
    """Serve the uploaded PDF for the viewer with defense-in-depth path validation."""
    settings = get_settings()
    session_data = await _get_session(session_id, current_user)
    file_paths = session_data.get("file_paths", [])
    file_names = session_data.get("file_names", [])

    if document_name:
        try:
            file_index = file_names.index(document_name)
        except ValueError:
            raise HTTPException(status_code=404, detail="Document file not found in session")

    if not file_paths or file_index < 0 or file_index >= len(file_paths):
        raise HTTPException(status_code=404, detail="Document file not found")

    file_path = Path(file_paths[file_index]).resolve()
    upload_root = Path(settings.UPLOAD_DIR).resolve()
    if not file_path.is_relative_to(upload_root) or not file_path.exists():
        raise HTTPException(status_code=404, detail="Document file not found on disk")

    return FileResponse(
        path=str(file_path),
        media_type="application/pdf",
        filename=file_names[file_index] if file_index < len(file_names) else "document.pdf",
        headers={
            "Cache-Control": "private, no-cache, no-store, must-revalidate",
            "Accept-Ranges": "bytes",
        }
    )


@router.get("/api/documents/{session_id}/insights")
async def get_document_insights(
    session_id: str,
    document_name: Optional[str] = None,
    current_user: UserContext = Depends(get_current_user)
):
    """Get document summary, questions, and financial/legal entities."""
    settings = get_settings()
    session_data = await _get_session(session_id, current_user)
    insights_dict = session_data.get("insights", {})

    if not isinstance(insights_dict, dict):
        insights_dict = {}

    if not document_name:
        file_names = session_data.get("file_names", [])
        if file_names:
            document_name = file_names[0]

    if not document_name:
        raise HTTPException(status_code=400, detail="No active document in session")

    if document_name in insights_dict:
        insights = insights_dict[document_name]
        return insights.model_dump() if hasattr(insights, 'model_dump') else insights.dict()

    try:
        chunks = [c for c in session_data.get("chunks", []) if c.get("source_file") == document_name]
        try:
            llm = FreeLLMService(provider=settings.LLM_PROVIDER)
        except Exception:
            llm = None
        matching_meta = next((m for m in session_data.get("metadata", []) if m.get("filename") == document_name), {})
        total_pages = matching_meta.get("num_pages", 0)

        insights = generate_document_insights(
            session_id=session_id,
            chunks=chunks,
            llm_service=llm,
            total_pages=total_pages
        )
        insights_dict[document_name] = insights
        session_data["insights"] = insights_dict
        return insights.model_dump() if hasattr(insights, 'model_dump') else insights.dict()
    except Exception as e:
        logger.error(f"Insights generation failed for {document_name}: {e}")
        # Always return a valid fallback DocumentInsights structure rather than crashing with 500
        fallback = generate_document_insights(
            session_id=session_id,
            chunks=[c for c in session_data.get("chunks", []) if c.get("source_file") == document_name],
            llm_service=None,
            total_pages=0
        )
        return fallback.model_dump() if hasattr(fallback, 'model_dump') else fallback.dict()


@router.get("/api/sessions/{session_id}")
async def get_session_info(
    session_id: str,
    current_user: UserContext = Depends(get_current_user)
):
    """Get session metadata and document list."""
    session_data = await _get_session(session_id, current_user)
    return {
        "session_id": session_id,
        "file_names": session_data.get("file_names", []),
        "chunk_count": len(session_data.get("chunks", [])),
        "metadata": session_data.get("metadata", []),
        "created_at": session_data.get("created_at"),
        "has_insights": session_data.get("insights") is not None,
    }


@router.delete("/api/sessions/{session_id}")
async def delete_session(
    session_id: str,
    current_user: UserContext = Depends(get_current_user)
):
    """Delete a session, its files, and conversation history."""
    settings = get_settings()
    session_data = await _get_session(session_id, current_user)
    deleted_files = 0

    for path_str in session_data.get("file_paths", []):
        if _safe_delete_file(path_str):
            deleted_files += 1

    session_dir = Path(settings.UPLOAD_DIR) / "sessions" / session_id
    _safe_delete_file(session_dir)

    conversation = get_conversation_manager()
    conversation.clear_history(session_id)

    with _sessions_lock:
        sessions.pop(session_id, None)

    if database.is_database_configured():
        try:
            await database.delete_session(session_id)
        except Exception as e:
            logger.error(f"Error deleting session {session_id} from database: {e}")

    logger.info(f"User {current_user.user_id} deleted session {session_id}")
    return {
        "status": "success",
        "session_id": session_id,
        "deleted_files_count": deleted_files,
        "message": "Session permanently deleted."
    }


@router.delete("/api/sessions/{session_id}/documents/{document_name}")
async def delete_document_from_session(
    session_id: str,
    document_name: str,
    current_user: UserContext = Depends(get_current_user)
):
    """Delete a single document from an active session and update the vector index."""
    settings = get_settings()
    session_data = await _get_session(session_id, current_user)
    file_names = session_data.get("file_names", [])
    file_paths = session_data.get("file_paths", [])

    if document_name not in file_names:
        raise HTTPException(status_code=404, detail=f"Document '{document_name}' not found in session.")

    idx = file_names.index(document_name)
    target_path = file_paths[idx] if idx < len(file_paths) else None
    if target_path:
        _safe_delete_file(target_path)

    file_names.pop(idx)
    if idx < len(file_paths):
        file_paths.pop(idx)

    old_chunks = session_data.get("chunks", [])
    remaining_chunks = [c for c in old_chunks if c.get("source_file") != document_name]
    session_data["chunks"] = remaining_chunks
    session_data["file_names"] = file_names
    session_data["file_paths"] = file_paths
    session_data.get("insights", {}).pop(document_name, None)

    if "embeddings" in session_data and session_data["embeddings"] is not None:
        kept_indices = [i for i, c in enumerate(old_chunks) if c.get("source_file") != document_name]
        if kept_indices:
            session_data["embeddings"] = session_data["embeddings"][kept_indices]
        else:
            session_data["embeddings"] = None

    session_dir = Path(settings.UPLOAD_DIR) / "sessions" / session_id
    if session_dir.exists():
        raw_insights = session_data.get("insights", {})
        serializable_insights = {
            k: (v.model_dump() if hasattr(v, "model_dump") else (v.dict() if hasattr(v, "dict") else v))
            for k, v in raw_insights.items()
        }
        session_meta = {
            "session_id": session_id,
            "file_paths": file_paths,
            "file_names": file_names,
            "metadata": session_data.get("metadata", []),
            "insights": serializable_insights,
            "owner_id": current_user.user_id,
        }
        with open(session_dir / "session.json", "w", encoding="utf-8") as f:
            json.dump(session_meta, f, indent=2, default=str)

    if database.is_database_configured():
        try:
            await database.delete_document_from_session(session_id, document_name)
            await database.save_session(
                session_id=session_id,
                owner_id=current_user.user_id,
                file_names=file_names,
                file_paths=file_paths,
                metadata=session_data.get("metadata", []),
                insights=session_data.get("insights", {}),
            )
        except Exception as e:
            logger.error(f"Error updating PostgreSQL after document deletion: {e}")

    return {
        "status": "success",
        "session_id": session_id,
        "removed_document": document_name,
        "remaining_documents": file_names,
        "remaining_chunks": len(remaining_chunks)
    }
