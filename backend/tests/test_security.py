"""
Security and Multi-Tenant Access Control Tests for Veridocs.
Verifies CORS origin restrictions, tamper-proof token authentication,
gateway API key enforcement, and strict user ownership isolation (anti-IDOR).
"""

import time
import pytest
from fastapi.testclient import TestClient
from pathlib import Path

import main
from config import get_settings
from auth import create_access_token, verify_access_token, UserContext


class TestSecurityAndAccessControl:
    """Test suite verifying access control, token signing, and session isolation."""

    def test_token_generation_and_validation(self):
        """Verify tokens can be created, signed, and validated with UserContext."""
        token = create_access_token(user_id="alice_123", expires_in_hours=2)
        assert isinstance(token, str)
        assert "." in token

        user_ctx = verify_access_token(token)
        assert user_ctx.user_id == "alice_123"
        assert user_ctx.role == "user"
        assert user_ctx.expires_at > time.time()

    def test_token_tampering_rejected(self):
        """Verify that any modification to payload or signature causes 401 rejection."""
        token = create_access_token(user_id="alice_123")
        payload_b64, sig_b64 = token.split(".")

        # Tampered signature
        bad_token = f"{payload_b64}.tampered_sig"
        with pytest.raises(Exception) as excinfo:
            verify_access_token(bad_token)
        assert "401" in str(excinfo.value) or "Invalid token signature" in str(excinfo.value)

    def test_expired_token_rejected(self):
        """Verify that expired tokens are rejected."""
        # Create token that expired 10 seconds ago
        token = create_access_token(user_id="bob", expires_in_hours=-1)
        with pytest.raises(Exception) as excinfo:
            verify_access_token(token)
        assert "401" in str(excinfo.value) or "expired" in str(excinfo.value).lower()

    def test_auth_token_endpoint(self, test_client: TestClient):
        """Verify POST /api/auth/token generates a valid signed bearer token."""
        response = test_client.post("/api/auth/token", json={"user_id": "test_user_42"})
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["user_id"] == "test_user_42"
        assert data["expires_in"] > 0

    def test_unauthenticated_request_rejected(self, sample_txt_bytes, patch_models, mock_llm_service):
        """Verify endpoints reject requests with 401 when no token is supplied."""
        unauthed_client = TestClient(main.app)  # No Authorization header
        files = [("files", ("secret.txt", sample_txt_bytes, "text/plain"))]
        resp = unauthed_client.post("/api/upload", files=files)
        assert resp.status_code == 401
        assert "authentication required" in resp.json()["detail"].lower()

    def test_cross_user_isolation_anti_idor(self, sample_txt_bytes, patch_models, mock_llm_service):
        """
        Verify multi-tenant isolation:
        User A creates a session. User B cannot read, query, inspect, download, or delete User A's session.
        """
        # 1. Setup User A and User B clients with distinct signed identities
        token_a = create_access_token(user_id="user_alice")
        client_a = TestClient(main.app)
        client_a.headers["Authorization"] = f"Bearer {token_a}"

        token_b = create_access_token(user_id="user_bob")
        client_b = TestClient(main.app)
        client_b.headers["Authorization"] = f"Bearer {token_b}"

        # 2. User A uploads a document and gets session_id
        files = [("files", ("contract_alice.txt", sample_txt_bytes, "text/plain"))]
        upload_resp = client_a.post("/api/upload", files=files)
        assert upload_resp.status_code == 200
        session_id = upload_resp.json()["session_id"]

        # 3. User A can view session info and query documents
        assert client_a.get(f"/api/sessions/{session_id}").status_code == 200
        query_resp = client_a.post(
            "/api/query",
            json={"session_id": session_id, "question": "What is the revenue?"}
        )
        assert query_resp.status_code == 200

        # 4. User B attempts to access User A's session -> must be rejected with 403 Forbidden
        idor_info = client_b.get(f"/api/sessions/{session_id}")
        assert idor_info.status_code == 403
        assert "permission" in idor_info.json()["detail"].lower()

        idor_query = client_b.post(
            "/api/query",
            json={"session_id": session_id, "question": "What is the revenue?"}
        )
        assert idor_query.status_code == 403

        idor_pdf = client_b.get(f"/api/documents/{session_id}/pdf")
        assert idor_pdf.status_code == 403

        idor_history = client_b.get(f"/api/sessions/{session_id}/history")
        assert idor_history.status_code == 403

        idor_insights = client_b.get(f"/api/documents/{session_id}/insights")
        assert idor_insights.status_code == 403

        idor_delete = client_b.delete(f"/api/sessions/{session_id}")
        assert idor_delete.status_code == 403

    def test_query_param_token_for_browser_views(self, sample_txt_bytes, patch_models, mock_llm_service):
        """Verify ?token=<token> allows browser PDF and stream requests without headers."""
        token_a = create_access_token(user_id="browser_user")
        client_a = TestClient(main.app)
        client_a.headers["Authorization"] = f"Bearer {token_a}"

        # Upload document
        files = [("files", ("view.txt", sample_txt_bytes, "text/plain"))]
        upload_resp = client_a.post("/api/upload", files=files)
        session_id = upload_resp.json()["session_id"]

        # Request PDF using query param token with a clean client
        clean_client = TestClient(main.app)
        resp = clean_client.get(f"/api/documents/{session_id}/pdf?token={token_a}")
        assert resp.status_code == 200

    def test_cors_origin_headers(self, test_client: TestClient):
        """Verify CORS allows configured origins and handles preflight OPTIONS."""
        settings = get_settings()
        allowed_origin = settings.CORS_ORIGINS[0]

        # Preflight OPTIONS request
        response = test_client.options(
            "/api/upload",
            headers={
                "Origin": allowed_origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "Authorization,Content-Type",
            }
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == allowed_origin

    def test_api_key_gateway_enforcement(self, monkeypatch, sample_txt_bytes, patch_models, mock_llm_service):
        """Verify REQUIRE_API_KEY restricts requests when configured."""
        settings = get_settings()
        monkeypatch.setattr(settings, "REQUIRE_API_KEY", True)
        monkeypatch.setattr(settings, "API_KEY", "gateway_secret_key_999")

        client = TestClient(main.app)
        token = create_access_token(user_id="user_with_token")
        client.headers["Authorization"] = f"Bearer {token}"

        # Without X-API-Key header -> 401
        files = [("files", ("test.txt", sample_txt_bytes, "text/plain"))]
        resp_unauthed = client.post("/api/upload", files=files)
        assert resp_unauthed.status_code == 401
        assert "api key" in resp_unauthed.json()["detail"].lower()

        # With correct X-API-Key header -> 200
        client.headers["X-API-Key"] = "gateway_secret_key_999"
        resp_authed = client.post("/api/upload", files=files)
        assert resp_authed.status_code == 200
