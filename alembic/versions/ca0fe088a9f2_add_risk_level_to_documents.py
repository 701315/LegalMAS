"""add_risk_level_to_documents

Revision ID: ca0fe088a9f2
Revises: a294f1560b77
Create Date: 2026-03-08 09:07:39.012600

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ca0fe088a9f2'
down_revision: Union[str, None] = 'a294f1560b77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'documents',
        sa.Column(
            'risk_level',
            sa.String(20),
            nullable=True,
            comment='Уровень риска: low, medium, high, critical'
        )
    )


def downgrade() -> None:
    op.drop_column('documents', 'risk_level')