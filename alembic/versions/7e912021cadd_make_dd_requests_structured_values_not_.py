"""make dd_requests.structured_values not null

Revision ID: 7e912021cadd
Revises: 81531ca94e53
Create Date: 2026-03-05 15:58:28.932500

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7e912021cadd'
down_revision: Union[str, None] = '81531ca94e53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
