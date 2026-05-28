# src/services/document_composition_query.py

"""
Сервис для построения composition (логических документов/сегментов) по списку документов.

Для непрофессионального программиста:

- Один физический файл в Data Room (одна запись Document) может содержать
  один или несколько логических документов (сегментов):
  основной договор, приложения, акты, счета и т.п.

- DocumentSegment описывает каждый такой логический документ в отдельной строке БД.
  Он хранит:
    * segment_id (стабильный UUID сегмента),
    * segment_order (порядок в файле),
    * segment_title / segment_type,
    * is_primary (флаг основного сегмента).

- Этот сервис НЕ меняет базу данных, а только читает:
    * последнюю версию документа (DocumentVersion),
    * сегменты этой версии (DocumentSegment),
  и на их основе строит удобную для API/Pydantic модель:
    DocumentCompositionSummary (см. api.schemas.documents).

Где используется:
- в эндпоинте списка документов сделки (GET /deals/{deal_id}/documents),
  чтобы обогатить DocumentResponse полем composition;
- может использоваться и в экспортных сценариях, если нужно
  показывать информацию о сегментах в Excel/Word/PDF.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.documents import DocumentCompositionSummary
from db.models.document import Document, DocumentSegment, DocumentVersion
from db.repositories.document_segment_repo import DocumentSegmentRepository
from db.repositories.document_version_repo import DocumentVersionRepository


class DocumentCompositionQueryService:
    """
    Read-model сервис для построения composition summary по документам.

    Важно:
    - сервис работает только на чтение (READ ONLY);
    - не изменяет таблицы Document / DocumentVersion / DocumentSegment;
    - не обращается к S3, layout'ам и extracted values — только к БД.

    Основная задача — вернуть словарь:
        { document_id: DocumentCompositionSummary | None }
    для набора документов.
    """

    def __init__(self, session: AsyncSession) -> None:
        """
        Инициализация сервиса.

        Параметр:
        - session: AsyncSession SQLAlchemy — текущая сессия базы данных.
          Обычно её предоставляет FastAPI через Depends(get_db).
        """
        self._session = session
        self._version_repo = DocumentVersionRepository(session)
        self._segment_repo = DocumentSegmentRepository(session)

    async def build_for_documents(
        self,
        documents: Sequence[Document],
    ) -> dict[uuid.UUID, DocumentCompositionSummary | None]:
        """
        Построить composition summary для списка документов.

        Формат результата:
            {
                <document_id>: DocumentCompositionSummary | None,
                ...
            }

        Для непрофессионального программиста:

        - На входе список ORM-объектов Document (строки из таблицы documents).
        - Для каждого документа мы:
            * находим его последнюю версию (DocumentVersion);
            * загружаем все сегменты этой версии (DocumentSegment);
            * на основе сегментов считаем:
                - single/multi,
                - общее количество сегментов,
                - основной сегмент (primary),
                - человекочитаемый заголовок основного сегмента.
        - Если у документа нет версий или сегментов (legacy-режим),
          возвращаем None для его composition.
        """
        if not documents:
            return {}

        doc_ids = [doc.id for doc in documents]

        # 1) Получаем последние версии для всех документов одним запросом (batch),
        #    чтобы не делать N+1 запросов к базе.
        latest_versions_by_doc = await self._version_repo.get_latest_for_documents(
            document_ids=doc_ids
        )

        # Собираем список ID версий, у которых реально есть запись.
        version_ids: list[uuid.UUID] = [version.id for version in latest_versions_by_doc.values()]
        if not version_ids:
            # Нет версий ни у одного документа — composition везде None.
            return {doc_id: None for doc_id in doc_ids}

        # 2) Загружаем сегменты для всех найденных версий одним запросом (batch).
        segments_by_version = await self._segment_repo.list_by_versions(
            document_version_ids=version_ids
        )

        # 3) Собираем итоговую карту document_id -> DocumentCompositionSummary | None.
        result: dict[uuid.UUID, DocumentCompositionSummary | None] = {}

        for doc in documents:
            version = latest_versions_by_doc.get(doc.id)
            if version is None:
                # У документа ещё нет версий — считаем, что composition не построен.
                result[doc.id] = None
                continue

            segments = segments_by_version.get(version.id, [])
            summary = self._build_for_version(version=version, segments=segments)
            result[doc.id] = summary

        return result

    def _build_for_version(
        self,
        version: DocumentVersion,
        segments: Sequence[DocumentSegment],
    ) -> DocumentCompositionSummary | None:
        """
        Построить DocumentCompositionSummary для одной версии документа.

        Правила:
        - если сегментов нет → возвращаем None (legacy / сегментация ещё не выполнялась);
        - 1 сегмент → composition_type = "single", is_composite_file = False;
        - 2+ сегментов → composition_type = "multi", is_composite_file = True;
        - основной сегмент (primary):
            * сначала ищем сегмент с is_primary = True;
            * если такого нет — берём первый по порядку (segment_order);
        - primary_segment_label:
            * сначала segment_title, если не пустой;
            * иначе segment_doc_type (результат segment-level классификации), если есть;
            * иначе segment_type (общий тип сегмента, например "appendix").
        """
        if not segments:
            return None

        segment_count = len(segments)

        if segment_count == 1:
            composition_type: str = "single"
            is_composite_file = False
        else:
            composition_type = "multi"
            is_composite_file = True

        # Ищем основной (primary) сегмент.
        primary_segment = next(
            (s for s in segments if s.is_primary),
            None,
        )
        if primary_segment is None:
            # Если в данных нет явного primary, берём первый по порядку.
            primary_segment = segments[0]

        # Строим человекочитаемое имя основного сегмента.
        # Это то, что потом фронт покажет юристу.
        primary_label = (
            (primary_segment.segment_title or "").strip()
            or (primary_segment.segment_doc_type or "").strip()
            or (primary_segment.segment_type or "").strip()
            or None
        )

        return DocumentCompositionSummary(
            composition_type=composition_type,  # "single" или "multi"
            segment_count=segment_count,
            primary_segment_id=primary_segment.segment_id,
            primary_segment_label=primary_label,
            is_composite_file=is_composite_file,
        )
