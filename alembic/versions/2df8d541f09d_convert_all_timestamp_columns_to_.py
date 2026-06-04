"""convert all timestamp columns to timestamptz

Revision ID: 2df8d541f09d
Revises: a8dade36df13
Create Date: 2026-06-03 19:00:34.548324

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2df8d541f09d'
down_revision: Union[str, None] = 'a8dade36df13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE dd_requests
            ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC',
            ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING updated_at AT TIME ZONE 'UTC'
    """)

    op.execute("""
        ALTER TABLE deal_members
            ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC'
    """)

    op.execute("""
        ALTER TABLE document_stage_executions
            ALTER COLUMN started_at  TYPE TIMESTAMPTZ USING started_at  AT TIME ZONE 'UTC',
            ALTER COLUMN finished_at TYPE TIMESTAMPTZ USING finished_at AT TIME ZONE 'UTC'
    """)

    op.execute("""
        ALTER TABLE jobs
            ALTER COLUMN started_at  TYPE TIMESTAMPTZ USING started_at  AT TIME ZONE 'UTC',
            ALTER COLUMN finished_at TYPE TIMESTAMPTZ USING finished_at AT TIME ZONE 'UTC'
    """)

    op.execute("""
        ALTER TABLE runs
            ALTER COLUMN started_at   TYPE TIMESTAMPTZ USING started_at   AT TIME ZONE 'UTC',
            ALTER COLUMN completed_at TYPE TIMESTAMPTZ USING completed_at AT TIME ZONE 'UTC'
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE runs
            ALTER COLUMN started_at   TYPE TIMESTAMP USING started_at   AT TIME ZONE 'UTC',
            ALTER COLUMN completed_at TYPE TIMESTAMP USING completed_at AT TIME ZONE 'UTC'
    """)

    op.execute("""
        ALTER TABLE jobs
            ALTER COLUMN started_at  TYPE TIMESTAMP USING started_at  AT TIME ZONE 'UTC',
            ALTER COLUMN finished_at TYPE TIMESTAMP USING finished_at AT TIME ZONE 'UTC'
    """)

    op.execute("""
        ALTER TABLE document_stage_executions
            ALTER COLUMN started_at  TYPE TIMESTAMP USING started_at  AT TIME ZONE 'UTC',
            ALTER COLUMN finished_at TYPE TIMESTAMP USING finished_at AT TIME ZONE 'UTC'
    """)

    op.execute("""
        ALTER TABLE deal_members
            ALTER COLUMN created_at TYPE TIMESTAMP USING created_at AT TIME ZONE 'UTC'
    """)

    op.execute("""
        ALTER TABLE dd_requests
            ALTER COLUMN created_at TYPE TIMESTAMP USING created_at AT TIME ZONE 'UTC',
            ALTER COLUMN updated_at TYPE TIMESTAMP USING updated_at AT TIME ZONE 'UTC'
    """)

    