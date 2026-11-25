"""
Tests for .docx / .doc magic-byte validation, parsing (paragraphs, headings, tables),
chunk schema parity, LibreOffice fallback behavior, and text viewer fallback endpoint.
"""

import io
import zipfile
import pytest
from docx import Document as DocxDocument
from fastapi.testclient import TestClient

from ingestion.router import validate_and_detect_file_type, parse_document
from ingestion import docx_backend


def _build_sample_docx_bytes() -> bytes:
    doc = DocxDocument()
    doc.add_heading("Master Services Agreement", level=1)
    doc.add_paragraph("This agreement governs the cloud services provided by Acme Corp.")
    doc.add_heading("3. Commercial Terms", level=1)
    doc.add_heading("3.1 Payment Terms", level=2)
    doc.add_paragraph("Invoices are payable within thirty (30) days of receipt.")

    table = doc.add_table(rows=3, cols=2)
    table.rows[0].cells[0].text = "Tier"
    table.rows[0].cells[1].text = "Monthly Fee"
    table.rows[1].cells[0].text = "Starter"
    table.rows[1].cells[1].text = "$1,500"
    table.rows[2].cells[0].text = "Enterprise"
    table.rows[2].cells[1].text = "$5,000"

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_docx_magic_bytes_validation(tmp_path):
    docx_file = tmp_path / "contract.docx"
    docx_file.write_bytes(_build_sample_docx_bytes())
    assert validate_and_detect_file_type(docx_file) == "docx"

    # A plain ZIP without word/ or [Content_Types].xml must be rejected
    fake_zip = tmp_path / "not_a_docx.docx"
    with zipfile.ZipFile(fake_zip, "w") as zf:
        zf.writestr("hello.txt", "world")
    with pytest.raises(ValueError) as exc:
        validate_and_detect_file_type(fake_zip)
    assert "not a valid .docx" in str(exc.value).lower()


def test_doc_rejection_without_libreoffice(tmp_path, monkeypatch):
    monkeypatch.setattr(docx_backend, "find_libreoffice_bin", lambda: None)
    monkeypatch.setattr("ingestion.router.find_libreoffice_bin", lambda: None)

    legacy_doc = tmp_path / "legacy.doc"
    legacy_doc.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512)

    assert validate_and_detect_file_type(legacy_doc) == "doc"
    with pytest.raises(ValueError) as exc:
        parse_document(legacy_doc)
    assert "libreoffice" in str(exc.value).lower()


def test_docx_parsing_paragraphs_headings_and_tables(tmp_path):
    docx_file = tmp_path / "sample.docx"
    docx_file.write_bytes(_build_sample_docx_bytes())

    parsed = parse_document(docx_file)
    assert parsed.total_pages >= 1
    page = parsed.pages[0]
    assert "Invoices are payable within thirty (30) days" in page.text
    assert len(page.tables) == 1
    assert "Enterprise" in page.tables[0].markdown
    assert page.tables[0].section_path == "3. Commercial Terms > 3.1 Payment Terms"

    # Heading hierarchy preserved in blocks
    payment_blocks = [b for b in page.blocks if "thirty (30) days" in b.get("text", "")]
    assert payment_blocks
    assert payment_blocks[0]["section_path"] == "3. Commercial Terms > 3.1 Payment Terms"


def test_docx_pipeline_and_text_viewer_fallback(test_client: TestClient, tmp_path):
    import time

    docx_bytes = _build_sample_docx_bytes()
    files = {
        "file": (
            "service_terms.docx",
            docx_bytes,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    }
    res = test_client.post("/documents/upload", files=files, data={"session_id": "docx-session"})
    assert res.status_code == 200
    doc_id = res.json()["document_id"]

    # Poll status until background thread finishes (ready)
    status_val = None
    for _ in range(200):
        st_res = test_client.get(f"/documents/{doc_id}/status")
        assert st_res.status_code == 200
        status_val = st_res.json()["status"]
        if status_val in ("ready", "failed"):
            break
        time.sleep(0.05)
    assert status_val == "ready"

    # Tables endpoint works for docx
    tbl_res = test_client.get(f"/documents/{doc_id}/tables")
    assert tbl_res.status_code == 200
    assert len(tbl_res.json()["tables"]) == 1

    # Text fallback viewer endpoint returns extracted pages
    txt_res = test_client.get("/api/documents/docx-session/text?document_name=service_terms.docx")
    assert txt_res.status_code == 200
    txt_data = txt_res.json()
    assert txt_data["viewer_mode"] == "text"
    assert len(txt_data["pages"]) >= 1
    assert "thirty (30) days" in txt_data["pages"][0]["text"]


def test_doc_upload_rejected_cleanly_when_no_libreoffice(test_client: TestClient, monkeypatch):
    monkeypatch.setattr("routers.documents.find_libreoffice_bin", lambda: None)
    files = {"file": ("old_contract.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64, "application/msword")}
    res = test_client.post("/documents/upload", files=files)
    assert res.status_code == 400
    assert "libreoffice" in res.json()["detail"].lower()
