"""
Unit tests for two-stage verification and NLI entailment logic in Veridocs.
"""

from verification import (
    check_nli_entailment,
    verify_claim_against_chunks,
    check_citations,
    split_sentences_safely,
    is_factual_claim,
)


def test_split_sentences_safely():
    text = "The contract was signed on Jan 1, 2024. Payment is due in 30 days (i.e. Net 30). What about item 1.5?"
    sentences = split_sentences_safely(text)
    assert len(sentences) >= 2
    assert any("contract was signed" in s for s in sentences)
    assert any("Payment is due" in s for s in sentences)


def test_is_factual_claim():
    assert is_factual_claim("The total invoice balance is $12,500 due by Friday.") is True
    assert is_factual_claim("Here are the main points:") is False
    assert is_factual_claim("What is the invoice amount?") is False
    assert is_factual_claim("Short") is False


def test_check_nli_entailment_supported():
    premise = "The total subscription fee is $500 per month payable within thirty days."
    hypothesis = "The monthly subscription fee is $500."
    status, score, label = check_nli_entailment(premise, hypothesis, overlap_score=0.60)
    assert status == "supported"
    assert label == "entailment"
    assert score >= 0.70


def test_check_nli_entailment_numerical_contradiction():
    premise = "The contract penalty fee is $5,000 for early termination."
    hypothesis = "The contract penalty fee is $15,000 for early termination."
    status, score, label = check_nli_entailment(premise, hypothesis, overlap_score=0.75)
    assert status == "contradicted"
    assert label == "contradiction"


def test_check_nli_entailment_negation_contradiction():
    premise = "The vendor is prohibited from disclosing confidential customer information."
    hypothesis = "The vendor is permitted to disclose confidential customer information."
    status, score, label = check_nli_entailment(premise, hypothesis, overlap_score=0.70)
    assert status == "contradicted"
    assert label == "contradiction"


def test_check_nli_entailment_unsupported():
    premise = "The weather in Seattle is rainy in November."
    hypothesis = "The payment terms are net 45 days from invoice issuance."
    status, score, label = check_nli_entailment(premise, hypothesis, overlap_score=0.05)
    assert status == "unsupported"
    assert label == "neutral"


def test_verify_claim_against_chunks():
    chunks = [
        {
            "text": "Invoice #INV-2024-001 has a total due of $4,500.00 by December 15, 2024.",
            "page_number": 1,
            "filename": "invoice.pdf",
            "chunk_type": "text",
            "extraction_method": "text_layer",
            "ocr_confidence": 0.98,
        },
        {
            "text": "Acme Corp provides consulting services with standard net 30 payment terms.",
            "page_number": 2,
            "filename": "invoice.pdf",
            "chunk_type": "text",
            "extraction_method": "text_layer",
            "ocr_confidence": 0.98,
        },
    ]

    claim = "The invoice total due is $4,500.00."
    res = verify_claim_against_chunks(claim, chunks)
    assert res["status"] == "supported"
    assert res["is_supported"] is True
    assert res["matched_page"] == 1
    assert res["source_file"] == "invoice.pdf"


def test_check_citations_with_warnings():
    chunks = [
        {
            "text": "The Q3 revenue grew by 18% year over year according to the bar chart.",
            "page_number": 1,
            "filename": "report.pdf",
            "chunk_type": "figure",
            "extraction_method": "vision",
            "ocr_confidence": None,
        },
        {
            "text": "Scanned blurry receipt showing total amount of $34.50 paid in cash.",
            "page_number": 2,
            "filename": "receipt.pdf",
            "chunk_type": "text",
            "extraction_method": "ocr",
            "ocr_confidence": 0.45,  # Low OCR confidence
        },
    ]

    answer = "The Q3 revenue grew by 18% year over year. The scanned receipt shows an amount of $999.00 paid in cash."

    result = check_citations(answer, chunks)
    assert result["total_claims"] == 2
    assert result["has_vision_only_warning"] is True
    assert result["has_low_confidence_ocr_warning"] is True
    assert result["has_contradiction_warning"] is True
    assert result["contradicted_claims"] >= 1
