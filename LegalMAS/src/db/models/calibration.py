"""
ClassificationCalibration model — stores calibration data for confidence scores.
Used to adjust raw classifier confidence to real-world accuracy.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base


class ClassificationCalibration(Base):
    __tablename__ = "classification_calibration"

    doc_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Document type code (e.g. contract_1.6_real_estate)",
    )

    level: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="Classification level: L1, L2, L3, L4",
    )

    raw_confidence_bucket: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Raw confidence bucket (0.0-1.0, step 0.1)",
    )

    calibrated_confidence: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="Calibrated (actual) confidence based on historical data",
    )

    sample_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Number of samples in this bucket",
    )

    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),  # ← Добавлен timezone=True
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "doc_type",
            "level",
            "raw_confidence_bucket",
            name="uq_calibration_type_level_bucket",
        ),
        Index("idx_calibration_lookup", "doc_type", "level", "raw_confidence_bucket"),
    )
