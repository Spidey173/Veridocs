"""
Knowledge Graph routes for Veridocs.
Endpoints:
- GET /documents/{document_id}/graph: Returns document knowledge sub-graph with capped node notice
- GET /graph: Returns cross-document knowledge graph querying connections for an entity
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query

import database
from models_db import Document
from graph.builder import KnowledgeGraphBuilder

logger = logging.getLogger(__name__)
router = APIRouter(tags=["graph"])


@router.get("/documents/{document_id}/graph")
@router.get("/api/documents/{document_id}/graph")
async def get_document_graph_endpoint(
    document_id: str, max_nodes: Optional[int] = Query(None, description="Max nodes to render (defaults to 50)")
):
    """
    Retrieve knowledge graph representation of a document:
    Nodes: Party, Organization, Person, Date, MoneyAmount, Clause, Document.
    Edges: PARTY_TO, PAYS, OWES, SIGNED_BY, EFFECTIVE_ON, REFERENCES, AMENDS, MENTIONED_IN.
    """
    with database.get_db() as db:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found.")

        builder = KnowledgeGraphBuilder(db)
        # Fetch existing graph, or build on demand if empty
        graph_data = builder.get_document_graph(document_id, max_nodes=max_nodes)
        if graph_data.get("total_edges", 0) == 0:
            graph_data = builder.build_for_document(document_id)

    return graph_data


@router.get("/graph")
@router.get("/api/graph")
async def search_cross_document_graph_endpoint(
    entity: Optional[str] = Query(None, description="Entity name or keyword to trace connections"),
    max_nodes: Optional[int] = Query(None, description="Max nodes to render (defaults to 50)"),
):
    """
    Cross-document graph discovery: trace relationships, contracts, and obligations
    associated with an entity across all processed documents.
    """
    if not entity or not entity.strip():
        raise HTTPException(status_code=400, detail="Query parameter 'entity' is required.")

    with database.get_db() as db:
        builder = KnowledgeGraphBuilder(db)
        data = builder.search_cross_document_graph(entity.strip(), max_nodes=max_nodes)

    return data
