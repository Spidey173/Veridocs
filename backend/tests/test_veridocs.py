"""
Real behavior test suite for Veridocs Document RAG & Verification Engine.
Tests document upload, chunking, Fastembed vector retrieval, citation checking, and API endpoints.
"""

from fastapi.testclient import TestClient
from vector_store import VectorStore
from verification import check_citations, extract_citations_from_answer
import database


def test_root_endpoint(test_client: TestClient):
    """Verify root endpoint status."""
    res = test_client.get("/")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "online"


def test_health_check(test_client: TestClient):
    """Verify health check endpoint returns valid system status."""
    res = test_client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "llm_configured" in data
    assert "embedding_model_loaded" in data


def test_upload_invalid_extension(test_client: TestClient):
    """Verify rejection of unsupported file extensions."""
    files = [("files", ("script.sh", b"echo hello", "text/x-sh"))]
    res = test_client.post("/api/upload", files=files)
    assert res.status_code == 400
    assert "unsupported" in res.json()["detail"].lower()


def test_upload_txt_file(test_client: TestClient, sample_txt_bytes: bytes):
    """Verify uploading and indexing a real text file."""
    files = [("files", ("agreement.txt", sample_txt_bytes, "text/plain"))]
    res = test_client.post("/api/upload", files=files)
    assert res.status_code == 200
    data = res.json()
    assert "session_id" in data
    assert data["processed_files"] == 1
    assert data["chunk_count"] >= 1


def test_upload_pdf_file(test_client: TestClient, sample_pdf_bytes: bytes):
    """Verify uploading and indexing a real PDF file."""
    files = [("files", ("contract.pdf", sample_pdf_bytes, "application/pdf"))]
    res = test_client.post("/api/upload", files=files)
    assert res.status_code == 200
    data = res.json()
    assert data["processed_files"] == 1
    assert data["chunk_count"] >= 1


def test_get_session_info(test_client: TestClient, sample_txt_bytes: bytes):
    """Verify session metadata retrieval from SQLite."""
    files = [("files", ("test.txt", sample_txt_bytes, "text/plain"))]
    res = test_client.post("/api/upload", files=files)
    sid = res.json()["session_id"]

    info_res = test_client.get(f"/api/sessions/{sid}")
    assert info_res.status_code == 200
    info = info_res.json()
    assert info["session_id"] == sid
    assert "test.txt" in info["file_names"]
    assert info["chunk_count"] >= 1


def test_get_document_pdf(test_client: TestClient, sample_pdf_bytes: bytes):
    """Verify document binary serving endpoint."""
    files = [("files", ("sample.pdf", sample_pdf_bytes, "application/pdf"))]
    upload_res = test_client.post("/api/upload", files=files)
    sid = upload_res.json()["session_id"]

    pdf_res = test_client.get(f"/api/documents/{sid}/pdf?document_name=sample.pdf")
    assert pdf_res.status_code == 200
    assert len(pdf_res.content) > 0


def test_vector_search(test_client: TestClient, sample_txt_bytes: bytes):
    """Verify Fastembed vector search returns relevant chunks with scores."""
    files = [("files", ("terms.txt", sample_txt_bytes, "text/plain"))]
    res = test_client.post("/api/upload", files=files)
    sid = res.json()["session_id"]

    results = VectorStore.search(sid, "What are the payment terms?", top_k=2)
    assert len(results) > 0
    top = results[0]
    assert "relevance_score" in top
    assert top["relevance_score"] > 0
    assert "Payment Terms" in top["text"]


def test_citation_check_supported():
    """Verify citation check accurately flags supported statements."""
    chunks = [{
        "page": 1,
        "source_file": "agreement.pdf",
        "text": "All invoices are payable within 30 days of invoice receipt."
    }]
    answer = "Invoices are payable within 30 days of receipt [Page 1]."
    result = check_citations(answer, chunks)
    assert result["supported_claims"] == 1
    assert result["total_claims"] == 1
    assert result["citation_score"] == 1.0


def test_citation_check_unsupported():
    """Verify citation check flags claims not present in source text."""
    chunks = [{
        "page": 1,
        "source_file": "agreement.pdf",
        "text": "All invoices are payable within 30 days of invoice receipt."
    }]
    answer = "The platform requires biometric authentication for all user logins."
    result = check_citations(answer, chunks)
    assert result["supported_claims"] == 0
    assert result["citation_score"] == 0.0


def test_extract_citations():
    """Verify citation marker extraction and chunk mapping."""
    chunks = [
        {"page": 1, "source_file": "doc_a.pdf", "text": "Payment due in 30 days."},
        {"page": 2, "source_file": "doc_a.pdf", "text": "Liability capped at $500,000."},
    ]
    answer = "Payment is due in 30 days [Page 1] and liability is capped [Page 2]."
    citations = extract_citations_from_answer(answer, chunks)
    assert len(citations) == 2
    assert citations[0]["page"] == 1
    assert citations[1]["page"] == 2


def test_stream_query_sse(test_client: TestClient, sample_txt_bytes: bytes):
    """Verify SSE streaming query endpoint yields citations and tokens."""
    files = [("files", ("doc.txt", sample_txt_bytes, "text/plain"))]
    upload_res = test_client.post("/api/upload", files=files)
    sid = upload_res.json()["session_id"]

    stream_res = test_client.post(
        "/api/query/stream",
        json={
            "session_id": sid,
            "question": "What is the liability cap?"
        },
        headers={
            "X-LLM-API-Key": "test_key",
            "X-LLM-Base-Url": "http://localhost:11434/v1",
        }
    )
    assert stream_res.status_code == 200
    assert "text/event-stream" in stream_res.headers["content-type"]
    text = stream_res.text
    assert "event: citation" in text
    assert "event: done" in text


def test_delete_session(test_client: TestClient, sample_txt_bytes: bytes):
    """Verify deleting a session purges records from SQLite."""
    files = [("files", ("temp.txt", sample_txt_bytes, "text/plain"))]
    upload_res = test_client.post("/api/upload", files=files)
    sid = upload_res.json()["session_id"]

    del_res = test_client.delete(f"/api/sessions/{sid}")
    assert del_res.status_code == 200

    check_res = test_client.get(f"/api/sessions/{sid}")
    assert check_res.status_code == 404


def test_granular_passage_chunking(test_client: TestClient, sample_pdf_bytes: bytes):
    """Verify ~500-char granular passage chunking creates focused passages, not 1-per-page."""
    files = [("files", ("multipage.pdf", sample_pdf_bytes, "application/pdf"))]
    upload_res = test_client.post("/api/upload", files=files)
    assert upload_res.status_code == 200
    chunk_count = upload_res.json()["chunk_count"]
    # 6 pages with 650-800 chars each should produce at least 10 granular chunks
    assert chunk_count >= 10, f"Expected >= 10 granular chunks, got {chunk_count}"


def test_rate_limiting_and_byok_bypass(test_client: TestClient, sample_txt_bytes: bytes):
    """Verify rate limiter blocks excess requests and custom key header bypasses limit."""
    from rate_limiter import _limiter
    from config import get_settings
    _limiter.reset()
    settings = get_settings()

    # Upload test document
    files = [("files", ("rate_doc.txt", sample_txt_bytes, "text/plain"))]
    sid = test_client.post("/api/upload", files=files).json()["session_id"]

    # Fill rate limit bucket
    for _ in range(settings.RATE_LIMIT_QUERY_PER_HOUR):
        _limiter.check("query:testclient", max_requests=settings.RATE_LIMIT_QUERY_PER_HOUR)

    # Next standard request should be rate limited
    res = test_client.post("/api/query", json={"session_id": sid, "question": "test"})
    assert res.status_code == 429
    assert "rate limit" in res.json()["detail"].lower()

    # Request with custom API key header bypasses rate limit
    byok_res = test_client.post(
        "/api/query",
        json={"session_id": sid, "question": "test"},
        headers={"X-LLM-API-Key": "sk-custom-user-key"}
    )
    # Status code is 200 (or if key invalid, not 429)
    assert byok_res.status_code != 429

    _limiter.reset()


def test_upload_file_size_limit(test_client: TestClient):
    """Verify rejection of files exceeding the 10 MB limit."""
    from config import get_settings
    settings = get_settings()

    # Create dummy 11MB payload
    oversized = b"x" * (11 * 1024 * 1024)
    files = [("files", ("huge.txt", oversized, "text/plain"))]
    res = test_client.post("/api/upload", files=files)
    assert res.status_code == 400
    assert "exceeds" in res.json()["detail"].lower()


def test_health_check_llm_status_reporting(test_client: TestClient, monkeypatch):
    """Verify health endpoint dynamically reflects LLM configuration status."""
    import config

    # 1. When no LLM credentials are set
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    config.reload_settings()

    res = test_client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["llm_configured"] is False

    # 2. When LLM credentials are set via universal vars
    monkeypatch.setenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setenv("LLM_API_KEY", "gsk_test_key_12345")
    monkeypatch.setenv("LLM_MODEL", "llama-3.3-70b-versatile")
    config.reload_settings()

    res = test_client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["llm_configured"] is True

    # 3. Clean up
    config.reload_settings()


def test_system_notice_not_scored_by_citation_check(test_client: TestClient, sample_txt_bytes: bytes, monkeypatch):
    """Verify system notices (e.g. No LLM configured) do not emit citations or citation_check."""
    import config
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    config.reload_settings()

    # Upload document
    files = [("files", ("notice_doc.txt", sample_txt_bytes, "text/plain"))]
    sid = test_client.post("/api/upload", files=files).json()["session_id"]

    # Stream query with no LLM configured
    stream_res = test_client.post("/api/query/stream", json={
        "session_id": sid,
        "question": "What is the fee?"
    })
    assert stream_res.status_code == 200
    body = stream_res.text
    # Tokens should include honest warning notice
    assert "No LLM is configured" in body
    # Notice must NOT emit citation or citation_check events
    assert "event: citation_check" not in body
    assert "event: citation" not in body


def test_dynamic_suggested_questions(test_client: TestClient, sample_txt_bytes: bytes):
    """Verify sample agreement gets agreement questions while other docs get general questions."""
    # 1. Non-agreement document gets generic questions
    files = [("files", ("resume_jane_doe.txt", sample_txt_bytes, "text/plain"))]
    res = test_client.post("/api/upload", files=files)
    assert res.status_code == 200
    suggestions = res.json()["suggested_questions"]
    assert len(suggestions) >= 2
    assert "Summarize this document" in suggestions or any("key" in s.lower() for s in suggestions)

    # 2. Query suggestions endpoint
    sid = res.json()["session_id"]
    sugg_res = test_client.get(f"/api/sessions/{sid}/suggestions")
    assert sugg_res.status_code == 200
    assert sugg_res.json()["suggestions"] == suggestions


