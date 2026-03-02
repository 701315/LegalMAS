"""
Точка входа API (FastAPI приложение).

Архитектурные договорённости по работе с БД:

- HTTP-эндпоинты используют db: AsyncSession = Depends(get_db);
  в них создаются репозитории и сервисы поверх одной сессии.

- Middleware и фоновые задачи НЕ используют get_db и DI FastAPI.
  Им нужна своя AsyncSession через get_session или db_uow (для worker'ов).

- Unit of Work для worker'ов реализован через db_uow (src/db/uow.py):
  одна Celery-таска = один UnitOfWork/AsyncSession.
"""


from fastapi import FastAPI

from src.api.endpoints import (
    runner, 
    documents, 
    deal_review, 
    runs, 
    results, 
    admin,
    # requests  # подключишь, когда появится src/api/endpoints/requests.py
)
from src.api.middleware.audit import AuditMiddleware


app = FastAPI(
    title="LegalMAS API",
    version="0.1.0",
)

# Подключаем middleware аудита ДО роутеров
app.add_middleware(AuditMiddleware)

# Подключаем роутеры
app.include_router(runner.router)
app.include_router(documents.router)
app.include_router(deal_review.router)
app.include_router(runs.router)
app.include_router(results.router)
app.include_router(admin.router)
# app.include_router(requests.router)
