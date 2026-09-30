"""
Extended Pydantic models for the DocuMind AI platform.
Covers requests, responses, streaming events, and domain entities.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum
from datetime import datetime


# === Enums ===

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class StreamEventType(str, Enum):
    TOKEN = "token"
    CITATION = "citation"
    CONFIDENCE = "confidence"
    VERIFICATION = "verification"
    SUGGESTED_QUESTIONS = "suggested_questions"
    ERROR = "error"
    DONE = "done"


class ProcessingStage(str, Enum):
    UPLOADING = "uploading"
    EXTRACTING = "extracting"
    CHUNKING = "chunking"
    EMBEDDING = "embedding"
    ANALYZING = "analyzing"
    COMPLETE = "complete"
    ERROR = "error"


# === Source & Citation Models ===

class SourceInfo(BaseModel):
    page: int
    snippet: str
    source_file: Optional[str] = "Uploaded PDF"
    section: Optional[str] = None
    relevance_score: Optional[float] = None


class CitationInfo(BaseModel):
    """Structured citation with page location and highlighted text."""
    citation_id: int
    page: int
    source_file: str
    highlighted_text: str
    section: Optional[str] = None
    confidence: Optional[float] = None


# === Request Models ===

class QueryRequest(BaseModel):
    session_id: str
    question: str
    history: Optional[List[Dict[str, str]]] = None  # Multi-turn conversation
    active_files: Optional[List[str]] = None


class StreamQueryRequest(BaseModel):
    session_id: str
    question: str
    history: Optional[List[Dict[str, str]]] = None
    active_files: Optional[List[str]] = None


# === Response Models ===

class ClaimStatus(str, Enum):
    VERIFIED = "verified"
    INFERRED = "inferred"
    HALLUCINATED = "hallucinated"


class ClaimVerification(BaseModel):
    claim: str
    score: float
    status: str = "verified"
    is_supported: bool = True
    numeric_grounded: bool = True
    best_source_page: Optional[int] = None
    source_file: Optional[str] = None


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceInfo]
    citations: Optional[List[CitationInfo]] = None
    confidence_score: Optional[float] = None
    suggested_followups: Optional[List[str]] = None
    claim_verifications: Optional[List[ClaimVerification]] = None


class StreamEvent(BaseModel):
    """Server-Sent Event payload for streaming responses."""
    event: StreamEventType
    data: Dict[str, Any]


# === Upload Models ===

class UploadProgress(BaseModel):
    stage: ProcessingStage
    progress: float = 0.0  # 0.0 to 1.0
    message: str = ""
    file_name: Optional[str] = None
    pages_processed: Optional[int] = None
    total_pages: Optional[int] = None
    chunks_created: Optional[int] = None


class UploadResponse(BaseModel):
    session_id: str
    chunk_count: int
    processed_files: int
    failed_files: List[str]
    message: str
    document_metadata: Optional[List[Dict[str, Any]]] = None


# === Conversation Models ===

class ConversationMessage(BaseModel):
    id: Optional[str] = None
    role: MessageRole
    content: str
    citations: Optional[List[CitationInfo]] = None
    confidence_score: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ConversationHistory(BaseModel):
    session_id: str
    messages: List[ConversationMessage]
    document_name: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


# === Insights Models ===

class EntityInfo(BaseModel):
    """Extracted named entity from documents."""
    entity_type: str  # PERSON, ORG, DATE, MONEY, LOCATION
    value: str
    page: Optional[int] = None
    count: int = 1


class ExecutiveSummary(BaseModel):
    purpose: str
    key_findings: List[str]
    risks: Optional[List[str]] = None
    conclusions: List[str]


class DocumentInsights(BaseModel):
    session_id: str
    executive_summary: Optional[ExecutiveSummary] = None
    suggested_questions: List[str] = []
    key_entities: List[EntityInfo] = []
    total_pages: int = 0
    total_chunks: int = 0
    processing_time_ms: Optional[float] = None


# === Document Metadata ===

class DocumentMetadata(BaseModel):
    filename: str
    num_pages: int
    file_size_bytes: int
    is_scanned: bool = False
    sections: Optional[List[str]] = None
    upload_timestamp: datetime = Field(default_factory=datetime.utcnow)


# === Health Check ===

class HealthResponse(BaseModel):
    status: str
    version: str
    active_sessions: int
    models_loaded: Dict[str, bool]
    providers_available: Dict[str, bool]