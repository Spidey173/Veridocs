"""
Vector Store for Veridocs: Persistent storage via SQLite and fast dense vector search
using pure NumPy cosine similarity.
"""

import logging
from typing import List, Dict, Any, Optional
import numpy as np

from config import get_settings, get_model_registry
import database

logger = logging.getLogger(__name__)

# Query embedding cache
_QUERY_CACHE: Dict[str, np.ndarray] = {}
_MAX_QUERY_CACHE = 512


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


class VectorStore:
    """Persistent vector store backed by SQLite database with NumPy cosine search."""

    @staticmethod
    def save_chunks(session_id: str, chunks: List[Dict[str, Any]], embeddings: List[np.ndarray]):
        """Persist chunks and embeddings to SQLite."""
        database.save_chunks(session_id, chunks, embeddings)

    @staticmethod
    def search(
        session_id: str,
        query: str,
        top_k: Optional[int] = None,
        active_files: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Search top-k most similar chunks for query."""
        settings = get_settings()
        k = top_k or settings.TOP_K

        chunks, embeddings = database.get_chunks_and_embeddings(session_id, active_files=active_files)
        if len(chunks) == 0 or embeddings.shape[0] == 0:
            return []

        q_emb = get_query_embedding(query)

        # NumPy cosine similarity (dot product of L2-normalized vectors)
        scores = np.dot(embeddings, q_emb)
        top_indices = np.argsort(scores)[::-1][:k]

        results = []
        for idx in top_indices:
            item = dict(chunks[idx])
            item["relevance_score"] = float(scores[idx])
            results.append(item)

        # Debug logging for retrieved chunks
        logger.info(f"[VectorStore Debug] Query: '{query}' | top_k={k} | found={len(results)} chunks:")
        for i, r in enumerate(results):
            logger.info(
                f"  Rank {i+1} [Score {r.get('relevance_score', 0):.3f} | Page {r.get('page')} | File: {r.get('source_file')}]: "
                f"{r.get('text', '')[:120].replace(chr(10), ' ')}..."
            )

        return results
