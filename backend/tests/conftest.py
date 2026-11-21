"""
Pytest configuration and fixtures for Veridocs tests.
"""

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import main
from config import get_settings
import database


@pytest.fixture(autouse=True)
def clean_environment(tmp_path, monkeypatch):
    """Set up isolated temp database and upload directory for each test."""
    test_upload = tmp_path / "uploads"
    test_upload.mkdir(parents=True, exist_ok=True)
    test_db = str(tmp_path / "test_veridocs.db")

    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", test_upload)
    monkeypatch.setattr(settings, "DATABASE_PATH", test_db)

    database.init_db()


@pytest.fixture
def test_client():
    return TestClient(main.app)


@pytest.fixture
def sample_txt_bytes():
    return b"""VERIDOCS SAMPLE AGREEMENT
Section 1. Payment Terms. Invoices are payable within 30 days of receipt.
Section 2. Availability SLA. Provider commits to 99.9% uptime.
Section 3. Liability. Maximum cumulative liability is capped at $500,000."""


@pytest.fixture
def sample_pdf_bytes():
    pdf_path = Path(__file__).resolve().parent.parent / "uploads" / "sample_agreement.pdf"
    if pdf_path.exists():
        return pdf_path.read_bytes()
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\nxref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \ntrailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n115\n%%EOF\n"
