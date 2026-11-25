"""
SQLAlchemy 2.x declarative models for Veridocs.
Includes Document, Page, Chunk, Table, Session, and Message entities.
Supports pgvector vector(384) on PostgreSQL with SQLite fallback.
"""

import time
import uuid
from typing import Dict, Any
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Boolean,
    Text,
    ForeignKey,
    Index,
    JSON,
    LargeBinary,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# Attempt to load pgvector's SQLAlchemy Vector type
try:
    from pgvector.sqlalchemy import Vector

    HAS_PGVECTOR = True
except ImportError:
    Vector = None
    HAS_PGVECTOR = False


def generate_uuid() -> str:
    return str(uuid.uuid4())


class Document(Base):
    """Uploaded or ingested document metadata."""

    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(64), nullable=True, index=True)
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False, default="application/pdf")
    status = Column(
        String(50), nullable=False, default="queued", index=True
    )  # queued, parsing, ocr, chunking, embedding, ready, failed
    page_count = Column(Integer, default=0)
    doc_type = Column(String(50), nullable=True)  # invoice, contract, research_paper, resume, other
    doc_type_confidence = Column(Float, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)

    # Relationships
    pages = relationship("Page", back_populates="document", cascade="all, delete-orphan", order_by="Page.page_number")
    chunks = relationship(
        "Chunk", back_populates="document", cascade="all, delete-orphan", order_by="Chunk.chunk_index"
    )
    tables = relationship(
        "Table", back_populates="document", cascade="all, delete-orphan", order_by="Table.page_number"
    )
    vision_pages = relationship(
        "PageVision", back_populates="document", cascade="all, delete-orphan", order_by="PageVision.page_number"
    )
    entities = relationship("Entity", back_populates="document", cascade="all, delete-orphan")
    extractions = relationship("Extraction", back_populates="document", cascade="all, delete-orphan")
    clauses = relationship(
        "Clause", back_populates="document", cascade="all, delete-orphan", order_by="Clause.clause_index"
    )
    flags = relationship("Flag", back_populates="document", cascade="all, delete-orphan")
    summary = relationship("DocumentSummary", back_populates="document", uselist=False, cascade="all, delete-orphan")
    report = relationship("DocumentReport", back_populates="document", uselist=False, cascade="all, delete-orphan")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "filename": self.filename,
            "mime_type": self.mime_type,
            "status": self.status,
            "page_count": self.page_count,
            "doc_type": self.doc_type,
            "doc_type_confidence": self.doc_type_confidence,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class Page(Base):
    """Per-page extracted text, OCR metadata, and structural flags."""

    __tablename__ = "pages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    text = Column(Text, nullable=False, default="")
    extraction_method = Column(String(50), nullable=False, default="text_layer")  # text_layer | ocr
    ocr_confidence = Column(Float, nullable=True)
    has_figures = Column(Boolean, default=False)
    has_tables = Column(Boolean, default=False)
    has_signature_block = Column(Boolean, default=False)

    document = relationship("Document", back_populates="pages")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "page_number": self.page_number,
            "text": self.text,
            "extraction_method": self.extraction_method,
            "ocr_confidence": self.ocr_confidence,
            "has_figures": self.has_figures,
            "has_tables": self.has_tables,
            "has_signature_block": self.has_signature_block,
        }


class Chunk(Base):
    """Passage or table chunk with vector embedding and metadata."""

    __tablename__ = "chunks"
    __table_args__ = (Index("ix_chunks_session_filename", "session_id", "filename"),)

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    session_id = Column(String(64), nullable=True, index=True)
    filename = Column(String(255), nullable=False, default="document", index=True)
    page_number = Column(Integer, nullable=False, default=1)
    chunk_index = Column(Integer, nullable=False, default=0)
    content = Column(Text, nullable=False)
    chunk_type = Column(String(50), nullable=False, default="text")  # text | table
    section_path = Column(String(512), nullable=True)

    # Vector column: pgvector Vector(384) on Postgres; fallback to LargeBinary/Text for SQLite
    if HAS_PGVECTOR and Vector is not None:
        embedding = Column(Vector(384), nullable=True)
    else:
        embedding = Column(LargeBinary, nullable=True)

    metadata_json = Column("metadata", JSON, nullable=True)

    document = relationship("Document", back_populates="chunks")

    def to_dict(self) -> Dict[str, Any]:
        meta = self.metadata_json or {}
        return {
            "id": self.id,
            "document_id": self.document_id,
            "session_id": self.session_id,
            "source_file": self.filename,
            "filename": self.filename,
            "page": self.page_number,
            "page_number": self.page_number,
            "chunk_index": self.chunk_index,
            "text": self.content,
            "content": self.content,
            "chunk_type": self.chunk_type,
            "section_path": self.section_path or meta.get("section_path"),
            "metadata": meta,
        }


class Table(Base):
    """Extracted table representation in Markdown and structured JSON."""

    __tablename__ = "tables"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False, default=1)
    markdown = Column(Text, nullable=False)
    table_json = Column("json", JSON, nullable=False)
    bbox = Column(JSON, nullable=True)

    document = relationship("Document", back_populates="tables")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "page_number": self.page_number,
            "markdown": self.markdown,
            "json": self.table_json,
            "bbox": self.bbox,
        }


class SessionModel(Base):
    """Conversational workspace session matching current system."""

    __tablename__ = "sessions"

    session_id = Column(String(64), primary_key=True)
    created_at = Column(Float, default=time.time)
    file_names = Column(JSON, default=list)
    suggested_questions = Column(JSON, default=list)


class MessageModel(Base):
    """Persistent chat messages and verified citation logs."""

    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(64), ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    citations = Column(JSON, nullable=True)
    sources = Column(JSON, nullable=True)
    citation_check = Column(JSON, nullable=True)
    timestamp = Column(String(50), nullable=True)


class PageVision(Base):
    """Multimodal vision analysis results per page."""

    __tablename__ = "page_vision"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False)
    image_hash = Column(String(64), nullable=True, index=True)
    json_data = Column(JSON, nullable=False)  # figures, signatures, layout_notes
    model = Column(String(100), nullable=False)
    cost_tokens = Column(Integer, default=0)
    created_at = Column(Float, default=time.time)

    document = relationship("Document", back_populates="vision_pages")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "page_number": self.page_number,
            "image_hash": self.image_hash,
            "figures": self.json_data.get("figures", []),
            "signatures": self.json_data.get("signatures", []),
            "layout_notes": self.json_data.get("layout_notes", ""),
            "model": self.model,
            "cost_tokens": self.cost_tokens,
            "created_at": self.created_at,
        }


class Entity(Base):
    """Extracted named entity with offsets and normalization."""

    __tablename__ = "entities"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    page_number = Column(Integer, nullable=False, default=1)
    chunk_id = Column(String(64), nullable=True, index=True)
    label = Column(String(50), nullable=False, index=True)  # person, organization, date, money, location, etc.
    text = Column(Text, nullable=False)
    normalized = Column(JSON, nullable=True)  # ISO 8601 string or {amount: float, currency: str}
    start_offset = Column(Integer, nullable=True)
    end_offset = Column(Integer, nullable=True)
    score = Column(Float, default=1.0)
    created_at = Column(Float, default=time.time)

    document = relationship("Document", back_populates="entities")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "page_number": self.page_number,
            "chunk_id": self.chunk_id,
            "label": self.label,
            "text": self.text,
            "normalized": self.normalized,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "score": self.score,
            "created_at": self.created_at,
        }


class Extraction(Base):
    """Schema-based structured document extraction with evidence verification."""

    __tablename__ = "extractions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    schema_type = Column(String(50), nullable=False)  # invoice, contract, research_paper, resume, other
    json_data = Column(JSON, nullable=False)  # structured fields with value, page, quote, confidence, verified
    verified_ratio = Column(Float, default=0.0)
    user_edits = Column(JSON, nullable=True)  # Separate storage for user manual overrides
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)

    document = relationship("Document", back_populates="extractions")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "schema_type": self.schema_type,
            "fields": self.json_data,
            "verified_ratio": self.verified_ratio,
            "user_edits": self.user_edits or {},
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class Clause(Base):
    """Segmented contract clause with numbering, heading, text, and vector embedding."""

    __tablename__ = "clauses"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    clause_index = Column(Integer, nullable=False, default=0)
    number = Column(String(50), nullable=True)
    heading = Column(String(255), nullable=True)
    text = Column(Text, nullable=False)
    page_start = Column(Integer, nullable=False, default=1)
    page_end = Column(Integer, nullable=False, default=1)

    if HAS_PGVECTOR and Vector is not None:
        embedding = Column(Vector(384), nullable=True)
    else:
        embedding = Column(LargeBinary, nullable=True)

    created_at = Column(Float, default=time.time)

    document = relationship("Document", back_populates="clauses")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "clause_index": self.clause_index,
            "number": self.number,
            "heading": self.heading,
            "text": self.text,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "created_at": self.created_at,
        }


class Comparison(Base):
    """Pairwise contract comparison record with aligned clauses, redlines, and risk summaries."""

    __tablename__ = "comparisons"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    doc_a = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    doc_b = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(50), nullable=False, default="queued")  # queued, processing, ready, failed
    json_data = Column("json", JSON, nullable=True)  # { aligned_clauses: [...], diff_summary: {...} }
    error = Column(Text, nullable=True)
    created_at = Column(Float, default=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "doc_a": self.doc_a,
            "doc_b": self.doc_b,
            "status": self.status,
            "data": self.json_data or {},
            "error": self.error,
            "created_at": self.created_at,
        }


class Flag(Base):
    """Rule-based anomaly indicator (heuristics for human review, not automated accusations)."""

    __tablename__ = "flags"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    rule_id = Column(String(100), nullable=False, index=True)
    severity = Column(String(20), nullable=False)  # low | medium | high
    message = Column(Text, nullable=False)
    evidence = Column(JSON, nullable=True)  # [{ page: int, quote: str, details: str }]
    confidence = Column(Float, default=1.0)
    created_at = Column(Float, default=time.time)

    document = relationship("Document", back_populates="flags")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "message": self.message,
            "evidence": self.evidence or [],
            "confidence": self.confidence,
            "created_at": self.created_at,
        }


class GraphNode(Base):
    """Knowledge graph node representing an entity, document, or clause."""

    __tablename__ = "graph_nodes"

    id = Column(String(128), primary_key=True)  # Canonical ID, e.g. "org:acme_corp"
    label = Column(
        String(50), nullable=False, index=True
    )  # Party, Organization, Person, Date, MoneyAmount, Clause, Document
    name = Column(String(255), nullable=False)
    canonical_name = Column(String(255), nullable=False, index=True)
    aliases = Column(JSON, nullable=True)  # List of alias variations
    properties = Column(JSON, nullable=True)
    document_ids = Column(JSON, nullable=True)  # List of documents where this node occurs
    created_at = Column(Float, default=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "name": self.name,
            "canonical_name": self.canonical_name,
            "aliases": self.aliases or [],
            "properties": self.properties or {},
            "document_ids": self.document_ids or [],
            "created_at": self.created_at,
        }


class GraphEdge(Base):
    """Knowledge graph directed edge with verified source quote and page citation."""

    __tablename__ = "graph_edges"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    source_id = Column(String(128), ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    target_id = Column(String(128), ForeignKey("graph_nodes.id", ondelete="CASCADE"), nullable=False, index=True)
    relation = Column(
        String(50), nullable=False, index=True
    )  # PARTY_TO, PAYS, OWES, SIGNED_BY, EFFECTIVE_ON, REFERENCES, AMENDS, MENTIONED_IN
    document_id = Column(String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=True, index=True)
    page_number = Column(Integer, nullable=True)
    quote = Column(Text, nullable=True)
    verified = Column(Boolean, default=True)
    properties = Column(JSON, nullable=True)
    created_at = Column(Float, default=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relation": self.relation,
            "document_id": self.document_id,
            "page_number": self.page_number,
            "quote": self.quote,
            "verified": self.verified,
            "properties": self.properties or {},
            "created_at": self.created_at,
        }


class DocumentSummary(Base):
    """Cached map-reduce structured summary with NLI grounding scores."""

    __tablename__ = "document_summaries"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    status = Column(String(50), nullable=False, default="queued")  # queued | processing | ready | failed
    summary_json = Column("summary", JSON, nullable=True)
    verification_json = Column("verification", JSON, nullable=True)
    grounding_score = Column(Float, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)

    document = relationship("Document", back_populates="summary")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "document_id": self.document_id,
            "status": self.status,
            "summary": self.summary_json,
            "verification": self.verification_json,
            "grounding_score": self.grounding_score,
            "error": self.error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class DocumentReport(Base):
    """Cached structured document intelligence report (findings, risks, recommendations)."""

    __tablename__ = "document_reports"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    document_id = Column(
        String(36), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    report_json = Column("report", JSON, nullable=False)
    created_at = Column(Float, default=time.time)
    updated_at = Column(Float, default=time.time, onupdate=time.time)

    document = relationship("Document", back_populates="report")

    def to_dict(self) -> Dict[str, Any]:
        data = dict(self.report_json or {})
        data["document_id"] = self.document_id
        data["generated_at"] = self.updated_at or self.created_at
        return data


class QueryLog(Base):
    """Logged QA queries and verification scores for analytics."""

    __tablename__ = "query_log"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    session_id = Column(String(64), nullable=True, index=True)
    question = Column(Text, nullable=False)
    retrieval_strategy = Column(String(50), nullable=True)
    citation_score = Column(Float, nullable=True)
    total_claims = Column(Integer, default=0)
    supported_claims = Column(Integer, default=0)
    created_at = Column(Float, default=time.time, index=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "question": self.question,
            "retrieval_strategy": self.retrieval_strategy,
            "citation_score": self.citation_score,
            "total_claims": self.total_claims,
            "supported_claims": self.supported_claims,
            "created_at": self.created_at,
        }
