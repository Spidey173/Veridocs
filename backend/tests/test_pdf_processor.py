"""
Unit tests for pdf_processor.py text cleaning, section detection, and file extraction.
"""

import io
import pytest
from pypdf import PdfWriter

from pdf_processor import (
    fix_spaced_text,
    detect_sections,
    chunk_text,
    get_document_metadata,
    extract_text_from_file,
    get_pdf_metadata,
)


class TestPDFProcessor:
    def test_fix_spaced_text_empty(self):
        """Verify empty and whitespace string handling."""
        assert fix_spaced_text("") == ""
        assert fix_spaced_text(None) == ""

    def test_fix_spaced_text_normal(self):
        """Verify normal text without unnatural spacing is preserved."""
        normal = "This is a normal paragraph with standard spacing."
        assert fix_spaced_text(normal) == normal

    def test_fix_spaced_text_spaced_characters(self):
        """Verify text with spaced letters is correctly defragmented."""
        spaced = "T h i s   i s   d e f r a g m e n t e d"
        cleaned = fix_spaced_text(spaced)
        assert "This is defragmented" in cleaned

    def test_detect_sections_patterns(self):
        """Verify section detection across various heading patterns."""
        sample_doc = (
            "1. Introduction\n"
            "This is the first paragraph.\n\n"
            "2.3 Technical Architecture\n"
            "Here we explain architecture.\n\n"
            "IV. Discussion and Analysis\n"
            "Points to consider.\n\n"
            "KEY FINDINGS\n"
            "Summary of results.\n\n"
            "Background:\n"
            "Context here.\n\n"
            "**Conclusion**\n"
            "Final remarks."
        )
        sections = detect_sections(sample_doc)
        headings = [s["heading"] for s in sections]

        assert any("1. Introduction" in h for h in headings)
        assert any("2.3 Technical Architecture" in h for h in headings)
        assert any("IV. Discussion and Analysis" in h for h in headings)
        assert any("KEY FINDINGS" in h for h in headings)
        assert any("Conclusion" in h for h in headings)

    def test_chunk_text_basic(self):
        """Verify chunk_text splits pages into structured chunks."""
        pages = [
            {
                "page": 1,
                "text": "1. Executive Summary\n" + "Veridocs makes document search effortless. " * 30,
                "sections": [{"heading": "1. Executive Summary"}],
            },
            {
                "page": 2,
                "text": "2. System Design\n" + "Architecture includes vector store and reranker. " * 30,
                "sections": [{"heading": "2. System Design"}],
            },
        ]
        chunks = chunk_text(pages, chunk_size=200, chunk_overlap=20)
        assert len(chunks) > 0

        # Check metadata preserved
        for chunk in chunks:
            assert "text" in chunk
            assert "page" in chunk
            assert chunk["page"] in (1, 2)
            assert "section" in chunk

    def test_chunk_text_empty(self):
        """Verify empty pages return empty chunks."""
        assert chunk_text([]) == []
        assert chunk_text([{"page": 1, "text": ""}]) == []

    def test_get_document_metadata_txt(self, sample_txt_bytes):
        """Verify metadata extraction for TXT files."""
        meta = get_document_metadata(sample_txt_bytes, "notes.txt")
        assert meta is not None
        assert meta["filename"] == "notes.txt"
        assert meta["file_size_bytes"] == len(sample_txt_bytes)
        assert meta["num_pages"] >= 1

    def test_get_document_metadata_docx(self, sample_docx_bytes):
        """Verify metadata extraction for DOCX files."""
        meta = get_document_metadata(sample_docx_bytes, "document.docx")
        assert meta is not None
        assert meta["filename"] == "document.docx"
        assert meta["file_size_bytes"] == len(sample_docx_bytes)
        assert meta["is_encrypted"] is False

    def test_get_document_metadata_corrupt(self):
        """Verify handling of invalid/corrupt data."""
        meta = get_document_metadata(b"Not a valid pdf binary", "corrupt.pdf")
        assert meta is None

    def test_extract_text_from_txt(self, sample_txt_bytes):
        """Verify text extraction from plain text."""
        pages = extract_text_from_file(sample_txt_bytes, "info.txt")
        assert len(pages) >= 1
        page_dict = pages[0]
        assert page_dict["page"] == 1
        assert "Veridocs is an enterprise-grade" in page_dict["text"]

    def test_extract_text_from_docx(self, sample_docx_bytes):
        """Verify text extraction from DOCX."""
        pages = extract_text_from_file(sample_docx_bytes, "doc.docx")
        assert len(pages) >= 1
        full_text = " ".join(p["text"] for p in pages)
        assert "Veridocs extracts key insights" in full_text
        assert "Alan Turing" in full_text

    def test_extract_text_unsupported_extension(self):
        """Verify unsupported extensions raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported file type"):
            extract_text_from_file(b"content", "file.xyz")

    def test_get_pdf_metadata_invalid(self):
        """Verify get_pdf_metadata returns None for corrupted data."""
        assert get_pdf_metadata(b"corrupt") is None
