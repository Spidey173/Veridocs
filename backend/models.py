from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class SourceInfo(BaseModel):
    page: int
    snippet: str
    source_file: str = "Uploaded PDF"
    relevance_score: Optional[float] = None
    chunk_type: Optional[str] = "text"
    extraction_method: Optional[str] = "text_layer"
    section_path: Optional[str] = None


class CitationInfo(BaseModel):
    citation_id: int
    page: int
    source_file: str
    highlighted_text: str
    chunk_type: Optional[str] = "text"
    extraction_method: Optional[str] = "text_layer"
    ocr_confidence: Optional[float] = None
    section_path: Optional[str] = None


class ClaimCheckDetail(BaseModel):
    claim: str
    overlap_score: float
    is_supported: bool
    matched_page: Optional[int] = None
    source_file: Optional[str] = None
    section_path: Optional[str] = None
    is_low_confidence_ocr: bool = False


class CitationCheckResult(BaseModel):
    citation_score: float = Field(default=0.0, description="Fraction of answer claims supported by retrieved context")
    total_claims: int = 0
    supported_claims: int = 0
    claims: List[ClaimCheckDetail] = []
    has_low_confidence_ocr_warning: bool = False


class QueryRequest(BaseModel):
    session_id: str
    question: str
    history: Optional[List[Dict[str, str]]] = None
    active_files: Optional[List[str]] = None


class StreamQueryRequest(BaseModel):
    session_id: str
    question: str
    history: Optional[List[Dict[str, str]]] = None
    active_files: Optional[List[str]] = None


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceInfo]
    citations: List[CitationInfo] = []
    citation_check: Optional[CitationCheckResult] = None
    retrieval_strategy: Optional[str] = "hybrid"


class UploadResponse(BaseModel):
    session_id: str
    chunk_count: int
    processed_files: int
    failed_files: List[str]
    message: str
    suggested_questions: List[str] = []
    document_metadata: Optional[List[Dict[str, Any]]] = None


class AsyncUploadResponse(BaseModel):
    document_id: str
    session_id: str
    filename: str
    status: str = "queued"
    message: str


class DocumentStatusResponse(BaseModel):
    document_id: str
    session_id: Optional[str] = None
    filename: str
    status: str
    page_count: Optional[int] = 0
    doc_type: Optional[str] = None
    error: Optional[str] = None
    created_at: Optional[float] = None
    updated_at: Optional[float] = None


class TableResponse(BaseModel):
    id: str
    document_id: str
    page_number: int
    markdown: str
    json_data: Dict[str, Any] = Field(default_factory=dict, alias="json")
    bbox: Optional[Dict[str, Any]] = None


class SessionInfo(BaseModel):
    session_id: str
    created_at: float
    file_names: List[str]
    chunk_count: int
    suggested_questions: List[str] = []


class HealthResponse(BaseModel):
    status: str
    version: str
    llm_configured: bool
    active_sessions: int
    embedding_model_loaded: bool


class SummaryRequest(BaseModel):
    force: bool = False


class StructuredSummaryPayload(BaseModel):
    main_purpose: str = ""
    important_points: List[str] = Field(default_factory=list)
    key_information: List[str] = Field(default_factory=list)
    conclusion: str = ""


class DocumentSummaryResponse(BaseModel):
    document_id: str
    filename: Optional[str] = None
    status: str
    summary: Optional[StructuredSummaryPayload] = None
    verification: Optional[Dict[str, Any]] = None
    grounding_score: Optional[float] = None
    error: Optional[str] = None
    created_at: Optional[float] = None
    updated_at: Optional[float] = None


class ReportCitation(BaseModel):
    chunk_id: Optional[str] = None
    page: int = 1
    section_path: Optional[str] = None
    quote: str = ""


class ReportFinding(BaseModel):
    title: str
    detail: str
    severity: Optional[str] = None
    category: Optional[str] = None
    citations: List[ReportCitation] = Field(default_factory=list)


class DocumentReportResponse(BaseModel):
    document_id: str
    filename: Optional[str] = None
    executive_summary: str = ""
    important_findings: List[ReportFinding] = Field(default_factory=list)
    risks: List[ReportFinding] = Field(default_factory=list)
    recommendations: List[ReportFinding] = Field(default_factory=list)
    generated_at: Optional[float] = None


class DailyAnalyticsBucket(BaseModel):
    date: str
    documents_uploaded: int = 0
    documents_analyzed: int = 0
    questions_asked: int = 0
    flags_found: int = 0
    avg_verification_score: Optional[float] = None


class AnalyticsResponse(BaseModel):
    documents_uploaded: int = 0
    documents_analyzed: int = 0
    questions_asked: int = 0
    flags_found: int = 0
    avg_verification_score: Optional[float] = None
    by_day: List[DailyAnalyticsBucket] = Field(default_factory=list)


class CrossDocSearchRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    scope: str = "library"
    top_k: int = Field(default=12, ge=1, le=50)


class SearchChunkMatch(BaseModel):
    chunk_id: Optional[str] = None
    content: str
    page: int = 1
    section_path: Optional[str] = None
    chunk_type: str = "text"
    score: float = 0.0


class SearchDocumentGroup(BaseModel):
    document_id: Optional[str] = None
    filename: str
    session_id: Optional[str] = None
    max_score: float = 0.0
    matches: List[SearchChunkMatch] = Field(default_factory=list)


class CrossDocSearchResponse(BaseModel):
    query: str
    scope: str
    total_matches: int = 0
    documents: List[SearchDocumentGroup] = Field(default_factory=list)
