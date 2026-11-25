"""
Base models and interface for multimodal vision analysis.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class FigureInfo(BaseModel):
    """Visual figure extracted from page rendering (chart, diagram, photo, etc.)."""

    type: Literal["chart", "diagram", "photo", "logo", "other"] = "other"
    title: str = Field(default="", description="Short title or caption of the visual figure")
    description: str = Field(default="", description="Detailed factual description of visual elements")
    data_points: List[str] = Field(default_factory=list, description="Key data values or trend series")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class SignatureInfo(BaseModel):
    """Detected signature block and execution status."""

    present: bool = Field(default=False, description="Whether a signature block exists on the page")
    signed: Optional[bool] = Field(
        default=None, description="True if executed/inked, False if blank line, None if uncertain"
    )
    location_hint: str = Field(default="", description="Approximate page position (e.g., bottom-left, footer)")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class PageVisionOutput(BaseModel):
    """Structured multimodal vision output for a single page."""

    page_number: int
    figures: List[FigureInfo] = Field(default_factory=list)
    signatures: List[SignatureInfo] = Field(default_factory=list)
    layout_notes: str = Field(default="", description="Observations on visual arrangement, stamps, or watermarks")
    model: str = Field(default="", description="Vision model identifier used")
    cost_tokens: int = Field(default=0, ge=0)


class VisionBackend(ABC):
    """Abstract interface for multimodal vision backends."""

    @abstractmethod
    def analyze_page(
        self, image_bytes: bytes, page_number: int, context_text: Optional[str] = None
    ) -> PageVisionOutput:
        """Analyze page image and return structured visual figures, signatures, and notes."""
        pass
