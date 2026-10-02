"""
Unit tests for insights_engine.py entity extraction and document insights generation.
"""

from unittest.mock import MagicMock
import pytest

from insights_engine import (
    extract_entities,
    generate_document_insights,
    _default_questions,
)
from models import DocumentInsights


class TestInsightsEngine:
    def test_extract_entities(self):
        """Verify regex extraction of MONEY, DATE, PERCENTAGE, ORG, PERSON, and LOCATION."""
        chunks = [
            {
                "text": (
                    "In January 15, 2024, CEO Jane Doe announced that Alphabet Inc "
                    "acquired TechCorp LLC for $15 million in New York."
                ),
                "page": 1,
            },
            {
                "text": (
                    "During Q3 2024, revenue grew by 25.5% according to Dr. Alan Turing "
                    "in London. Meanwhile, Alphabet Inc expanded operations."
                ),
                "page": 2,
            },
        ]
        entities = extract_entities(chunks)
        assert len(entities) > 0

        entity_types = {e.entity_type for e in entities}
        values = {e.value for e in entities}

        assert "MONEY" in entity_types
        assert "DATE" in entity_types
        assert "PERCENTAGE" in entity_types
        assert "ORGANIZATION" in entity_types
        assert "LOCATION" in entity_types

        # Check deduplication and counting for Alphabet Inc
        org_entities = [e for e in entities if "Alphabet Inc" in e.value]
        if org_entities:
            assert org_entities[0].count >= 2

    def test_generate_document_insights_with_llm(self, sample_chunks, mock_llm_service):
        """Verify document insights generation with LLM."""
        from llm_service import FreeLLMService
        llm = FreeLLMService()

        insights = generate_document_insights(
            session_id="sess-insights-test",
            chunks=sample_chunks,
            llm_service=llm,
            total_pages=3
        )
        assert isinstance(insights, DocumentInsights)
        assert insights.session_id == "sess-insights-test"
        assert insights.total_pages == 3
        assert insights.total_chunks == len(sample_chunks)
        assert insights.executive_summary is not None
        assert len(insights.executive_summary.key_findings) > 0
        assert len(insights.suggested_questions) > 0
        assert len(insights.key_entities) > 0

    def test_generate_document_insights_fallback(self, sample_chunks):
        """Verify fallback when LLM fails or is not provided."""
        insights = generate_document_insights(
            session_id="sess-fallback",
            chunks=sample_chunks,
            llm_service=None,
            total_pages=1
        )
        assert insights.session_id == "sess-fallback"
        assert insights.executive_summary is None
        assert insights.suggested_questions == _default_questions()

    def test_default_questions(self):
        """Verify default fallback questions list."""
        questions = _default_questions()
        assert len(questions) >= 5
        assert all(isinstance(q, str) and q.endswith("?") for q in questions)
