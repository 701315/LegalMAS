# src/db/repositories/deal_repo.py

"""
Репозиторий для CRUD‑операций со сделками (Deal) с принудительной изоляцией тенантов.

Принцип Hardening:
- Все публичные методы чтения и записи ТРЕБУЮТ tenant_id.
- База данных фильтрует данные на уровне SQL WHERE clause.
- Методы без фильтрации помечены как unsafe_ и используются только во внутренних воркерах.
"""

import uuid
from typing import Sequence

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import PermanentError
from ..models.deal import Deal


class DealRepository:
    def __init__(self, session: AsyncSession):
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
        summary: str | None = None,
    ) -> Deal:
        """Создать новую сделку."""
        deal = Deal(
            tenant_id=tenant_id,
            name=name.strip(),
            summary=summary,
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

    async def exists_by_name(
        self,
        tenant_id: uuid.UUID,
        name: str,
    ) -> bool:
        normalized_name = name.strip()
        if not normalized_name:
            return False

        stmt = (
            select(Deal.id)
            .where(
                Deal.tenant_id == tenant_id,
                func.lower(func.btrim(Deal.name)) == normalized_name.lower(),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_by_id(self, deal_id: uuid.UUID, tenant_id: uuid.UUID) -> Deal | None:
        """
        Найти сделку строго в рамках тенанта.
        СИСТЕМНЫЙ ФИКС: Добавлен обязательный tenant_id.
        """
        stmt = select(Deal).where(
            Deal.id == deal_id,
            Deal.tenant_id == tenant_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def assert_tenant_owns_deal(
        self,
        deal_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Deal:
        """
        Жёстко проверить, что сделка существует и принадлежит указанному tenant.

        Используется во внутренних use case / worker orchestration слоях,
        где отсутствие доступа к сделке является terminal business error,
        а не HTTP-level 404/403.

        Args:
            deal_id: Идентификатор сделки.
            tenant_id: Идентификатор tenant'а, в рамках которого разрешён доступ.

        Returns:
            Deal: найденная scoped-сделка.

        Raises:
            PermanentError:
                если сделка не существует в рамках tenant'а.
        """
        deal = await self.get_by_id(deal_id, tenant_id)
        if deal is None:
            raise PermanentError(
                "Deal not found or does not belong to tenant",
                details={
                    "deal_id": str(deal_id),
                    "tenant_id": str(tenant_id),
                },
            )
        return deal

    async def get_by_tenant(self, tenant_id: uuid.UUID) -> list[Deal]:
        """
        Вернуть все сделки указанного тенанта.
        Используется для tenant_admin роли.
        """
        stmt = (
            select(Deal)
            .where(Deal.tenant_id == tenant_id)
            .order_by(Deal.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def internal_unsafe_get_by_id(self, deal_id: uuid.UUID) -> Deal | None:
        """
        Найти сделку без проверки тенанта.
        ИСПОЛЬЗОВАТЬ ТОЛЬКО ВО ВНУТРЕННИХ ВОРКЕРАХ ИЛИ ОРКЕСТРАТОРЕ.
        """
        result = await self.session.execute(select(Deal).where(Deal.id == deal_id))
        return result.scalar_one_or_none()

    async def get_page(
        self,
        page: int,
        per_page: int,
        tenant_id: uuid.UUID,
        status: str | None = None,
    ) -> tuple[Sequence[Deal], int]:
        """
        Вернуть страницу сделок строго для указанного тенанта.
        СИСТЕМНЫЙ ФИКС: tenant_id теперь обязателен.
        """
        offset = (page - 1) * per_page
        filters = [Deal.tenant_id == tenant_id]

        if status is not None:
            filters.append(Deal.status == status)

        # 1) Считаем total
        count_stmt = select(func.count(Deal.id)).where(*filters)
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one() or 0

        if total == 0:
            return [], 0

        # 2) Выбираем данные
        stmt = (
            select(Deal)
            .where(*filters)
            .order_by(Deal.created_at.desc())
            .offset(offset)
            .limit(per_page)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all(), total

    async def unsafe_get_all_platform_admin_only(self) -> list[Deal]:
        """Вернуть все сделки системы. Только для глобальных админов."""
        stmt = select(Deal).order_by(Deal.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # --- Секция обновлений с защитой тенанта ---

    async def update_status(
        self,
        deal_id: uuid.UUID,
        tenant_id: uuid.UUID,
        status: str,
    ) -> Deal | None:
        """Обновить статус сделки с проверкой владения."""
        stmt = (
            update(Deal)
            .where(Deal.id == deal_id, Deal.tenant_id == tenant_id)
            .values(status=status)
            .returning(Deal)
        )
        result = await self.session.execute(stmt)
        deal = result.scalar_one_or_none()
        if deal:
            await self.session.flush()
        return deal

    async def update_summary(
        self,
        deal_id: uuid.UUID,
        tenant_id: uuid.UUID,
        summary: str | None,
    ) -> Deal | None:
        """Обновить резюме сделки с проверкой владения."""
        normalized = summary.strip() if summary else None
        stmt = (
            update(Deal)
            .where(Deal.id == deal_id, Deal.tenant_id == tenant_id)
            .values(summary=normalized)
            .returning(Deal)
        )
        result = await self.session.execute(stmt)
        deal = result.scalar_one_or_none()
        if deal:
            await self.session.flush()
        return deal

    async def update_languages(
        self,
        deal_id: uuid.UUID,
        tenant_id: uuid.UUID,
        languages: list[str],
    ) -> None:
        """Обновить языки сделки с проверкой владения."""
        stmt = (
            update(Deal)
            .where(Deal.id == deal_id, Deal.tenant_id == tenant_id)
            .values(languages=languages)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def update_primary_language(
        self,
        deal_id: uuid.UUID,
        tenant_id: uuid.UUID,
        primary_language: str | None,
    ) -> None:
        """Обновить основной язык сделки с проверкой владения."""
        stmt = (
            update(Deal)
            .where(Deal.id == deal_id, Deal.tenant_id == tenant_id)
            .values(primary_language=primary_language)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    # --- Системные методы (используются воркерами, могут быть unscoped) ---

    async def update_language_discovery_status(
        self,
        deal_id: uuid.UUID,
        status: str,
    ) -> Deal | None:
        """
        Обновить deal-level статус pre-run language discovery.

        Системный метод: используется только внутренними воркерами /
        orchestrator-слоем, поэтому tenant_id здесь не требуется.

        Допустимые значения status:
        - pending
        - processing
        - completed
        - partial
        - failed
        """
        stmt = (
            update(Deal)
            .where(Deal.id == deal_id)
            .values(language_discovery_status=status)
            .returning(Deal)
        )
        result = await self.session.execute(stmt)
        deal = result.scalar_one_or_none()
        if deal:
            await self.session.flush()
        return deal

    async def set_languages_and_discovery_status(
        self,
        deal_id: uuid.UUID,
        languages: list[str] | None,
        discovery_status: str,
    ) -> Deal | None:
        """
        Атомарно обновить deal-level languages и language_discovery_status.

        Системный метод: используется внутренними сервисами/воркерами
        при recompute агрегированного состояния language discovery по сделке.

        Args:
            deal_id: Идентификатор сделки.
            languages: Нормализованный список языков сделки (может быть None).
            discovery_status: Итоговый агрегированный статус discovery.

        Returns:
            Обновлённый Deal или None, если сделка не найдена.
        """
        stmt = (
            update(Deal)
            .where(Deal.id == deal_id)
            .values(
                languages=languages,
                language_discovery_status=discovery_status,
            )
            .returning(Deal)
        )
        result = await self.session.execute(stmt)
        deal = result.scalar_one_or_none()
        if deal:
            await self.session.flush()
        return deal

    async def set_last_run_id(
        self,
        deal_id: uuid.UUID,
        run_id: uuid.UUID | None,
        checks_mode: str | None = None,
        pipeline_strategy: str | None = None,
    ) -> None:
        """Внутренний метод оркестратора (без tenant_id)."""
        values: dict[str, object] = {"last_run_id": run_id}
        if checks_mode:
            values["last_run_checks_mode"] = checks_mode
        if pipeline_strategy:
            values["last_run_pipeline_strategy"] = pipeline_strategy

        stmt = update(Deal).where(Deal.id == deal_id).values(**values)
        await self.session.execute(stmt)
        await self.session.flush()

    async def set_has_pending_manual_reclassifications(
        self,
        deal_id: uuid.UUID,
        value: bool,
    ) -> None:
        """Внутренний метод пайплайна."""
        stmt = (
            update(Deal)
            .where(Deal.id == deal_id)
            .values(has_pending_manual_reclassifications=value)
        )
        await self.session.execute(stmt)
        await self.session.flush()


        