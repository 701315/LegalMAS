# src/api/endpoints/results.py

"""
Эндпоинты для результатов проверок (check_results).

- GET /results — список результатов с фильтрами:
    - conditional_only: только условные проверки
    - has_structured_data: только результаты со structured_data

- GET /results/{result_id}/evidence — подробная информация о доказательствах
  (место в документе, сниппет текста, служебные поля).
"""

from typing import List
import uuid

from fastapi import APIRouter, Depends, Query, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from api.deps.auth import CurrentUser, get_current_user
from db.session import get_db
from db.repositories.result_repo import ResultRepository
from db.repositories.check_result_repo import CheckResultRepository
from db.models.result import CheckResult
from ..schemas.results import CheckResultResponse

from pydantic import BaseModel

router = APIRouter(prefix="/results", tags=["results"])


class EvidenceResponse(BaseModel):
    """
    Структура ответа с доказательствами (evidence) для одного результата проверки.

    Эту структуру читает фронтенд через src/api/evidence.ts как EvidenceDetail.
    Часть полей (doc_type, yaml_instruction_ref) пока заполняем None,
    позже их можно будет обогатить связями c документом и плейбуком.
    """

    # Идентификаторы
    result_id: uuid.UUID
    document_id: uuid.UUID
    run_id: uuid.UUID

    # Основная информация о результате
    severity: str
    result: str  # fail / pass / unclear

    # Текстовое описание найденного (краткое)
    value_text: str | None = None

    # Указатель на место в документе / артефакт
    evidence_ref: str | None = None

    # Метаданные для навигации и подсветки
    page: int | None = None
    clause_uid: str | None = None
    element_id: str | None = None
    bbox: dict | None = None

    # Служебные поля детектора
    confidence: float | None = None
    detector_used: str | None = None
    origin: str | None = None

    # Расширения для фронта (пока не заполняем)
    doc_type: str | None = None
    yaml_instruction_ref: str | None = None


@router.get(
    "",
    response_model=List[CheckResultResponse],
    summary="Список результатов проверок с фильтрами",
)
async def list_results(
    deal_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    conditional_only: bool | None = Query(
        default=None,
        description="Если true — вернуть только условные проверки",
    ),
    has_structured_data: bool | None = Query(
        default=None,
        description="Если true — вернуть только результаты с structured_data",
    ),
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Возвращает список результатов проверок.

    Фильтры:
    - deal_id: по сделке;
    - run_id: по run;
    - conditional_only: только условные проверки;
    - has_structured_data: только результаты, где structured_data не пустой.

    ВАЖНО:
    - Сейчас этот эндпоинт не проверяет, есть ли у пользователя доступ
      к указанной сделке/run. Он предполагается как admin/diagnostic.
    - Когда будет готова полная ACL, можно:
        * либо ограничить его только для глобальных админов;
        * либо проверять доступ через deal_id/run_id и роли проекта.
    """

    repo = ResultRepository(db)

    # Базовая загрузка — подстрой под свой репозиторий:
    if run_id:
        # Используем вариант с join документов и уже готовыми dict'ами
        raw_results = await repo.get_by_run_with_docs(uuid.UUID(run_id))
        out: List[CheckResultResponse] = [
            CheckResultResponse.model_validate(r) for r in raw_results
        ]
    elif deal_id:
        # TODO: когда появится get_by_deal / list_latest, сюда можно
        # добавить полноценную реализацию выборки по сделке.
        results = (
            await repo.get_by_run_with_docs(uuid.UUID(run_id))
            if run_id
            else []
        )
        out = [CheckResultResponse.model_validate(r) for r in results]
    else:
        # Пока без дополнительных фильтров — возвращаем пустой список.
        # При необходимости можно будет добавить выборку "последнего run по проекту".
        out = []

    # Фильтр: только условные проверки
    if conditional_only is True:
        out = [r for r in out if r.conditional_check_triggered]

    # Фильтр: только с structured_data
    if has_structured_data is True:
        out = [r for r in out if r.structured_data]

    return out


@router.get(
    "/{result_id}/evidence",
    response_model=EvidenceResponse,
    summary="Получить доказательства (evidence) по результату проверки",
)
async def get_evidence(
    result_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    Возвращает подробную информацию о доказательствах (evidence) для одного CheckResult.

    Технические сценарии:
    - Некорректный UUID -> 400.
    - Результат не найден -> 404.
    - Успех -> 200 + структура EvidenceResponse.
    """

    # 1. Валидируем формат UUID
    try:
        result_uuid = uuid.UUID(result_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid result_id format")

    # 2. Ищем результат в базе
    # TODO (улучшение 16): перенести в CheckResultRepository.get_by_id
    stmt = select(CheckResult).where(CheckResult.id == result_uuid)
    db_result = await db.execute(stmt)
    check_result: CheckResult | None = db_result.scalar_one_or_none()

    if check_result is None:
        raise HTTPException(status_code=404, detail="Result not found")

    # 3. TODO: добавить ACL‑проверку доступа к сделке/документу.

    return EvidenceResponse(
        result_id=check_result.id,
        document_id=check_result.document_id,
        run_id=check_result.run_id,
        severity=check_result.severity,
        result=check_result.result,
        value_text=check_result.value_text,
        evidence_ref=check_result.evidence_ref,
        page=check_result.page,
        clause_uid=check_result.clause_uid,
        element_id=check_result.element_id,
        bbox=check_result.bbox,
        confidence=check_result.confidence,
        detector_used=check_result.detector_used,
        origin=check_result.origin,
        doc_type=None,
        yaml_instruction_ref=None,
    )


@router.get(
    "/debug/{result_id}",
    summary="DEBUG: проверить, есть ли CheckResult с таким id",
)
async def debug_check_result(
    result_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    """
    DEBUG-эндпоинт для проверки наличия CheckResult по id.

    ВАЖНО:
    - Доступен ТОЛЬКО для глобальной роли superadmin.
    - Возвращает внутренние идентификаторы (run_id, document_id),
      поэтому должен быть максимально ограничен.
    """

    # NEW: защита по глобальной роли
    if user.global_role != "superadmin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin only",
        )

    try:
        result_uuid = uuid.UUID(result_id)
    except ValueError:
        return {"ok": False, "reason": "invalid_uuid"}

    stmt = select(CheckResult).where(CheckResult.id == result_uuid)
    db_result = await db.execute(stmt)
    obj = db_result.scalar_one_or_none()

    if obj is None:
        return {"ok": False, "reason": "not_found"}

    return {
        "ok": True,
        "result_id": str(obj.id),
        "run_id": str(obj.run_id),
        "document_id": str(obj.document_id),
        "has_evidence_ref": bool(obj.evidence_ref),
        "page": obj.page,
        "clause_uid": obj.clause_uid,
        "element_id": obj.element_id,
    }