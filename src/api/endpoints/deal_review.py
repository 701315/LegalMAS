# src/api/endpoints/deal_review.py

"""
FastAPI-эндпоинты для UI-обзора сделки (deal review).

Все эндпоинты требуют роли viewer/editor/admin в проекте.
Данные строятся через load_aggregated_results → build_* функции сервиса.

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

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from db.session import get_db
from db.repositories.run_repo import RunRepository
from db.repositories.playbook_repo import PlaybookRepository
from services.deal_review_service import (
    build_conditional_checks,
    build_dd_matrix,
    build_dd_requests,
    build_document_detail,
    build_document_summaries,
    build_extracted_values,
    load_aggregated_results,
)
from ..schemas.deal_review import (
    ConditionalCheckDTO,
    DDMatrixResponseDTO,
    DDRequestDTO,
    DocumentDetailDTO,
    DocumentStructuredDataDTO,
    DocumentSummaryDTO,
    ExtractedValueDTO,
)

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
    agg, documents = await load_aggregated_results(deal_id, run_id)
    return build_document_summaries(agg, documents)


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
    agg, documents = await load_aggregated_results(deal_id, run_id)
    if document_id not in documents:
        raise HTTPException(status_code=404, detail="Document not found")
    return build_document_detail(agg, documents, document_id)


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
    # Загружаем run + проверяем права — нам нужен объект run для метаданных
    run = await _get_run_with_access_check(deal_id, run_id, db, user)

    # Загружаем агрегацию
    agg, documents = await load_aggregated_results(deal_id, run_id)

    doc_meta = documents.get(document_id)
    if not doc_meta:
        raise HTTPException(status_code=404, detail="Document not found in this run")

    # Загружаем имя плейбука — у run есть playbook_version_id
    playbook_name: str | None = None
    playbook_version_id_str: str | None = None
    if getattr(run, "playbook_version_id", None):
        playbook_version_id_str = str(run.playbook_version_id)
        try:
            pb_repo = PlaybookRepository(db)
            pv = await pb_repo.get_by_id(run.playbook_version_id)
            playbook_name = pv.name if pv else None
        except Exception:
            # Не критично — имя плейбука не блокирует ответ
            pass

    # Фильтруем значения строго по document_id (не по имени — имена могут совпадать)
    all_values = build_extracted_values(agg)
    # structured_value_rows хранят document_id — используем его для точной фильтрации
    doc_values = [
        v for sv, v in zip(agg.structured_value_rows, all_values)
        if sv.document_id == document_id
    ]

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
    Список DD-запросов сгенерированных по fail-результатам рана.
    Дедуплицированы по check_id, отсортированы по приоритету.

    Доступ: viewer / editor / admin проекта.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )
    agg, _ = await load_aggregated_results(deal_id, run_id)
    return build_dd_requests(agg)


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
    agg, _ = await load_aggregated_results(deal_id, run_id)
    return build_conditional_checks(agg)


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
    agg, _ = await load_aggregated_results(deal_id, run_id)
    return build_extracted_values(agg)


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

    Возвращает DDMatrixResponseDTO — готовую структуру для рендеринга
    матрицы на фронтенде без дополнительных запросов:

    - checks: реестр всех чеков (описания столбцов)
    - global_check_ids: столбцы для вкладки «Глобальные проверки»
    - doc_type_check_ids: столбцы для вкладок по типам документов
    - documents: строки матрицы, отсортированы по убыванию рисков
      (сначала документы с наибольшим числом critical fail)

    Ячейки матрицы (MatrixCellDTO):
    - result / severity — цвет ячейки
    - snippet + page + clause_uid — pinpoint evidence
    - extracted — список структурированных значений этого чека
    - qc_status — статус ручной проверки QC

    Отсутствие ячейки в results означает что чек не применялся
    к документу (n/a) — фронт рисует серую ячейку.

    Доступ: viewer / editor / admin проекта.
    """
    await require_project_role(
        db=db,
        user=user,
        deal_id=uuid.UUID(deal_id),
        allowed_roles=("admin", "editor", "viewer"),
    )
    agg, documents = await load_aggregated_results(deal_id, run_id)
    return build_dd_matrix(agg, documents)
