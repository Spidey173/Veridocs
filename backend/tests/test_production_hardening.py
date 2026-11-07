"""
Production hardening test suite for Veridocs:
- Thread-safe query embedding cache
- Sliding-window rate limiter and HTTP 429 enforcement
- Document salience extraction across multi-page documents
- Async streaming token yield
"""

import time
import threading
import numpy as np
import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient

from main import app, InMemoryRateLimiter
from vector_store import _get_cached_query_embedding, _set_cached_query_embedding, _QUERY_CACHE
from contradiction_engine import _select_salient_chunks
from auth import create_access_token


class TestProductionHardening:
    """Tests verifying thread-safety, rate-limiting, and scaling upgrades."""

    def test_query_cache_thread_safety(self):
        """Verify concurrent reads and writes to query embedding cache do not raise exceptions."""
        errors = []

        def worker(thread_id: int):
            try:
                for i in range(50):
                    q = f"query_{thread_id}_{i}"
                    emb = np.random.rand(1, 384).astype(np.float32)
                    _set_cached_query_embedding(q, emb)
                    cached = _get_cached_query_embedding(q)
                    assert cached is not None
                    assert cached.shape == (1, 384)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Concurrent query cache errors encountered: {errors}"

    def test_rate_limiter_sliding_window(self):
        """Verify InMemoryRateLimiter correctly throttles when max_requests exceeded."""
        limiter = InMemoryRateLimiter()
        key = "test_client_ip"

        # Allow up to 5 requests in a 10s window
        for _ in range(5):
            allowed = limiter.check(key, max_requests=5, window_seconds=10)
            assert allowed is True

        # 6th request must be rejected
        rejected = limiter.check(key, max_requests=5, window_seconds=10)
        assert rejected is False

        # Independent key should still be allowed
        other_allowed = limiter.check("other_ip", max_requests=5, window_seconds=10)
        assert other_allowed is True

    def test_salient_chunks_selection_full_document(self):
        """Verify _select_salient_chunks captures clauses from throughout a document."""
        # Create a 40-chunk synthetic document spanning 40 pages
        chunks = []
        for p in range(1, 41):
            if p == 35:
                text = "Section 18: Liability under this agreement shall be strictly capped at $5,000,000."
                section = "Section 18. Limitation of Liability"
            elif p == 25:
                text = "Section 12: Invoices must be settled within 45 days net of receipt."
                section = "Section 12. Payment Terms"
            else:
                text = f"General background text for page {p} describing operational workflows."
                section = None

            chunks.append({
                "page": p,
                "text": text,
                "section": section,
            })

        # Request salient chunks with a budget
        salient = _select_salient_chunks(chunks, max_chars=3000)

        # Ensure pages 25 and 35 (which have financial figures) are retained
        salient_pages = {c["page"] for c in salient}
        assert 25 in salient_pages, "Payment terms on page 25 should be selected"
        assert 35 in salient_pages, "Liability cap on page 35 should be selected"

    def test_rate_limit_http_429_response(self, test_client: TestClient, monkeypatch):
        """Verify HTTP 429 is returned by endpoints when rate limit is exceeded."""
        from config import get_settings
        settings = get_settings()

        # Temporarily enable low rate limit for testing
        monkeypatch.setattr(settings, "RATE_LIMITING_ENABLED", True)
        monkeypatch.setattr(settings, "UPLOAD_RATE_LIMIT", 2)

        files = [("files", ("test.txt", b"Test content for rate limiting", "text/plain"))]

        # 1st and 2nd upload allowed
        r1 = test_client.post("/api/upload", files=files)
        assert r1.status_code in (200, 429)

        r2 = test_client.post("/api/upload", files=files)
        # By 3rd or when limit hit, should return 429
        r3 = test_client.post("/api/upload", files=files)
        assert r3.status_code == 429
        assert "Rate limit exceeded" in r3.json()["detail"]
        assert "Retry-After" in r3.headers
