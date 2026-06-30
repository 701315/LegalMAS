"""rebuild_deal_members_with_user_fk

Revision ID: d53629bc872c
Revises: 3240cca82e12
Create Date: 2026-06-30 16:01:02.104812

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd53629bc872c'
down_revision: Union[str, None] = '3240cca82e12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Чистый reset таблицы deal_members.

    Почему можно так делать:
    - старые memberships относятся только к тестовым данным;
    - обратная совместимость не требуется;
    - новая модель membership принципиально другая:
      user_id -> FK users.id, без login/name/password.
    """
    op.drop_table("deal_members")

    op.create_table(
        "deal_members",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "deal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "deal_id",
            "user_id",
            name="uq_deal_members_deal_user",
        ),
    )

    op.create_index(
        "ix_deal_members_deal_id",
        "deal_members",
        ["deal_id"],
        unique=False,
    )
    op.create_index(
        "ix_deal_members_user_id",
        "deal_members",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    """
    Восстановление legacy-структуры deal_members.
    Данные membership при downgrade будут потеряны — это допустимо,
    т.к. старая модель несовместима с новой.
    """
    op.drop_index("ix_deal_members_user_id", table_name="deal_members")
    op.drop_index("ix_deal_members_deal_id", table_name="deal_members")
    op.drop_table("deal_members")

    op.create_table(
        "deal_members",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "deal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "name",
            sa.String(length=200),
            nullable=False,
        ),
        sa.Column(
            "login",
            sa.String(length=100),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "deal_id",
            "user_id",
            name="uq_deal_members_deal_user",
        ),
        sa.UniqueConstraint(
            "deal_id",
            "login",
            name="uq_deal_members_deal_login",
        ),
    )

    