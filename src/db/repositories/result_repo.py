# src/db/repositories/result_repo.py

"""
Repository for CheckResult operations.

Отвечает за:
- создание результатов проверок (create);
- выборку по run (с документами и без);
- пагинацию для DD Grid;
- обновление QC-статуса.

Важно:
- этот слой не решает "что такое structured_data",
  он только аккуратно отдаёт то, что записал раннер
  (ExtractionExecutor / CheckRunner) в CheckResult.structured_data.
- контракт structured_data задаётся в api/schemas/results.py
  (StructuredField / LocationField и т.п.).
"""

import uuid
from datetime import UTC, datetime
from typing import Sequence, Any
from uuid import UUID

from sqlalchemy import func, select, update, distinct, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import DBAPIError  # важно для обработки DB-ошибок

from core.constants import CheckExecutionStatus  # новый enum для execution_status
from ..models.result import CheckResult
from ..models.document import Document  # подтягиваем документы к результатам
from db.repositories.check_result_persist_error_repo import CheckResultPersistErrorRepository

def normalize_origin_type(origin: str | None) -> str | None:
    """
    Нормализует "сырое" поле origin из БД в логический тип источника.

    Возвращает одно из:
    - "global"  — глобальный плейбук;
    - "doctype" — плейбук по типу документа;
    - "custom"  — все прочие случаи / кастомные источники;
    - None      — если origin пустой.
    """
    if origin is None:
        return None

    raw = origin
    upper = raw.upper()

    # Глобальный плейбук (старые и новые варианты)
    if upper == "GLOBAL_PLAYBOOK" or raw == "global_playbook" or raw == "project_playbook":
        return "global"

    # Проверки по типу документа
    if upper == "DOCUMENT_TYPE":
        return "doctype"

    # Всё остальное считаем кастомным/прочим источником
    return "custom"


def is_permanent_db_error(err: DBAPIError) -> bool:
    """
    Простая классификация DB-ошибок на permanent vs transient.

    Permanent (возвращаем True) — ошибки данных/схемы, которые не исчезнут
    от повторного запроса (например, слишком длинная строка для varchar).

    Transient (возвращаем False) — временные проблемы (deadlock, timeout),
    которые теоретически можно ретраить.

    ВАЖНО: здесь мы сознательно делаем минимальную классификацию.
    Потом её можно вынести в отдельный модуль ошибок и расширить.
    """
    # У DBAPIError часто есть атрибут .orig с "сырой" ошибкой драйвера.
    # Для asyncpg, например, там может быть asyncpg.exceptions.*.
    orig = getattr(err, "orig", None)

    # Если это asyncpg и есть SQLSTATE, можно использовать его:
    # 22001 — string_data_right_truncation (слишком длинная строка).
    sqlstate = getattr(orig, "sqlstate", None)
    if sqlstate == "22001":
        # StringDataRightTruncationError — data error, permanent
        return True

    # Можно добавить сюда другие коды data errors (22xxx), если нужно.
    # Пока считаем все прочие ошибки transient, чтобы не угадать лишнего.
    return False


class ResultRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
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
        quality_flags: dict | None = None,
        structured_data: dict | None = None,
        conditional_check_triggered: bool = False,
        trigger_name: str | None = None,
        origin: str | None = None,
    ) -> CheckResult:
        """Создать результат проверки."""
        cr = CheckResult(
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
            # ВАЖНО: сюда раннер кладёт JSON формата StructuredDataDict
            structured_data=structured_data,
            conditional_check_triggered=conditional_check_triggered,
            trigger_name=trigger_name,
            origin=origin,
        )

        self.session.add(cr)
        # Здесь flush оставляем "как есть", но по-хорошему,
        # для единообразия тоже стоит обернуть в try/except, как в upsert.
        await self.session.flush()
        return cr

    async def get_by_run(self, run_id: uuid.UUID, severity: str | None = None) -> list[CheckResult]:
        """Получить все результаты для run (без join с документами)."""
        stmt = select(CheckResult).where(CheckResult.run_id == run_id)
        if severity is not None:
            stmt = stmt.where(CheckResult.severity == severity)
        stmt = stmt.order_by(CheckResult.severity, CheckResult.check_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_run_with_docs(self, run_id: uuid.UUID) -> list[dict]:
        """
        Получить результаты для run с джойном документов.

        Возвращает список dict'ов, совместимых с CheckResultResponse:
        - поля из CheckResult;
        - origin / origin_type (источник определения проверки);
        - document_name, doc_type;
        - doc_classification_level, doc_classification_confidence;
        - doc_requires_manual_review.
        """
        stmt = (
            select(
                CheckResult,
                Document.filename.label("document_name"),
                Document.doc_type.label("doc_type"),
                Document.classification_level.label("doc_classification_level"),
                Document.classification_confidence.label("doc_classification_confidence"),
                Document.classification_requires_review.label("doc_requires_manual_review"),
            )
            .join(Document, Document.id == CheckResult.document_id)
            .where(CheckResult.run_id == run_id)
            .order_by(CheckResult.severity, CheckResult.check_id)
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        out: list[dict] = []
        for (
            cr,
            document_name,
            doc_type,
            doc_level,
            doc_conf,
            doc_requires_manual_review,
        ) in rows:
            # cr — ORM-объект CheckResult; берём его поля как есть
            item = {
                "id": cr.id,
                "run_id": cr.run_id,
                "document_id": cr.document_id,
                "check_id": cr.check_id,
                "check_name": cr.check_name,
                "result": cr.result,
                "severity": cr.severity,
                "value_text": cr.value_text,
                "confidence": cr.confidence,
                "detector_used": cr.detector_used,
                "quality_flags": cr.quality_flags,
                "qc_status": cr.qc_status,
                "qc_by": cr.qc_by,
                "qc_comment": cr.qc_comment,
                "qc_at": cr.qc_at,
                "created_at": cr.created_at,
                # исходное "сырое" origin
                "origin": cr.origin,
                # нормализованный тип источника для фронта и API
                "origin_type": normalize_origin_type(cr.origin),
                # обогащение из Document
                "document_name": document_name,
                "doc_type": doc_type,
                # доп. поля, которые уже ждёт фронт (через types)
                "doc_classification_level": doc_level,
                "doc_classification_confidence": doc_conf,
                "doc_requires_manual_review": doc_requires_manual_review,
                # structured_data и conditional
                # ОЖИДАНИЕ: cr.structured_data уже в формате StructuredDataDict
                "structured_data": cr.structured_data,
                "conditional_check_triggered": cr.conditional_check_triggered,
                "trigger_name": cr.trigger_name,
                "segment_id": cr.segment_id,
                "segment_type": cr.segment_type,
                "segment_title": cr.segment_title,
                "segment_order": cr.segment_order,
                "is_primary_segment": cr.is_primary_segment,
            }

            out.append(item)

        return out

    async def get_by_document(self, document_id: uuid.UUID, run_id: uuid.UUID) -> list[CheckResult]:
        """Получить все результаты для документа в рамках одного run."""
        result = await self.session.execute(
            select(CheckResult).where(
                CheckResult.document_id == document_id,
                CheckResult.run_id == run_id,
            )
        )
        return list(result.scalars().all())

    async def update_qc(
        self,
        result_id: uuid.UUID,
        qc_status: str,
        qc_by: str,
        qc_comment: str | None = None,
    ) -> CheckResult | None:
        """Обновить QC-статус одного результата."""
        stmt = (
            update(CheckResult)
            .where(CheckResult.id == result_id)
            .values(
                qc_status=qc_status,
                qc_by=qc_by,
                qc_comment=qc_comment,
                qc_at=datetime.now(UTC),
            )
            .returning(CheckResult)
        )
        result = await self.session.execute(stmt)
        cr = result.scalar_one_or_none()
        if cr:
            await self.session.flush()
        return cr

    async def bulk_update_qc(
        self,
        result_ids: list[uuid.UUID],
        qc_status: str,
        qc_by: str,
        qc_comment: str | None = None,
    ) -> int:
        """Массовое обновление QC-статуса. Возвращает количество обновлённых строк."""
        stmt = (
            update(CheckResult)
            .where(CheckResult.id.in_(result_ids))
            .values(
                qc_status=qc_status,
                qc_by=qc_by,
                qc_comment=qc_comment,
                qc_at=datetime.now(UTC),
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def count_by_severity(self, run_id: uuid.UUID) -> dict[str, int]:
        """Посчитать количество результатов по severity для run."""
        stmt = (
            select(CheckResult.severity, func.count(CheckResult.id))
            .where(CheckResult.run_id == run_id)
            .group_by(CheckResult.severity)
        )
        result = await self.session.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def get_page_for_run(
        self,
        run_id: UUID,
        page: int,
        per_page: int,
        doc_type: str | None = None,
        severity: str | None = None,
        conditional_only: bool | None = None,
        has_structured_data: bool | None = None,
    ) -> tuple[Sequence[dict], int]:
        """
        Пагинированный список результатов для одного run с фильтрами.
        Возвращает (items, total), где items — dict'ы, совместимые с CheckResultResponse.
        """
        base_stmt = (
            select(
                CheckResult,
                Document.filename.label("document_name"),
                Document.doc_type.label("doc_type"),
                Document.classification_level.label("doc_classification_level"),
                Document.classification_confidence.label("doc_classification_confidence"),
                Document.classification_requires_review.label("doc_requires_manual_review"),
            )
            .join(Document, Document.id == CheckResult.document_id)
            .where(CheckResult.run_id == run_id)
        )

        if doc_type is not None:
            base_stmt = base_stmt.where(Document.doc_type == doc_type)

        if severity is not None:
            base_stmt = base_stmt.where(CheckResult.severity == severity)

        if conditional_only is True:
            base_stmt = base_stmt.where(CheckResult.conditional_check_triggered.is_(True))

        if has_structured_data is True:
            base_stmt = base_stmt.where(CheckResult.structured_data.isnot(None))

        # total
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

        # сортировка + пагинация
        stmt = (
            base_stmt.order_by(CheckResult.created_at.desc())
            .offset((page - 1) * per_page)
            .limit(per_page)
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        items: list[dict] = []
        for (
            cr,
            document_name,
            doc_type_value,
            doc_level,
            doc_conf,
            doc_requires_manual_review,
        ) in rows:
            item = {
                "id": cr.id,
                "run_id": cr.run_id,
                "document_id": cr.document_id,
                "check_id": cr.check_id,
                "check_name": cr.check_name,
                "result": cr.result,
                "severity": cr.severity,
                "value_text": cr.value_text,
                "confidence": cr.confidence,
                "detector_used": cr.detector_used,
                "quality_flags": cr.quality_flags,
                "qc_status": cr.qc_status,
                "qc_by": cr.qc_by,
                "qc_comment": cr.qc_comment,
                "qc_at": cr.qc_at,
                "created_at": cr.created_at,
                # исходное "сырое" origin
                "origin": cr.origin,
                # нормализованный тип источника
                "origin_type": normalize_origin_type(cr.origin),
                "document_name": document_name,
                "doc_type": doc_type_value,
                "doc_classification_level": doc_level,
                "doc_classification_confidence": doc_conf,
                "doc_requires_manual_review": doc_requires_manual_review,
                # structured_data должно быть совместимо с StructuredDataDict
                "structured_data": cr.structured_data,
                "conditional_check_triggered": cr.conditional_check_triggered,
                "trigger_name": cr.trigger_name,
                "segment_id": cr.segment_id,
                "segment_type": cr.segment_type,
                "segment_title": cr.segment_title,
                "segment_order": cr.segment_order,
                "is_primary_segment": cr.is_primary_segment,
            }

            items.append(item)

        return items, total

    async def get_one(
        self,
        run_id: uuid.UUID,
        document_id: uuid.UUID,
        check_id: str,
    ) -> CheckResult | None:
        """Найти один результат по ключу (run, doc, check)."""
        stmt = select(CheckResult).where(
            CheckResult.run_id == run_id,
            CheckResult.document_id == document_id,
            CheckResult.check_id == check_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert_single_check_result(
        self,
        *,
        run_id: uuid.UUID,
        document_id: uuid.UUID,
        check_id: str,
        check_name: str,
        result: str,
        severity: str,
        value_text: str | None,
        evidence_ref: str | None,
        confidence: float | None,
        detector_used: str | None,
        quality_flags: dict | None,
        structured_data: dict | None,
        conditional_check_triggered: bool,
        trigger_name: str | None,
        origin: str | None,
        playbook_version_id: uuid.UUID | None,
        page: int | None,
        clause_uid: str | None,
        element_id: str | None,
        bbox: dict | None,
        # новые поля сегмента
        segment_id: str | None = None,
        segment_type: str | None = None,
        segment_title: str | None = None,
        segment_order: int | None = None,
        is_primary_segment: bool | None = None,
        execution_status: str,
        error_details: dict | None = None,
    ) -> CheckResult:
        """
        Создать или обновить результат одной проверки (идемпотентно по run/doc/check).

        ВАЖНО:
        - запись обёрнута в try/except DBAPIError;
        - при любой DB-ошибке делаем session.rollback();
        - дальше поднимаем понятное исключение, чтобы вызывающий код
          мог решить, ретраить задачу или считать её permanent-фейлом.
        """
        now = datetime.now(UTC)

        started_statuses = {
            CheckExecutionStatus.PENDING.value,
            CheckExecutionStatus.RUNNING.value,
            CheckExecutionStatus.SUCCESS.value,
            CheckExecutionStatus.FAILED.value,          # legacy
            CheckExecutionStatus.COMPUTE_FAILED.value,
            CheckExecutionStatus.PERSIST_FAILED.value,
            CheckExecutionStatus.TIMEOUT.value,
        }

        finished_statuses = {
            CheckExecutionStatus.SUCCESS.value,
            CheckExecutionStatus.FAILED.value,          # legacy
            CheckExecutionStatus.COMPUTE_FAILED.value,
            CheckExecutionStatus.PERSIST_FAILED.value,
            CheckExecutionStatus.TIMEOUT.value,
        }

        # Приводим входной execution_status к Enum/строке из CheckExecutionStatus.
        # Это защищает от опечаток в строках выше по стэку.
        if isinstance(execution_status, CheckExecutionStatus):
            status_value = execution_status.value
        else:
            try:
                status_value = CheckExecutionStatus(execution_status).value
            except ValueError:
                # Неизвестный статус не должен ронять persist-слой.
                # Для обратной совместимости деградируем в legacy FAILED.
                status_value = CheckExecutionStatus.FAILED.value

        try:
            existing = await self.get_one(run_id, document_id, check_id)

            if existing is None:
                cr = CheckResult(
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
                    # новые поля segment-aware provenance:
                    segment_id=segment_id,
                    segment_type=segment_type,
                    segment_title=segment_title,
                    segment_order=segment_order,
                    is_primary_segment=is_primary_segment,
                    execution_status=status_value,
                    started_at=now if status_value in started_statuses else None,
                    finished_at=now if status_value in finished_statuses else None,
                    error_details=error_details,
                )
                self.session.add(cr)
                await self.session.flush()
                return cr

            # Обновляем существующую запись (например, после partial failure/timeout)
            existing.check_name = check_name
            existing.result = result
            existing.severity = severity
            existing.value_text = value_text
            existing.evidence_ref = evidence_ref
            existing.confidence = confidence
            existing.detector_used = detector_used
            existing.quality_flags = quality_flags or {}
            existing.structured_data = structured_data
            existing.conditional_check_triggered = conditional_check_triggered
            existing.trigger_name = trigger_name
            existing.origin = origin
            existing.playbook_version_id = playbook_version_id
            existing.page = page
            existing.clause_uid = clause_uid
            existing.element_id = element_id
            existing.bbox = bbox
            # новые поля:
            existing.segment_id = segment_id
            existing.segment_type = segment_type
            existing.segment_title = segment_title
            existing.segment_order = segment_order
            existing.is_primary_segment = is_primary_segment
            existing.execution_status = status_value
            existing.error_details = error_details

            # started_at не трогаем, если уже был старт;
            # finished_at обновляем только для финальных статусов.
            if existing.started_at is None and status_value in started_statuses:
                existing.started_at = now

            if status_value in finished_statuses:
                existing.finished_at = now

            await self.session.flush()
            return existing

        except DBAPIError as err:
            # После любой ошибки flush/commit сессию нужно откатить,
            # иначе она останется в PendingRollback.
            await self.session.rollback()

            permanent = is_permanent_db_error(err)
            orig = getattr(err, "orig", None)
            sqlstate = getattr(orig, "sqlstate", None)

            payload: dict[str, Any] = {
                "run_id": str(run_id),
                "document_id": str(document_id),
                "check_id": check_id,
                "check_name": check_name,
                "result": result,
                "severity": severity,
                "value_text": value_text,
                "evidence_ref": evidence_ref,
                "confidence": confidence,
                "detector_used": detector_used,
                "quality_flags": quality_flags or {},
                "structured_data": structured_data,
                "conditional_check_triggered": conditional_check_triggered,
                "trigger_name": trigger_name,
                "origin": origin,
                "playbook_version_id": (
                    str(playbook_version_id) if playbook_version_id else None
                ),
                "page": page,
                "clause_uid": clause_uid,
                "element_id": element_id,
                "bbox": bbox,
                "segment_id": segment_id,
                "segment_type": segment_type,
                "segment_title": segment_title,
                "segment_order": segment_order,
                "is_primary_segment": is_primary_segment,
                "execution_status": execution_status,
                "error_details": error_details,
            }

            persist_error_repo = CheckResultPersistErrorRepository(self.session)
            await persist_error_repo.log_error(
                run_id=run_id,
                document_id=document_id,
                check_id=check_id,
                payload=payload,
                error_type=(
                    "permanent_db_error" if permanent else "transient_db_error"
                ),
                sqlstate=sqlstate,
                error_message=str(err),
                retryable=not permanent,
            )

            # Здесь мы поднимаем RuntimeError с понятным сообщением.
            # В реальном коде ты можешь заменить это на свои кастомные
            # исключения, например PermanentDBError/TransientDBError.
            if permanent:
                raise RuntimeError(
                    f"Permanent DB error while upserting check_result "
                    f"(run_id={run_id}, document_id={document_id}, check_id={check_id}): {err}"
                ) from err
            else:
                raise RuntimeError(
                    f"Transient DB error while upserting check_result "
                    f"(run_id={run_id}, document_id={document_id}, check_id={check_id}): {err}"
                ) from err

    async def count_distinct_checks_for_run(self, run_id: uuid.UUID) -> int:
        """
        Сколько уникальных пар (document_id, check_id) вообще есть в check_results для run.
        Это наш фактически материализованный прогресс по checks.
        """
        stmt = select(func.count()).select_from(
            select(
                distinct(CheckResult.document_id),
                CheckResult.check_id,
            )
            .where(CheckResult.run_id == run_id)
            .subquery()
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def count_finished_checks_for_run(self, run_id: uuid.UUID) -> int:
        """
        Сколько уникальных пар (document_id, check_id) уже в финальном execution_status.
        Финальные статусы: SUCCESS, COMPUTE_FAILED, PERSIST_FAILED, TIMEOUT
        (и legacy FAILED для обратной совместимости).
        """
        finished_statuses = [
            CheckExecutionStatus.SUCCESS.value,
            CheckExecutionStatus.FAILED.value,          # legacy
            CheckExecutionStatus.COMPUTE_FAILED.value,
            CheckExecutionStatus.PERSIST_FAILED.value,
            CheckExecutionStatus.TIMEOUT.value,
        ]

        stmt = select(func.count()).select_from(
            select(
                distinct(CheckResult.document_id),
                CheckResult.check_id,
            )
            .where(
                CheckResult.run_id == run_id,
                CheckResult.execution_status.in_(finished_statuses),
            )
            .subquery()
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def count_documents_fully_finished_for_run(self, run_id: uuid.UUID) -> int:
        """
        Сколько документов полностью завершили все свои checks.
        Используем для метрик «прогресс по документам» (сколько документов имеют все checks в финальном статусе).
        """
        finished_statuses = [
            CheckExecutionStatus.SUCCESS.value,
            CheckExecutionStatus.FAILED.value,          # legacy
            CheckExecutionStatus.COMPUTE_FAILED.value,
            CheckExecutionStatus.PERSIST_FAILED.value,
            CheckExecutionStatus.TIMEOUT.value,
        ]

        per_doc = (
            select(
                CheckResult.document_id,
                func.count().label("total_cnt"),
                func.sum(
                    case(
                        (
                            CheckResult.execution_status.in_(finished_statuses),
                            1,
                        ),
                        else_=0,
                    )
                ).label("finished_cnt"),
            )
            .where(CheckResult.run_id == run_id)
            .group_by(CheckResult.document_id)
            .subquery()
        )

        stmt = select(func.count()).select_from(per_doc).where(
            per_doc.c.total_cnt == per_doc.c.finished_cnt
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def has_failed_or_timed_out_checks(self, run_id: uuid.UUID) -> bool:
        """
        Есть ли по run хотя бы один check с неуспешным финальным статусом.
        """
        problematic_statuses = [
            CheckExecutionStatus.FAILED.value,          # legacy
            CheckExecutionStatus.COMPUTE_FAILED.value,
            CheckExecutionStatus.PERSIST_FAILED.value,
            CheckExecutionStatus.TIMEOUT.value,
        ]

        stmt = (
            select(CheckResult.id)
            .where(
                CheckResult.run_id == run_id,
                CheckResult.execution_status.in_(problematic_statuses),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None


    