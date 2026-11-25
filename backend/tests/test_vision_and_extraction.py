"""
Unit tests for Vision classification, Entity extraction, and Schema extraction.
"""

from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from vision.classifier import classify_page_heuristics
from vision.base import PageVisionOutput, FigureInfo
from vision.service import VisionService, OpenAIVisionBackend
from classification.classifier import classify_document_heuristics
from entities.extractor import EntityExtractor
from extraction.extractor import verify_quote_in_page_text, run_invoice_math_checks
import database


def test_classify_page_heuristics():
    # Text with signatures and tables
    text = (
        "This agreement is signed below.\n"
        "By: _____________________\n"
        "Authorized Signature\n"
        "Date: January 1, 2025\n"
        "| ID | Item | Price |\n"
        "| 1  | Bolt | $2.00 |\n"
    )
    flags = classify_page_heuristics(
        text=text,
        page_number=1,
        tables=[{"markdown": "| ID | Item | Price |"}],
        image_count=1,
        has_drawings=True,
    )
    assert flags["has_figures"] is True
    assert flags["has_tables"] is True
    assert flags["has_signature_block"] is True


def test_classify_document_heuristics():
    doc_type, conf = classify_document_heuristics("INVOICE #1024\nBill To: John Doe\nTotal Due: $500.00")
    assert doc_type == "invoice"
    assert conf >= 0.80

    doc_type, conf = classify_document_heuristics(
        "MASTER SERVICES AGREEMENT\nBetween Party A and Party B\nGoverning Law"
    )
    assert doc_type == "contract"
    assert conf >= 0.80

    doc_type, conf = classify_document_heuristics("Abstract: We propose a deep learning method... References: [1]")
    assert doc_type == "research_paper"
    assert conf >= 0.80

    doc_type, conf = classify_document_heuristics("Curriculum Vitae\nExperience\nEducation\nSkills: Python, TypeScript")
    assert doc_type == "resume"
    assert conf >= 0.80


def test_entity_extractor_normalization():
    extractor = EntityExtractor()
    text = "John Smith from Acme Corp paid $1,500.50 on October 12, 2024 in San Francisco."
    entities = extractor.extract_from_chunk(chunk_text=text, page_number=1, chunk_id="chk-1")

    # Verify money extraction & normalization
    money_ents = [e for e in entities if e["label"] == "money"]
    assert len(money_ents) > 0
    assert money_ents[0]["normalized"]["amount"] == 1500.50
    assert money_ents[0]["normalized"]["currency"] == "USD"

    # Verify date extraction & normalization
    date_ents = [e for e in entities if e["label"] == "date"]
    assert len(date_ents) > 0
    assert "2024-10-12" in date_ents[0]["normalized"]


def test_verify_quote_in_page_text():
    page_text = "The vendor shall deliver all materials by November 30, 2024 without delay."

    # Exact / normalized match
    assert verify_quote_in_page_text("materials by November 30, 2024", page_text) is True
    # Extra whitespace
    assert verify_quote_in_page_text("materials   by   November 30, 2024", page_text) is True
    # Non-existent quote
    assert verify_quote_in_page_text("materials by January 1, 2025", page_text) is False


def test_invoice_math_checks():
    # Valid math
    valid_data = {
        "line_items": [
            {"description": "Item A", "quantity": 2, "unit_price": 50.0, "amount": 100.0},
            {"description": "Item B", "quantity": 1, "unit_price": 50.0, "amount": 50.0},
        ],
        "subtotal": {"value": 150.0, "page": 1, "quote": "Subtotal: $150.00", "verified": True},
        "tax": {"value": 15.0, "page": 1, "quote": "Tax: $15.00", "verified": True},
        "total": {"value": 165.0, "page": 1, "quote": "Total: $165.00", "verified": True},
    }
    run_invoice_math_checks(valid_data)
    assert valid_data["subtotal"].get("math_mismatch", False) is False
    assert valid_data["total"].get("math_mismatch", False) is False

    # Invalid math
    invalid_data = {
        "line_items": [
            {"description": "Item A", "quantity": 1, "unit_price": 100.0, "amount": 100.0},
        ],
        "subtotal": {"value": 100.0, "page": 1, "quote": "Subtotal: $100.00", "verified": True},
        "tax": {"value": 10.0, "page": 1, "quote": "Tax: $10.00", "verified": True},
        "total": {"value": 999.0, "page": 1, "quote": "Total: $999.00", "verified": True},  # Mismatch!
    }
    run_invoice_math_checks(invalid_data)
    assert invalid_data["total"].get("math_mismatch") is True


def test_vision_service_figure_chunks():
    backend = MagicMock(spec=OpenAIVisionBackend)
    backend.analyze_page.return_value = PageVisionOutput(
        page_number=1,
        figures=[
            FigureInfo(
                type="chart",
                title="Quarterly Revenue Trend",
                description="Bar chart showing Q1 to Q4 revenue growing from $10M to $15M.",
                data_points=["Q1: $10M", "Q4: $15M"],
                confidence=0.95,
            )
        ],
        signatures=[],
        layout_notes="Standard single column layout.",
    )

    doc = database.create_document(
        filename="dummy.pdf",
        mime_type="application/pdf",
        session_id="vision-test-session",
    )
    service = VisionService(backend=backend)
    res = service.process_document_vision(
        document_id=doc["id"],
        pages=[{"page_number": 1, "has_figures": True, "text": "Chart text"}],
        file_path="dummy.pdf",
    )

    chunks = res["figure_chunks"]
    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk["chunk_type"] == "figure"
    assert "Quarterly Revenue Trend" in chunk["content"]
    assert chunk["metadata"]["figure_type"] == "chart"
    assert chunk["metadata"]["extraction_method"] == "vision"


def test_document_routes_for_extraction_and_entities(test_client: TestClient):
    # Create document directly in database
    doc = database.create_document(
        filename="contract.txt",
        mime_type="text/plain",
        session_id="test-session-extract",
    )
    doc_id = doc["id"]

    # Test GET entities
    ent_res = test_client.get(f"/api/documents/{doc_id}/entities")
    assert ent_res.status_code == 200
    assert "entities" in ent_res.json()

    # Test GET extraction (initially empty or default)
    ext_res = test_client.get(f"/api/documents/{doc_id}/extraction")
    assert ext_res.status_code == 200

    # Test PATCH document type
    patch_res = test_client.patch(f"/api/documents/{doc_id}/type", json={"doc_type": "contract"})
    assert patch_res.status_code == 200
    assert patch_res.json()["doc_type"] == "contract"

    # Test PUT extraction (saving user corrections)
    put_res = test_client.put(
        f"/api/documents/{doc_id}/extraction",
        json={
            "user_edits": {
                "parties": [{"value": "Acme Corp", "page": 1, "quote": "Acme Corp", "verified": True}],
                "effective_date": {
                    "value": "2024-01-01",
                    "page": 1,
                    "quote": "effective January 1, 2024",
                    "verified": True,
                },
            },
        },
    )
    assert put_res.status_code == 200
    assert put_res.json()["status"] == "updated"

    # Verify updated extraction
    get_updated = test_client.get(f"/api/documents/{doc_id}/extraction")
    assert get_updated.status_code == 200
    data = get_updated.json()
    assert data["schema_type"] == "contract"
    assert "parties" in data["user_edits"]
