# src/db/repositories/result_repo.py

"""
Repository for CheckResult operations.

Отвечает за:
- создание результатов проверок (create);
- выборку по run (с документами и без);
- пагинацию для DD Grid;
- обновление QC-статуса.

"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import case, distinct, func, select, update, tuple_
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from core.anchors.models import CheckAnchor
from core.anchors.selection import method_strength, select_primary_anchor
from core.check_result_persist_errors import (
    CheckResultPersistPermanentError,
    CheckResultPersistTransientError,
)
from core.constants import CheckExecutionStatus
from core.logging import get_logger
from db.repositories.check_result_anchor_repo import CheckResultAnchorRepository
from db.repositories.check_result_persist_error_repo import CheckResultPersistErrorRepository
from core.result_presentation_content import build_presentation_source_hash
from ..models.run import Run
from ..models.result import CheckResultPresentation
from ..models.document import Document
from ..models.result import CheckResult

logger = get_logger(__name__)

# B4: hard cap on anchors persisted per CheckResult.
# Защита от per-finding anchor explosion; при превышении оставляем
# топ-N по силе метода (tie-break по anchor_confidence).
_MAX_ANCHORS_PER_CHECK_RESULT: int = 5



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

    if upper == "GLOBAL_PLAYBOOK" or raw == "global_playbook" or raw == "project_playbook":
        return "global"

    if upper == "DOCUMENT_TYPE":
        return "doctype"

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
    orig = getattr(err, "orig", None)
    sqlstate = getattr(orig, "sqlstate", None)

    if sqlstate == "22001":
        return True

    return False


def _safe_truncate(value: str | None, max_len: int, field_name: str, check_id: str) -> str | None:
    """
    Безопасно усечь строку до max_len символов для защиты от
    StringDataRightTruncationError (VARCHAR overflow).

    Hot-fix до выполнения миграции БД, расширяющей колонки до VARCHAR(50).
    Логирует предупреждение при каждом усечении для отслеживания.
    """
    if value is None:
        return None
    if len(value) <= max_len:
        return value
    truncated = value[:max_len]
    logger.warning(
        "ResultRepository: truncating field to fit DB column",
        extra={
            "field": field_name,
            "original_len": len(value),
            "max_len": max_len,
            "original": value,
            "truncated": truncated,
            "check_id": check_id,
        },
    )
    return truncated


# ── Canonical display semantics block для dict output ────────────────────────
# Вынесен как helper чтобы не дублировать в трёх местах.


def _display_semantics_dict(cr: CheckResult) -> dict[str, Any]:
    """
    Вернуть словарь canonical display semantics полей из ORM-объекта CheckResult.

    Используется в get_by_run_with_docs и get_page_for_run чтобы
    не дублировать одинаковый блок полей.
    """
    return {
        "ui_mode": cr.ui_mode,
        "display_text": cr.display_text,
        "machine_reason_code": cr.machine_reason_code,
        "review_status": cr.review_status,
        "review_message": cr.review_message,
        "needs_manual_review": cr.needs_manual_review or False,
    }


def _provenance_dict(cr: CheckResult) -> dict[str, Any]:
    """
    Вернуть словарь canonical provenance полей из ORM-объекта CheckResult.

    Используется в get_by_run_with_docs и get_page_for_run чтобы
    не дублировать одинаковый блок полей.

    Включает:
    - viewer/highlight fields (page, clause_uid, element_id, bbox)
    - segment-aware provenance (segment_*)
    - retrieval chunk provenance (chunk_id, chunk_index)
    - retrieval context trace (context_trace)
    """
    return {
        "page": cr.page,
        "clause_uid": cr.clause_uid,
        "element_id": cr.element_id,
        "bbox": cr.bbox,
        "segment_id": cr.segment_id,
        "segment_type": cr.segment_type,
        "segment_title": cr.segment_title,
        "segment_order": cr.segment_order,
        "is_primary_segment": cr.is_primary_segment,
        "chunk_id": cr.chunk_id,
        "chunk_index": cr.chunk_index,
        "context_trace": cr.context_trace,
    }


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
        """
        Простой метод создания результата без idempotent-логики.

        ВАЖНО: он не учитывает segment_id и уникальные индексы.
        Для нормальной работы пайплайна используется upsert_single_check_result.
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

        # ── APPLICATION-LEVEL SAFEGUARD (Hot-Fix for VARCHAR(20) overflow) ──
        result = _safe_truncate(result, 20, "result", check_id) or result
        severity = _safe_truncate(severity, 20, "severity", check_id) or severity

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
            canonical_locale=run_lang,         # <-- ДОБАВИТЬ
            canonical_content_hash=new_hash,   # <-- ДОБАВИТЬ
            content_revision=1,                # <-- ДОБАВИТЬ
        )

        self.session.add(cr)
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
        - doc_requires_manual_review;
        - Spec v2: canonical display semantics поля.
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
            item = {
                "id": cr.id,
                "run_id": cr.run_id,
                "document_id": cr.document_id,
                "check_id": cr.check_id,
                "check_name": cr.check_name,
                "result": cr.result,
                "severity": cr.severity,
                "value_text": cr.value_text,
                "evidence_ref": cr.evidence_ref,
                "confidence": cr.confidence,
                "detector_used": cr.detector_used,
                "quality_flags": cr.quality_flags,
                "qc_status": cr.qc_status,
                "qc_by": cr.qc_by,
                "qc_comment": cr.qc_comment,
                "qc_at": cr.qc_at,
                "created_at": cr.created_at,
                "origin": cr.origin,
                "origin_type": normalize_origin_type(cr.origin),
                "document_name": document_name,
                "doc_type": doc_type,
                "doc_classification_level": doc_level,
                "doc_classification_confidence": doc_conf,
                "doc_requires_manual_review": doc_requires_manual_review,
                "structured_data": cr.structured_data,
                "conditional_check_triggered": cr.conditional_check_triggered,
                "trigger_name": cr.trigger_name,
                # ── Canonical provenance ───────────────────────────────────────
                **_provenance_dict(cr),
                # ── Spec v2: canonical display semantics ──────────────────────
                **_display_semantics_dict(cr),
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

    async def update_review_qc(
        self,
        run_id: uuid.UUID,
        document_id: uuid.UUID,
        check_id: str,
        segment_id: str | None,
        qc_status: str,
        qc_by: str,
        qc_comment: str | None,
    ) -> int:
        """
        Обновить QC-статус для одной review-находки.

        Простыми словами:
        - review finding в новой DD Matrix может состоять не из одной строки БД,
          а из нескольких строк CheckResult;
        - такое бывает, когда один и тот же check представлен несколькими
          кусками/сегментами одного физического файла;
        - поэтому для review QC мы обновляем НЕ одну строку по result_id,
          а ВСЮ группу строк по ключу:
              (run_id, document_id, check_id, segment_id)

        Правило segment_id:
        - single-document файл -> segment_id is None -> ищем segment_id IS NULL
        - multi-document файл  -> segment_id = "seg-..." -> ищем точное совпадение

        Возвращает:
        - количество обновлённых строк.
        """
        stmt = (
            update(CheckResult)
            .where(
                CheckResult.run_id == run_id,
                CheckResult.document_id == document_id,
                CheckResult.check_id == check_id,
                CheckResult.segment_id.is_(None)
                if segment_id is None
                else CheckResult.segment_id == segment_id,
            )
            .values(
                qc_status=qc_status,
                qc_by=qc_by,
                qc_comment=qc_comment,
                qc_at=func.now(),
            )
        )
        result = await self.session.execute(stmt)
        return result.rowcount

    async def count_by_severity(self, run_id: uuid.UUID) -> dict[str, int]:
        """
        Посчитать количество результатов по severity для run.

        ВАЖНО: считаем все строки check_results, в том числе сегментные.
        Для бизнес-метрик агрегатор сверху может считать по-другому.
        """
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

        ВАЖНО: здесь мы показываем "сырые" строки результатов,
        поэтому segment_id/segment_* попадают в ответ как есть.
        Spec v2: включены canonical display semantics поля.
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

        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        total = (await self.session.execute(count_stmt)).scalar_one()

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
                "evidence_ref": cr.evidence_ref,
                "confidence": cr.confidence,
                "detector_used": cr.detector_used,
                "quality_flags": cr.quality_flags,
                "qc_status": cr.qc_status,
                "qc_by": cr.qc_by,
                "qc_comment": cr.qc_comment,
                "qc_at": cr.qc_at,
                "created_at": cr.created_at,
                "origin": cr.origin,
                "origin_type": normalize_origin_type(cr.origin),
                "document_name": document_name,
                "doc_type": doc_type_value,
                "doc_classification_level": doc_level,
                "doc_classification_confidence": doc_conf,
                "doc_requires_manual_review": doc_requires_manual_review,
                "structured_data": cr.structured_data,
                "conditional_check_triggered": cr.conditional_check_triggered,
                "trigger_name": cr.trigger_name,
                # ── Canonical provenance ───────────────────────────────────────
                **_provenance_dict(cr),
                # ── Spec v2: canonical display semantics ──────────────────────
                **_display_semantics_dict(cr),
            }
            items.append(item)

        return items, total

    async def get_one(
        self,
        run_id: uuid.UUID,
        document_id: uuid.UUID,
        check_id: str,
        segment_id: str | None,
    ) -> CheckResult | None:
        """
        Найти один результат по ключу (run, doc, segment, check).

        Для непрофессионального программиста:
        - single-document: segment_id = None → ищем запись с segment_id IS NULL;
        - multi-document: segment_id = "seg-123" → ищем запись с этим segment_id.
        """
        stmt = select(CheckResult).where(
            CheckResult.run_id == run_id,
            CheckResult.document_id == document_id,
            CheckResult.check_id == check_id,
        )

        if segment_id is None:
            stmt = stmt.where(CheckResult.segment_id.is_(None))
        else:
            stmt = stmt.where(CheckResult.segment_id == segment_id)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def has_success_for_doc_check(
        self,
        run_id: uuid.UUID,
        document_id: uuid.UUID,
        check_id: str,
    ) -> bool:
        """
        Проверить, есть ли уже успешный результат по агрегату (run, doc, check),
        независимо от segment_id.

        Архитектурный смысл:
        - orchestration-слой (Celery task run_single_check) работает на уровне
          бизнес-единицы "одна проверка для одного документа";
        - storage-слой хранит одну или несколько строк CheckResult:
          * single-document: одна строка с segment_id IS NULL;
          * multi-document: одна строка на каждый сегмент.

        Поэтому для идемпотентности задачи нам нельзя смотреть
        на конкретную storage-строку через get_one(..., segment_id=...).
        Нам нужен агрегирующий ответ:
        "Есть ли уже SUCCESS по этому document/check хотя бы на одном сегменте?"

        Возвращает:
        - True  -> если найден хотя бы один CheckResult со статусом SUCCESS;
        - False -> если успешных результатов ещё нет.
        """
        stmt = (
            select(CheckResult.id)
            .where(
                CheckResult.run_id == run_id,
                CheckResult.document_id == document_id,
                CheckResult.check_id == check_id,
                CheckResult.execution_status == CheckExecutionStatus.SUCCESS.value,
            )
            .limit(1)
        )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def get_first_success_for_doc_check(
        self,
        run_id: uuid.UUID,
        document_id: uuid.UUID,
        check_id: str,
    ) -> CheckResult | None:
        """
        Вернуть первую найденную успешную запись по агрегату (run, doc, check),
        чтобы orchestration-слой мог залогировать, какой именно segment-level
        результат уже закрыл задачу.

        ВАЖНО:
        - метод не нужен для бизнес-логики принятия решения;
          решение "скипать или нет" остаётся за has_success_for_doc_check(...).
        - этот метод только для observability / debug logging.
        - порядок берём детерминированный: primary segment сначала, затем
          segment_order, затем created_at, затем id.
        """
        stmt = (
            select(CheckResult)
            .where(
                CheckResult.run_id == run_id,
                CheckResult.document_id == document_id,
                CheckResult.check_id == check_id,
                CheckResult.execution_status == CheckExecutionStatus.SUCCESS.value,
            )
            .order_by(
                CheckResult.is_primary_segment.desc().nullslast(),
                CheckResult.segment_order.asc().nullslast(),
                CheckResult.created_at.asc(),
                CheckResult.id.asc(),
            )
            .limit(1)
        )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


    @staticmethod
    def _apply_anchor_limit(
        anchors: list[CheckAnchor],
    ) -> list[CheckAnchor]:
        """
        Ограничить число anchors до _MAX_ANCHORS_PER_CHECK_RESULT.

        Приоритет — сильнейшие по методу (method_strength), tie-break
        по anchor_confidence. Порядок входного списка не гарантируется
        после обрезки — но select_primary_anchor всё равно выберет сильнейший.

        Пустой вход -> пустой выход. Список <= 5 -> как есть (без сортировки).
        """
        if len(anchors) <= _MAX_ANCHORS_PER_CHECK_RESULT:
            return anchors

        ranked = sorted(
            anchors,
            key=lambda a: (method_strength(a.anchor_method), a.anchor_confidence),
            reverse=True,
        )
        return ranked[:_MAX_ANCHORS_PER_CHECK_RESULT]

    async def _replace_anchors_for_check_result(
        self,
        *,
        cr: CheckResult,
        anchors: list[CheckAnchor],
    ) -> None:
        """
        Заменить полный набор anchors для CheckResult и денормализовать
        primary на сам CheckResult.

        Idempotency: delete + create_many. Rerun того же CheckResult
        полностью перезаписывает anchors.

        Семантика primary:
        - anchors пустой -> delete all, обнулить 4 денорм-колонки;
        - anchors непустой -> apply limit (топ-5), replace, select_primary_anchor,
          set_primary, денормализация 4 колонок.

        anchor_stale=False — stale-detection отложена в B4b (не реализована).
        """
        anchor_repo = CheckResultAnchorRepository(self.session)

        # Пустой набор -> полная очистка (idempotent rerun без anchors).
        if not anchors:
            await anchor_repo.delete_for_check_result(check_result_id=cr.id)
            cr.primary_anchor_id = None
            cr.primary_anchor_method = None
            cr.primary_anchor_confidence = None
            cr.anchor_stale = False
            return

        limited = self._apply_anchor_limit(anchors)

        created = await anchor_repo.replace_for_check_result(
            check_result_id=cr.id,
            anchors=limited,
        )

        primary = select_primary_anchor(limited)
        if primary is None:
            # Недостижимо на непустом входе, но fail-safe.
            cr.primary_anchor_id = None
            cr.primary_anchor_method = None
            cr.primary_anchor_confidence = None
            cr.anchor_stale = False
            return

        # Identity-lookup: select_primary_anchor возвращает ту же ссылку,
        # что лежит в limited. Equality-based index() хрупок из-за float
        # в anchor_diagnostics/anchor_confidence.
        primary_idx = next(
            i for i, a in enumerate(limited) if a is primary
        )
        primary_row = created[primary_idx]

        await anchor_repo.set_primary(
            check_result_id=cr.id,
            anchor_id=primary_row.id,
        )

        cr.primary_anchor_id = primary_row.id
        cr.primary_anchor_method = primary.anchor_method.value
        cr.primary_anchor_confidence = primary.anchor_confidence
        cr.anchor_stale = False



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
        plan_item_id: uuid.UUID | None = None,
        page: int | None,
        clause_uid: str | None,
        element_id: str | None,
        bbox: dict | None,
        segment_id: str | None = None,
        segment_type: str | None = None,
        segment_title: str | None = None,
        segment_order: int | None = None,
        is_primary_segment: bool | None = None,
        chunk_id: str | None = None,
        chunk_index: int | None = None,
        context_trace: list[dict[str, Any]] | None = None,
        execution_status: str = CheckExecutionStatus.SUCCESS.value,
        error_details: dict | None = None,
        ui_mode: str | None = None,
        display_text: str | None = None,
        machine_reason_code: str | None = None,
        review_status: str | None = None,
        review_message: str | None = None,
        needs_manual_review: bool = False,
        anchors: list[CheckAnchor] | None = None,
    ) -> CheckResult:
        """
        Создать или обновить результат одной проверки.

        Идемпотентность по ключу (run, doc, segment_id, check):
        - для single-document: segment_id = None;
        - для multi-document: отдельная запись на каждый сегмент.

        Важно про savepoint:
        - Мы используем session.begin_nested() вместо прямого rollback().
        - begin_nested() создаёт PostgreSQL SAVEPOINT внутри текущей транзакции.
        - При DBAPIError откатывается только этот savepoint.
        - Основная транзакция сессии остаётся живой.
        - Все ORM-объекты, загруженные до этого вызова, остаются валидными.
        - log_error() выполняется в рамках той же основной транзакции.

        Provenance contract:
        - chunk_id / chunk_index: retrieval chunk, из которого LLM собирал контекст.
        - context_trace: компактный список top-N retrieval contexts (без полного текста).
          Хранится для forensic/debug audit, не для фильтрации.

        Spec v2:
        - Параметры ui_mode, display_text, machine_reason_code,
          review_status, review_message, needs_manual_review записываются
          в CheckResult при create и update.
        """

        # Вычисляем хэш канонического контента на основе Display-semantics полей
        new_hash = build_presentation_source_hash(
            check_name=check_name,
            display_text=display_text,
            review_message=review_message,
            dd_request_text=None,
        )

        # Получаем язык анализа из запущенного рана
        run_stmt = select(Run.analysis_language).where(Run.id == run_id)
        run_lang = (await self.session.execute(run_stmt)).scalar_one_or_none()

        # ── APPLICATION-LEVEL SAFEGUARD (Hot-Fix for VARCHAR(20) overflow) ──
        # Усекаем result и severity до 20 символов для совместимости с текущей
        # схемой БД. После миграции ALTER COLUMN → VARCHAR(50) эта защита станет
        # no-op (значения уже будут влезать), и её можно будет убрать.
        result = _safe_truncate(result, 20, "result", check_id) or result
        severity = _safe_truncate(severity, 20, "severity", check_id) or severity

        now = datetime.now(UTC)

        started_statuses = {
            CheckExecutionStatus.PENDING.value,
            CheckExecutionStatus.RUNNING.value,
            CheckExecutionStatus.SUCCESS.value,
            CheckExecutionStatus.FAILED.value,
            CheckExecutionStatus.COMPUTE_FAILED.value,
            CheckExecutionStatus.PERSIST_FAILED.value,
            CheckExecutionStatus.TIMEOUT.value,
        }

        finished_statuses = {
            CheckExecutionStatus.SUCCESS.value,
            CheckExecutionStatus.FAILED.value,
            CheckExecutionStatus.COMPUTE_FAILED.value,
            CheckExecutionStatus.PERSIST_FAILED.value,
            CheckExecutionStatus.TIMEOUT.value,
        }

        if isinstance(execution_status, CheckExecutionStatus):
            status_value = execution_status.value
        else:
            try:
                status_value = CheckExecutionStatus(execution_status).value
            except ValueError:
                status_value = CheckExecutionStatus.FAILED.value

        try:
            # Используем savepoint (begin_nested) вместо прямого rollback сессии.
            # При DBAPIError откатывается только этот savepoint, основная транзакция
            # и все уже загруженные ORM-объекты остаются живыми и валидными.
            async with self.session.begin_nested():
                existing = await self.get_one(run_id, document_id, check_id, segment_id)

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
                        plan_item_id=plan_item_id,
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
                        execution_status=status_value,
                        started_at=now if status_value in started_statuses else None,
                        finished_at=now if status_value in finished_statuses else None,
                        error_details=error_details,
                        # ── Spec v2: canonical display semantics ──────────────
                        ui_mode=ui_mode,
                        display_text=display_text,
                        machine_reason_code=machine_reason_code,
                        review_status=review_status,
                        review_message=review_message,
                        needs_manual_review=needs_manual_review,
                        # ── Sprint 1: канонические поля ────────────────────────
                        canonical_locale=run_lang,
                        canonical_content_hash=new_hash,
                        content_revision=1,
                    )
                    self.session.add(cr)
                    await self.session.flush()

                    if anchors is not None:
                        await self._replace_anchors_for_check_result(
                            cr=cr,
                            anchors=anchors,
                        )
                        await self.session.flush()

                    return cr

                # ── UPDATE path ───────────────────────────────────────────────
                # Проверяем, изменился ли канонический контент
                hash_changed = existing.canonical_content_hash != new_hash

                if hash_changed:
                    # Увеличиваем монотонный счетчик ревизии канонического контента
                    existing.content_revision = (existing.content_revision or 1) + 1
                    existing.canonical_content_hash = new_hash

                    # В рамках этой же транзакции инвалидируем связанные презентации (устарели)
                    # Сделаем это через batched UPDATE (Task 1.5)
                    await self.session.execute(
                        update(CheckResultPresentation)
                        .where(
                            CheckResultPresentation.check_result_id == existing.id,
                            CheckResultPresentation.translation_status.in_(
                                ["ready", "reviewed", "approved"]
                            )
                        )
                        .values(translation_status="stale")
                    )

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
                existing.plan_item_id = plan_item_id
                existing.page = page
                existing.clause_uid = clause_uid
                existing.element_id = element_id
                existing.bbox = bbox
                existing.segment_id = segment_id
                existing.segment_type = segment_type
                existing.segment_title = segment_title
                existing.segment_order = segment_order
                existing.is_primary_segment = is_primary_segment
                existing.chunk_id = chunk_id
                existing.chunk_index = chunk_index
                existing.context_trace = context_trace
                existing.execution_status = status_value
                existing.error_details = error_details
                # ── Spec v2: canonical display semantics ──────────────────────
                existing.ui_mode = ui_mode
                existing.display_text = display_text
                existing.machine_reason_code = machine_reason_code
                existing.review_status = review_status
                existing.review_message = review_message
                existing.needs_manual_review = needs_manual_review
                
                # Обновляем canonical_locale на случай, если применился backfill
                existing.canonical_locale = run_lang

                if existing.started_at is None and status_value in started_statuses:
                    existing.started_at = now

                if status_value in finished_statuses:
                    existing.finished_at = now

                await self.session.flush()

                if anchors is not None:
                    await self._replace_anchors_for_check_result(
                        cr=existing,
                        anchors=anchors,
                    )
                    await self.session.flush()

                return existing

        except DBAPIError as err:
            # Savepoint уже откатился автоматически при выходе из begin_nested().
            # Основная транзакция сессии жива — можно продолжать работу с ней.
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
                "playbook_version_id": (str(playbook_version_id) if playbook_version_id else None),
                "plan_item_id": (str(plan_item_id) if plan_item_id else None),
                "page": page,
                "clause_uid": clause_uid,
                "element_id": element_id,
                "bbox": bbox,
                "segment_id": segment_id,
                "segment_type": segment_type,
                "segment_title": segment_title,
                "segment_order": segment_order,
                "is_primary_segment": is_primary_segment,
                "chunk_id": chunk_id,
                "chunk_index": chunk_index,
                "context_trace": context_trace,
                "execution_status": status_value,
                "raw_execution_status": (
                    execution_status.value
                    if isinstance(execution_status, CheckExecutionStatus)
                    else execution_status
                ),
                "error_details": error_details,
                # ── Spec v2: включаем в payload для диагностики ───────────────
                "ui_mode": ui_mode,
                "display_text": display_text,
                "machine_reason_code": machine_reason_code,
                "review_status": review_status,
                "review_message": review_message,
                "needs_manual_review": needs_manual_review,
                # ── B4: anchors entry count (не сами anchors —太重)
                "anchors_count": (len(anchors) if anchors is not None else None),
            }

            persist_error_repo = CheckResultPersistErrorRepository(self.session)
            try:
                await persist_error_repo.log_error(
                    run_id=run_id,
                    document_id=document_id,
                    check_id=check_id,
                    payload=payload,
                    error_type=("permanent_db_error" if permanent else "transient_db_error"),
                    sqlstate=sqlstate,
                    error_message=str(err),
                    retryable=not permanent,
                )
            except Exception as log_exc:
                logger.warning(
                    "ResultRepository.upsert_single_check_result: failed to log persist error",
                    extra={
                        "run_id": str(run_id),
                        "document_id": str(document_id),
                        "check_id": check_id,
                        "sqlstate": sqlstate,
                        "logging_error": str(log_exc),
                    },
                )

            if permanent:
                raise CheckResultPersistPermanentError(
                    (
                        "Permanent DB error while upserting check_result "
                        f"(run_id={run_id}, document_id={document_id}, check_id={check_id}): {err}"
                    ),
                    sqlstate=sqlstate,
                ) from err

            raise CheckResultPersistTransientError(
                (
                    "Transient DB error while upserting check_result "
                    f"(run_id={run_id}, document_id={document_id}, check_id={check_id}): {err}"
                ),
                sqlstate=sqlstate,
            ) from err

    async def count_distinct_checks_for_run(self, run_id: uuid.UUID) -> int:
        """
        Сколько уникальных пар (document_id, check_id) вообще есть в check_results для run.

        ВАЖНО:
        - здесь мы сознательно считаем уникальные проверки на документ,
          без учёта сегментов (segment_id).
        - это означает: если у документа есть check X хотя бы в одном сегменте,
          он считается один раз.
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
        Количество уникальных (document_id, check_id), для которых
        все materialized storage-rows уже находятся в terminal execution_status.

        Это важно для segment-aware хранения:
        - один doc/check может материализоваться в несколько rows по segment_id;
        - finished считается только если нет ни одной non-terminal row
        внутри того же (document_id, check_id).
        """
        finished_statuses = (
            CheckExecutionStatus.SUCCESS.value,
            CheckExecutionStatus.FAILED.value,
            CheckExecutionStatus.COMPUTE_FAILED.value,
            CheckExecutionStatus.PERSIST_FAILED.value,
            CheckExecutionStatus.TIMEOUT.value,
        )

        per_check = (
            select(
                CheckResult.document_id.label("document_id"),
                CheckResult.check_id.label("check_id"),
                func.count().label("total_rows"),
                func.sum(
                    case(
                        (CheckResult.execution_status.in_(finished_statuses), 1),
                        else_=0,
                    )
                ).label("finished_rows"),
            )
            .where(CheckResult.run_id == run_id)
            .group_by(CheckResult.document_id, CheckResult.check_id)
            .subquery()
        )

        stmt = select(func.count()).select_from(per_check).where(
            per_check.c.total_rows == per_check.c.finished_rows
        )

        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def count_documents_fully_finished_for_run(self, run_id: uuid.UUID) -> int:
        """
        Сколько документов полностью завершили все свои checks.

        Используем для метрик «прогресс по документам» (сколько документов
        имеют все checks в финальном статусе).

        ВАЖНО:
        - здесь считаем по всем строкам (включая сегменты),
          но условие "все checks завершены" проверяется по количеству строк.
        - этот метод оставляем без segment_id в ключе на этом этапе, потому что
          бизнес-смысл "полностью завершён" нам ещё нужно переосмыслить
          с учётом сегментов (можем сделать это отдельной задачей).
        """
        finished_statuses = [
            CheckExecutionStatus.SUCCESS.value,
            CheckExecutionStatus.FAILED.value,
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

        stmt = (
            select(func.count())
            .select_from(per_doc)
            .where(per_doc.c.total_cnt == per_doc.c.finished_cnt)
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one() or 0)

    async def has_failed_or_timed_out_checks(self, run_id: uuid.UUID) -> bool:
        """
        Есть ли по run хотя бы один check с неуспешным финальным статусом.
        """
        problematic_statuses = [
            CheckExecutionStatus.FAILED.value,
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
    
    async def get_successful_doc_check_keys(
        self,
        run_id: uuid.UUID,
        doc_check_pairs: list[tuple[uuid.UUID, str]],
    ) -> set[tuple[uuid.UUID, str]]:
        """
        Высокопроизводительная batch-проверка существующих успешных проверок.
        Использует composite IN кортежей (PostgreSQL row-value comparison).
        """
        if not doc_check_pairs:
            return set()

        # Нормализация пар в список (UUID, str)
        normalized_pairs = [
            (p[0] if isinstance(p[0], uuid.UUID) else uuid.UUID(str(p[0])), str(p[1]))
            for p in doc_check_pairs
        ]

        stmt = (
            select(CheckResult.document_id, CheckResult.check_id)
            .where(
                CheckResult.run_id == run_id,
                CheckResult.execution_status == CheckExecutionStatus.SUCCESS.value,
                tuple_(CheckResult.document_id, CheckResult.check_id).in_(normalized_pairs),
            )
        )

        result = await self.session.execute(stmt)
        return {(row.document_id, row.check_id) for row in result}

        
    
