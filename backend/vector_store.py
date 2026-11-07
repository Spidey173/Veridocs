from abc import ABC, abstractmethod
import logging
import threading
from typing import Dict, Optional, List, Tuple, Any
import numpy as np
from fastapi import HTTPException

from config import get_settings, get_model_registry
import database
from session_store import sessions, _sessions_lock
from tracing import tracer

logger = logging.getLogger(__name__)

# Thread-safe LRU cache for query embeddings
_QUERY_CACHE: Dict[str, np.ndarray] = {}
_QUERY_CACHE_LOCK = threading.Lock()
_MAX_QUERY_CACHE_SIZE = 512


def _get_cached_query_embedding(query_norm: str) -> Optional[np.ndarray]:
    """Get query embedding from cache if present."""
    with _QUERY_CACHE_LOCK:
        if query_norm in _QUERY_CACHE:
            return _QUERY_CACHE[query_norm].copy()
    return None


def _set_cached_query_embedding(query_norm: str, embedding: np.ndarray):
    """Save query embedding to cache."""
    with _QUERY_CACHE_LOCK:
        if len(_QUERY_CACHE) >= _MAX_QUERY_CACHE_SIZE:
            first_key = next(iter(_QUERY_CACHE))
            del _QUERY_CACHE[first_key]
        _QUERY_CACHE[query_norm] = embedding.copy()


def get_query_embedding(query: str) -> np.ndarray:
    """Get or compute normalized query embedding vector."""
    query_norm = query.strip().lower()
    cached = _get_cached_query_embedding(query_norm)
    if cached is not None:
        return cached

    registry = get_model_registry()
    model = registry.embedding_model
    emb = model.encode([query], convert_to_numpy=True)[0]
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm
    _set_cached_query_embedding(query_norm, emb)
    return emb


def reciprocal_rank_fusion(
    rankings: List[List[Tuple[int, float]]],
    k: int = 60,
    weights: Optional[List[float]] = None
) -> List[Tuple[int, float]]:
    """Combine rankings from multiple search methods using RRF."""
    with tracer.span("retrieval.rrf", attributes={"rankings_count": len(rankings)}):
        from collections import defaultdict
        if weights is None:
            weights = [1.0] * len(rankings)

        fused_scores: Dict[int, float] = defaultdict(float)

        for ranking, weight in zip(rankings, weights):
            for rank, (doc_idx, _score) in enumerate(ranking):
                fused_scores[doc_idx] += weight / (k + rank + 1)

        return sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)


# =====================================================================
# VectorStore Strategy Pattern
# =====================================================================

class BaseVectorStore(ABC):
    """Abstract interface defining hybrid retrieval and chunk persistence operations."""

    @abstractmethod
    async def hybrid_search(
        self,
        session_id: str,
        query: str,
        query_embedding: np.ndarray,
        k: int = 20,
        dense_weight: float = 0.7,
        bm25_weight: float = 0.3,
        active_files: Optional[List[str]] = None,
        session_data: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Retrieve top candidate chunks matching query via hybrid dense/sparse search."""
        pass

    @abstractmethod
    async def save_chunks(
        self,
        session_id: str,
        chunks: List[Any],
        embeddings: np.ndarray
    ) -> bool:
        """Persist document chunks and dense embeddings."""
        pass

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """Delete all chunks and indexes for a given session."""
        pass


class PostgresVectorStore(BaseVectorStore):
    """Production vector store backed by PostgreSQL pgvector (HNSW) and tsvector (GIN)."""

    async def hybrid_search(
        self,
        session_id: str,
        query: str,
        query_embedding: np.ndarray,
        k: int = 20,
        dense_weight: float = 0.7,
        bm25_weight: float = 0.3,
        active_files: Optional[List[str]] = None,
        session_data: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        settings = get_settings()
        if not database.is_database_configured() or not database.is_database_ready():
            if settings.ENVIRONMENT == "production":
                logger.error("PostgreSQL connection pool is down during query retrieval in production.")
                raise HTTPException(
                    status_code=503,
                    detail="Database connection is unavailable. In-memory fallback is disabled in production to prevent worker state divergence."
                )
            logger.warning("PostgreSQL pool offline; falling back to in-memory store for development.")
            in_mem = InMemoryVectorStore()
            return await in_mem.hybrid_search(
                session_id=session_id,
                query=query,
                query_embedding=query_embedding,
                k=k,
                dense_weight=dense_weight,
                bm25_weight=bm25_weight,
                active_files=active_files,
                session_data=session_data
            )

        with tracer.span("retrieval.hybrid_search.postgres", attributes={"session_id": session_id, "k": k}):
            candidates = await database.hybrid_search_postgres(
                session_id=session_id,
                query=query,
                query_embedding=query_embedding,
                k=k,
                dense_weight=dense_weight,
                bm25_weight=bm25_weight,
                active_files=active_files or None
            )

            if active_files is not None:
                candidates = [c for c in candidates if c.get("source_file") in active_files]

            return candidates

    async def save_chunks(
        self,
        session_id: str,
        chunks: List[Any],
        embeddings: np.ndarray
    ) -> bool:
        return await database.save_chunks(session_id, chunks, embeddings)

    async def delete_session(self, session_id: str) -> bool:
        return await database.delete_session(session_id)


class InMemoryVectorStore(BaseVectorStore):
    """Ephemeral in-memory vector store for local development, fast unit tests, and demo mode."""

    async def hybrid_search(
        self,
        session_id: str,
        query: str,
        query_embedding: np.ndarray,
        k: int = 20,
        dense_weight: float = 0.7,
        bm25_weight: float = 0.3,
        active_files: Optional[List[str]] = None,
        session_data: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        settings = get_settings()
        if settings.ENVIRONMENT == "production":
            raise HTTPException(
                status_code=503,
                detail="PostgreSQL database is required in production mode. Ephemeral vector store is disabled."
            )

        if session_data is None:
            with _sessions_lock:
                session_data = sessions.get(session_id, {})

        with tracer.span("retrieval.hybrid_search.in_memory", attributes={"session_id": session_id, "k": k}):
            candidates: List[Dict[str, Any]] = []
            if "chunks" in session_data and session_data["chunks"]:
                session_chunks = session_data["chunks"]
                session_embs = session_data.get("embeddings")
                if session_embs is not None and len(session_embs) == len(session_chunks):
                    q_norm = np.linalg.norm(query_embedding)
                    q_unit = query_embedding / (q_norm if q_norm > 0 else 1.0)
                    emb_norms = np.linalg.norm(session_embs, axis=1, keepdims=True)
                    emb_norms[emb_norms == 0] = 1.0
                    normed_embs = session_embs / emb_norms
                    scores = np.dot(normed_embs, q_unit)
                    ranked_indices = np.argsort(scores)[::-1][:k]
                    for idx in ranked_indices:
                        chunk_copy = dict(session_chunks[idx])
                        chunk_copy["relevance_score"] = float(round(scores[idx], 4))
                        chunk_copy["dense_score"] = float(round(scores[idx], 4))
                        chunk_copy["bm25_score"] = 0.0
                        candidates.append(chunk_copy)
                else:
                    candidates = list(session_chunks[:k])

            if active_files is not None:
                candidates = [c for c in candidates if c.get("source_file") in active_files]

            return candidates

    async def save_chunks(
        self,
        session_id: str,
        chunks: List[Any],
        embeddings: np.ndarray
    ) -> bool:
        with _sessions_lock:
            if session_id in sessions:
                sessions[session_id]["chunks"] = chunks
                sessions[session_id]["embeddings"] = embeddings
        return True

    async def delete_session(self, session_id: str) -> bool:
        with _sessions_lock:
            sessions.pop(session_id, None)
        return True


def get_vector_store() -> BaseVectorStore:
    """Factory returning the appropriate VectorStore implementation based on runtime environment."""
    settings = get_settings()
    if settings.ENVIRONMENT == "production":
        if not database.is_database_configured():
            logger.critical("FATAL: PostgreSQL + pgvector is mandatory in production. Ephemeral fallback is strictly disabled.")
            raise HTTPException(
                status_code=503,
                detail="PostgreSQL database is required for queries in production mode. Ephemeral fallback is disabled."
            )
        return PostgresVectorStore()

    if database.is_database_configured() and database.is_database_ready():
        return PostgresVectorStore()
    return InMemoryVectorStore()
