# src/db/repositories/document_repo.py

"""
Repository for Document CRUD and classification operations.

Этот модуль инкапсулирует всю работу с таблицей документов:

- создание записей о документах сделки;
- получение документов:
  - по id;
  - по сделке;
  - по SHA‑256 (для дедупликации);
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

- processing_error_details — JSON‑поле в Document, куда мы пишем,
  что именно пошло не так по конкретному документу;
- методы set_failed / set_quarantined — единственные точки,
  через которые бизнес‑логика и воркеры должны помечать документ
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
  на каком шаге документ остановился (import, extract, pii, structure, classify, checks, export),
  и понятное сообщение, что произошло;
- все стадии пайплайна (все воркеры) используют один и тот же формат ошибки,
  поэтому фронт не должен подстраиваться под разные схемы.
"""

import uuid

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.constants import DocumentStatus
from ..models.document import Document


class DocumentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

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
        """
        Создать новую запись документа в сделке.

        Для юриста это означает:
        - «в системе появился ещё один документ по сделке»;
        - документ пока может быть даже не обработан (status=pending).
        """
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
        """Вернуть документ по ID (или None, если не найден)."""
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
        """
        Вернуть документы по сделке, опционально фильтруя по статусу и типу.

        Это основной метод, через который фронт получает список документов
        для таблицы документов по сделке.
        """
        stmt = select(Document).where(Document.deal_id == deal_id)
        if status is not None:
            stmt = stmt.where(Document.status == status)
        if doc_type is not None:
            stmt = stmt.where(Document.doc_type == doc_type)
        stmt = stmt.order_by(Document.folder_path, Document.filename)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_sha256(self, deal_id: uuid.UUID, sha256: str) -> Document | None:
        """
        Найти документ по SHA256‑хэшу внутри сделки (для дедупликации).

        Используется, чтобы:
        - не создавать дубликаты документов;
        - помечать новые загрузки как DUPLICATE, если такой файл уже есть.
        """
        result = await self.session.execute(
            select(Document).where(
                Document.deal_id == deal_id,
                Document.sha256_file == sha256,
            )
        )
        return result.scalar_one_or_none()

    async def update_status(self, doc_id: uuid.UUID, status: str, **kwargs) -> Document | None:
        """
        Обновить статус документа и дополнительные поля.

        Важно:
        - этот метод не навязывает формат processing_error_details;
        - для FAILED / QUARANTINE нужно использовать set_failed / set_quarantined,
          чтобы не потерять единый контракт по ошибкам.
        """
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
        """
        Перевести документ в FAILED и записать детали ошибки в processing_error_details.

        Использовать этот метод должны все стадии пайплайна (import, extract, pii,
        structure, classify, checks, export), когда ошибка по документу:
        - фатальна для этого документа;
        - и мы больше не можем продолжать обработку (например, битый PDF, нет clause_tree).

        Поле stage должно отражать стадию пайплайна, на которой остановился документ:
        - "import", "extract", "pii", "structure", "classify", "checks", "export" и т.п.
        """
        from datetime import datetime, UTC

        details: dict[str, object] = {
            "stage": stage,
            "type": "failed",
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        if reason is not None:
            # reason — короткий машинный код причины (например, "pdf_corrupted").
            details["reason"] = reason
        if run_id is not None:
            # run_id — чтобы фронт мог показать, в рамках какого Run произошла ошибка.
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
        """
        Перевести документ в QUARANTINE и записать детали ошибки.

        Использовать, когда:
        - документ формально обработан, но есть сомнения в корректности результата;
        - требуется ручная проверка юристом (например, очень плохое качество OCR,
          подозрение на неправильную классификацию и т.п.).

        Для юриста это выглядит как отдельный статус "quarantine" с пояснением,
        что именно вызывает сомнение.
        """
        from datetime import datetime, UTC

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
        """
        Перевести документ в статус COMPLETED (полный анализ выполнен).

        Важно:
        - этот метод используется, когда по документу успешно прошли все стадии
          пайплайна, включая проверки по плейбуку (checks).
        - в отличие от FAILED / QUARANTINE, здесь мы не пишем processing_error_details,
          потому что это "нормальное" успешное завершение обработки.
        """
        return await self.update_status(
            doc_id,
            DocumentStatus.COMPLETED.value,
        )


    async def update_classification(
        self,
        doc_id: uuid.UUID,
        doc_type: str,
        classification_confidence: float,
        classification_level: str,
        classification_details: dict,
        applicable_triggers: list[str],
        language: str | None = None,
        jurisdiction: str | None = None,
        playbook_version_id: uuid.UUID | None = None,
    ) -> Document | None:
        """
        Обновить результаты классификации документа.

        Это вызывается после успешной работы классификатора:
        - сохранение типа договора (doc_type);
        - уровня (L0–L4) и уверенности;
        - детальной информации о том, почему выбрана такая классификация;
        - языковых и юрисдикционных метаданных;
        - ID версии плейбука, по которому классифицировали документ.
        """
        values = {
            "doc_type": doc_type,
            "classification_confidence": classification_confidence,
            "classification_level": classification_level,
            "classification_details": classification_details,
            "applicable_triggers": applicable_triggers,
        }

        # Обновляем язык и юрисдикцию, если они переданы.
        if language:
            values["language"] = language
        if jurisdiction:
            values["jurisdiction_guess"] = jurisdiction

        if playbook_version_id is not None:
            values["playbook_version_id"] = playbook_version_id

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

    async def count_by_status(self, deal_id: uuid.UUID) -> dict[str, int]:
        """
        Посчитать количество документов по статусам для сделки.

        Фронт может использовать это для сводки:
        - сколько документов в работе;
        - сколько уже полностью обработаны;
        - сколько в quarantine / failed.
        """
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
        """
        Вернуть документы указанного типа с минимальной уверенностью классификации.

        Удобно, например, чтобы:
        - выбрать «подозрительные» договора определённого типа
          (ниже некоторого порога уверенности).
        """
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
        """
        Вернуть документы с низкой уверенностью классификации
        для указанной сделки.

        Используется, чтобы:
        - подсветить юристу документы, которые стоит посмотреть вручную.
        """
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
        """
        Вернуть все документы в статусе QUARANTINE для сделки.

        Это даёт фронту возможность построить отдельный список
        «Документы, требующие ручной проверки».
        """
        stmt = select(Document).where(
            Document.deal_id == deal_id,
            Document.status == DocumentStatus.QUARANTINE.value,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def reset_for_reprocessing(
        self,
        doc_id: uuid.UUID,
        new_status: str = "pending",
        clear_classification: bool = True,
    ) -> Document | None:
        """
        Сбросить документ для повторной обработки.

        Что происходит:
        - статус -> new_status (по умолчанию 'pending');
        - при clear_classification=True обнуляются поля классификации.

        Это удобно, когда:
        - юрист или система хочет перепройти весь пайплайн по документу
          (например, после обновления моделей или плейбука).
        """
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

    async def get_page_for_deal(
        self,
        deal_id: uuid.UUID,
        page: int,
        per_page: int,
        include_classification: bool = False,
    ) -> tuple[list[Document], int]:
        """
        Вернуть страницу документов сделки + общее количество.

        Это основа для пагинации в UI:
        - список документов по страницам;
        - возможность сортировать по статусу/типу/уверенности.
        """
        offset = (page - 1) * per_page

        # 1) total
        count_stmt = select(func.count(Document.id)).where(Document.deal_id == deal_id)
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one() or 0

        if total == 0:
            return [], 0

        # 2) страница
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

    async def list_by_deal_id(self, deal_id: uuid.UUID) -> list[Document]:
        """
        Вернуть все документы по сделке (без пагинации), для экспорта.

        Порядок — как в обычной таблице: по folder_path, filename.
        """
        stmt = (
            select(Document)
            .where(Document.deal_id == deal_id)
            .order_by(Document.folder_path, Document.filename)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def exists_manual_classified_docs(self, deal_id: uuid.UUID) -> bool:
        """
        Проверить, есть ли в сделке документы с ручной классификацией.

        Для первого этапа считаем, что "ручная классификация" = уровень L_manual.
        В будущем можно уточнить логику (учитывать последний run, дату изменения и т.п.).
        """

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
