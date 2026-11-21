from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class SourceInfo(BaseModel):
    page: int
    snippet: str
    source_file: str = "Uploaded PDF"
    relevance_score: Optional[float] = None


class CitationInfo(BaseModel):
    citation_id: int
    page: int
    source_file: str
    highlighted_text: str


class ClaimCheckDetail(BaseModel):
    claim: str
    overlap_score: float
    is_supported: bool
    matched_page: Optional[int] = None
    source_file: Optional[str] = None


class CitationCheckResult(BaseModel):
    citation_score: float = Field(default=0.0, description="Fraction of answer claims supported by retrieved context")
    total_claims: int = 0
    supported_claims: int = 0
    claims: List[ClaimCheckDetail] = []


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


class UploadResponse(BaseModel):
    session_id: str
    chunk_count: int
    processed_files: int
    failed_files: List[str]
    message: str
    suggested_questions: List[str] = []
    document_metadata: Optional[List[Dict[str, Any]]] = None


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
