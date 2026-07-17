# src/db/repositories/calibration_repo.py

"""
Repository for ClassificationCalibration operations.
"""

from datetime import UTC, datetime

from sqlalchemy import Float, cast, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.calibration import ClassificationCalibration


class CalibrationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_calibration(
        self,
        doc_type: str,
        level: str,
        bucket: float,
    ) -> ClassificationCalibration | None:
        """Get calibration data for a specific bucket."""
        result = await self.session.execute(
            select(ClassificationCalibration).where(
                ClassificationCalibration.doc_type == doc_type,
                ClassificationCalibration.level == level,
                ClassificationCalibration.raw_confidence_bucket == bucket,
            )
        )
        return result.scalar_one_or_none()

    async def update_calibration(
        self,
        doc_type: str,
        level: str,
        bucket: float,
        correct: bool,
    ) -> None:
        """
        Atomically upsert calibration running average.

        Concurrency safety:
        - first sample inserts a new row;
        - subsequent samples use PostgreSQL ON CONFLICT DO UPDATE;
        - sample_count increments in the database atomically;
        - calibrated_confidence is recalculated from the persisted aggregate
          and the incoming sample in one SQL statement.

        This removes both:
        - lost update in read-modify-write flows;
        - insert race when two writers create the same bucket simultaneously.
        """
        sample_value = 1.0 if correct else 0.0
        now = datetime.now(UTC)

        table = ClassificationCalibration.__table__

        insert_stmt = insert(table).values(
            doc_type=doc_type,
            level=level,
            raw_confidence_bucket=bucket,
            calibrated_confidence=sample_value,
            sample_count=1,
            last_updated=now,
        )

        existing_count = table.c.sample_count
        existing_avg = table.c.calibrated_confidence
        incoming_value = insert_stmt.excluded.calibrated_confidence

        updated_avg = (
            (existing_avg * cast(existing_count, Float()) + incoming_value)
            / cast(existing_count + 1, Float())
        )

        stmt = insert_stmt.on_conflict_do_update(
            index_elements=[
                table.c.doc_type,
                table.c.level,
                table.c.raw_confidence_bucket,
            ],
            set_={
                "calibrated_confidence": updated_avg,
                "sample_count": existing_count + 1,
                "last_updated": now,
            },
        )

        await self.session.execute(stmt)
        await self.session.flush()


        
