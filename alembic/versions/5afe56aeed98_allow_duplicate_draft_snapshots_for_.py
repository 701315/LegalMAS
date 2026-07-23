"""allow duplicate draft snapshots for global instructions

Revision ID: 5afe56aeed98
Revises: c6544493e02d
Create Date: 2026-07-23 16:30:28.066110

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5afe56aeed98'
down_revision: Union[str, None] = 'c6544493e02d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Удаляем старые partial unique indexes, которые запрещали
    # любой duplicate source_sha256 независимо от version_status.
    op.execute(
        "DROP INDEX IF EXISTS uix_global_instruction_versions_platform_sha256"
    )
    op.execute(
        "DROP INDEX IF EXISTS uix_global_instruction_versions_tenant_sha256"
    )

    # Создаём новые partial unique indexes:
    # одинаковый snapshot запрещён только среди non-draft версий
    # (published / archived), но разрешён для draft.
    op.execute(
        """
        CREATE UNIQUE INDEX uix_global_instruction_versions_platform_sha256
        ON global_instruction_versions (instruction_code, source_sha256)
        WHERE owner_scope = 'platform'
          AND version_status IN ('published', 'archived')
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX uix_global_instruction_versions_tenant_sha256
        ON global_instruction_versions (instruction_code, source_sha256, tenant_id)
        WHERE owner_scope = 'tenant'
          AND version_status IN ('published', 'archived')
        """
    )


def downgrade() -> None:
    # Возвращаем старую более жёсткую логику уникальности:
    # duplicate source_sha256 запрещён для всех статусов, включая draft.
    op.execute(
        "DROP INDEX IF EXISTS uix_global_instruction_versions_platform_sha256"
    )
    op.execute(
        "DROP INDEX IF EXISTS uix_global_instruction_versions_tenant_sha256"
    )

    op.execute(
        """
        CREATE UNIQUE INDEX uix_global_instruction_versions_platform_sha256
        ON global_instruction_versions (instruction_code, source_sha256)
        WHERE owner_scope = 'platform'
        """
    )

    op.execute(
        """
        CREATE UNIQUE INDEX uix_global_instruction_versions_tenant_sha256
        ON global_instruction_versions (instruction_code, source_sha256, tenant_id)
        WHERE owner_scope = 'tenant'
        """
    )