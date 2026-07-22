"""add processing_error_details to documents

Revision ID: 9cfee2741dc5
Revises: 6dba4c39da0b
Create Date: 2026-03-11 19:40:30.562162

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '9cfee2741dc5'
down_revision: Union[str, None] = '6dba4c39da0b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # IF NOT EXISTS — безопасно при накатке с нуля если initial_schema
    # уже содержит эту колонку
    op.execute("""
        ALTER TABLE documents
        ADD COLUMN IF NOT EXISTS processing_error_details JSONB
    """)


def downgrade() -> None:
    op.drop_column("documents", "processing_error_details")


    