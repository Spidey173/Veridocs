"""Add query_log table for analytics

Revision ID: 007_query_log
Revises: 006_document_reports
Create Date: 2026-11-25 15:00:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "007_query_log"
down_revision: Union[str, None] = "006_document_reports"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "query_log",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("session_id", sa.String(length=64), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("retrieval_strategy", sa.String(length=50), nullable=True),
        sa.Column("citation_score", sa.Float(), nullable=True),
        sa.Column("total_claims", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("supported_claims", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_query_log_session", "query_log", ["session_id"], unique=False)
    op.create_index("idx_query_log_created", "query_log", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_table("query_log")
