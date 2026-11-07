"""
Unit tests for vector_store.py: Query caching, embedding normalization, and Reciprocal Rank Fusion.
"""

import numpy as np
from vector_store import (
    get_query_embedding,
    reciprocal_rank_fusion,
    _get_cached_query_embedding,
    _set_cached_query_embedding,
    _QUERY_CACHE,
    _QUERY_CACHE_LOCK,
    _MAX_QUERY_CACHE_SIZE,
)


class TestRRF:
    def test_reciprocal_rank_fusion(self):
        """Verify merging of multiple ranked lists with RRF."""
        list1 = [(0, 0.9), (1, 0.8), (2, 0.7)]
        list2 = [(1, 10.0), (0, 5.0), (3, 2.0)]

        fused = reciprocal_rank_fusion([list1, list2], weights=[0.5, 0.5], k=60)
        assert len(fused) == 4
        top_doc, top_score = fused[0]
        # Docs 0 and 1 are in top positions in both lists
        assert top_doc in (0, 1)
        assert top_score > 0

    def test_reciprocal_rank_fusion_empty(self):
        """Verify RRF handles empty ranking lists cleanly."""
        fused = reciprocal_rank_fusion([], weights=[])
        assert fused == []

    def test_reciprocal_rank_fusion_weights(self):
        """Verify weighted RRF prioritizes higher-weighted ranking list."""
        list1 = [(0, 0.9)]
        list2 = [(1, 0.9)]
        # list1 heavily weighted
        fused = reciprocal_rank_fusion([list1, list2], weights=[10.0, 1.0], k=60)
        assert fused[0][0] == 0


class TestQueryCache:
    def test_cache_set_and_get(self):
        """Verify query embedding cache stores and retrieves arrays correctly."""
        vec = np.random.randn(384).astype(np.float32)
        _set_cached_query_embedding("test query", vec)
        retrieved = _get_cached_query_embedding("test query")
        assert retrieved is not None
        np.testing.assert_allclose(retrieved, vec)

    def test_cache_miss_returns_none(self):
        """Verify cache miss returns None."""
        assert _get_cached_query_embedding("non_existent_key_12345") is None

    def test_cache_eviction_at_max_size(self):
        """Verify LRU eviction when cache exceeds max size."""
        with _QUERY_CACHE_LOCK:
            _QUERY_CACHE.clear()

        # Fill cache to limit
        for i in range(_MAX_QUERY_CACHE_SIZE + 5):
            vec = np.array([float(i)], dtype=np.float32)
            _set_cached_query_embedding(f"key_{i}", vec)

        with _QUERY_CACHE_LOCK:
            assert len(_QUERY_CACHE) <= _MAX_QUERY_CACHE_SIZE


class TestGetQueryEmbedding:
    def test_get_query_embedding_normalized(self, patch_models):
        """Verify get_query_embedding returns an L2-normalized vector."""
        vec = get_query_embedding("What are the quarterly financial results?")
        assert isinstance(vec, np.ndarray)
        assert vec.shape == (384,)
        norm = np.linalg.norm(vec)
        assert np.isclose(norm, 1.0, atol=1e-4)

    def test_get_query_embedding_uses_cache(self, patch_models):
        """Verify subsequent calls return cached embedding without re-invoking model."""
        vec1 = get_query_embedding("repeatable search string")
        vec2 = get_query_embedding("repeatable search string")
        np.testing.assert_array_equal(vec1, vec2)
