"""initial pgvector schema

Revision ID: 001_initial_pgvector
Revises: 
Create Date: 2026-11-07 21:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision: str = '001_initial_pgvector'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Enable pgvector extension
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # 2. Sessions table
    op.create_table(
        'sessions',
        sa.Column('id', sa.String(length=128), primary_key=True),
        sa.Column('owner_id', sa.String(length=128), nullable=False),
        sa.Column('file_names', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('file_paths', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column('insights', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.Float(precision=53), nullable=False),
        sa.Column('updated_at', sa.Float(precision=53), nullable=False),
    )
    op.create_index('idx_sessions_owner', 'sessions', ['owner_id'])
    op.create_index('idx_sessions_created', 'sessions', ['created_at'])

    # 3. Document chunks table
    op.create_table(
        'document_chunks',
        sa.Column('id', sa.BigInteger(), sa.Identity(always=False), primary_key=True, autoincrement=True),
        sa.Column('session_id', sa.String(length=128), sa.ForeignKey('sessions.id', ondelete='CASCADE'), nullable=True),
        sa.Column('source_file', sa.String(length=255), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
        sa.Column('embedding', Vector(384), nullable=True),
    )

    # Indexes on document_chunks
    op.create_index('idx_chunks_session', 'document_chunks', ['session_id'])
    op.create_index('idx_chunks_source', 'document_chunks', ['session_id', 'source_file'])
    
    # HNSW vector index
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_chunks_hnsw 
    ON document_chunks USING hnsw (embedding vector_cosine_ops)
    """)

    # Full-text search GIN index
    op.execute("""
    CREATE INDEX IF NOT EXISTS idx_chunks_fts 
    ON document_chunks USING gin (to_tsvector('english', text))
    """)

    # 4. Chat messages table
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.String(length=128), primary_key=True),
        sa.Column('session_id', sa.String(length=128), sa.ForeignKey('sessions.id', ondelete='CASCADE'), nullable=True),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.Float(precision=53), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=True),
    )
    op.create_index('idx_messages_session', 'chat_messages', ['session_id', 'created_at'])


def downgrade() -> None:
    op.drop_table('chat_messages')
    op.drop_table('document_chunks')
    op.drop_index('idx_sessions_created', table_name='sessions')
    op.drop_index('idx_sessions_owner', table_name='sessions')
    op.drop_table('sessions')
    op.execute("DROP EXTENSION IF EXISTS vector CASCADE;")
