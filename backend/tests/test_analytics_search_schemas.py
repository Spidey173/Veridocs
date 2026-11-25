"""
Tests for analytics, cross-document search, and schema extraction:
- GET /analytics + query_log persistence from /api/query and /api/query/stream
- POST /search cross-document library search grouped by document with section + page
- InvoiceExtraction customer_name/customer_address and ContractExtraction deadlines with verbatim quote verification
"""

import io
import time
from docx import Document as DocxDocument
from fastapi.testclient import TestClient

from extraction.schemas import InvoiceExtraction, ContractExtraction
from extraction.extractor import SchemaExtractor
from models_db import QueryLog
import database


def test_schema_polish_invoice_customer_and_contract_deadlines(monkeypatch):
    # Validate Pydantic schemas
    inv = InvoiceExtraction()
    assert hasattr(inv, "customer_name")
    assert hasattr(inv, "customer_address")

    con = ContractExtraction(
        deadlines=[
            {
                "description": "Payment due",
                "date": "30 days",
                "quote": "Invoices are payable within 30 days.",
                "page": 1,
                "verified": True,
            }
        ]
    )
    assert len(con.deadlines) == 1
    assert con.deadlines[0].date == "30 days"

    # Validate heuristic extraction + verbatim quote verification
    extractor = SchemaExtractor()
    monkeypatch.setattr(extractor.settings, "is_llm_configured", lambda: False)
    inv_pages = [
        {
            "page_number": 1,
            "text": (
                "INVOICE #INV-2026-904\n"
                "Customer: Globex Corporation\n"
                "Customer Address: 742 Evergreen Terrace, Springfield\n"
                "Amount Due: $14,500.00\n"
                "Due Date: 2026-12-15\n"
            ),
        }
    ]
    inv_res = extractor.extract("doc-inv", "invoice", inv_pages)
    assert inv_res["fields"]["customer_name"]["value"] == "Globex Corporation"
    assert inv_res["fields"]["customer_name"]["verified"] is True
    assert "742 Evergreen Terrace" in inv_res["fields"]["customer_address"]["value"]
    assert inv_res["fields"]["customer_address"]["verified"] is True

    con_pages = [
        {
            "page_number": 1,
            "text": (
                "SECTION 1. TERM. Effective 2026-01-01.\n"
                "SECTION 2. PAYMENT. Invoices are payable within 30 days of invoice date.\n"
                "SECTION 3. CONFIDENTIALITY Strict confidentiality.\n"
                "SECTION 4. TERMINATION. Either party may terminate with 60 days prior written notice.\n"
            ),
        }
    ]
    con_res = extractor.extract("doc-con", "contract", con_pages)
    deadlines = con_res["fields"]["deadlines"]
    assert len(deadlines) >= 2
    assert all(d["verified"] is True for d in deadlines)
    assert any("30 days" in d["date"] or "2026-01-01" in d["date"] for d in deadlines)


def test_cross_document_search_and_analytics(test_client: TestClient, monkeypatch):
    # Upload two different documents across two distinct sessions
    doc1 = DocxDocument()
    doc1.add_heading("1. Service Level Agreement", level=1)
    doc1.add_paragraph("Provider guarantees 99.99% uptime SLA for production clusters.")
    buf1 = io.BytesIO()
    doc1.save(buf1)

    doc2 = DocxDocument()
    doc2.add_heading("2. Billing Policy", level=1)
    doc2.add_paragraph("Annual subscription fees are billed upfront with 99.9% uptime credits.")
    buf2 = io.BytesIO()
    doc2.save(buf2)

    r1 = test_client.post(
        "/documents/upload",
        files={
            "file": (
                "sla_alpha.docx",
                buf1.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"session_id": "lib-session-a"},
    )
    r2 = test_client.post(
        "/documents/upload",
        files={
            "file": (
                "billing_beta.docx",
                buf2.getvalue(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        data={"session_id": "lib-session-b"},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    d1_id = r1.json()["document_id"]
    d2_id = r2.json()["document_id"]

    for did in (d1_id, d2_id):
        status_val = None
        for _ in range(200):
            status_val = test_client.get(f"/documents/{did}/status").json()["status"]
            if status_val in ("ready", "failed"):
                break
            time.sleep(0.05)
        assert status_val == "ready"

    # 1. Cross-document search with no session scope (library)
    s_res = test_client.post("/search", json={"query": "uptime SLA credits", "top_k": 10})
    assert s_res.status_code == 200
    s_data = s_res.json()
    assert s_data["scope"] == "library"
    assert s_data["total_matches"] >= 2
    filenames = {g["filename"] for g in s_data["documents"]}
    assert "sla_alpha.docx" in filenames
    assert "billing_beta.docx" in filenames
    # Every match carries section_path and page
    first_match = s_data["documents"][0]["matches"][0]
    assert first_match["page"] >= 1
    assert first_match["section_path"] is not None

    # 2. Query endpoint writes to query_log
    from llm_service import LLMService

    monkeypatch.setattr(LLMService, "is_configured", lambda self: True)
    monkeypatch.setattr(
        LLMService,
        "generate_answer",
        lambda self, q, chunks, history=None: "Provider guarantees 99.99% uptime SLA [1].",
    )
    q_res = test_client.post("/api/query", json={"session_id": "lib-session-a", "question": "What is the uptime SLA?"})
    assert q_res.status_code == 200

    with database.get_db() as db:
        logs = db.query(QueryLog).all()
        assert len(logs) == 1
        assert logs[0].question == "What is the uptime SLA?"
        assert logs[0].citation_score is not None

    # 3. GET /analytics returns counts and daily breakdown
    a_res = test_client.get("/analytics")
    assert a_res.status_code == 200
    a_data = a_res.json()
    assert a_data["documents_uploaded"] >= 2
    assert a_data["documents_analyzed"] >= 2
    assert a_data["questions_asked"] == 1
    assert a_data["avg_verification_score"] >= 0.0
    assert len(a_data["by_day"]) >= 1
    assert a_data["by_day"][0]["questions_asked"] == 1
