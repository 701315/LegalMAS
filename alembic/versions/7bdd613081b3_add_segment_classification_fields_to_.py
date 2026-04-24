"""add segment classification fields to document_segments

Revision ID: 7bdd613081b3
Revises: 0651f2019eb2
Create Date: 2026-04-22 16:17:22.063943

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '7bdd613081b3'
down_revision: Union[str, None] = '0651f2019eb2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.add_column(
        "document_segments",
        sa.Column(
            "segment_doc_type",
            sa.String(length=100),
            nullable=True,
            comment=(
                "Итоговый type_code для этого сегмента, определённый "
                "segment-level классификатором."
            ),
        ),
    )

    op.add_column(
        "document_segments",
        sa.Column(
            "segment_classification_confidence",
            sa.Float(),
            nullable=True,
            comment="Итоговая уверенность классификации сегмента 0.0-1.0.",
        ),
    )

    op.add_column(
        "document_segments",
        sa.Column(
            "segment_classification_level",
            sa.String(length=20),
            nullable=True,
            comment=(
                "Уровень, который дал финальное решение по сегменту: "
                "L3, L4, HYBRID, COPIED и т.п."
            ),
        ),
    )

    op.add_column(
        "document_segments",
        sa.Column(
            "segment_confidence_zone",
            sa.String(length=20),
            nullable=True,
            comment=(
                "Зона уверенности segment-level классификации: "
                "high / medium / low / unknown."
            ),
        ),
    )

    op.add_column(
        "document_segments",
        sa.Column(
            "segment_applicable_triggers",
            postgresql.ARRAY(sa.String(length=100)),
            nullable=True,
            comment=(
                "Список триггеров/условий, применимых к данному сегменту "
                "по результату классификации."
            ),
        ),
    )

    op.add_column(
        "document_segments",
        sa.Column(
            "segment_classification_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Полный JSON payload segment-level классификации: "
                "levels_tried, candidates, confidence_zone, requires_manual_review и т.д."
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("document_segments", "segment_classification_details")
    op.drop_column("document_segments", "segment_applicable_triggers")
    op.drop_column("document_segments", "segment_confidence_zone")
    op.drop_column("document_segments", "segment_classification_level")
    op.drop_column("document_segments", "segment_classification_confidence")
    op.drop_column("document_segments", "segment_doc_type")

    