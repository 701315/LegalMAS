"""merge R-33 index with existing d5c31b8073ba

Revision ID: 175b89560f5f
Revises: bf78307e1293, d5c31b8073ba
Create Date: 2026-10-26 15:22:18.347295

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '175b89560f5f'
down_revision: Union[str, None] = ('bf78307e1293', 'd5c31b8073ba')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
