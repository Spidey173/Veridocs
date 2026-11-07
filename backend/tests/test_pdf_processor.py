"""
Unit tests for pdf_processor.py text cleaning, section detection, and file extraction.
"""

import pytest

from pdf_processor import (
    fix_spaced_text,
    detect_sections,
    chunk_text,
    get_document_metadata,
    extract_text_from_file,
    get_pdf_metadata,
    _extract_blocks,
    _format_table_block,
    _chunk_table_atomically,
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

    def test_table_line_and_block_extraction(self):
        """Verify markdown and tab-separated table detection and atomic block grouping."""
        table_text = (
            "Standard paragraph before table.\n\n"
            "| Quarter | Revenue | Growth |\n"
            "| --- | --- | --- |\n"
            "| Q1 2024 | $10M | 12% |\n"
            "| Q2 2024 | $14M | 18% |\n\n"
            "Paragraph after table."
        )
        blocks = _extract_blocks(table_text)
        assert len(blocks) == 3
        assert blocks[0][1] is False  # not table
        assert blocks[1][1] is True   # table block
        assert "| Q1 2024 | $10M | 12% |" in blocks[1][0]
        assert blocks[2][1] is False  # not table

    def test_chunk_text_preserves_table_metadata(self):
        """Verify chunk_text tags table chunks with is_table flag."""
        pages = [{
            "page": 1,
            "text": "| Feature | Supported |\n| --- | --- |\n| OCR | Yes |\n| Tables | Yes |",
            "sections": [],
        }]
        chunks = chunk_text(pages, chunk_size=200)
        assert len(chunks) >= 1
        assert any(c.get("is_table") for c in chunks)

    def test_extract_text_from_file_path_and_streaming(self, tmp_path, sample_txt_bytes):
        """Verify streaming extraction directly from a file path on disk without memory bloat."""
        sample_file = tmp_path / "test_sec_doc.txt"
        sample_file.write_bytes(sample_txt_bytes)

        pages = extract_text_from_file(sample_file, filename="test_sec_doc.txt")
        assert len(pages) > 0
        assert "revenue" in pages[0]["text"].lower()

    def test_borderless_financial_balance_sheet_parsing(self):
        """Verify complex borderless financial statement rows are detected and converted to markdown."""
        from pdf_processor import _format_table_block, _is_table_line

        # 1. Test individual financial line detection
        line1 = "Cash and cash equivalents        $ 24,500        $ 19,200"
        line2 = "Total operating expenses         (14,250)        (12,100)"
        line3 = "Gross margin percentage          38.5%           36.2%"
        line4 = "This is a regular descriptive paragraph without tabular figures."

        assert _is_table_line(line1) is True
        assert _is_table_line(line2) is True
        assert _is_table_line(line3) is True
        assert _is_table_line(line4) is False

        # 2. Test multi-row borderless table extraction and markdown conversion
        raw_balance_sheet = (
            "Consolidated Balance Sheets\n\n"
            "Line Item                        2024          2023\n"
            "---------------------------------------------------\n"
            "Cash and cash equivalents        $ 24,500      $ 19,200\n"
            "Short-term investments           $ 12,000      $ 10,500\n"
            "Total Current Assets             $ 36,500      $ 29,700\n\n"
            "Notes to consolidated financial statements."
        )
        blocks = _extract_blocks(raw_balance_sheet)
        assert len(blocks) == 3
        assert blocks[0][1] is False  # Header paragraph
        assert blocks[1][1] is True   # Balance sheet table block
        assert blocks[2][1] is False  # Notes paragraph

        # 3. Test markdown formatting
        md_table = _format_table_block(blocks[1][0])
        assert "| Line Item | 2024 | 2023 |" in md_table
        assert "| --- |" in md_table
        assert "| Cash and cash equivalents | $ 24,500 | $ 19,200 |" in md_table

    def test_atomic_table_chunking_preserves_headers_across_splits(self):
        """Verify that large tables split strictly at row boundaries and repeat column headers on every chunk."""
        # 1. Test small table remains an indivisible semantic unit
        small_tbl = (
            "| Metric | 2024 | 2023 |\n"
            "| --- | --- | --- |\n"
            "| Cash | $ 100 | $ 90 |\n"
            "| Debt | $ 50 | $ 60 |"
        )
        small_splits = _chunk_table_atomically(small_tbl, max_chunk_chars=500)
        assert len(small_splits) == 1
        assert small_splits[0] == small_tbl

        # 2. Test large multi-row table exceeding chunk threshold
        header = "| Metric Name | FY 2024 (in Millions) | FY 2023 (in Millions) |\n| --- | --- | --- |"
        rows = [f"| Financial Line Item {i:02d} | $ {i*150:,} | $ {i*120:,} |" for i in range(1, 31)]
        dense_tbl = header + "\n" + "\n".join(rows)

        # Split with tight character budget
        splits = _chunk_table_atomically(dense_tbl, max_chunk_chars=400)
        assert len(splits) > 1

        # Every partition must have header and separator
        for i, split in enumerate(splits):
            lines = split.strip().split("\n")
            assert lines[0] == "| Metric Name | FY 2024 (in Millions) | FY 2023 (in Millions) |"
            assert lines[1] == "| --- | --- | --- |"
            # Ensure every remaining line is an unsevered row starting and ending with pipe
            for row_line in lines[2:]:
                assert row_line.startswith("|")
                assert row_line.endswith("|")
                assert row_line.count("|") == 4

    def test_multi_page_table_stitching_across_pages(self):
        """Verify that multi-page tables continuing across page boundaries inherit column headers."""
        page1_text = (
            "Form 10-K Consolidated Statements of Operations\n\n"
            "Line Item                        2024          2023\n"
            "---------------------------------------------------\n"
            "Net Sales                        $ 150,000     $ 120,000\n"
            "Cost of Goods Sold               $ 90,000      $ 75,000"
        )
        page2_text = (
            "Gross Profit                     $ 60,000      $ 45,000\n"
            "Operating Expenses               $ 30,000      $ 25,000\n"
            "Operating Income                 $ 30,000      $ 20,000\n\n"
            "Note 1: Summary of Significant Accounting Policies."
        )

        pages = [
            {"page": 1, "text": page1_text, "sections": []},
            {"page": 2, "text": page2_text, "sections": []},
        ]

        chunks = chunk_text(pages, chunk_size=500)
        assert len(chunks) >= 2

        # Verify page 1 table chunk has headers
        p1_chunks = [c for c in chunks if c["page"] == 1 and c["is_table"]]
        assert len(p1_chunks) >= 1
        assert "| Line Item | 2024 | 2023 |" in p1_chunks[0]["raw_text"]
        assert "| Net Sales | $ 150,000 | $ 120,000 |" in p1_chunks[0]["raw_text"]

        # Verify page 2 continuing table chunk inherited the column header from page 1!
        p2_chunks = [c for c in chunks if c["page"] == 2 and c["is_table"]]
        assert len(p2_chunks) >= 1
        assert "| Line Item | 2024 | 2023 |" in p2_chunks[0]["raw_text"]
        assert "| Gross Profit | $ 60,000 | $ 45,000 |" in p2_chunks[0]["raw_text"]
        assert "| --- |" in p2_chunks[0]["raw_text"]

