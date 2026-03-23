# src/db/repositories/deal_repo.py


"""
Репозиторий для CRUD‑операций со сделками (Deal).

Это тонкая обёртка над SQLAlchemy ORM:
- никакой бизнес‑логики;
- только чтение/запись/поиск сделок в БД;
- все операции выполняются через переданную AsyncSession.
"""

import uuid

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.deal import Deal


class DealRepository:
    """
    Класс-репозиторий для работы со сделками.

    Экземпляр живёт внутри одного запроса / юнита работы и использует
    уже созданную AsyncSession — сам сессию не открывает и не закрывает.
    """

    def __init__(self, session: AsyncSession):
        """
        Инициализировать репозиторий.

        Параметры:
        - session: активная AsyncSession, через которую будут выполняться запросы.
        """
        self.session = session

    async def create(
        self,
        tenant_id: uuid.UUID,
        name: str,
        deal_type: str | None = None,
        jurisdiction: str | None = None,
        languages: list[str] | None = None,
        pii_mode: str = "local_only",
        profile: str = "full",
        playbook_version_id: uuid.UUID | None = None,
        metadata_: dict | None = None,
    ) -> Deal:
        """
        Создать новую сделку и сохранить её в БД.

        Параметры:
        - tenant_id: идентификатор арендатора, к которому относится сделка;
        - name: человекочитаемое название сделки;
        - deal_type: тип сделки (опционально, для фильтрации и плейбуков);
        - jurisdiction: юрисдикция сделки;
        - languages: список языков документов по сделке;
        - pii_mode: режим работы с PII (по умолчанию 'local_only');
        - profile: профиль анализа (например, 'full'/'light');
        - playbook_version_id: ID версии плейбука, к которой привязана сделка;
        - metadata_: произвольный JSON с дополнительными метаданными.

        Возвращает:
        - созданный объект Deal (уже с заполненным id).
        """
        deal = Deal(
            tenant_id=tenant_id,
            name=name,
            deal_type=deal_type,
            jurisdiction=jurisdiction,
            languages=languages,
            pii_mode=pii_mode,
            profile=profile,
            playbook_version_id=playbook_version_id,
            metadata_=metadata_ or {},
        )
        self.session.add(deal)
        await self.session.flush()
        return deal

    async def get_by_id(self, deal_id: uuid.UUID) -> Deal | None:
        """
        Найти сделку по её ID.

        Параметры:
        - deal_id: идентификатор сделки.

        Возвращает:
        - объект Deal, если найден;
        - None, если сделки с таким ID нет.
        """
        result = await self.session.execute(select(Deal).where(Deal.id == deal_id))
        return result.scalar_one_or_none()

    async def get_by_tenant(
        self,
        tenant_id: uuid.UUID,
        status: str | None = None,
    ) -> list[Deal]:
        """
        Вернуть список сделок для указанного арендатора.

        Параметры:
        - tenant_id: идентификатор арендатора;
        - status: опциональный фильтр по статусу сделки.

        Возвращает:
        - список объектов Deal, отсортированный по дате создания (новые сверху).
        """
        stmt = select(Deal).where(Deal.tenant_id == tenant_id)
        if status is not None:
            stmt = stmt.where(Deal.status == status)
        stmt = stmt.order_by(Deal.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all(self) -> list[Deal]:
        """
        Вернуть все сделки в системе.

        Используется в dev‑режиме и админских сценариях, где нужно увидеть
        полный список сделок без фильтров.
        """
        stmt = select(Deal).order_by(Deal.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(self, deal_id: uuid.UUID, status: str) -> Deal | None:
        """
        Обновить статус сделки.

        Параметры:
        - deal_id: идентификатор сделки;
        - status: новый статус (строковое значение, например 'active', 'archived').

        Возвращает:
        - обновлённый объект Deal;
        - None, если сделки с таким ID не найдено.
        """
        stmt = (
            update(Deal)
            .where(Deal.id == deal_id)
            .values(status=status)
            .returning(Deal)
        )
        result = await self.session.execute(stmt)
        deal = result.scalar_one_or_none()
        if deal:
            await self.session.flush()
        return deal

    async def get_page(
        self,
        page: int,
        per_page: int,
        status: str | None = None,
        tenant_id: uuid.UUID | None = None,
    ) -> tuple[list[Deal], int]:
        """
        Вернуть одну страницу сделок с учётом фильтров и общее количество записей.

        Параметры:
        - page: номер страницы (начиная с 1);
        - per_page: размер страницы (количество сделок на странице);
        - status: опциональный фильтр по статусу сделки;
        - tenant_id: опциональный фильтр по арендатору.

        Возвращает кортеж:
        - список сделок на запрошенной странице;
        - общее количество сделок, подходящих под фильтры (для расчёта пагинации).
        """
        offset = (page - 1) * per_page

        filters = []
        if status is not None:
            filters.append(Deal.status == status)
        if tenant_id is not None:
            filters.append(Deal.tenant_id == tenant_id)

        # 1) считаем total с учётом фильтров
        count_stmt = select(func.count(Deal.id))
        if filters:
            count_stmt = count_stmt.where(*filters)

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one() or 0

        if total == 0:
            return [], 0

        # 2) выбираем записи страницы
        stmt = (
            select(Deal)
            .where(*filters)
            .order_by(Deal.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def set_last_run_id(
        self,
        deal_id: uuid.UUID,
        run_id: uuid.UUID | None,
        checks_mode: str | None = None,
        pipeline_strategy: str | None = None,
    ) -> None:
        """
        Обновить у сделки ссылку на последний Run и его параметры.

        Обновляет в таблице Deal:
        - last_run_id                 — идентификатор последнего Run;
        - last_run_checks_mode        — режим проверок последнего Run (если передан);
        - last_run_pipeline_strategy  — стратегию пайплайна последнего Run (если передана).

        Эти поля используются в UI и отчётах, чтобы быстро показать,
        в каком режиме и с какой стратегией был выполнен последний анализ сделки.
        """
        values: dict[str, object] = {"last_run_id": run_id}
        if checks_mode is not None:
            values["last_run_checks_mode"] = checks_mode
        if pipeline_strategy is not None:
            values["last_run_pipeline_strategy"] = pipeline_strategy

        stmt = (
            update(Deal)
            .where(Deal.id == deal_id)
            .values(**values)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def set_has_pending_manual_reclassifications(
        self,
        deal_id: uuid.UUID,
        value: bool,
    ) -> None:
        """
        Обновить флаг has_pending_manual_reclassifications у сделки.

        Этот флаг показывает, есть ли незакрытые ручные переклассификации
        документов по сделке, которые ещё не были учтены в новом анализе.
        """
        stmt = (
            update(Deal)
            .where(Deal.id == deal_id)
            .values(has_pending_manual_reclassifications=value)
        )
        await self.session.execute(stmt)
        await self.session.flush()
