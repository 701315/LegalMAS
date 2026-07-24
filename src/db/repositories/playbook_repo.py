# src/db/repositories/playbook_repo.py


"""
Repository for Playbook, PlaybookVersion and ModelConfig operations.
"""
from uuid import UUID
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import json
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import PlaybookStatus

from ..models.deal import Deal
from ..models.playbook import (
    ModelConfig,
    Playbook,
    PlaybookLineItem,
    PlaybookVersion,
)
from ..models.run import Run


def compute_source_payload_hash(source_payload: dict) -> str:
    """
    Compute deterministic SHA256 of canonical JSON serialization.

    Canonicalization:
    - sorted keys
    - no whitespace
    - UTF-8 encoding
    """
    canonical = json.dumps(
        source_payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()



@dataclass
class PlaybookLineUsage:
    """
    Простая структура для описания использования логического плейбука (Playbook).

    Для непрофессионального программиста:
    - line_exists:    найден ли сам шаблон (Playbook).
    - versions_count: сколько версий PlaybookVersion к нему привязано.
    - used_in_deals:  сколько сделок прямо сейчас ссылаются на эти версии.
    - used_in_runs:   сколько запусков Run ссылаются на эти версии (история).
    - deal_names:     несколько имён сделок для понятного сообщения пользователю.
    """

    line_exists: bool
    versions_count: int = 0
    used_in_deals: int = 0
    used_in_runs: int = 0
    deal_names: list[str] | None = None


class PlaybookRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def _ensure_not_published(self, pv: PlaybookVersion):
        if pv.status == PlaybookStatus.PUBLISHED.value:
            raise Exception("PUBLISHED_VERSION_IMMUTABLE")
        
    # --- ModelConfig operations ---

    async def create_model_config(
        self,
        name: str,
        embeddings_primary: str = "intfloat/multilingual-e5-large",
        embeddings_fallback: str | None = "cointegrated/LaBSE",
        retrieval_config: dict | None = None,
        scoring_config: dict | None = None,
    ) -> ModelConfig:
        """Create a model configuration."""
        mc = ModelConfig(
            name=name,
            embeddings_primary=embeddings_primary,
            embeddings_fallback=embeddings_fallback,
            retrieval_config=retrieval_config or {},
            scoring_config=scoring_config or {},
        )
        self.session.add(mc)
        await self.session.flush()
        return mc

    async def list_model_configs(self) -> list[ModelConfig]:
        """List all model configurations (for UI selector)."""
        result = await self.session.execute(select(ModelConfig))
        return list(result.scalars().all())

    async def get_model_config(self, config_id: uuid.UUID) -> ModelConfig | None:
        """Get single model configuration by ID."""
        result = await self.session.execute(select(ModelConfig).where(ModelConfig.id == config_id))
        return result.scalar_one_or_none()

    async def update_model_config(
        self,
        config_id: uuid.UUID,
        *,
        name: str | None = None,
        embeddings_primary: str | None = None,
        embeddings_fallback: str | None = None,
        retrieval_config: dict | None = None,
        scoring_config: dict | None = None,
    ) -> ModelConfig | None:
        """Update fields of a model configuration."""
        mc = await self.get_model_config(config_id)
        if mc is None:
            return None

        if name is not None:
            mc.name = name
        if embeddings_primary is not None:
            mc.embeddings_primary = embeddings_primary
        if embeddings_fallback is not None:
            mc.embeddings_fallback = embeddings_fallback
        if retrieval_config is not None:
            mc.retrieval_config = retrieval_config
        if scoring_config is not None:
            mc.scoring_config = scoring_config

        await self.session.flush()
        return mc

    # --- Playbook (logical line) operations ---

    async def create_playbook(
        self,
        code: str,
        title: str,
        description: str | None = None,
        deal_type: str | None = None,
        jurisdiction: str | None = None,
        language: str | None = None,
        risk_profile: str | None = None,
        tenant_id: uuid.UUID | None = None,
    ) -> Playbook:
        """
        Create a logical Playbook (template/line).

        Ownership:
        - tenant_id = None → platform-owned, visible to all tenants
        - tenant_id = <uuid> → tenant-owned, visible only inside this tenant

        Code must be unique; caller is responsible for handling conflicts.
        """
        owner_scope = "tenant" if tenant_id is not None else "platform"

        playbook = Playbook(
            code=code,
            title=title,
            description=description,
            deal_type=deal_type,
            jurisdiction=jurisdiction,
            language=language,
            risk_profile=risk_profile,
            tenant_id=tenant_id,
            owner_scope=owner_scope,
        )
        self.session.add(playbook)
        await self.session.flush()
        return playbook

    async def get_playbook_by_id(self, playbook_id: uuid.UUID) -> Playbook | None:
        """Get Playbook by ID."""
        result = await self.session.execute(select(Playbook).where(Playbook.id == playbook_id))
        return result.scalar_one_or_none()

    async def get_playbook_by_code(self, code: str) -> Playbook | None:
        """Get Playbook by its machine-readable code."""
        result = await self.session.execute(select(Playbook).where(Playbook.code == code))
        return result.scalar_one_or_none()

    async def list_playbooks(
        self,
        deal_type: str | None = None,
        jurisdiction: str | None = None,
        language: str | None = None,
        tenant_id: uuid.UUID | None = None,
        include_platform: bool = True,
        only_tenant_owned: bool = False,
    ) -> list[Playbook]:
        """
        List Playbooks with optional filtering.

        Tenant scope semantics:
        - tenant_id=None, include_platform=True → all platform playbooks
          (used by superadmin without tenant filter)
        - tenant_id=<uuid>, include_platform=True → platform + this tenant's
          (used by tenant_admin / member in general listings)
        - tenant_id=<uuid>, only_tenant_owned=True → ONLY this tenant's
          (used by "My playbooks" catalog page)
        - tenant_id=None, include_platform=False → nothing meaningful, avoid
        """
        from sqlalchemy import or_

        stmt = select(Playbook)

        if deal_type is not None:
            stmt = stmt.where(Playbook.deal_type == deal_type)
        if jurisdiction is not None:
            stmt = stmt.where(Playbook.jurisdiction == jurisdiction)
        if language is not None:
            stmt = stmt.where(Playbook.language == language)

        if only_tenant_owned:
            if tenant_id is None:
                # nothing to return
                return []
            stmt = stmt.where(Playbook.tenant_id == tenant_id)
        else:
            if tenant_id is not None and include_platform:
                stmt = stmt.where(
                    or_(
                        Playbook.tenant_id == tenant_id,
                        Playbook.tenant_id.is_(None),
                    )
                )
            elif tenant_id is not None:
                stmt = stmt.where(Playbook.tenant_id == tenant_id)
            elif not include_platform:
                # tenant_id None + include_platform False → return nothing
                return []

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # --- Playbook line items (constructor content) ---

    async def get_line_with_items(
        self,
        playbook_id: uuid.UUID,
    ) -> tuple[Playbook | None, list[PlaybookLineItem]]:
        """
        Получить логический плейбук и все его элементы (topics/checks),
        отсортированные по order_index и id.
        """
        playbook = await self.get_playbook_by_id(playbook_id)
        if playbook is None:
            return None, []

        result = await self.session.execute(
            select(PlaybookLineItem)
            .where(PlaybookLineItem.line_id == playbook_id)
            .order_by(PlaybookLineItem.order_index, PlaybookLineItem.id)
        )
        items = list(result.scalars().all())
        return playbook, items

    async def create_line_with_items(
        self,
        title: str,
        description: str | None,
        deal_type: str | None,
        jurisdiction: str | None,
        language: str | None,
        items: Iterable[dict],
        tenant_id: uuid.UUID | None = None,
    ) -> tuple[Playbook, list[PlaybookLineItem]]:
        """
        Создать логический Playbook (линию) и полностью задать его состав (items).

        items — итерируемый список словарей:
        {
            "kind": "check",
            "instruction_code": str,
            "order_index": int,
        }

        tenant_id:
        - None → platform-owned (visible to all tenants)
        - <uuid> → tenant-owned (visible only inside this tenant)
        """
        code = self._generate_code_from_title(title)

        playbook = await self.create_playbook(
            code=code,
            title=title,
            description=description,
            deal_type=deal_type,
            jurisdiction=jurisdiction,
            language=language,
            risk_profile=None,
            tenant_id=tenant_id,
        )

        line_items: list[PlaybookLineItem] = []
        for payload in items:
            item = PlaybookLineItem(
                line_id=playbook.id,
                kind=payload.get("kind"),
                instruction_code=payload.get("instruction_code"),
                order_index=payload.get("order_index") or 0,
            )
            self.session.add(item)
            line_items.append(item)

        await self.session.flush()
        return playbook, line_items

    async def update_line_with_items(
        self,
        line_id: uuid.UUID,
        title: str,
        description: str | None,
        deal_type: str | None,
        jurisdiction: str | None,
        language: str | None,
        items: Iterable[dict],
    ) -> tuple[Playbook | None, list[PlaybookLineItem]]:
        """
        Обновить логический Playbook и полностью пересоздать его состав (items).

        Если плейбук с таким ID не найден, вернёт (None, []).
        """
        playbook = await self.get_playbook_by_id(line_id)
        if playbook is None:
            return None, []

        playbook.title = title
        playbook.description = description
        playbook.deal_type = deal_type
        playbook.jurisdiction = jurisdiction
        playbook.language = language

        # Удаляем старые элементы
        await self.session.execute(
            text("DELETE FROM playbook_line_items WHERE line_id = :line_id"),
            {"line_id": str(line_id)},
        )

        # Добавляем новые элементы
        line_items: list[PlaybookLineItem] = []
        for payload in items:
            item = PlaybookLineItem(
                line_id=playbook.id,
                kind=payload.get("kind"),
                instruction_code=payload.get("instruction_code"),
                order_index=payload.get("order_index") or 0,
            )
            self.session.add(item)
            line_items.append(item)

        await self.session.flush()
        return playbook, line_items

    def _generate_code_from_title(self, title: str) -> str:
        """
        Простейший генератор machine-readable кода по title.

        Делает slug в snake_case, обрезает до 80 символов.
        """
        base = title.lower().replace(" ", "_").replace("/", "_").replace("—", "_").replace("-", "_")
        base = "".join(ch for ch in base if ch.isalnum() or ch == "_")
        return base[:80]

    # --- Playbook line usage & delete ---

    async def get_line_usage(self, line_id: uuid.UUID) -> PlaybookLineUsage:
        """
        Вернуть информацию об использовании логического плейбука (Playbook).

        Для непрофессионального программиста:
        - шаг 1: проверяем, существует ли сам шаблон;
        - шаг 2: ищем все его версии PlaybookVersion;
        - шаг 3: считаем, есть ли Deal, которые сейчас ссылаются на эти версии;
        - шаг 4: считаем, есть ли Run, которые исторически ссылаются на эти версии.

        Это нужно, чтобы перед удалением шаблона понять, можно ли его безопасно удалить.
        """

        # 1. Существует ли сам Playbook
        playbook = await self.get_playbook_by_id(line_id)
        if playbook is None:
            return PlaybookLineUsage(
                line_exists=False,
                versions_count=0,
                used_in_deals=0,
                used_in_runs=0,
                deal_names=[],
            )

        # 2. Все версии этого Playbook
        versions_stmt = select(PlaybookVersion.id).where(PlaybookVersion.playbook_id == line_id)
        versions_result = await self.session.execute(versions_stmt)
        version_ids = list(versions_result.scalars().all())
        versions_count = len(version_ids)

        if versions_count == 0:
            # Нет версий — точно никто не использует
            return PlaybookLineUsage(
                line_exists=True,
                versions_count=0,
                used_in_deals=0,
                used_in_runs=0,
                deal_names=[],
            )

        # 3. Считаем сделки, использующие эти версии
        deals_stmt = select(Deal).where(Deal.playbook_version_id.in_(version_ids))
        deals_result = await self.session.execute(deals_stmt)
        deals = list(deals_result.scalars().all())
        used_in_deals = len(deals)

        deal_names: list[str] = []
        for d in deals[:5]:
            # Берём понятное имя сделки (или id, если имени нет)
            name = getattr(d, "name", None) or str(d.id)
            deal_names.append(name)

        # 4. Считаем запуски Run, использующие эти версии
        runs_stmt = (
            select(func.count()).select_from(Run).where(Run.playbook_version_id.in_(version_ids))
        )
        runs_result = await self.session.execute(runs_stmt)
        used_in_runs = int(runs_result.scalar_one() or 0)

        return PlaybookLineUsage(
            line_exists=True,
            versions_count=versions_count,
            used_in_deals=used_in_deals,
            used_in_runs=used_in_runs,
            deal_names=deal_names,
        )

    async def delete_line_with_items(self, line_id: uuid.UUID) -> bool:
        """
        Удаляет Playbook и все его line_items.

        Для непрофессионального программиста:
        - на вход подаём ID шаблона;
        - если шаблон найден — удаляем его (элементы удалятся каскадно);
        - если не найден — возвращаем False.

        Важно: этот метод сам по себе НЕ проверяет использование.
        Перед вызовом нужно вызвать get_line_usage и убедиться, что шаблон
        не используется сделками и запусками.
        """
        playbook = await self.get_playbook_by_id(line_id)
        if playbook is None:
            return False

        await self.session.delete(playbook)
        # Связанные PlaybookLineItem удалятся благодаря cascade="all, delete-orphan"
        await self.session.flush()
        return True

    # --- PlaybookVersion operations ---

    async def create_version(
        self,
        name: str,
        semver: str,
        model_config_id: uuid.UUID,
        git_commit: str | None = None,
        yaml_sha256: str | None = None,
        compiled_checks: dict | None = None,
        status: str = PlaybookStatus.DRAFT.value,
        playbook_id: uuid.UUID | None = None,
        source_payload: dict | None = None,
        tenant_id: uuid.UUID | None = None,
    ) -> PlaybookVersion:
        """
        Create a new playbook version.

        If status='default', automatically archives the previous default version
        to ensure only one default exists at any time (global default).
        """
        is_default = status == PlaybookStatus.DEFAULT.value
        if is_default:
            # Снимаем is_default со всех существующих
            await self.session.execute(
                update(PlaybookVersion)
                .where(PlaybookVersion.is_default.is_(True))
                .values(is_default=False)
            )
            status = PlaybookStatus.PUBLISHED.value

        source_payload_sha256: str | None = None
        if source_payload is not None:
            source_payload_sha256 = compute_source_payload_hash(source_payload)

        owner_scope = "tenant" if tenant_id is not None else "platform"

        pv = PlaybookVersion(
            playbook_id=playbook_id,
            name=name,
            semver=semver,
            model_config_id=model_config_id,
            git_commit=git_commit,
            yaml_sha256=yaml_sha256,
            compiled_checks=compiled_checks,
            status=status,
            is_default=is_default,
            source_payload=source_payload,
            source_payload_sha256=source_payload_sha256,
            tenant_id=tenant_id,
            owner_scope=owner_scope,
        )
        self.session.add(pv)
        await self.session.flush()
        return pv

    async def get_default(self) -> PlaybookVersion | None:
        """Get the global default playbook version."""
        result = await self.session.execute(
            select(PlaybookVersion).where(PlaybookVersion.is_default.is_(True))
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, version_id: uuid.UUID) -> PlaybookVersion | None:
        """Get playbook version by ID."""
        result = await self.session.execute(
            select(PlaybookVersion).where(PlaybookVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def get_for_deal(self, deal_id: uuid.UUID) -> PlaybookVersion | None:
        """
        Get playbook for a specific deal:
        1) try Deal.playbook_version_id
        2) fallback to global default.
        """
        # 1) playbook, явно привязанный к сделке
        result = await self.session.execute(
            select(PlaybookVersion)
            .join(Deal, Deal.playbook_version_id == PlaybookVersion.id)
            .where(Deal.id == deal_id)
        )
        pb = result.scalar_one_or_none()
        if pb is not None:
            return pb

        # 2) глобальный default
        return await self.get_default()

    async def promote_to_default(self, version_id: uuid.UUID) -> PlaybookVersion | None:
        """
        Назначить version как глобальный default.

        Снимает is_default со всех остальных версий,
        ставит is_default=True на указанную.
        """
        # Снимаем is_default со всех
        await self.session.execute(
            update(PlaybookVersion)
            .where(PlaybookVersion.is_default.is_(True))
            .values(is_default=False)
        )

        # Ставим is_default на target
        await self.session.execute(
            update(PlaybookVersion)
            .where(PlaybookVersion.id == version_id)
            .values(is_default=True)
        )

        await self.session.flush()

        result = await self.session.execute(
            select(PlaybookVersion).where(PlaybookVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def update_draft_compiled_checks(
        self,
        version_id: uuid.UUID,
        compiled_checks: dict,
    ) -> PlaybookVersion | None:

        pv = await self.get_by_id(version_id)
        if not pv:
            return None

        self._ensure_not_published(pv)

        pv.compiled_checks = compiled_checks
        await self.session.flush()
        return pv


    async def get_effective_version_for_deal(
        self,
        deal_id: UUID,
    ) -> PlaybookVersion | None:
        """
        Возвращает версию playbook для запуска Run.

        Приоритет:

        1. Если у сделки явно указан playbook_version_id:
        - если status in (published, active) → использовать
        - если draft или archived → ошибка

        2. Иначе:
        - последняя published версия
        - fallback на legacy active
        """

        # --- 1️⃣ Проверяем, есть ли явно привязанная версия у сделки ---

        result = await self.session.execute(
            select(Deal.playbook_version_id).where(Deal.id == deal_id)
        )
        deal_playbook_id = result.scalar_one_or_none()

        if deal_playbook_id:
            pv = await self.get_by_id(deal_playbook_id)
            if pv is None:
                return None

            # Разрешаем published и legacy active
            if pv.status in (
                PlaybookStatus.PUBLISHED.value,
                "active",  # legacy fallback
            ):
                return pv

            # draft / archived запрещены для Run
            raise Exception("PLAYBOOK_VERSION_NOT_RUNNABLE")

        # --- 2️⃣ Нет явной версии → ищем published ---

        stmt = (
            select(PlaybookVersion)
            .where(PlaybookVersion.status == PlaybookStatus.PUBLISHED.value)
            .order_by(PlaybookVersion.published_at.desc())
            .limit(1)
        )

        result = await self.session.execute(stmt)
        published = result.scalar_one_or_none()

        if published:
            return published

        # --- 3️⃣ Fallback на legacy active ---

        stmt = (
            select(PlaybookVersion)
            .where(PlaybookVersion.status == "active")
            .order_by(PlaybookVersion.created_at.desc())
            .limit(1)
        )

        result = await self.session.execute(stmt)
        legacy = result.scalar_one_or_none()

        return legacy
    
    async def list_versions_for_playbook(
        self,
        playbook_id: uuid.UUID,
    ) -> list[PlaybookVersion]:
        """
        Вернуть все версии, относящиеся к конкретному logical Playbook.

        Используется facade API:
        GET /api/v1/admin/instructions/global/{playbook_id}/versions
        """
        stmt = (
            select(PlaybookVersion)
            .where(PlaybookVersion.playbook_id == playbook_id)
            .order_by(
                PlaybookVersion.published_at.desc().nullslast(),
                PlaybookVersion.created_at.desc(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
    

