"""Add performance indexes on documents.status, chunks.filename, and chunks(session_id, filename)

Revision ID: 008_add_perf_indexes
Revises: 007_query_log
Create Date: 2026-11-25 18:30:00.000000

"""

from typing import Sequence, Union
from alembic import op

revision: str = "008_add_perf_indexes"
down_revision: Union[str, None] = "007_query_log"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_documents_status", "documents", ["status"], unique=False)
    op.create_index("ix_chunks_filename", "chunks", ["filename"], unique=False)
    op.create_index("ix_chunks_session_filename", "chunks", ["session_id", "filename"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_chunks_session_filename", table_name="chunks")
    op.drop_index("ix_chunks_filename", table_name="chunks")
    op.drop_index("ix_documents_status", table_name="documents")
