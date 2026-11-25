"""
Core data models and abstract interfaces for document parsers.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from pathlib import Path
from pydantic import BaseModel, Field


class TableData(BaseModel):
    """Structured table information."""

    page_number: int
    markdown: str
    json_data: Dict[str, Any] = Field(default_factory=dict)
    bbox: Optional[Dict[str, Any]] = None
    section_path: Optional[str] = None


class Page(BaseModel):
    """Extracted page data with text, layout blocks, tables, and OCR attribution."""

    number: int
    text: str
    blocks: List[Dict[str, Any]] = Field(default_factory=list)
    tables: List[TableData] = Field(default_factory=list)
    images: List[Dict[str, Any]] = Field(default_factory=list)
    extraction_method: str = "text_layer"  # "text_layer" | "ocr"
    ocr_confidence: Optional[float] = None
    has_figures: bool = False
    has_tables: bool = False
    has_signature_block: bool = False


class ParsedDocument(BaseModel):
    """Standardized document representation from any parser backend."""

    filename: str
    pages: List[Page]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    total_pages: int = 0

    def model_post_init(self, __context: Any) -> None:
        if not self.total_pages:
            self.total_pages = len(self.pages)


class ParserBackend(ABC):
    """Abstract interface that all parsing engines must implement."""

    @abstractmethod
    def parse(self, file_path: Path, filename: Optional[str] = None) -> ParsedDocument:
        """Parse file into standardized ParsedDocument structure."""
        pass
