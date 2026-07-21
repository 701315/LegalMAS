"""add execution_manifest to runs

Revision ID: 0e7b30fb1e7a
Revises: cdb948125d37
Create Date: 2026-07-20 22:20:08.582947

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0e7b30fb1e7a'
down_revision: Union[str, None] = 'cdb948125d37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "runs",
        sa.Column(
            "execution_manifest",
            postgresql.JSONB(),
            nullable=True,
            comment=(
                "Frozen execution manifest V1: "
                "{schema_version, playbook:{version_id, immutable_content_hash, model_config_id}, "
                "doc_type_instructions:{doc_type:{version_id}}}"
            ),
        ),
    )


def downgrade() -> None:
    op.drop_column("runs", "execution_manifest")

    