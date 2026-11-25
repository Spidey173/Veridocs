"""
Ingestion subsystem for Veridocs: Multi-modal document parsing, OCR fallback, and table extraction.
"""

from ingestion.base import Page, ParsedDocument, ParserBackend, TableData
from ingestion.router import parse_document, validate_and_detect_file_type, convert_image_to_pdf

__all__ = [
    "Page",
    "ParsedDocument",
    "ParserBackend",
    "TableData",
    "parse_document",
    "validate_and_detect_file_type",
    "convert_image_to_pdf",
]
