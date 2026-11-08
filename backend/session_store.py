"""
Central Session Store and Data Lifecycle Manager for Veridocs.
Manages in-memory session caches, disk snapshots, retention policies, and parallel document insights.
"""

import json
import time
import shutil
import asyncio
import logging
import threading
import concurrent.futures
from pathlib import Path
from typing import Dict, List, Optional, Union, Any, Tuple
import numpy as np
from fastapi import HTTPException, UploadFile

from config import get_settings
from auth import UserContext, assert_resource_ownership
import database
from llm_service import FreeLLMService
from insights_engine import generate_document_insights
from conversation import get_conversation_manager

logger = logging.getLogger(__name__)

# Global thread-safe session registry
sessions: Dict[str, Dict[str, Any]] = {}
_sessions_lock = threading.Lock()


def _safe_delete_file(file_path: Union[str, Path]) -> bool:
    """Safely delete a file ensuring it is strictly within the upload directory."""
    settings = get_settings()
    try:
        target = Path(file_path).resolve()
        base = Path(settings.UPLOAD_DIR).resolve()
        if base not in target.parents and target != base:
            logger.warning(f"Security Alert: Prevented deletion outside upload directory: {target}")
            return False

        if target.is_file() or target.is_symlink():
            target.unlink(missing_ok=True)
            return True
        elif target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
            return True
    except Exception as e:
        logger.warning(f"Error during safe deletion of {file_path}: {e}")
    return False


async def save_upload_file_stream(
    file: UploadFile,
    max_bytes: int,
    session_file_id: str,
    ext: str,
) -> Tuple[Path, int, bool]:
    """
    Stream-writes an UploadFile directly to disk in 1MB chunks to ensure O(1) memory usage.
    Returns: (save_path, total_bytes_read, file_too_large)
    """
    settings = get_settings()
    save_path = Path(settings.UPLOAD_DIR) / f"{session_file_id}{ext}"
    total_read = 0
    file_too_large = False

    with open(save_path, "wb") as out_f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total_read += len(chunk)
            if total_read > max_bytes:
                file_too_large = True
                break
            out_f.write(chunk)

    return save_path, total_read, file_too_large


def _generate_insights_background(
    session_id: str,
    chunks_by_file: Dict[str, List[Dict]],
    doc_metadata: List[Dict],
    provider: str
) -> None:
    """Generate summary and key questions in the background concurrently across files."""
    try:
        with _sessions_lock:
            session_data = sessions.get(session_id)
        if not session_data:
            return

        llm = FreeLLMService(provider=provider)
        insights_dict = session_data.get("insights", {})

        files_to_process = [
            (fn, file_chunks) for fn, file_chunks in chunks_by_file.items()
            if fn not in insights_dict
        ]

        if not files_to_process:
            return

        def _process_file(fn: str, file_chunks: List[Dict]) -> Tuple[str, Any]:
            matching_meta = next((m for m in doc_metadata if m.get("filename") == fn), {})
            pages_count = matching_meta.get("num_pages", 0)
            logger.info(f"Generating background insights for {fn} in parallel...")
            doc_insights = generate_document_insights(
                session_id=session_id,
                chunks=file_chunks,
                llm_service=llm,
                total_pages=pages_count
            )
            return fn, doc_insights

        # Dispatch files in parallel worker threads to eliminate serial wait
        workers = min(4, len(files_to_process))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_process_file, fn, chunks)
                for fn, chunks in files_to_process
            ]
            for future in concurrent.futures.as_completed(futures):
                try:
                    fn, doc_insights = future.result()
                    with _sessions_lock:
                        if session_id in sessions:
                            sessions[session_id].setdefault("insights", {})[fn] = doc_insights
                except Exception as ex:
                    logger.warning(f"Failed to generate insights for file: {ex}")

        logger.info(f"Background insights complete for session {session_id}")
    except Exception as e:
        logger.error(f"Background insights generation failed: {e}", exc_info=True)


def persist_session_snapshot(
    session_id: str,
    saved_paths: List[str],
    file_names: List[str],
    doc_metadata: List[Dict],
    owner_id: str,
    chunks: Optional[List[Dict]] = None,
    embeddings: Optional[np.ndarray] = None,
    insights: Optional[Dict] = None,
) -> None:
    """Save complete session snapshot (metadata, chunks, and embeddings) to disk."""
    settings = get_settings()
    try:
        session_dir = Path(settings.UPLOAD_DIR) / "sessions" / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        session_meta_file = session_dir / "session.json"
        tmp_meta_file = session_dir / f"session_{uuid.uuid4().hex[:8]}.tmp"
        with open(tmp_meta_file, "w", encoding="utf-8") as f:
            json.dump({
                "session_id": session_id,
                "owner_id": owner_id,
                "file_paths": saved_paths,
                "file_names": file_names,
                "metadata": doc_metadata,
                "insights": insights or {},
                "created_at": time.time(),
            }, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_meta_file, session_meta_file)

        if chunks is not None:
            chunks_file = session_dir / "chunks.json"
            tmp_chunks_file = session_dir / f"chunks_{uuid.uuid4().hex[:8]}.tmp"
            clean_chunks = []
            for c in chunks:
                chk = dict(c)
                if "embedding" in chk:
                    chk.pop("embedding")
                clean_chunks.append(chk)
            with open(tmp_chunks_file, "w", encoding="utf-8") as f:
                json.dump(clean_chunks, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_chunks_file, chunks_file)

        if embeddings is not None:
            embeddings_file = session_dir / "embeddings.npy"
            np.save(str(embeddings_file), embeddings)

        logger.info(f"Persisted session snapshot {session_id} to disk.")
    except Exception as e:
        logger.error(f"Failed to persist session {session_id} to disk: {e}")


def _persist_session_background(
    session_id: str,
    saved_paths: List[str],
    file_names: List[str],
    doc_metadata: List[Dict],
    owner_id: str,
    chunks: Optional[List[Dict]] = None,
    embeddings: Optional[np.ndarray] = None,
) -> None:
    """Background task wrapper for session disk persistence."""
    persist_session_snapshot(
        session_id=session_id,
        saved_paths=saved_paths,
        file_names=file_names,
        doc_metadata=doc_metadata,
        owner_id=owner_id,
        chunks=chunks,
        embeddings=embeddings
    )


async def _get_session(session_id: str, current_user: UserContext) -> Dict[str, Any]:
    """Retrieve session from memory, disk, or PostgreSQL, checking user ownership."""
    settings = get_settings()
    session_data = None
    with _sessions_lock:
        if session_id in sessions:
            session_data = sessions[session_id]

    if not session_data:
        try:
            session_dir = Path(settings.UPLOAD_DIR) / "sessions" / session_id
            session_meta_file = session_dir / "session.json"
            chunks_file = session_dir / "chunks.json"
            embeddings_file = session_dir / "embeddings.npy"

            if session_dir.exists() and session_meta_file.exists():
                try:
                    with open(session_meta_file, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                except Exception as me:
                    logger.warning(f"Error reading {session_meta_file}: {me}")
                    meta = {}

                chunks = []
                if chunks_file.exists():
                    try:
                        with open(chunks_file, "r", encoding="utf-8") as f:
                            chunks = json.load(f)
                    except Exception as ce:
                        logger.warning(f"Error loading chunks for session {session_id}: {ce}")

                embeddings = None
                if embeddings_file.exists():
                    try:
                        embeddings = np.load(str(embeddings_file))
                    except Exception as ee:
                        logger.warning(f"Error loading embeddings for session {session_id}: {ee}")

                restored_session = {
                    "chunks": chunks,
                    "embeddings": embeddings,
                    "file_paths": meta.get("file_paths", []),
                    "file_names": meta.get("file_names", []),
                    "metadata": meta.get("metadata", []),
                    "insights": meta.get("insights", {}),
                    "created_at": meta.get("created_at", time.time()),
                    "owner_id": meta.get("owner_id"),
                }
                with _sessions_lock:
                    sessions[session_id] = restored_session
                session_data = restored_session
                logger.info(f"Loaded session {session_id} from disk with {len(chunks)} chunks")
        except Exception as e:
            logger.error(f"Error loading session {session_id} from disk: {e}")

    # Fallback to PostgreSQL if configured and pool is ready
    if not session_data and database.is_database_ready():
        try:
            db_session = await database.get_session(session_id)
            if db_session:
                chunks = await database.get_chunks_for_session(session_id, include_embeddings=True)
                embeddings = None
                if chunks and all("embedding" in c and c["embedding"] is not None for c in chunks):
                    embeddings = np.array([c.pop("embedding") for c in chunks], dtype=np.float32)

                restored_session = {
                    "chunks": chunks,
                    "embeddings": embeddings,
                    "file_paths": db_session.get("file_paths", []),
                    "file_names": db_session.get("file_names", []),
                    "metadata": db_session.get("metadata", []),
                    "insights": db_session.get("insights", {}),
                    "created_at": db_session.get("created_at", time.time()),
                    "owner_id": db_session.get("owner_id"),
                }
                with _sessions_lock:
                    sessions[session_id] = restored_session
                session_data = restored_session
                logger.info(f"Loaded session {session_id} from PostgreSQL")
        except Exception as e:
            logger.error(f"Error loading session {session_id} from PostgreSQL: {e}")

    if not session_data:
        raise HTTPException(
            status_code=404,
            detail="Session not found or expired. Please upload documents again."
        )

    assert_resource_ownership(
        resource_owner_id=session_data.get("owner_id"),
        current_user=current_user,
        resource_type="session",
        action="access"
    )

    return session_data


def _validate_question(question: str) -> None:
    """Validate question input length and presence."""
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if len(question) > 1000:
        raise HTTPException(status_code=400, detail="Question is too long (max 1000 characters).")


def _cleanup_session(session_id: str) -> None:
    """Delete session data, files, and conversation history."""
    settings = get_settings()
    session_data = None
    with _sessions_lock:
        if session_id in sessions:
            session_data = sessions.pop(session_id, None)

    if session_data:
        for path in session_data.get("file_paths", []):
            _safe_delete_file(path)
        _safe_delete_file(Path(settings.UPLOAD_DIR) / "sessions" / session_id)
        get_conversation_manager().clear_history(session_id)
        logger.info(f"Cleaned up session {session_id[:8]}")


def cleanup_expired_sessions(max_age_hours: Optional[int] = None) -> Dict[str, int]:
    """Delete expired sessions and files older than retention limit."""
    settings = get_settings()
    ttl_hours = max_age_hours if max_age_hours is not None else (settings.RETENTION_HOURS or 24)
    cutoff_time = time.time() - (ttl_hours * 3600)
    purged_sessions = 0
    purged_files = 0

    # Purge expired in-memory sessions
    with _sessions_lock:
        expired_session_ids = [
            sid for sid, data in list(sessions.items())
            if data.get("created_at", 0) < cutoff_time
        ]
        for sid in expired_session_ids:
            session_data = sessions.pop(sid, None)
            if session_data:
                for path in session_data.get("file_paths", []):
                    if _safe_delete_file(path):
                        purged_files += 1
                _safe_delete_file(Path(settings.UPLOAD_DIR) / "sessions" / sid)
                get_conversation_manager().clear_history(sid)
                purged_sessions += 1

    # Purge expired sessions on disk
    sessions_root = Path(settings.UPLOAD_DIR) / "sessions"
    if sessions_root.exists():
        for session_folder in list(sessions_root.iterdir()):
            if session_folder.is_dir():
                meta_file = session_folder / "session.json"
                mtime = session_folder.stat().st_mtime
                file_paths_to_delete = []
                if meta_file.exists():
                    try:
                        with open(meta_file, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                            mtime = meta.get("created_at", mtime)
                            file_paths_to_delete = meta.get("file_paths", [])
                    except Exception as e:
                        logger.debug(f"Failed to read session metadata {meta_file}: {e}")

                if mtime < cutoff_time:
                    for p in file_paths_to_delete:
                        if _safe_delete_file(p):
                            purged_files += 1
                    _safe_delete_file(session_folder)
                    purged_sessions += 1

    # Purge expired database sessions if configured
    if database.is_database_configured():
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(database.delete_expired_sessions(cutoff_time))
            else:
                loop.run_until_complete(database.delete_expired_sessions(cutoff_time))
        except Exception as e:
            logger.debug(f"Async DB cleanup skipped: {e}")

    logger.info(f"Retention cleanup: purged {purged_sessions} sessions, {purged_files} files.")
    return {"purged_sessions": purged_sessions, "purged_files": purged_files}


async def _retention_cleanup_loop():
    """Periodic task to clean up old sessions and orphaned files."""
    settings = get_settings()
    logger.info(
        f"Retention cleaner started (interval: {settings.CLEANUP_INTERVAL_MINUTES}m, "
        f"retention: {settings.RETENTION_HOURS}h)"
    )
    while True:
        try:
            await asyncio.sleep(settings.CLEANUP_INTERVAL_MINUTES * 60)
            res = cleanup_expired_sessions(max_age_hours=settings.RETENTION_HOURS)
            if res.get("purged_sessions", 0) > 0 or res.get("purged_files", 0) > 0:
                logger.info(
                    f"Cleaned up {res['purged_sessions']} sessions, {res['purged_files']} files."
                )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error during retention cleanup: {e}")
