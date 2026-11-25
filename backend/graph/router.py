"""
Graph-aware QA query routing and path logging for Veridocs.
Identifies relationship and multi-entity questions (e.g., 'who pays whom?',
'which contracts involve Acme?', 'who signed the agreement?'), retrieves structured
graph facts from PostgreSQL, and blends them into the retrieval context.
"""

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from models_db import Document, GraphNode, GraphEdge

logger = logging.getLogger(__name__)

RELATIONSHIP_PATTERNS = [
    re.compile(r"\bwho\s+pays\s+whom\b", re.IGNORECASE),
    re.compile(r"\bwho\s+signed\b", re.IGNORECASE),
    re.compile(r"\bwho\s+(?:is|are)\s+the\s+parties\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+(?:is|are)\s+the\s+relationship\b", re.IGNORECASE),
    re.compile(r"\bwhich\s+contracts\s+(?:does|do|involve)\b", re.IGNORECASE),
    re.compile(r"\bwho\s+owes\s+whom\b", re.IGNORECASE),
    re.compile(r"\bwho\s+is\s+(?:paying|billing|signing)\b", re.IGNORECASE),
    re.compile(r"\bgoverning\s+law\s+across\b", re.IGNORECASE),
    re.compile(r"\bconnections?\s+between\b", re.IGNORECASE),
]


def is_relationship_query(question: str) -> bool:
    """Returns True if user question inquires about graph relationships between entities."""
    for pat in RELATIONSHIP_PATTERNS:
        if pat.search(question):
            return True
    return False


class GraphQARouter:
    """Routes queries to the knowledge graph first and falls back to chunk retrieval."""

    def __init__(self, db: Session):
        self.db = db

    def route_query(
        self, question: str, session_id: str, active_files: Optional[List[str]] = None
    ) -> Tuple[List[Dict[str, Any]], str]:
        """
        Evaluates question intent:
        - If relationship question: queries graph edges and builds factual graph chunks.
        - Returns (graph_chunks, retrieval_strategy: 'graph' | 'hybrid' | 'vector')
        """
        if not is_relationship_query(question):
            return [], "hybrid"

        logger.info(f"[Graph Router] Detected relationship question: '{question}'")

        # Find document IDs in this session
        doc_query = self.db.query(Document).filter(Document.session_id == session_id)
        if active_files:
            doc_query = doc_query.filter(Document.filename.in_(active_files))
        docs = doc_query.all()
        doc_ids = [d.id for d in docs]
        doc_names = {d.id: d.filename for d in docs}

        if not doc_ids:
            return [], "hybrid"

        # Fetch all edges for these documents
        edges = self.db.query(GraphEdge).filter(GraphEdge.document_id.in_(doc_ids)).all()

        if not edges:
            logger.info("[Graph Router] No graph edges found for session documents; falling back to hybrid.")
            return [], "hybrid"

        # Fetch connected node names
        node_ids = set()
        for e in edges:
            node_ids.add(e.source_id)
            node_ids.add(e.target_id)

        nodes = self.db.query(GraphNode).filter(GraphNode.id.in_(list(node_ids))).all()
        node_map = {n.id: n.name for n in nodes}

        # Convert graph facts into structured context chunks
        graph_chunks = []
        for idx, edge in enumerate(edges):
            src_name = node_map.get(edge.source_id, edge.source_id)
            tgt_name = node_map.get(edge.target_id, edge.target_id)
            fname = doc_names.get(edge.document_id, "document.pdf")
            p_num = edge.page_number or 1

            fact_text = (
                f"[Knowledge Graph Fact] In document '{fname}' (Page {p_num}): "
                f"'{src_name}' has relation {edge.relation} with '{tgt_name}'."
            )
            if edge.quote:
                fact_text += f' Source quote: "{edge.quote}"'

            graph_chunks.append(
                {
                    "id": f"graph_fact_{idx}",
                    "text": fact_text,
                    "content": fact_text,
                    "source_file": fname,
                    "filename": fname,
                    "page": p_num,
                    "page_number": p_num,
                    "chunk_type": "graph",
                    "quote": edge.quote,
                    "score": 1.5,
                }
            )

        logger.info(f"[Graph Router] Successfully extracted {len(graph_chunks)} graph facts for answer context.")
        return graph_chunks, "graph"
