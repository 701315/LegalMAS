"""create document_stage_executions

Revision ID: 6e0203699b46
Revises: f9180764e900
Create Date: 2026-04-15 22:21:01.049380

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '6e0203699b46'
down_revision: Union[str, None] = 'f9180764e900'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_stage_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Run that initiated this stage execution",
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Document to which this stage execution belongs",
        ),
        sa.Column(
            "document_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            comment="Exact document version processed by this stage execution",
        ),
        sa.Column(
            "from_status",
            sa.String(length=50),
            nullable=False,
            comment="Document.status value before this stage execution started",
        ),
        sa.Column(
            "to_status",
            sa.String(length=50),
            nullable=False,
            comment="Target Document.status expected after successful stage completion",
        ),
        sa.Column(
            "orchestration_strategy",
            sa.String(length=64),
            nullable=False,
            comment=(
                "High-level orchestration strategy for this execution attempt "
                "(e.g. V2_ONLY, REUSE_STRUCTURE, FULL_RERUN). "
                "Not the same as DocumentVersion.pipeline_strategy."
            ),
        ),
        sa.Column(
            "task_name",
            sa.String(length=200),
            nullable=False,
            comment="Celery task name that executes this stage",
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default="planned",
            comment=(
                "Lifecycle of this stage execution attempt: "
                "planned / dispatched / started / succeeded / failed / cancelled"
            ),
        ),
        sa.Column(
            "celery_task_id",
            sa.String(length=100),
            nullable=True,
            comment="Celery task id returned by send_task/apply_async if available",
        ),
        sa.Column(
            "error_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment=(
                "Execution error metadata: "
                "{stage, type, reason, message, run_id, timestamp, extra}"
            ),
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when worker actually started execution",
        ),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when execution finished (success/fail/cancel)",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["document_version_id"],
            ["document_versions.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index(
        "idx_document_stage_executions_run_id",
        "document_stage_executions",
        ["run_id"],
        unique=False,
    )

    op.create_index(
        "idx_document_stage_executions_document_id",
        "document_stage_executions",
        ["document_id"],
        unique=False,
    )

    op.create_index(
        "idx_document_stage_executions_document_version_id",
        "document_stage_executions",
        ["document_version_id"],
        unique=False,
    )

    op.create_index(
        "idx_dse_run_created",
        "document_stage_executions",
        ["run_id", "created_at"],
        unique=False,
    )

    op.create_index(
        "idx_dse_docver_created",
        "document_stage_executions",
        ["document_version_id", "created_at"],
        unique=False,
    )

    op.create_index(
        "idx_dse_doc_stage_status",
        "document_stage_executions",
        ["document_id", "to_status", "status"],
        unique=False,
    )

    op.execute(
        """
        CREATE UNIQUE INDEX uq_dse_active_stage
        ON document_stage_executions (document_version_id, to_status, orchestration_strategy)
        WHERE status IN ('planned', 'dispatched', 'started');
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_dse_active_stage")

    op.drop_index("idx_dse_doc_stage_status", table_name="document_stage_executions")
    op.drop_index("idx_dse_docver_created", table_name="document_stage_executions")
    op.drop_index("idx_dse_run_created", table_name="document_stage_executions")
    op.drop_index(
        "idx_document_stage_executions_document_version_id",
        table_name="document_stage_executions",
    )
    op.drop_index(
        "idx_document_stage_executions_document_id",
        table_name="document_stage_executions",
    )
    op.drop_index(
        "idx_document_stage_executions_run_id",
        table_name="document_stage_executions",
    )

    op.drop_table("document_stage_executions")

