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
from config import get_settings, get_model_registry
from pdf_processor import extract_text_from_file, chunk_text
import database

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
    """Background task to extract text, create chunks, and build vector index."""
    tracker = get_job_tracker()
    tracker.update_progress(
        job_id,
        percent=5.0,
        stage="Loading files..."
    )

    all_chunks = []
    doc_metadata = []
    valid_file_paths = []
    valid_file_names = []
    processed_count = 0
    total_scanned_count = 0
    total_pages_count = 0

    try:
        total_files = len(file_paths)
        for idx, (path_str, filename) in enumerate(zip(file_paths, file_names)):
            file_path = Path(path_str)
            if not file_path.exists():
                logger.warning(f"File not found: {path_str}")
                continue

            base_pct = 10.0 + (float(idx) / max(total_files, 1)) * 60.0

            def _on_page_progress(cur_page: int, total_pages: int, message: str):
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
                stage=f"Extracting text from {filename}..."
            )

            # Stream extract directly from disk file to prevent high memory usage on large documents
            pages = extract_text_from_file(
                file_path,
                filename=filename,
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
                "file_size_bytes": file_path.stat().st_size,
                "num_pages": num_pages,
                "is_scanned": scanned_pages > 0,
                "scanned_pages_count": scanned_pages,
                "metadata": {}
            }
            doc_metadata.append(metadata)

            tracker.update_progress(
                job_id,
                stage=f"Generating chunks for {filename}..."
            )
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
                processed_count += 1
                valid_file_paths.append(str(file_path))
                valid_file_names.append(filename)

        if not all_chunks:
            error_msg = "No readable text could be extracted from uploaded files."
            tracker.fail_job(job_id, error_msg)
            raise ValueError(error_msg)

        # Build vector index
        tracker.update_progress(
            job_id,
            percent=75.0,
            stage="Generating vector embeddings...",
            chunks_created=len(all_chunks),
            total_pages=total_pages_count,
            scanned_pages=total_scanned_count
        )

        reg = get_model_registry()
        chunk_texts = [c["text"] for c in all_chunks]
        embeddings = reg.embedding_model.encode(
            chunk_texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            batch_size=settings.EMBEDDING_BATCH_SIZE
        )

        if not session_id:
            session_id = str(uuid.uuid4())

        tracker.update_progress(
            job_id,
            percent=90.0,
            stage="Saving session to PostgreSQL..."
        )

        # Persist session and chunks directly to PostgreSQL
        try:
            import asyncio
            if database.is_database_configured():
                async def _save_to_db():
                    await database.init_db()
                    await database.save_session(
                        session_id=session_id,
                        owner_id=owner_id,
                        file_names=valid_file_names,
                        file_paths=valid_file_paths,
                        metadata=doc_metadata,
                        insights={},
                        created_at=time.time()
                    )
                    await database.save_chunks(session_id, all_chunks, embeddings)

                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.ensure_future(_save_to_db())
                    else:
                        loop.run_until_complete(_save_to_db())
                except RuntimeError:
                    asyncio.run(_save_to_db())
        except Exception as e:
            logger.debug(f"Could not persist async job session to database: {e}")

        # Update session cache
        try:
            import main
            main.sessions[session_id] = {
                "chunks": all_chunks,
                "file_paths": valid_file_paths,
                "file_names": valid_file_names,
                "metadata": doc_metadata,
                "insights": {},
                "created_at": time.time(),
                "owner_id": owner_id,
            }
        except Exception as e:
            logger.debug(f"Failed to populate in-process session cache from background task: {e}")

        result_summary = {
            "session_id": session_id,
            "chunk_count": len(all_chunks),
            "processed_files": processed_count,
            "total_pages": total_pages_count,
            "scanned_pages": total_scanned_count,
            "file_names": valid_file_names,
        }

        tracker.complete_job(
            job_id,
            session_id=session_id,
            result_summary=result_summary
        )
        logger.info(f"Job {job_id} completed for session {session_id}")
        return result_summary

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}", exc_info=True)
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
    """Run document processing via Celery or local background thread."""
    if is_celery_broker_reachable() or settings.CELERY_TASK_ALWAYS_EAGER:
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
            logger.warning(f"Celery dispatch failed ({e}), falling back to thread")

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
