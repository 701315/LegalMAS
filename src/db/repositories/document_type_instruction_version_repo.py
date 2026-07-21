# src/db/repositories/document_type_instruction_version_repo.py

# src/db/repositories/document_type_instruction_version_repo.py

"""
Repository for persisted document type instruction versions.

Задача:
- по runtime DocumentTypeConfig из YAMLRegistry найти или создать
  историческую запись DocumentTypeInstructionVersion;
- гарантировать race-safe поведение через PostgreSQL ON CONFLICT;
- предоставлять lifecycle-ready repository API для draft/published/archive flow;
- поддерживать multi-tenant scope (platform / tenant);
- не смешивать бизнес-логику publish/validate с деталями persistence.

Scope-модель:
- platform: owner_scope='platform', tenant_id=NULL
  Видимы всем tenant'ам, не редактируются tenant'ами напрямую.
- tenant: owner_scope='tenant', tenant_id=<uuid>
  Принадлежат одному tenant'у, видимы только внутри него.

Backward-compatibility:
- все существующие call sites (document_repo, document_segment_repo,
  instruction_snapshot) работают без изменений через platform-only path.
- новые scope-aware методы добавлены рядом без ломки старых контрактов.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import Select, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from classifiers.yaml_registry import DocumentTypeConfig
from core.logging import get_logger
from db.models.document_type_instruction import DocumentTypeInstructionVersion

logger = get_logger(__name__)


class TenantOwnershipError(Exception):
    """Instruction version не принадлежит данному tenant'у."""


@dataclass(slots=True)
class ResolveInstructionVersionResult:
    """
    Результат resolve/create операции.

    Для непрофессионального программиста:
    - version: ORM-объект persisted instruction version;
    - created: True, если запись была создана в этой операции;
    - lookup_key: удобный debug-ключ для логов/аудита.
    """

    version: DocumentTypeInstructionVersion
    created: bool
    lookup_key: str


class DocumentTypeInstructionVersionRepository:
    """
    Репозиторий persisted snapshot-версий doc_type YAML-инструкций.

    Контракт:
    - принимает AsyncSession текущего unit of work;
    - не делает commit самостоятельно;
    - может безопасно вызываться внутри общей транзакции runner/worker;
    - предоставляет lifecycle-ready операции для publish service;
    - поддерживает platform scope (tenant_id=NULL) и tenant scope.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # ------------------------------------------------------------------
    # Basic reads
    # ------------------------------------------------------------------

    async def get_by_id(
        self,
        instruction_version_id,
    ) -> DocumentTypeInstructionVersion | None:
        stmt: Select[tuple[DocumentTypeInstructionVersion]] = select(
            DocumentTypeInstructionVersion
        ).where(DocumentTypeInstructionVersion.id == instruction_version_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_version_for_update(
        self,
        instruction_version_id,
    ) -> DocumentTypeInstructionVersion | None:
        """
        Загрузить version row c SELECT ... FOR UPDATE.

        Используется publish/archive service-слоем, чтобы:
        - защититься от гонок при publish;
        - не публиковать уже изменённый draft;
        - не архивировать/version-switch конкурентно.
        """
        stmt: Select[tuple[DocumentTypeInstructionVersion]] = (
            select(DocumentTypeInstructionVersion)
            .where(DocumentTypeInstructionVersion.id == instruction_version_id)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_doc_type_and_sha256(
        self,
        *,
        doc_type_code: str,
        source_sha256: str,
        owner_scope: str = "platform",
        tenant_id: uuid.UUID | None = None,
    ) -> DocumentTypeInstructionVersion | None:
        """
        Найти версию по (doc_type_code, source_sha256) с учётом scope.

        Platform scope: owner_scope='platform', tenant_id=None.
        Tenant scope: owner_scope='tenant', tenant_id=<uuid>.

        Backward-compatible: по умолчанию ищет в platform scope,
        что соответствует старому поведению до multi-tenant.
        """
        stmt = select(DocumentTypeInstructionVersion).where(
            DocumentTypeInstructionVersion.doc_type_code == doc_type_code,
            DocumentTypeInstructionVersion.source_sha256 == source_sha256,
            DocumentTypeInstructionVersion.owner_scope == owner_scope,
        )
        if owner_scope == "tenant":
            stmt = stmt.where(
                DocumentTypeInstructionVersion.tenant_id == tenant_id,
            )
        else:
            stmt = stmt.where(
                DocumentTypeInstructionVersion.tenant_id.is_(None),
            )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_doc_type_code(
        self,
        doc_type_code: str,
        *,
        owner_scope: str | None = None,
        tenant_id: uuid.UUID | None = None,
    ) -> list[DocumentTypeInstructionVersion]:
        """
        Вернуть все версии инструкции для doc_type_code, новые сначала.

        Если owner_scope не задан — возвращает все версии (platform + tenant).
        Если owner_scope='platform' — только platform.
        Если owner_scope='tenant' — только для конкретного tenant_id.

        Backward-compatible: без параметров возвращает всё (старое поведение).
        """
        stmt = select(DocumentTypeInstructionVersion).where(
            DocumentTypeInstructionVersion.doc_type_code == doc_type_code,
        )
        if owner_scope == "platform":
            stmt = stmt.where(
                DocumentTypeInstructionVersion.owner_scope == "platform",
                DocumentTypeInstructionVersion.tenant_id.is_(None),
            )
        elif owner_scope == "tenant" and tenant_id is not None:
            stmt = stmt.where(
                DocumentTypeInstructionVersion.owner_scope == "tenant",
                DocumentTypeInstructionVersion.tenant_id == tenant_id,
            )
        stmt = stmt.order_by(DocumentTypeInstructionVersion.created_at.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_all_versions(
        self,
    ) -> list[DocumentTypeInstructionVersion]:
        """
        Вернуть все persisted instruction versions для catalog/dashboard UI.

        Возвращает все версии (platform + все tenant) без фильтра.
        Для tenant-scoped catalog используй build_effective_catalog().

        Сортировка:
        - сначала по doc_type_code,
        - внутри doc_type — новые версии сверху.
        """
        stmt = (
            select(DocumentTypeInstructionVersion)
            .order_by(
                DocumentTypeInstructionVersion.doc_type_code.asc(),
                DocumentTypeInstructionVersion.created_at.desc(),
                DocumentTypeInstructionVersion.updated_at.desc(),
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_platform_versions(
        self,
        *,
        doc_type_code: str | None = None,
        version_status: str | None = None,
    ) -> list[DocumentTypeInstructionVersion]:
        """
        Список platform-owned versions.

        Если doc_type_code=None — все platform versions.
        Если version_status задан — фильтрует по статусу.
        """
        stmt = select(DocumentTypeInstructionVersion).where(
            DocumentTypeInstructionVersion.owner_scope == "platform",
            DocumentTypeInstructionVersion.tenant_id.is_(None),
        )
        if doc_type_code is not None:
            stmt = stmt.where(
                DocumentTypeInstructionVersion.doc_type_code == doc_type_code,
            )
        if version_status is not None:
            stmt = stmt.where(
                DocumentTypeInstructionVersion.version_status == version_status,
            )
        stmt = stmt.order_by(
            DocumentTypeInstructionVersion.doc_type_code.asc(),
            DocumentTypeInstructionVersion.created_at.desc(),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_tenant_versions(
        self,
        tenant_id: uuid.UUID,
        *,
        doc_type_code: str | None = None,
        version_status: str | None = None,
    ) -> list[DocumentTypeInstructionVersion]:
        """
        Список tenant-owned versions.

        Только owner_scope='tenant' AND tenant_id=tenant_id.
        """
        stmt = select(DocumentTypeInstructionVersion).where(
            DocumentTypeInstructionVersion.owner_scope == "tenant",
            DocumentTypeInstructionVersion.tenant_id == tenant_id,
        )
        if doc_type_code is not None:
            stmt = stmt.where(
                DocumentTypeInstructionVersion.doc_type_code == doc_type_code,
            )
        if version_status is not None:
            stmt = stmt.where(
                DocumentTypeInstructionVersion.version_status == version_status,
            )
        stmt = stmt.order_by(
            DocumentTypeInstructionVersion.doc_type_code.asc(),
            DocumentTypeInstructionVersion.created_at.desc(),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def build_effective_catalog(
        self,
        tenant_id: uuid.UUID,
    ) -> list[DocumentTypeInstructionVersion]:
        """
        Effective catalog для tenant:
        - все platform versions (любой status);
        - все tenant-owned versions (любой status).

        Это read-model для UI catalog.
        Не используется в runtime — там только exact version refs.
        """
        stmt = select(DocumentTypeInstructionVersion).where(
            (
                (DocumentTypeInstructionVersion.owner_scope == "platform")
                | (
                    (DocumentTypeInstructionVersion.owner_scope == "tenant")
                    & (DocumentTypeInstructionVersion.tenant_id == tenant_id)
                )
            )
        ).order_by(
            DocumentTypeInstructionVersion.doc_type_code.asc(),
            DocumentTypeInstructionVersion.owner_scope.asc(),
            DocumentTypeInstructionVersion.created_at.desc(),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_by_doc_type_code(
        self,
        doc_type_code: str,
        *,
        published_only: bool = True,
    ) -> DocumentTypeInstructionVersion | None:
        """
        Вернуть самую свежую persisted instruction version для doc_type_code.

        Ищет только в platform scope (owner_scope='platform').
        RunSnapshotService должен использовать published_only=True,
        чтобы draft-версии не попадали в исполняемые Run.
        """
        stmt = select(DocumentTypeInstructionVersion).where(
            DocumentTypeInstructionVersion.doc_type_code == doc_type_code,
            DocumentTypeInstructionVersion.owner_scope == "platform",
            DocumentTypeInstructionVersion.tenant_id.is_(None),
        )
        if published_only:
            stmt = stmt.where(
                DocumentTypeInstructionVersion.version_status == "published"
            )

        stmt = stmt.order_by(DocumentTypeInstructionVersion.created_at.desc()).limit(1)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_published(
        self,
        doc_type_code: str,
        *,
        tenant_id: uuid.UUID | None = None,
    ) -> DocumentTypeInstructionVersion | None:
        """
        Получить последнюю published версию инструкции по doc_type_code.

        tenant_id=None (default) → искать только в platform scope.
        tenant_id=<uuid> → сначала искать tenant-published, если нет — platform.

        Это canonical метод для runtime/override resolution.
        """
        if tenant_id is not None:
            # Сначала пробуем tenant-owned published version
            tenant_stmt = select(DocumentTypeInstructionVersion).where(
                DocumentTypeInstructionVersion.doc_type_code == doc_type_code,
                DocumentTypeInstructionVersion.owner_scope == "tenant",
                DocumentTypeInstructionVersion.tenant_id == tenant_id,
                DocumentTypeInstructionVersion.version_status == "published",
            ).order_by(DocumentTypeInstructionVersion.created_at.desc()).limit(1)
            tenant_result = await self.session.execute(tenant_stmt)
            tenant_version = tenant_result.scalar_one_or_none()
            if tenant_version is not None:
                return tenant_version

        # Platform published version
        platform_stmt = select(DocumentTypeInstructionVersion).where(
            DocumentTypeInstructionVersion.doc_type_code == doc_type_code,
            DocumentTypeInstructionVersion.owner_scope == "platform",
            DocumentTypeInstructionVersion.tenant_id.is_(None),
            DocumentTypeInstructionVersion.version_status == "published",
        ).order_by(DocumentTypeInstructionVersion.created_at.desc()).limit(1)
        platform_result = await self.session.execute(platform_stmt)
        return platform_result.scalar_one_or_none()

    async def assert_tenant_owns(
        self,
        version_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> DocumentTypeInstructionVersion:
        """
        Загрузить version и проверить что tenant её владеет.

        Raises: TenantOwnershipError если version не принадлежит tenant.
        Используется как guard в service/endpoint layer.
        """
        version = await self.get_by_id(version_id)
        if version is None:
            raise TenantOwnershipError(
                f"Instruction version {version_id} not found."
            )
        if version.owner_scope != "tenant" or version.tenant_id != tenant_id:
            raise TenantOwnershipError(
                f"Instruction version {version_id} does not belong to tenant {tenant_id}. "
                f"owner_scope={version.owner_scope}, version.tenant_id={version.tenant_id}"
            )
        return version

    async def create_version(
        self,
        *,
        doc_type_code: str,
        source_yaml: str,
        source_sha256: str,
        compiled_payload: dict | None,
        name: str | None = None,
        source_format: str = "yaml",
        source_path: str | None = None,
        git_commit: str | None = None,
        semver: str | None = None,
        version_status: str = "draft",
        immutable_content_hash: str | None = None,
        validation_report: dict | None = None,
        parent_version_id=None,
        derived_from_version_id=None,
        published_at=None,
        created_by=None,
        change_summary: str | None = None,
        owner_scope: str = "platform",
        tenant_id: uuid.UUID | None = None,
    ) -> DocumentTypeInstructionVersion:
        """
        Создать новую persisted instruction version.

        Repository не решает бизнес-правила lifecycle.
        Он только создаёт строку с переданными данными и flush'ит её.

        owner_scope='platform' + tenant_id=None → platform instruction.
        owner_scope='tenant' + tenant_id=<uuid> → tenant instruction.
        """
        version = DocumentTypeInstructionVersion(
            doc_type_code=doc_type_code,
            name=name,
            source_format=source_format,
            source_yaml=source_yaml,
            source_sha256=source_sha256,
            source_path=source_path,
            git_commit=git_commit,
            semver=semver,
            compiled_payload=compiled_payload,
            version_status=version_status,
            immutable_content_hash=immutable_content_hash,
            validation_report=validation_report,
            parent_version_id=parent_version_id,
            derived_from_version_id=derived_from_version_id,
            published_at=published_at,
            created_by=created_by,
            change_summary=change_summary,
            owner_scope=owner_scope,
            tenant_id=tenant_id,
        )
        self.session.add(version)
        await self.session.flush()

        logger.info(
            "Instruction version created explicitly",
            extra={
                "doc_type_code": doc_type_code,
                "instruction_version_id": str(version.id),
                "version_status": version_status,
                "owner_scope": owner_scope,
                "tenant_id": str(tenant_id) if tenant_id else None,
            },
        )
        return version

    # ------------------------------------------------------------------
    # Lifecycle mutations
    # ------------------------------------------------------------------

    async def archive_previous_published(
        self,
        *,
        doc_type_code: str,
        exclude_version_id,
        owner_scope: str = "platform",
        tenant_id: uuid.UUID | None = None,
    ) -> int:
        """
        Архивировать все published версии для doc_type_code,
        кроме exclude_version_id.

        Фильтрует только внутри того же scope:
        - platform publish не трогает tenant versions;
        - tenant publish не трогает platform или другие tenant versions.

        Используется publish service после успешной публикации новой версии.

        Returns:
            Количество затронутых строк.
        """
        stmt = update(DocumentTypeInstructionVersion).where(
            DocumentTypeInstructionVersion.doc_type_code == doc_type_code,
            DocumentTypeInstructionVersion.version_status == "published",
            DocumentTypeInstructionVersion.id != exclude_version_id,
            DocumentTypeInstructionVersion.owner_scope == owner_scope,
        )

        if owner_scope == "tenant" and tenant_id is not None:
            stmt = stmt.where(
                DocumentTypeInstructionVersion.tenant_id == tenant_id,
            )
        else:
            stmt = stmt.where(
                DocumentTypeInstructionVersion.tenant_id.is_(None),
            )

        stmt = stmt.values(version_status="archived")
        result = await self.session.execute(stmt)
        await self.session.flush()

        affected = result.rowcount or 0
        logger.info(
            "Archived previous published instruction versions",
            extra={
                "doc_type_code": doc_type_code,
                "exclude_version_id": str(exclude_version_id),
                "owner_scope": owner_scope,
                "tenant_id": str(tenant_id) if tenant_id else None,
                "affected_count": affected,
            },
        )
        return affected

    async def update_version(
        self,
        version: DocumentTypeInstructionVersion,
        *,
        source_yaml: str,
        source_sha256: str,
        compiled_payload: dict | None,
        name: str | None = None,
        source_path: str | None = None,
        git_commit: str | None = None,
        semver: str | None = None,
        validation_report: dict | None = None,
        change_summary: str | None = None,
        immutable_content_hash: str | None = None,
        version_status: str | None = None,
        parent_version_id=None,
        published_at=None,
    ) -> DocumentTypeInstructionVersion:
        """
        Обновить ORM-объект version в памяти и flush'нуть.

        ВАЖНО:
        - repository не решает, МОЖНО ли обновлять конкретный статус;
        - это решает service-слой;
        - repository только предоставляет единый safe update helper;
        - owner_scope и tenant_id не меняются через update — они immutable.
        """
        version.source_yaml = source_yaml
        version.source_sha256 = source_sha256
        version.compiled_payload = compiled_payload
        version.name = name
        version.source_path = source_path
        version.git_commit = git_commit
        version.semver = semver
        version.validation_report = validation_report
        version.change_summary = change_summary

        if immutable_content_hash is not None:
            version.immutable_content_hash = immutable_content_hash
        if version_status is not None:
            version.version_status = version_status
        if parent_version_id is not None:
            version.parent_version_id = parent_version_id
        if published_at is not None:
            version.published_at = published_at

        await self.session.flush()
        return version

    # ------------------------------------------------------------------
    # Resolve/create from runtime config (platform-only, backward-compatible)
    # ------------------------------------------------------------------

    async def resolve_or_create_from_config(
        self,
        cfg: DocumentTypeConfig,
        *,
        git_commit: str | None = None,
        semver: str | None = None,
        compiled_payload: dict | None = None,
    ) -> ResolveInstructionVersionResult:
        """
        Найти или создать persisted instruction version по runtime config.

        ВАЖНО: этот метод работает только с platform scope.
        Используется при:
        - classification (document_repo, document_segment_repo)
        - instruction snapshot freeze (instruction_snapshot.py)

        Tenant-scope operations используют create_version() напрямую
        через service-layer.

        Args:
            cfg:
                Конфиг из YAMLRegistry.get_config(type_code).
            git_commit:
                Опциональный git commit source repository.
            semver:
                Опциональная человекочитаемая версия.
            compiled_payload:
                Опциональный нормализованный/compiled payload.

        Returns:
            ResolveInstructionVersionResult(version=..., created=bool, lookup_key=...)

        Raises:
            ValueError:
                если cfg не содержит минимально достаточных данных.
        """
        payload = self._build_persistence_payload(
            cfg,
            git_commit=git_commit,
            semver=semver,
            compiled_payload=compiled_payload,
        )
        lookup_key = f"{payload['doc_type_code']}:{payload['source_sha256']}"

        # 1) Fast path: сначала пробуем найти уже существующую запись.
        existing = await self.get_by_doc_type_and_sha256(
            doc_type_code=payload["doc_type_code"],
            source_sha256=payload["source_sha256"],
            owner_scope="platform",
            tenant_id=None,
        )
        if existing is not None:
            logger.debug(
                "Instruction version resolved from existing row",
                extra={
                    "doc_type_code": payload["doc_type_code"],
                    "source_sha256": payload["source_sha256"],
                    "instruction_version_id": str(existing.id),
                    "source_kind": getattr(cfg, "source_kind", None),
                },
            )
            return ResolveInstructionVersionResult(
                version=existing,
                created=False,
                lookup_key=lookup_key,
            )

        # 2) Race-safe create через PostgreSQL ON CONFLICT DO NOTHING.
        # Используем partial unique index для platform scope:
        # uix_doc_type_instruction_versions_platform_source_sha256
        stmt = (
            pg_insert(DocumentTypeInstructionVersion)
            .values(**payload)
            .on_conflict_do_nothing(
                index_elements=None,
                # Используем where clause из partial index:
                # WHERE owner_scope = 'platform'
                # Alembic не умеет напрямую ref partial unique,
                # поэтому используем constraint name для старой compat
                # или fallback на except/re-select ниже.
            )
            .returning(DocumentTypeInstructionVersion.id)
        )

        # Примечание: pg_insert с partial unique index требует
        # указания index_where или constraint name.
        # Так как у нас нет named constraint (только partial index),
        # используем безопасный fallback: try/except.
        try:
            result = await self.session.execute(stmt)
            inserted_id = result.scalar_one_or_none()
        except Exception:
            # Если ON CONFLICT не сработал корректно с partial index,
            # перечитываем запись.
            inserted_id = None

        if inserted_id is not None:
            created = await self.get_by_id(inserted_id)
            if created is None:
                raise RuntimeError(
                    "Instruction version row was inserted but could not be reloaded"
                )

            logger.info(
                "Instruction version created",
                extra={
                    "doc_type_code": payload["doc_type_code"],
                    "source_sha256": payload["source_sha256"],
                    "instruction_version_id": str(created.id),
                    "source_kind": getattr(cfg, "source_kind", None),
                },
            )
            return ResolveInstructionVersionResult(
                version=created,
                created=True,
                lookup_key=lookup_key,
            )

        # 3) Кто-то другой вставил ту же запись между нашим SELECT и INSERT.
        existing_after_conflict = await self.get_by_doc_type_and_sha256(
            doc_type_code=payload["doc_type_code"],
            source_sha256=payload["source_sha256"],
            owner_scope="platform",
            tenant_id=None,
        )
        if existing_after_conflict is None:
            raise RuntimeError(
                "Instruction version was not inserted and could not be resolved after conflict"
            )

        logger.debug(
            "Instruction version resolved after insert conflict",
            extra={
                "doc_type_code": payload["doc_type_code"],
                "source_sha256": payload["source_sha256"],
                "instruction_version_id": str(existing_after_conflict.id),
                "source_kind": getattr(cfg, "source_kind", None),
            },
        )
        return ResolveInstructionVersionResult(
            version=existing_after_conflict,
            created=False,
            lookup_key=lookup_key,
        )

    def _build_persistence_payload(
        self,
        cfg: DocumentTypeConfig,
        *,
        git_commit: str | None,
        semver: str | None,
        compiled_payload: dict | None,
    ) -> dict:
        """
        Собрать безопасный payload для persisted instruction version.

        Всегда создаёт platform-scope version (owner_scope='platform').
        Используется только в resolve_or_create_from_config.
        """
        doc_type_code = str(getattr(cfg, "type_code", "") or "").strip()
        if not doc_type_code:
            raise ValueError("Cannot persist instruction version: cfg.type_code is empty")

        name = str(getattr(cfg, "name", "") or "").strip() or None

        source_yaml = getattr(cfg, "source_yaml", None)
        if not isinstance(source_yaml, str) or not source_yaml.strip():
            raw = getattr(cfg, "raw", None) or {}
            source_yaml = DocumentTypeConfig._dump_canonical_yaml(raw)

        source_yaml = source_yaml.strip()
        if not source_yaml:
            raise ValueError(
                f"Cannot persist instruction version for '{doc_type_code}': source_yaml is empty"
            )

        source_sha256 = str(getattr(cfg, "source_sha256", "") or "").strip()
        if not source_sha256:
            source_sha256 = DocumentTypeConfig._compute_sha256(source_yaml)

        source_path = getattr(cfg, "source_path", None)
        if source_path is not None:
            source_path = str(source_path).strip() or None

        source_format = "yaml"

        effective_compiled_payload = compiled_payload
        if effective_compiled_payload is None:
            effective_compiled_payload = getattr(cfg, "raw", None) or {}

        payload = {
            "doc_type_code": doc_type_code,
            "name": name,
            "source_format": source_format,
            "source_yaml": source_yaml,
            "source_sha256": source_sha256,
            "source_path": source_path,
            "git_commit": (str(git_commit).strip() if git_commit else None),
            "semver": (str(semver).strip() if semver else None),
            "compiled_payload": effective_compiled_payload,
            # lifecycle defaults for resolve/create path:
            "version_status": "draft",
            "immutable_content_hash": None,
            "validation_report": None,
            "parent_version_id": None,
            "derived_from_version_id": None,
            # platform scope — это canonical path для runtime/classification
            "owner_scope": "platform",
            "tenant_id": None,
        }

        logger.debug(
            "Built instruction version persistence payload",
            extra={
                "doc_type_code": doc_type_code,
                "source_sha256": source_sha256,
                "owner_scope": "platform",
            },
        )
        return payload
    
    
    

    