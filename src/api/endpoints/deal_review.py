# src/api/endpoints/deal_review.py

"""
FastAPI-эндпоинты для UI-обзора сделки (deal review).

Все эндпоинты требуют роли viewer/editor/admin в проекте.
Данные строятся через прямое чтение check_results из БД.

Маршруты:
  GET /{deal_id}/runs/{run_id}/documents
      Список документов со счётчиками рисков.

  GET /{deal_id}/runs/{run_id}/documents/{document_id}
      Детальная карточка документа со всеми проверками.

  GET /{deal_id}/runs/{run_id}/documents/{document_id}/structured-data
      Структурированные значения по одному документу.

  GET /{deal_id}/runs/{run_id}/dd-requests
      DD-запросы по результатам рана.

  GET /{deal_id}/runs/{run_id}/conditional-checks
      Сработавшие условные проверки.

  GET /{deal_id}/runs/{run_id}/extracted-values
      Все извлечённые структурированные значения.

  GET /{deal_id}/runs/{run_id}/dd-matrix
      Матричное представление DD Grid (документы × чеки).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from db.models.run import Run
from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from db.repositories.playbook_repo import PlaybookRepository
from db.repositories.run_repo import RunRepository
from db.session import get_db
from services.deal_review_service import (
    build_conditional_checks,
    build_dd_grid_v1_response,
    build_dd_matrix,
    build_dd_requests,
    build_extracted_values,
)

from ..schemas.deal_review import (
    CheckItemDTO,
    ConditionalCheckDTO,
    DDGridV1ResponseDTO,
    DDMatrixResponseDTO,
    DDRequestDTO,
    DocumentDetailDTO,
    DocumentStructuredDataDTO,
    DocumentSummaryDTO,
    ExtractedValueDTO,
)

from db.models.deal import Deal  # добавить к существующим импортам

router = APIRouter(prefix="/deals", tags=["deal_review"])


# ---------------------------------------------------------------------------
# Вспомогательная функция: проверка доступа + загрузка run
# Используется в эндпоинтах которым нужен объект run (не только deal_id).
# ---------------------------------------------------------------------------


async def _get_run_with_access_check(
    deal_id: str,
    run_id: str,
    db: AsyncSession,
    user: CurrentUser,
) -> object:
    """
    Загрузить Run из БД и проверить что:
    1. Run существует.
    2. Run принадлежит указанной сделке.
    3. Пользователь имеет роль viewer/editor/admin в этой сделке.

    Возвращает объект Run.
    Выбрасывает HTTPException 404 / 400 / 403 при нарушении условий.
    """
    run_repo = RunRepository(db)
    run = await run_repo.get_by_id(uuid.UUID(run_id))
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    if str(run.deal_id) != deal_id:
        raise HTTPException(status_code=400, detail="Run does not belong to this deal")

    await require_project_role(
        db=db,
        user=user,
        deal_id=run.deal_id,
        allowed_roles=("admin", "editor", "viewer"),
    )
    return run


# ---------------------------------------------------------------------------
# Эндпоинты
# ---------------------------------------------------------------------------


@router.get(
    "/{deal_id}/runs/{run_id}/documents",
    response_model=list[DocumentSummaryDTO],
    summary="Список документов и рисков для run",
)
async def get_documents_for_run(
    deal_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Список документов со счётчиками рисков по уровням критичности
    для указанного рана.

    Доступ: viewer / editor / admin проекта.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )

    run_uuid = uuid.UUID(run_id)
    from db.repositories.runner_repo import RunnerRepository
    from db.uow import db_uow

    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        documents = await runner_repo.load_documents_for_run(run_uuid)

    # Прямой подсчёт severity по документам
    doc_stats: dict[str, dict[str, int]] = {
        doc_id: {"critical": 0, "high": 0, "medium": 0, "pass": 0, "unclear": 0}
        for doc_id in documents.keys()
    }

    for cr in check_results:
        doc_id = cr.get("document_id", "")
        if doc_id not in doc_stats:
            continue

        result = cr.get("result", "unclear")
        severity = cr.get("severity", "medium")

        if result == "fail":
            if severity in doc_stats[doc_id]:
                doc_stats[doc_id][severity] += 1
        elif result == "pass":
            doc_stats[doc_id]["pass"] += 1
        else:
            doc_stats[doc_id]["unclear"] += 1

    # Сборка DTO
    summaries: list[DocumentSummaryDTO] = []
    for doc_id, doc_meta in documents.items():
        stats = doc_stats.get(doc_id, {})
        summaries.append(
            DocumentSummaryDTO(
                document_id=doc_id,
                name=doc_meta.get("name", ""),
                doc_type=doc_meta.get("doc_type", "Generic"),
                status=doc_meta.get("status", ""),
                critical_count=stats.get("critical", 0),
                high_count=stats.get("high", 0),
                medium_count=stats.get("medium", 0),
                pass_count=stats.get("pass", 0),
                unclear_count=stats.get("unclear", 0),
                has_degraded_structure=False,  # Можно добавить если нужно
                in_quarantine=doc_meta.get("status") == "quarantine",
                classification_level=doc_meta.get("classification_level", ""),
                classification_confidence=float(doc_meta.get("classification_confidence", 0.0)),
            )
        )

    summaries.sort(key=lambda s: s.name.lower())
    return summaries


@router.get(
    "/{deal_id}/runs/{run_id}/documents/{document_id}",
    response_model=DocumentDetailDTO,
    summary="Детальная карточка документа для run",
)
async def get_document_detail_for_run(
    deal_id: str,
    run_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Детальная карточка одного документа: все проверки, evidence, structured_data,
    метаданные классификации.

    Доступ: viewer / editor / admin проекта.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )

    run_uuid = uuid.UUID(run_id)
    from db.repositories.runner_repo import RunnerRepository
    from db.uow import db_uow

    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        documents = await runner_repo.load_documents_for_run(run_uuid)

    if document_id not in documents:
        raise HTTPException(status_code=404, detail="Document not found")

    doc_meta = documents[document_id]

    # Фильтруем check_results по document_id
    doc_check_results = [
        cr for cr in check_results
        if cr.get("document_id") == document_id
    ]

    # Сборка CheckItemDTO
    checks: list[CheckItemDTO] = []
    for cr in doc_check_results:
        checks.append(
            CheckItemDTO(
                check_id=cr.get("check_id", ""),
                check_name=cr.get("check_name", ""),
                result=cr.get("result", "unclear"),
                severity=cr.get("severity", "medium"),
                evidence_snippet=(cr.get("display_text") or cr.get("value_text", ""))[:300],
                page=cr.get("page"),
                clause_uid=cr.get("clause_uid", ""),
                confidence=cr.get("confidence", 0.0),
                detector_used=cr.get("detector_used", ""),
                quality_flags={"flags": cr.get("quality_flags")} if cr.get("quality_flags") else None,
                conditional_check_triggered=cr.get("conditional_check_triggered", False),
                trigger_name=cr.get("trigger_name", ""),
                structured_data=cr.get("structured_data") or {},
                origin=cr.get("origin"),
                segment_id=cr.get("segment_id"),
                segment_type=cr.get("segment_type"),
                segment_title=cr.get("segment_title"),
                segment_order=cr.get("segment_order"),
                is_primary_segment=cr.get("is_primary_segment"),
                display_text=cr.get("display_text"),
                review_status=cr.get("review_status"),
                review_message=cr.get("review_message"),
                needs_manual_review=cr.get("needs_manual_review", False),
                ui_mode=cr.get("ui_mode"),
            )
        )

    return DocumentDetailDTO(
        document_id=document_id,
        name=doc_meta.get("name", ""),
        doc_type=doc_meta.get("doc_type", "Generic"),
        status=doc_meta.get("status", ""),
        classification_level=doc_meta.get("classification_level", ""),
        classification_confidence=float(doc_meta.get("classification_confidence", 0.0)),
        applicable_triggers=doc_meta.get("applicable_triggers", []),
        checks=checks,
    )


@router.get(
    "/{deal_id}/runs/{run_id}/documents/{document_id}/structured-data",
    response_model=DocumentStructuredDataDTO,
    summary="Структурированные значения по документу в рамках run",
)
async def get_document_structured_data_for_run(
    deal_id: str,
    run_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Все структурированные значения (суммы, даты, стороны и т.п.)
    извлечённые из одного документа в рамках указанного рана.

    Доступ: viewer / editor / admin проекта.
    """
    run_uuid = uuid.UUID(run_id)
    run = await _get_run_with_access_check(deal_id, run_id, db, user)

    from db.repositories.runner_repo import RunnerRepository
    from db.uow import db_uow

    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        documents = await runner_repo.load_documents_for_run(run_uuid)

    doc_meta = documents.get(document_id)
    if not doc_meta:
        raise HTTPException(status_code=404, detail="Document not found in this run")

    # Загружаем имя плейбука
    playbook_name: str | None = None
    playbook_version_id_str: str | None = None
    if getattr(run, "playbook_version_id", None):
        playbook_version_id_str = str(run.playbook_version_id)
        try:
            pb_repo = PlaybookRepository(db)
            pv = await pb_repo.get_by_id(run.playbook_version_id)
            playbook_name = pv.name if pv else None
        except Exception:
            pass

    # Извлекаем structured values напрямую из check_results
    doc_values: list[ExtractedValueDTO] = []

    for cr in check_results:
        if cr.get("document_id") != document_id:
            continue

        structured_data = cr.get("structured_data") or {}

        for field_name, field_value in structured_data.items():
            # Нормализация значения
            if isinstance(field_value, dict) and "value" in field_value:
                raw_display_value = field_value.get("value")
            else:
                raw_display_value = field_value

            if raw_display_value is None or str(raw_display_value) in ("not_found", "not_defined", "None", ""):
                continue

            display_value = str(raw_display_value)

            # Infer format
            name_lower = field_name.lower()
            if any(x in name_lower for x in ("amount", "price", "sum", "cost")):
                field_format = "money"
            elif any(x in name_lower for x in ("date", "expiry", "term")):
                field_format = "date"
            elif any(x in name_lower for x in ("party", "parties", "entity")):
                field_format = "entity_name"
            else:
                field_format = "text"

            doc_values.append(
                ExtractedValueDTO(
                    document_name=doc_meta.get("name", ""),
                    doc_type=doc_meta.get("doc_type", "Generic"),
                    check_name=cr.get("check_name", ""),
                    field_name=field_name,
                    field_value=display_value,
                    field_format=field_format,
                    page=cr.get("page"),
                    clause_uid=cr.get("clause_uid", ""),
                    segment_id=cr.get("segment_id"),
                    segment_type=cr.get("segment_type"),
                    segment_title=cr.get("segment_title"),
                    segment_order=cr.get("segment_order"),
                    is_primary_segment=cr.get("is_primary_segment"),
                )
            )

    return DocumentStructuredDataDTO(
        deal_id=str(run.deal_id),
        run_id=str(run.id),
        document_id=document_id,
        document_name=doc_meta["name"],
        doc_type=doc_meta["doc_type"],
        playbook_version_id=playbook_version_id_str,
        playbook_name=playbook_name,
        profile=getattr(run, "profile", None),
        total_values=len(doc_values),
        values=doc_values,
    )


@router.get(
    "/{deal_id}/runs/{run_id}/dd-requests",
    response_model=list[DDRequestDTO],
    summary="DD-запросы по результатам run",
)
async def get_dd_requests(
    deal_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Список DD-запросов сгенерированных по missing required полям.
    Дедуплицированы по check_id, отсортированы по приоритету.

    Доступ: viewer / editor / admin проекта.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )

    run_uuid = uuid.UUID(run_id)

    from db.repositories.runner_repo import RunnerRepository
    from db.repositories.playbook_repo import PlaybookRepository
    from db.uow import db_uow
    from db.models.run import Run
    from engine.playbook.loader import load_playbook_from_version

    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        pb_repo = PlaybookRepository(uow.session)

        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        documents = await runner_repo.load_documents_for_run(run_uuid)

        # Загружаем PlaybookVersion для получения CheckDefinition
        run = await uow.session.get(Run, run_uuid)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        pb_version = await pb_repo.get_by_id(run.playbook_version_id)
        if not pb_version:
            raise HTTPException(status_code=404, detail="PlaybookVersion not found")

        playbook = load_playbook_from_version(pb_version)

        # Строим {check_id: CheckDefinition}
        checks_by_id = {check.id: check for check in playbook.checks}

    return build_dd_requests(check_results, documents, checks_by_id)


@router.get(
    "/{deal_id}/runs/{run_id}/conditional-checks",
    response_model=list[ConditionalCheckDTO],
    summary="Список сработавших условных проверок",
)
async def get_conditional_checks(
    deal_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Список условных проверок которые были активированы триггерами
    из applicabletriggers документов в этом ране.

    Доступ: viewer / editor / admin проекта.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )
    run_uuid = uuid.UUID(run_id)
    from db.repositories.runner_repo import RunnerRepository
    from db.uow import db_uow
    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        documents = await runner_repo.load_documents_for_run(run_uuid)
    return build_conditional_checks(check_results, documents)


@router.get(
    "/{deal_id}/runs/{run_id}/extracted-values",
    response_model=list[ExtractedValueDTO],
    summary="Все извлечённые структурированные значения по run",
)
async def get_extracted_values(
    deal_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Все структурированные значения извлечённые по всем документам рана:
    суммы, даты, стороны, кадастровые номера и т.п.

    Доступ: viewer / editor / admin проекта.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )
    run_uuid = uuid.UUID(run_id)
    from db.repositories.runner_repo import RunnerRepository
    from db.uow import db_uow
    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        documents = await runner_repo.load_documents_for_run(run_uuid)
    return build_extracted_values(check_results, documents)


@router.get(
    "/{deal_id}/runs/{run_id}/dd-matrix",
    response_model=DDMatrixResponseDTO,
    summary="Матричное представление DD Grid (документы × чеки)",
)
async def get_dd_matrix(
    deal_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Полное матричное представление результатов DD для рана.

    Доступ: viewer / editor / admin проекта.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )

    run_uuid = uuid.UUID(run_id)

    from db.repositories.runner_repo import RunnerRepository
    from db.repositories.playbook_repo import PlaybookRepository
    from db.repositories.run_repo import RunRepository
    from db.uow import db_uow
    from engine.playbook.loader import load_playbook_from_version

    async with db_uow() as uow:
        runner_repo = RunnerRepository(uow.session)
        pb_repo = PlaybookRepository(uow.session)
        run_repo = RunRepository(uow.session)

        check_results = await runner_repo.load_check_results_for_run(run_uuid)
        documents = await runner_repo.load_documents_for_run(run_uuid)

        # Загружаем PlaybookVersion для CheckDefinition
        run = await run_repo.get_by_id(run_uuid)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")

        pb_version = await pb_repo.get_by_id(run.playbook_version_id)
        if not pb_version:
            raise HTTPException(status_code=404, detail="PlaybookVersion not found")

        playbook = load_playbook_from_version(pb_version)
        checks_by_id = {check.id: check for check in playbook.checks}

        deal = await uow.session.get(Deal, uuid.UUID(deal_id))
        deal_name = deal.name if deal else deal_id

    return build_dd_matrix(
        check_results=check_results,
        documents=documents,
        checks_by_id=checks_by_id,
        deal_id=deal_id,
        run_id=run_id,
        deal_name=deal_name,
    )

@router.get(
    "/{deal_id}/runs/{run_id}/dd-grid-v1",
    response_model=DDGridV1ResponseDTO,
    summary="DD Grid V1 — иерархическое представление (groups → columns → cells)",
)
async def get_dd_grid_v1(
    deal_id: str,
    run_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    DD Grid V1: полная иерархическая структура DD-проверок для нового UI.

    Возвращает DDGridV1ResponseDTO — готовую структуру для рендеринга
    DD Grid без дополнительных запросов к серверу.

    Отличия от /dd-matrix:
    - иерархия global_groups (group → checks → columns)
    - иерархия doc_type_classes (registry groups → types → checks)
    - cell_values с cell_state:
        defined         — значение найдено, display_value форматировано.
        not_defined     — check выполнен, значение не найдено.
        not_applicable  — check не применим к doc_type документа.
        not_executed    — check не выполнялся для этого документа.
        error           — техническая ошибка выполнения.
    - drawer_contents с reason + field details + evidence + location.
    - location propagation:
        exact (high confidence) — clause_ref + page из LLM extraction.
        fallback (low confidence) — check-level ref или null.

    Column formats:
      text           — plain string (+ unit если задан).
      enum           — lookup enum_labels[raw_value].
      yes_no         — 'Да' / 'Нет'.
      presence_only  — 'Присутствует'.

    Drawer reason precedence:
      1. metadata field 'reason'
      2. metadata field 'explanation'
      3. metadata field 'notes'
      4. review_message (CheckResult)
      5. display_text (CheckResult)

    Полный API contract: docs/dd_grid_v1_contract.md

    Доступ: viewer / editor / admin проекта.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )
    try:
        return await build_dd_grid_v1_response(deal_id=deal_id, run_id=run_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    

    