"""
Vector Store for Veridocs: Persistent storage via SQLite and fast dense vector search
using FAISS (if installed) with pure NumPy cosine similarity fallback.
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

# Optional FAISS support
try:
    import faiss
    HAS_FAISS = True
except ImportError:
    HAS_FAISS = False


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
    """Persistent vector store backed by SQLite database with FAISS / NumPy cosine search."""

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

        # 1. Use FAISS if installed
        if HAS_FAISS:
            try:
                dim = embeddings.shape[1]
                index = faiss.IndexFlatIP(dim)
                index.add(embeddings)
                scores, indices = index.search(np.expand_dims(q_emb, axis=0), min(k, len(chunks)))
                results = []
                for score, idx in zip(scores[0], indices[0]):
                    if idx >= 0 and idx < len(chunks):
                        item = dict(chunks[idx])
                        item["relevance_score"] = float(score)
                        results.append(item)
                return results
            except Exception as e:
                logger.warning(f"FAISS search failed, falling back to NumPy: {e}")

        # 2. NumPy cosine similarity (dot product of L2-normalized vectors)
        scores = np.dot(embeddings, q_emb)
        top_indices = np.argsort(scores)[::-1][:k]

        results = []
        for idx in top_indices:
            item = dict(chunks[idx])
            item["relevance_score"] = float(scores[idx])
            results.append(item)

        return results


def get_vector_store() -> VectorStore:
    return VectorStore()
