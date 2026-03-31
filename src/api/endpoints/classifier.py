# src/api/endpoints/classifier.py

"""
Classifier endpoints — запуск каскадной классификации документов (workers.classify_document).

Назначение:
- Дать фронту HTTP-эндпоинт, который стартует классификацию документов сделки
  через Celery-воркер workers.classify_document, а не через engine.Runner.

Позиция в архитектуре:
- import → extract → pii → structure → classify (этот эндпоинт) → run_deal_checks → export_results.

Контракт:
- Вход: deal_id (строка UUID).
- Логика:
    1) находим non-duplicate документы сделки через RunnerRepository;
    2) для каждого документа ставим Celery-задачу workers.classify_document;
    3) возвращаем агрегированную статистику (сколько документов найдено и сколько задач запланировано).
- Выход: JSON
    {
        "deal_id": "...",
        "docs_total": N,
        "tasks_scheduled": M
    }

RBAC:
- В production-окружении доступ ограничен ролями (через require_project_role),
  в development может быть ослаблен (как в других эндпоинтах).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps.auth import CurrentUser, get_current_user
from api.deps.security import require_project_role
from core.config import settings
from core.logging import get_logger
from db.repositories.runner_repo import RunnerRepository
from db.session import get_db
from mas_queue.celery_app import celery_app

logger = get_logger(__name__)

router = APIRouter(prefix="/classifier", tags=["classifier"])


@router.post(
    "/runs",
    status_code=status.HTTP_200_OK,
)
async def run_deal_classification(
    deal_id: str,
    db: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """
    Запустить классификацию всех non-duplicate документов сделки через Celery-воркеры.

    Для непрофессионального программиста:
    - Этот эндпоинт НЕ делает классификацию сам.
    - Он только ставит задачи в очередь Celery (workers.classify_document) по каждому документу.
    - Сами воркеры обновят статус документов и при необходимости запустят checks.

    В production:
    - Доступ ограничен ролями (например, admin/editor) через require_project_role.
    """
    # RBAC: в dev-окружении можно ослабить проверку, в prod — требуем роль.
    if settings.ENVIRONMENT == "production":
        await require_project_role(
            db=db,
            user=user,
            project_id=None,  # если есть привязка к проекту, подставь сюда
            required_roles={"admin", "editor"},
        )
    else:
        logger.warning(
            "RBAC check skipped in development mode",
            extra={"endpoint": "POST /classifier/runs", "user_id": str(user.id), "deal_id": deal_id},
        )

    # Валидация deal_id как UUID
    try:
        deal_uuid = uuid.UUID(deal_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid deal_id format",
        )

    # 1. Получаем non-duplicate документы сделки
    runner_repo = RunnerRepository(db)
    docs = await runner_repo.get_non_duplicate_docs(deal_uuid)

    docs_total = len(docs)
    if docs_total == 0:
        logger.info(
            "Classifier API: no non-duplicate documents for deal",
            extra={"deal_id": deal_id},
        )
        return {
            "deal_id": deal_id,
            "docs_total": 0,
            "tasks_scheduled": 0,
        }

    logger.info(
        "Classifier API: scheduling classification tasks for deal",
        extra={"deal_id": deal_id, "docs_total": docs_total},
    )

    # 2. Ставим Celery-задачи workers.classify_document для каждого документа
    tasks_scheduled = 0
    for doc in docs:
        try:
            celery_app.send_task(
                "workers.classify_document",
                kwargs={
                    "document_id": str(doc.id),
                    # run_id / tenant_id можно добавить при необходимости:
                    # "run_id": ...,
                    # "deal_id": str(doc.deal_id),
                    # "tenant_id": ...
                },
            )
            tasks_scheduled += 1
        except Exception as e:
            logger.error(
                "Classifier API: failed to schedule classification task",
                extra={
                    "deal_id": deal_id,
                    "doc_id": str(getattr(doc, "id", None)),
                    "error": str(e),
                },
            )

    logger.info(
        "Classifier API: classification tasks scheduled",
        extra={
            "deal_id": deal_id,
            "docs_total": docs_total,
            "tasks_scheduled": tasks_scheduled,
        },
    )

    return {
        "deal_id": deal_id,
        "docs_total": docs_total,
        "tasks_scheduled": tasks_scheduled,
    }