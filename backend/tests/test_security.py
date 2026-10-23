"""
Security and Multi-Tenant Access Control Tests for Veridocs.
Verifies CORS origin restrictions, tamper-proof token authentication,
gateway API key enforcement, and strict user ownership isolation (anti-IDOR).
"""

import time
import json
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
        """Verify POST /api/auth/demo-token generates a valid signed demo bearer token."""
        response = test_client.post("/api/auth/demo-token")
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["mode"] == "demo"
        assert "demo_usr_" in data["user_id"]
        assert data["expires_in"] > 0

    def test_demo_token_disabled_in_production(self, test_client: TestClient, monkeypatch):
        """Verify demo token issuance is rejected with 403 in production or gateway mode."""
        settings = get_settings()
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")
        resp = test_client.post("/api/auth/demo-token")
        assert resp.status_code == 403
        assert "disabled in production" in resp.json()["detail"].lower()

    def test_production_fails_without_strong_secret(self, monkeypatch):
        """Verify validation fails fast on startup in production if secret is missing or insecure."""
        settings = get_settings()
        monkeypatch.setattr(settings, "ENVIRONMENT", "production")

        monkeypatch.setattr(settings, "AUTH_SECRET_KEY", "")
        with pytest.raises(RuntimeError) as excinfo:
            settings.validate_production_configuration()
        assert "AUTH_SECRET_KEY is required" in str(excinfo.value)

        monkeypatch.setattr(settings, "AUTH_SECRET_KEY", "too-short-secret")
        with pytest.raises(RuntimeError) as excinfo:
            settings.validate_production_configuration()
        assert "too short" in str(excinfo.value)

        monkeypatch.setattr(settings, "AUTH_SECRET_KEY", "veridocs-default-secret-key-change-in-production")
        with pytest.raises(RuntimeError) as excinfo:
            settings.validate_production_configuration()
        assert "insecure default placeholder" in str(excinfo.value)

        # In production gateway mode, fail if GATEWAY_SHARED_SECRET is not configured to prevent header spoofing
        monkeypatch.setattr(settings, "AUTH_SECRET_KEY", "strong-32-character-secret-key-for-test-suite")
        monkeypatch.setattr(settings, "AUTH_MODE", "gateway")
        monkeypatch.setattr(settings, "GATEWAY_SHARED_SECRET", "")
        monkeypatch.setattr(settings, "REQUIRE_API_KEY", False)
        with pytest.raises(RuntimeError) as excinfo:
            settings.validate_production_configuration()
        assert "GATEWAY_SHARED_SECRET" in str(excinfo.value)

    def test_gateway_trusted_identity_header(self, monkeypatch, sample_txt_bytes, patch_models, mock_llm_service):
        """Verify gateway mode authenticates through trusted upstream headers without client tokens."""
        settings = get_settings()
        monkeypatch.setattr(settings, "AUTH_MODE", "gateway")
        monkeypatch.setattr(settings, "GATEWAY_SHARED_SECRET", "")  # Unrestricted gateway mode (internal VPC)

        gw_client = TestClient(main.app)
        gw_client.headers["X-Consumer-Custom-ID"] = "corp_employee_99"
        gw_client.headers["X-Consumer-Role"] = "user"

        files = [("files", ("corp_policy.txt", sample_txt_bytes, "text/plain"))]
        resp = gw_client.post("/api/upload", files=files)
        assert resp.status_code == 200
        session_id = resp.json()["session_id"]

        # Read session info as same employee
        info_resp = gw_client.get(f"/api/sessions/{session_id}")
        assert info_resp.status_code == 200

        # Different employee trying to access session -> 403 Forbidden
        other_gw_client = TestClient(main.app)
        other_gw_client.headers["X-Consumer-Custom-ID"] = "different_employee_12"
        other_resp = other_gw_client.get(f"/api/sessions/{session_id}")
        assert other_resp.status_code == 403

    def test_gateway_shared_secret_enforcement(self, monkeypatch, sample_txt_bytes, patch_models, mock_llm_service):
        """Verify that when GATEWAY_SHARED_SECRET is set, requests without valid gateway secret header are rejected."""
        settings = get_settings()
        monkeypatch.setattr(settings, "AUTH_MODE", "gateway")
        monkeypatch.setattr(settings, "GATEWAY_SHARED_SECRET", "super-secret-gateway-token-1234")

        # 1. Attacker tries to send gateway identity headers directly without gateway secret -> 401 Unauthorized
        spoof_client = TestClient(main.app)
        spoof_client.headers["X-Consumer-Custom-ID"] = "victim_user"
        files = [("files", ("spoof.txt", sample_txt_bytes, "text/plain"))]
        resp = spoof_client.post("/api/upload", files=files)
        assert resp.status_code == 401
        assert "untrusted gateway" in resp.json()["detail"].lower()

        # 2. Attacker provides wrong gateway secret -> 401 Unauthorized
        spoof_client.headers["X-Gateway-Secret"] = "wrong-secret"
        resp = spoof_client.post("/api/upload", files=files)
        assert resp.status_code == 401

        # 3. Legitimate gateway provides matching gateway secret -> 200 OK
        valid_gw_client = TestClient(main.app)
        valid_gw_client.headers["X-Consumer-Custom-ID"] = "corp_employee_1"
        valid_gw_client.headers["X-Gateway-Secret"] = "super-secret-gateway-token-1234"
        resp = valid_gw_client.post("/api/upload", files=files)
        assert resp.status_code == 200

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

    def test_session_missing_ownership_rejected(self, test_client: TestClient, sample_txt_bytes):
        """Verify sessions on disk or in memory with missing or null ownership are denied (403)."""
        files = [("files", ("test.txt", sample_txt_bytes, "text/plain"))]
        upload_resp = test_client.post("/api/upload", files=files)
        session_id = upload_resp.json()["session_id"]

        # Strip ownership from session
        main.sessions[session_id]["owner_id"] = None
        session_dir = Path(get_settings().UPLOAD_DIR) / "sessions" / session_id
        meta_file = session_dir / "session.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            meta["owner_id"] = None
            meta_file.write_text(json.dumps(meta), encoding="utf-8")

        # Subsequent access must be rejected with 403 Forbidden
        resp = test_client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 403
        assert "ownership is missing" in resp.json()["detail"].lower()

    def test_query_param_token_rejected_for_urls(self, sample_txt_bytes, patch_models, mock_llm_service):
        """Verify ?token=<token> in URLs is rejected to prevent token leakage in history and logs."""
        token_a = create_access_token(user_id="browser_user")
        client_a = TestClient(main.app)
        client_a.headers["Authorization"] = f"Bearer {token_a}"

        # Upload document
        files = [("files", ("view.txt", sample_txt_bytes, "text/plain"))]
        upload_resp = client_a.post("/api/upload", files=files)
        session_id = upload_resp.json()["session_id"]

        # Request PDF using query param token with a clean client (no header)
        clean_client = TestClient(main.app)
        resp = clean_client.get(f"/api/documents/{session_id}/pdf?token={token_a}")
        assert resp.status_code == 401
        assert "authentication required" in resp.json()["detail"].lower()

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

    def test_retention_cleanup_requires_admin_role_and_valid_bounds(self, test_client: TestClient, monkeypatch):
        """Verify ordinary users cannot trigger admin cleanup, and retention bounds are strictly enforced."""
        # Regular user token (role="user") -> 403 Forbidden
        resp = test_client.post("/api/admin/cleanup")
        assert resp.status_code == 403
        assert "administrator privileges required" in resp.json()["detail"].lower()

        # Admin token (role="admin")
        admin_token = create_access_token(user_id="sys_admin", role="admin")
        admin_client = TestClient(main.app)
        admin_client.headers["Authorization"] = f"Bearer {admin_token}"

        # Invalid bounds (< 1 hour)
        resp_bad_min = admin_client.post("/api/admin/cleanup?max_age_hours=0")
        assert resp_bad_min.status_code == 400
        assert "between 1 and 720" in resp_bad_min.json()["detail"]

        # Invalid bounds (> 720 hours)
        resp_bad_max = admin_client.post("/api/admin/cleanup?max_age_hours=1000")
        assert resp_bad_max.status_code == 400

        # Valid bounds
        resp_ok = admin_client.post("/api/admin/cleanup?max_age_hours=24")
        assert resp_ok.status_code == 200
        assert resp_ok.json()["status"] == "success"

        # Admin API Key header
        settings = get_settings()
        monkeypatch.setattr(settings, "ADMIN_API_KEY", "cron_admin_secret_key_456")
        cron_client = TestClient(main.app)
        cron_client.headers["X-Admin-Key"] = "cron_admin_secret_key_456"
        cron_resp = cron_client.post("/api/admin/cleanup?max_age_hours=48")
        assert cron_resp.status_code == 200
        assert cron_resp.json()["status"] == "success"
