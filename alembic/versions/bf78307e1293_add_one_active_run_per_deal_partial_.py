"""add one active run per deal partial unique index

Revision ID: bf78307e1293
Revises: e8f9c1a4b2d3
Create Date: 2026-10-26T15:19:28+00:00

Prevents race condition where multiple Runs for the same deal can be
in PENDING or RUNNING state simultaneously. Enables the API layer to
return 409 Conflict on concurrent run start attempts.

R-33 mitigation (defense-in-depth at DB level).

Partial unique index: one active run per deal. Completed / failed /
cancelled / completed_with_errors runs do NOT conflict — users can
start new runs after prior runs finish.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bf78307e1293"
down_revision: Union[str, None] = "e8f9c1a4b2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # Pre-check: fail-fast with actionable message if migration cannot be applied.
    # PostgreSQL would raise a generic "could not create unique index" error,
    # but an explicit message helps ops resolve the offending deals manually.
    duplicates = bind.execute(
        sa.text(
            "SELECT deal_id, COUNT(*) AS cnt FROM runs "
            "WHERE status IN ('pending', 'running') "
            "GROUP BY deal_id HAVING COUNT(*) > 1"
        )
    ).fetchall()

    if duplicates:
        offenders = ", ".join(
            f"deal_id={row[0]} (count={row[1]})" for row in duplicates[:5]
        )
        raise RuntimeError(
            f"Cannot apply migration: {len(duplicates)} deal(s) have 2+ active runs. "
            f"Resolve manually before retry. First offenders: {offenders}. "
            f"Cancel or complete one run per deal to unblock."
        )

    # Partial unique index: one active run per deal.
    # Concurrent PENDING or RUNNING runs for same deal -> IntegrityError.
    # idempotent: if_not_exists=True allows safe re-run on schema_drift recovery.
    op.create_index(
        "uq_runs_one_active_per_deal",
        "runs",
        ["deal_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'running')"),
        if_not_exists=True,
    )


def downgrade() -> None:
    # Drop index only. Does not touch data.
    # After downgrade, concurrent active runs per deal are no longer blocked at DB level.
    op.drop_index(
        "uq_runs_one_active_per_deal",
        table_name="runs",
        if_exists=True,
    )
