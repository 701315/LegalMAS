"""extend document_family_members with id and timestamps

Revision ID: 87fd971b1eb4
Revises: 97dfb4f0db7a
Create Date: 2026-02-27 23:19:24.519730

"""
from typing import Sequence, Union
from sqlalchemy.dialects import postgresql
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '87fd971b1eb4'
down_revision: Union[str, None] = '97dfb4f0db7a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Добавляем surrogate id
    op.add_column(
        "document_family_members",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
    )

    # Добавляем timestamps
    op.add_column(
        "document_family_members",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.add_column(
        "document_family_members",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # Делаем id PK, а старый составной PK превращаем в UNIQUE
    op.create_unique_constraint(
        "uq_document_family_members_family_doc",
        "document_family_members",
        ["family_id", "doc_id"],
    )
    op.drop_constraint("document_family_members_pkey", "document_family_members", type_="primary")
    op.create_primary_key(
        "pk_document_family_members",
        "document_family_members",
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("pk_document_family_members", "document_family_members", type_="primary")
    op.create_primary_key(
        "document_family_members_pkey",
        "document_family_members",
        ["family_id", "doc_id"],
    )
    op.drop_constraint("uq_document_family_members_family_doc", "document_family_members", type_="unique")
    op.drop_column("document_family_members", "updated_at")
    op.drop_column("document_family_members", "created_at")
    op.drop_column("document_family_members", "id")