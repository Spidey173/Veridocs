"""
Unit and integration tests for Celery/Redis asynchronous background job processing.
Validates async upload, real-time progress tracking, SEC 10-K item section extraction,
multi-tenant anti-IDOR isolation, and job lifecycle management.
"""

import time
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from auth import create_access_token
from job_tracker import get_job_tracker
from pdf_processor import detect_sections
from tasks import process_document_job


class TestAsyncJobs:
    """Test suite for asynchronous document job processing and Celery/Redis infrastructure."""

    def test_submit_async_job_success(self, test_client: TestClient, sample_txt_bytes):
        """Verify successful submission of an async document processing job returning 202."""
        files = [("files", ("annual_filing_10k.txt", sample_txt_bytes, "text/plain"))]
        response = test_client.post("/api/jobs/upload", files=files)

        assert response.status_code == 202
        data = response.json()
        assert "job_id" in data
        assert data["job_id"].startswith("job_")
        assert data["status"] in ("queued", "processing", "completed")
        assert data["file_names"] == ["annual_filing_10k.txt"]
        assert "queued" in data["message"].lower() or "progress" in data["message"].lower()

    def test_get_job_status_and_query_session(self, test_client: TestClient, sample_txt_bytes):
        """Verify job status polling, progress tracking, and subsequent query execution on the session."""
        files = [("files", ("sec_10k_report.txt", sample_txt_bytes, "text/plain"))]
        submit_res = test_client.post("/api/upload/async", files=files)
        assert submit_res.status_code == 202
        job_id = submit_res.json()["job_id"]

        # Poll status until complete (within 5 seconds)
        completed = False
        final_data = None
        for _ in range(50):
            status_res = test_client.get(f"/api/jobs/{job_id}")
            assert status_res.status_code == 200
            final_data = status_res.json()
            if final_data["status"] == "completed":
                completed = True
                break
            time.sleep(0.1)

        assert completed, f"Job did not complete in time: {final_data}"
        assert final_data["progress"]["percent"] == 100.0
        assert final_data["session_id"] is not None
        assert final_data["result_summary"]["chunk_count"] > 0

        # Query the session created asynchronously by the job
        session_id = final_data["session_id"]
        query_payload = {
            "session_id": session_id,
            "question": "What was the revenue and profit in Q3 2024?"
        }
        query_res = test_client.post("/api/query", json=query_payload)
        assert query_res.status_code == 200
        q_data = query_res.json()
        assert "answer" in q_data
        assert len(q_data["sources"]) > 0

    def test_async_job_anti_idor_isolation(self, test_client: TestClient, sample_txt_bytes):
        """Verify strict multi-tenant isolation: User B cannot inspect or delete User A's background job."""
        # 1. User A creates job
        files = [("files", ("confidential_10k.txt", sample_txt_bytes, "text/plain"))]
        submit_res = test_client.post("/api/jobs/upload", files=files)
        assert submit_res.status_code == 202
        job_id = submit_res.json()["job_id"]

        # 2. User B tries to read User A's job
        token_b = create_access_token(user_id="intruder_user_b", role="user")
        intruder_client = TestClient(test_client.app)
        intruder_client.headers["Authorization"] = f"Bearer {token_b}"

        read_res = intruder_client.get(f"/api/jobs/{job_id}")
        assert read_res.status_code == 403
        assert "access denied" in read_res.json()["detail"].lower()

        # 3. User B tries to delete User A's job
        delete_res = intruder_client.delete(f"/api/jobs/{job_id}")
        assert delete_res.status_code == 403
        assert "access denied" in delete_res.json()["detail"].lower()

    def test_list_jobs_for_authenticated_user(self, test_client: TestClient, sample_txt_bytes):
        """Verify listing jobs returns only those belonging to the authenticated user."""
        files = [("files", ("doc_1.txt", sample_txt_bytes, "text/plain"))]
        test_client.post("/api/jobs/upload", files=files)

        res = test_client.get("/api/jobs")
        assert res.status_code == 200
        data = res.json()
        assert data["total"] >= 1
        assert all(j["owner_id"] == "default_test_user" for j in data["jobs"])

    def test_delete_job_endpoint(self, test_client: TestClient, sample_txt_bytes):
        """Verify cancellation and deletion of a background job."""
        files = [("files", ("temp_doc.txt", sample_txt_bytes, "text/plain"))]
        submit_res = test_client.post("/api/jobs/upload", files=files)
        job_id = submit_res.json()["job_id"]

        del_res = test_client.delete(f"/api/jobs/{job_id}")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "deleted"

        get_res = test_client.get(f"/api/jobs/{job_id}")
        assert get_res.status_code == 404

    def test_invalid_file_extension_rejected(self, test_client: TestClient):
        """Verify async upload rejects prohibited extensions."""
        files = [("files", ("malware.exe", b"binary content", "application/octet-stream"))]
        res = test_client.post("/api/jobs/upload", files=files)
        assert res.status_code == 400
        assert "unsupported type" in res.json()["detail"].lower()

    def test_sec_10k_heading_detection(self):
        """Verify detection of canonical SEC 10-K Item sections and Parts."""
        sample_sec_10k = (
            "PART I\n\n"
            "ITEM 1. BUSINESS\n"
            "Overview of the company's hardware, software, and services businesses.\n\n"
            "ITEM 1A. RISK FACTORS\n"
            "Global macroeconomic conditions may impact customer purchasing decisions.\n\n"
            "PART II\n\n"
            "ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION\n"
            "Net sales were $383.3 billion during the fiscal year.\n\n"
            "ITEM 8. FINANCIAL STATEMENTS AND SUPPLEMENTARY DATA\n"
            "Consolidated Statements of Operations and Consolidated Balance Sheets.\n\n"
            "ITEM 9A. CONTROLS AND PROCEDURES\n"
            "Evaluation of disclosure controls and procedures."
        )

        sections = detect_sections(sample_sec_10k)
        headings = [s["heading"] for s in sections]

        assert any("PART I" in h for h in headings)
        assert any("ITEM 1. BUSINESS" in h for h in headings)
        assert any("ITEM 1A. RISK FACTORS" in h for h in headings)
        assert any("PART II" in h for h in headings)
        assert any("ITEM 7." in h for h in headings)
        assert any("ITEM 8." in h for h in headings)
        assert any("ITEM 9A." in h for h in headings)

    def test_direct_task_execution(self, tmp_path, sample_txt_bytes, patch_models):
        """Verify direct execution of Celery process_document_job task function."""
        test_file = tmp_path / "filing_apple_10k.txt"
        test_file.write_bytes(sample_txt_bytes)

        job_id = "job_test_direct_sec"
        tracker = get_job_tracker()
        tracker.create_job(
            job_id=job_id,
            file_names=["filing_apple_10k.txt"],
            file_paths=[str(test_file)],
            owner_id="test_analyst_1"
        )

        res = process_document_job(
            job_id=job_id,
            file_paths=[str(test_file)],
            file_names=["filing_apple_10k.txt"],
            owner_id="test_analyst_1"
        )

        assert res["session_id"] is not None
        assert res["chunk_count"] > 0
        assert res["processed_files"] == 1

        final_job = tracker.get_job(job_id)
        assert final_job["status"] == "completed"
        assert final_job["progress"]["percent"] == 100.0
