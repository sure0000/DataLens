"""Add knowledge_git_sources.extraction_config for multi-language extraction settings.

Revision ID: a1b2c3d4e5f6
Revises: 93e87c998f74
Create Date: 2026-05-30
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "93e87c998f74"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE knowledge_git_sources ADD COLUMN IF NOT EXISTS extraction_config JSONB;"
    )


def downgrade() -> None:
    op.drop_column("knowledge_git_sources", "extraction_config")
