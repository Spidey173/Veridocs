"""
Pydantic schemas for structured extraction across document types.
Every extracted field carries evidence: value, page, quote, confidence, verified status,
and math_mismatch indicators.
"""

from typing import List, Optional, Any
from pydantic import BaseModel, Field


class FieldEvidence(BaseModel):
    """Evidence model wrapped around every extracted field."""

    value: Any = None
    page: int = Field(default=1, description="1-indexed source page number")
    quote: str = Field(default="", max_length=250, description="Verbatim source quote <=200 chars")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    verified: bool = Field(default=False, description="True if quote confirmed verbatim in page text")
    math_mismatch: bool = Field(default=False, description="Flagged if numerical calculation fails math check")


class InvoiceLineItem(BaseModel):
    """Single line item on an invoice."""

    description: str = ""
    quantity: float = 1.0
    unit_price: float = 0.0
    amount: float = 0.0
    evidence: Optional[FieldEvidence] = None


class InvoiceExtraction(BaseModel):
    """Schema for invoice extraction."""

    vendor: FieldEvidence = Field(default_factory=FieldEvidence)
    vendor_address: FieldEvidence = Field(default_factory=FieldEvidence)
    customer_name: FieldEvidence = Field(default_factory=FieldEvidence)
    customer_address: FieldEvidence = Field(default_factory=FieldEvidence)
    invoice_number: FieldEvidence = Field(default_factory=FieldEvidence)
    invoice_date: FieldEvidence = Field(default_factory=FieldEvidence)
    due_date: FieldEvidence = Field(default_factory=FieldEvidence)
    currency: FieldEvidence = Field(default_factory=FieldEvidence)
    line_items: List[InvoiceLineItem] = Field(default_factory=list)
    subtotal: FieldEvidence = Field(default_factory=FieldEvidence)
    tax: FieldEvidence = Field(default_factory=FieldEvidence)
    total: FieldEvidence = Field(default_factory=FieldEvidence)
    payment_terms: FieldEvidence = Field(default_factory=FieldEvidence)


class DeadlineItem(BaseModel):
    """Single contractual deadline or notice obligation with verbatim quote verification."""

    description: str = ""
    date: str = ""
    quote: str = Field(default="", max_length=250)
    page: int = Field(default=1)
    verified: bool = Field(default=False)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class ContractExtraction(BaseModel):
    """Schema for contract / agreement extraction."""

    parties: List[FieldEvidence] = Field(default_factory=list)
    effective_date: FieldEvidence = Field(default_factory=FieldEvidence)
    term: FieldEvidence = Field(default_factory=FieldEvidence)
    renewal: FieldEvidence = Field(default_factory=FieldEvidence)
    termination_clause: FieldEvidence = Field(default_factory=FieldEvidence)
    governing_law: FieldEvidence = Field(default_factory=FieldEvidence)
    payment_terms: FieldEvidence = Field(default_factory=FieldEvidence)
    liability_cap: FieldEvidence = Field(default_factory=FieldEvidence)
    confidentiality: FieldEvidence = Field(default_factory=FieldEvidence)
    deadlines: List[DeadlineItem] = Field(default_factory=list)
    signatures: List[FieldEvidence] = Field(default_factory=list)


class ResearchPaperExtraction(BaseModel):
    """Schema for academic research paper extraction."""

    title: FieldEvidence = Field(default_factory=FieldEvidence)
    authors: List[FieldEvidence] = Field(default_factory=list)
    venue: FieldEvidence = Field(default_factory=FieldEvidence)
    year: FieldEvidence = Field(default_factory=FieldEvidence)
    abstract: FieldEvidence = Field(default_factory=FieldEvidence)
    key_findings: List[FieldEvidence] = Field(default_factory=list)
    datasets: List[FieldEvidence] = Field(default_factory=list)
    limitations: List[FieldEvidence] = Field(default_factory=list)


class ResumeExtraction(BaseModel):
    """Schema for professional resume / CV extraction."""

    candidate_name: FieldEvidence = Field(default_factory=FieldEvidence)
    email: FieldEvidence = Field(default_factory=FieldEvidence)
    phone: FieldEvidence = Field(default_factory=FieldEvidence)
    current_role: FieldEvidence = Field(default_factory=FieldEvidence)
    experience_years: FieldEvidence = Field(default_factory=FieldEvidence)
    skills: List[FieldEvidence] = Field(default_factory=list)
    education: List[FieldEvidence] = Field(default_factory=list)
