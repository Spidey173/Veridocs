"""
Unit and integration tests for the Forensic Contradiction Engine and endpoint.
"""

from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from main import app
from contradiction_engine import (
    run_cross_document_audit,
    _deterministic_diff,
    AuditDiffReport,
    get_audit_cache,
)
from rate_limiter import get_token_limiter
from config import get_settings

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

    def test_api_audit_contradictions_demo_session(self, test_client: TestClient):
        response = test_client.post(
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

    def test_audit_caching_returns_cached_report_with_zero_llm_calls(self):
        """Verify that repeat audits of unchanged chunks hit the content cache with zero token consumption."""
        cache = get_audit_cache()
        cache.clear()

        chunks_a = [{"page": 1, "text": "Net 30 payment terms.", "section": "Payment"}]
        chunks_b = [{"page": 1, "text": "Net 60 payment terms.", "section": "Payment"}]

        mock_llm = MagicMock()
        mock_llm.provider = "openai"
        mock_llm.model = "gpt-4o-mini"
        mock_llm.client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content='{"alignment_score": 0.7, "summary": "Payment mismatch", "conflicts": []}'))
        ]

        # First run: populates cache
        report1 = run_cross_document_audit(chunks_a, chunks_b, "A.pdf", "B.pdf", llm_service=mock_llm)
        call_count_after_first = mock_llm.client.chat.completions.create.call_count

        # Second run: must hit cache without invoking mock LLM
        report2 = run_cross_document_audit(chunks_a, chunks_b, "A.pdf", "B.pdf", llm_service=mock_llm)
        call_count_after_second = mock_llm.client.chat.completions.create.call_count

        assert report1.alignment_score == report2.alignment_score
        assert call_count_after_second == call_count_after_first

    def test_two_phase_hybrid_audit_short_circuits_non_conflicting_documents(self):
        """Verify non-conflicting documents short-circuit Phase 1 with 0 LLM calls (100% token savings)."""
        cache = get_audit_cache()
        cache.clear()

        # Both documents have identical standard terms
        chunks_a = [{"page": 1, "text": "Invoices are payable within 30 days of receipt.", "section": "Payment"}]
        chunks_b = [{"page": 1, "text": "Invoices are payable within 30 days of receipt.", "section": "Payment"}]

        mock_llm = MagicMock()
        mock_llm.provider = "openai"

        report = run_cross_document_audit(chunks_a, chunks_b, "Master_v1.pdf", "Master_v2.pdf", llm_service=mock_llm)
        assert report.alignment_score == 1.0
        assert len(report.conflicts) == 0
        # Mock LLM must NEVER have been called!
        assert mock_llm.client.chat.completions.create.call_count == 0

    def test_targeted_verification_prompt_slashes_prompt_size(self):
        """Verify that Phase 2 builds a compact targeted candidate prompt rather than dumping entire documents."""
        cache = get_audit_cache()
        cache.clear()

        chunks_a = [
            {"page": 1, "text": "Payment shall be rendered within 30 days of invoice date.", "section": "Section 4.1"},
            {"page": 2, "text": "General legal boilerplate paragraph with standard clauses." * 20, "section": "General"}
        ]
        chunks_b = [
            {"page": 1, "text": "Payment shall be rendered within 60 days of invoice date.", "section": "Section 4.1"},
            {"page": 2, "text": "General legal boilerplate paragraph with standard clauses." * 20, "section": "General"}
        ]

        captured_prompts = []

        mock_llm = MagicMock()
        mock_llm.provider = "openai"
        mock_llm.model = "gpt-4o-mini"

        def mock_chat_create(**kwargs):
            messages = kwargs.get("messages", [])
            for m in messages:
                captured_prompts.append(m.get("content", ""))
            return MagicMock(choices=[MagicMock(message=MagicMock(content='{"alignment_score": 0.8, "summary": "Payment mismatch", "conflicts": []}'))])

        mock_llm.client.chat.completions.create.side_effect = mock_chat_create

        run_cross_document_audit(chunks_a, chunks_b, "DocA.pdf", "DocB.pdf", llm_service=mock_llm)

        assert len(captured_prompts) > 0
        prompt_text = captured_prompts[0]
        # Must contain candidate conflict snippet
        assert "Payment & Invoicing" in prompt_text or "Candidate #1" in prompt_text
        # Prompt must be concise and targeted (far less than the 12,000 char unbudgeted limit)
        assert len(prompt_text) < 2500

    def test_token_limiter_protects_against_tpm_overrun(self):
        """Verify that when sliding-window token budget is exhausted, audit falls back to deterministic diff."""
        cache = get_audit_cache()
        cache.clear()

        limiter = get_token_limiter()
        limiter.max_tpm = None
        limiter.reset()

        # Artificially cap token limiter to trigger budget protection
        limiter.max_tpm = 100

        chunks_a = [{"page": 1, "text": "Invoices are payable within 30 days of receipt.", "section": "Payment"}]
        chunks_b = [{"page": 1, "text": "Invoices are payable within 90 days of receipt.", "section": "Payment"}]

        mock_llm = MagicMock()
        mock_llm.provider = "openai"

        report = run_cross_document_audit(chunks_a, chunks_b, "A.pdf", "B.pdf", llm_service=mock_llm)

        # Must have fallen back gracefully without crashing or calling external LLM
        assert len(report.conflicts) >= 1
        assert "token budget" in report.summary or "deterministic" in report.summary.lower()
        assert mock_llm.client.chat.completions.create.call_count == 0

        limiter.max_tpm = None
        limiter.reset()

    def test_api_audit_contradictions_rate_limiting(self, test_client: TestClient, monkeypatch):
        """Verify that the /api/audit/contradictions endpoint enforces client request rate limiting."""
        settings = get_settings()
        monkeypatch.setattr(settings, "RATE_LIMITING_ENABLED", True)
        monkeypatch.setattr(settings, "AUDIT_RATE_LIMIT", 2)

        # First request: 200 OK
        r1 = test_client.post(
            "/api/audit/contradictions",
            json={"session_id": "demo-session", "doc_a": "A.pdf", "doc_b": "B.pdf"}
        )
        assert r1.status_code == 200

        # Second request: 200 OK
        r2 = test_client.post(
            "/api/audit/contradictions",
            json={"session_id": "demo-session", "doc_a": "A.pdf", "doc_b": "B.pdf"}
        )
        assert r2.status_code == 200

        # Third request: 429 Too Many Requests
        r3 = test_client.post(
            "/api/audit/contradictions",
            json={"session_id": "demo-session", "doc_a": "A.pdf", "doc_b": "B.pdf"}
        )
        assert r3.status_code == 429
        assert "Rate limit exceeded" in r3.json()["detail"]

    def test_transient_llm_rate_limit_error_falls_back_gracefully(self):
        """Verify that when an external LLM returns a 429 rate limit error, the audit gracefully falls back to deterministic diff."""
        cache = get_audit_cache()
        cache.clear()
        limiter = get_token_limiter()
        limiter.max_tpm = None
        limiter.reset()

        chunks_a = [{"page": 1, "text": "Liability is capped at $1,000,000.", "section": "Liability"}]
        chunks_b = [{"page": 1, "text": "Liability is capped at $100,000.", "section": "Liability"}]

        mock_llm = MagicMock()
        mock_llm.provider = "openai"
        mock_llm.model = "gpt-4o-mini"
        mock_llm.client.chat.completions.create.side_effect = RuntimeError("429 Too Many Requests: Rate limit reached")

        # Must NOT raise exception; must catch 429 and return deterministic report
        report = run_cross_document_audit(chunks_a, chunks_b, "A.pdf", "B.pdf", llm_service=mock_llm)
        assert isinstance(report, AuditDiffReport)
        assert len(report.conflicts) >= 1
        assert "Liability" in report.conflicts[0].topic
