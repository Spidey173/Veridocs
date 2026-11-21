"""
Persistent SQLite database for Veridocs sessions, documents, and chunk embeddings.
"""

import sqlite3
import json
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

from config import get_settings

logger = logging.getLogger(__name__)


def get_db_connection() -> sqlite3.Connection:
    settings = get_settings()
    conn = sqlite3.connect(settings.DATABASE_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize SQLite tables for sessions, documents, and chunk embeddings."""
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at REAL,
                file_names TEXT
            );
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                filename TEXT NOT NULL,
                page INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                embedding BLOB NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_session ON chunks(session_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(session_id, filename);")
        conn.commit()


# Auto-initialize database on import
init_db()


def save_session(session_id: str, file_names: List[str]):
    """Insert or update session with file names."""
    with get_db_connection() as conn:
        existing = conn.execute("SELECT file_names FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if existing:
            current_files = json.loads(existing["file_names"])
            merged = list(dict.fromkeys(current_files + file_names))
            conn.execute(
                "UPDATE sessions SET file_names = ? WHERE session_id = ?",
                (json.dumps(merged), session_id)
            )
        else:
            conn.execute(
                "INSERT INTO sessions (session_id, created_at, file_names) VALUES (?, ?, ?)",
                (session_id, time.time(), json.dumps(file_names))
            )
        conn.commit()


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve session metadata from SQLite."""
    with get_db_connection() as conn:
        row = conn.execute("SELECT session_id, created_at, file_names FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if not row:
            return None
        chunk_count = conn.execute("SELECT COUNT(*) as cnt FROM chunks WHERE session_id = ?", (session_id,)).fetchone()["cnt"]
        return {
            "session_id": row["session_id"],
            "created_at": row["created_at"],
            "file_names": json.loads(row["file_names"]),
            "chunk_count": chunk_count,
        }


def save_chunks(session_id: str, chunks: List[Dict[str, Any]], embeddings: List[np.ndarray]):
    """Persist chunks and binary float32 embeddings for a session."""
    with get_db_connection() as conn:
        data_to_insert = []
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings)):
            emb_arr = np.asarray(emb, dtype=np.float32)
            # L2 normalize
            norm = np.linalg.norm(emb_arr)
            if norm > 0:
                emb_arr = emb_arr / norm
            data_to_insert.append((
                session_id,
                chunk.get("source_file", "unknown"),
                chunk.get("page", 1),
                i,
                chunk.get("text", ""),
                emb_arr.tobytes()
            ))
        conn.executemany(
            """INSERT INTO chunks (session_id, filename, page, chunk_index, text, embedding)
               VALUES (?, ?, ?, ?, ?, ?)""",
            data_to_insert
        )
        conn.commit()


def get_chunks_and_embeddings(
    session_id: str,
    active_files: Optional[List[str]] = None
) -> Tuple[List[Dict[str, Any]], np.ndarray]:
    """Retrieve stored chunks and reconstruct 2D numpy embedding matrix."""
    with get_db_connection() as conn:
        if active_files:
            placeholders = ",".join("?" for _ in active_files)
            rows = conn.execute(
                f"""SELECT id, filename, page, text, embedding FROM chunks
                   WHERE session_id = ? AND filename IN ({placeholders})
                   ORDER BY id ASC""",
                [session_id] + list(active_files)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, filename, page, text, embedding FROM chunks
                   WHERE session_id = ? ORDER BY id ASC""",
                (session_id,)
            ).fetchall()

    if not rows:
        return [], np.empty((0, 0), dtype=np.float32)

    chunks = []
    emb_list = []
    for r in rows:
        chunks.append({
            "id": r["id"],
            "source_file": r["filename"],
            "page": r["page"],
            "text": r["text"],
        })
        emb = np.frombuffer(r["embedding"], dtype=np.float32)
        emb_list.append(emb)

    return chunks, np.vstack(emb_list)


def delete_session(session_id: str) -> bool:
    """Delete session and all its chunks from SQLite."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM chunks WHERE session_id = ?", (session_id,))
        cursor = conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
        conn.commit()
        return cursor.rowcount > 0


def delete_document(session_id: str, document_name: str) -> bool:
    """Delete a single document's chunks and update session file list."""
    with get_db_connection() as conn:
        conn.execute("DELETE FROM chunks WHERE session_id = ? AND filename = ?", (session_id, document_name))
        row = conn.execute("SELECT file_names FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row:
            files = [f for f in json.loads(row["file_names"]) if f != document_name]
            conn.execute("UPDATE sessions SET file_names = ? WHERE session_id = ?", (json.dumps(files), session_id))
        conn.commit()
        return True


def list_sessions() -> List[Dict[str, Any]]:
    """List all sessions with counts."""
    with get_db_connection() as conn:
        rows = conn.execute("SELECT session_id, created_at, file_names FROM sessions ORDER BY created_at DESC").fetchall()
        res = []
        for r in rows:
            cnt = conn.execute("SELECT COUNT(*) as c FROM chunks WHERE session_id = ?", (r["session_id"],)).fetchone()["c"]
            res.append({
                "session_id": r["session_id"],
                "created_at": r["created_at"],
                "file_names": json.loads(r["file_names"]),
                "chunk_count": cnt,
            })
        return res
