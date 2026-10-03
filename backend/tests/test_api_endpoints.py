"""
Integration tests for FastAPI REST and SSE endpoints in main.py.
Uses FastAPI TestClient with mocked ML and LLM dependencies for fast, deterministic execution.
"""

import io
import json
import pytest
from fastapi.testclient import TestClient

import main
from config import get_settings


class TestAPIEndpoints:
    def test_root_endpoint(self, test_client: TestClient):
        """Verify root endpoint returns welcome message or static frontend."""
        response = test_client.get("/")
        assert response.status_code == 200
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            assert "Veridocs" in response.text or "<!DOCTYPE html>" in response.text or "<html" in response.text
        else:
            data = response.json()
            assert "Welcome to Veridocs API" in data["message"]

    def test_health_check(self, test_client: TestClient):
        """Verify health check endpoint returns expected structure."""
        response = test_client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "models_loaded" in data
        assert "providers_available" in data
        assert isinstance(data["active_sessions"], int)

    def test_upload_invalid_extension(self, test_client: TestClient):
        """Verify rejection when file extension is not permitted."""
        files = [("files", ("script.sh", b"echo hello", "text/x-sh"))]
        response = test_client.post("/api/upload", files=files)
        assert response.status_code == 400
        assert "unsupported type" in response.json()["detail"].lower()

    def test_upload_oversized_file(self, test_client: TestClient, monkeypatch):
        """Verify rejection when file exceeds MAX_FILE_SIZE_MB."""
        settings = get_settings()
        monkeypatch.setattr(settings, "MAX_FILE_SIZE_MB", 1)  # 1MB limit for test
        large_bytes = b"A" * (2 * 1024 * 1024)  # 2MB
        files = [("files", ("large.txt", large_bytes, "text/plain"))]
        response = test_client.post("/api/upload", files=files)
        assert response.status_code == 400
        assert "exceeds" in response.json()["detail"].lower()

    def test_upload_single_txt(self, test_client: TestClient, sample_txt_bytes):
        """Verify successful upload of a valid TXT file."""
        files = [("files", ("report.txt", sample_txt_bytes, "text/plain"))]
        response = test_client.post("/api/upload", files=files)
        assert response.status_code == 200
        data = response.json()

        assert "session_id" in data
        assert data["processed_files"] == 1
        assert data["chunk_count"] > 0
        assert len(data["failed_files"]) == 0
        assert len(data["document_metadata"]) == 1
        assert data["document_metadata"][0]["filename"] == "report.txt"

    def test_upload_multi_file_and_session_continuation(
        self, test_client: TestClient, sample_txt_bytes, sample_docx_bytes
    ):
        """Verify multi-file upload and subsequent upload appending to same session."""
        # 1. Initial upload (TXT + DOCX)
        files = [
            ("files", ("report.txt", sample_txt_bytes, "text/plain")),
            ("files", ("guide.docx", sample_docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
        ]
        resp1 = test_client.post("/api/upload", files=files)
        assert resp1.status_code == 200
        data1 = resp1.json()
        session_id = data1["session_id"]
        assert data1["processed_files"] == 2
        initial_chunks = data1["chunk_count"]

        # 2. Append additional file to the same session
        extra_txt = b"3. Additional Chapter\nThis is appended content for the existing session."
        files2 = [("files", ("append.txt", extra_txt, "text/plain"))]
        resp2 = test_client.post("/api/upload", files=files2, data={"session_id": session_id})
        assert resp2.status_code == 200
        data2 = resp2.json()

        assert data2["session_id"] == session_id
        assert data2["chunk_count"] > initial_chunks
        assert data2["processed_files"] == 1

    def test_get_session_info(self, test_client: TestClient, sample_txt_bytes):
        """Verify session metadata retrieval."""
        # 404 for nonexistent
        resp_404 = test_client.get("/api/sessions/nonexistent-id")
        assert resp_404.status_code == 404

        # Upload to create session
        files = [("files", ("doc.txt", sample_txt_bytes, "text/plain"))]
        upload_resp = test_client.post("/api/upload", files=files).json()
        session_id = upload_resp["session_id"]

        # 200 for valid session
        resp = test_client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert "doc.txt" in data["file_names"]
        assert data["chunk_count"] > 0
        assert data["has_insights"] is True

    def test_get_document_pdf(self, test_client: TestClient, sample_txt_bytes):
        """Verify document file serving endpoint."""
        files = [("files", ("my_notes.txt", sample_txt_bytes, "text/plain"))]
        upload_resp = test_client.post("/api/upload", files=files).json()
        session_id = upload_resp["session_id"]

        # Success serving by index
        resp = test_client.get(f"/api/documents/{session_id}/pdf?file_index=0")
        assert resp.status_code == 200

        # Success serving by document_name
        resp_name = test_client.get(f"/api/documents/{session_id}/pdf?document_name=my_notes.txt")
        assert resp_name.status_code == 200

        # 404 for invalid index
        resp_bad_idx = test_client.get(f"/api/documents/{session_id}/pdf?file_index=99")
        assert resp_bad_idx.status_code == 404

        # 404 for invalid document_name
        resp_bad_name = test_client.get(f"/api/documents/{session_id}/pdf?document_name=ghost.pdf")
        assert resp_bad_name.status_code == 404

    def test_query_flow(self, test_client: TestClient, sample_txt_bytes):
        """Verify question answering endpoint (/api/query)."""
        # Upload document
        files = [("files", ("financials.txt", sample_txt_bytes, "text/plain"))]
        upload_resp = test_client.post("/api/upload", files=files).json()
        session_id = upload_resp["session_id"]

        # 1. 404 on invalid session
        resp_invalid_sess = test_client.post(
            "/api/query",
            json={"session_id": "ghost-session", "question": "What is revenue?"}
        )
        assert resp_invalid_sess.status_code == 404

        # 2. 400 on empty question
        resp_empty_q = test_client.post(
            "/api/query",
            json={"session_id": session_id, "question": "   "}
        )
        assert resp_empty_q.status_code == 400

        # 3. 400 on overly long question
        resp_long_q = test_client.post(
            "/api/query",
            json={"session_id": session_id, "question": "X" * 1001}
        )
        assert resp_long_q.status_code == 400

        # 4. Valid query
        query_payload = {
            "session_id": session_id,
            "question": "What is the revenue for Q3 2024?",
        }
        resp = test_client.post("/api/query", json=query_payload)
        assert resp.status_code == 200
        data = resp.json()

        assert "answer" in data
        assert len(data["sources"]) > 0
        assert data["confidence_score"] is not None
        assert isinstance(data["suggested_followups"], list)

        # 5. Conversation history check
        hist_resp = test_client.get(f"/api/sessions/{session_id}/history")
        assert hist_resp.status_code == 200
        hist_data = hist_resp.json()
        assert len(hist_data["messages"]) == 2  # user + assistant

    def test_query_active_files_filter(self, test_client: TestClient, sample_txt_bytes, sample_docx_bytes):
        """Verify active_files filters context candidates."""
        files = [
            ("files", ("f1.txt", sample_txt_bytes, "text/plain")),
            ("files", ("f2.docx", sample_docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
        ]
        session_id = test_client.post("/api/upload", files=files).json()["session_id"]

        # Query only f1.txt
        resp = test_client.post(
            "/api/query",
            json={
                "session_id": session_id,
                "question": "What is the topic?",
                "active_files": ["f1.txt"]
            }
        )
        assert resp.status_code == 200
        for src in resp.json()["sources"]:
            assert src["source_file"] == "f1.txt"

    def test_stream_query_sse(self, test_client: TestClient, sample_txt_bytes):
        """Verify streaming query endpoint (/api/query/stream) yields SSE events."""
        files = [("files", ("stream_doc.txt", sample_txt_bytes, "text/plain"))]
        session_id = test_client.post("/api/upload", files=files).json()["session_id"]

        resp = test_client.post(
            "/api/query/stream",
            json={"session_id": session_id, "question": "Summarize key points"}
        )
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]

        content = resp.text
        assert "event: token" in content
        assert "event: done" in content

    def test_get_document_insights(self, test_client: TestClient, sample_txt_bytes):
        """Verify document insights endpoint (/api/documents/{id}/insights)."""
        files = [("files", ("insights_doc.txt", sample_txt_bytes, "text/plain"))]
        session_id = test_client.post("/api/upload", files=files).json()["session_id"]

        resp = test_client.get(f"/api/documents/{session_id}/insights")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == session_id
        assert "executive_summary" in data
        assert "suggested_questions" in data
        assert "key_entities" in data
