# src/db/repositories/document_repo.py

"""
Repository for Document CRUD and classification operations.

Этот модуль инкапсулирует всю работу с таблицей документов:

- создание записей о документах сделки;
- получение документов:
  - по id;
  - по сделке;
  - по SHA-256 (для дедупликации);
- обновление статуса документа (pending, extracting, extracted, sanitized,
  structured, classified, completed, quarantine, failed и т.д.);
- обновление результатов классификации:
  - doc_type;
  - уровень и уверенность (classification_level / classification_confidence);
  - детали классификации;
  - applicable_triggers;
  - язык, юрисдикция;
  - версия playbook;
- вспомогательные выборки для аналитики:
  - количество по статусам;
  - выборка по типу и минимальной уверенности;
  - документы с низкой уверенностью.

Отдельно важен единый контракт по ошибкам обработки:

- processing_error_details — JSON-поле в Document, куда мы пишем,
  что именно пошло не так по конкретному документу;
- методы set_failed / set_quarantined — единственные точки,
  через которые бизнес-логика и воркеры должны помечать документ
  как "FAILED" или "QUARANTINE" и записывать детали ошибки.

Структура processing_error_details:

    {
        "stage": "<имя стадии пайплайна>",
        "type": "failed" | "quarantine",
        "reason": "<машинное короткое имя причины>" (опционально),
        "message": "<человекочитаемое описание ошибки>",
        "timestamp": "<ISO8601 UTC>",
        "run_id": "<UUID Run, если есть>" (опционально)
    }

Зачем это нужно юристу и фронтенду:

- по статусу документа и полю processing_error_details UI всегда может показать,
  на каком шаге документ остановился (import, extract, pii, structure, classify,
  checks, export), и понятное сообщение, что произошло;
- все стадии пайплайна (все воркеры) используют один и тот же формат ошибки,
  поэтому фронт не должен подстраиваться под разные схемы.

Language discovery contract:

- Каноническое поле document-level discovery status: Document.language_discovery_status
- Методы для работы с ним: update_language_discovery(),
  try_mark_language_discovery_pending(), try_mark_language_discovery_processing()
- Ни один из этих методов не меняет Document.status (основной pipeline status).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from classifiers.yaml_registry import YAMLRegistry
from core.constants import DocumentStatus
from core.logging import get_logger
from ..models.document import Document
from .document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
)

logger = get_logger(__name__)


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Basic CRUD ────────────────────────────────────────────────────────────

    async def create(
        self,
        deal_id: uuid.UUID,
        bundle_id: uuid.UUID,
        filename: str,
        folder_path: str | None = None,
        sha256_file: str | None = None,
        status: str = "pending",
        source_extension: str | None = None,
        source_filetype: str | None = None,
    ) -> Document:
        doc = Document(
            deal_id=deal_id,
            bundle_id=bundle_id,
            filename=filename,
            folder_path=folder_path,
            sha256_file=sha256_file,
            status=status,
            source_extension=source_extension,
            source_filetype=source_filetype,
        )
        self.session.add(doc)
        await self.session.flush()
        return doc

    async def get_by_id(self, doc_id: uuid.UUID) -> Document | None:
        result = await self.session.execute(
            select(Document).where(Document.id == doc_id)
        )
        return result.scalar_one_or_none()

    async def get_by_deal(
        self,
        deal_id: uuid.UUID,
        status: str | None = None,
        doc_type: str | None = None,
    ) -> list[Document]:
        stmt = select(Document).where(Document.deal_id == deal_id)
        if status is not None:
            stmt = stmt.where(Document.status == status)
        if doc_type is not None:
            stmt = stmt.where(Document.doc_type == doc_type)
        stmt = stmt.order_by(Document.folder_path, Document.filename)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_sha256(self, deal_id: uuid.UUID, sha256: str) -> Document | None:
        result = await self.session.execute(
            select(Document).where(
                Document.deal_id == deal_id,
                Document.sha256_file == sha256,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_deal_id(self, deal_id: uuid.UUID) -> list[Document]:
        stmt = (
            select(Document)
            .where(Document.deal_id == deal_id)
            .order_by(Document.folder_path, Document.filename)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # ── Status updates ────────────────────────────────────────────────────────

    async def update_status(
        self,
        doc_id: uuid.UUID,
        status: str,
        **kwargs: Any,
    ) -> Document | None:
        values = {"status": status, **kwargs}
        stmt = (
            update(Document)
            .where(Document.id == doc_id)
            .values(**values)
            .returning(Document)
        )
        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()
        if doc:
            await self.session.flush()
        return doc

    async def set_failed(
        self,
        doc_id: uuid.UUID,
        *,
        stage: str,
        message: str,
        reason: str | None = None,
        run_id: uuid.UUID | None = None,
    ) -> Document | None:
        details: dict[str, object] = {
            "stage": stage,
            "type": "failed",
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if reason is not None:
            details["reason"] = reason
        if run_id is not None:
            details["run_id"] = str(run_id)

        return await self.update_status(
            doc_id,
            DocumentStatus.FAILED.value,
            processing_error_details=details,
        )

    async def set_quarantined(
        self,
        doc_id: uuid.UUID,
        *,
        stage: str,
        message: str,
        reason: str | None = None,
        run_id: uuid.UUID | None = None,
    ) -> Document | None:
        details: dict[str, object] = {
            "stage": stage,
            "type": "quarantine",
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if reason is not None:
            details["reason"] = reason
        if run_id is not None:
            details["run_id"] = str(run_id)

        return await self.update_status(
            doc_id,
            DocumentStatus.QUARANTINE.value,
            processing_error_details=details,
        )

    async def set_completed(self, doc_id: uuid.UUID) -> Document | None:
        return await self.update_status(doc_id, DocumentStatus.COMPLETED.value)

    # ── Language discovery ────────────────────────────────────────────────────
    #
    # Канонический lifecycle document-level language discovery status:
    #
    #   None → pending → processing → completed
    #                 ↘             ↘ failed
    #
    # Ни один из методов ниже не меняет Document.status.
    # Document.status — это основной pipeline status документа.
    # Document.language_discovery_status — независимый sub-lifecycle.

    async def get_for_language_discovery(
        self,
        deal_id: uuid.UUID,
        *,
        document_ids: list[uuid.UUID] | None = None,
        include_statuses: list[str | None] | None = None,
    ) -> list[Document]:
        """
        Вернуть документы сделки для этапа language discovery.

        Args:
            deal_id: Идентификатор сделки.
            document_ids: Если задан — ограничить выборку этими документами.
            include_statuses: Фильтр по language_discovery_status.
                None в списке означает «статус IS NULL».
                Если параметр не передан — возвращаются все документы сделки.
        """
        stmt = select(Document).where(Document.deal_id == deal_id)

        if document_ids:
            stmt = stmt.where(Document.id.in_(document_ids))

        if include_statuses is not None:
            conditions = []
            for st in include_statuses:
                if st is None:
                    conditions.append(Document.language_discovery_status.is_(None))
                else:
                    conditions.append(Document.language_discovery_status == st)
            if conditions:
                stmt = stmt.where(or_(*conditions))

        stmt = stmt.order_by(Document.folder_path, Document.filename, Document.id)

        result = await self.session.execute(stmt)
        documents = list(result.scalars().all())

        logger.debug(
            "Fetched documents for language discovery",
            extra={
                "deal_id": str(deal_id),
                "document_ids_filter": [str(d) for d in (document_ids or [])],
                "include_statuses": include_statuses,
                "documents_total": len(documents),
                "documents": [
                    {
                        "document_id": str(doc.id),
                        "language_discovery_status": doc.language_discovery_status,
                        "detected_languages": doc.detected_languages,
                        "filename": doc.filename,
                    }
                    for doc in documents
                ],
            },
        )

        return documents

    async def update_language_discovery(
        self,
        doc_id: uuid.UUID,
        *,
        detected_languages: list[str] | None,
        status: str,
    ) -> Document | None:
        """
        Записать финальный результат document-level language discovery.

        Обновляет только:
        - Document.language_discovery_status
        - Document.detected_languages

        Не затрагивает Document.status (основной pipeline status).
        """
        stmt = (
            update(Document)
            .where(Document.id == doc_id)
            .values(
                language_discovery_status=status,
                detected_languages=detected_languages,
            )
            .returning(Document)
        )
        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()
        if doc:
            await self.session.flush()

        logger.info(
            "Document language discovery updated",
            extra={
                "document_id": str(doc_id),
                "language_discovery_status": status,
                "detected_languages": detected_languages or [],
            },
        )

        return doc

    async def try_mark_language_discovery_pending(
        self,
        doc_id: uuid.UUID,
        *,
        allowed_current_statuses: list[str | None],
        preserve_detected_languages: list[str] | None = None,
    ) -> Document | None:
        """
        Атомарно перевести document language discovery в «pending».

        Переход выполняется только если текущий language_discovery_status
        входит в allowed_current_statuses. Если условие не выполняется —
        возвращает None без ошибки (caller решает, критично ли это).

        Args:
            doc_id: Идентификатор документа.
            allowed_current_statuses: Допустимые текущие статусы для перехода.
                None в списке означает «IS NULL».
            preserve_detected_languages: Если передан — сохраняет этот список
                языков при переходе. Обычно None (очистка при retry).

        Returns:
            Обновлённый Document если CAS-переход выполнен, иначе None.
        """
        if not allowed_current_statuses:
            raise ValueError("allowed_current_statuses must not be empty")

        conditions = []
        for st in allowed_current_statuses:
            if st is None:
                conditions.append(Document.language_discovery_status.is_(None))
            else:
                conditions.append(Document.language_discovery_status == st)

        stmt = (
            update(Document)
            .where(Document.id == doc_id)
            .where(or_(*conditions))
            .values(
                language_discovery_status="pending",
                detected_languages=preserve_detected_languages,
            )
            .returning(Document)
        )

        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()
        if doc:
            await self.session.flush()

        return doc

    async def try_mark_language_discovery_processing(
        self,
        doc_id: uuid.UUID,
        *,
        expected_current_status: str = "pending",
        preserve_detected_languages: list[str] | None = None,
    ) -> Document | None:
        """
        Атомарно перевести document language discovery в «processing».

        Переход выполняется только если текущий language_discovery_status
        равен expected_current_status. Защищает от двойного запуска worker'а.

        Args:
            doc_id: Идентификатор документа.
            expected_current_status: Ожидаемый текущий статус (по умолчанию «pending»).
            preserve_detected_languages: Если передан — сохраняет этот список языков.

        Returns:
            Обновлённый Document если CAS-переход выполнен, иначе None.
        """
        stmt = (
            update(Document)
            .where(Document.id == doc_id)
            .where(Document.language_discovery_status == expected_current_status)
            .values(
                language_discovery_status="processing",
                detected_languages=preserve_detected_languages,
            )
            .returning(Document)
        )

        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()
        if doc:
            await self.session.flush()

        return doc

    # ── Classification ────────────────────────────────────────────────────────

    async def update_classification(
        self,
        doc_id: uuid.UUID,
        doc_type: str | None,
        classification_confidence: float,
        classification_level: str | None,
        classification_details: dict,
        applicable_triggers: list[str],
        classification_requires_review: bool | None = None,
        language: str | None = None,
        jurisdiction: str | None = None,
        playbook_version_id: uuid.UUID | None = None,
        registry: YAMLRegistry | None = None,
        git_commit: str | None = None,
        semver: str | None = None,
    ) -> Document | None:
        classification_result = {
            "final_type": doc_type,
            "final_confidence": float(classification_confidence),
            "level": classification_level,
            "language": language,
            "jurisdiction": jurisdiction,
            "applicable_triggers": list(applicable_triggers or []),
            "details": classification_details or {},
        }

        if classification_requires_review is not None:
            classification_result["requires_manual_review"] = (
                classification_requires_review
            )

        return await self.save_classification_result(
            document_id=doc_id,
            classification_result=classification_result,
            playbook_version_id=playbook_version_id,
            registry=registry,
            git_commit=git_commit,
            semver=semver,
        )

    async def save_classification_result(
        self,
        *,
        document_id: uuid.UUID,
        classification_result: dict,
        playbook_version_id: uuid.UUID | None = None,
        registry: YAMLRegistry | None = None,
        git_commit: str | None = None,
        semver: str | None = None,
    ) -> Document:
        stmt = select(Document).where(Document.id == document_id)
        result = await self.session.execute(stmt)
        document = result.scalar_one_or_none()
        if document is None:
            raise ValueError(f"Document not found: {document_id}")

        final_type = classification_result.get("final_type")
        final_confidence = float(classification_result.get("final_confidence") or 0.0)
        level = classification_result.get("level")
        language = classification_result.get("language")
        jurisdiction = classification_result.get("jurisdiction")
        applicable_triggers = list(
            classification_result.get("applicable_triggers") or []
        )
        details = classification_result.get("details") or {}

        requires_review = bool(
            classification_result.get("requires_manual_review")
            or details.get("requires_manual_review")
        )

        instruction_version_id = await self._resolve_doc_type_instruction_version_id(
            final_type=final_type,
            registry=registry,
            git_commit=git_commit,
            semver=semver,
        )

        document.doc_type = final_type
        document.classification_confidence = final_confidence
        document.classification_level = level
        document.language = language
        document.jurisdiction_guess = jurisdiction
        document.applicable_triggers = applicable_triggers
        document.classification_details = classification_result
        document.classification_requires_review = requires_review
        document.doc_type_instruction_version_id = instruction_version_id

        if playbook_version_id is not None:
            document.playbook_version_id = playbook_version_id

        logger.info(
            "Document classification saved",
            extra={
                "document_id": str(document_id),
                "final_type": final_type,
                "final_confidence": final_confidence,
                "classification_level": level,
                "instruction_version_id": (
                    str(instruction_version_id) if instruction_version_id else None
                ),
                "playbook_version_id": (
                    str(playbook_version_id) if playbook_version_id else None
                ),
            },
        )

        return document

    # ── Analytics helpers ─────────────────────────────────────────────────────

    async def count_by_status(self, deal_id: uuid.UUID) -> dict[str, int]:
        stmt = (
            select(Document.status, func.count(Document.id))
            .where(Document.deal_id == deal_id)
            .group_by(Document.status)
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def get_by_type_and_confidence(
        self,
        deal_id: uuid.UUID,
        doc_type: str,
        min_confidence: float = 0.0,
    ) -> list[Document]:
        stmt = (
            select(Document)
            .where(
                Document.deal_id == deal_id,
                Document.doc_type == doc_type,
                Document.classification_confidence >= min_confidence,
            )
            .order_by(Document.classification_confidence.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_low_confidence_docs(
        self,
        deal_id: uuid.UUID,
        threshold: float = 0.6,
    ) -> list[Document]:
        stmt = (
            select(Document)
            .where(Document.deal_id == deal_id)
            .where(Document.classification_confidence < threshold)
            .where(Document.classification_confidence > 0)
            .order_by(Document.classification_confidence.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_quarantined(self, deal_id: uuid.UUID) -> list[Document]:
        stmt = select(Document).where(
            Document.deal_id == deal_id,
            Document.status == DocumentStatus.QUARANTINE.value,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def exists_manual_classified_docs(self, deal_id: uuid.UUID) -> bool:
        stmt = (
            select(func.count(Document.id))
            .where(
                Document.deal_id == deal_id,
                Document.classification_level == "L_manual",
            )
        )
        result = await self.session.execute(stmt)
        count = result.scalar_one() or 0
        return count > 0

    # ── Pagination ────────────────────────────────────────────────────────────

    async def get_page_for_deal(
        self,
        deal_id: uuid.UUID,
        page: int,
        per_page: int,
        include_classification: bool = False,
    ) -> tuple[list[Document], int]:
        offset = (page - 1) * per_page

        count_stmt = select(func.count(Document.id)).where(
            Document.deal_id == deal_id
        )
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one() or 0

        if total == 0:
            return [], 0

        stmt = select(Document).where(Document.deal_id == deal_id)

        if include_classification:
            stmt = stmt.order_by(
                Document.status,
                Document.doc_type.is_(None),
                Document.doc_type,
                Document.classification_confidence.desc().nullslast(),
                Document.folder_path,
                Document.filename,
            )
        else:
            stmt = stmt.order_by(
                Document.folder_path,
                Document.filename,
            )

        stmt = stmt.offset(offset).limit(per_page)
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    # ── Reprocessing ──────────────────────────────────────────────────────────

    async def reset_for_reprocessing(
        self,
        doc_id: uuid.UUID,
        new_status: str = "pending",
        clear_classification: bool = True,
    ) -> Document | None:
        values: dict[str, object] = {"status": new_status}

        if clear_classification:
            values.update(
                {
                    "doc_type": None,
                    "classification_confidence": None,
                    "classification_level": None,
                    "classification_details": None,
                    "applicable_triggers": None,
                }
            )

        stmt = (
            update(Document)
            .where(Document.id == doc_id)
            .values(**values)
            .returning(Document)
        )
        result = await self.session.execute(stmt)
        doc = result.scalar_one_or_none()
        if doc:
            await self.session.flush()
        return doc

    # ── Internal helpers ──────────────────────────────────────────────────────

    async def _resolve_doc_type_instruction_version_id(
        self,
        *,
        final_type: str | None,
        registry: YAMLRegistry | None = None,
        git_commit: str | None = None,
        semver: str | None = None,
    ) -> uuid.UUID | None:
        if not isinstance(final_type, str) or not final_type.strip():
            return None

        normalized = final_type.strip()
        if normalized == "UNKNOWN":
            return None

        effective_registry = registry or YAMLRegistry.get_instance()
        cfg = effective_registry.get_config(normalized)
        if cfg is None:
            return None

        repo = DocumentTypeInstructionVersionRepository(self.session)
        resolved = await repo.resolve_or_create_from_config(
            cfg,
            git_commit=git_commit,
            semver=semver,
        )
        return resolved.version.id
    

    