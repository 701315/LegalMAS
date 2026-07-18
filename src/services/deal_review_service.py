# src/services/deal_review_service.py

"""
Сервис для UI-обзора сделки (deal review).

Задачи:
- загрузить из БД документы, результаты проверок и имя сделки для рана
- построить AggregatedResults через Aggregator
- делегировать построение DTO в review_presenter и dd_matrix_builder
- построить DD Grid V1 response (с persisted instruction snapshots)

Архитектурный принцип:
  Бэкенд строит ОДНУ полную таблицу (AggregatedResults) содержащую все
  результаты всех чеков по всем документам рана. Из неё строятся все
  представления через специализированные builder'ы.

  Этот сервис является тонким координатором:
  - загрузка данных из БД (UoW)
  - вызов агрегатора
  - делегирование построения DTO в review_presenter и dd_matrix_builder
  - оркестрация DD Grid V1 (с DatabaseInstructionProvider для инвариантности)
"""

from __future__ import annotations

import uuid
from typing import Any

from core.logging import get_logger
from db.repositories.deal_repo import DealRepository
from db.repositories.playbook_repo import PlaybookRepository
from db.repositories.run_repo import RunRepository
from db.repositories.runner_repo import RunnerRepository
from db.uow import db_uow
from services.export.aggregator import aggregate_results
from services.export.models import AggregatedResults

# Новые специализированные компоненты
from services import review_presenter
from services.dd_matrix_builder import build_dd_matrix

# Engine
from classifiers.yaml_registry import YAMLRegistry
from db.repositories.document_type_instruction_version_repo import (
    DocumentTypeInstructionVersionRepository,
)
from engine.doc_type_checks.loader import (
    DatabaseInstructionProvider,
    DocTypeCheckLoader,
)
from engine.playbook.loader import load_playbook_from_version
from engine.playbook.models import CheckDefinition
from services.dd_grid_v1_builder import (
    CheckSubgroupDTO,
    DDGridV1Data,
    build_dd_grid_v1,
)

# API schemas
from api.schemas.deal_review import (
    DDGridV1ResponseDTO,
    DDMatrixResponseDTO,
    DocumentDetailDTO,
    DocumentSummaryDTO,
    ConditionalCheckDTO,
    DDRequestDTO,
    ExtractedValueDTO,
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

    Возвращает кортеж:
    - aggregated: AggregatedResults — единый источник данных для всех экспортов
    - documents: словарь {document_id: {name, folder_path, doc_type, ...}}
    """
    deal_uuid = uuid.UUID(deal_id)
    run_uuid = uuid.UUID(run_id)

    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        deal_repo = DealRepository(uow.session)

        documents = await runner_repo.load_documents_for_run(run_uuid)
        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        deal = await deal_repo.internal_unsafe_get_by_id(deal_uuid)

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
# Делегирование в review_presenter
# ---------------------------------------------------------------------------


def build_document_summaries(
    agg: AggregatedResults,
    documents: dict[str, dict[str, Any]],
) -> list[DocumentSummaryDTO]:
    """Делегирует в review_presenter."""
    return review_presenter.build_document_summaries(agg, documents)


def build_document_detail(
    agg: AggregatedResults,
    documents: dict[str, dict[str, Any]],
    document_id: str,
) -> DocumentDetailDTO:
    """Делегирует в review_presenter."""
    return review_presenter.build_document_detail(agg, documents, document_id)


def build_dd_requests(agg: AggregatedResults) -> list[DDRequestDTO]:
    """Делегирует в review_presenter."""
    return review_presenter.build_dd_requests(agg)


def build_conditional_checks(agg: AggregatedResults) -> list[ConditionalCheckDTO]:
    """Делегирует в review_presenter."""
    return review_presenter.build_conditional_checks(agg)


def build_extracted_values(agg: AggregatedResults) -> list[ExtractedValueDTO]:
    """Делегирует в review_presenter."""
    return review_presenter.build_extracted_values(agg)


# ---------------------------------------------------------------------------
# Делегирование в dd_matrix_builder
# ---------------------------------------------------------------------------


def build_dd_matrix(
    agg: AggregatedResults,
    documents: dict[str, dict[str, Any]],
) -> DDMatrixResponseDTO:
    """
    Делегирует построение матрицы рисков в dd_matrix_builder.
    Используется эндпоинтом GET /deals/{deal_id}/runs/{run_id}/dd-matrix.
    """
    return build_dd_matrix(agg, documents)


# ---------------------------------------------------------------------------
# DD Grid V1 — оркестрация с persisted instruction snapshots
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

    def _map_subgroup(sg: CheckSubgroupDTO) -> DDGridCheckSubgroupDTO:
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

    global_groups_dto = [
        DDGridGlobalGroupDTO(
            group_id=g.group_id,
            label=g.label,
            display_order=g.display_order,
            checks=[_map_subgroup(sg) for sg in g.checks],
        )
        for g in data.global_groups
    ]

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


def _collect_dd_grid_v1_checks(
    *,
    playbook_checks: list[CheckDefinition],
    check_results: list[dict[str, Any]],
    documents: dict[str, dict[str, Any]],
    doc_type_loader: DocTypeCheckLoader | None = None,
) -> list[CheckDefinition]:
    """
    Собрать полный список CheckDefinition для построения DD Grid V1 response.

    Использует переданный doc_type_loader (DatabaseInstructionProvider в production).
    Это гарантирует, что DD Grid строится по тем же версиям инструкций,
    которые были зафиксированы в момент запуска Run (инвариант воспроизводимости).

    Логика:
    1. Global checks берутся из playbook.compiled_checks.
    2. Doc-type checks загружаются через loader ТОЛЬКО если в результатах есть
       записи с origin != GLOBAL_PLAYBOOK (сохраняем поведение global_only runs).
    3. Doc-type checks фильтруются по фактическим check_id из check_results.
    4. Duplicate check_id дедуплицируются: doc_types объединяются.
    """
    # Шаг 1: check_id, которые были выполнены как doc-type
    non_global_check_ids: set[str] = set()
    for row in check_results:
        origin = (row.get("origin") or "").strip().upper()
        if origin and origin != "GLOBAL_PLAYBOOK":
            check_id = row.get("check_id")
            if check_id:
                non_global_check_ids.add(str(check_id))

    if not non_global_check_ids:
        logger.debug(
            "DD Grid V1: no doc-type check results, using global checks only",
            playbook_checks_count=len(playbook_checks),
        )
        return list(playbook_checks)

    # Шаг 2: (doc_type, triggers) пары из documents
    doc_type_trigger_pairs: list[tuple[str, tuple[str, ...]]] = []
    seen_pairs: set[tuple[str, tuple[str, ...]]] = set()
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
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            doc_type_trigger_pairs.append(pair)

    # Шаг 3: загружаем checks через loader (Filesystem или Database)
    loader = doc_type_loader or DocTypeCheckLoader()
    loaded_by_id: dict[str, CheckDefinition] = {}

    for doc_type, triggers in doc_type_trigger_pairs:
        try:
            loaded = loader.load_checks_for_doc(
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

        for check in loaded:
            if check.id not in non_global_check_ids:
                continue
            existing = loaded_by_id.get(check.id)
            if existing is None:
                loaded_by_id[check.id] = check
            else:
                merged = list(existing.doc_types or [])
                for dt in (check.doc_types or []):
                    if dt not in merged:
                        merged.append(dt)
                loaded_by_id[check.id] = existing.model_copy(update={"doc_types": merged})

    doc_type_checks = list(loaded_by_id.values())

    # Диагностика
    missing = non_global_check_ids - set(loaded_by_id.keys())
    if missing:
        logger.warning(
            "DD Grid V1: some doc-type check results have no matching CheckDefinition",
            missing_check_ids=sorted(missing),
            searched_doc_types=sorted({dt for dt, _ in doc_type_trigger_pairs}),
        )

    logger.info(
        "DD Grid V1: collected checks",
        global_checks=len(playbook_checks),
        doc_type_checks=len(doc_type_checks),
        non_global_result_ids=len(non_global_check_ids),
        missing_from_source=len(missing),
    )

    return list(playbook_checks) + doc_type_checks


async def build_dd_grid_v1_response(
    deal_id: str,
    run_id: str,
) -> DDGridV1ResponseDTO:
    """
    Загрузить данные и построить DD Grid V1 response.

    Ключевой архитектурный инвариант:
    Если Run содержит instruction_versions (зафиксированные версии инструкций),
    DD Grid строится по snapshot'ам из БД через DatabaseInstructionProvider.
    Это гарантирует, что Grid показывает те же checks, что выполнялись в Run,
    даже если YAML-файлы на диске изменились после запуска.

    Загрузка:
    1. Run → playbook_version_id + instruction_versions
    2. PlaybookVersion.compiled_checks → PlaybookDefinition → list[CheckDefinition]
    3. instruction_versions → DocumentTypeInstructionVersion → compiled_payload
    4. DatabaseInstructionProvider(compiled_payload) → DocTypeCheckLoader
    5. check_results + documents из RunnerRepository
    """
    run_uuid = uuid.UUID(run_id)
    deal_uuid = uuid.UUID(deal_id)

    async with db_uow() as uow:
        run_repo = RunRepository(uow.session)
        runner_repo = RunnerRepository(uow.session)
        pb_repo = PlaybookRepository(uow.session)
        deal_repo = DealRepository(uow.session)
        instr_repo = DocumentTypeInstructionVersionRepository(uow.session)

        # Загрузка Run
        run = await run_repo.get_by_id(run_uuid)
        if not run:
            raise ValueError(f"Run {run_id} not found")
        if str(run.deal_id) != deal_id:
            raise ValueError(f"Run {run_id} does not belong to deal {deal_id}")

        # Загрузка PlaybookVersion
        pb_version = await pb_repo.get_by_id(run.playbook_version_id)
        if not pb_version:
            raise ValueError(f"PlaybookVersion {run.playbook_version_id} not found")

        # Загрузка результатов и документов
        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        documents = await runner_repo.load_documents_for_run(run_uuid)

        # Валидация deal
        deal = await deal_repo.internal_unsafe_get_by_id(deal_uuid)
        if not deal:
            raise ValueError(f"Deal {deal_id} not found")

        # Построение DocTypeCheckLoader из зафиксированных snapshot'ов.
        # Если instruction_versions пуст — loader упадёт на FilesystemProvider,
        # что допустимо только для старых Run, созданных до введения фиксации.
        compiled_map: dict[str, dict] = {}
        if run.instruction_versions:
            for doc_type, version_id_str in run.instruction_versions.items():
                try:
                    version_id = uuid.UUID(version_id_str)
                    version_obj = await instr_repo.get_by_id(version_id)
                    if version_obj and version_obj.compiled_payload:
                        compiled_map[doc_type] = version_obj.compiled_payload
                    else:
                        logger.warning(
                            "DD Grid V1: instruction version not found or has no payload",
                            doc_type=doc_type,
                            version_id=version_id_str,
                        )
                except (ValueError, Exception) as exc:
                    logger.warning(
                        "DD Grid V1: failed to load instruction version",
                        doc_type=doc_type,
                        version_id=version_id_str,
                        error=str(exc),
                    )

    # После закрытия UoW работаем только с примитивами
    playbook = load_playbook_from_version(pb_version)

    # Если есть зафиксированные версии — используем DatabaseProvider.
    # Если нет — FilesystemProvider (fallback для legacy runs).
    if compiled_map:
        provider = DatabaseInstructionProvider(compiled_map)
        logger.info(
            "DD Grid V1: using DatabaseInstructionProvider (persisted snapshots)",
            run_id=run_id,
            doc_types_count=len(compiled_map),
        )
    else:
        provider = None
        logger.warning(
            "DD Grid V1: no instruction_versions in Run, falling back to FilesystemProvider",
            run_id=run_id,
        )

    persisted_loader = DocTypeCheckLoader(provider=provider)

    checks = _collect_dd_grid_v1_checks(
        playbook_checks=playbook.checks,
        check_results=check_results,
        documents=documents,
        doc_type_loader=persisted_loader,
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
        using_persisted_instructions=bool(compiled_map),
    )

    grid_data = build_dd_grid_v1(
        checks=checks,
        check_results=check_results,
        documents=documents,
        registry=registry,
    )

    return _map_dd_grid_v1_to_response(grid_data, deal_id, run_id)


