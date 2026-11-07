import io
import re
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Callable, Union, Generator, Iterable, Any
import pypdf
from langchain_text_splitters import RecursiveCharacterTextSplitter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_spaced_text(text: str) -> str:
    """Reconstruct text that has spaces between every character."""
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


# Common heading patterns in documents
HEADING_PATTERNS = [
    re.compile(r'^(\d+\.[\d.]*)\s+(.+)$'),
    re.compile(r'^((?:I{1,3}|IV|V|VI{0,3}|IX|X{0,3})\.)\s+(.+)$', re.IGNORECASE),
    re.compile(r'^(ITEM\s+\d+[A-Z]?\.?)\s*(.*)$', re.IGNORECASE),
    re.compile(r'^(PART\s+(?:I{1,3}|IV)\.?)\s*(.*)$', re.IGNORECASE),
    re.compile(r'^([A-Z][A-Z\s&]{2,60})$'),
    re.compile(r'^([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s*:'),
    re.compile(r'^\*\*(.+)\*\*$'),
]


def detect_sections(text: str) -> List[Dict[str, str]]:
    """Detect section headings from text lines."""
    sections = []
    lines = text.split('\n')

    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or len(stripped) < 3:
            continue

        for j, pattern in enumerate(HEADING_PATTERNS):
            match = pattern.match(stripped)
            if match:
                level = 1 if j < 2 else 2
                heading_text = match.group(0).strip()

                if 3 <= len(heading_text) <= 100:
                    sections.append({
                        "heading": heading_text,
                        "line_index": i,
                        "level": level
                    })
                break

    return sections


def iter_pdf_pages(
    file_input: Union[bytes, str, Path, io.IOBase],
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Generator[Dict[str, Any], None, None]:
    """Stream PDF pages one by one to minimize memory usage on large documents."""
    close_stream = False
    if isinstance(file_input, (str, Path)):
        stream = open(file_input, "rb")
        close_stream = True
    elif isinstance(file_input, bytes):
        stream = io.BytesIO(file_input)
    else:
        stream = file_input

    try:
        try:
            reader = pypdf.PdfReader(stream)
        except Exception as e:
            logger.error(f"Failed to read PDF: {str(e)}")
            raise ValueError(f"Invalid or corrupted PDF file: {str(e)}")

        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as e:
                logger.error(f"Cannot decrypt PDF: {str(e)}")
                raise ValueError("PDF is encrypted and cannot be processed")

        total_pages = len(reader.pages)
        scanned_page_count = 0
        logger.info(f"Streaming text extraction for {total_pages} PDF pages")

        yielded_any = False
        scanned_indices = []

        for i, page in enumerate(reader.pages):
            if progress_callback and (i % 5 == 0 or i == total_pages - 1):
                progress_callback(i + 1, total_pages, f"Extracting digital text (page {i + 1}/{total_pages})")

            try:
                text = page.extract_text()

                if text:
                    text = fix_spaced_text(text)
                    cleaned_text = ' '.join(text.split())

                    if len(cleaned_text.strip()) > 10:
                        sections = detect_sections(text)
                        section_names = [s["heading"] for s in sections]

                        yielded_any = True
                        yield {
                            "page": i + 1,
                            "text": cleaned_text.strip(),
                            "raw_text": text,
                            "sections": section_names,
                            "is_scanned": False
                        }
                    else:
                        scanned_page_count += 1
                        scanned_indices.append(i + 1)
                else:
                    scanned_page_count += 1
                    scanned_indices.append(i + 1)

            except Exception as e:
                logger.warning(f"Error extracting text from page {i + 1}: {str(e)}")
                continue

        # If most pages appear to be scanned images, run OCR fallback
        if scanned_page_count > 0 and scanned_page_count >= total_pages * 0.5:
            logger.info(f"{scanned_page_count}/{total_pages} pages appear scanned. Running OCR fallback...")
            if isinstance(file_input, bytes):
                ocr_bytes = file_input
            elif isinstance(file_input, (str, Path)):
                ocr_bytes = Path(file_input).read_bytes()
            else:
                stream.seek(0)
                ocr_bytes = stream.read()

            ocr_pages = _ocr_pdf_pages(ocr_bytes, total_pages, progress_callback=progress_callback)
            for ocr_p in ocr_pages:
                if not yielded_any or ocr_p["page"] in scanned_indices:
                    yield ocr_p
                    yielded_any = True

        if not yielded_any:
            raise ValueError(
                "No readable text found in the PDF. The file might be scanned images only."
            )

    finally:
        if close_stream:
            stream.close()


def extract_text_from_pdf(
    file_input: Union[bytes, str, Path, io.IOBase],
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> List[Dict[str, Any]]:
    """Extract text from PDF pages as a list."""
    return list(iter_pdf_pages(file_input, progress_callback=progress_callback))


def _ocr_pdf_pages(
    file_bytes: bytes,
    total_pages: int,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> List[Dict]:
    """OCR fallback for scanned PDF pages using EasyOCR and PyMuPDF."""
    try:
        import easyocr
        import fitz
    except ImportError:
        logger.warning("OCR packages not installed (easyocr/pymupdf).")
        return []

    try:
        reader = easyocr.Reader(['en'], gpu=False, verbose=False)
        doc = fitz.open(stream=file_bytes, filetype="pdf")
        ocr_pages = []

        for page_num in range(min(total_pages, len(doc))):
            if progress_callback:
                progress_callback(
                    page_num + 1,
                    total_pages,
                    f"Running OCR on page {page_num + 1}/{total_pages}"
                )

            page = doc[page_num]
            pix = page.get_pixmap(dpi=200)
            img_bytes = pix.tobytes("png")

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

        doc.close()
        return ocr_pages

    except Exception as e:
        logger.warning(f"OCR processing failed: {str(e)}")
        return []


def extract_text_from_docx(file_bytes: bytes) -> List[Dict[str, str]]:
    """Extract text from DOCX files."""
    try:
        from docx import Document as DocxDocument
    except ImportError:
        raise ValueError("DOCX support requires python-docx package")

    try:
        doc = DocxDocument(io.BytesIO(file_bytes))
        pages = []
        current_text = []
        current_page = 1

        for para in doc.paragraphs:
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

        return pages

    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Error processing DOCX: {str(e)}")
        raise ValueError(f"Error processing DOCX file: {str(e)}")


def extract_text_from_txt(file_bytes: bytes) -> List[Dict[str, str]]:
    """Extract text from plain text files."""
    try:
        text = file_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = file_bytes.decode("latin-1")

    if not text.strip():
        raise ValueError("Text file is empty.")

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


def extract_text_from_file(
    file_input: Union[bytes, str, Path],
    filename: Optional[str] = None,
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> List[Dict[str, Any]]:
    """Extract text from PDF, DOCX, or TXT file bytes or path on disk."""
    if isinstance(file_input, (str, Path)):
        fname = filename or Path(file_input).name
        ext = Path(fname).suffix.lower()
        if ext == ".pdf":
            return extract_text_from_pdf(file_input, progress_callback=progress_callback)
        elif ext == ".docx":
            return extract_text_from_docx(Path(file_input).read_bytes())
        elif ext == ".txt":
            return extract_text_from_txt(Path(file_input).read_bytes())
        else:
            raise ValueError(f"Unsupported file type: {ext}. Supported: .pdf, .docx, .txt")
    else:
        fname = filename or "document"
        ext = Path(fname).suffix.lower()
        if ext == ".pdf":
            return extract_text_from_pdf(file_input, progress_callback=progress_callback)
        elif ext == ".docx":
            return extract_text_from_docx(file_input)
        elif ext == ".txt":
            return extract_text_from_txt(file_input)
        else:
            raise ValueError(f"Unsupported file type: {ext}. Supported: .pdf, .docx, .txt")


_FINANCIAL_NUM_RE = re.compile(
    r'^[\$€£¥]?\s*\(?[\d,]+(?:\.\d+)?\)?%?$'
)


def _is_table_line(line: str) -> bool:
    """Check if a line is part of a markdown, tab-separated, or borderless space-aligned table."""
    s = line.strip()
    if not s:
        return False

    # 1. Standard markdown tables (| col | col |)
    if s.startswith("|") and s.endswith("|") and s.count("|") >= 2:
        return True
    if re.match(r'^\|?[\s\-:]+(\|[\s\-:]+)+\|?$', s):
        return True

    # 2. Tab-separated tables
    if "\t" in s and len(s.split("\t")) >= 3:
        return True

    # 3. Accounting & table divider lines (e.g. "-----------------", "=================")
    if len(s) >= 8 and (s.count("-") >= 6 or s.count("=") >= 6 or s.count("_") >= 6):
        if re.match(r'^[\s\-=_]+$', s):
            return True

    # 4. Multi-column space-aligned financial lines (SEC 10-K balance sheets, cash flows, income statements)
    columns = [col.strip() for col in re.split(r'\s{2,}', s) if col.strip()]
    if len(columns) >= 3:
        num_count = sum(1 for c in columns if _FINANCIAL_NUM_RE.match(c))
        if num_count >= 1 or len(columns) >= 4:
            return True
    elif len(columns) == 2:
        if _FINANCIAL_NUM_RE.match(columns[1]):
            return True

    return False


def _format_table_block(block_text: str) -> str:
    """Ensure table block is formatted with markdown pipes for optimal LLM and embedding comprehension."""
    lines = block_text.strip().split("\n")
    if not lines:
        return block_text

    # If already formatted as a markdown table, return as is
    if any(line.strip().startswith("|") for line in lines):
        return block_text

    formatted_rows = []
    for line in lines:
        s = line.strip()
        if not s:
            continue
        if re.match(r'^[\s\-=_]+$', s):
            continue  # omit raw divider lines in markdown conversion

        if "\t" in s:
            cols = [c.strip() for c in s.split("\t") if c.strip()]
        else:
            cols = [c.strip() for c in re.split(r'\s{2,}', s) if c.strip()]

        if cols:
            formatted_rows.append("| " + " | ".join(cols) + " |")

    if len(formatted_rows) >= 2:
        col_count = formatted_rows[0].count("|") - 1
        sep = "| " + " | ".join(["---"] * max(col_count, 1)) + " |"
        return "\n".join([formatted_rows[0], sep] + formatted_rows[1:])
    elif formatted_rows:
        return "\n".join(formatted_rows)

    return block_text


def _extract_blocks(text: str) -> List[Tuple[str, bool]]:
    """Separate text lines into table blocks and regular paragraph blocks."""
    lines = text.split("\n")
    blocks = []
    current_lines = []
    in_table = False

    for i, line in enumerate(lines):
        is_tbl = _is_table_line(line)

        # Allow single blank line inside an active table if followed by another table line
        if not is_tbl and in_table and not line.strip():
            next_is_tbl = False
            for j in range(i + 1, min(i + 3, len(lines))):
                if lines[j].strip():
                    next_is_tbl = _is_table_line(lines[j])
                    break
            if next_is_tbl:
                is_tbl = True

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
    """Split document pages into overlapping text chunks with metadata."""
    try:
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len,
            is_separator_regex=False
        )

        chunks = []
        current_section = None

        for page_info in pages:
            page_num = page_info["page"]
            page_text = page_info["text"]
            page_sections = page_info.get("sections", [])
            is_scanned = page_info.get("is_scanned", False)

            if page_sections:
                if isinstance(page_sections[0], dict):
                    current_section = page_sections[0].get("heading", current_section)
                elif isinstance(page_sections[0], str):
                    current_section = page_sections[0]

            if not page_text or len(page_text.strip()) < 10:
                continue

            try:
                blocks = _extract_blocks(page_text)

                for block_text, is_table in blocks:
                    block_stripped = block_text.strip()
                    if not block_stripped:
                        continue

                    if is_table:
                        formatted_table = _format_table_block(block_stripped)
                        splits = [formatted_table] if len(formatted_table) <= chunk_size * 2 else text_splitter.split_text(formatted_table)
                    else:
                        splits = text_splitter.split_text(block_stripped)

                    for split in splits:
                        raw_split = split.strip()
                        if len(raw_split) > 15:
                            chunk_section = current_section
                            if isinstance(page_sections, list):
                                for sec in page_sections:
                                    sec_name = sec if isinstance(sec, str) else sec.get("heading", "")
                                    if sec_name and sec_name.lower() in raw_split.lower():
                                        chunk_section = sec_name
                                        break

                            parts = []
                            if document_name:
                                parts.append(f"Document: {document_name}")
                            if chunk_section:
                                parts.append(f"Section: {chunk_section}")
                            breadcrumb = f"[{' > '.join(parts)}]" if parts else ""

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

        return chunks

    except Exception as e:
        logger.error(f"Error in chunk_text: {str(e)}")
        return [
            {"page": p["page"], "text": p["text"][:chunk_size], "section": None, "is_scanned": False}
            for p in pages
            if p.get("text")
        ]


def get_pdf_metadata(file_input: Union[bytes, str, Path]) -> Optional[Dict]:
    """Extract metadata from PDF header."""
    try:
        close_file = False
        if isinstance(file_input, (str, Path)):
            stream = open(file_input, "rb")
            close_file = True
        else:
            stream = io.BytesIO(file_input)

        try:
            reader = pypdf.PdfReader(stream)
            return {
                "num_pages": len(reader.pages),
                "is_encrypted": reader.is_encrypted,
                "metadata": dict(reader.metadata) if reader.metadata else {}
            }
        finally:
            if close_file:
                stream.close()
    except Exception as e:
        logger.error(f"Failed to extract PDF metadata: {str(e)}")
        return None


def get_document_metadata(file_bytes: bytes, filename: str) -> Optional[Dict]:
    """Get metadata for a document file."""
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
            "num_pages": None,
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
