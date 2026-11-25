"""
Tests for map-reduce structured summary, document_summaries caching,
force regeneration, and NLI verification grounding scores.
"""

import io
import time
from docx import Document as DocxDocument
from fastapi.testclient import TestClient


def _upload_sample_docx(test_client: TestClient) -> str:
    doc = DocxDocument()
    doc.add_heading("1. Purpose", level=1)
    doc.add_paragraph("This Master Agreement defines cloud hosting services provided by Acme Corp to Beta Inc.")
    doc.add_heading("2. Pricing and Payment", level=1)
    doc.add_paragraph("Customer shall pay $10,000 per month. Invoices are payable net 30 days.")
    doc.add_heading("3. Termination", level=1)
    doc.add_paragraph("Either party may terminate for convenience with 60 days prior written notice.")

    buf = io.BytesIO()
    doc.save(buf)

    res = test_client.post(
        "/documents/upload",
        files={
            "file": (
                "msa.docx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"session_id": "summary-test-session"},
    )
    assert res.status_code == 200
    doc_id = res.json()["document_id"]

    for _ in range(50):
        st = test_client.get(f"/documents/{doc_id}/status").json()["status"]
        if st == "ready":
            break
        time.sleep(0.05)
    assert st == "ready"
    return doc_id


def test_summary_generation_caching_and_nli_verification(test_client: TestClient):
    doc_id = _upload_sample_docx(test_client)

    # 1. Before generation, GET returns not_generated
    pre = test_client.get(f"/documents/{doc_id}/summary")
    assert pre.status_code == 200
    assert pre.json()["status"] == "not_generated"

    # 2. POST triggers background map-reduce + NLI verification
    post_res = test_client.post(f"/documents/{doc_id}/summary")
    assert post_res.status_code == 200
    assert post_res.json()["status"] in ("queued", "processing", "ready")

    # 3. Poll GET until ready
    summary_data = None
    for _ in range(60):
        g = test_client.get(f"/documents/{doc_id}/summary")
        assert g.status_code == 200
        summary_data = g.json()
        if summary_data["status"] in ("ready", "failed"):
            break
        time.sleep(0.05)

    assert summary_data is not None
    assert summary_data["status"] == "ready"
    s = summary_data["summary"]
    assert s["main_purpose"]
    assert isinstance(s["important_points"], list) and len(s["important_points"]) >= 1
    assert isinstance(s["key_information"], list) and len(s["key_information"]) >= 1
    assert s["conclusion"]

    # Grounding score & NLI verification details present
    assert summary_data["grounding_score"] is not None
    assert 0.0 <= summary_data["grounding_score"] <= 1.0
    ver = summary_data["verification"]
    assert ver["total_claims"] >= 3
    assert len(ver["claims"]) == ver["total_claims"]

    # 4. Subsequent POST without force returns cached ready result immediately
    cached_res = test_client.post(f"/documents/{doc_id}/summary")
    assert cached_res.status_code == 200
    assert cached_res.json()["status"] == "ready"
    assert cached_res.json()["summary"] == s

    # 5. POST with force=true regenerates
    regen_res = test_client.post(f"/documents/{doc_id}/summary?force=true")
    assert regen_res.status_code == 200
    assert regen_res.json()["status"] in ("queued", "processing", "ready")

    for _ in range(60):
        g2 = test_client.get(f"/documents/{doc_id}/summary")
        if g2.json()["status"] in ("ready", "failed"):
            break
        time.sleep(0.05)
    assert g2.json()["status"] == "ready"
