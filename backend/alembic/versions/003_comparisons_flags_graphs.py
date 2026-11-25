"""Add clauses, comparisons, flags, graph_nodes, and graph_edges tables

Revision ID: 003_comparisons_flags_graphs
Revises: 002_vision_entities_extractions
Create Date: 2026-11-25 00:00:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

try:
    from pgvector.sqlalchemy import Vector

    HAS_PGVECTOR = True
except ImportError:
    Vector = None
    HAS_PGVECTOR = False

revision: str = "003_comparisons_flags_graphs"
down_revision: Union[str, None] = "002_vision_entities_extractions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create clauses table
    clause_columns = [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("clause_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("number", sa.String(length=50), nullable=True),
        sa.Column("heading", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("page_end", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.Float(), nullable=True),
    ]
    if HAS_PGVECTOR and Vector is not None:
        clause_columns.append(sa.Column("embedding", Vector(384), nullable=True))
    else:
        clause_columns.append(sa.Column("embedding", sa.LargeBinary(), nullable=True))

    op.create_table(
        "clauses",
        *clause_columns,
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_clauses_doc", "clauses", ["document_id"], unique=False)
    op.create_index("idx_clauses_doc_idx", "clauses", ["document_id", "clause_index"], unique=False)

    # 2. Create comparisons table
    op.create_table(
        "comparisons",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("doc_a", sa.String(length=36), nullable=False),
        sa.Column("doc_b", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="queued"),
        sa.Column("json", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["doc_a"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["doc_b"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_comparisons_doc_a", "comparisons", ["doc_a"], unique=False)
    op.create_index("idx_comparisons_doc_b", "comparisons", ["doc_b"], unique=False)

    # 3. Create flags table
    op.create_table(
        "flags",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("rule_id", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True, server_default="1.0"),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_flags_doc", "flags", ["document_id"], unique=False)
    op.create_index("idx_flags_rule", "flags", ["rule_id"], unique=False)

    # 4. Create graph_nodes table
    op.create_table(
        "graph_nodes",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("label", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("canonical_name", sa.String(length=255), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=True),
        sa.Column("properties", sa.JSON(), nullable=True),
        sa.Column("document_ids", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_graph_nodes_label", "graph_nodes", ["label"], unique=False)
    op.create_index("idx_graph_nodes_canonical", "graph_nodes", ["canonical_name"], unique=False)

    # 5. Create graph_edges table
    op.create_table(
        "graph_edges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("target_id", sa.String(length=128), nullable=False),
        sa.Column("relation", sa.String(length=50), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("quote", sa.Text(), nullable=True),
        sa.Column("verified", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("properties", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["graph_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_id"], ["graph_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_graph_edges_src", "graph_edges", ["source_id"], unique=False)
    op.create_index("idx_graph_edges_tgt", "graph_edges", ["target_id"], unique=False)
    op.create_index("idx_graph_edges_rel", "graph_edges", ["relation"], unique=False)
    op.create_index("idx_graph_edges_doc", "graph_edges", ["document_id"], unique=False)


def downgrade() -> None:
    op.drop_table("graph_edges")
    op.drop_table("graph_nodes")
    op.drop_table("flags")
    op.drop_table("comparisons")
    op.drop_table("clauses")
