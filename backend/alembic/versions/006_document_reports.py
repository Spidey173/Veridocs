"""Add document_reports table

Revision ID: 006_document_reports
Revises: 005_document_summaries
Create Date: 2026-11-25 14:00:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "006_document_reports"
down_revision: Union[str, None] = "005_document_summaries"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("report", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=True),
        sa.Column("updated_at", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", name="uq_document_reports_doc_id"),
    )
    op.create_index("idx_document_reports_doc", "document_reports", ["document_id"], unique=True)


def downgrade() -> None:
    op.drop_table("document_reports")
