"""
Knowledge Graph Construction Engine for Veridocs.
Builds and maintains interconnected nodes and edges from:
- Documents
- Clauses
- Extracted Entities (Organization, Person, Date, Money)
- Structured Schema Extractions (Parties, Payment Obligations, Signatures)

Ensures every edge cites page numbers and verbatim verified quotes.
"""

import time
import uuid
import logging
from typing import Dict, Any, Optional, Set
from sqlalchemy.orm import Session

from config import get_settings
from models_db import Document, Clause, Entity, Extraction, GraphNode, GraphEdge
from graph.resolution import EntityResolver, strip_legal_suffixes
from extraction.extractor import verify_quote_in_page_text

logger = logging.getLogger(__name__)


class KnowledgeGraphBuilder:
    """Builds and queries the PostgreSQL-backed knowledge graph."""

    def __init__(self, db: Session):
        self.db = db
        self.resolver = EntityResolver()
        self.settings = get_settings()

    def build_for_document(self, document_id: str) -> Dict[str, Any]:
        """Extracts and connects nodes and edges for a given document."""
        doc = self.db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            logger.warning(f"Document {document_id} not found for graph construction.")
            return {"nodes": [], "edges": []}

        pages = {p.page_number: p.text for p in doc.pages}

        # 1. Document Node
        doc_node_id = f"doc:{doc.id}"
        self._get_or_create_node(
            node_id=doc_node_id,
            label="Document",
            name=doc.filename,
            canonical_name=doc.filename,
            document_id=doc.id,
            properties={"mime_type": doc.mime_type, "doc_type": doc.doc_type},
        )

        existing_db_nodes = [n.to_dict() for n in self.db.query(GraphNode).all()]

        # 2. Process Clauses
        clauses = self.db.query(Clause).filter(Clause.document_id == document_id).all()
        for clause in clauses:
            clause_node_id = f"clause:{doc.id}_{clause.clause_index}"
            heading = clause.heading or f"Section {clause.clause_index + 1}"
            self._get_or_create_node(
                node_id=clause_node_id,
                label="Clause",
                name=heading,
                canonical_name=heading,
                document_id=doc.id,
                properties={"number": clause.number, "page_start": clause.page_start, "page_end": clause.page_end},
            )

            # Edge: Clause -> REFERENCES -> Document
            quote = clause.text[:60] if clause.text else heading
            self._create_edge(
                source_id=clause_node_id,
                target_id=doc_node_id,
                relation="REFERENCES",
                document_id=doc.id,
                page_number=clause.page_start,
                quote=quote,
                page_text=pages.get(clause.page_start, ""),
            )

        # 3. Process Entities (Organizations, Persons, Dates, Money)
        entities = self.db.query(Entity).filter(Entity.document_id == document_id).all()
        for ent in entities:
            label = ent.label.capitalize()
            if label not in ("Organization", "Person", "Date", "Money"):
                if label == "Party":
                    label = "Party"
                else:
                    continue

            raw_text = ent.text.strip()
            if len(raw_text) < 2:
                continue

            node_id, canonical, is_match = self.resolver.resolve_entity(raw_text, label, existing_db_nodes)

            node = self._get_or_create_node(
                node_id=node_id,
                label=label,
                name=raw_text,
                canonical_name=canonical,
                document_id=doc.id,
                properties={"normalized": ent.normalized},
            )

            # Edge: Entity -> MENTIONED_IN -> Document
            p_text = pages.get(ent.page_number, "")
            self._create_edge(
                source_id=node.id,
                target_id=doc_node_id,
                relation="MENTIONED_IN",
                document_id=doc.id,
                page_number=ent.page_number,
                quote=raw_text,
                page_text=p_text,
            )

        # 4. Process Structured Extractions (Parties, Payment Obligations, Signatures)
        ext_record = self.db.query(Extraction).filter(Extraction.document_id == document_id).first()
        if ext_record and ext_record.json_data:
            fields = ext_record.json_data

            # (a) Contract / Invoice Parties
            parties_entry = fields.get("parties")
            if isinstance(parties_entry, dict) and "value" in parties_entry:
                parties_list = parties_entry.get("value") or []
                p_quote = parties_entry.get("quote", "")
                p_page = parties_entry.get("page", 1)
                p_text = pages.get(p_page, "")

                party_nodes = []
                for p_name in parties_list:
                    p_id, p_canon, _ = self.resolver.resolve_entity(str(p_name), "Party", existing_db_nodes)
                    p_node = self._get_or_create_node(p_id, "Party", str(p_name), p_canon, doc.id)
                    party_nodes.append(p_node)

                    # Edge: Party -> PARTY_TO -> Document
                    self._create_edge(
                        source_id=p_node.id,
                        target_id=doc_node_id,
                        relation="PARTY_TO",
                        document_id=doc.id,
                        page_number=p_page,
                        quote=p_quote or str(p_name),
                        page_text=p_text,
                    )

            # (b) Vendor / Customer relationships & Payment Obligations
            vendor_entry = fields.get("vendor") or {}
            buyer_entry = fields.get("buyer") or fields.get("customer") or {}
            total_entry = fields.get("total") or {}

            vend_name = vendor_entry.get("value")
            buyer_name = buyer_entry.get("value")
            total_val = total_entry.get("value")

            if vend_name and buyer_name:
                v_id, v_canon, _ = self.resolver.resolve_entity(str(vend_name), "Organization", existing_db_nodes)
                b_id, b_canon, _ = self.resolver.resolve_entity(str(buyer_name), "Organization", existing_db_nodes)

                v_node = self._get_or_create_node(v_id, "Organization", str(vend_name), v_canon, doc.id)
                b_node = self._get_or_create_node(b_id, "Organization", str(buyer_name), b_canon, doc.id)

                quote_pays = f"Customer: {buyer_name} pays Vendor: {vend_name}"
                p_num = total_entry.get("page", 1)
                p_text = pages.get(p_num, "")

                if total_val:
                    quote_pays += f" Total: ${total_val}"

                # Edge: Buyer -> PAYS / OWES -> Vendor
                self._create_edge(
                    source_id=b_node.id,
                    target_id=v_node.id,
                    relation="PAYS",
                    document_id=doc.id,
                    page_number=p_num,
                    quote=total_entry.get("quote", quote_pays),
                    page_text=p_text,
                    properties={"amount": total_val},
                )

            # (c) Signatures
            signer_entry = fields.get("signed_by") or fields.get("signatory") or {}
            signer_name = signer_entry.get("value")
            if signer_name:
                s_id, s_canon, _ = self.resolver.resolve_entity(str(signer_name), "Person", existing_db_nodes)
                s_node = self._get_or_create_node(s_id, "Person", str(signer_name), s_canon, doc.id)
                s_page = signer_entry.get("page", 1)
                self._create_edge(
                    source_id=s_node.id,
                    target_id=doc_node_id,
                    relation="SIGNED_BY",
                    document_id=doc.id,
                    page_number=s_page,
                    quote=signer_entry.get("quote", str(signer_name)),
                    page_text=pages.get(s_page, ""),
                )

        self.db.commit()
        return self.get_document_graph(document_id)

    def get_document_graph(self, document_id: str, max_nodes: Optional[int] = None) -> Dict[str, Any]:
        """Retrieves nodes and edges connected to a document, capped for performance."""
        limit = max_nodes or self.settings.GRAPH_MAX_RENDER_NODES

        # Find all edges for this document
        edges = self.db.query(GraphEdge).filter(GraphEdge.document_id == document_id).limit(limit * 2).all()

        node_ids: Set[str] = {f"doc:{document_id}"}
        for e in edges:
            node_ids.add(e.source_id)
            node_ids.add(e.target_id)

        nodes = self.db.query(GraphNode).filter(GraphNode.id.in_(list(node_ids)[:limit])).all()

        return {
            "document_id": document_id,
            "capped": len(node_ids) > limit,
            "total_nodes": len(nodes),
            "total_edges": len(edges),
            "nodes": [n.to_dict() for n in nodes],
            "edges": [e.to_dict() for e in edges],
        }

    def search_cross_document_graph(self, entity_query: str, max_nodes: Optional[int] = None) -> Dict[str, Any]:
        """Cross-document graph traversal finding all connections for an entity or company."""
        limit = max_nodes or self.settings.GRAPH_MAX_RENDER_NODES
        clean_q = strip_legal_suffixes(entity_query).lower()

        matching_nodes = self.db.query(GraphNode).filter(GraphNode.canonical_name.ilike(f"%{clean_q}%")).all()

        if not matching_nodes:
            return {"query": entity_query, "nodes": [], "edges": []}

        seed_ids = {n.id for n in matching_nodes}

        # 1-hop and 2-hop edges
        connected_edges = (
            self.db.query(GraphEdge)
            .filter((GraphEdge.source_id.in_(seed_ids)) | (GraphEdge.target_id.in_(seed_ids)))
            .limit(limit * 2)
            .all()
        )

        all_node_ids = set(seed_ids)
        for e in connected_edges:
            all_node_ids.add(e.source_id)
            all_node_ids.add(e.target_id)

        all_nodes = self.db.query(GraphNode).filter(GraphNode.id.in_(list(all_node_ids)[:limit])).all()

        return {
            "query": entity_query,
            "capped": len(all_node_ids) > limit,
            "total_nodes": len(all_nodes),
            "total_edges": len(connected_edges),
            "nodes": [n.to_dict() for n in all_nodes],
            "edges": [e.to_dict() for e in connected_edges],
        }

    def _get_or_create_node(
        self,
        node_id: str,
        label: str,
        name: str,
        canonical_name: str,
        document_id: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> GraphNode:
        """Finds or creates a GraphNode in DB and updates document associations."""
        node = self.db.query(GraphNode).filter(GraphNode.id == node_id).first()
        if not node:
            node = GraphNode(
                id=node_id,
                label=label,
                name=name,
                canonical_name=canonical_name,
                aliases=[name],
                properties=properties or {},
                document_ids=[document_id],
                created_at=time.time(),
            )
            self.db.add(node)
        else:
            doc_ids = node.document_ids or []
            if document_id not in doc_ids:
                doc_ids.append(document_id)
                node.document_ids = doc_ids

            aliases = node.aliases or []
            if name not in aliases:
                aliases.append(name)
                node.aliases = aliases

        return node

    def _create_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        document_id: str,
        page_number: int,
        quote: str,
        page_text: str = "",
        properties: Optional[Dict[str, Any]] = None,
    ) -> Optional[GraphEdge]:
        """Creates a verified edge connecting two nodes."""
        if source_id == target_id:
            return None

        # Verify quote if page text is available
        is_verified = True
        if quote and page_text:
            is_verified = verify_quote_in_page_text(quote, page_text)

        # Check existing edge
        existing = (
            self.db.query(GraphEdge)
            .filter(
                GraphEdge.source_id == source_id,
                GraphEdge.target_id == target_id,
                GraphEdge.relation == relation,
                GraphEdge.document_id == document_id,
            )
            .first()
        )
        if existing:
            return existing

        edge = GraphEdge(
            id=str(uuid.uuid4()),
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            document_id=document_id,
            page_number=page_number,
            quote=quote,
            verified=is_verified,
            properties=properties or {},
            created_at=time.time(),
        )
        self.db.add(edge)
        return edge
