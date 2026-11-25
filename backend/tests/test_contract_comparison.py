"""
Unit tests for Contract Comparison and Clause Segmentation:
1. Clause segmentation (numbering, headings, LLM fallback, embeddings)
2. Hungarian algorithm alignment and word-level diffing
3. Change classification (unchanged, modified, added, removed, moved)
4. Risk summaries, verbatim quote validation, and Markdown export
5. REST API endpoints (POST /comparisons, GET /comparisons/{id})
"""

import pytest
from models_db import Document, Page
import database
from comparison.clause_segmenter import ClauseSegmenter
from comparison.aligner import ClauseAligner
from comparison.service import ComparisonService, summarize_clause_change_llm, export_comparison_to_markdown


@pytest.fixture
def sample_contract_pages_v1():
    return [
        {
            "page_number": 1,
            "text": (
                "MASTER SERVICES AGREEMENT\n"
                "This Agreement is entered into between Acme Corp and Beta Corp.\n"
                "1. Term. The initial term of this agreement shall be 12 months.\n"
                "2. Fees and Invoicing. Customer agrees to pay $5,000 per month for cloud database hosting.\n"
            ),
        },
        {
            "page_number": 2,
            "text": (
                "3. Limitation of Liability. Neither party's aggregate liability shall exceed $100,000.00.\n"
                "4. Governing Law. This agreement is governed by the laws of Delaware.\n"
                "5. Confidentiality. Parties will maintain confidentiality for 3 years.\n"
            ),
        },
    ]


@pytest.fixture
def sample_contract_pages_v2():
    return [
        {
            "page_number": 1,
            "text": (
                "MASTER SERVICES AGREEMENT\n"
                "This Agreement is entered into between Acme Corp and Beta Corp.\n"
                "1. Term. The initial term of this agreement shall be 24 months.\n"  # Modified: 12 -> 24
                "2. Fees and Invoicing. Customer agrees to pay $15,000 per month for cloud database hosting.\n"  # Modified: 5,000 -> 15,000
                "2.1 Surcharges. Fuel and energy surcharges of 5% may apply.\n"  # Added clause
            ),
        },
        {
            "page_number": 2,
            "text": (
                "3. Limitation of Liability. Neither party's aggregate liability shall exceed $100,000.00.\n"  # Unchanged
                "4. Governing Law. This agreement is governed by the laws of Delaware.\n"  # Unchanged
                # Removed: Confidentiality clause
            ),
        },
    ]


def test_clause_segmenter_numbering_and_headings(sample_contract_pages_v1):
    segmenter = ClauseSegmenter()
    clauses = segmenter.segment_pages(sample_contract_pages_v1, document_id="doc_v1")

    assert len(clauses) >= 5
    numbers = [c.get("number") for c in clauses if c.get("number")]
    assert "1" in numbers or "1." in numbers
    assert "2" in numbers or "2." in numbers
    assert "3" in numbers or "3." in numbers

    # Verify embeddings exist and have dimension 384
    for c in clauses:
        emb = c.get("embedding")
        assert emb is not None
        assert len(emb) == 384


def test_clause_aligner_diff_and_classification(sample_contract_pages_v1, sample_contract_pages_v2):
    segmenter = ClauseSegmenter()
    clauses_v1 = segmenter.segment_pages(sample_contract_pages_v1, document_id="doc_v1")
    clauses_v2 = segmenter.segment_pages(sample_contract_pages_v2, document_id="doc_v2")

    aligner = ClauseAligner(similarity_threshold=0.60)
    aligned = aligner.align_and_diff(clauses_v1, clauses_v2)

    statuses = [a["status"] for a in aligned]
    assert "unchanged" in statuses
    assert "modified" in statuses
    assert "added" in statuses
    assert "removed" in statuses

    # Find modified fee clause
    fee_diff = next(
        a for a in aligned if a["status"] == "modified" and ("fee" in (a["clause_a"].get("text", "").lower()))
    )
    assert fee_diff["clause_a"] is not None
    assert fee_diff["clause_b"] is not None
    assert fee_diff["similarity"] >= 0.70

    # Test word-level diff tokens
    tokens = fee_diff["diff_tokens"]
    inserted = [t["text"] for t in tokens if t["type"] == "insert"]
    deleted = [t["text"] for t in tokens if t["type"] == "delete"]
    assert any("$15,000" in t for t in inserted)
    assert any("$5,000" in t for t in deleted)


def test_summarize_clause_change_and_risk():
    clause_a = {
        "text": "Neither party's aggregate liability shall exceed $100,000.00.",
        "page_start": 2,
    }
    clause_b = {
        "text": "Neither party's aggregate liability shall exceed $10,000,000.00.",
        "page_start": 2,
    }

    analysis = summarize_clause_change_llm(clause_a, clause_b)
    assert analysis["change_type"] in ("liability", "financial", "other")
    assert analysis["risk"] in ("medium", "high")
    assert bool(analysis["summary"]) is True


def test_export_comparison_to_markdown():
    comparison_data = {
        "doc_a": {"filename": "contract_2023.pdf", "clause_count": 4},
        "doc_b": {"filename": "contract_2024.pdf", "clause_count": 5},
        "stats": {
            "status_counts": {"unchanged": 2, "modified": 2, "added": 1, "removed": 0, "moved": 0},
            "risk_counts": {"high": 1, "medium": 1, "low": 0},
        },
        "aligned_clauses": [
            {
                "status": "modified",
                "clause_a": {"number": "2.", "heading": "Fees", "text": "Pay $5,000."},
                "clause_b": {"number": "2.", "heading": "Fees", "text": "Pay $15,000."},
                "page_a": 1,
                "page_b": 1,
                "diff_tokens": [
                    {"type": "equal", "text": "Pay"},
                    {"type": "delete", "text": "$5,000."},
                    {"type": "insert", "text": "$15,000."},
                ],
                "analysis": {
                    "change_type": "financial",
                    "risk": "high",
                    "summary": "Monthly fee increased from $5,000 to $15,000.",
                    "risk_reason": "3x cost increase.",
                    "evidence_quote": "$15,000.",
                    "quote_verified": True,
                },
            }
        ],
    }

    md = export_comparison_to_markdown(comparison_data)
    assert "# Contract Comparison Report" in md
    assert "HIGH RISK" in md
    assert "~~$5,000.~~" in md
    assert "**$15,000.**" in md


def test_comparison_api_and_service(test_client):
    with database.get_db() as db:
        doc1 = Document(filename="agreement_v1.pdf", status="ready")
        doc2 = Document(filename="agreement_v2.pdf", status="ready")
        db.add_all([doc1, doc2])
        db.commit()
        db.refresh(doc1)
        db.refresh(doc2)

        # Add sample pages to doc1 and doc2
        p1 = Page(document_id=doc1.id, page_number=1, text="1. Term: 12 months.\n2. Liability: $50,000.")
        p2 = Page(document_id=doc2.id, page_number=1, text="1. Term: 24 months.\n2. Liability: $50,000.")
        db.add_all([p1, p2])
        db.commit()

        doc1_id = doc1.id
        doc2_id = doc2.id

    # 1. Test POST /comparisons
    res = test_client.post("/comparisons", json={"doc_a": doc1_id, "doc_b": doc2_id})
    assert res.status_code == 200
    data = res.json()
    comp_id = data["id"]
    assert data["status"] in ("queued", "processing", "ready")

    # 2. Run service synchronously to populate ready state
    with database.get_db() as db:
        service = ComparisonService(db)
        comp = service.run_comparison(doc1_id, doc2_id, comparison_id=comp_id)
        assert comp.status == "ready"
        assert comp.json_data is not None

    # 3. Test GET /comparisons/{id}
    res_get = test_client.get(f"/comparisons/{comp_id}")
    assert res_get.status_code == 200
    res_data = res_get.json()
    assert res_data["status"] == "ready"
    assert "aligned_clauses" in res_data["data"]

    # 4. Test GET /comparisons/{id}/export
    res_exp = test_client.get(f"/comparisons/{comp_id}/export")
    assert res_exp.status_code == 200
    exp_json = res_exp.json()
    assert "markdown" in exp_json
    assert "Contract Comparison Report" in exp_json["markdown"]
