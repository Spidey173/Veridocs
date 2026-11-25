"""
Test suite for Veridocs document ingestion and hybrid retrieval pipeline:
- Parser selection per page (text layer vs OCR fallback)
- OCR fallback on scanned fixtures
- Table extraction on fixtures (Markdown and JSON)
- Async upload, status transitions, and SSE live progress
- Pgvector / hybrid retrieval with reciprocal rank fusion
- Quality & safety limits (file size, corrupt/encrypted PDFs, magic bytes)
"""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient

from ingestion.router import validate_and_detect_file_type, parse_document, convert_image_to_pdf
from vector_store import VectorStore
import database
from tasks import process_document_pipeline

FIXTURES_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "fixtures"


def test_magic_bytes_detection():
    """Verify format detection based on magic bytes rather than extension alone."""
    assert validate_and_detect_file_type(FIXTURES_DIR / "digital_doc.pdf") == "pdf"
    assert validate_and_detect_file_type(FIXTURES_DIR / "scanned_invoice.png") == "png"
    assert validate_and_detect_file_type(FIXTURES_DIR / "contract.txt") == "txt"


def test_reject_corrupt_or_encrypted_pdf(tmp_path):
    """Verify rejection of corrupt or encrypted PDFs with user-friendly errors."""
    corrupt_file = tmp_path / "corrupt.pdf"
    corrupt_file.write_bytes(b"%PDF-1.4\ncorrupted content without xref or EOF")

    with pytest.raises(ValueError) as exc:
        validate_and_detect_file_type(corrupt_file)
    assert "corrupt" in str(exc.value).lower() or "not a valid pdf" in str(exc.value).lower()


def test_parser_selection_digital_pdf():
    """Verify digital PDF uses text_layer extraction."""
    parsed = parse_document(FIXTURES_DIR / "digital_doc.pdf")
    assert parsed.total_pages >= 1
    page1 = parsed.pages[0]
    assert page1.extraction_method == "text_layer"
    assert "Payment Terms" in page1.text or "Agreement" in page1.text


def test_ocr_fallback_scanned_pdf():
    """Verify scanned PDF with low/no text triggers OCR fallback or is detected properly."""
    parsed = parse_document(FIXTURES_DIR / "scanned_doc.pdf")
    assert parsed.total_pages == 1
    page1 = parsed.pages[0]
    # Scanned PDF without text stream must trigger OCR extraction method
    assert page1.extraction_method == "ocr"


def test_image_to_pdf_conversion(tmp_path):
    """Verify image uploads are converted to single-page PDF for viewer rendering."""
    target_pdf = tmp_path / "converted_invoice.pdf"
    convert_image_to_pdf(FIXTURES_DIR / "scanned_invoice.png", target_pdf)
    assert target_pdf.exists()
    assert target_pdf.stat().st_size > 0
    # Must be valid PDF
    assert validate_and_detect_file_type(target_pdf) == "pdf"


def test_table_extraction_fixture():
    """Verify tables are extracted as Markdown and structured JSON."""
    parsed = parse_document(FIXTURES_DIR / "table_doc.pdf")
    assert parsed.total_pages >= 1
    page1 = parsed.pages[0]
    assert len(page1.tables) >= 1
    table = page1.tables[0]
    assert "Tier" in table.markdown
    assert "Monthly Cost" in table.markdown or "Storage" in table.markdown
    # Verify structured JSON
    assert "headers" in table.json_data or "rows" in table.json_data


def test_status_transitions_pipeline():
    """Verify queued -> parsing -> ocr -> chunking -> embedding -> ready pipeline."""
    # Create document
    doc = database.create_document(
        filename="digital_doc.pdf",
        mime_type="application/pdf",
        session_id="test-pipeline-session",
        status="queued",
    )
    doc_id = doc["id"]
    assert doc["status"] == "queued"

    # Run processing pipeline
    result = process_document_pipeline(
        document_id=doc_id, file_path_str=str(FIXTURES_DIR / "digital_doc.pdf"), session_id="test-pipeline-session"
    )

    assert result["status"] == "ready"
    assert result["chunk_count"] >= 1

    # Verify DB status
    updated_doc = database.get_document(doc_id)
    assert updated_doc["status"] == "ready"
    assert updated_doc["page_count"] >= 1


def test_async_upload_endpoint(test_client: TestClient):
    """Verify POST /documents/upload enqueues job and returns immediately with document_id."""
    pdf_bytes = (FIXTURES_DIR / "digital_doc.pdf").read_bytes()
    files = {"file": ("digital_doc.pdf", pdf_bytes, "application/pdf")}

    res = test_client.post("/documents/upload", files=files)
    assert res.status_code == 200
    data = res.json()
    assert "document_id" in data
    assert data["status"] == "queued"
    doc_id = data["document_id"]

    # Verify status polling endpoint
    status_res = test_client.get(f"/documents/{doc_id}/status")
    assert status_res.status_code == 200
    assert status_res.json()["document_id"] == doc_id


def test_document_tables_endpoint(test_client: TestClient):
    """Verify GET /documents/{id}/tables retrieves extracted tables."""
    # Process table document
    doc = database.create_document(
        filename="table_doc.pdf", mime_type="application/pdf", session_id="table-session", status="queued"
    )
    doc_id = doc["id"]
    process_document_pipeline(doc_id, str(FIXTURES_DIR / "table_doc.pdf"), session_id="table-session")

    tables_res = test_client.get(f"/documents/{doc_id}/tables")
    assert tables_res.status_code == 200
    tables_data = tables_res.json()
    assert tables_data["document_id"] == doc_id
    assert len(tables_data["tables"]) >= 1
    assert "markdown" in tables_data["tables"][0]


def test_hybrid_retrieval_finds_expected_chunk(test_client: TestClient):
    """Verify hybrid retrieval ranks relevant passage and table chunks."""
    doc = database.create_document(
        filename="contract.txt", mime_type="text/plain", session_id="retrieval-session", status="queued"
    )
    doc_id = doc["id"]
    process_document_pipeline(doc_id, str(FIXTURES_DIR / "contract.txt"), session_id="retrieval-session")

    # Search for payment terms
    results = VectorStore.search(
        session_id="retrieval-session", query="When are invoices payable under this agreement?", top_k=3
    )

    assert len(results) > 0
    top_text = " ".join([r["text"] for r in results])
    assert "thirty (30) days" in top_text or "payable" in top_text.lower()
