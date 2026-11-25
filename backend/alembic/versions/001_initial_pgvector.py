"""Initial migration for Veridocs: documents, pages, chunks (pgvector + GIN), tables, sessions, messages

Revision ID: 001_initial_pgvector
Revises:
Create Date: 2026-11-24 12:00:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial_pgvector"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    # 1. Enable pgvector extension on PostgreSQL
    if is_postgres:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # 2. Create documents table
    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("doc_type", sa.String(length=50), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_documents_session", "documents", ["session_id"], unique=False)

    # 3. Create pages table
    op.create_table(
        "pages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("extraction_method", sa.String(length=50), nullable=False),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
        sa.Column("has_figures", sa.Boolean(), nullable=True),
        sa.Column("has_tables", sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_pages_document_page", "pages", ["document_id", "page_number"], unique=False)

    # 4. Create chunks table
    chunks_cols = [
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("chunk_type", sa.String(length=50), nullable=False, server_default="text"),
    ]

    if is_postgres:
        op.create_table(
            "chunks",
            *chunks_cols,
            sa.Column("embedding", postgresql.BYTEA(), nullable=True),  # Altered to vector below
            sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        # Convert embedding column to pgvector vector(384)
        op.execute("ALTER TABLE chunks ALTER COLUMN embedding TYPE vector(384) USING embedding::vector;")
        # HNSW Index for Cosine Similarity
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw "
            "ON chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);"
        )
        # GIN Index for Full-Text Search
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_chunks_content_gin ON chunks USING gin (to_tsvector('english', content));"
        )
    else:
        op.create_table(
            "chunks",
            *chunks_cols,
            sa.Column("embedding", sa.LargeBinary(), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )

    op.create_index("idx_chunks_document", "chunks", ["document_id"], unique=False)
    op.create_index("idx_chunks_session", "chunks", ["session_id"], unique=False)

    # 5. Create tables table
    op.create_table(
        "tables",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("markdown", sa.Text(), nullable=False),
        sa.Column("json", postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(), nullable=False),
        sa.Column("bbox", postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_tables_document_page", "tables", ["document_id", "page_number"], unique=False)

    # 6. Create sessions table
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.Column("file_names", postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(), nullable=True),
        sa.Column(
            "suggested_questions", postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(), nullable=True
        ),
        sa.PrimaryKeyConstraint("session_id"),
    )

    # 7. Create messages table
    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(), nullable=True),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(), nullable=True),
        sa.Column(
            "citation_check", postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(), nullable=True
        ),
        sa.Column("timestamp", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.session_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_messages_session", "messages", ["session_id"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    op.drop_table("messages")
    op.drop_table("sessions")
    op.drop_table("tables")
    if is_postgres:
        op.execute("DROP INDEX IF EXISTS idx_chunks_content_gin;")
        op.execute("DROP INDEX IF EXISTS idx_chunks_embedding_hnsw;")
    op.drop_table("chunks")
    op.drop_table("pages")
    op.drop_table("documents")
