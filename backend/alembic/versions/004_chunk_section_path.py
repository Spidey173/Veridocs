"""Add section_path column to chunks table

Revision ID: 004_chunk_section_path
Revises: 003_comparisons_flags_graphs
Create Date: 2026-11-25 12:00:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "004_chunk_section_path"
down_revision: Union[str, None] = "003_comparisons_flags_graphs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("chunks", sa.Column("section_path", sa.String(length=512), nullable=True))


def downgrade() -> None:
    op.drop_column("chunks", "section_path")
