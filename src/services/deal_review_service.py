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
    DDGridV1ResponseDTO,
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
from classifiers.yaml_registry import YAMLRegistry
from db.repositories.playbook_repo import PlaybookRepository
from db.repositories.run_repo import RunRepository
from engine.doc_type_checks.loader import DocTypeCheckLoader
from engine.playbook.models import CheckDefinition
from engine.playbook.loader import load_playbook_from_version
from services.dd_grid_v1_builder import (
    CheckSubgroupDTO,
    DDGridV1Data,
    build_dd_grid_v1,
)
from api.schemas.deal_review import DDGridV1ResponseDTO



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
                # Segment metadata
                segment_id=row.segment_id or None,
                segment_type=row.segment_type or None,
                segment_title=row.segment_title or None,
                segment_order=row.segment_order,
                is_primary_segment=row.is_primary_segment,
                # Canonical display semantics — thin projection из ExportRow.
                # ExportRow уже несёт денормализованные поля из CheckResult.
                # build_document_detail не переформирует текст — только проецирует.
                display_text=row.display_text,
                review_status=row.review_status,
                review_message=row.review_message,
                needs_manual_review=row.needs_manual_review,
                ui_mode=row.ui_mode,
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
            # Segment provenance для viewer navigation
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
      2. Из agg.structured_value_rows строим два индекса:
         - segment-aware: (doc_id, seg_id, check_id) → [ExtractedFieldDTO]
         - fallback:      (doc_id, check_id) → [ExtractedFieldDTO]
         Segment-aware индекс используется для SegmentMatrixRowDTO ячеек,
         fallback — для legacy DocumentMatrixRowDTO и как запасной вариант.
      3. Строим индекс результатов на уровне файла: (doc_id, check_id) → ExportRow.
         Это legacy-слой для DocumentMatrixRowDTO.
      4. Строим segment-ориентированные строки: группируем agg.rows по
         (document_id, segment_id), внутри — по check_id, выбираем "лучший"
         ExportRow по result/severity/confidence и формируем SegmentMatrixRowDTO.
         MatrixCellDTO получает canonical display semantics из ExportRow.
      5. Строим legacy file-ориентированные строки (как было раньше), чтобы
         не ломать текущий фронт: DocumentMatrixRowDTO по (doc_id, check_id).
         MatrixCellDTO также получает canonical display semantics.
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
    # Шаг 2. Индекс структурированных значений
    #
    # Segment-aware ключ: (doc_id, seg_id, check_id)
    #   Используется для ячеек segment_documents — каждый сегмент получает
    #   только свои extracted values, а не все значения документа.
    #
    # Fallback ключ: (doc_id, check_id)
    #   Используется для legacy file-level ячеек и как запасной вариант
    #   когда segment-aware ключ не найден (seg_id пустой).
    # ------------------------------------------------------------------
    sv_index_segment: dict[tuple[str, str, str], list[ExtractedFieldDTO]] = defaultdict(list)
    sv_index_fallback: dict[tuple[str, str], list[ExtractedFieldDTO]] = defaultdict(list)

    for sv in agg.structured_value_rows:
        extracted_field = ExtractedFieldDTO(
            field_name=sv.field_name,
            field_value=sv.field_value,
            field_format=sv.field_format,
        )
        seg_id = sv.segment_id or ""
        # Segment-aware индекс
        sv_index_segment[(sv.document_id, seg_id, sv.check_id)].append(extracted_field)
        # Fallback индекс (doc-level) — агрегирует все сегменты
        sv_index_fallback[(sv.document_id, sv.check_id)].append(extracted_field)

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

    segment_rows: list[SegmentMatrixRowDTO] = []

    for (doc_id, seg_id), rows_for_segment in segment_groups.items():
        doc_meta = documents.get(doc_id, {})
        r0 = rows_for_segment[0]

        by_check: dict[str, list[Any]] = defaultdict(list)
        for r in rows_for_segment:
            by_check[r.check_id].append(r)

        segment_results: dict[str, MatrixCellDTO] = {}

        for check_id, rows_for_check in by_check.items():
            best = select_best_row(rows_for_check)

            # Segment-aware extracted values:
            # приоритет — точный ключ (doc_id, seg_id, check_id),
            # fallback — (doc_id, check_id) для несегментированных документов.
            sv_seg_key = (doc_id, seg_id, check_id)
            extracted = sv_index_segment.get(sv_seg_key)
            if extracted is None:
                extracted = sv_index_fallback.get((doc_id, check_id), [])

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
                # Canonical display semantics — thin projection из ExportRow.
                # build_dd_matrix не переформирует текст — только проецирует.
                display_text=best.display_text,
                review_status=best.review_status,
                review_message=best.review_message,
                needs_manual_review=best.needs_manual_review,
                ui_mode=best.ui_mode,
            )

        segment_rows.append(
            SegmentMatrixRowDTO(
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
                extracted=sv_index_fallback.get((doc_id, check_id), []),
                confidence=export_row.confidence or 0.0,
                qc_status=export_row.qc_status or "pending",
                qc_by=export_row.qc_by,
                qc_comment=export_row.qc_comment,
                qc_at=export_row.qc_at,
                conditional_check_triggered=export_row.conditional_check_triggered,
                trigger_name=export_row.trigger_name or "",
                # File-level строки не несут segment provenance —
                # для навигации фронт использует segment_documents.
                segment_id=None,
                segment_type=None,
                segment_title=None,
                segment_order=None,
                is_primary_segment=None,
                chunk_id=None,
                chunk_index=None,
                # Canonical display semantics — thin projection из ExportRow.
                display_text=export_row.display_text,
                review_status=export_row.review_status,
                review_message=export_row.review_message,
                needs_manual_review=export_row.needs_manual_review,
                ui_mode=export_row.ui_mode,
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


    
# ---------------------------------------------------------------------------
# DD Grid V1 — новый builder
# ---------------------------------------------------------------------------


def _map_dd_grid_v1_to_response(
    data: DDGridV1Data,
    deal_id: str,
    run_id: str,
) -> DDGridV1ResponseDTO:
    """
    Перепаковать DDGridV1Data (runtime dataclasses) в Pydantic API DTO.

    Тонкий маппинг: никакой бизнес-логики, только конвертация типов.
    """
    from api.schemas.deal_review import (
        DDGridCellValueDTO,
        DDGridCheckSubgroupDTO,
        DDGridColumnDTO,
        DDGridDocTypeClassDTO,
        DDGridDocTypeNodeDTO,
        DDGridDocumentMetaDTO,
        DDGridDrawerDTO,
        DDGridDrawerFieldDTO,
        DDGridGlobalGroupDTO,
    )

    # Column registry
    column_registry_dto: dict[str, DDGridColumnDTO] = {
        col_id: DDGridColumnDTO(
            column_id=col.column_id,
            check_id=col.column_id.split("__")[0] if "__" in col.column_id else col.column_id,
            label=col.label,
            format=col.format,
            fallback_display=col.fallback_display,
            display_order=col.display_order,
            enum_labels=dict(col.enum_labels),
            unit=col.unit,
        )
        for col_id, col in data.column_registry.items()
    }

    def _map_subgroup(sg: "CheckSubgroupDTO") -> DDGridCheckSubgroupDTO:
        return DDGridCheckSubgroupDTO(
            check_id=sg.check_id,
            check_name=sg.check_name,
            display_order=sg.display_order,
            columns=[
                DDGridColumnDTO(
                    column_id=col.column_id,
                    check_id=col.column_id.split("__")[0] if "__" in col.column_id else col.column_id,
                    label=col.label,
                    format=col.format,
                    fallback_display=col.fallback_display,
                    display_order=col.display_order,
                    enum_labels=dict(col.enum_labels),
                    unit=col.unit,
                )
                for col in sg.columns
            ],
            display_summary_field=sg.display_summary_field,
            metadata_fields=list(sg.metadata_fields),
        )

    # Global groups
    global_groups_dto = [
        DDGridGlobalGroupDTO(
            group_id=g.group_id,
            label=g.label,
            display_order=g.display_order,
            checks=[_map_subgroup(sg) for sg in g.checks],
        )
        for g in data.global_groups
    ]

    # Doc type classes
    doc_type_classes_dto = [
        DDGridDocTypeClassDTO(
            group_id=cls.group_id,
            label=cls.label,
            display_order=cls.display_order,
            types=[
                DDGridDocTypeNodeDTO(
                    type_code=t.type_code,
                    name=t.name,
                    checks=[_map_subgroup(sg) for sg in t.checks],
                )
                for t in cls.types
            ],
        )
        for cls in data.doc_type_classes
    ]

    # Cell values
    cell_values_dto: dict[str, dict[str, DDGridCellValueDTO]] = {
        doc_id: {
            col_id: DDGridCellValueDTO(
                cell_state=cell.cell_state,
                display_value=cell.display_value,
                raw_value=cell.raw_value,
                location_clause_ref=cell.location_clause_ref,
                location_page=cell.location_page,
                location_confidence=cell.location_confidence,
                has_location_fallback=cell.has_location_fallback,
                location_fallback_reason=cell.location_fallback_reason,
            )
            for col_id, cell in doc_cells.items()
        }
        for doc_id, doc_cells in data.cell_values.items()
    }

    # Drawer contents
    drawer_contents_dto: dict[str, dict[str, DDGridDrawerDTO]] = {
        doc_id: {
            check_id: DDGridDrawerDTO(
                check_id=drawer.check_id,
                check_name=drawer.check_name,
                document_id=drawer.document_id,
                cell_state=drawer.cell_state,
                reason=drawer.reason,
                review_status=drawer.review_status,
                review_message=drawer.review_message,
                display_text=drawer.display_text,
                execution_status=drawer.execution_status,
                detection_level=drawer.detection_level,
                confidence=drawer.confidence,
                quality_flags=drawer.quality_flags,
                qc_status=drawer.qc_status,
                qc_by=drawer.qc_by,
                qc_at=drawer.qc_at,
                qc_comment=drawer.qc_comment,
                agent_name=drawer.agent_name,
                model_version=drawer.model_version,
                execution_time_ms=drawer.execution_time_ms,
                retry_attempts=drawer.retry_attempts,
                input_tokens=drawer.input_tokens,
                output_tokens=drawer.output_tokens,
                fields=[
                    DDGridDrawerFieldDTO(
                        column_id=f.column_id,
                        field_name=f.field_name,
                        label=f.label,
                        cell_state=f.cell_state,
                        display_value=f.display_value,
                        raw_value=f.raw_value,
                        location_clause_ref=f.location_clause_ref,
                        location_page=f.location_page,
                        location_confidence=f.location_confidence,
                        has_location_fallback=f.has_location_fallback,
                        location_fallback_reason=f.location_fallback_reason,
                    )
                    for f in drawer.fields
                ],
                evidence_items=list(drawer.evidence_items),
            )
            for check_id, drawer in doc_drawers.items()
        }
        for doc_id, doc_drawers in data.drawer_contents.items()
    }

    # Documents meta
    documents_meta_dto = [
        DDGridDocumentMetaDTO(
            document_id=dm.document_id,
            filename=dm.filename,
            doc_type=dm.doc_type,
            status=dm.status,
            folder_path=dm.folder_path,
        )
        for dm in data.documents_meta
    ]

    return DDGridV1ResponseDTO(
        deal_id=deal_id,
        run_id=run_id,
        global_groups=global_groups_dto,
        doc_type_classes=doc_type_classes_dto,
        column_registry=column_registry_dto,
        cell_values=cell_values_dto,
        drawer_contents=drawer_contents_dto,
        documents_meta=documents_meta_dto,
    )


# ---------------------------------------------------------------------------
# Helper: сборка полного списка CheckDefinition для DD Grid V1
# ---------------------------------------------------------------------------


def _collect_dd_grid_v1_checks(
    *,
    playbook_checks: list[CheckDefinition],
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    doc_type_loader: DocTypeCheckLoader | None = None,
) -> list[CheckDefinition]:
    """
    Собрать полный список CheckDefinition для построения DD Grid V1 response.

    Логика:
    1. Global checks берутся из playbook.compiled_checks (playbook_checks).
    2. Doc-type checks подгружаются через DocTypeCheckLoader ТОЛЬКО если
       в check_results реально присутствуют записи с origin != GLOBAL_PLAYBOOK.
       Это сохраняет корректное поведение для global_only runs — иначе grid
       заполнился бы сотнями not_executed ячеек для checks, которые не запускались.
    3. Doc-type checks фильтруются по фактическим check_id из check_results,
       чтобы grid отражал именно то, что было выполнено в конкретном run.
    4. Duplicate check_id (один check применим к нескольким documents/doc_types)
       дедуплицируются: сохраняется первая CheckDefinition, doc_types объединяются.

    Args:
        playbook_checks: global checks из PlaybookVersion.compiled_checks.
        check_results: raw dicts из RunnerRepository.load_check_results_for_run.
        documents: dict {doc_id: {doc_type, applicable_triggers, ...}}.
        doc_type_loader: опционально — для тестируемости. По умолчанию
            создаётся новый DocTypeCheckLoader().

    Returns:
        Объединённый список CheckDefinition для передачи в build_dd_grid_v1().
    """
    # Шаг 1: собираем check_id, которые реально были выполнены как doc-type
    non_global_check_ids: set[str] = set()
    for row in check_results:
        origin = (row.get("origin") or "").strip().upper()
        if origin and origin != "GLOBAL_PLAYBOOK":
            check_id = row.get("check_id")
            if check_id:
                non_global_check_ids.add(str(check_id))

    # Шаг 2: если нет doc-type результатов — возвращаем только global.
    # Это сохраняет корректное поведение global_only run.
    if not non_global_check_ids:
        logger.debug(
            "DD Grid V1: no doc-type check results, using global checks only",
            playbook_checks_count=len(playbook_checks),
        )
        return list(playbook_checks)

    # Шаг 3: собираем (doc_type, applicable_triggers) пары из documents
    doc_type_trigger_pairs: list[tuple[str, tuple[str, ...]]] = []
    seen_doc_type_trigger: set[tuple[str, tuple[str, ...]]] = set()
    for doc_info in documents.values():
        if not isinstance(doc_info, dict):
            continue
        doc_type = doc_info.get("doc_type")
        if not doc_type:
            continue
        triggers = doc_info.get("applicable_triggers") or []
        if not isinstance(triggers, (list, tuple)):
            triggers = []
        pair = (str(doc_type), tuple(sorted(str(t) for t in triggers)))
        if pair in seen_doc_type_trigger:
            continue
        seen_doc_type_trigger.add(pair)
        doc_type_trigger_pairs.append(pair)

    # Шаг 4: загружаем doc-type checks через loader
    loader = doc_type_loader or DocTypeCheckLoader()
    loaded_by_id: dict[str, CheckDefinition] = {}

    for doc_type, triggers in doc_type_trigger_pairs:
        try:
            loaded_checks = loader.load_checks_for_doc(
                doc_type=doc_type,
                applicable_triggers=list(triggers),
            )
        except Exception as exc:
            logger.warning(
                "DD Grid V1: failed to load doc-type checks",
                doc_type=doc_type,
                error=str(exc),
            )
            continue

        for check in loaded_checks:
            # Фильтр по фактически выполненным check_id
            if check.id not in non_global_check_ids:
                continue

            existing = loaded_by_id.get(check.id)
            if existing is None:
                loaded_by_id[check.id] = check
            else:
                # Дедупликация: объединяем doc_types если check применим к нескольким типам
                merged_doc_types = list(existing.doc_types or [])
                for dt in (check.doc_types or []):
                    if dt not in merged_doc_types:
                        merged_doc_types.append(dt)
                # Пересобираем CheckDefinition с объединённым doc_types.
                # model_copy сохраняет все остальные поля неизменными.
                loaded_by_id[check.id] = existing.model_copy(
                    update={"doc_types": merged_doc_types}
                )

    doc_type_checks = list(loaded_by_id.values())

    # Шаг 5: диагностика — какие doc-type check_id из результатов не были найдены в YAML
    loaded_ids = set(loaded_by_id.keys())
    missing_from_yaml = non_global_check_ids - loaded_ids
    if missing_from_yaml:
        logger.warning(
            "DD Grid V1: some doc-type check results have no matching CheckDefinition in YAML",
            missing_check_ids=sorted(missing_from_yaml),
            searched_doc_types=sorted({dt for dt, _ in doc_type_trigger_pairs}),
        )

    logger.info(
        "DD Grid V1: collected checks",
        global_checks=len(playbook_checks),
        doc_type_checks=len(doc_type_checks),
        non_global_result_ids=len(non_global_check_ids),
        missing_from_yaml=len(missing_from_yaml),
    )

    return list(playbook_checks) + doc_type_checks


async def build_dd_grid_v1_response(
    deal_id: str,
    run_id: str,
) -> DDGridV1ResponseDTO:
    """
    Загрузить данные и построить DD Grid V1 response.

    Загрузка:
    1. Run → playbook_version_id
    2. PlaybookVersion.compiled_checks → PlaybookDefinition → list[CheckDefinition]
    3. check_results (raw dicts с execution_status)
    4. documents dict
    5. YAMLRegistry singleton

    Returns:
        DDGridV1ResponseDTO — готовая структура для фронтенда.
    """

    run_uuid = uuid.UUID(run_id)
    deal_uuid = uuid.UUID(deal_id)

    async with db_uow() as uow:
        run_repo = RunRepository(uow.session)
        runner_repo = RunnerRepository(uow.session)
        pb_repo = PlaybookRepository(uow.session)
        deal_repo = DealRepository(uow.session)

        run = await run_repo.get_by_id(run_uuid)
        if not run:
            raise ValueError(f"Run {run_id} not found")

        if str(run.deal_id) != deal_id:
            raise ValueError(f"Run {run_id} does not belong to deal {deal_id}")

        pb_version = await pb_repo.get_by_id(run.playbook_version_id)
        if not pb_version:
            raise ValueError(f"PlaybookVersion {run.playbook_version_id} not found")

        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        documents = await runner_repo.load_documents_for_run(run_uuid)
        await deal_repo.get_by_id(deal_uuid)

    playbook = load_playbook_from_version(pb_version)

    # Собираем полный список checks: global + doc-type (если run их выполнял).
    # Логика в _collect_dd_grid_v1_checks — не тащим doc-type checks для
    # global_only runs, чтобы не наполнять grid not_executed ячейками.
    checks = _collect_dd_grid_v1_checks(
        playbook_checks=playbook.checks,
        check_results=check_results,
        documents=documents,
    )

    registry = YAMLRegistry.get_instance()

    logger.info(
        "Building DD Grid V1 response",
        deal_id=deal_id,
        run_id=run_id,
        checks_count=len(checks),
        playbook_checks_count=len(playbook.checks),
        doc_type_checks_count=len(checks) - len(playbook.checks),
        check_results_count=len(check_results),
        documents_count=len(documents),
    )

    grid_data = build_dd_grid_v1(
        checks=checks,
        check_results=check_results,
        documents=documents,
        registry=registry,
    )

    return _map_dd_grid_v1_to_response(grid_data, deal_id, run_id)



