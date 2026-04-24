# src/engine/runner.py

"""
Runner: classification + triggers.

Назначение:
- Оркестрирует пайплайн анализа документов сделки:
  1) учёт дубликатов и master-документов (families).
  2) каскадная классификация L1–L3 (имя файла, заголовок, семантика).
  3) Детекция триггеров по документу/семье.

Основные шаги:
1. Получает non-duplicate документы сделки через RunnerRepository.
2. Для каждого документа вызывает HybridClassifier.classify_document(doc_id), который:
   - при наличии master-документа может скопировать классификацию (уровень "COPIED"),
   - собирает сигналы L1/L2/L3 и возвращает:
        * final_type, final_confidence, level,
        * language, jurisdiction,
        * applicable_triggers (если есть),
        * подробные details (levels_tried, candidates, voting и т.п.).
3. Обновляет поля документа:
   - doc_type, classification_confidence, classification_level,
     classification_details, language, jurisdiction.
4. Вызывает TriggerDetector для расчёта триггеров по документу/семье и
   объединяет их с триггерами из результата классификатора, записывая
   итоговый список в doc.applicable_triggers.
5. Возвращает агрегированную статистику по сделке:
   docs_total, docs_classified.

Архитектура:
- Работает поверх асинхронного UnitOfWork (db_uow), сам сессии не создаёт.
- Должен вызываться только внутри контекста:
    async with db_uow() as uow:
        runner = Runner(uow)
        stats = await runner.run_deal(deal_id)
"""

import uuid
from typing import Any

from classifiers.stage8.hybrid_classifier import HybridClassifier
from core.logging import get_logger
from db.repositories.runner_repo import RunnerRepository
from db.repositories.document_version_repo import DocumentVersionRepository
from db.repositories.document_segment_repo import DocumentSegmentRepository
from engine.checks.executor import CheckExecutor
from engine.content.document_content_service import (
    ClauseTreeStorageClient,
    DocumentContentService,
)
from engine.triggers.detector import TriggerDetector

logger = get_logger(__name__)


class Runner:
    def __init__(
        self,
        uow,
        llm_client=None,
        content_service: DocumentContentService | None = None,
    ):
        """
        uow: асинхронный UnitOfWork из db_uow().
        Runner отвечает только за:
        - выбор non-duplicate документов сделки,
        - классификацию документов,
        - детекцию и запись триггеров.
        Runner НЕ создаёт записей в check_results.
        """
        self.uow = uow
        self.repo = RunnerRepository(uow.session)
        self.version_repo = DocumentVersionRepository(uow.session)
        self.segment_repo = DocumentSegmentRepository(uow.session)

        # Сервис контента: clause tree → чанки, header/snippet
        # (сейчас нужен для классификатора; для checks используется
        # отдельный компонент оркестрации проверок).
        self.content_service = content_service or DocumentContentService(
            uow.session,
            ClauseTreeStorageClient(),
        )

        self.classifier = HybridClassifier(uow, self.content_service)
        self.trigger_detector = TriggerDetector(uow)

        # Эти поля остаются на будущее, чтобы другой компонент мог
        # использовать их для проверок, но сам Runner их не вызывает.
        self.check_executor = CheckExecutor(llm_client or self._dummy_llm_client)

    class _dummy_llm_client:
        @staticmethod
        def complete(prompt: str) -> str:
            return '{"found": false, "evidence": "", "confidence": 0.0}'


    async def _classify_segments_for_document(self, doc) -> int:
        """
        Выполнить segment-level классификацию для последней версии документа.

        Для непрофессионального программиста:
        - Если у документа нет сегментов, метод просто ничего не делает.
        - Если сегменты есть, мы проходим по каждому сегменту,
          берём его текст, отправляем в HybridClassifier.classify_segment(...),
          а потом сохраняем результат в таблицу DocumentSegment.
        - Это нужно, чтобы следующий этап (checks) мог работать
          не только по doc.doc_type, но и по segment_doc_type.
        
        Возвращает:
        - сколько сегментов реально удалось классифицировать.
        """
        version = await self.version_repo.get_latest(doc.id)
        if not version:
            return 0

        segments = await self.segment_repo.list_by_version(version.id)
        if not segments:
            return 0

        classified_segments = 0

        for segment in segments:
            segment_id = getattr(segment, "segment_id", None)
            if not segment_id:
                continue

            try:
                segment_text = await self.content_service.get_segment_text(
                    document_version_id=version.id,
                    segment_id=segment_id,
                    max_chars=12000,
                )

                if not segment_text or not segment_text.strip():
                    logger.info(
                        "Runner: segment classification skipped because text is empty",
                        extra={
                            "doc_id": str(getattr(doc, "id", None)),
                            "document_version_id": str(version.id),
                            "segment_id": segment_id,
                        },
                    )
                    continue

                class_result = await self.classifier.classify_segment(
                    segment_id=segment_id,
                    text=segment_text,
                    filename=getattr(doc, "filename", "") or "",
                    folder_path=getattr(doc, "folder_path", "") or getattr(doc, "folder", "") or "",
                    language_hint=getattr(doc, "language", None),
                    jurisdiction_hint=getattr(doc, "jurisdiction", None),
                )

                await self.segment_repo.update_classification_for_segment(
                    document_version_id=version.id,
                    segment_id=segment_id,
                    segment_doc_type=class_result.get("final_type"),
                    segment_confidence=class_result.get("final_confidence"),
                    segment_level=class_result.get("level"),
                    segment_confidence_zone=(class_result.get("details") or {}).get("confidence_zone"),
                    segment_applicable_triggers=class_result.get("applicable_triggers") or [],
                    segment_details=class_result,
                )

                classified_segments += 1

            except Exception as e:
                logger.exception(
                    "Runner: segment classification failed",
                    extra={
                        "doc_id": str(getattr(doc, "id", None)),
                        "document_version_id": str(version.id),
                        "segment_id": segment_id,
                        "error": str(e),
                    },
                )

        return classified_segments


    async def run_deal(self, deal_id: str, run_id: uuid.UUID) -> dict:
        """
        Полный async‑пайплайн по сделке (без выполнения checks):
        - классификация (HybridClassifier, L1–L3 + Stage 7 dedup),
        - определение триггеров.

        Runner:
        - обновляет только документы и их триггеры,
        - возвращает статистику по документам,
        - НЕ создаёт строки в check_results.
        """
        logger.info("Runner started", deal_id=str(deal_id))

        docs = await self.repo.get_non_duplicate_docs(deal_id)

        stats: dict = {
            "deal_id": str(deal_id),
            "docs_total": len(docs),
            "docs_classified": 0,
            "segments_classified": 0,
        }

        for doc in docs:
            # 1. Сначала document-level классификация (как и раньше).
            class_result = await self.classifier.classify_document(str(doc.id))

            doc.doc_type = class_result.get("final_type")
            doc.classification_confidence = class_result.get("final_confidence", 0.0)
            doc.classification_level = class_result.get("level")
            doc.classification_details = class_result

            if hasattr(doc, "language"):
                doc.language = class_result.get("language")
            if hasattr(doc, "jurisdiction"):
                doc.jurisdiction = class_result.get("jurisdiction")

            # 2. Затем document-level triggers (как и раньше).
            triggers = await self.trigger_detector.detect_triggers(doc)
            triggers_from_classifier = class_result.get("applicable_triggers") or []
            merged_triggers = sorted(set(triggers or []) | set(triggers_from_classifier))
            doc.applicable_triggers = merged_triggers

            # 3. После этого — segment-level классификация.
            #    Это не заменяет document-level результат, а дополняет его.
            classified_segments = await self._classify_segments_for_document(doc)
            stats["segments_classified"] += classified_segments

            # ORM-сессия UoW отслеживает doc, отдельный вызов repo не нужен.
            stats["docs_classified"] += 1

        # commit сделает db_uow() при выходе из контекста
        logger.info("Runner finished", **stats)
        return stats
