"""add dd_requests table

Revision ID: 81531ca94e53
Revises: c4fa323362ba
Create Date: 2026-03-05 15:12:20.380262

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql



# revision identifiers, used by Alembic.
revision: str = '81531ca94e53'
down_revision: Union[str, None] = 'c4fa323362ba'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "dd_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("deal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=True),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("check_id", sa.String(length=100), nullable=True),
        sa.Column("addressee", sa.String(length=255), nullable=False, server_default="Юридический советник"),
        sa.Column("structured_values", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="manual"),
        sa.Column("document_refs", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("evidence_refs", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["deal_id"], ["deals.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_dd_requests_deal_id", "dd_requests", ["deal_id"])


def downgrade() -> None:
    op.drop_index("ix_dd_requests_deal_id", table_name="dd_requests")
    op.drop_table("dd_requests")