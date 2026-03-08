# src/api/endpoints/results.py

"""
Эндпоинты для результатов проверок (check_results).

- GET /results — список результатов с фильтрами:
    - conditional_only: только условные проверки
    - has_structured_data: только результаты со structured_data
"""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from db.session import get_db
from db.repositories.result_repo import ResultRepository
from ..schemas.results import CheckResultResponse

router = APIRouter(prefix="/results", tags=["results"])


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
        results = await repo.get_by_run(run_id)
    elif deal_id:
        results = await repo.get_by_deal(deal_id)
    else:
        results = await repo.list_latest(limit=500)

    # Преобразуем к Pydantic, если repo отдаёт ORM
    out: List[CheckResultResponse] = [
        CheckResultResponse.model_validate(r) for r in results
    ]

    # Фильтр: только условные проверки
    if conditional_only is True:
        out = [r for r in out if r.conditional_check_triggered]

    # Фильтр: только с structured_data
    if has_structured_data is True:
        out = [r for r in out if r.structured_data]

    return out
