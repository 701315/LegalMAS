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
from api.deps.security import require_project_role, get_scoped_deal # Наш Hardening
from core.config import settings
from core.logging import get_logger
from db.repositories.runner_repo import RunnerRepository
from db.session import get_db
from mas_queue.task_dispatcher import send_task_with_context

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
    Запустить классификацию всех документов сделки через Celery.
    Доступ: только admin/editor текущего тенанта.
    """
    # Валидация UUID
    try:
        deal_uuid = uuid.UUID(deal_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid deal_id format")

    # 1. ПРОВЕРКА ТЕНАНТА: get_scoped_deal выбросит 404, если сделка чужая
    await get_scoped_deal(deal_id=deal_uuid, user=user, db=db)

    # 2. RBAC: Проверка ролей внутри проекта
    await require_project_role(
        db=db,
        user=user,
        deal_id=deal_uuid,
        allowed_roles=("admin", "editor"), # Исправлено: allowed_roles вместо required_roles
    )

    # 3. Логика запуска (без изменений)
    runner_repo = RunnerRepository(db)
    docs = await runner_repo.get_non_duplicate_docs(deal_uuid)

    if not docs:
        return {"deal_id": deal_id, "docs_total": 0, "tasks_scheduled": 0}

    tasks_scheduled = 0
    for doc in docs:
        try:
            send_task_with_context(
                "workers.classify_document",
                kwargs={"document_id": str(doc.id), "deal_id": str(deal_id)},
            )
            tasks_scheduled += 1
        except Exception as e:
            logger.error("Classifier API task failed", extra={"doc_id": str(doc.id), "error": str(e)})

    return {"deal_id": deal_id, "docs_total": len(docs), "tasks_scheduled": tasks_scheduled}



