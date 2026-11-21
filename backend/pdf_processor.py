"""
Document processing and text extraction for Veridocs (PDF and TXT).
Fast, reliable, and lightweight extraction using pypdf.
"""

import io
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Union, Optional, Tuple
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
    chunk_size: int = 600,
    chunk_overlap: int = 100,
    document_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Split extracted pages into cohesive passage chunks (~700-800 characters with overlap),
    splitting before natural section headers and on paragraph boundaries.
    Preserves page number and document name metadata for every chunk.
    """
    all_chunks = []
    doc_prefix = f"[Document: {document_name}] " if document_name else ""

    for page_data in pages:
        page_num = page_data["page"]
        text = page_data["text"].strip()
        if not text:
            continue

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        current_lines: List[str] = []
        curr_len = 0

        for line in lines:
            # Check for major section headings (resumes, contracts, reports)
            is_heading = bool(
                re.match(r'^(?:SECTION\s*\d+|KEY\s+[A-Z\s]+|[A-Z\s&–—\-\:]{4,35})$', line)
                and len(line) < 40
                and not line.endswith(".")
            )

            # Break before heading if chunk is already substantive, or when max size reached
            if (is_heading and curr_len > 250) or (curr_len + len(line) + 1 > chunk_size):
                if current_lines:
                    chunk_text_str = " ".join(current_lines)
                    all_chunks.append({
                        "source_file": document_name or "document",
                        "page": page_num,
                        "text": f"{doc_prefix}{chunk_text_str}",
                    })

                    # Maintain word-boundary overlap
                    overlap_words = []
                    o_len = 0
                    for word_line in reversed(current_lines):
                        if o_len + len(word_line) + 1 <= chunk_overlap:
                            overlap_words.insert(0, word_line)
                            o_len += len(word_line) + 1
                        else:
                            break

                    current_lines = overlap_words + [line]
                    curr_len = sum(len(w) + 1 for w in current_lines)
                else:
                    current_lines = [line]
                    curr_len = len(line) + 1
            else:
                current_lines.append(line)
                curr_len += len(line) + 1

        if current_lines:
            chunk_text_str = " ".join(current_lines)
            all_chunks.append({
                "source_file": document_name or "document",
                "page": page_num,
                "text": f"{doc_prefix}{chunk_text_str}",
            })

    return all_chunks


def safe_delete_file(file_path: Path) -> bool:
    """Safely delete a file ensuring it is within the uploads directory."""
    from config import get_settings
    settings = get_settings()
    try:
        target = Path(file_path).resolve()
        base = Path(settings.UPLOAD_DIR).resolve()
        if base in target.parents or target == base:
            if target.is_file():
                target.unlink(missing_ok=True)
                return True
    except Exception as e:
        logger.warning(f"Error deleting file {file_path}: {e}")
    return False


async def save_upload_file_stream(
    file: Any,
    max_bytes: int,
    file_id: str,
    ext: str,
) -> Tuple[Path, int, bool]:
    """Stream-writes an UploadFile directly to disk in 1MB chunks."""
    from config import get_settings
    settings = get_settings()
    save_path = settings.UPLOAD_DIR / f"{file_id}{ext}"
    total_read = 0
    file_too_large = False

    with open(save_path, "wb") as out_f:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            total_read += len(chunk)
            if total_read > max_bytes:
                file_too_large = True
                break
            out_f.write(chunk)

    return save_path, total_read, file_too_large


def validate_question(question: str) -> None:
    """Validate query input."""
    from fastapi import HTTPException
    if not question or not question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    if len(question.strip()) > 1000:
        raise HTTPException(status_code=400, detail="Question exceeds maximum length of 1000 characters.")
