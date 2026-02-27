"""add default to document_relations id

Revision ID: 5a1bd4eb9ac2
Revises: cf3726abeb23
Create Date: 2026-02-27 22:41:03.934664

"""
from typing import Sequence, Union
from sqlalchemy.dialects.postgresql import UUID

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a1bd4eb9ac2'
down_revision: Union[str, None] = 'cf3726abeb23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "document_relations",
        "id",
        type_=UUID(as_uuid=True),
        existing_type=UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "document_relations",
        "id",
        type_=UUID(as_uuid=True),
        existing_type=UUID(as_uuid=True),
        server_default=None,
        existing_nullable=False,
    )