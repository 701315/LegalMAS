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
from datetime import datetime

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
            status="pending",
            idempotency_key=idempotency_key,
            file_count=0,
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

    async def mark_completed(self, bundle_id: uuid.UUID) -> Bundle | None:
        """
        Пометить bundle как завершённый (status='completed', completed_at=now()).
        """
        stmt = (
            update(Bundle)
            .where(Bundle.id == bundle_id)
            .values(
                status="completed",
                completed_at=datetime.utcnow(),
            )
            .returning(Bundle)
        )
        result = await self.session.execute(stmt)
        bundle = result.scalar_one_or_none()
        if bundle:
            await self.session.flush()
        return bundle
