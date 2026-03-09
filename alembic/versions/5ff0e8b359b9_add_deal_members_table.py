"""add deal_members table

Revision ID: 5ff0e8b359b9
Revises: ca0fe088a9f2
Create Date: 2026-03-09 21:56:21.335026

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '5ff0e8b359b9'
down_revision: Union[str, None] = 'ca0fe088a9f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        "deal_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("login", sa.String(length=100), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
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

    op.create_unique_constraint(
        "uq_deal_members_deal_user",
        "deal_members",
        ["deal_id", "user_id"],
    )
    op.create_unique_constraint(
        "uq_deal_members_login",
        "deal_members",
        ["login"],
    )

    op.create_foreign_key(
        "fk_deal_members_deal_id_deals",
        "deal_members",
        "deals",
        ["deal_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint("fk_deal_members_deal_id_deals", "deal_members", type_="foreignkey")
    op.drop_constraint("uq_deal_members_login", "deal_members", type_="unique")
    op.drop_constraint("uq_deal_members_deal_user", "deal_members", type_="unique")
    op.drop_index("ix_deal_members_user_id", table_name="deal_members")
    op.drop_index("ix_deal_members_deal_id", table_name="deal_members")
    op.drop_table("deal_members")
