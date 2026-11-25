"""
Tests for document report generation (with cited findings, risks, recommendations)
and export endpoints (?format=md|pdf|docx).
"""

import io
import time
from docx import Document as DocxDocument
from fastapi.testclient import TestClient


def _upload_contract_docx(test_client: TestClient) -> str:
    doc = DocxDocument()
    doc.add_heading("1. Scope and Term", level=1)
    doc.add_paragraph("Provider delivers managed cloud analytics for 24 months effective 2026-01-01.")
    doc.add_heading("2. Liability and Penalty Risk", level=1)
    doc.add_paragraph(
        "Provider faces unlimited liability and a $500,000 penalty for SLA breach or data exposure. "
        "Customer may terminate immediately upon uncured default."
    )
    doc.add_heading("3. Payment", level=1)
    doc.add_paragraph("Invoices totaling $10,000.00 are payable net 30 days.")

    buf = io.BytesIO()
    doc.save(buf)

    res = test_client.post(
        "/documents/upload",
        files={
            "file": (
                "risk_contract.docx",
                buf.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"session_id": "report-test-session"},
    )
    assert res.status_code == 200
    doc_id = res.json()["document_id"]

    st = ""
    for _ in range(240):
        st = test_client.get(f"/documents/{doc_id}/status").json()["status"]
        if st in ("ready", "failed"):
            break
        time.sleep(0.05)
    assert st == "ready"
    return doc_id


def test_generate_report_and_export_formats(test_client: TestClient):
    doc_id = _upload_contract_docx(test_client)

    # 1. Generate report
    rep_res = test_client.post(f"/documents/{doc_id}/report")
    assert rep_res.status_code == 200
    report = rep_res.json()

    assert report["document_id"] == doc_id
    assert report["executive_summary"]
    assert len(report["important_findings"]) >= 1
    assert len(report["risks"]) >= 1
    assert len(report["recommendations"]) >= 1

    # Every finding/risk/recommendation must cite chunks (page + section)
    for group in (report["important_findings"], report["risks"], report["recommendations"]):
        for item in group:
            assert item["citations"], f"Missing citations on {item}"
            cit = item["citations"][0]
            assert cit["page"] >= 1
            assert "section_path" in cit
            assert cit["quote"]

    # 2. Export Markdown
    md_res = test_client.get(f"/documents/{doc_id}/report/export?format=md")
    assert md_res.status_code == 200
    assert "text/markdown" in md_res.headers["content-type"]
    md_text = md_res.text
    assert "# Document Intelligence Report" in md_text
    assert "## Executive Summary" in md_text
    assert "## Important Findings" in md_text

    # 3. Export PDF
    pdf_res = test_client.get(f"/documents/{doc_id}/report/export?format=pdf")
    assert pdf_res.status_code == 200
    assert pdf_res.headers["content-type"] == "application/pdf"
    assert pdf_res.content.startswith(b"%PDF-")

    # 4. Export DOCX
    docx_res = test_client.get(f"/documents/{doc_id}/report/export?format=docx")
    assert docx_res.status_code == 200
    assert "wordprocessingml.document" in docx_res.headers["content-type"]
    assert docx_res.content.startswith(b"PK\x03\x04")
    parsed_docx = DocxDocument(io.BytesIO(docx_res.content))
    full_docx_text = "\n".join(p.text for p in parsed_docx.paragraphs)
    assert "Executive Summary" in full_docx_text
    assert "Important Findings" in full_docx_text
