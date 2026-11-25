"""Add vision, entities, and structured extraction tables

Revision ID: 002_vision_entities_extractions
Revises: 001_initial_pgvector
Create Date: 2026-11-24 18:00:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "002_vision_entities_extractions"
down_revision: Union[str, None] = "001_initial_pgvector"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add columns to existing tables
    op.add_column("documents", sa.Column("doc_type_confidence", sa.Float(), nullable=True))
    op.add_column("pages", sa.Column("has_signature_block", sa.Boolean(), server_default="false", nullable=True))

    # 2. Create page_vision table
    op.create_table(
        "page_vision",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("image_hash", sa.String(length=64), nullable=True),
        sa.Column("json_data", sa.JSON(), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("cost_tokens", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_page_vision_doc", "page_vision", ["document_id"], unique=False)
    op.create_index("idx_page_vision_hash", "page_vision", ["image_hash"], unique=False)

    # 3. Create entities table
    op.create_table(
        "entities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("chunk_id", sa.String(length=64), nullable=True),
        sa.Column("label", sa.String(length=50), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized", sa.JSON(), nullable=True),
        sa.Column("start_offset", sa.Integer(), nullable=True),
        sa.Column("end_offset", sa.Integer(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True, server_default="1.0"),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_entities_doc", "entities", ["document_id"], unique=False)
    op.create_index("idx_entities_label", "entities", ["label"], unique=False)

    # 4. Create extractions table
    op.create_table(
        "extractions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("schema_type", sa.String(length=50), nullable=False),
        sa.Column("json_data", sa.JSON(), nullable=False),
        sa.Column("verified_ratio", sa.Float(), nullable=True, server_default="0.0"),
        sa.Column("user_edits", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_extractions_doc", "extractions", ["document_id"], unique=False)


def downgrade() -> None:
    op.drop_table("extractions")
    op.drop_table("entities")
    op.drop_table("page_vision")
    op.drop_column("pages", "has_signature_block")
    op.drop_column("documents", "doc_type_confidence")
