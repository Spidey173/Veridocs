import os
import json
import logging
import time
import asyncio
from pathlib import Path
from typing import List, Dict, Optional, Any
import asyncpg
from pgvector.asyncpg import register_vector
import numpy as np

from config import get_settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


def is_database_configured() -> bool:
    """Check if a PostgreSQL database URL is configured."""
    settings = get_settings()
    return bool(settings.DATABASE_URL and settings.DATABASE_URL.strip())


def run_migrations(dsn: Optional[str] = None) -> bool:
    """Run Alembic database migrations programmatically up to head."""
    try:
        from alembic.config import Config
        from alembic import command

        base_dir = Path(__file__).resolve().parent
        ini_path = base_dir / "alembic.ini"

        alembic_cfg = Config(str(ini_path))
        target_dsn = dsn or (get_settings().DATABASE_URL or os.getenv("DATABASE_URL", ""))
        if target_dsn:
            sync_dsn = target_dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
            alembic_cfg.set_main_option("sqlalchemy.url", sync_dsn)

        command.upgrade(alembic_cfg, "head")
        logger.info("Successfully executed Alembic migrations to head.")
        return True
    except Exception as e:
        logger.warning(f"Alembic migration runner notice: {e}")
        return False


def get_migration_head() -> Optional[str]:
    """Get the latest revision identifier from Alembic scripts."""
    try:
        from alembic.script import ScriptDirectory
        from alembic.config import Config

        base_dir = Path(__file__).resolve().parent
        ini_path = base_dir / "alembic.ini"
        alembic_cfg = Config(str(ini_path))
        script = ScriptDirectory.from_config(alembic_cfg)
        return script.get_current_head()
    except Exception as e:
        logger.warning(f"Could not retrieve Alembic head: {e}")
        return None


async def _init_connection(conn):
    """Register pgvector types on each pooled connection."""
    await register_vector(conn)


async def init_db() -> bool:
    """Initialize PostgreSQL connection pool and verify database schema."""
    global _pool
    if not is_database_configured():
        logger.info("DATABASE_URL not configured. Running with in-memory storage.")
        return False

    settings = get_settings()
    dsn = settings.DATABASE_URL.strip()

    try:
        # Run Alembic versioned migrations
        await asyncio.to_thread(run_migrations, dsn)

        # Create connection pool
        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=1,
            max_size=10,
            init=_init_connection,
            command_timeout=30,
        )

        # Initialize tables and indexes
        async with _pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            await register_vector(conn)

            # Sessions table
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id VARCHAR(128) PRIMARY KEY,
                owner_id VARCHAR(128) NOT NULL,
                file_names JSONB NOT NULL DEFAULT '[]'::jsonb,
                file_paths JSONB NOT NULL DEFAULT '[]'::jsonb,
                metadata JSONB NOT NULL DEFAULT '[]'::jsonb,
                insights JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at DOUBLE PRECISION NOT NULL,
                updated_at DOUBLE PRECISION NOT NULL
            );
            """)

            # Document chunks with vector and full-text search
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id BIGSERIAL PRIMARY KEY,
                session_id VARCHAR(128) REFERENCES sessions(id) ON DELETE CASCADE,
                source_file VARCHAR(255) NOT NULL,
                page_number INT NOT NULL,
                chunk_index INT NOT NULL,
                text TEXT NOT NULL,
                metadata JSONB DEFAULT '{}'::jsonb,
                embedding vector(384)
            );
            CREATE INDEX IF NOT EXISTS idx_chunks_session ON document_chunks(session_id);
            CREATE INDEX IF NOT EXISTS idx_chunks_source ON document_chunks(session_id, source_file);
            CREATE INDEX IF NOT EXISTS idx_chunks_hnsw ON document_chunks USING hnsw (embedding vector_cosine_ops);
            CREATE INDEX IF NOT EXISTS idx_chunks_fts ON document_chunks USING gin (to_tsvector('english', text));
            """)

            # Chat history table
            await conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id VARCHAR(128) PRIMARY KEY,
                session_id VARCHAR(128) REFERENCES sessions(id) ON DELETE CASCADE,
                role VARCHAR(16) NOT NULL,
                content TEXT NOT NULL,
                created_at DOUBLE PRECISION NOT NULL,
                metadata JSONB DEFAULT '{}'::jsonb
            );
            CREATE INDEX IF NOT EXISTS idx_messages_session ON chat_messages(session_id, created_at);
            """)

        logger.info("Connected to PostgreSQL and verified pgvector schema.")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL database: {e}")
        _pool = None
        return False


async def close_db():
    """Close the database connection pool."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("Closed PostgreSQL connection pool.")


def get_pool() -> Optional[asyncpg.Pool]:
    """Get the active database connection pool."""
    return _pool


# Session operations

async def save_session(
    session_id: str,
    owner_id: str,
    file_names: List[str],
    file_paths: List[str],
    metadata: List[Dict],
    insights: Dict,
    created_at: Optional[float] = None
) -> bool:
    """Save or update session metadata in PostgreSQL."""
    if _pool is None:
        return False

    now = created_at or time.time()
    query = """
    INSERT INTO sessions (id, owner_id, file_names, file_paths, metadata, insights, created_at, updated_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    ON CONFLICT (id) DO UPDATE SET
        file_names = EXCLUDED.file_names,
        file_paths = EXCLUDED.file_paths,
        metadata = EXCLUDED.metadata,
        insights = EXCLUDED.insights,
        updated_at = EXCLUDED.updated_at;
    """
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                query,
                session_id,
                owner_id,
                json.dumps(file_names),
                json.dumps(file_paths),
                json.dumps(metadata),
                json.dumps(insights),
                now,
                time.time()
            )
        return True
    except Exception as e:
        logger.error(f"Error saving session {session_id} to database: {e}")
        return False


async def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve session from PostgreSQL."""
    if _pool is None:
        return None

    query = "SELECT id, owner_id, file_names, file_paths, metadata, insights, created_at, updated_at FROM sessions WHERE id = $1;"
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(query, session_id)
            if not row:
                return None

            file_names = json.loads(row["file_names"]) if isinstance(row["file_names"], str) else row["file_names"]
            file_paths = json.loads(row["file_paths"]) if isinstance(row["file_paths"], str) else row["file_paths"]
            metadata = json.loads(row["metadata"]) if isinstance(row["metadata"], str) else row["metadata"]
            insights = json.loads(row["insights"]) if isinstance(row["insights"], str) else row["insights"]

            return {
                "session_id": row["id"],
                "owner_id": row["owner_id"],
                "file_names": file_names,
                "file_paths": file_paths,
                "metadata": metadata,
                "insights": insights,
                "created_at": row["created_at"],
            }
    except Exception as e:
        logger.error(f"Error retrieving session {session_id} from database: {e}")
        return None


async def delete_session(session_id: str) -> bool:
    """Delete session and cascade delete all chunks and messages."""
    if _pool is None:
        return False

    query = "DELETE FROM sessions WHERE id = $1;"
    try:
        async with _pool.acquire() as conn:
            await conn.execute(query, session_id)
        return True
    except Exception as e:
        logger.error(f"Error deleting session {session_id} from database: {e}")
        return False


async def delete_document_from_session(session_id: str, document_name: str) -> bool:
    """Remove chunks for a single document from PostgreSQL."""
    if _pool is None:
        return False

    query = "DELETE FROM document_chunks WHERE session_id = $1 AND source_file = $2;"
    try:
        async with _pool.acquire() as conn:
            await conn.execute(query, session_id, document_name)
        return True
    except Exception as e:
        logger.error(f"Error deleting document {document_name} from session {session_id}: {e}")
        return False


# Chunk & Vector operations

async def save_chunks(session_id: str, chunks: List[Dict], embeddings: np.ndarray) -> bool:
    """Save document chunks and vector embeddings to PostgreSQL."""
    if _pool is None or not chunks:
        return False

    records = []
    for i, chunk in enumerate(chunks):
        emb = embeddings[i]
        meta = {k: v for k, v in chunk.items() if k not in ("text", "embedding")}
        records.append((
            session_id,
            chunk.get("source_file", "unknown"),
            int(chunk.get("page", 1)),
            int(chunk.get("chunk_index", i)),
            chunk.get("text", ""),
            json.dumps(meta),
            emb
        ))

    insert_query = """
    INSERT INTO document_chunks (session_id, source_file, page_number, chunk_index, text, metadata, embedding)
    VALUES ($1, $2, $3, $4, $5, $6, $7);
    """
    try:
        async with _pool.acquire() as conn:
            await conn.executemany(insert_query, records)
        logger.info(f"Saved {len(records)} chunks to PostgreSQL for session {session_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving chunks to PostgreSQL: {e}")
        return False


async def get_chunks_for_session(
    session_id: str,
    source_file: Optional[str] = None,
    include_embeddings: bool = False
) -> List[Dict]:
    """Retrieve all chunks for a session from PostgreSQL, optionally including embeddings."""
    if _pool is None:
        return []

    select_fields = "id, source_file, page_number, chunk_index, text, metadata"
    if include_embeddings:
        select_fields += ", embedding"

    if source_file:
        query = f"""
        SELECT {select_fields}
        FROM document_chunks
        WHERE session_id = $1 AND source_file = $2
        ORDER BY chunk_index ASC;
        """
        params = [session_id, source_file]
    else:
        query = f"""
        SELECT {select_fields}
        FROM document_chunks
        WHERE session_id = $1
        ORDER BY source_file, chunk_index ASC;
        """
        params = [session_id]

    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            chunks = []
            for r in rows:
                meta = json.loads(r["metadata"]) if isinstance(r["metadata"], str) else (r["metadata"] or {})
                item = {
                    "text": r["text"],
                    "page": r["page_number"],
                    "chunk_index": r["chunk_index"],
                    "source_file": r["source_file"],
                    **meta
                }
                if include_embeddings and "embedding" in r and r["embedding"] is not None:
                    item["embedding"] = r["embedding"]
                chunks.append(item)
            return chunks
    except Exception as e:
        logger.error(f"Error fetching chunks for session {session_id}: {e}")
        return []


async def hybrid_search_postgres(
    session_id: str,
    query: str,
    query_embedding: np.ndarray,
    k: int = 5,
    dense_weight: float = 0.7,
    bm25_weight: float = 0.3,
    active_files: Optional[List[str]] = None
) -> List[Dict]:
    """Perform hybrid search (vector cosine similarity + full text search) in PostgreSQL with RRF."""
    if _pool is None:
        return []

    sql = """
    WITH dense AS (
        SELECT id, text, page_number, source_file, metadata,
               1 - (embedding <=> $2) AS dense_score,
               ROW_NUMBER() OVER (ORDER BY embedding <=> $2) AS dense_rank
        FROM document_chunks
        WHERE session_id = $1
          AND ($7::varchar[] IS NULL OR source_file = ANY($7::varchar[]))
        ORDER BY embedding <=> $2
        LIMIT 20
    ),
    sparse AS (
        SELECT id, text, page_number, source_file, metadata,
               ts_rank_cd(to_tsvector('english', text), plainto_tsquery('english', $3)) AS sparse_score,
               ROW_NUMBER() OVER (ORDER BY ts_rank_cd(to_tsvector('english', text), plainto_tsquery('english', $3)) DESC) AS sparse_rank
        FROM document_chunks
        WHERE session_id = $1
          AND ($7::varchar[] IS NULL OR source_file = ANY($7::varchar[]))
          AND to_tsvector('english', text) @@ plainto_tsquery('english', $3)
        LIMIT 20
    ),
    combined AS (
        SELECT
            COALESCE(d.id, s.id) AS id,
            COALESCE(d.text, s.text) AS text,
            COALESCE(d.page_number, s.page_number) AS page_number,
            COALESCE(d.source_file, s.source_file) AS source_file,
            COALESCE(d.metadata, s.metadata) AS metadata,
            COALESCE(d.dense_score, 0.0) AS dense_score,
            COALESCE(s.sparse_score, 0.0) AS sparse_score,
            (COALESCE($4 * (1.0 / (60.0 + d.dense_rank)), 0.0) +
             COALESCE($5 * (1.0 / (60.0 + s.sparse_rank)), 0.0)) AS rrf_score
        FROM dense d
        FULL OUTER JOIN sparse s ON d.id = s.id
    )
    SELECT id, text, page_number, source_file, metadata, dense_score, sparse_score, rrf_score
    FROM combined
    ORDER BY rrf_score DESC
    LIMIT $6;
    """

    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                sql,
                session_id,
                query_embedding,
                query,
                dense_weight,
                bm25_weight,
                k,
                active_files
            )

            results = []
            for r in rows:
                meta = json.loads(r["metadata"]) if isinstance(r["metadata"], str) else (r["metadata"] or {})
                item = {
                    "text": r["text"],
                    "page": r["page_number"],
                    "source_file": r["source_file"],
                    "relevance_score": round(float(r["rrf_score"]), 4),
                    "dense_score": round(float(r["dense_score"]), 4),
                    "bm25_score": round(float(r["sparse_score"]), 4),
                    **meta
                }
                results.append(item)
            return results
    except Exception as e:
        logger.error(f"Error during PostgreSQL hybrid search: {e}")
        return []


# Chat History operations

async def save_chat_message(
    session_id: str,
    message_id: str,
    role: str,
    content: str,
    metadata: Optional[Dict] = None
) -> bool:
    """Save a chat message to PostgreSQL."""
    if _pool is None:
        return False

    query = """
    INSERT INTO chat_messages (id, session_id, role, content, created_at, metadata)
    VALUES ($1, $2, $3, $4, $5, $6)
    ON CONFLICT (id) DO NOTHING;
    """
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                query,
                message_id,
                session_id,
                role,
                content,
                time.time(),
                json.dumps(metadata or {})
            )
        return True
    except Exception as e:
        logger.error(f"Error saving chat message to database: {e}")
        return False


async def get_chat_history(session_id: str, limit: int = 50) -> List[Dict]:
    """Retrieve chat history from PostgreSQL."""
    if _pool is None:
        return []

    query = """
    SELECT id, role, content, created_at, metadata
    FROM chat_messages
    WHERE session_id = $1
    ORDER BY created_at ASC
    LIMIT $2;
    """
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(query, session_id, limit)
            messages = []
            for r in rows:
                meta = json.loads(r["metadata"]) if isinstance(r["metadata"], str) else (r["metadata"] or {})
                messages.append({
                    "id": r["id"],
                    "role": r["role"],
                    "content": r["content"],
                    "created_at": r["created_at"],
                    "metadata": meta,
                })
            return messages
    except Exception as e:
        logger.error(f"Error fetching chat history from database: {e}")
        return []


async def clear_chat_history(session_id: str) -> bool:
    """Delete all chat messages for a session."""
    if _pool is None:
        return False

    query = "DELETE FROM chat_messages WHERE session_id = $1;"
    try:
        async with _pool.acquire() as conn:
            await conn.execute(query, session_id)
        return True
    except Exception as e:
        logger.error(f"Error clearing chat history from database: {e}")
        return False

