"""
Unit tests for models.py Pydantic schemas and enums.
"""

import pytest
from datetime import datetime
from pydantic import ValidationError

from models import (
    MessageRole,
    StreamEventType,
    ProcessingStage,
    SourceInfo,
    CitationInfo,
    QueryRequest,
    StreamQueryRequest,
    QueryResponse,
    StreamEvent,
    UploadProgress,
    UploadResponse,
    ConversationMessage,
    ConversationHistory,
    EntityInfo,
    ExecutiveSummary,
    DocumentInsights,
)


class TestModels:
    def test_enums(self):
        """Verify enum string representations."""
        assert MessageRole.USER == "user"
        assert MessageRole.ASSISTANT == "assistant"
        assert MessageRole.SYSTEM == "system"

        assert StreamEventType.TOKEN == "token"
        assert StreamEventType.CITATION == "citation"
        assert StreamEventType.CONFIDENCE == "confidence"
        assert StreamEventType.DONE == "done"

        assert ProcessingStage.UPLOADING == "uploading"
        assert ProcessingStage.COMPLETE == "complete"

    def test_source_info_defaults(self):
        """Verify SourceInfo default values and optional attributes."""
        source = SourceInfo(page=1, snippet="Test snippet")
        assert source.page == 1
        assert source.snippet == "Test snippet"
        assert source.source_file == "Uploaded PDF"
        assert source.section is None
        assert source.relevance_score is None

        # Custom values
        source_custom = SourceInfo(
            page=3,
            snippet="Custom snippet",
            source_file="custom.pdf",
            section="Summary",
            relevance_score=0.95
        )
        assert source_custom.page == 3
        assert source_custom.source_file == "custom.pdf"
        assert source_custom.relevance_score == 0.95

    def test_citation_info(self):
        """Verify CitationInfo initialization and field mapping."""
        citation = CitationInfo(
            citation_id=1,
            page=2,
            source_file="report.pdf",
            highlighted_text="Revenue grew 20%",
            section="Financials",
            confidence=0.88
        )
        assert citation.citation_id == 1
        assert citation.page == 2
        assert citation.highlighted_text == "Revenue grew 20%"
        assert citation.confidence == 0.88

    def test_query_request_validation(self):
        """Verify QueryRequest validation and defaults."""
        req = QueryRequest(session_id="sess-123", question="What is X?")
        assert req.session_id == "sess-123"
        assert req.question == "What is X?"
        assert req.history is None
        assert req.active_files is None

        # Multi-turn history and active files
        req_full = QueryRequest(
            session_id="sess-123",
            question="What about Y?",
            history=[{"role": "user", "content": "What is X?"}],
            active_files=["doc1.pdf"]
        )
        assert len(req_full.history) == 1
        assert req_full.active_files == ["doc1.pdf"]

        # Missing required fields
        with pytest.raises(ValidationError):
            QueryRequest(question="Missing session_id")

        with pytest.raises(ValidationError):
            QueryRequest(session_id="sess-123")

    def test_stream_query_request(self):
        """Verify StreamQueryRequest model."""
        req = StreamQueryRequest(session_id="sess-456", question="Summarize page 2")
        assert req.session_id == "sess-456"
        assert req.question == "Summarize page 2"

    def test_query_response(self):
        """Verify QueryResponse serialization."""
        source = SourceInfo(page=1, snippet="Content")
        citation = CitationInfo(citation_id=1, page=1, source_file="doc.pdf", highlighted_text="Content")
        resp = QueryResponse(
            answer="This is the answer.",
            sources=[source],
            citations=[citation],
            confidence_score=0.92,
            suggested_followups=["Why?", "How?"]
        )
        assert resp.answer == "This is the answer."
        assert len(resp.sources) == 1
        assert len(resp.citations) == 1
        assert resp.confidence_score == 0.92
        assert len(resp.suggested_followups) == 2

    def test_stream_event(self):
        """Verify StreamEvent packaging."""
        event = StreamEvent(
            event=StreamEventType.TOKEN,
            data={"text": "hello"}
        )
        assert event.event == StreamEventType.TOKEN
        assert event.data["text"] == "hello"

    def test_upload_response(self):
        """Verify UploadResponse model."""
        resp = UploadResponse(
            session_id="uuid-1",
            chunk_count=10,
            processed_files=2,
            failed_files=[],
            message="Upload successful",
            document_metadata=[{"filename": "doc.pdf", "num_pages": 5}]
        )
        assert resp.session_id == "uuid-1"
        assert resp.chunk_count == 10
        assert resp.processed_files == 2
        assert len(resp.document_metadata) == 1

    def test_conversation_message_and_history(self):
        """Verify ConversationMessage and ConversationHistory."""
        msg = ConversationMessage(
            role=MessageRole.USER,
            content="Hello there"
        )
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello there"
        assert isinstance(msg.timestamp, datetime)

        history = ConversationHistory(
            session_id="sess-hist",
            messages=[msg],
            document_name="test.pdf"
        )
        assert history.session_id == "sess-hist"
        assert len(history.messages) == 1
        assert history.document_name == "test.pdf"

    def test_entity_and_insights_models(self):
        """Verify EntityInfo, ExecutiveSummary, and DocumentInsights."""
        entity = EntityInfo(
            entity_type="MONEY",
            value="$1,000,000",
            page=1,
            count=3
        )
        assert entity.entity_type == "MONEY"
        assert entity.count == 3

        summary = ExecutiveSummary(
            purpose="Financial review",
            key_findings=["Revenue up 10%"],
            risks=["Market volatility"],
            conclusions=["Buy signal"]
        )
        assert summary.purpose == "Financial review"
        assert len(summary.key_findings) == 1

        insights = DocumentInsights(
            session_id="sess-insights",
            executive_summary=summary,
            suggested_questions=["What is revenue?"]
        )
        assert insights.session_id == "sess-insights"
        assert insights.executive_summary.purpose == "Financial review"
        assert len(insights.suggested_questions) == 1
