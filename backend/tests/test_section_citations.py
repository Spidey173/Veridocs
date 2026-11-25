"""
Tests for section-level citations across parsers, chunks DB column,
hybrid retrieval results, NLI verification, and query endpoints.
"""

import io
from docx import Document as DocxDocument
from fastapi.testclient import TestClient

from ingestion.router import parse_document
from pdf_processor import chunk_text
from vector_store import VectorStore
from verification import extract_citations_from_answer, verify_claim_against_chunks
from models_db import Chunk
import database
from config import get_model_registry


def test_section_path_stored_and_returned_in_retrieval(tmp_path):
    doc = DocxDocument()
    doc.add_heading("3", level=1)
    doc.add_heading("3.1 Payment Terms", level=2)
    doc.add_paragraph("All invoices shall be paid net 30 days from invoice receipt.")
    doc.add_heading("3.2 Late Fees", level=2)
    doc.add_paragraph("Late balances accrue interest at 1.5% per month.")

    docx_path = tmp_path / "terms.docx"
    doc.save(str(docx_path))

    parsed = parse_document(docx_path, filename="terms.docx")
    pages_data = [
        {
            "page": p.number,
            "page_number": p.number,
            "text": p.text,
            "blocks": p.blocks,
            "tables": [t.model_dump() for t in p.tables],
            "extraction_method": p.extraction_method,
            "ocr_confidence": p.ocr_confidence,
        }
        for p in parsed.pages
    ]
    chunks = chunk_text(pages_data, document_name="terms.docx")
    assert any(c.get("section_path") == "3 > 3.1 Payment Terms" for c in chunks)
    assert any(c.get("section_path") == "3 > 3.2 Late Fees" for c in chunks)

    reg = get_model_registry()
    embs = list(reg.embedding_model.embed([c["text"] for c in chunks]))
    database.save_session("sec-session", ["terms.docx"])
    database.save_chunks("sec-session", chunks, embs)

    # Verify DB column stored section_path
    with database.get_db() as db:
        rows = db.query(Chunk).filter(Chunk.session_id == "sec-session").all()
        assert any(r.section_path == "3 > 3.1 Payment Terms" for r in rows)

    # Verify VectorStore.search returns section_path
    results = VectorStore.search("sec-session", "When must invoices be paid?", top_k=2)
    assert results
    assert results[0].get("section_path") == "3 > 3.1 Payment Terms"


def test_citations_and_verification_include_section_path():
    chunks = [
        {
            "page": 4,
            "source_file": "msa.pdf",
            "section_path": "3 > 3.1 Payment Terms",
            "text": "Invoices are payable within 30 days of receipt.",
        }
    ]
    cits = extract_citations_from_answer("Invoices are payable within 30 days [1].", chunks)
    assert len(cits) == 1
    assert cits[0]["section_path"] == "3 > 3.1 Payment Terms"
    assert cits[0]["page"] == 4

    claim_res = verify_claim_against_chunks("Invoices are payable within 30 days of receipt.", chunks)
    assert claim_res["section_path"] == "3 > 3.1 Payment Terms"
    assert claim_res["matched_page"] == 4


def test_pdf_fixture_section_path_extraction():
    from pathlib import Path

    fixtures_dir = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"
    parsed = parse_document(fixtures_dir / "digital_doc.pdf")
    pages_data = [
        {
            "page": p.number,
            "page_number": p.number,
            "text": p.text,
            "blocks": p.blocks,
            "tables": [t.model_dump() for t in p.tables],
            "extraction_method": p.extraction_method,
        }
        for p in parsed.pages
    ]
    chunks = chunk_text(pages_data, document_name="digital_doc.pdf")
    assert len(chunks) >= 1
    # Ensure chunks have section_path key and at least one heading was detected
    assert all("section_path" in c for c in chunks)
    assert any(c.get("section_path") for c in chunks)


def test_query_endpoint_returns_section_path(test_client: TestClient, monkeypatch):
    # Upload a docx with sections and query with mocked LLM
    doc = DocxDocument()
    doc.add_heading("4. Confidentiality", level=1)
    doc.add_paragraph("Confidential information shall be protected for five (5) years.")
    buf = io.BytesIO()
    doc.save(buf)

    upload_res = test_client.post(
        "/api/upload",
        files=[
            (
                "files",
                ("nda.docx", buf.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            )
        ],
    )
    assert upload_res.status_code == 200
    sid = upload_res.json()["session_id"]

    # Mock LLMService.is_configured and generate_answer to avoid external network
    from llm_service import LLMService

    monkeypatch.setattr(LLMService, "is_configured", lambda self: True)
    monkeypatch.setattr(
        LLMService,
        "generate_answer",
        lambda self, q, chunks, history=None: "Confidential information is protected for 5 years [1].",
    )

    q_res = test_client.post(
        "/api/query", json={"session_id": sid, "question": "How long is confidentiality protected?"}
    )
    assert q_res.status_code == 200
    data = q_res.json()
    assert data["sources"]
    assert data["sources"][0]["section_path"] == "4. Confidentiality"
    assert data["citations"]
    assert data["citations"][0]["section_path"] == "4. Confidentiality"
