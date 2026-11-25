"""
Vector Store for Veridocs:
- PostgreSQL + pgvector: HNSW cosine vector search + GIN full-text search fused with Reciprocal Rank Fusion (RRF).
- Local/SQLite fallback: Dense Fastembed cosine similarity + keyword match fused with Reciprocal Rank Fusion.
"""

import logging
from typing import List, Dict, Any, Optional
import numpy as np
from sqlalchemy import text

from config import get_settings, get_model_registry
import database
from database import get_db
from models_db import HAS_PGVECTOR

logger = logging.getLogger(__name__)

# Query embedding cache & hybrid search result cache
_QUERY_CACHE: Dict[str, np.ndarray] = {}
_MAX_QUERY_CACHE = 512
_SEARCH_CACHE: Dict[tuple, List[Dict[str, Any]]] = {}
_MAX_SEARCH_CACHE = 256


def get_query_embedding(query: str) -> np.ndarray:
    """Compute and cache L2-normalized embedding for query string."""
    q_norm = " ".join(query.strip().lower().split())
    if q_norm in _QUERY_CACHE:
        return _QUERY_CACHE[q_norm]

    reg = get_model_registry()
    emb = list(reg.embedding_model.embed([q_norm]))[0]
    emb = np.asarray(emb, dtype=np.float32)
    norm = np.linalg.norm(emb)
    if norm > 0:
        emb = emb / norm

    if len(_QUERY_CACHE) >= _MAX_QUERY_CACHE:
        _QUERY_CACHE.pop(next(iter(_QUERY_CACHE)))
    _QUERY_CACHE[q_norm] = emb
    return emb


def compute_rrf(dense_ranked_ids: List[str], sparse_ranked_ids: List[str], k: int = 60) -> Dict[str, float]:
    """
    Reciprocal Rank Fusion (RRF) scoring:
    RRF_score(d) = sum(1 / (k + rank_i))
    """
    scores: Dict[str, float] = {}

    for rank, doc_id in enumerate(dense_ranked_ids):
        scores[doc_id] = scores.get(doc_id, 0.0) + (1.0 / (k + rank + 1))

    for rank, doc_id in enumerate(sparse_ranked_ids):
        scores[doc_id] = scores.get(doc_id, 0.0) + (1.0 / (k + rank + 1))

    return scores


class VectorStore:
    """Hybrid vector and full-text search store with Reciprocal Rank Fusion."""

    @staticmethod
    def save_chunks(
        session_id: str, chunks: List[Dict[str, Any]], embeddings: List[np.ndarray], document_id: Optional[str] = None
    ):
        """Persist chunks and embeddings."""
        database.save_chunks(session_id, chunks, embeddings, document_id=document_id)

    @classmethod
    def search(
        cls,
        session_id: Optional[str],
        query: str,
        top_k: Optional[int] = None,
        active_files: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Perform hybrid retrieval using Reciprocal Rank Fusion (RRF).
        If session_id is None, searches across all documents in the library.
        """
        settings = get_settings()
        k = top_k or settings.TOP_K
        q_norm = " ".join(query.strip().lower().split())
        files_key = tuple(sorted(active_files)) if active_files else None
        cache_key = (database.get_chunk_cache_version(), session_id, files_key, q_norm, k)
        cached = _SEARCH_CACHE.get(cache_key)
        if cached is not None:
            return [dict(item) for item in cached]

        if settings.is_postgres and HAS_PGVECTOR:
            try:
                results = cls._search_postgres_hybrid(session_id, query, k, active_files)
            except Exception as e:
                logger.warning(f"PostgreSQL pgvector search failed, falling back to local hybrid search: {e}")
                results = cls._search_local_hybrid(session_id, query, k, active_files)
        else:
            results = cls._search_local_hybrid(session_id, query, k, active_files)

        if len(_SEARCH_CACHE) >= _MAX_SEARCH_CACHE:
            _SEARCH_CACHE.pop(next(iter(_SEARCH_CACHE)))
        _SEARCH_CACHE[cache_key] = [dict(item) for item in results]
        return results

    @classmethod
    def _search_postgres_hybrid(
        cls, session_id: Optional[str], query: str, top_k: int, active_files: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Execute PostgreSQL pgvector cosine similarity + GIN tsvector full-text search,
        fused with Reciprocal Rank Fusion (RRF).
        """
        q_emb = get_query_embedding(query)
        q_emb_list = q_emb.tolist()

        where_clauses: List[str] = []
        params: Dict[str, Any] = {
            "q_emb": str(q_emb_list),
            "query": query,
            "limit": top_k * 3,
        }
        if session_id:
            where_clauses.append("session_id = :session_id")
            params["session_id"] = session_id
        if active_files:
            where_clauses.append("filename = ANY(:active_files)")
            params["active_files"] = list(active_files)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
        sparse_where_sql = ("WHERE " + " AND ".join(where_clauses) + " AND ") if where_clauses else "WHERE "

        with get_db() as db:
            # 1. Dense search using pgvector cosine distance operator <=>
            dense_sql = text(f"""
                SELECT id, document_id, session_id, filename, page_number, content, chunk_type, section_path, metadata,
                       1 - (embedding <=> :q_emb::vector) as similarity
                FROM chunks
                {where_sql}
                ORDER BY embedding <=> :q_emb::vector ASC
                LIMIT :limit
            """)
            dense_rows = db.execute(dense_sql, params).fetchall()

            # 2. Sparse full-text search using ts_rank
            sparse_sql = text(f"""
                SELECT id, document_id, session_id, filename, page_number, content, chunk_type, section_path, metadata,
                       ts_rank_cd(to_tsvector('english', content), plainto_tsquery('english', :query)) as rank_score
                FROM chunks
                {sparse_where_sql} to_tsvector('english', content) @@ plainto_tsquery('english', :query)
                ORDER BY rank_score DESC
                LIMIT :limit
            """)
            sparse_rows = db.execute(sparse_sql, params).fetchall()

            dense_ids = [r.id for r in dense_rows]
            sparse_ids = [r.id for r in sparse_rows]

            # Reciprocal Rank Fusion
            rrf_scores = compute_rrf(dense_ids, sparse_ids, k=60)

            chunk_map = {}
            sim_map = {}
            for r in dense_rows:
                chunk_map[r.id] = r
                sim_map[r.id] = float(r.similarity)
            for r in sparse_rows:
                if r.id not in chunk_map:
                    chunk_map[r.id] = r

            sorted_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)[:top_k]

            results = []
            for cid in sorted_ids:
                row = chunk_map[cid]
                meta = row.metadata or {}
                results.append(
                    {
                        "id": row.id,
                        "document_id": getattr(row, "document_id", None),
                        "session_id": getattr(row, "session_id", None),
                        "source_file": row.filename,
                        "filename": row.filename,
                        "page": row.page_number,
                        "page_number": row.page_number,
                        "text": row.content,
                        "content": row.content,
                        "chunk_type": row.chunk_type,
                        "section_path": getattr(row, "section_path", None) or meta.get("section_path"),
                        "relevance_score": sim_map.get(cid, round(rrf_scores[cid] * 10, 4)),
                        "rrf_score": rrf_scores[cid],
                        "metadata": meta,
                    }
                )

            logger.info(f"[VectorStore PG Hybrid] Query: '{query}' | retrieved={len(results)}")
            return results

    @classmethod
    def _search_local_hybrid(
        cls, session_id: Optional[str], query: str, top_k: int, active_files: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """
        Local/SQLite fallback:
        Computes dense Fastembed cosine similarity + token keyword overlap, fused with RRF.
        """
        chunks, embeddings = database.get_chunks_and_embeddings(session_id=session_id, active_files=active_files)
        if len(chunks) == 0 or embeddings.shape[0] == 0:
            return []

        q_emb = get_query_embedding(query)

        # 1. Dense cosine similarity ranking
        dense_scores = np.dot(embeddings, q_emb)
        dense_order = np.argsort(dense_scores)[::-1]
        dense_ranked_ids = [str(chunks[i]["id"]) for i in dense_order]

        # 2. Sparse keyword matching ranking
        q_tokens = set(query.lower().split())
        sparse_scores = []
        for c in chunks:
            text_tokens = set(c.get("text", "").lower().split())
            overlap = len(q_tokens & text_tokens)
            sparse_scores.append(overlap)

        sparse_order = np.argsort(np.array(sparse_scores))[::-1]
        sparse_ranked_ids = [str(chunks[i]["id"]) for i in sparse_order if sparse_scores[i] > 0]

        # 3. Reciprocal Rank Fusion
        rrf_scores = compute_rrf(dense_ranked_ids, sparse_ranked_ids, k=60)

        chunk_lookup = {str(c["id"]): (c, dense_scores[i]) for i, c in enumerate(chunks)}
        sorted_ids = sorted(rrf_scores.keys(), key=lambda cid: rrf_scores[cid], reverse=True)[:top_k]

        results = []
        for cid in sorted_ids:
            chunk, d_score = chunk_lookup[cid]
            item = dict(chunk)
            item["relevance_score"] = float(d_score)
            item["rrf_score"] = rrf_scores[cid]
            results.append(item)

        logger.info(f"[VectorStore Local Hybrid] Query: '{query}' | top_k={top_k} | retrieved={len(results)}")
        return results
