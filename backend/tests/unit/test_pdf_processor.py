"""
Unit tests for pdf_processor.py text cleaning, section detection, and file extraction.
"""

import io
from PIL import Image
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
    _is_table_line,
    register_vision_transcriber,
    register_ocr_engine,
    _optimize_image_for_ocr,
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

    def test_multimodal_vision_fallback_for_scanned_image_pdf(self):
        """Verify that pure scanned PDFs without OCR text trigger the multimodal vision fallback."""
        # 1. Create a pure scanned image PDF with zero text characters
        img = Image.new("RGB", (300, 400), color=(255, 255, 255))
        pdf_buf = io.BytesIO()
        img.save(pdf_buf, format="PDF")
        scanned_pdf_bytes = pdf_buf.getvalue()

        # 2. Register mock multimodal vision model (e.g. simulating Gemini Flash vision)
        mock_transcription = (
            "CONFIDENTIAL AUDIT REPORT - SCANNED PHOTOCOPY\n\n"
            "| Item | 2024 | 2023 |\n"
            "| --- | --- | --- |\n"
            "| Total Revenue | $ 125,000 | $ 98,000 |\n\n"
            "Audited by Forensic Accounting Partners."
        )

        def mock_vision(img_bytes: bytes, page_num: int) -> str:
            assert len(img_bytes) > 0
            assert page_num == 1
            return mock_transcription

        register_vision_transcriber(mock_vision)

        try:
            pages = extract_text_from_file(scanned_pdf_bytes, filename="scanned_audit.pdf")
            assert len(pages) == 1
            assert pages[0]["page"] == 1
            assert pages[0]["is_scanned"] is True
            assert pages[0]["ocr_engine"] == "multimodal_vision"
            assert "CONFIDENTIAL AUDIT REPORT" in pages[0]["text"]
            assert "| Total Revenue | $ 125,000 | $ 98,000 |" in pages[0]["text"]
        finally:
            register_vision_transcriber(None)

    def test_multimodal_vision_parallel_batch_processing(self):
        """Verify that multi-page scanned filings process pages concurrently and maintain strict page order."""
        import time
        import threading

        # Create 6-page scanned PDF
        images = [Image.new("RGB", (100, 100), color=(i * 35, 120, 150)) for i in range(6)]
        buf = io.BytesIO()
        images[0].save(buf, format="PDF", save_all=True, append_images=images[1:])
        scanned_pdf_bytes = buf.getvalue()

        thread_ids = set()
        lock = threading.Lock()

        def mock_concurrent_vision(img_bytes: bytes, page_num: int) -> str:
            with lock:
                thread_ids.add(threading.get_ident())
            time.sleep(0.04)
            return f"Transcribed content for scanned page {page_num}\n\n1. Heading {page_num}\nDetails here."

        register_vision_transcriber(mock_concurrent_vision)
        try:
            pages = extract_text_from_file(scanned_pdf_bytes, filename="multipage_scanned_filing.pdf")
            assert len(pages) == 6
            # Strict ordering must be guaranteed
            page_numbers = [p["page"] for p in pages]
            assert page_numbers == [1, 2, 3, 4, 5, 6]
            # Multiple worker threads must have been utilized concurrently
            assert len(thread_ids) > 1
            for p in pages:
                assert p["is_scanned"] is True
                assert p["ocr_engine"] == "multimodal_vision"
                assert f"Transcribed content for scanned page {p['page']}" in p["text"]
        finally:
            register_vision_transcriber(None)

    def test_image_optimization_downscales_oversized_scan(self):
        """Verify that oversized scans (>1800px) are downscaled and JPEG-compressed to minimize transmission latency."""
        # Create oversized 3000x2400 uncompressed test scan
        oversized = Image.new("RGB", (3000, 2400), color=(240, 240, 240))
        raw_buf = io.BytesIO()
        oversized.save(raw_buf, format="PNG")
        raw_bytes = raw_buf.getvalue()

        optimized_bytes = _optimize_image_for_ocr(raw_bytes, max_dim=1800)
        assert len(optimized_bytes) > 0
        assert len(optimized_bytes) < len(raw_bytes)

        # Inspect resulting dimensions
        opt_img = Image.open(io.BytesIO(optimized_bytes))
        assert max(opt_img.size) <= 1800
        assert opt_img.format == "JPEG"

    def test_dedicated_ocr_engine_registration_and_priority(self):
        """Verify that dedicated OCR engines (e.g. DocTR, Surya) can be registered and take precedence over vision."""
        img = Image.new("RGB", (200, 200), color=(255, 255, 255))
        buf = io.BytesIO()
        img.save(buf, format="PDF")
        scanned_pdf_bytes = buf.getvalue()

        called_ocr_engine = False

        def mock_dedicated_ocr(file_bytes: bytes, target_indices: list) -> list:
            nonlocal called_ocr_engine
            called_ocr_engine = True
            assert len(file_bytes) > 0
            assert target_indices == [1]
            return [{
                "page": 1,
                "text": "DocTR / Surya High-Speed Local OCR Output",
                "raw_text": "DocTR / Surya High-Speed Local OCR Output",
                "sections": [],
                "is_scanned": True,
                "ocr_engine": "dedicated_engine"
            }]

        register_ocr_engine(mock_dedicated_ocr)
        try:
            pages = extract_text_from_file(scanned_pdf_bytes, filename="doctr_scanned.pdf")
            assert called_ocr_engine is True
            assert len(pages) == 1
            assert pages[0]["ocr_engine"] == "dedicated_engine"
            assert "DocTR / Surya High-Speed Local OCR Output" in pages[0]["text"]
        finally:
            register_ocr_engine(None)

    def test_mixed_digital_and_scanned_pdf_interleaving(self):
        """Verify that PDFs with mixed digital text and scanned image pages interleave in exact order."""
        import pypdf

        # Minimal valid PDF page with digital text stream
        raw_text_pdf = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 300 300] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj
4 0 obj << /Length 55 >>
stream
BT
/F1 12 Tf
72 200 Td
(Digital Text Page Content Here) Tj
ET
endstream
endobj
5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000230 00000 n 
0000000336 00000 n 
trailer << /Size 6 /Root 1 0 R >>
startxref
407
%%EOF"""

        # Scanned image for page 2
        img = Image.new("RGB", (200, 300), color=(255, 0, 0))
        img_buf = io.BytesIO()
        img.save(img_buf, format="PDF")

        # Assemble 3-page document: Page 1 (digital), Page 2 (scanned), Page 3 (digital)
        writer = pypdf.PdfWriter()
        writer.add_page(pypdf.PdfReader(io.BytesIO(raw_text_pdf)).pages[0])
        writer.add_page(pypdf.PdfReader(img_buf).pages[0])
        writer.add_page(pypdf.PdfReader(io.BytesIO(raw_text_pdf)).pages[0])

        out_buf = io.BytesIO()
        writer.write(out_buf)
        mixed_pdf_bytes = out_buf.getvalue()

        def mock_vision(img_bytes: bytes, page_num: int) -> str:
            assert page_num == 2
            return "Transcribed Scanned Exhibit Table on Page 2"

        register_vision_transcriber(mock_vision)
        try:
            pages = extract_text_from_file(mixed_pdf_bytes, filename="mixed_filing.pdf")
            assert len(pages) == 3
            assert pages[0]["page"] == 1
            assert pages[0]["is_scanned"] is False
            assert "Digital Text" in pages[0]["text"]

            assert pages[1]["page"] == 2
            assert pages[1]["is_scanned"] is True
            assert "Transcribed Scanned Exhibit" in pages[1]["text"]

            assert pages[2]["page"] == 3
            assert pages[2]["is_scanned"] is False
            assert "Digital Text" in pages[2]["text"]
        finally:
            register_vision_transcriber(None)

    def test_vision_worker_partial_failure_resilience(self):
        """Verify that transient failures on one page do not prevent other pages from completing."""
        images = [Image.new("RGB", (100, 100), color=(i * 40, 100, 100)) for i in range(3)]
        buf = io.BytesIO()
        images[0].save(buf, format="PDF", save_all=True, append_images=images[1:])
        scanned_pdf_bytes = buf.getvalue()

        def mock_failing_vision(img_bytes: bytes, page_num: int) -> str:
            if page_num == 2:
                # Page 2 fails
                raise RuntimeError("Simulated API rate limit error on page 2")
            return f"Transcribed page {page_num} successfully"

        register_vision_transcriber(mock_failing_vision)
        try:
            pages = extract_text_from_file(scanned_pdf_bytes, filename="partial_failure.pdf")
            # Pages 1 and 3 should be successfully extracted
            assert len(pages) == 2
            assert [p["page"] for p in pages] == [1, 3]
            assert "Transcribed page 1" in pages[0]["text"]
            assert "Transcribed page 3" in pages[1]["text"]
        finally:
            register_vision_transcriber(None)


