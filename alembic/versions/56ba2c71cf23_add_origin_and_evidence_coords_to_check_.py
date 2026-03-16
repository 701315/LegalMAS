"""add origin and evidence coords to check_results

Revision ID: 56ba2c71cf23
Revises: 6dfa359245c9
Create Date: 2026-03-16 07:40:12.502379

"""
from typing import Sequence, Union
from sqlalchemy.dialects import postgresql

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56ba2c71cf23'
down_revision: Union[str, None] = '6dfa359245c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # origin: источник определения проверки
    op.add_column(
        "check_results",
        sa.Column(
            "origin",
            sa.String(length=50),
            nullable=True,
            comment="Source of check definition: global_playbook, document_type_playbook, cross_doc",
        ),
    )

    # page: номер страницы
    op.add_column(
        "check_results",
        sa.Column(
            "page",
            sa.Integer(),
            nullable=True,
            comment="Page number where evidence was found",
        ),
    )

    # clause_uid: идентификатор клаузы/чанка
    op.add_column(
        "check_results",
        sa.Column(
            "clause_uid",
            sa.String(length=200),
            nullable=True,
            comment="Clause UID or chunk identifier within the document",
        ),
    )

    # element_id: ID элемента layout
    op.add_column(
        "check_results",
        sa.Column(
            "element_id",
            sa.String(length=200),
            nullable=True,
            comment="Layout element ID (for precise highlighting in viewer)",
        ),
    )

    # bbox: JSONB с координатами
    op.add_column(
        "check_results",
        sa.Column(
            "bbox",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Bounding box of evidence in document coordinates (for viewer highlight)",
        ),
    )


def downgrade() -> None:
    op.drop_column("check_results", "bbox")
    op.drop_column("check_results", "element_id")
    op.drop_column("check_results", "clause_uid")
    op.drop_column("check_results", "page")
    op.drop_column("check_results", "origin")