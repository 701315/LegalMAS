# src/db/repositories/document_type_instruction_version_repo.py

"""
Repository for persisted document type instruction versions.

Задача:
- по runtime DocumentTypeConfig из YAMLRegistry найти или создать
  историческую запись DocumentTypeInstructionVersion;
- гарантировать race-safe поведение через PostgreSQL ON CONFLICT;
- не смешивать бизнес-логику классификации и детали persistence.

Почему это нужно:
- classification использует runtime YAMLRegistry;
- audit/persistence должен ссылаться на durable DB entity;
- одна и та же YAML-инструкция не должна создаваться повторно.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from classifiers.yaml_registry import DocumentTypeConfig
from core.logging import get_logger
from db.models.document_type_instruction import DocumentTypeInstructionVersion

logger = get_logger(__name__)


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
    - может безопасно вызываться внутри общей транзакции runner/worker.

    Основной метод:
    - resolve_or_create_from_config(cfg)
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(
        self,
        instruction_version_id,
    ) -> DocumentTypeInstructionVersion | None:
        stmt: Select[tuple[DocumentTypeInstructionVersion]] = select(
            DocumentTypeInstructionVersion
        ).where(DocumentTypeInstructionVersion.id == instruction_version_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_doc_type_and_sha256(
        self,
        *,
        doc_type_code: str,
        source_sha256: str,
    ) -> DocumentTypeInstructionVersion | None:
        stmt: Select[tuple[DocumentTypeInstructionVersion]] = select(
            DocumentTypeInstructionVersion
        ).where(
            DocumentTypeInstructionVersion.doc_type_code == doc_type_code,
            DocumentTypeInstructionVersion.source_sha256 == source_sha256,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

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

        Args:
            cfg:
                Конфиг из YAMLRegistry.get_config(type_code).
            git_commit:
                Опциональный git commit source repository, если известен
                в контексте конкретного запуска.
            semver:
                Опциональная человекочитаемая версия, если поддерживается отдельно.
            compiled_payload:
                Опциональный нормализованный/compiled payload для audit/debug/UI.

        Returns:
            ResolveInstructionVersionResult(version=..., created=bool, lookup_key=...)

        Raises:
            ValueError:
                если cfg не содержит минимально достаточных данных для persistence.
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
        stmt = (
            pg_insert(DocumentTypeInstructionVersion)
            .values(**payload)
            .on_conflict_do_nothing(
                constraint="uq_doc_type_instruction_versions_doc_type_code_sha256"
            )
            .returning(DocumentTypeInstructionVersion.id)
        )

        result = await self.session.execute(stmt)
        inserted_id = result.scalar_one_or_none()

        if inserted_id is not None:
            created = await self.get_by_id(inserted_id)
            if created is None:
                raise RuntimeError("Instruction version row was inserted but could not be reloaded")

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

        Почему здесь отдельный метод:
        - централизуем валидацию;
        - проще тестировать;
        - проще расширять later without touching resolve flow.
        """
        doc_type_code = str(getattr(cfg, "type_code", "") or "").strip()
        if not doc_type_code:
            raise ValueError("Cannot persist instruction version: cfg.type_code is empty")

        name = str(getattr(cfg, "name", "") or "").strip() or None

        source_yaml = getattr(cfg, "source_yaml", None)
        if not isinstance(source_yaml, str) or not source_yaml.strip():
            # Для fallback-конфигов YAML файла может не быть.
            # Тогда стабильно сериализуем parsed raw в canonical YAML,
            # чтобы persisted row всё равно содержала полный snapshot.
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

        source_kind = str(getattr(cfg, "source_kind", "") or "").strip() or "file"
        source_format = "yaml"

        effective_compiled_payload = compiled_payload
        if effective_compiled_payload is None:
            # Консервативный дефолт: сохраняем raw dict как compiled payload,
            # чтобы downstream UI/debug мог использовать структурированное представление.
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
        }

        logger.debug(
            "Built instruction version persistence payload",
            extra={
                "doc_type_code": doc_type_code,
                "source_sha256": source_sha256,
                "source_kind": source_kind,
                "has_source_path": source_path is not None,
                "has_git_commit": payload["git_commit"] is not None,
                "has_semver": payload["semver"] is not None,
            },
        )
        return payload

    async def get_latest_by_doc_type_code(
        self,
        doc_type_code: str,
        *,
        published_only: bool = True,
    ) -> DocumentTypeInstructionVersion | None:
        """
        Вернуть самую свежую persisted instruction version для doc_type_code.

        Используется для staleness detection override и для snapshot
        resolution в RunSnapshotService: "какая версия инструкции сейчас
        актуальна для этого типа документа".

        Args:
            doc_type_code: Код типа документа.
            published_only: Если True — учитывать только is_published=True.
                RunSnapshotService должен использовать published_only=True,
                чтобы draft-версии не попадали в исполняемые Run.
        """
        stmt = select(DocumentTypeInstructionVersion).where(
            DocumentTypeInstructionVersion.doc_type_code == doc_type_code
        )
        if published_only:
            stmt = stmt.where(DocumentTypeInstructionVersion.is_published.is_(True))

        stmt = stmt.order_by(DocumentTypeInstructionVersion.created_at.desc()).limit(1)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    