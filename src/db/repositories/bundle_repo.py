# src/db/repositories/bundle_repo.py

"""
BundleRepository — репозиторий для работы с пакетами документов (Bundle).

Назначение:
- Bundle представляет одну операцию импорта/загрузки документов в рамках сделки.
- Позволяет:
  - создать bundle перед началом импорта;
  - увеличивать счётчик файлов по мере загрузки;
  - помечать bundle как завершённый после окончания импорта.

Для чего это нужно:
- фронт и сервисы могут по Bundle понять:
  - от какого источника шла загрузка (local/zip/vdr_api);
  - сколько файлов было в пакете;
  - успешно ли завершился импорт или была ошибка (через status/error_details);
  - когда именно импорт завершился (completed_at).
"""


import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.bundle import Bundle


class BundleRepository:
    """
    Репозиторий для работы с пакетами документов (Bundle).

    Bundle — это одна операция импорта/загрузки документов в рамках сделки.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        deal_id: uuid.UUID,
        source_type: str = "local",
        idempotency_key: str | None = None,
        *,
        status: str = "pending",
        file_count: int = 0,
    ) -> Bundle:
        """
        Создать новый bundle для сделки.

        source_type:
          - 'local'  — ручная загрузка с фронта;
          - 'zip'    — импорт из ZIP-архива;
          - 'vdr_api' — интеграция с VDR и т.п.
        """
        bundle = Bundle(
            deal_id=deal_id,
            source_type=source_type,
            status=status,
            idempotency_key=idempotency_key,
            file_count=file_count,
            completed_at=None,
            error_details=None,
        )
        self.session.add(bundle)
        await self.session.flush()
        return bundle

    async def increment_file_count(self, bundle_id: uuid.UUID, delta: int) -> Bundle | None:
        """
        Увеличить счётчик файлов в bundle на delta.
        """
        stmt = (
            update(Bundle)
            .where(Bundle.id == bundle_id)
            .values(file_count=Bundle.file_count + delta)
            .returning(Bundle)
        )
        result = await self.session.execute(stmt)
        bundle = result.scalar_one_or_none()
        if bundle:
            await self.session.flush()
        return bundle

    async def get_by_id(self, bundle_id: uuid.UUID) -> Bundle | None:
        result = await self.session.execute(
            select(Bundle).where(Bundle.id == bundle_id)
        )
        return result.scalar_one_or_none()


    async def update(
        self,
        bundle_id: uuid.UUID,
        **values,
    ) -> Bundle | None:
        stmt = (
            update(Bundle)
            .where(Bundle.id == bundle_id)
            .values(**values)
            .returning(Bundle)
        )
        result = await self.session.execute(stmt)
        bundle = result.scalar_one_or_none()
        if bundle:
            await self.session.flush()
        return bundle


    async def mark_completed(
        self,
        bundle_id: uuid.UUID,
        *,
        file_count: int | None = None,
    ) -> Bundle | None:
        """
        Пометить bundle как завершённый.
        При необходимости одновременно обновить итоговый file_count.
        """
        values: dict[str, object] = {
            "status": "completed",
            "completed_at": datetime.now(UTC),
        }
        if file_count is not None:
            values["file_count"] = file_count

        return await self.update(bundle_id, **values)

    async def mark_failed(
        self,
        bundle_id: uuid.UUID,
        *,
        error_details: dict,
    ) -> Bundle | None:
        return await self.update(
            bundle_id,
            status="failed",
            error_details=error_details,
            completed_at=datetime.now(UTC),
        )

