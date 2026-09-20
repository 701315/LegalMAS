# src/db/repositories/check_result_repo.py

"""
Repository for persisting and querying check_results.

Инкапсулирует запись результатов проверок (checks) в таблицу CheckResult
и выборку результатов для одного документа или всей сделки в рамках
конкретного run_id.

Методы:
- create(...):
  создаёт новую запись CheckResult по именованным параметрам, которые
  приходят из CheckRunner (run_id, document_id, check_id/name, result,
  severity, value_text, evidence_ref, confidence, detector_used,
  quality_flags, structured_data, conditional_check_triggered,
  trigger_name, origin, playbook_version_id, page, clause_uid,
  element_id, bbox); добавляет объект в сессию, делает flush/refresh
  и возвращает свежий ORM‑инстанс.
- for_doc(run_id, document_id) -> list[CheckResult]:
  возвращает все результаты по одному документу в рамках указанного run,
  отсортированные по check_id (для удобного группирования по чекам).
- for_deal(run_id, document_ids) -> list[CheckResult]:
  возвращает все результаты для списка документов сделки в рамках одного run;
  при пустом списке document_ids сразу возвращает [].

Назначение:
- быть тонким слоем доступа к check_results поверх AsyncSession,
  чтобы сервисы/Runner не работали с сырыми SQL/ORM деталями напрямую.
"""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from core.result_presentation_content import build_presentation_source_hash
from ..models.run import Run
from ..models.result import CheckResult


class CheckResultRepository:
    """Repository for creating and querying check_results."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        run_id: uuid.UUID,
        document_id: uuid.UUID,
        check_id: str,
        check_name: str,
        result: str,
        severity: str,
        value_text: str | None = None,
        evidence_ref: str | None = None,
        confidence: float | None = None,
        detector_used: str | None = None,
        quality_flags: dict[str, Any] | None = None,
        structured_data: dict[str, Any] | None = None,
        conditional_check_triggered: bool = False,
        trigger_name: str | None = None,
        origin: str | None = None,
        playbook_version_id: uuid.UUID | None = None,
        page: int | None = None,
        clause_uid: str | None = None,
        element_id: str | None = None,
        bbox: dict[str, Any] | None = None,
        segment_id: str | None = None,
        segment_type: str | None = None,
        segment_title: str | None = None,
        segment_order: int | None = None,
        is_primary_segment: bool | None = None,
        chunk_id: str | None = None,
        chunk_index: int | None = None,
        context_trace: list[dict[str, Any]] | None = None,
    ) -> CheckResult:
        """
        Создать новую запись в check_results.

        Все параметры передаются именованно (как в CheckRunner),
        без обёртки в dict.
        """

        # Вычисляем хэш канонического контента
        new_hash = build_presentation_source_hash(
            check_name=check_name,
            display_text=None,
            review_message=None,
            dd_request_text=None,
        )

        # Получаем язык анализа из запущенного рана
        run_stmt = select(Run.analysis_language).where(Run.id == run_id)
        run_lang = (await self.session.execute(run_stmt)).scalar_one_or_none()

        obj = CheckResult(
            run_id=run_id,
            document_id=document_id,
            check_id=check_id,
            check_name=check_name,
            result=result,
            severity=severity,
            value_text=value_text,
            evidence_ref=evidence_ref,
            confidence=confidence,
            detector_used=detector_used,
            quality_flags=quality_flags or {},
            structured_data=structured_data,
            conditional_check_triggered=conditional_check_triggered,
            trigger_name=trigger_name,
            origin=origin,
            playbook_version_id=playbook_version_id,
            page=page,
            clause_uid=clause_uid,
            element_id=element_id,
            bbox=bbox,
            segment_id=segment_id,
            segment_type=segment_type,
            segment_title=segment_title,
            segment_order=segment_order,
            is_primary_segment=is_primary_segment,
            chunk_id=chunk_id,
            chunk_index=chunk_index,
            context_trace=context_trace,
            canonical_locale=run_lang,         # <-- ДОБАВИТЬ
            canonical_content_hash=new_hash,   # <-- ДОБАВИТЬ
            content_revision=1,                # <-- ДОБАВИТЬ
        )

        self.session.add(obj)
        # commit делает UnitOfWork; здесь только flush/refresh
        await self.session.flush()
        await self.session.refresh(obj)
        return obj

    async def for_doc(
        self,
        run_id: uuid.UUID,
        document_id: uuid.UUID,
    ) -> list[CheckResult]:
        """Получить все результаты для документа в рамках одного run."""
        stmt = (
            select(CheckResult)
            .where(
                CheckResult.run_id == run_id,
                CheckResult.document_id == document_id,
            )
            .order_by(CheckResult.check_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def for_deal(
        self,
        run_id: uuid.UUID,
        document_ids: list[uuid.UUID],
    ) -> list[CheckResult]:
        """
        Получить результаты по списку документов сделки
        в рамках одного run.
        """
        if not document_ids:
            return []

        stmt = select(CheckResult).where(
            CheckResult.run_id == run_id,
            CheckResult.document_id.in_(document_ids),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
