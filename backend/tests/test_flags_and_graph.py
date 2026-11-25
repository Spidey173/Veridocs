"""
Unit tests for anomaly flags, knowledge graph, and graph-aware QA:
1. Rule-based anomaly flags (math mismatch, duplicate invoice, metadata anomaly, date inconsistency, cross-document, threshold evasion)
2. Knowledge graph builder and entity resolution (legal suffix normalization, rapidfuzz canonical matching)
3. Graph endpoints (GET /documents/{id}/graph, GET /graph?entity=...)
4. Graph-aware QA routing and retrieval strategy logging
"""

import database
from models_db import Document, Page, Extraction
from flags.rules import (
    check_invoice_math_mismatch,
    check_duplicate_invoice,
    check_pdf_metadata_anomaly,
    check_date_inconsistency,
    check_cross_document_mismatch,
    check_round_number_and_threshold,
)
from flags.checker import FlagCheckerService
from graph.resolution import strip_legal_suffixes, EntityResolver
from graph.builder import KnowledgeGraphBuilder
from graph.router import is_relationship_query, GraphQARouter


# --- Anomaly Flags Tests ---


def test_invoice_math_mismatch_flag():
    # Math mismatch: Subtotal $1,000 + Tax $100 != Total $1,500
    extractions = {
        "fields": {
            "subtotal": {"value": 1000.0, "page": 1, "quote": "Subtotal: $1,000.00"},
            "tax": {"value": 100.0, "page": 1, "quote": "Tax: $100.00"},
            "total": {"value": 1500.0, "page": 1, "quote": "Total: $1,500.00"},
        }
    }
    flags = check_invoice_math_mismatch("doc_01", extractions, [])
    assert len(flags) == 1
    assert flags[0]["rule_id"] == "invoice_math_mismatch"
    assert flags[0]["severity"] == "high"
    assert "$1,000.00" in flags[0]["message"]
    assert flags[0]["confidence"] >= 0.95


def test_date_inconsistency_flag():
    # Due date precedes invoice issuance date
    extractions = {
        "fields": {
            "invoice_date": {"value": "2024-10-15", "page": 1},
            "due_date": {"value": "2024-09-15", "page": 1},
            "payment_terms": {"value": "Net 30 days", "page": 1},
        }
    }
    flags = check_date_inconsistency("doc_01", extractions, [])
    assert len(flags) >= 1
    d_flag = next(f for f in flags if f["rule_id"] == "date_inconsistency")
    assert d_flag["severity"] == "high"
    assert "precedes invoice issuance date" in d_flag["message"]


def test_round_number_and_threshold_flag():
    # Amount calibrated just below $10,000 threshold
    extractions = {"fields": {"total": {"value": 9999.0, "page": 1, "quote": "$9,999.00"}}}
    flags = check_round_number_and_threshold("doc_01", extractions, [])
    assert len(flags) == 1
    assert flags[0]["rule_id"] == "round_number_and_threshold"
    assert flags[0]["severity"] == "medium"
    assert "$10,000.00" in flags[0]["message"]


def test_pdf_metadata_anomaly_flag():
    # Scanned OCR page with digital InDesign producer and future date
    pages = [{"page_number": 1, "extraction_method": "ocr", "text": "Scanned document"}]
    metadata = {
        "producer": "Adobe InDesign CC 2024 (Windows)",
        "creation_date": "D:20300101120000",
    }
    flags = check_pdf_metadata_anomaly("doc_01", pages, metadata)
    assert len(flags) >= 1
    rules = [f["rule_id"] for f in flags]
    assert "pdf_metadata_anomaly" in rules


def test_duplicate_invoice_flag():
    with database.get_db() as db:
        # Create earlier invoice
        doc_old = Document(filename="invoice_march.pdf", status="ready")
        db.add(doc_old)
        db.commit()
        db.refresh(doc_old)

        ext_old = Extraction(
            document_id=doc_old.id,
            schema_type="invoice",
            json_data={"invoice_number": {"value": "INV-7721"}, "vendor": {"value": "Acme Supplies"}},
            verified_ratio=1.0,
        )
        db.add(ext_old)
        db.commit()

        # Check new invoice with identical invoice number
        new_ext = {
            "fields": {
                "invoice_number": {"value": "INV-7721", "page": 1},
                "vendor": {"value": "Acme Supplies", "page": 1},
            }
        }
        flags = check_duplicate_invoice("doc_new", new_ext, db)
        assert len(flags) == 1
        assert flags[0]["rule_id"] == "duplicate_invoice"
        assert "INV-7721" in flags[0]["message"]


def test_cross_document_mismatch_flag():
    with database.get_db() as db:
        sid = "test_session_po"
        doc_po = Document(filename="purchase_order_99.pdf", session_id=sid, status="ready")
        doc_inv = Document(filename="invoice_99.pdf", session_id=sid, status="ready")
        db.add_all([doc_po, doc_inv])
        db.commit()
        db.refresh(doc_po)
        db.refresh(doc_inv)

        ext_po = Extraction(
            document_id=doc_po.id,
            schema_type="invoice",
            json_data={"total": {"value": 10000.0}},
            verified_ratio=1.0,
        )
        db.add(ext_po)
        db.commit()

        # Invoice claims $12,500 for a $10,000 authorized PO
        inv_ext = {"fields": {"total": {"value": 12500.0, "page": 1}}}
        flags = check_cross_document_mismatch(doc_inv.id, inv_ext, db)
        assert len(flags) == 1
        assert flags[0]["rule_id"] == "cross_document_mismatch"
        assert "$12,500.00" in flags[0]["message"]
        assert "$10,000.00" in flags[0]["message"]


def test_flags_checker_service_and_endpoint(test_client):
    with database.get_db() as db:
        doc = Document(filename="suspicious_invoice.pdf", status="ready")
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id

        p = Page(document_id=doc_id, page_number=1, text="Subtotal: $500.00\nTax: $50.00\nTotal: $9,999.00")
        db.add(p)
        db.commit()

        ext = Extraction(
            document_id=doc_id,
            schema_type="invoice",
            json_data={
                "subtotal": {"value": 500.0, "page": 1},
                "tax": {"value": 50.0, "page": 1},
                "total": {"value": 9999.0, "page": 1, "quote": "$9,999.00"},
            },
            verified_ratio=1.0,
        )
        db.add(ext)
        db.commit()

        service = FlagCheckerService(db)
        flags = service.run_all_checks(doc_id)
        assert len(flags) >= 2  # Math mismatch + round threshold

    # Test GET /documents/{id}/flags
    res = test_client.get(f"/documents/{doc_id}/flags")
    assert res.status_code == 200
    data = res.json()
    assert "disclaimer" in data
    assert "signals for human review" in data["disclaimer"]
    assert data["total_flags"] >= 2
    assert "severity_counts" in data


# --- Knowledge Graph & Resolution Tests ---


def test_entity_resolution_legal_suffixes():
    assert strip_legal_suffixes("Acme Corporation") == "Acme"
    assert strip_legal_suffixes("Beta Technologies LLC") == "Beta"
    assert strip_legal_suffixes("Global Holdings Inc.") == "Global"


def test_entity_resolution_fuzzy_matching():
    resolver = EntityResolver(similarity_threshold=85.0)

    existing_nodes = [
        {
            "id": "org:acme",
            "label": "Organization",
            "name": "Acme Corporation",
            "canonical_name": "Acme",
            "aliases": ["Acme Corp", "Acme Inc"],
        }
    ]

    # Test exact stripped match
    n_id, canon, is_match = resolver.resolve_entity("Acme Corp.", "Organization", existing_nodes)
    assert is_match is True
    assert n_id == "org:acme"

    # Test fuzzy match
    n_id2, canon2, is_match2 = resolver.resolve_entity("Acme Corporation Services", "Organization", existing_nodes)
    assert is_match2 is True
    assert n_id2 == "org:acme"

    # Test distinct entity does not match
    n_id3, canon3, is_match3 = resolver.resolve_entity("Delta Logistics Group", "Organization", existing_nodes)
    assert is_match3 is False
    assert "delta" in n_id3


def test_knowledge_graph_builder_and_endpoints(test_client):
    with database.get_db() as db:
        doc = Document(filename="alpha_beta_contract.pdf", status="ready")
        db.add(doc)
        db.commit()
        db.refresh(doc)
        doc_id = doc.id

        page_text = "Acme Corp agrees to pay Beta LLC $5,000 monthly. Signed by Alice Smith."
        p = Page(document_id=doc_id, page_number=1, text=page_text)
        db.add(p)
        db.commit()

        # Add extraction for payment & parties
        ext = Extraction(
            document_id=doc_id,
            schema_type="contract",
            json_data={
                "parties": {"value": ["Acme Corp", "Beta LLC"], "page": 1, "quote": "Acme Corp agrees to pay Beta LLC"},
                "buyer": {"value": "Acme Corp"},
                "vendor": {"value": "Beta LLC"},
                "total": {"value": 5000.0, "page": 1, "quote": "$5,000 monthly"},
                "signed_by": {"value": "Alice Smith", "page": 1, "quote": "Signed by Alice Smith"},
            },
            verified_ratio=1.0,
        )
        db.add(ext)
        db.commit()

        builder = KnowledgeGraphBuilder(db)
        graph = builder.build_for_document(doc_id)

        assert graph["total_nodes"] >= 3
        assert graph["total_edges"] >= 2
        relations = [e["relation"] for e in graph["edges"]]
        assert "PARTY_TO" in relations
        assert "PAYS" in relations
        assert "SIGNED_BY" in relations

        # Check edge quote verification
        pays_edge = next(e for e in graph["edges"] if e["relation"] == "PAYS")
        assert pays_edge["verified"] is True

    # Test GET /documents/{id}/graph
    res = test_client.get(f"/documents/{doc_id}/graph")
    assert res.status_code == 200
    graph_res = res.json()
    assert "nodes" in graph_res
    assert "edges" in graph_res
    assert graph_res["total_edges"] >= 2

    # Test GET /graph?entity=Acme
    res_cross = test_client.get("/graph?entity=Acme")
    assert res_cross.status_code == 200
    cross_data = res_cross.json()
    assert cross_data["total_nodes"] >= 1


# --- Graph-Aware QA Tests ---


def test_is_relationship_query():
    assert is_relationship_query("Who pays whom in the agreement?") is True
    assert is_relationship_query("Who signed the master agreement?") is True
    assert is_relationship_query("What is the relationship between Acme and Beta?") is True
    assert is_relationship_query("Which contracts involve Acme Corp?") is True
    assert is_relationship_query("What is the refund policy?") is False


def test_graph_qa_router_and_strategy(test_client):
    with database.get_db() as db:
        sid = "qa_session_graph"
        doc = Document(filename="payment_agreement.pdf", session_id=sid, status="ready")
        db.add(doc)
        db.commit()
        db.refresh(doc)

        p = Page(document_id=doc.id, page_number=1, text="Acme Corp pays Beta LLC $10,000.")
        db.add(p)
        db.commit()

        builder = KnowledgeGraphBuilder(db)
        # Seed nodes and edge
        n1 = builder._get_or_create_node("org:acme", "Organization", "Acme Corp", "Acme", doc.id)
        n2 = builder._get_or_create_node("org:beta", "Organization", "Beta LLC", "Beta", doc.id)
        builder._create_edge(
            source_id=n1.id,
            target_id=n2.id,
            relation="PAYS",
            document_id=doc.id,
            page_number=1,
            quote="Acme Corp pays Beta LLC $10,000",
            page_text=p.text,
        )
        db.commit()

        router = GraphQARouter(db)
        chunks, strategy = router.route_query(
            "Who pays whom in this document?",
            session_id=sid,
        )
        assert strategy == "graph"
        assert len(chunks) >= 1
        assert "Knowledge Graph Fact" in chunks[0]["text"]
        assert "PAYS" in chunks[0]["text"]
