# src/services/run_analytics_service.py

"""
Аналитика качества классификации для Run.

Сервис RunAnalyticsService строит сводный отчёт по результатам
классификации документов в рамках одного run_id и возвращает его
в виде схемы ClassificationReportResponse для API.

Метод build_classification_report:
- получает Run и связанные с ним документы, по которым есть результаты;
- агрегирует статистику по уровням классификации (L0–L4, LMANUAL),
  количеству low-confidence документов и документам с неизвестным типом;
- считает покрытие триггеров (applicable_triggers) по документам;
- формирует отсортированный список документов с низкой уверенностью
  и список документов с типом Generic/Unknown/None.

Используется эндпоинтом GET /api/v1/runs/{run_id}/classification_report
в api.endpoints.runs для отдачи отчёта по качеству классификации Run.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas.runs import ClassificationReportResponse, ClassificationStats
from db.models.document import Document
from db.repositories.run_repo import RunRepository


class RunNotFoundError(Exception):
    pass


class RunAnalyticsService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.run_repo = RunRepository(session)

    async def build_classification_report(
        self,
        run_id: uuid.UUID,
        low_conf_threshold: float = 0.6,
    ) -> ClassificationReportResponse:
        # 1. Берём run
        run = await self.run_repo.get_by_id(run_id)
        if not run:
            raise RunNotFoundError

        # 2. Получаем только те document_id, для которых есть результаты этого run
        doc_ids = await self.run_repo.get_document_ids_for_run(run_id)
        if not doc_ids:
            # нет результатов — пустой отчёт
            stats = ClassificationStats(total_documents=0)
            return ClassificationReportResponse(
                run_id=run_id,
                deal_id=run.deal_id,
                total_documents=0,
                stats=stats,
                low_confidence_docs=[],
                unknown_type_docs=[],
                trigger_coverage={},
            )

        # 3. Выбираем сами документы по этим id
        stmt = select(Document).where(Document.id.in_(doc_ids))
        result = await self.session.execute(stmt)
        docs: list[Document] = list(result.scalars().all())

        # 4. Статистика по уровням
        stats = ClassificationStats(
            total_documents=len(docs),
        )

        low_confidence: list[dict[str, Any]] = []
        unknown_type: list[dict[str, Any]] = []
        trigger_coverage: dict[str, int] = {}

        level_map = {
            "L0": "l0_no_match",
            "L1": "l1_filename",
            "L2": "l2_keyword",
            "L3": "l3_semantic",
            "L4": "l4_llm",
            "LMANUAL": "l4_llm",  # любой L_manual/Lmanual → LMANUAL → l4_llm
        }

        for doc in docs:
            raw_level = getattr(doc, "classification_level", None) or ""
            # Нормализуем: убираем подчёркивания и приводим к верхнему регистру
            level = raw_level.replace("_", "").upper()

            conf = getattr(doc, "classification_confidence", 0.0) or 0.0
            triggers = getattr(doc, "applicable_triggers", None) or []

            attr = level_map.get(level)
            if attr:
                setattr(stats, attr, getattr(stats, attr) + 1)

            # low confidence
            if conf == 0 or conf < low_conf_threshold:
                stats.low_confidence_count += 1
                low_confidence.append(
                    {
                        "doc_id": str(doc.id),
                        "filename": doc.filename,
                        "doc_type": doc.doc_type,
                        "confidence": round(conf, 3),
                        "classification_level": level,
                    }
                )

            # unknown type
            if not doc.doc_type or doc.doc_type in ("Generic", "Unknown"):
                stats.unknown_doc_type_count += 1
                unknown_type.append(
                    {
                        "doc_id": str(doc.id),
                        "filename": doc.filename,
                        "detected_type": doc.doc_type,
                    }
                )

            # trigger coverage
            for t in triggers:
                trigger_coverage[t] = trigger_coverage.get(t, 0) + 1

        low_confidence_sorted = sorted(low_confidence, key=lambda x: x["confidence"])

        return ClassificationReportResponse(
            run_id=run_id,
            deal_id=run.deal_id,
            total_documents=len(docs),
            stats=stats,
            low_confidence_docs=low_confidence_sorted,
            unknown_type_docs=unknown_type,
            trigger_coverage=trigger_coverage,
        )
