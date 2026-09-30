"""
Unit tests for reranker.py Cross-Encoder reranker.
"""

from unittest.mock import MagicMock
import pytest

from reranker import Reranker, rerank_chunks


class TestReranker:
    def test_rerank_empty_chunks(self):
        """Verify empty input returns empty list."""
        reranker = Reranker()
        assert reranker.rerank("query", []) == []

    def test_rerank_fewer_than_top_k(self):
        """Verify chunks count <= top_k is returned directly."""
        reranker = Reranker()
        chunks = [{"text": "chunk 1", "page": 1}]
        result = reranker.rerank("query", chunks, top_k=5)
        assert result == chunks

    def test_rerank_with_model(self, patch_models, sample_chunks):
        """Verify chunks are re-scored and sorted descending."""
        reranker = Reranker()
        # Query matching financial chunk
        result = reranker.rerank("Q3 2024 revenue", sample_chunks, top_k=2)

        assert len(result) == 2
        assert "rerank_score" in result[0]
        assert "rerank_score" in result[1]
        assert result[0]["rerank_score"] >= result[1]["rerank_score"]

    def test_rerank_model_none_fallback(self, monkeypatch, sample_chunks):
        """Verify fallback when reranker model is None."""
        reranker = Reranker()
        monkeypatch.setattr(reranker.registry, "_reranker_model", None)
        monkeypatch.setattr(reranker.settings, "RERANKER_ENABLED", False)

        result = reranker.rerank("query", sample_chunks, top_k=2)
        assert len(result) == 2
        assert result == sample_chunks[:2]

    def test_rerank_exception_fallback(self, patch_models, sample_chunks):
        """Verify fallback when model.predict raises an exception."""
        reranker = Reranker()
        mock_model = reranker.registry.reranker_model
        mock_model.predict.side_effect = RuntimeError("Inference crash")

        result = reranker.rerank("query", sample_chunks, top_k=2)
        assert len(result) == 2
        assert result == sample_chunks[:2]

    def test_rerank_chunks_helper(self, patch_models, sample_chunks):
        """Verify convenience function rerank_chunks."""
        result = rerank_chunks("FAISS", sample_chunks, top_k=1)
        assert len(result) == 1
        assert "rerank_score" in result[0]
