"""
Repository for ClassificationCalibration operations.
"""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.calibration import ClassificationCalibration


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
        Update calibration running average.
        Called after QC or golden dataset validation.
        """
        existing = await self.get_calibration(doc_type, level, bucket)

        if existing is None:
            # Create new calibration record
            calibration = ClassificationCalibration(
                doc_type=doc_type,
                level=level,
                raw_confidence_bucket=bucket,
                calibrated_confidence=1.0 if correct else 0.0,
                sample_count=1,
                last_updated=datetime.now(UTC),
            )
            self.session.add(calibration)
        else:
            # Update running average
            n = existing.sample_count
            new_value = 1.0 if correct else 0.0
            new_avg = (existing.calibrated_confidence * n + new_value) / (n + 1)

            stmt = (
                update(ClassificationCalibration)
                .where(ClassificationCalibration.id == existing.id)
                .values(
                    calibrated_confidence=new_avg,
                    sample_count=n + 1,
                    last_updated=datetime.now(UTC),
                )
            )
            await self.session.execute(stmt)

        await self.session.flush()
