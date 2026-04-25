# src/db/repositories/document_segment_repo.py

"""
Repository for DocumentSegment CRUD operations.

Для непрофессионального программиста:

- Этот репозиторий управляет logical segments внутри одного физического файла.
- Используется в multi-document режиме (v2), когда structure stage
  строит file_graph и отдельные clause trees по сегментам.
- На первом этапе нам нужен простой и безопасный контракт:
  delete old segments for version -> insert fresh segments from file_graph.

Важно:
- Все операции выполняются в рамках текущей транзакции UoW.
- replace_segments() не делает commit — commit остаётся на уровне worker/service.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.document import DocumentSegment


class DocumentSegmentRepository:
    """
    Repository для CRUD-операций по DocumentSegment.

    Для непрофессионального программиста:

    - DocumentSegment описывает один логический документ внутри физического файла.
    - Этот репозиторий позволяет:
      * получить все сегменты по версии или документу;
      * удалить старые сегменты и сохранить новые;
      * проверить, у всех ли сегментов построены чанки;
      * (новое) найти primary-сегмент, найти сегмент по segment_id;
      * (новое) обновить ссылки на артефакты сегмента (clause_tree / chunks).
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # -------------------------------------------------------------------------
    # Базовые выборки
    # -------------------------------------------------------------------------

    async def list_by_version(
        self,
        document_version_id: uuid.UUID,
    ) -> list[DocumentSegment]:
        """
        Вернуть все сегменты для указанной версии документа.

        Для непрофессионального программиста:
        - Один DocumentVersion может содержать несколько сегментов (основной договор
          + приложения, акты и т.п.).
        - Этот метод даёт полный список сегментов по version_id в порядке segment_order.
        """
        result = await self.session.execute(
            select(DocumentSegment)
            .where(DocumentSegment.document_version_id == document_version_id)
            .order_by(DocumentSegment.segment_order.asc())
        )
        return list(result.scalars().all())

    async def list_by_versions(
        self,
        document_version_ids: Sequence[uuid.UUID],
    ) -> dict[uuid.UUID, list[DocumentSegment]]:
        """
        Вернуть сегменты сразу для нескольких версий документов.

        Формат результата:
            {
                <document_version_id>: [DocumentSegment, ...],
                ...
            }

        Для непрофессионального программиста:
        - Этот метод нужен, когда у нас есть страница документов в UI;
        - у каждого документа есть своя последняя версия (DocumentVersion);
        - для каждой версии есть список сегментов (DocumentSegment);
        - чтобы не дергать базу в цикле (N+1 запрос), мы делаем
          один batch-запрос и раскладываем результаты по словарю.

        Поведение:
        - если у какой-то версии нет сегментов, она просто не попадёт
          в результирующий словарь;
        - метод не меняет БД, он только читает данные.
        """
        if not document_version_ids:
            return {}

        unique_version_ids = list(dict.fromkeys(document_version_ids))

        stmt = (
            select(DocumentSegment)
            .where(DocumentSegment.document_version_id.in_(unique_version_ids))
            .order_by(
                DocumentSegment.document_version_id.asc(),
                DocumentSegment.segment_order.asc(),
            )
        )
        result = await self.session.execute(stmt)
        segments = list(result.scalars().all())

        by_version: dict[uuid.UUID, list[DocumentSegment]] = {}
        for seg in segments:
            by_version.setdefault(seg.document_version_id, []).append(seg)

        return by_version

    async def list_by_document(
        self,
        document_id: uuid.UUID,
    ) -> list[DocumentSegment]:
        """
        Вернуть все сегменты по документу (по всем версиям).

        Для непрофессионального программиста:
        - Если по файлу создавались несколько версий (DocumentVersion),
          этот метод вернёт сегменты для всех версий сразу.
        - Обычно в runtime нас интересует только последняя версия, но
          для аудита/аналитики иногда нужен полный список.
        """
        result = await self.session.execute(
            select(DocumentSegment)
            .where(DocumentSegment.document_id == document_id)
            .order_by(
                DocumentSegment.document_version_id.asc(),
                DocumentSegment.segment_order.asc(),
            )
        )
        return list(result.scalars().all())

    async def get_by_segment_id(
        self,
        document_version_id: uuid.UUID,
        segment_id: str,
    ) -> DocumentSegment | None:
        """
        Найти один сегмент по document_version_id и segment_id.

        Для непрофессионального программиста:
        - segment_id — детерминированный UUID сегмента (строка),
          который генерируется из document_id + segment_order.
        - Этот метод нужен, когда у нас есть только segment_id
          (например, из file_graph или чанков), и нужно найти запись в БД.
        """
        result = await self.session.execute(
            select(DocumentSegment).where(
                DocumentSegment.document_version_id == document_version_id,
                DocumentSegment.segment_id == segment_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_primary_by_version(
        self,
        document_version_id: uuid.UUID,
    ) -> DocumentSegment | None:
        """
        Вернуть primary-сегмент для указанной версии документа.

        Для непрофессионального программиста:
        - is_primary=True означает, что этот сегмент считается "основным"
          документом в файле (обычно основной договор).
        - По контракту в одной версии должен быть ровно один такой сегмент.
        """
        result = await self.session.execute(
            select(DocumentSegment).where(
                DocumentSegment.document_version_id == document_version_id,
                DocumentSegment.is_primary.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_primary_by_document(
        self,
        document_id: uuid.UUID,
    ) -> list[DocumentSegment]:
        """
        Вернуть primary-сегменты по всем версиям документа.

        Для непрофессионального программиста:
        - Если документ переобрабатывался и получил несколько версий,
          у каждой версии есть свой primary-сегмент.
        - Этот метод полезен для аналитики и для сложных сценариев
          REUSE_STRUCTURE / FULL_RERUN.
        """
        result = await self.session.execute(
            select(DocumentSegment).where(
                DocumentSegment.document_id == document_id,
                DocumentSegment.is_primary.is_(True),
            )
        )
        return list(result.scalars().all())

    # -------------------------------------------------------------------------
    # Проверка наличия чанков у всех сегментов
    # -------------------------------------------------------------------------

    async def all_segments_have_chunk_refs(
        self,
        document_version_id: uuid.UUID,
    ) -> bool:
        """
        Проверить, у всех ли сегментов версии заполнено поле segment_chunks_ref.

        Для непрофессионального программиста:
        - segment_chunks_ref — это ссылка в S3 на чанки конкретного сегмента.
        - True означает, что стадия CHUNKS полностью отработала по всем сегментам.
        """
        summary = await self.get_chunk_refs_summary(document_version_id)
        return (
            summary["total_segments"] > 0
            and summary["segments_with_chunks"] == summary["total_segments"]
        )

    async def get_chunk_refs_summary(
        self,
        document_version_id: uuid.UUID,
    ) -> dict[str, int]:
        """
        Вернуть сводку по тому, сколько сегментов и у скольких есть segment_chunks_ref.

        Формат:
            {
                "total_segments": <общее количество сегментов>,
                "segments_with_chunks": <сколько сегментов имеют segment_chunks_ref != NULL>,
            }
        """
        total_stmt = select(func.count()).select_from(DocumentSegment).where(
            DocumentSegment.document_version_id == document_version_id
        )
        total = (await self.session.execute(total_stmt)).scalar_one()

        with_chunks_stmt = select(func.count()).select_from(DocumentSegment).where(
            DocumentSegment.document_version_id == document_version_id,
            DocumentSegment.segment_chunks_ref.is_not(None),
        )
        with_chunks = (await self.session.execute(with_chunks_stmt)).scalar_one()

        return {
            "total_segments": int(total or 0),
            "segments_with_chunks": int(with_chunks or 0),
        }

    # -------------------------------------------------------------------------
    # Подсчёт сегментов для orchestration (multi-document пайплайн)
    # -------------------------------------------------------------------------

    async def count_by_version_and_has_segment_id(
        self,
        document_version_id: uuid.UUID,
    ) -> int:
        """
        Сколько сегментов версии реально участвуют в multi-document пайплайне.

        Базовый критерий:
        - segment_id IS NOT NULL.
        Если позже появится явный флаг "is_logical_document", критерий нужно
        перенести сюда, не меняя вызовы репозитория.
        """
        stmt = (
            select(func.count(DocumentSegment.id))
            .where(DocumentSegment.document_version_id == document_version_id)
            .where(DocumentSegment.segment_id.is_not(None))
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def count_unclassified_for_version(
        self,
        document_version_id: uuid.UUID,
    ) -> int:
        """
        Сколько релевантных сегментов версии ещё не имеют финального
        segment-level результата классификации.

        Критерий "классифицирован":
        - есть либо segment_doc_type, либо segment_classification_level.
        """
        stmt = (
            select(func.count(DocumentSegment.id))
            .where(DocumentSegment.document_version_id == document_version_id)
            .where(DocumentSegment.segment_id.is_not(None))
            .where(func.coalesce(DocumentSegment.segment_doc_type, "") == "")
            .where(func.coalesce(DocumentSegment.segment_classification_level, "") == "")
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    # -------------------------------------------------------------------------
    # Массовая замена сегментов (используется стадией STRUCTURE)
    # -------------------------------------------------------------------------

    async def delete_by_version(
        self,
        document_version_id: uuid.UUID,
    ) -> None:
        """
        Удалить все сегменты для указанной версии документа.

        Важно:
        - метод не делает commit, он работает в рамках текущего UoW/транзакции;
        - обычно его вызывает replace_segments().
        """
        await self.session.execute(
            delete(DocumentSegment).where(
                DocumentSegment.document_version_id == document_version_id
            )
        )

    async def bulk_create(
        self,
        items: Sequence[dict],
    ) -> list[DocumentSegment]:
        """
        Массово создать сегменты из списка словарей.

        Для непрофессионального программиста:
        - каждый item — это dict с полями для конструктора DocumentSegment;
        - метод проверяет наличие обязательных полей и добавляет строки в сессию.
        """
        rows: list[DocumentSegment] = []

        required_keys = {
            "document_version_id",
            "document_id",
            "segment_id",
            "segment_order",
            "segment_type",
            "page_start",
            "page_end",
            "is_primary",
            "confidence",
        }

        for index, item in enumerate(items):
            missing = required_keys.difference(item.keys())
            if missing:
                raise ValueError(
                    f"DocumentSegment item at index {index} is missing keys: {sorted(missing)}"
                )

            row = DocumentSegment(**item)
            self.session.add(row)
            rows.append(row)

        return rows

    async def replace_segments(
        self,
        *,
        document_version_id: uuid.UUID,
        items: Sequence[dict],
    ) -> list[DocumentSegment]:
        """
        Безопасно заменить все сегменты версии новыми.

        Что происходит:
        - сначала удаляем все старые сегменты для указанной версии;
        - затем, если items не пустой, создаём новые;
        - делаем flush(), но не commit — commit остаётся на уровне worker/service.
        """
        await self.delete_by_version(document_version_id)

        if not items:
            await self.session.flush()
            return []

        rows = await self.bulk_create(items)
        await self.session.flush()
        return rows

    # -------------------------------------------------------------------------
    # Обновление артефактов сегмента (clause_tree, chunks, meta)
    # -------------------------------------------------------------------------

    async def update_segment_artifacts(
        self,
        *,
        document_version_id: uuid.UUID,
        segment_id: str,
        segment_clause_tree_ref: str | None = None,
        segment_chunks_ref: str | None = None,
        segment_meta: dict | None = None,
    ) -> DocumentSegment | None:
        """
        Обновить ссылки на артефакты одного сегмента.

        Для непрофессионального программиста:
        - этот метод удобно вызывать после того, как STRUCTURE/CHUNKS
          сохранили артефакты в S3 и вернули URI.
        - можно обновлять только часть полей (например, только segment_chunks_ref).
        """
        values: dict[str, object] = {}
        if segment_clause_tree_ref is not None:
            values["segment_clause_tree_ref"] = segment_clause_tree_ref
        if segment_chunks_ref is not None:
            values["segment_chunks_ref"] = segment_chunks_ref
        if segment_meta is not None:
            values["segment_meta"] = segment_meta

        if not values:
            # Нечего обновлять — возвращаем текущий сегмент как есть.
            return await self.get_by_segment_id(document_version_id, segment_id)

        stmt = (
            update(DocumentSegment)
            .where(
                DocumentSegment.document_version_id == document_version_id,
                DocumentSegment.segment_id == segment_id,
            )
            .values(**values)
            .returning(DocumentSegment)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            await self.session.flush()
        return row

    async def bulk_update_segment_chunks_ref(
        self,
        *,
        document_version_id: uuid.UUID,
        items: Sequence[tuple[str, str]],
    ) -> None:
        """
        Массово обновить segment_chunks_ref для нескольких сегментов.

        Параметр items:
        - список кортежей (segment_id, segment_chunks_ref).

        Для непрофессионального программиста:
        - удобно, когда стадия CHUNKS за один проход создаёт чанки
          для всех сегментов и хочет разом записать ссылки в БД.
        """
        for segment_id, chunks_ref in items:
            stmt = (
                update(DocumentSegment)
                .where(
                    DocumentSegment.document_version_id == document_version_id,
                    DocumentSegment.segment_id == segment_id,
                )
                .values(segment_chunks_ref=chunks_ref)
            )
            await self.session.execute(stmt)

        await self.session.flush()

    # -------------------------------------------------------------------------
    # Обновление segment-level классификации
    # -------------------------------------------------------------------------

    async def update_classification_for_segment(
        self,
        *,
        document_version_id: uuid.UUID,
        segment_id: str,
        segment_doc_type: str | None,
        segment_confidence: float | None,
        segment_level: str | None,
        segment_confidence_zone: str | None,
        segment_applicable_triggers: list[str] | None,
        segment_details: dict | None,
    ) -> DocumentSegment | None:
        """
        Обновить поля segment-level классификации для одного сегмента.

        Для непрофессионального программиста:
        - этот метод вызывается после того, как HybridClassifier.classify_segment(...)
          вернул результат для конкретного segment_id;
        - мы аккуратно записываем только итоговые агрегированные поля:
          segment_doc_type, уверенность, уровень, зону уверенности,
          список сработавших триггеров и полный JSON details.
        - метод работает в рамках текущей транзакции UoW и не делает commit.
        """
        values: dict[str, object] = {
            "segment_doc_type": segment_doc_type,
            "segment_classification_confidence": float(segment_confidence or 0.0)
            if segment_confidence is not None
            else None,
            "segment_classification_level": segment_level,
            "segment_confidence_zone": segment_confidence_zone,
            "segment_applicable_triggers": list(segment_applicable_triggers or []),
            "segment_classification_details": segment_details or {},
        }

        stmt = (
            update(DocumentSegment)
            .where(
                DocumentSegment.document_version_id == document_version_id,
                DocumentSegment.segment_id == segment_id,
            )
            .values(**values)
            .returning(DocumentSegment)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        if row:
            await self.session.flush()
        return row
    
    
        