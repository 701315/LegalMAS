"""drop obsolete global instruction source sha256 indexes

Revision ID: 21e1b267f0e9
Revises: 5afe56aeed98
Create Date: 2026-07-23 16:35:39.999675

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21e1b267f0e9'
down_revision: Union[str, None] = '5afe56aeed98'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Удаляем старые исторические unique indexes, которые запрещали
    # duplicate source_sha256 для всех статусов, включая draft.
    op.execute(
        "DROP INDEX IF EXISTS uix_global_instruction_versions_platform_source_sha256"
    )
    op.execute(
        "DROP INDEX IF EXISTS uix_global_instruction_versions_tenant_source_sha256"
    )


def downgrade() -> None:
    # Возвращаем старые historical indexes при откате.
    op.execute(
        """
        CREATE UNIQUE INDEX uix_global_instruction_versions_platform_source_sha256
        ON global_instruction_versions (instruction_code, source_sha256)
        WHERE owner_scope = 'platform'
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uix_global_instruction_versions_tenant_source_sha256
        ON global_instruction_versions (instruction_code, source_sha256, tenant_id)
        WHERE owner_scope = 'tenant'
        """
    )

    