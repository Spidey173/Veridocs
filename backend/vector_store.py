import logging
import threading
from typing import Dict, Optional, List, Tuple
import numpy as np

from config import get_model_registry, get_settings

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
    from collections import defaultdict
    if weights is None:
        weights = [1.0] * len(rankings)

    fused_scores: Dict[int, float] = defaultdict(float)

    for ranking, weight in zip(rankings, weights):
        for rank, (doc_idx, _score) in enumerate(ranking):
            fused_scores[doc_idx] += weight / (k + rank + 1)

    return sorted(fused_scores.items(), key=lambda x: x[1], reverse=True)
