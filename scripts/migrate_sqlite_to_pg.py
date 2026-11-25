#!/usr/bin/env python3
"""
One-off, idempotent migration script to migrate Veridocs data from SQLite to PostgreSQL.
Reads legacy SQLite sessions and chunk embeddings, and writes them into PostgreSQL + pgvector.

Usage:
    python scripts/migrate_sqlite_to_pg.py [--sqlite-path backend/data/veridocs.db] [--pg-url postgresql://...]
"""

import sys
import os
import argparse
import sqlite3
import json
import logging
from pathlib import Path
import numpy as np

# Ensure backend is on sys.path
repo_root = Path(__file__).resolve().parent.parent
backend_dir = repo_root / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from config import get_settings
from database import init_db, get_db
from models_db import SessionModel, Chunk

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("migrate_sqlite_to_pg")


def migrate(sqlite_path: Path, pg_url: str):
    if not sqlite_path.exists():
        logger.warning(f"SQLite file not found at {sqlite_path}. Nothing to migrate.")
        return

    logger.info(f"Opening SQLite database at: {sqlite_path}")
    sqlite_conn = sqlite3.connect(str(sqlite_path))
    sqlite_conn.row_factory = sqlite3.Row

    # Ensure PostgreSQL tables and pgvector extension are created
    os.environ["DATABASE_URL"] = pg_url
    from database import reset_engine

    reset_engine()
    init_db()

    # 1. Migrate Sessions
    migrated_sessions = 0
    with sqlite_conn:
        cur = sqlite_conn.execute("SELECT session_id, created_at, file_names, suggested_questions FROM sessions")
        session_rows = cur.fetchall()

    logger.info(f"Found {len(session_rows)} sessions in SQLite.")

    with get_db() as db:
        for row in session_rows:
            sid = row["session_id"]
            existing = db.get(SessionModel, sid)
            file_names = json.loads(row["file_names"]) if row["file_names"] else []
            suggested = json.loads(row["suggested_questions"]) if row["suggested_questions"] else []

            if not existing:
                sess_obj = SessionModel(
                    session_id=sid,
                    created_at=row["created_at"] or 0.0,
                    file_names=file_names,
                    suggested_questions=suggested,
                )
                db.add(sess_obj)
                migrated_sessions += 1
            else:
                # Update files if missing
                current_files = existing.file_names or []
                merged = list(dict.fromkeys(current_files + file_names))
                existing.file_names = merged

    logger.info(f"Sessions migration completed: {migrated_sessions} new sessions inserted.")

    # 2. Migrate Chunks
    with sqlite_conn:
        cur = sqlite_conn.execute("SELECT id, session_id, filename, page, chunk_index, text, embedding FROM chunks")
        chunk_rows = cur.fetchall()

    logger.info(f"Found {len(chunk_rows)} chunks in SQLite.")
    migrated_chunks = 0

    with get_db() as db:
        for r in chunk_rows:
            sid = r["session_id"]
            fname = r["filename"]
            c_idx = r["chunk_index"]

            # Idempotent check
            exists = (
                db.query(Chunk)
                .filter(Chunk.session_id == sid, Chunk.filename == fname, Chunk.chunk_index == c_idx)
                .first()
            )

            if exists:
                continue

            # Convert binary embedding to numpy array and list for pgvector
            emb_blob = r["embedding"]
            emb_arr = np.frombuffer(emb_blob, dtype=np.float32)
            emb_list = emb_arr.tolist()

            chunk_obj = Chunk(
                session_id=sid,
                filename=fname,
                page_number=r["page"],
                chunk_index=c_idx,
                content=r["text"],
                chunk_type="text",
                embedding=emb_list,
                metadata_json={
                    "source_file": fname,
                    "page": r["page"],
                    "migrated_from": "sqlite",
                },
            )
            db.add(chunk_obj)
            migrated_chunks += 1

    logger.info(f"Chunks migration completed: {migrated_chunks} new chunks inserted.")
    logger.info("Migration to PostgreSQL finished successfully.")


def main():
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Migrate Veridocs SQLite database to PostgreSQL + pgvector")
    parser.add_argument("--sqlite-path", type=Path, default=Path(settings.DATABASE_PATH), help="Path to veridocs.db")
    parser.add_argument("--pg-url", type=str, default=settings.DATABASE_URL, help="Target PostgreSQL connection URL")
    args = parser.parse_args()

    migrate(args.sqlite_path, args.pg_url)


if __name__ == "__main__":
    main()
