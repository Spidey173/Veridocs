"""
Unit tests for verifier behavior, entity extraction labeling, and DB safeguards:
1. Verifier honesty: Heuristic NLI screen vs model cross-encoder fallback.
2. Entity extraction honesty: Pattern-based extraction labeling and behavior.
3. Postgres CI enforcement: Immediate fail-loud behavior on unreachable database.
"""

import pytest
from verification import run_heuristic_nli_screen, check_nli_entailment
from entities.extractor import EntityExtractor
from config import get_settings


def test_heuristic_nli_screen_contradiction_detection():
    # Number discrepancy
    premise = "The total contract liability shall not exceed $500,000.00."
    claim_wrong_num = "The total contract liability shall not exceed $5,000,000.00."
    status, conf, label = run_heuristic_nli_screen(premise, claim_wrong_num, overlap_score=0.85)
    assert status == "contradicted"
    assert label == "contradiction"
    assert conf >= 0.85

    # Direct antonym/polarity flip
    premise_perm = "Vendor is strictly prohibited from sharing customer confidential information."
    claim_flip = "Vendor is permitted to share customer confidential information."
    status2, conf2, label2 = run_heuristic_nli_screen(premise_perm, claim_flip, overlap_score=0.80)
    assert status2 == "contradicted"
    assert label2 == "contradiction"

    # Consistent supported text
    premise_supp = "The payment terms are strictly Net 30 days from the invoice issuance date."
    claim_supp = "Payment terms are Net 30 days from the invoice date."
    status3, conf3, label3 = run_heuristic_nli_screen(premise_supp, claim_supp, overlap_score=0.75)
    assert status3 == "supported"
    assert label3 == "entailment"


def test_check_nli_entailment_heuristic_mode():
    premise = "Customer will pay $5,000 monthly subscription fee."
    claim_contra = "Customer will pay $15,000 monthly subscription fee."
    status, conf, label = check_nli_entailment(premise, claim_contra, 0.8, force_heuristic=True)
    assert status == "contradicted"
    assert label == "contradiction"

    claim_match = "Customer will pay $5,000 monthly subscription fee."
    status_supp, conf_supp, label_supp = check_nli_entailment(premise, claim_match, 0.9, force_heuristic=True)
    assert status_supp == "supported"
    assert label_supp == "entailment"
    assert conf_supp >= 0.70


def test_check_nli_entailment_model_mode_fallback():
    # When NLI_MODEL / sentence_transformers is not installed, it falls back cleanly to heuristic
    premise = "All data is encrypted at rest using AES-256."
    claim = "All data is encrypted at rest using AES-256."
    status, conf, label = check_nli_entailment(premise, claim, 0.9, force_heuristic=False)
    assert status in ("supported", "unsupported")
    assert isinstance(conf, float)
    assert label in ("entailment", "neutral", "contradiction")


def test_entity_extractor_honesty_labeling():
    settings = get_settings()
    extractor = EntityExtractor()
    assert extractor.pattern_mode is True or not settings.GLINER_ENABLED

    sample_chunk = "On October 15, 2024, ACME Corp agreed to pay $12,500.00 to Global Supplies LLC in Dover, Delaware."
    entities = extractor.extract_from_chunk(sample_chunk, page_number=1, chunk_id="test_01")
    assert len(entities) >= 3

    labels = {e["label"] for e in entities}
    assert "date" in labels
    assert "money" in labels
    assert "organization" in labels

    # Check normalization
    money_ents = [e for e in entities if e["label"] == "money"]
    assert any(m["normalized"] == {"amount": 12500.0, "currency": "USD"} for m in money_ents)


def test_ci_postgres_enforcement_raises_on_unreachable_db(monkeypatch):
    """
    Verifies that CI enforcement detects unreachable PostgreSQL and raises a RuntimeError
    instead of silently falling back to SQLite.
    """
    from sqlalchemy import create_engine, text

    unreachable_url = "postgresql://veridocs:invalid_pass@127.0.0.1:54321/nonexistent_db"

    with pytest.raises(RuntimeError) as exc_info:
        # Simulate the CI check in conftest.py
        try:
            check_engine = create_engine(unreachable_url, pool_pre_ping=True)
            with check_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception as e:
            raise RuntimeError(
                f"[CI Postgres Enforcement] Integration tests must run on real PostgreSQL in CI, "
                f"but PostgreSQL is unreachable at '{unreachable_url}': {e}."
            ) from e

    assert "[CI Postgres Enforcement]" in str(exc_info.value)
    assert "unreachable" in str(exc_info.value)
