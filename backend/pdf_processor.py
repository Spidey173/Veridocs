"""
Document processing, chunking, and table extraction for Veridocs.
Integrates with ingestion router (Docling / PyMuPDF + OCR / DOCX).
"""

import logging
from pathlib import Path
from typing import List, Dict, Any, Union, Optional, Tuple

from config import get_settings
from ingestion.router import parse_document
from ingestion.base import ParsedDocument
from ingestion.headings import SectionTracker

logger = logging.getLogger(__name__)


def extract_text_from_file(file_input: Union[bytes, str, Path], filename: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Extract text page-by-page from a file (PDF, TXT, or converted image).
    Returns list of dicts: [{"page": page_num, "text": clean_text, "tables": [...], ...}]
    """
    settings = get_settings()
    fname = filename or (Path(file_input).name if isinstance(file_input, (str, Path)) else "document.pdf")

    if isinstance(file_input, (str, Path)) and Path(file_input).exists():
        temp_path = Path(file_input)
        should_clean = False
    else:
        # Save bytes to a temp file in uploads
        temp_path = settings.UPLOAD_DIR / f"temp_{fname}"
        raw_bytes = file_input if isinstance(file_input, bytes) else file_input.encode("utf-8")
        temp_path.write_bytes(raw_bytes)
        should_clean = True

    try:
        parsed: ParsedDocument = parse_document(temp_path, filename=fname)
        pages_out = []
        for p in parsed.pages:
            pages_out.append(
                {
                    "page": p.number,
                    "page_number": p.number,
                    "text": p.text,
                    "blocks": p.blocks,
                    "tables": [t.model_dump() for t in p.tables],
                    "extraction_method": p.extraction_method,
                    "ocr_confidence": p.ocr_confidence,
                    "has_figures": p.has_figures,
                    "has_tables": p.has_tables,
                }
            )
        return pages_out
    finally:
        if should_clean and temp_path.exists():
            temp_path.unlink(missing_ok=True)


def chunk_text(
    pages: List[Dict[str, Any]],
    chunk_size: int = 600,
    chunk_overlap: int = 100,
    document_name: Optional[str] = None,
    document_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Split extracted pages into cohesive passage chunks (~600 chars with 100 char overlap)
    and create dedicated table chunks (never split mid-row) for retrieval.
    Preserves page number, chunk_type, extraction_method, and document name.
    """
    all_chunks = []
    doc_prefix = f"[Document: {document_name}] " if document_name else ""
    fallback_tracker = SectionTracker()

    for page_data in pages:
        page_num = page_data.get("page") or page_data.get("page_number", 1)
        text = page_data.get("text", "").strip()
        extraction_method = page_data.get("extraction_method", "text_layer")
        ocr_confidence = page_data.get("ocr_confidence")

        # 1. Create dedicated chunks for extracted tables
        tables = page_data.get("tables", [])
        for tbl in tables:
            md_table = tbl.get("markdown") if isinstance(tbl, dict) else getattr(tbl, "markdown", "")
            tbl_json = tbl.get("json_data") if isinstance(tbl, dict) else getattr(tbl, "json_data", {})
            tbl_section = (
                tbl.get("section_path") if isinstance(tbl, dict) else getattr(tbl, "section_path", None)
            ) or (tbl_json.get("section_path") if isinstance(tbl_json, dict) else None)
            if md_table and md_table.strip():
                section_note = f" [Section: {tbl_section}]" if tbl_section else ""
                table_content = f"{doc_prefix}[Table on Page {page_num}]{section_note}\n{md_table.strip()}"
                all_chunks.append(
                    {
                        "document_id": document_id,
                        "source_file": document_name or "document",
                        "filename": document_name or "document",
                        "page": page_num,
                        "page_number": page_num,
                        "text": table_content,
                        "content": table_content,
                        "chunk_type": "table",
                        "section_path": tbl_section,
                        "extraction_method": extraction_method,
                        "ocr_confidence": ocr_confidence,
                        "metadata": {
                            "chunk_type": "table",
                            "page": page_num,
                            "source_file": document_name or "document",
                            "section_path": tbl_section,
                            "extraction_method": extraction_method,
                            "ocr_confidence": ocr_confidence,
                            "table_json": tbl_json,
                        },
                    }
                )

        # 2. Split standard narrative text into passage chunks (~600 chars, 100 overlap)
        blocks = page_data.get("blocks") or []
        if blocks:
            current_lines: List[str] = []
            curr_len = 0
            curr_section: Optional[str] = None

            def emit_block_chunk(lines_buf: List[str], sec: Optional[str]) -> None:
                if not lines_buf:
                    return
                chunk_text_str = " ".join(lines_buf)
                full_content = f"{doc_prefix}{chunk_text_str}"
                all_chunks.append(
                    {
                        "document_id": document_id,
                        "source_file": document_name or "document",
                        "filename": document_name or "document",
                        "page": page_num,
                        "page_number": page_num,
                        "text": full_content,
                        "content": full_content,
                        "chunk_type": "text",
                        "section_path": sec,
                        "extraction_method": extraction_method,
                        "ocr_confidence": ocr_confidence,
                        "metadata": {
                            "chunk_type": "text",
                            "page": page_num,
                            "source_file": document_name or "document",
                            "section_path": sec,
                            "extraction_method": extraction_method,
                            "ocr_confidence": ocr_confidence,
                        },
                    }
                )

            for blk in blocks:
                line = (blk.get("text") or "").strip()
                if not line:
                    continue
                blk_section = blk.get("section_path")
                is_heading = bool(blk.get("is_heading"))

                if curr_section is None and blk_section:
                    curr_section = blk_section

                section_changed = is_heading and blk_section and blk_section != curr_section
                if (section_changed and current_lines) or (curr_len + len(line) + 1 > chunk_size and current_lines):
                    emit_block_chunk(current_lines, curr_section)
                    if section_changed:
                        current_lines = [line]
                        curr_len = len(line) + 1
                        curr_section = blk_section
                    else:
                        overlap_words: List[str] = []
                        o_len = 0
                        for word_line in reversed(current_lines):
                            if o_len + len(word_line) + 1 <= chunk_overlap:
                                overlap_words.insert(0, word_line)
                                o_len += len(word_line) + 1
                            else:
                                break
                        current_lines = overlap_words + [line]
                        curr_len = sum(len(w) + 1 for w in current_lines)
                        if blk_section:
                            curr_section = blk_section
                else:
                    current_lines.append(line)
                    curr_len += len(line) + 1
                    if blk_section:
                        curr_section = blk_section

            emit_block_chunk(current_lines, curr_section)
            continue

        if not text:
            continue

        lines = [l.strip() for l in text.split("\n") if l.strip()]
        current_lines: List[str] = []
        curr_len = 0
        curr_section: Optional[str] = fallback_tracker.current_path

        for line in lines:
            blk_info = fallback_tracker.process_line(line)
            is_heading = bool(blk_info["is_heading"])
            blk_sec = blk_info["section_path"]

            if (is_heading and curr_len > 250) or (curr_len + len(line) + 1 > chunk_size):
                if current_lines:
                    chunk_text_str = " ".join(current_lines)
                    full_content = f"{doc_prefix}{chunk_text_str}"
                    all_chunks.append(
                        {
                            "document_id": document_id,
                            "source_file": document_name or "document",
                            "filename": document_name or "document",
                            "page": page_num,
                            "page_number": page_num,
                            "text": full_content,
                            "content": full_content,
                            "chunk_type": "text",
                            "section_path": curr_section,
                            "extraction_method": extraction_method,
                            "ocr_confidence": ocr_confidence,
                            "metadata": {
                                "chunk_type": "text",
                                "page": page_num,
                                "source_file": document_name or "document",
                                "section_path": curr_section,
                                "extraction_method": extraction_method,
                                "ocr_confidence": ocr_confidence,
                            },
                        }
                    )

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
                    curr_section = blk_sec
                else:
                    current_lines = [line]
                    curr_len = len(line) + 1
                    curr_section = blk_sec
            else:
                current_lines.append(line)
                curr_len += len(line) + 1
                if blk_sec:
                    curr_section = blk_sec

        if current_lines:
            chunk_text_str = " ".join(current_lines)
            full_content = f"{doc_prefix}{chunk_text_str}"
            all_chunks.append(
                {
                    "document_id": document_id,
                    "source_file": document_name or "document",
                    "filename": document_name or "document",
                    "page": page_num,
                    "page_number": page_num,
                    "text": full_content,
                    "content": full_content,
                    "chunk_type": "text",
                    "section_path": curr_section,
                    "extraction_method": extraction_method,
                    "ocr_confidence": ocr_confidence,
                    "metadata": {
                        "chunk_type": "text",
                        "page": page_num,
                        "source_file": document_name or "document",
                        "section_path": curr_section,
                        "extraction_method": extraction_method,
                        "ocr_confidence": ocr_confidence,
                    },
                }
            )

    return all_chunks


def safe_delete_file(file_path: Path) -> bool:
    """Safely delete a file ensuring it is within the uploads directory."""
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
