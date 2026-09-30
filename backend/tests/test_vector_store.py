"""
Unit tests for vector_store.py BM25, RRF, and hybrid VectorStore.
"""

import pytest
import numpy as np

from vector_store import BM25, reciprocal_rank_fusion, VectorStore


class TestBM25:
    def test_tokenize(self):
        """Verify tokenization removes punctuation and short tokens."""
        text = "Hello, world! This is a test."
        tokens = BM25._tokenize(text)
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens
        assert "a" not in tokens  # 1-char token skipped

    def test_fit_and_search(self):
        """Verify BM25 corpus indexing and keyword search."""
        corpus = [
            "Veridocs uses FAISS for vector search.",
            "Cross-Encoder reranks the candidate chunks.",
            "Post-generation verification validates claim grounding.",
            "The quick brown fox jumps over the lazy dog.",
        ]
        bm25 = BM25()
        bm25.fit(corpus)

        assert bm25.doc_count == 4
        assert bm25.avg_doc_len > 0
        assert "faiss" in bm25.doc_freqs

        # Search for exact keyword
        results = bm25.search("faiss search", k=2)
        assert len(results) > 0
        # First result should be doc 0
        top_doc_idx, top_score = results[0]
        assert top_doc_idx == 0
        assert top_score > 0

    def test_search_unknown_terms(self):
        """Verify BM25 search with words not in the index."""
        bm25 = BM25()
        bm25.fit(["apple orange banana"])
        results = bm25.search("zebra dinosaur", k=3)
        # Scores should be 0.0
        assert all(score == 0.0 for _, score in results)


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


class TestVectorStore:
    def test_add_and_search(self, sample_chunks, patch_models):
        """Verify adding documents and performing hybrid search."""
        store = VectorStore()
        store.add_documents(sample_chunks)

        assert store.index is not None
        assert store.index.ntotal == len(sample_chunks)
        assert len(store.chunks) == len(sample_chunks)

        # Query relevant to chunk 0
        results = store.search("FAISS retrieval", k=2)
        assert len(results) > 0
        assert "text" in results[0]
        assert "relevance_score" in results[0]
        assert "source_file" in results[0]

    def test_search_empty_store(self, patch_models):
        """Verify search on unindexed store returns empty list."""
        store = VectorStore()
        results = store.search("anything", k=5)
        assert results == []

    def test_add_empty_chunks(self, patch_models):
        """Verify adding empty chunk list does not break store."""
        store = VectorStore()
        store.add_documents([])
        assert store.index is None
        assert len(store.chunks) == 0
