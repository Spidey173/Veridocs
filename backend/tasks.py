"""
Asynchronous background document processing tasks for Veridocs.
Handles heavy OCR, multi-hundred-page SEC 10-K filings, and embedding indexing.
Executes out-of-process via Celery workers or in background threads.
"""

import time
import uuid
import json
import logging
import threading
from pathlib import Path
from typing import List, Dict, Optional, Any
from fastapi import BackgroundTasks

from celery_app import celery_app, is_celery_broker_reachable
from job_tracker import get_job_tracker
from config import get_settings
from pdf_processor import extract_text_from_file, chunk_text
from vector_store import VectorStore

logger = logging.getLogger(__name__)
settings = get_settings()


@celery_app.task(name="veridocs.process_document_job")
def process_document_job(
    job_id: str,
    file_paths: List[str],
    file_names: List[str],
    owner_id: str,
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Celery background worker task for heavy document processing.
    Extracts text/OCR page-by-page, tracks progress, chunks structured tables,
    and builds the FAISS + BM25 hybrid vector store.
    """
    tracker = get_job_tracker()
    tracker.update_progress(
        job_id,
        percent=5.0,
        stage="Initializing background worker & loading files..."
    )

    all_chunks = []
    doc_metadata = []
    processed_count = 0
    total_scanned_count = 0
    total_pages_count = 0

    try:
        total_files = len(file_paths)
        for idx, (path_str, filename) in enumerate(zip(file_paths, file_names)):
            file_path = Path(path_str)
            if not file_path.exists():
                logger.warning(f"File not found during task execution: {path_str}")
                continue

            file_bytes = file_path.read_bytes()
            base_pct = 10.0 + (float(idx) / max(total_files, 1)) * 60.0

            def _on_page_progress(cur_page: int, total_pages: int, message: str):
                # Scale file progress across the allocated 60% window
                step_pct = base_pct + (float(cur_page) / max(total_pages, 1)) * (60.0 / total_files)
                tracker.update_progress(
                    job_id,
                    percent=round(step_pct, 1),
                    stage=f"[{filename}] {message}",
                    current_page=cur_page,
                    total_pages=total_pages,
                )

            tracker.update_progress(
                job_id,
                percent=round(base_pct, 1),
                stage=f"Processing {filename} (page analysis & text extraction)..."
            )

            # Extract pages with real-time progress callbacks for scans & SEC 10-K filings
            pages = extract_text_from_file(
                file_bytes,
                filename,
                progress_callback=_on_page_progress
            )

            if not pages:
                continue

            num_pages = len(pages)
            total_pages_count += num_pages
            scanned_pages = sum(1 for p in pages if p.get("is_scanned", False))
            total_scanned_count += scanned_pages

            metadata = {
                "filename": filename,
                "file_size_bytes": len(file_bytes),
                "num_pages": num_pages,
                "is_scanned": scanned_pages > 0,
                "scanned_pages_count": scanned_pages,
                "metadata": {}
            }
            doc_metadata.append(metadata)

            # Chunk document preserving tables and injecting hierarchical breadcrumbs
            tracker.update_progress(
                job_id,
                stage=f"Detecting tables & generating chunks for {filename}..."
            )
            chunks = chunk_text(
                pages,
                chunk_size=settings.CHUNK_SIZE,
                chunk_overlap=settings.CHUNK_OVERLAP,
                document_name=filename
            )

            for chunk in chunks:
                chunk["source_file"] = filename
            all_chunks.extend(chunks)
            processed_count += 1

        if not all_chunks:
            error_msg = "No readable text or content could be extracted from uploaded files."
            tracker.fail_job(job_id, error_msg)
            raise ValueError(error_msg)

        # Build Vector Store
        tracker.update_progress(
            job_id,
            percent=75.0,
            stage="Generating neural FastEmbed vectors & building FAISS index...",
            chunks_created=len(all_chunks),
            total_pages=total_pages_count,
            scanned_pages=total_scanned_count
        )

        vector_store = VectorStore()
        vector_store.add_documents(all_chunks)

        if not session_id:
            session_id = str(uuid.uuid4())

        # Persist session to disk storage
        tracker.update_progress(
            job_id,
            percent=90.0,
            stage="Persisting session and vector store to disk storage..."
        )

        session_dir = Path(settings.UPLOAD_DIR) / "sessions" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        vector_store.save_to_disk(session_dir)

        session_meta = {
            "session_id": session_id,
            "file_paths": file_paths,
            "file_names": file_names,
            "metadata": doc_metadata,
            "created_at": time.time(),
            "owner_id": owner_id,
            "total_pages": total_pages_count,
            "scanned_pages": total_scanned_count,
            "is_async_job": True,
            "job_id": job_id
        }
        with open(session_dir / "session.json", "w", encoding="utf-8") as f:
            json.dump(session_meta, f, indent=2)

        # Update in-memory session if main server is running in same process
        try:
            import main
            main.sessions[session_id] = {
                "vector_store": vector_store,
                "chunks": all_chunks,
                "file_paths": file_paths,
                "file_names": file_names,
                "metadata": doc_metadata,
                "insights": {},
                "created_at": time.time(),
                "owner_id": owner_id,
            }
        except Exception:
            pass

        result_summary = {
            "session_id": session_id,
            "chunk_count": len(all_chunks),
            "processed_files": processed_count,
            "total_pages": total_pages_count,
            "scanned_pages": total_scanned_count,
            "file_names": file_names,
        }

        tracker.complete_job(
            job_id,
            session_id=session_id,
            result_summary=result_summary
        )
        logger.info(f"Async job {job_id} successfully completed. Session: {session_id}")
        return result_summary

    except Exception as e:
        logger.error(f"Async job {job_id} failed: {e}", exc_info=True)
        tracker.fail_job(job_id, str(e))
        raise


def dispatch_document_job(
    job_id: str,
    file_paths: List[str],
    file_names: List[str],
    owner_id: str,
    session_id: Optional[str] = None,
    background_tasks: Optional[BackgroundTasks] = None
):
    """
    Route job execution dynamically:
    1. If Celery broker is reachable or eager mode is active, dispatch to Celery.
    2. Otherwise, fall back to FastAPI BackgroundTasks or a daemon thread.
    """
    if is_celery_broker_reachable() or settings.CELERY_TASK_ALWAYS_EAGER:
        logger.info(f"Dispatching job {job_id} to Celery worker queue...")
        try:
            process_document_job.delay(
                job_id=job_id,
                file_paths=file_paths,
                file_names=file_names,
                owner_id=owner_id,
                session_id=session_id
            )
            return
        except Exception as e:
            logger.warning(f"Celery dispatch failed ({e}), falling back to background runner")

    # Local fallback execution
    logger.info(f"Executing job {job_id} via local background thread runner...")
    if background_tasks:
        background_tasks.add_task(
            process_document_job,
            job_id=job_id,
            file_paths=file_paths,
            file_names=file_names,
            owner_id=owner_id,
            session_id=session_id
        )
    else:
        thread = threading.Thread(
            target=process_document_job,
            args=(job_id, file_paths, file_names, owner_id, session_id),
            daemon=True
        )
        thread.start()
