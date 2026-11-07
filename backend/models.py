from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from enum import Enum
from datetime import datetime


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class StreamEventType(str, Enum):
    TOKEN = "token"
    CITATION = "citation"
    CONFIDENCE = "confidence"
    VERIFICATION = "verification"
    AUDIT_METRICS = "audit_metrics"
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


class SourceInfo(BaseModel):
    page: int
    snippet: str
    source_file: Optional[str] = "Uploaded PDF"
    section: Optional[str] = None
    relevance_score: Optional[float] = None
    bm25_score: Optional[float] = None
    dense_score: Optional[float] = None
    rerank_score: Optional[float] = None


class DocumentChunk(BaseModel):
    """Strongly typed document chunk model with vector & sparse retrieval telemetry."""
    id: Optional[Union[str, int]] = None
    session_id: Optional[str] = None
    source_file: str = "Uploaded PDF"
    page: int = Field(default=1, alias="page_number")
    chunk_index: int = 0
    text: str
    raw_text: Optional[str] = None
    section: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    relevance_score: Optional[float] = None
    dense_score: Optional[float] = None
    sparse_score: Optional[float] = None
    bm25_score: Optional[float] = None
    rerank_score: Optional[float] = None
    is_table: bool = False
    is_scanned: bool = False
    ocr_engine: Optional[str] = None

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
        "extra": "allow"
    }

    def to_dict(self) -> Dict[str, Any]:
        """Convert chunk model to standard dictionary format for legacy consumers."""
        d = self.model_dump(by_alias=False)
        d["page_number"] = self.page
        return d


class CitationInfo(BaseModel):
    citation_id: int
    page: int
    source_file: str
    highlighted_text: str
    section: Optional[str] = None
    confidence: Optional[float] = None


class QueryRequest(BaseModel):
    session_id: str
    question: str
    history: Optional[List[Dict[str, str]]] = None
    active_files: Optional[List[str]] = None
    provider: Optional[str] = Field(default=None, description="LLM provider: 'openai', 'groq', 'deepseek', 'google', 'ollama', 'anthropic', 'mistral', 'openrouter', 'github', 'custom'")
    model: Optional[str] = Field(default=None, description="Model identifier override")
    api_key: Optional[str] = Field(default=None, description="Optional per-request API key")
    base_url: Optional[str] = Field(default=None, description="Optional custom base URL for Ollama / vLLM")


class StreamQueryRequest(BaseModel):
    session_id: str
    question: str
    history: Optional[List[Dict[str, str]]] = None
    active_files: Optional[List[str]] = None
    provider: Optional[str] = Field(default=None, description="LLM provider: 'openai', 'groq', 'deepseek', 'google', 'ollama', 'anthropic', 'mistral', 'openrouter', 'github', 'custom'")
    model: Optional[str] = Field(default=None, description="Model identifier override")
    api_key: Optional[str] = Field(default=None, description="Optional per-request API key")
    base_url: Optional[str] = Field(default=None, description="Optional custom base URL for Ollama / vLLM")


class CrossDocAuditRequest(BaseModel):
    session_id: str
    doc_a: str
    doc_b: str
    focus_topic: Optional[str] = "all"


class ClaimVerification(BaseModel):
    claim: str
    score: float
    status: str = "verified"
    is_supported: bool = True
    numeric_grounded: bool = True
    best_source_page: Optional[int] = None
    source_file: Optional[str] = None


class RagTriadMetrics(BaseModel):
    context_relevance: float = Field(default=0.0, description="Fraction of retrieved chunks relevant to query")
    groundedness: float = Field(default=0.0, description="Agreement between answer and sources")
    answer_relevance: float = Field(default=0.0, description="How well the answer addresses the question")
    numeric_accuracy: float = Field(default=1.0, description="Accuracy of numbers and dates")
    latency_ms: Optional[float] = None
    retrieval_pipeline: Optional[str] = "Hybrid Full-Text + pgvector HNSW"


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceInfo]
    citations: Optional[List[CitationInfo]] = None
    confidence_score: Optional[float] = None
    rag_triad: Optional[RagTriadMetrics] = None
    suggested_followups: Optional[List[str]] = None
    claim_verifications: Optional[List[ClaimVerification]] = None


class StreamEvent(BaseModel):
    event: StreamEventType
    data: Dict[str, Any]


class UploadResponse(BaseModel):
    session_id: str
    chunk_count: int
    processed_files: int
    failed_files: List[str]
    message: str
    document_metadata: Optional[List[Dict[str, Any]]] = None


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


class EntityInfo(BaseModel):
    entity_type: str
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


class HealthResponse(BaseModel):
    status: str
    version: str
    active_sessions: int
    models_loaded: Dict[str, bool]
    providers_available: Dict[str, bool]
    database_connected: Optional[bool] = None


class JobStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobProgress(BaseModel):
    current_page: int = 0
    total_pages: int = 0
    percent: float = 0.0
    stage: str = "queued"
    scanned_pages: int = 0
    chunks_created: int = 0

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]] = None) -> "JobProgress":
        if not data or not isinstance(data, dict):
            return cls()
        return cls(
            current_page=data.get("current_page", 0),
            total_pages=data.get("total_pages", 0),
            percent=data.get("percent", 0.0),
            stage=data.get("stage", ""),
            scanned_pages=data.get("scanned_pages", 0),
            chunks_created=data.get("chunks_created", 0),
        )


class JobResponse(BaseModel):
    job_id: str
    status: JobStatus
    created_at: float
    file_names: List[str]
    message: str = "Document queued for processing"


class JobDetailResponse(BaseModel):
    job_id: str
    status: JobStatus
    owner_id: str
    created_at: float
    updated_at: float
    file_names: List[str]
    progress: JobProgress
    session_id: Optional[str] = None
    error: Optional[str] = None
    result_summary: Optional[Dict[str, Any]] = None


class JobListResponse(BaseModel):
    jobs: List[JobDetailResponse]
    total: int
