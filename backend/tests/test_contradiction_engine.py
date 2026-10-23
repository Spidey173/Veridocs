"""
Unit and integration tests for the Forensic Contradiction Engine and endpoint.
"""

import pytest
from fastapi.testclient import TestClient
from main import app
from contradiction_engine import (
    run_cross_document_audit,
    _deterministic_diff,
    AuditDiffReport,
)

from auth import create_access_token

client = TestClient(app)
client.headers["Authorization"] = f"Bearer {create_access_token('audit_test_user')}"


class TestContradictionEngine:
    """Tests for contradiction detection and cross-document comparative audit."""

    def test_deterministic_diff_detects_numerical_mismatch(self):
        chunks_a = [
            {
                "page": 1,
                "text": "Payment shall be rendered within 30 days of invoice date.",
                "raw_text": "Payment shall be rendered within 30 days of invoice date.",
                "section": "Section 4.1 Payment"
            },
            {
                "page": 2,
                "text": "The aggregate liability under this agreement is capped at $1,000,000.",
                "raw_text": "The aggregate liability under this agreement is capped at $1,000,000.",
                "section": "Section 8 Liability"
            }
        ]

        chunks_b = [
            {
                "page": 1,
                "text": "Payment shall be rendered within 60 days of invoice date.",
                "raw_text": "Payment shall be rendered within 60 days of invoice date.",
                "section": "Section 4 Payment Schedule"
            },
            {
                "page": 2,
                "text": "The aggregate liability under this agreement is capped at $250,000.",
                "raw_text": "The aggregate liability under this agreement is capped at $250,000.",
                "section": "Section 8 Damages"
            }
        ]

        report = _deterministic_diff(chunks_a, chunks_b, "Contract_v1.pdf", "Contract_v2.pdf")
        assert isinstance(report, AuditDiffReport)
        assert len(report.conflicts) >= 2
        assert report.alignment_score < 1.0

        topics = [c.topic for c in report.conflicts]
        assert any("Payment" in t for t in topics)
        assert any("Liability" in t for t in topics)

    def test_run_cross_document_audit_empty(self):
        report = run_cross_document_audit([], [], "A.pdf", "B.pdf")
        assert report.alignment_score == 1.0
        assert len(report.conflicts) == 0

    def test_api_audit_contradictions_demo_session(self):
        response = client.post(
            "/api/audit/contradictions",
            json={
                "session_id": "demo-session",
                "doc_a": "SaaS_Agreement_2024_v1.pdf",
                "doc_b": "SaaS_Agreement_2025_Amended.pdf"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["doc_a_name"] == "SaaS_Agreement_2024_v1.pdf"
        assert data["doc_b_name"] == "SaaS_Agreement_2025_Amended.pdf"
        assert len(data["conflicts"]) == 3
        assert data["critical_count"] == 2
        assert data["warning_count"] == 1
        assert "Payment" in data["conflicts"][0]["topic"]
