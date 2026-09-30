"""
Enhanced PDF & document processor for DocuMind AI.
Features: metadata extraction, section detection, OCR fallback, DOCX/TXT support.
"""

import io
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import pypdf
from langchain_text_splitters import RecursiveCharacterTextSplitter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Text Cleaning Utilities
# ──────────────────────────────────────────────

def fix_spaced_text(text: str) -> str:
    """
    Detects and reconstructs text that was extracted with spaces between every character.
    Leaves normal text untouched.
    """
    if not text:
        return ""

    lines = text.splitlines()
    cleaned_lines = []

    for line in lines:
        tokens = line.split()
        if not tokens:
            cleaned_lines.append("")
            continue

        single_char_tokens = [t for t in tokens if len(t) == 1 and t.isalnum()]
        alnum_tokens = [t for t in tokens if any(c.isalnum() for c in t)]

        if len(alnum_tokens) > 3 and (len(single_char_tokens) / len(alnum_tokens)) > 0.4:
            parts = re.split(r'\s{2,}', line.strip())
            if len(parts) > 1:
                cleaned_parts = []
                for part in parts:
                    cleaned_word = part.replace(" ", "")
                    if cleaned_word:
                        cleaned_parts.append(cleaned_word)
                cleaned_line = " ".join(cleaned_parts)
            else:
                cleaned_line = line.replace(" ", "")
                cleaned_line = re.sub(r'([,.;:!?])', r'\1 ', cleaned_line)
                cleaned_line = " ".join(cleaned_line.split())

            cleaned_lines.append(cleaned_line)
        else:
            cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


# ──────────────────────────────────────────────
# Section / Heading Detection
# ──────────────────────────────────────────────

# Common heading patterns in documents
HEADING_PATTERNS = [
    # Numbered sections: "1. Introduction", "2.3 Methods"
    re.compile(r'^(\d+\.[\d.]*)\s+(.+)$'),
    # Roman numeral sections: "I. Introduction", "IV. Discussion"
    re.compile(r'^((?:I{1,3}|IV|V|VI{0,3}|IX|X{0,3})\.)\s+(.+)$', re.IGNORECASE),
    # ALL CAPS headings (at least 3 chars, not too long)
    re.compile(r'^([A-Z][A-Z\s&]{2,60})$'),
    # Title Case headings with colon
    re.compile(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*:'),
    # Bold-style markers often found in PDFs
    re.compile(r'^\*\*(.+)\*\*$'),
]


def detect_sections(text: str) -> List[Dict[str, str]]:
    """
    Detect section headings from extracted text.
    Returns list of {heading, start_pos, level}.
    """
    sections = []
    lines = text.split('\n')

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) < 3:
            continue

        for j, pattern in enumerate(HEADING_PATTERNS):
            match = pattern.match(stripped)
            if match:
                # Determine heading level based on pattern type
                level = 1 if j < 2 else 2
                heading_text = match.group(0).strip()

                # Filter out false positives: too short or too long
                if 3 <= len(heading_text) <= 100:
                    sections.append({
                        "heading": heading_text,
                        "line_index": i,
                        "level": level
                    })
                break

    return sections


def get_section_for_position(sections: List[Dict], line_index: int) -> Optional[str]:
    """Find which section a given line belongs to."""
    current_section = None
    for section in sections:
        if section["line_index"] <= line_index:
            current_section = section["heading"]
        else:
            break
    return current_section


# ──────────────────────────────────────────────
# PDF Text Extraction
# ──────────────────────────────────────────────

def extract_text_from_pdf(file_bytes: bytes) -> List[Dict[str, str]]:
    """
    Extract text from PDF bytes, returning list of pages with text, page number,
    and detected section information.

    Args:
        file_bytes: Raw bytes of the PDF file

    Returns:
        List of dictionaries with 'page', 'text', and optional 'sections' keys

    Raises:
        ValueError: If no text could be extracted
    """
    try:
        pdf_file = io.BytesIO(file_bytes)

        try:
            reader = pypdf.PdfReader(pdf_file)
        except Exception as e:
            logger.error(f"Failed to read PDF: {str(e)}")
            raise ValueError(f"Invalid or corrupted PDF file: {str(e)}")

        if reader.is_encrypted:
            logger.warning("PDF is encrypted, attempting to decrypt...")
            try:
                reader.decrypt("")
            except Exception as e:
                logger.error(f"Cannot decrypt PDF: {str(e)}")
                raise ValueError("PDF is encrypted and cannot be processed")

        pages = []
        total_pages = len(reader.pages)
        scanned_page_count = 0
        logger.info(f"Processing PDF with {total_pages} pages")

        for i, page in enumerate(reader.pages):
            try:
                text = page.extract_text()

                if text:
                    # Fix spaced-out text
                    text = fix_spaced_text(text)
                    cleaned_text = ' '.join(text.split())

                    if len(cleaned_text.strip()) > 10:
                        # Detect sections within this page
                        sections = detect_sections(text)
                        section_names = [s["heading"] for s in sections]

                        pages.append({
                            "page": i + 1,
                            "text": cleaned_text.strip(),
                            "raw_text": text,  # Keep raw for section mapping
                            "sections": section_names,
                            "is_scanned": False
                        })
                        logger.debug(f"Page {i + 1}: extracted {len(cleaned_text)} chars, {len(sections)} sections")
                    else:
                        scanned_page_count += 1
                        logger.debug(f"Page {i + 1}: insufficient text (possibly scanned)")
                else:
                    scanned_page_count += 1
                    logger.debug(f"Page {i + 1}: no text extracted (scanned/image)")

            except Exception as e:
                logger.warning(f"Error extracting text from page {i + 1}: {str(e)}")
                continue

        # Attempt OCR for scanned pages if too many failed
        if scanned_page_count > 0 and scanned_page_count >= total_pages * 0.5:
            logger.info(f"{scanned_page_count}/{total_pages} pages appear scanned. Attempting OCR...")
            ocr_pages = _ocr_pdf_pages(file_bytes, total_pages)
            if ocr_pages:
                # Merge OCR results with existing pages
                existing_page_nums = {p["page"] for p in pages}
                for ocr_page in ocr_pages:
                    if ocr_page["page"] not in existing_page_nums:
                        pages.append(ocr_page)
                pages.sort(key=lambda p: p["page"])

        if not pages:
            logger.error("No text could be extracted from any page")
            raise ValueError(
                "No readable text found in the PDF. The file might be scanned images only. "
                "OCR processing was attempted but could not extract text."
            )

        logger.info(f"Successfully extracted text from {len(pages)}/{total_pages} pages")
        return pages

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error processing PDF: {str(e)}")
        raise Exception(f"Error processing PDF: {str(e)}")


def _ocr_pdf_pages(file_bytes: bytes, total_pages: int) -> List[Dict]:
    """
    OCR fallback for scanned PDF pages.
    Converts pages to images and runs EasyOCR.
    """
    try:
        import easyocr
        import fitz  # PyMuPDF for page-to-image conversion
    except ImportError:
        logger.warning(
            "OCR dependencies not available (easyocr/PyMuPDF). "
            "Install with: pip install easyocr pymupdf"
        )
        return []

    try:
        reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        ocr_pages = []

        for page_num in range(min(total_pages, len(doc))):
            page = doc[page_num]
            # Render page to image at 200 DPI
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")

            # Run OCR
            results = reader.readtext(img_bytes, detail=0, paragraph=True)
            text = " ".join(results)

            if text and len(text.strip()) > 20:
                ocr_pages.append({
                    "page": page_num + 1,
                    "text": text.strip(),
                    "raw_text": text,
                    "sections": [],
                    "is_scanned": True
                })
                logger.debug(f"OCR Page {page_num + 1}: extracted {len(text)} chars")

        doc.close()
        logger.info(f"OCR extracted text from {len(ocr_pages)} pages")
        return ocr_pages

    except Exception as e:
        logger.warning(f"OCR processing failed: {str(e)}")
        return []


# ──────────────────────────────────────────────
# DOCX Support
# ──────────────────────────────────────────────

def extract_text_from_docx(file_bytes: bytes) -> List[Dict[str, str]]:
    """Extract text from DOCX files, treating each page-break-delimited section as a 'page'."""
    try:
        from docx import Document as DocxDocument
    except ImportError:
        logger.warning("python-docx not installed. Install with: pip install python-docx")
        raise ValueError("DOCX support requires python-docx package")

    try:
        doc = DocxDocument(io.BytesIO(file_bytes))
        pages = []
        current_text = []
        current_page = 1

        for para in doc.paragraphs:
            # Check for page break
            for run in para.runs:
                if run._element.xml.find('w:br') != -1 and 'type="page"' in run._element.xml:
                    if current_text:
                        combined = " ".join(current_text)
                        if len(combined.strip()) > 10:
                            pages.append({
                                "page": current_page,
                                "text": combined.strip(),
                                "raw_text": "\n".join(current_text),
                                "sections": [],
                                "is_scanned": False
                            })
                        current_page += 1
                        current_text = []

            if para.text.strip():
                current_text.append(para.text.strip())

        # Don't forget the last page
        if current_text:
            combined = " ".join(current_text)
            if len(combined.strip()) > 10:
                pages.append({
                    "page": current_page,
                    "text": combined.strip(),
                    "raw_text": "\n".join(current_text),
                    "sections": [],
                    "is_scanned": False
                })

        if not pages:
            raise ValueError("No readable text found in the DOCX file.")

        logger.info(f"Extracted text from DOCX: {len(pages)} sections")
        return pages

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Error processing DOCX: {str(e)}")
        raise ValueError(f"Error processing DOCX file: {str(e)}")


# ──────────────────────────────────────────────
# TXT Support
# ──────────────────────────────────────────────

def extract_text_from_txt(file_bytes: bytes) -> List[Dict[str, str]]:
    """Extract text from plain text files, splitting into logical pages."""
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    if not text.strip():
        raise ValueError("Text file is empty.")

    # Split into pages of ~3000 chars each
    page_size = 3000
    pages = []
    for i in range(0, len(text), page_size):
        page_text = text[i:i + page_size].strip()
        if len(page_text) > 10:
            page_num = (i // page_size) + 1
            pages.append({
                "page": page_num,
                "text": page_text,
                "raw_text": page_text,
                "sections": detect_sections(page_text),
                "is_scanned": False
            })

    if not pages:
        raise ValueError("No readable text found in the file.")

    return pages


# ──────────────────────────────────────────────
# Universal Document Extractor
# ──────────────────────────────────────────────

def extract_text_from_file(file_bytes: bytes, filename: str) -> List[Dict[str, str]]:
    """
    Route to the correct extractor based on file extension.
    Supports: PDF, DOCX, TXT
    """
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_bytes)
    elif ext == ".docx":
        return extract_text_from_docx(file_bytes)
    elif ext == ".txt":
        return extract_text_from_txt(file_bytes)
    else:
        raise ValueError(f"Unsupported file type: {ext}. Supported: .pdf, .docx, .txt")


# ──────────────────────────────────────────────
# Chunking with Metadata
# ──────────────────────────────────────────────

def _is_table_line(line: str) -> bool:
    """Check if a line looks like part of a Markdown or formatted table."""
    s = line.strip()
    if not s:
        return False
    if s.startswith("|") and s.endswith("|") and s.count("|") >= 2:
        return True
    if re.match(r'^\|?[\s\-:]+(\|[\s\-:]+)+\|?$', s):
        return True
    if "\t" in s and len(s.split("\t")) >= 3:
        return True
    return False


def _extract_blocks(text: str) -> List[Tuple[str, bool]]:
    """
    Split text into alternating blocks of (content, is_table).
    Markdown and formatted tables are kept as atomic blocks.
    """
    lines = text.split("\n")
    blocks = []
    current_lines = []
    in_table = False

    for line in lines:
        is_tbl = _is_table_line(line)
        if is_tbl != in_table:
            if current_lines:
                blocks.append(("\n".join(current_lines), in_table))
                current_lines = []
            in_table = is_tbl
        current_lines.append(line)

    if current_lines:
        blocks.append(("\n".join(current_lines), in_table))

    return blocks


def chunk_text(
        pages: List[Dict[str, str]],
        chunk_size: int = 500,
        chunk_overlap: int = 50,
        document_name: Optional[str] = None
) -> List[Dict]:
    """
    Split page texts into overlapping chunks, preserving page, table, and section metadata.
    Injects hierarchical breadcrumbs: [Document: Report.pdf > Section: 2.1 Balance Sheet].

    Each chunk includes:
    - page: page number
    - text: chunk content with hierarchical breadcrumb
    - raw_text: original text content
    - section: detected section heading (if any)
    - breadcrumb: formatted breadcrumb
    - is_table: whether this chunk contains a structured table
    - is_scanned: whether this came from OCR
    """
    try:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
            is_separator_regex=False
        )

        chunks = []
        # Track global section context across pages
        current_section = None

        for page_info in pages:
            page_num = page_info["page"]
            page_text = page_info["text"]
            page_sections = page_info.get("sections", [])
            is_scanned = page_info.get("is_scanned", False)

            # Update current section if this page has headings
            if page_sections:
                if isinstance(page_sections[0], dict):
                    current_section = page_sections[0].get("heading", current_section)
                elif isinstance(page_sections[0], str):
                    current_section = page_sections[0]

            if not page_text or len(page_text.strip()) < 10:
                continue

            try:
                # Segment page into table blocks vs regular text blocks
                blocks = _extract_blocks(page_text)

                for block_text, is_table in blocks:
                    block_stripped = block_text.strip()
                    if not block_stripped:
                        continue

                    # If this block is a table, keep it intact if possible
                    if is_table:
                        splits = [block_stripped] if len(block_stripped) <= chunk_size * 2 else text_splitter.split_text(block_stripped)
                    else:
                        splits = text_splitter.split_text(block_stripped)

                    for split in splits:
                        raw_split = split.strip()
                        if len(raw_split) > 15:
                            # Try to find which section this chunk belongs to
                            chunk_section = current_section
                            if isinstance(page_sections, list):
                                for sec in page_sections:
                                    sec_name = sec if isinstance(sec, str) else sec.get("heading", "")
                                    if sec_name and sec_name.lower() in raw_split.lower():
                                        chunk_section = sec_name
                                        break

                            # Build hierarchical breadcrumb
                            parts = []
                            if document_name:
                                parts.append(f"Document: {document_name}")
                            if chunk_section:
                                parts.append(f"Section: {chunk_section}")
                            breadcrumb = f"[{' > '.join(parts)}]" if parts else ""

                            # Enrich chunk with breadcrumb for high-precision retrieval
                            enriched_text = f"{breadcrumb}\n{raw_split}" if breadcrumb else raw_split

                            chunks.append({
                                "page": page_num,
                                "text": enriched_text,
                                "raw_text": raw_split,
                                "section": chunk_section,
                                "breadcrumb": breadcrumb,
                                "is_table": is_table,
                                "is_scanned": is_scanned,
                            })

            except Exception as e:
                logger.warning(f"Error chunking page {page_num}: {str(e)}")
                if len(page_text) <= chunk_size * 2:
                    raw_text = page_text.strip()
                    parts = []
                    if document_name:
                        parts.append(f"Document: {document_name}")
                    if current_section:
                        parts.append(f"Section: {current_section}")
                    breadcrumb = f"[{' > '.join(parts)}]" if parts else ""
                    enriched = f"{breadcrumb}\n{raw_text}" if breadcrumb else raw_text

                    chunks.append({
                        "page": page_num,
                        "text": enriched,
                        "raw_text": raw_text,
                        "section": current_section,
                        "breadcrumb": breadcrumb,
                        "is_table": False,
                        "is_scanned": is_scanned,
                    })

        logger.info(f"Created {len(chunks)} chunks from {len(pages)} pages")

        if not chunks:
            logger.warning("No chunks were created from the pages")

        return chunks

    except Exception as e:
        logger.error(f"Error in chunk_text: {str(e)}")
        logger.warning("Falling back to page-level chunks")
        return [
            {"page": p["page"], "text": p["text"][:chunk_size], "section": None, "is_scanned": False}
            for p in pages
            if p.get("text")
        ]


# ──────────────────────────────────────────────
# PDF Metadata
# ──────────────────────────────────────────────

def get_pdf_metadata(file_bytes: bytes) -> Optional[Dict]:
    """
    Extract metadata from PDF without full text extraction.
    Useful for quick validation.
    """
    try:
        pdf_file = io.BytesIO(file_bytes)
        reader = pypdf.PdfReader(pdf_file)

        return {
            "num_pages": len(reader.pages),
            "is_encrypted": reader.is_encrypted,
            "metadata": dict(reader.metadata) if reader.metadata else {}
        }
    except Exception as e:
        logger.error(f"Failed to extract PDF metadata: {str(e)}")
        return None


def get_document_metadata(file_bytes: bytes, filename: str) -> Optional[Dict]:
    """Get metadata for any supported document type."""
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        meta = get_pdf_metadata(file_bytes)
        if meta:
            meta["filename"] = filename
            meta["file_size_bytes"] = len(file_bytes)
        return meta
    elif ext == ".docx":
        return {
            "filename": filename,
            "file_size_bytes": len(file_bytes),
            "num_pages": None,  # DOCX doesn't have fixed pages
            "is_encrypted": False,
            "metadata": {}
        }
    elif ext == ".txt":
        return {
            "filename": filename,
            "file_size_bytes": len(file_bytes),
            "num_pages": max(1, len(file_bytes) // 3000),
            "is_encrypted": False,
            "metadata": {}
        }
    else:
        return None