# src/db/models/export.py

"""
Export model — tracks generated export files (Excel, Word, PDF).
"""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base


class Export(Base):
    __tablename__ = "exports"

    deal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("deals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("runs.id", ondelete="CASCADE"),
        nullable=False,
    )

    export_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="grid_xlsx, deal_summary_xlsx, report_docx, report_pdf",
    )

    # Основной реф для обратной совместимости (например, dd_grid.xlsx)
    file_ref: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
        comment="Primary file reference (s3://...) for backward compatibility",
    )

    # Набор рефов, если экспорт генерирует несколько файлов
    file_refs: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Optional map of named file references: {name: s3://...}",
    )

    requested_by: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    requester_role: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    file_size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        comment="pending, completed, failed",
    )
