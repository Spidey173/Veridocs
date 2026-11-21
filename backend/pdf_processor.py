"""
Document processing and text extraction for Veridocs (PDF and TXT).
Fast, reliable, and lightweight extraction using pypdf.
"""

import io
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Union, Optional
import pypdf

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_input: Union[bytes, str, Path]) -> List[Dict[str, Any]]:
    """Extract text page-by-page from a PDF file."""
    if isinstance(file_input, (str, Path)):
        reader = pypdf.PdfReader(str(file_input))
    else:
        reader = pypdf.PdfReader(io.BytesIO(file_input))

    pages = []
    for idx, page in enumerate(reader.pages):
        try:
            text = page.extract_text() or ""
        except Exception as e:
            logger.warning(f"Failed to extract text from page {idx + 1}: {e}")
            text = ""

        # Clean excess null bytes or erratic whitespace
        clean_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
        clean_text = re.sub(r'\n{3,}', '\n\n', clean_text).strip()

        if clean_text:
            pages.append({
                "page": idx + 1,
                "text": clean_text
            })

    if not pages:
        raise ValueError("No extractable text found in PDF.")

    return pages


def extract_text_from_txt(file_input: Union[bytes, str, Path]) -> List[Dict[str, Any]]:
    """Extract text from a TXT file, splitting into virtual pages for long documents."""
    if isinstance(file_input, (str, Path)):
        raw = Path(file_input).read_bytes()
    else:
        raw = file_input

    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")

    text = text.strip()
    if not text:
        raise ValueError("Text file is empty.")

    # Split into virtual pages of roughly 2500 characters
    page_size = 2500
    pages = []
    total_len = len(text)
    page_num = 1
    start = 0

    while start < total_len:
        end = min(start + page_size, total_len)
        # Find clean boundary (paragraph or sentence)
        if end < total_len:
            boundary = text.rfind("\n\n", start, end)
            if boundary != -1 and boundary > start + 1000:
                end = boundary + 2
            else:
                space_boundary = text.rfind(". ", start, end)
                if space_boundary != -1 and space_boundary > start + 1000:
                    end = space_boundary + 2

        chunk_str = text[start:end].strip()
        if chunk_str:
            pages.append({
                "page": page_num,
                "text": chunk_str
            })
            page_num += 1
        start = end

    return pages


def extract_text_from_file(
    file_input: Union[bytes, str, Path],
    filename: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Extract text based on file extension."""
    fname = filename or (Path(file_input).name if isinstance(file_input, (str, Path)) else "document.pdf")
    ext = Path(fname).suffix.lower()

    if ext == ".pdf":
        return extract_text_from_pdf(file_input)
    elif ext == ".txt":
        return extract_text_from_txt(file_input)
    else:
        raise ValueError(f"Unsupported file type '{ext}'. Supported formats: .pdf, .txt")


def chunk_text(
    pages: List[Dict[str, Any]],
    chunk_size: int = 500,
    chunk_overlap: int = 50,
    document_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Split extracted pages into smaller chunks with metadata while preserving page numbers."""
    all_chunks = []
    doc_prefix = f"[Document: {document_name}]\n" if document_name else ""

    for page_data in pages:
        page_num = page_data["page"]
        text = page_data["text"]

        words = text.split()
        if not words:
            continue

        step = max(1, chunk_size - chunk_overlap)
        for i in range(0, len(words), step):
            chunk_words = words[i:i + chunk_size]
            if len(chunk_words) < 10 and all_chunks:
                # Avoid tiny trailing fragments
                continue

            chunk_text_str = " ".join(chunk_words)
            all_chunks.append({
                "source_file": document_name or "document",
                "page": page_num,
                "text": f"{doc_prefix}{chunk_text_str}" if doc_prefix else chunk_text_str,
            })

    return all_chunks


def get_document_metadata(file_bytes: bytes, filename: str) -> Dict[str, Any]:
    """Return basic metadata about the uploaded document."""
    ext = Path(filename).suffix.lower()
    num_pages = 1
    if ext == ".pdf":
        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            num_pages = len(reader.pages)
        except Exception:
            num_pages = 1

    return {
        "filename": filename,
        "file_size_bytes": len(file_bytes),
        "num_pages": num_pages,
    }
