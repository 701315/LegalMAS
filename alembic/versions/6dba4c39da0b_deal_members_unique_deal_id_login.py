"""deal_members unique deal_id_login

Revision ID: 6dba4c39da0b
Revises: 30190b117152
Create Date: 2026-03-10 19:19:44.511387

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6dba4c39da0b'
down_revision: Union[str, None] = '30190b117152'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Снимаем старый уникальный constraint по login
    op.drop_constraint(
        "uq_deal_members_login",
        "deal_members",
        type_="unique",
    )

    # Добавляем новый уникальный constraint по (deal_id, login)
    op.create_unique_constraint(
        "uq_deal_members_deal_login",
        "deal_members",
        ["deal_id", "login"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_deal_members_deal_login",
        "deal_members",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_deal_members_login",
        "deal_members",
        ["login"],
    )