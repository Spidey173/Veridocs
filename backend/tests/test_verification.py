"""
Unit tests for verification.py grounding verification and citation extraction.
"""

import pytest
from verification import (
    calculate_grounding_score,
    extract_citations_from_answer,
    _extract_claims,
    _substring_similarity,
)


class TestVerification:
    def test_calculate_grounding_score_empty(self):
        """Verify empty answer or chunks returns confidence 0.0."""
        res1 = calculate_grounding_score("", [{"text": "content", "page": 1}])
        assert res1["confidence_score"] == 0.0

        res2 = calculate_grounding_score("Some answer here.", [])
        assert res2["confidence_score"] == 0.0

    def test_calculate_grounding_score_grounded(self, sample_chunks):
        """Verify high confidence score for answer matching source chunks."""
        answer = (
            "Veridocs provides two-stage retrieval using FAISS and Cross-Encoder. "
            "Q3 2024 revenue reached $2.5 million representing a 35% increase."
        )
        score_info = calculate_grounding_score(answer, sample_chunks)
        assert score_info["confidence_score"] >= 0.7
        assert score_info["supported_claims"] >= 1
        assert len(score_info["unsupported_claims"]) == 0

    def test_calculate_grounding_score_unsupported(self, sample_chunks):
        """Verify lower score and unsupported claims when hallucinations occur."""
        answer = (
            "The company was founded in Antarctica in the year 1820. "
            "Penguins represent the majority of executive leadership."
        )
        score_info = calculate_grounding_score(answer, sample_chunks)
        assert score_info["confidence_score"] < 0.5
        assert len(score_info["unsupported_claims"]) > 0

    def test_extract_citations_from_answer(self, sample_chunks):
        """Verify [Page X] extraction and mapping to chunks."""
        answer = "Veridocs uses FAISS [Page 1] and verification [Page 2]."
        citations = extract_citations_from_answer(answer, sample_chunks)

        assert len(citations) == 2
        pages = [c["page"] for c in citations]
        assert 1 in pages
        assert 2 in pages
        assert citations[0]["citation_id"] == 1
        assert citations[1]["citation_id"] == 2
        assert "highlighted_text" in citations[0]

    def test_extract_citations_no_matches(self, sample_chunks):
        """Verify answer without page markers returns empty list."""
        answer = "No page citations here."
        citations = extract_citations_from_answer(answer, sample_chunks)
        assert citations == []

    def test_extract_claims_filtering(self):
        """Verify _extract_claims filters out meta-statements and questions."""
        text = (
            "Here is the summary. "
            "Veridocs supports fast document indexing with semantic embeddings. "
            "How does it work? "
            "The system was evaluated on enterprise benchmarks."
        )
        claims = _extract_claims(text)
        assert not any("here is the summary" in c.lower() for c in claims)
        assert not any(c.endswith("?") for c in claims)
        assert any("Veridocs supports" in c for c in claims)

    def test_substring_similarity(self):
        """Verify 3-word window substring matching."""
        claim = "the fast brown fox jumped"
        source = "we noticed that the fast brown fox jumped over the fence"
        sim = _substring_similarity(claim, source)
        assert sim == 1.0

        diff_source = "completely unrelated text without those words"
        assert _substring_similarity(claim, diff_source) == 0.0
