# src/services/deal_review_service.py

"""
Сервис для UI-обзора сделки (deal review).

Задачи:
- загрузить из БД документы, результаты проверок и имя сделки для рана
- построить AggregatedResults через Aggregator
- преобразовать AggregatedResults в DTO для фронтенда
- построить матричное представление DD Grid (DDMatrixResponseDTO)

Архитектурный принцип:
  Бэкенд строит ОДНУ полную таблицу (AggregatedResults) содержащую все
  результаты всех чеков по всем документам рана. Из неё строятся все
  представления: плоский список, матрица, DD-запросы, extracted values.
  Фронтенд получает готовые данные и рендерит нужное представление
  без повторных запросов к серверу.
"""

import uuid
from collections import defaultdict
from typing import Any

from api.schemas.deal_review import (
    CheckItemDTO,
    CheckMetaDTO,
    ConditionalCheckDTO,
    DDMatrixResponseDTO,
    DDRequestDTO,
    DocumentDetailDTO,
    DocumentMatrixRowDTO,
    DocumentSummaryDTO,
    ExtractedFieldDTO,
    ExtractedValueDTO,
    MatrixCellDTO,
    SegmentMatrixRowDTO,
)
from core.logging import get_logger
from db.repositories.deal_repo import DealRepository
from db.repositories.runner_repo import RunnerRepository
from db.uow import db_uow
from services.export.aggregator import aggregate_results
from services.export.models import AggregatedResults

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Загрузка AggregatedResults из БД
# ---------------------------------------------------------------------------


async def load_aggregated_results(
    deal_id: str,
    run_id: str,
) -> tuple[AggregatedResults, dict[str, dict[str, Any]]]:
    """
    Загрузить документы и результаты проверок для сделки/рана из БД
    и собрать AggregatedResults.

    Имя сделки загружается из БД через DealRepository.
    deal_id и run_id принимаются как str и конвертируются в uuid.UUID
    перед передачей в репозитории.

    Возвращает кортеж:
    - aggregated: AggregatedResults — единый источник данных для всех
      экспортов и API-эндпоинтов
    - documents: словарь {document_id: {name, folder_path, doc_type,
      status, classification_level, classification_confidence,
      applicable_triggers}}
    """
    deal_uuid = uuid.UUID(deal_id)
    run_uuid = uuid.UUID(run_id)

    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        deal_repo = DealRepository(uow.session)

        documents = await runner_repo.load_documents_for_run(run_uuid)
        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        deal = await deal_repo.get_by_id(deal_uuid)

    deal_name = deal.name if deal else f"Deal {deal_id}"

    logger.info(
        "Building AggregatedResults for deal run",
        deal_id=deal_id,
        run_id=run_id,
        deal_name=deal_name,
        documents=len(documents),
        check_results=len(check_results),
    )

    aggregated = aggregate_results(
        deal_id=deal_id,
        deal_name=deal_name,
        run_id=run_id,
        check_results=check_results,
        documents=documents,
    )
    return aggregated, documents


# ---------------------------------------------------------------------------
# Маппинг AggregatedResults → DTO для существующих UI-эндпоинтов
# ---------------------------------------------------------------------------


def build_document_summaries(
    agg: AggregatedResults,
    documents: dict[str, dict[str, Any]],
) -> list[DocumentSummaryDTO]:
    """
    Построить краткие статусы документов для списка документов сделки.

    Каждый DocumentSummaryDTO содержит счётчики рисков по уровням критичности
    и метаданные классификации. Документы сортируются по имени (A→Z).
    """
    by_doc: dict[str, dict[str, Any]] = {}

    for row in agg.rows:
        doc_id = row.document_id
        if doc_id not in by_doc:
            doc_meta = documents.get(doc_id, {})
            by_doc[doc_id] = {
                "document_id": doc_id,
                "name": row.document_name,
                "doc_type": row.doc_type,
                "status": doc_meta.get("status", ""),
                "critical_count": 0,
                "high_count": 0,
                "medium_count": 0,
                "pass_count": 0,
                "unclear_count": 0,
                "has_degraded_structure": "structure_degraded" in (row.quality_flags or ""),
                "in_quarantine": doc_meta.get("status", "") == "quarantine",
                "classification_level": doc_meta.get("classification_level", ""),
                "classification_confidence": float(doc_meta.get("classification_confidence", 0.0)),
            }

        if row.result == "fail":
            if row.severity == "critical":
                by_doc[doc_id]["critical_count"] += 1
            elif row.severity == "high":
                by_doc[doc_id]["high_count"] += 1
            elif row.severity == "medium":
                by_doc[doc_id]["medium_count"] += 1
        elif row.result == "pass":
            by_doc[doc_id]["pass_count"] += 1
        elif row.result == "unclear":
            by_doc[doc_id]["unclear_count"] += 1

    return [
        DocumentSummaryDTO(**v)
        for _, v in sorted(by_doc.items(), key=lambda kv: kv[1]["name"].lower())
    ]


def build_document_detail(
    agg: AggregatedResults,
    documents: dict[str, dict[str, Any]],
    document_id: str,
) -> DocumentDetailDTO:
    """
    Построить детальную карточку документа (DocumentDetailDTO) по его id.

    Для каждого чека подтягивает structured_data напрямую из agg.rows
    (это сырой JSON из CheckResult.structured_data с полями value/source/confidence/found/location/qc).

    ВНИМАНИЕ: сейчас карточка остаётся документ-ориентированной (без segment‑группировки),
    чтобы не ломать существующий контракт фронта.
    """
    doc_meta = documents.get(document_id)
    if not doc_meta:
        raise ValueError(f"Document {document_id} not found in aggregated data")

    checks: list[CheckItemDTO] = []
    for row in agg.rows:
        if row.document_id != document_id:
            continue

        structured_data = row.structured_data or {}

        checks.append(
            CheckItemDTO(
                check_id=row.check_id,
                check_name=row.check_name,
                result=row.result,
                severity=row.severity,
                evidence_snippet=row.evidence_snippet,
                page=row.page,
                clause_uid=row.clause_uid or "",
                confidence=row.confidence,
                detector_used=row.detector_used,
                quality_flags={"flags": row.quality_flags} if row.quality_flags else None,
                conditional_check_triggered=row.conditional_check_triggered,
                trigger_name=row.trigger_name,
                structured_data=structured_data,
                origin=row.origin,
                # NEW: segment metadata (совпадает с DTO)
                segment_id=row.segment_id or None,
                segment_type=row.segment_type or None,
                segment_title=row.segment_title or None,
                segment_order=row.segment_order,
                is_primary_segment=row.is_primary_segment,
            )
        )

    return DocumentDetailDTO(
        document_id=document_id,
        name=doc_meta["name"],
        doc_type=doc_meta["doc_type"],
        status=doc_meta["status"],
        classification_level=doc_meta.get("classification_level", ""),
        classification_confidence=float(doc_meta.get("classification_confidence", 0.0)),
        applicable_triggers=doc_meta.get("applicable_triggers", []),
        checks=checks,
    )


def build_dd_requests(agg: AggregatedResults) -> list[DDRequestDTO]:
    """
    Построить список DD-запросов для UI из AggregatedResults.dd_requests.

    Теперь передаёт segment provenance для точной навигации в viewer
    при клике "Open in document" из review panel.
    """
    return [
        DDRequestDTO(
            request_id=req.request_id,
            priority=req.priority,
            check_id=req.check_id,
            check_name=req.check_name,
            addressee=req.addressee,
            text=req.text,
            document_ids=req.document_ids,
            document_names=req.document_names,
            doc_types=req.doc_types,
            structured_values=req.structured_values,
            # NEW: segment provenance для viewer navigation
            segment_id=req.segment_id or None,
            segment_type=req.segment_type or None,
            segment_title=req.segment_title or None,
            segment_order=req.segment_order,
            is_primary_segment=req.is_primary_segment,
            chunk_id=req.chunk_id or None,
            chunk_index=req.chunk_index,
        )
        for req in agg.dd_requests
    ]


def build_conditional_checks(agg: AggregatedResults) -> list[ConditionalCheckDTO]:
    """
    Построить список условных проверок для UI из AggregatedResults.conditional_rows.
    """
    return [
        ConditionalCheckDTO(
            document_name=cr.document_name,
            doc_type=cr.doc_type,
            trigger_name=cr.trigger_name,
            check_id=cr.check_id,
            check_name=cr.check_name,
            result=cr.result,
            severity=cr.severity,
            evidence_snippet=cr.evidence_snippet,
            page=cr.page,
            confidence=cr.confidence,
            quality_flags={"flags": cr.quality_flags} if cr.quality_flags else None,
        )
        for cr in agg.conditional_rows
    ]


def build_extracted_values(agg: AggregatedResults) -> list[ExtractedValueDTO]:
    """
    Построить список извлечённых структурированных значений для UI
    из AggregatedResults.structured_value_rows.

    Теперь DTO ExtractedValueDTO содержит опциональные segment-поля,
    поэтому мы можем аккуратно их пробросить без изменения контракта
    для существующих клиентов.
    """
    return [
        ExtractedValueDTO(
            document_name=sv.document_name,
            doc_type=sv.doc_type,
            check_name=sv.check_name,
            field_name=sv.field_name,
            field_value=sv.field_value,
            field_format=sv.field_format,
            page=sv.page,
            clause_uid=sv.clause_uid or "",
            segment_id=sv.segment_id or None,
            segment_type=sv.segment_type or None,
            segment_title=sv.segment_title or None,
            segment_order=sv.segment_order,
            is_primary_segment=sv.is_primary_segment,
        )
        for sv in agg.structured_value_rows
    ]


# ---------------------------------------------------------------------------
# DD Matrix — матричное представление всех результатов рана
# ---------------------------------------------------------------------------


def build_dd_matrix(
    agg: AggregatedResults,
    documents: dict[str, dict[str, Any]],
) -> DDMatrixResponseDTO:
    """
    Перепаковать AggregatedResults в матричную структуру DD Matrix.

    Используется эндпоинтом GET /deals/{deal_id}/runs/{run_id}/dd-matrix.

    Новая архитектура:
      - file-уровень (documents): строки на уровне физического файла (legacy),
        будут использоваться как контейнер/группировка;
      - segment-уровень (segment_documents): строки на уровне логического документа
        (сегмента), это целевой уровень для DD Grid на фронте.

    Алгоритм:
      1. Из agg.rows собираем реестр уникальных чеков (CheckMetaDTO).
         GLOBAL_PLAYBOOK получают меньший order_index и идут первыми.
      2. Из agg.structured_value_rows строим индекс
         (doc_id, check_id) → [ExtractedFieldDTO] для заполнения ячеек.
         (пока без разбиения по сегментам, этого достаточно для MVP).
      3. Строим индекс результатов на уровне файла: (doc_id, check_id) → ExportRow.
         Это legacy-слой для DocumentMatrixRowDTO.
      4. Строим segment-ориентированные строки: группируем agg.rows по
         (document_id, segment_id), внутри — по check_id, выбираем "лучший"
         ExportRow по result/severity/confidence и формируем SegmentMatrixRowDTO.
      5. Строим legacy file-ориентированные строки (как было раньше), чтобы
         не ломать текущий фронт: DocumentMatrixRowDTO по (doc_id, check_id).
      6. Сортируем строки по риску: сначала critical fail, затем прочие fail,
         карантинные документы в конце.
      7. Формируем global_check_ids и doc_type_check_ids для вкладок фронта.
    """

    # ------------------------------------------------------------------
    # Шаг 1. Реестр уникальных чеков (столбцы матрицы)
    # ------------------------------------------------------------------
    seen_checks: dict[str, dict[str, Any]] = {}

    # Проход 1: GLOBAL_PLAYBOOK
    for row in agg.rows:
        origin = (row.origin or "").upper()
        if origin != "GLOBAL_PLAYBOOK":
            continue
        if row.check_id not in seen_checks:
            seen_checks[row.check_id] = {
                "check_id": row.check_id,
                "check_name": row.check_name,
                "origin": "GLOBAL_PLAYBOOK",
                "severity": row.severity,
                "applicable_doc_types": None,
            }

    # Проход 2: DOCUMENT_TYPE / CONDITIONAL
    for row in agg.rows:
        origin = (row.origin or "").upper()
        if origin == "GLOBAL_PLAYBOOK":
            continue

        resolved_origin = "CONDITIONAL" if row.conditional_check_triggered else "DOCUMENT_TYPE"

        if row.check_id not in seen_checks:
            seen_checks[row.check_id] = {
                "check_id": row.check_id,
                "check_name": row.check_name,
                "origin": resolved_origin,
                "severity": row.severity,
                "applicable_doc_types": [],
            }

        applicable = seen_checks[row.check_id]["applicable_doc_types"]
        if applicable is not None and row.doc_type not in applicable:
            applicable.append(row.doc_type)

    checks_list: list[CheckMetaDTO] = []
    global_check_ids: list[str] = []
    doc_type_check_ids: dict[str, list[str]] = defaultdict(list)

    for idx, (check_id, meta) in enumerate(seen_checks.items()):
        checks_list.append(
            CheckMetaDTO(
                check_id=meta["check_id"],
                check_name=meta["check_name"],
                origin=meta["origin"],
                severity=meta["severity"],
                order_index=idx,
                applicable_doc_types=meta["applicable_doc_types"],
            )
        )
        if meta["origin"] == "GLOBAL_PLAYBOOK":
            global_check_ids.append(check_id)
        else:
            for doc_type in meta["applicable_doc_types"] or []:
                if check_id not in doc_type_check_ids[doc_type]:
                    doc_type_check_ids[doc_type].append(check_id)

    # ------------------------------------------------------------------
    # Шаг 2. Индекс структурированных значений: (doc_id, check_id) → [ExtractedFieldDTO]
    # ------------------------------------------------------------------
    sv_index: dict[tuple[str, str], list[ExtractedFieldDTO]] = defaultdict(list)
    for sv in agg.structured_value_rows:
        key = (sv.document_id, sv.check_id)
        sv_index[key].append(
            ExtractedFieldDTO(
                field_name=sv.field_name,
                field_value=sv.field_value,
                field_format=sv.field_format,
            )
        )

    # ------------------------------------------------------------------
    # Шаг 3. Индекс результатов на уровне файла: (doc_id, check_id) → ExportRow
    # ------------------------------------------------------------------
    result_index: dict[tuple[str, str], Any] = {}
    for row in agg.rows:
        # Если для одного (doc_id, check_id) несколько строк (разные сегменты),
        # здесь останется последняя. Это legacy-поведение для file-level матрицы,
        # основной правдой станет segment_documents ниже.
        result_index[(row.document_id, row.check_id)] = row

    # ------------------------------------------------------------------
    # Шаг 4. Сегмент-ориентированные строки (segment_documents)
    # ------------------------------------------------------------------

    # Группируем все ExportRow по (document_id, segment_id).
    segment_groups: dict[tuple[str, str], list[Any]] = defaultdict(list)
    for row in agg.rows:
        seg_id = row.segment_id or ""  # для несегментированных документов
        segment_groups[(row.document_id, seg_id)].append(row)

    # Вспомогательные приоритеты: что считать "худшим" результатом.
    result_priority = {"fail": 3, "unclear": 2, "pass": 1}
    severity_priority = {"critical": 4, "high": 3, "medium": 2, "low": 1}

    def select_best_row(rows_for_check: list[Any]) -> Any:
        """
        Выбрать наиболее "важную" строку для данного (segment, check):
        - сначала по result: fail > unclear > pass;
        - потом по severity: critical > high > medium > low;
        - затем по confidence (по убыванию).
        """

        def key(r: Any) -> tuple[int, int, float]:
            return (
                result_priority.get(r.result, 0),
                severity_priority.get(r.severity, 0),
                r.confidence or 0.0,
            )

        return max(rows_for_check, key=key)

    doc_order: dict[str, None] = {}
    for row in agg.rows:
        doc_order[row.document_id] = None

    segment_rows: list[SegmentMatrixRowDTO] = []  # правильный тип

    for (doc_id, seg_id), rows_for_segment in segment_groups.items():
        doc_meta = documents.get(doc_id, {})
        r0 = rows_for_segment[0]

        by_check: dict[str, list[Any]] = defaultdict(list)
        for r in rows_for_segment:
            by_check[r.check_id].append(r)

        segment_results: dict[str, MatrixCellDTO] = {}

        for check_id, rows_for_check in by_check.items():
            best = select_best_row(rows_for_check)
            sv_key = (doc_id, check_id)
            extracted = sv_index.get(sv_key, [])

            segment_results[check_id] = MatrixCellDTO(
                result=best.result,
                severity=best.severity,
                snippet=best.evidence_snippet or "",
                page=best.page,
                clause_uid=best.clause_uid or "",
                extracted=extracted,
                confidence=best.confidence or 0.0,
                qc_status=best.qc_status or "pending",
                qc_by=best.qc_by or None,
                qc_comment=best.qc_comment or None,
                qc_at=best.qc_at.isoformat() if best.qc_at else None,
                conditional_check_triggered=best.conditional_check_triggered,
                trigger_name=best.trigger_name or "",
                segment_id=best.segment_id or None,
                segment_type=best.segment_type or None,
                segment_title=best.segment_title or None,
                segment_order=best.segment_order,
                is_primary_segment=best.is_primary_segment,
                chunk_id=best.chunk_id or None,
                chunk_index=best.chunk_index,
            )

        segment_rows.append(
            SegmentMatrixRowDTO(  # правильный класс
                document_id=doc_id,
                document_name=doc_meta.get("name", ""),
                doc_type=doc_meta.get("doc_type", "Generic"),
                folder_path=doc_meta.get("folder_path") or None,
                segment_id=seg_id or None,  # "" → None для несегментированных
                segment_type=r0.segment_type or None,
                segment_title=r0.segment_title or None,
                segment_order=r0.segment_order,
                is_primary_segment=r0.is_primary_segment,
                status=doc_meta.get("status", "completed"),
                classification_level=doc_meta.get("classification_level", ""),
                classification_confidence=float(doc_meta.get("classification_confidence", 0.0)),
                requires_manual_review=bool(
                    doc_meta.get("classification_requires_review") or False
                ),
                results=segment_results,
            )
        )

    # ------------------------------------------------------------------
    # Шаг 5. Legacy file-ориентированные строки (documents)
    # ------------------------------------------------------------------

    file_rows: list[DocumentMatrixRowDTO] = []

    for doc_id in doc_order:
        doc_meta = documents.get(doc_id, {})
        file_results: dict[str, MatrixCellDTO] = {}

        for check_id in seen_checks:
            export_row = result_index.get((doc_id, check_id))
            if export_row is None:
                continue

            file_results[check_id] = MatrixCellDTO(
                result=export_row.result,
                severity=export_row.severity,
                snippet=export_row.evidence_snippet or "",
                page=export_row.page,
                clause_uid=export_row.clause_uid or "",
                extracted=sv_index.get((doc_id, check_id), []),
                confidence=export_row.confidence or 0.0,
                qc_status=export_row.qc_status or "pending",
                qc_by=export_row.qc_by,  # ← ИСПРАВЛЕНО
                qc_comment=export_row.qc_comment,  # ← ИСПРАВЛЕНО
                qc_at=export_row.qc_at,  # ← ИСПРАВЛЕНО
                conditional_check_triggered=export_row.conditional_check_triggered,
                trigger_name=export_row.trigger_name or "",
                # segment_* / chunk_* здесь можно не заполнять, т.к. этот слой legacy;
                # для честной навигации фронт должен использовать segment_documents.
                segment_id=None,
                segment_type=None,
                segment_title=None,
                segment_order=None,
                is_primary_segment=None,
                chunk_id=None,
                chunk_index=None,
            )

        file_rows.append(
            DocumentMatrixRowDTO(
                document_id=doc_id,
                document_name=doc_meta.get("name", ""),
                doc_type=doc_meta.get("doc_type", "Generic"),
                folder_path=doc_meta.get("folder_path") or None,
                status=doc_meta.get("status", "completed"),
                classification_level=doc_meta.get("classification_level", ""),
                classification_confidence=float(doc_meta.get("classification_confidence", 0.0)),
                requires_manual_review=bool(
                    doc_meta.get("classification_requires_review") or False
                ),
                results=file_results,
            )
        )

    # ------------------------------------------------------------------
    # Шаг 6. Сортировка строк по риску, карантин в конец
    # ------------------------------------------------------------------

    def sort_key(row: DocumentMatrixRowDTO | SegmentMatrixRowDTO) -> tuple[int, int, int]:
        critical_fails = sum(
            1 for c in row.results.values() if c.result == "fail" and c.severity == "critical"
        )
        all_fails = sum(1 for c in row.results.values() if c.result == "fail")
        quarantine_flag = 1 if row.status == "quarantine" else 0
        return (quarantine_flag, -critical_fails, -all_fails)

    file_rows.sort(key=sort_key)
    segment_rows.sort(key=sort_key)

    # ------------------------------------------------------------------
    # Шаг 7. Финальная сборка ответа
    # ------------------------------------------------------------------
    return DDMatrixResponseDTO(
        deal_id=agg.deal_id,
        run_id=agg.run_id,
        deal_name=agg.deal_name,
        checks=checks_list,
        global_check_ids=global_check_ids,
        doc_type_check_ids=dict(doc_type_check_ids),
        documents=file_rows,
        segment_documents=segment_rows,
        total_documents=agg.total_documents,
        total_checks=agg.total_checks,
        severity_counts=agg.severity_counts.to_dict(),
        quarantine_count=agg.quarantine_count,
        degraded_count=agg.degraded_count,
        evidence_validity_rate=round(agg.evidence_validity_rate, 3),
    )
