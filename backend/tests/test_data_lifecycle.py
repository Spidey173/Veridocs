"""
Data Lifecycle & Retention Tests for Veridocs.
Verifies secure session deletion, individual document removal,
path traversal protection, and retention cleanup policies.
"""

import time
import json
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

import main
from config import get_settings
from conversation import get_conversation_manager
from main import _safe_delete_file, cleanup_expired_sessions


class TestDataLifecycle:
    """Test suite verifying document/session deletion and data retention policies."""

    def test_session_deletion_endpoint(self, test_client: TestClient, sample_txt_bytes):
        """
        Verify DELETE /api/sessions/{session_id} securely removes:
        - Uploaded files from disk
        - Persisted session folder on disk
        - Conversation history
        - In-memory session record
        """
        # 1. Upload file to create session
        files = [("files", ("contract.txt", sample_txt_bytes, "text/plain"))]
        upload_resp = test_client.post("/api/upload", files=files)
        assert upload_resp.status_code == 200
        session_id = upload_resp.json()["session_id"]

        settings = get_settings()
        session_dir = Path(settings.UPLOAD_DIR) / "sessions" / session_id
        session_data = main.sessions[session_id]
        saved_file_path = Path(session_data["file_paths"][0])

        assert saved_file_path.exists(), "Uploaded file should exist on disk"
        assert session_dir.exists(), "Persisted session directory should exist on disk"

        # 2. Add message to conversation history
        cm = get_conversation_manager()
        cm.add_message(session_id, "user", "What is the fee?")
        assert len(cm.get_history(session_id)) == 1

        # 3. Call DELETE /api/sessions/{session_id}
        del_resp = test_client.delete(f"/api/sessions/{session_id}")
        assert del_resp.status_code == 200
        data = del_resp.json()
        assert data["status"] == "success"
        assert data["deleted_files_count"] >= 1

        # 4. Verify all assets are purged
        assert not saved_file_path.exists(), "Uploaded file must be removed from disk"
        assert not session_dir.exists(), "Session folder on disk must be removed"
        assert session_id not in main.sessions, "Session must be removed from in-memory dictionary"
        assert len(cm.get_history(session_id)) == 0, "Conversation history must be cleared"

        # 5. Subsequent access returns 404
        assert test_client.get(f"/api/sessions/{session_id}").status_code == 404

    def test_document_deletion_from_session(
        self, test_client: TestClient, sample_txt_bytes, sample_docx_bytes
    ):
        """Verify deleting a single document removes its file and chunks while keeping other documents."""
        # Upload 2 documents
        files = [
            ("files", ("doc1.txt", sample_txt_bytes, "text/plain")),
            ("files", ("doc2.docx", sample_docx_bytes, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
        ]
        upload_resp = test_client.post("/api/upload", files=files)
        session_id = upload_resp.json()["session_id"]
        initial_chunks = upload_resp.json()["chunk_count"]

        # Delete doc1.txt
        del_resp = test_client.delete(f"/api/sessions/{session_id}/documents/doc1.txt")
        assert del_resp.status_code == 200
        data = del_resp.json()
        assert data["removed_document"] == "doc1.txt"
        assert data["remaining_documents"] == ["doc2.docx"]
        assert data["remaining_chunks"] < initial_chunks

        # Verify session info
        info_resp = test_client.get(f"/api/sessions/{session_id}")
        assert info_resp.status_code == 200
        assert info_resp.json()["file_names"] == ["doc2.docx"]

    def test_safe_delete_path_traversal_prevention(self, tmp_path):
        """Verify _safe_delete_file rejects path traversal attempts outside UPLOAD_DIR."""
        settings = get_settings()
        outside_file = tmp_path / "critical_system_file.txt"
        outside_file.write_text("critical data")

        # Attempt to delete file outside upload dir
        result = _safe_delete_file(outside_file)
        assert result is False
        assert outside_file.exists(), "File outside UPLOAD_DIR must NOT be deleted"

        # Relative traversal path attempt
        traversal_path = Path(settings.UPLOAD_DIR) / ".." / "critical_system_file.txt"
        result_traversal = _safe_delete_file(traversal_path)
        assert result_traversal is False
        assert outside_file.exists()

    def test_retention_cleanup_purges_expired_data(self, test_client: TestClient, sample_txt_bytes):
        """Verify cleanup_expired_sessions purges data older than RETENTION_HOURS."""
        # 1. Upload to create a session
        files = [("files", ("old_contract.txt", sample_txt_bytes, "text/plain"))]
        upload_resp = test_client.post("/api/upload", files=files)
        session_id = upload_resp.json()["session_id"]

        settings = get_settings()
        file_path = Path(main.sessions[session_id]["file_paths"][0])
        session_dir = Path(settings.UPLOAD_DIR) / "sessions" / session_id

        # 2. Artificially backdate session timestamps to simulate expiry (e.g. 48 hours ago)
        old_timestamp = time.time() - (48 * 3600)
        main.sessions[session_id]["created_at"] = old_timestamp

        meta_file = session_dir / "session.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            meta["created_at"] = old_timestamp
            meta_file.write_text(json.dumps(meta), encoding="utf-8")

        # 3. Run retention cleanup with 24-hour max age
        result = cleanup_expired_sessions(max_age_hours=24)
        assert result["purged_sessions"] >= 1
        assert result["purged_files"] >= 1

        # 4. Verify expired assets are purged
        assert session_id not in main.sessions
        assert not file_path.exists()
        assert not session_dir.exists()

    def test_admin_cleanup_endpoint(self, sample_txt_bytes):
        """Verify POST /api/admin/cleanup endpoint triggers retention purging when authorized as admin."""
        from auth import create_access_token
        admin_token = create_access_token(user_id="lifecycle_admin", role="admin")
        admin_client = TestClient(main.app)
        admin_client.headers["Authorization"] = f"Bearer {admin_token}"

        resp = admin_client.post("/api/admin/cleanup?max_age_hours=24")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "purged_sessions" in data
        assert "purged_files" in data
