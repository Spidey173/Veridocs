"""
Pytest configuration and fixtures for Veridocs tests.
Provides isolated environment fixtures for SQLite and PostgreSQL tests.
"""

import os
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
from models_db import Base


@pytest.fixture(autouse=True)
def clean_environment(tmp_path, monkeypatch):
    """
    Set up isolated test database (PostgreSQL if available via TEST_DATABASE_URL/DATABASE_URL,
    otherwise isolated SQLite) and upload directory for each test.
    """
    test_upload = tmp_path / "uploads"
    test_upload.mkdir(parents=True, exist_ok=True)

    settings = get_settings()
    monkeypatch.setattr(settings, "UPLOAD_DIR", test_upload)

    pg_test_url = os.environ.get("TEST_DATABASE_URL")
    if not pg_test_url:
        env_db_url = os.environ.get("DATABASE_URL", "")
        if env_db_url.startswith("postgres"):
            pg_test_url = env_db_url

    # Enforce real PostgreSQL when REQUIRE_POSTGRES is set (e.g., Postgres CI job)
    is_ci = os.environ.get("REQUIRE_POSTGRES", "").lower() in (
        "true",
        "1",
    )
    if is_ci:
        if not pg_test_url or not pg_test_url.startswith("postgres"):
            pg_test_url = "postgresql+psycopg2://veridocs:veridocs_test_password@localhost:5432/veridocs_test"
        elif pg_test_url.startswith("postgres://"):
            pg_test_url = "postgresql+psycopg2://" + pg_test_url[len("postgres://") :]
        elif pg_test_url.startswith("postgresql://"):
            pg_test_url = "postgresql+psycopg2://" + pg_test_url[len("postgresql://") :]

        from sqlalchemy import create_engine, text

        try:
            check_engine = create_engine(pg_test_url, pool_pre_ping=True)
            with check_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            raise RuntimeError(
                f"[CI Postgres Enforcement] Integration tests must run on real PostgreSQL in CI, "
                f"but PostgreSQL is unreachable at '{pg_test_url}': {e}. "
                f"Failing test execution immediately."
            ) from e

        monkeypatch.setattr(settings, "DATABASE_URL", pg_test_url)
    elif pg_test_url and pg_test_url.startswith("postgres"):
        monkeypatch.setattr(settings, "DATABASE_URL", pg_test_url)
    else:
        test_db = str(tmp_path / "test_veridocs.db")
        monkeypatch.setattr(settings, "DATABASE_PATH", test_db)
        monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{test_db}")

    database.reset_engine()
    database.init_db()

    from rate_limiter import _limiter

    _limiter.reset()

    # Clean up PostgreSQL tables between tests
    if settings.DATABASE_URL.startswith("postgres"):
        try:
            with database.get_db() as db:
                for table in reversed(Base.metadata.sorted_tables):
                    try:
                        db.execute(table.delete())
                    except Exception:
                        pass
                db.commit()
        except Exception:
            pass


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
    pdf_path = Path(__file__).resolve().parent.parent.parent / "public" / "sample_agreement.pdf"
    if not pdf_path.exists():
        pdf_path = Path(__file__).resolve().parent.parent / "public" / "sample_agreement.pdf"
    if not pdf_path.exists():
        pdf_path = Path(__file__).resolve().parent.parent / "uploads" / "sample_agreement.pdf"
    if pdf_path.exists():
        return pdf_path.read_bytes()
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\nxref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \ntrailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n115\n%%EOF\n"
