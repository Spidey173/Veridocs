"""
Ingestion router: Magic-bytes verification, security limits, image-to-PDF conversion,
and parser backend dispatching.
"""

import zipfile
import logging
from pathlib import Path
from typing import Optional
from PIL import Image

from config import get_settings
from ingestion.base import ParsedDocument
from ingestion.pymupdf_backend import PyMuPDFBackend
from ingestion.docling_backend import DoclingBackend
from ingestion.docx_backend import (
    DocxParserBackend,
    convert_doc_to_docx,
    convert_office_to_pdf,
    find_libreoffice_bin,
)

logger = logging.getLogger(__name__)

# File magic byte signatures
MAGIC_SIGNATURES = {
    "pdf": b"%PDF-",
    "png": b"\x89PNG\r\n\x1a\n",
    "jpeg": b"\xff\xd8\xff",
    "tiff_le": b"II*\x00",
    "tiff_be": b"MM\x00*",
    "zip": b"PK\x03\x04",
    "zip_empty": b"PK\x05\x06",
    "ole2": b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
}


def validate_and_detect_file_type(file_path: Path) -> str:
    """
    Validate file by magic bytes rather than extension alone.
    Returns detected format ('pdf', 'png', 'jpeg', 'tiff', 'docx', 'doc', 'txt').
    Raises ValueError with user-friendly message if invalid or corrupt.
    """
    if not file_path.exists():
        raise ValueError(f"File '{file_path.name}' does not exist.")

    header = file_path.read_bytes()[:16]

    if header.startswith(MAGIC_SIGNATURES["pdf"]):
        # Validate that PDF is not corrupt or encrypted
        try:
            import pypdf

            reader = pypdf.PdfReader(str(file_path))
            if reader.is_encrypted:
                raise ValueError(
                    f"'{file_path.name}' is password-protected or encrypted. Please decrypt before uploading."
                )
            _ = len(reader.pages)
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"'{file_path.name}' is corrupt or not a valid PDF: {str(e)}")
        return "pdf"

    if header.startswith(MAGIC_SIGNATURES["png"]):
        return "png"

    if header.startswith(MAGIC_SIGNATURES["jpeg"]):
        return "jpeg"

    if header.startswith(MAGIC_SIGNATURES["tiff_le"]) or header.startswith(MAGIC_SIGNATURES["tiff_be"]):
        return "tiff"

    if header.startswith(MAGIC_SIGNATURES["zip"]) or header.startswith(MAGIC_SIGNATURES["zip_empty"]):
        try:
            with zipfile.ZipFile(file_path, "r") as zf:
                names = zf.namelist()
                has_content_types = "[Content_Types].xml" in names
                has_word_entry = any(n.startswith("word/") for n in names)
                if has_content_types and has_word_entry:
                    return "docx"
        except zipfile.BadZipFile as e:
            raise ValueError(f"'{file_path.name}' is corrupt or not a valid .docx archive: {str(e)}") from e
        raise ValueError(
            f"File '{file_path.name}' is a ZIP archive but not a valid .docx document "
            "(missing [Content_Types].xml or word/ entries)."
        )

    if header.startswith(MAGIC_SIGNATURES["ole2"]):
        if file_path.suffix.lower() == ".doc" or True:
            return "doc"

    # Check if text file (valid UTF-8 or ASCII text)
    try:
        sample = file_path.read_bytes()[:4096]
        # Text should not have significant null bytes
        if b"\x00" not in sample:
            sample.decode("utf-8")
            return "txt"
    except UnicodeDecodeError:
        try:
            sample.decode("latin-1")
            return "txt"
        except Exception:
            pass

    ext = file_path.suffix.lower()
    raise ValueError(
        f"File '{file_path.name}' has invalid magic bytes for format '{ext}'. "
        "Upload PDF, DOCX, DOC, PNG, JPG, TIFF, or TXT."
    )


def convert_image_to_pdf(image_path: Path, output_pdf_path: Path) -> Path:
    """
    Convert an image (PNG, JPG, or multi-page TIFF) into a standard PDF so the
    PDF viewer renders it seamlessly and citation navigation behaves identically.
    """
    with Image.open(image_path) as img:
        frames = []
        try:
            while True:
                frames.append(img.copy().convert("RGB"))
                img.seek(img.tell() + 1)
        except EOFError:
            pass

        if not frames:
            frames = [img.convert("RGB")]

        first = frames[0]
        if len(frames) > 1:
            first.save(output_pdf_path, "PDF", resolution=150.0, save_all=True, append_images=frames[1:])
        else:
            first.save(output_pdf_path, "PDF", resolution=150.0)

    logger.info(f"Converted image '{image_path.name}' to PDF: '{output_pdf_path.name}' ({len(frames)} pages)")
    return output_pdf_path


def parse_document(file_path: Path, filename: Optional[str] = None) -> ParsedDocument:
    """
    Parse a document using the configured backend (Docling or PyMuPDF).
    Enforces file size and page count limits from config.
    """
    settings = get_settings()
    fname = filename or file_path.name

    # 1. Validate magic bytes and format
    file_type = validate_and_detect_file_type(file_path)

    # 2. Check file size limit
    size_mb = file_path.stat().st_size / (1024 * 1024)
    if size_mb > settings.MAX_FILE_SIZE_MB:
        raise ValueError(
            f"'{fname}' ({size_mb:.1f}MB) exceeds the maximum allowed size of {settings.MAX_FILE_SIZE_MB}MB."
        )

    # 3. Handle image or Office-to-PDF conversion for viewer
    if file_type in ("png", "jpeg", "tiff"):
        pdf_name = f"{file_path.stem}_converted.pdf"
        target_pdf = file_path.parent / pdf_name
        convert_image_to_pdf(file_path, target_pdf)

    parse_target = file_path
    if file_type == "doc":
        if not find_libreoffice_bin():
            raise ValueError(
                f"Cannot process legacy .doc file '{fname}': LibreOffice headless conversion "
                "is not installed on this server. Please convert to .docx or .pdf and re-upload."
            )
        converted_docx = convert_doc_to_docx(file_path, file_path.parent)
        convert_office_to_pdf(converted_docx, file_path.parent / f"{file_path.stem}_converted.pdf")
        parse_target = converted_docx
        file_type = "docx"
    elif file_type == "docx":
        convert_office_to_pdf(file_path, file_path.parent / f"{file_path.stem}_converted.pdf")

    # 4. Dispatch to configured parser backend
    if file_type == "docx":
        backend = DocxParserBackend()
        parsed = backend.parse(parse_target, fname)
    else:
        backend_name = settings.PARSER_BACKEND
        if backend_name == "docling":
            backend = DoclingBackend()
        else:
            backend = PyMuPDFBackend()
        parsed = backend.parse(parse_target, fname)

    # 5. Check page count limit
    if parsed.total_pages > settings.MAX_PDF_PAGES:
        raise ValueError(
            f"'{fname}' has {parsed.total_pages} pages, which exceeds the maximum limit of {settings.MAX_PDF_PAGES} pages."
        )

    return parsed
