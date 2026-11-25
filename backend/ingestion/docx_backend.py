"""
DOCX and legacy DOC parser backend using python-docx and optional LibreOffice headless conversion.
Extracts paragraphs, heading hierarchy (section_path metadata), and structured tables
into the standardized ParsedDocument schema.
"""

import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from docx import Document as DocxDocument
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.text.paragraph import Paragraph
from docx.table import Table as DocxTable

from ingestion.base import ParserBackend, ParsedDocument, Page, TableData

logger = logging.getLogger(__name__)

_HEADING_STYLE_RE = re.compile(r"^Heading\s*(\d+)$", re.IGNORECASE)


def find_libreoffice_bin() -> Optional[str]:
    """Locate LibreOffice / soffice binary if installed."""
    for candidate in (
        shutil.which("soffice"),
        shutil.which("libreoffice"),
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
        "/usr/bin/soffice",
        "/usr/bin/libreoffice",
    ):
        if candidate and Path(candidate).exists():
            return candidate
    return None


def convert_doc_to_docx(doc_path: Path, output_dir: Path) -> Path:
    """
    Convert a legacy .doc file to .docx using LibreOffice headless mode.
    Raises ValueError with a clear message if LibreOffice is unavailable or conversion fails.
    """
    soffice = find_libreoffice_bin()
    if not soffice:
        raise ValueError(
            f"Cannot process legacy .doc file '{doc_path.name}': LibreOffice headless conversion "
            "is not installed on this server. Please convert the file to .docx or .pdf and upload again."
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix="lo_prof_") as prof_dir:
            res = subprocess.run(
                [
                    soffice,
                    f"-env:UserInstallation={Path(prof_dir).as_uri()}",
                    "--headless",
                    "--norestore",
                    "--convert-to",
                    "docx",
                    "--outdir",
                    str(output_dir),
                    str(doc_path),
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"LibreOffice conversion timed out for '{doc_path.name}'.") from exc
    except Exception as exc:
        raise ValueError(f"LibreOffice conversion failed for '{doc_path.name}': {exc}") from exc

    expected = output_dir / f"{doc_path.stem}.docx"
    if res.returncode != 0 or not expected.exists():
        err_detail = (res.stderr or res.stdout or "unknown error").strip()
        raise ValueError(f"Failed to convert legacy .doc file '{doc_path.name}': {err_detail}")

    return expected


def convert_office_to_pdf(input_path: Path, output_pdf_path: Path) -> Optional[Path]:
    """
    Convert a .docx or .doc file to PDF via LibreOffice headless so the PDF viewer
    and page-jump citations work seamlessly. Returns None if LibreOffice is unavailable.
    """
    soffice = find_libreoffice_bin()
    if not soffice:
        logger.info("LibreOffice not installed; skipping Office-to-PDF conversion for viewer.")
        return None

    output_dir = output_pdf_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with tempfile.TemporaryDirectory(prefix="lo_prof_") as prof_dir:
            res = subprocess.run(
                [
                    soffice,
                    f"-env:UserInstallation={Path(prof_dir).as_uri()}",
                    "--headless",
                    "--norestore",
                    "--convert-to",
                    "pdf",
                    "--outdir",
                    str(output_dir),
                    str(input_path),
                ],
                capture_output=True,
                text=True,
                timeout=90,
            )
        generated = output_dir / f"{input_path.stem}.pdf"
        if res.returncode == 0 and generated.exists():
            if generated.resolve() != output_pdf_path.resolve():
                shutil.move(str(generated), str(output_pdf_path))
            logger.info(f"Converted '{input_path.name}' to PDF for viewer: '{output_pdf_path.name}'")
            return output_pdf_path
        logger.warning(f"LibreOffice PDF conversion returned non-zero for '{input_path.name}': {res.stderr}")
    except Exception as e:
        logger.warning(f"LibreOffice PDF conversion error for '{input_path.name}': {e}")

    return None


def _heading_level_from_paragraph(para: Paragraph) -> Optional[int]:
    """Return 0-based/1-based heading level from Word paragraph style, or None if body text."""
    style = getattr(para, "style", None)
    style_name = (getattr(style, "name", "") or "").strip()
    style_id = (getattr(style, "style_id", "") or "").strip()

    for name in (style_name, style_id):
        if not name:
            continue
        low = name.lower()
        if low == "title":
            return 0
        if low == "subtitle":
            return 1
        m = _HEADING_STYLE_RE.match(name)
        if m:
            return int(m.group(1))
        if low.startswith("heading") and low[7:].isdigit():
            return int(low[7:])

    return None


def _paragraph_has_page_break(para: Paragraph) -> bool:
    """Detect explicit or rendered page breaks inside a Word paragraph XML."""
    xml = para._p.xml
    return ('w:type="page"' in xml) or ("w:type='page'" in xml) or ("lastRenderedPageBreak" in xml)


def _extract_docx_table(tbl: DocxTable, page_number: int, section_path: Optional[str]) -> Optional[TableData]:
    """Convert a python-docx Table into TableData (Markdown + structured JSON)."""
    raw_rows: List[List[str]] = []
    for row in tbl.rows:
        cells = [" ".join(cell.text.split()) for cell in row.cells]
        if any(cells):
            raw_rows.append(cells)

    if not raw_rows:
        return None

    col_count = max(len(r) for r in raw_rows)
    padded_rows = [r + [""] * (col_count - len(r)) for r in raw_rows]

    headers = padded_rows[0]
    data_rows = padded_rows[1:] if len(padded_rows) > 1 else []

    md_lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for r in data_rows:
        md_lines.append("| " + " | ".join(r) + " |")
    md_table = "\n".join(md_lines)

    return TableData(
        page_number=page_number,
        markdown=md_table,
        json_data={"headers": headers, "rows": data_rows, "section_path": section_path},
        bbox=None,
        section_path=section_path,
    )


class DocxParserBackend(ParserBackend):
    """Parser backend for .docx documents preserving heading hierarchy and tables."""

    VIRTUAL_PAGE_CHARS = 2500

    def parse(self, file_path: Path, filename: Optional[str] = None) -> ParsedDocument:
        fname = filename or file_path.name
        try:
            doc = DocxDocument(str(file_path))
        except Exception as e:
            raise ValueError(f"'{fname}' could not be parsed as a valid .docx document: {e}") from e

        heading_stack: List[Tuple[int, str]] = []
        current_section_path: Optional[str] = None

        pages: List[Page] = []
        current_blocks: List[Dict[str, Any]] = []
        current_tables: List[TableData] = []
        current_lines: List[str] = []
        current_chars = 0
        page_num = 1
        saw_headings = False

        def flush_page() -> None:
            nonlocal page_num, current_blocks, current_tables, current_lines, current_chars
            if not current_lines and not current_tables:
                return
            page_text = "\n".join(current_lines).strip()
            pages.append(
                Page(
                    number=page_num,
                    text=page_text,
                    blocks=list(current_blocks),
                    tables=list(current_tables),
                    extraction_method="text_layer",
                    ocr_confidence=None,
                    has_tables=len(current_tables) > 0,
                )
            )
            page_num += 1
            current_blocks = []
            current_tables = []
            current_lines = []
            current_chars = 0

        for child in doc.element.body.iterchildren():
            if isinstance(child, CT_P):
                para = Paragraph(child, doc)
                has_break = _paragraph_has_page_break(para)
                if has_break and (current_lines or current_tables):
                    flush_page()

                text = " ".join(para.text.split()).strip()
                if not text:
                    continue

                level = _heading_level_from_paragraph(para)
                is_heading = level is not None
                if is_heading and level is not None:
                    saw_headings = True
                    while heading_stack and heading_stack[-1][0] >= level:
                        heading_stack.pop()
                    heading_stack.append((level, text))
                    current_section_path = " > ".join(item[1] for item in heading_stack)

                if current_chars >= self.VIRTUAL_PAGE_CHARS and (current_lines or current_tables):
                    flush_page()

                current_lines.append(text)
                current_chars += len(text) + 1
                current_blocks.append(
                    {
                        "text": text,
                        "section_path": current_section_path,
                        "is_heading": is_heading,
                        "heading_level": level,
                    }
                )

            elif isinstance(child, CT_Tbl):
                tbl = DocxTable(child, doc)
                tbl_data = _extract_docx_table(tbl, page_num, current_section_path)
                if tbl_data:
                    current_tables.append(tbl_data)

        flush_page()

        # Fallback: check headers/footers if body was completely empty
        if not pages:
            extra_lines: List[str] = []
            for section in doc.sections:
                for p in section.header.paragraphs:
                    t = p.text.strip()
                    if t:
                        extra_lines.append(t)
                for p in section.footer.paragraphs:
                    t = p.text.strip()
                    if t:
                        extra_lines.append(t)
            fallback_text = "\n".join(extra_lines).strip()
            pages.append(
                Page(
                    number=1,
                    text=fallback_text,
                    blocks=[{"text": fallback_text, "section_path": None, "is_heading": False}]
                    if fallback_text
                    else [],
                    extraction_method="text_layer",
                )
            )

        return ParsedDocument(
            filename=fname,
            pages=pages,
            metadata={"source_format": "docx", "has_headings": saw_headings},
            total_pages=len(pages),
        )
