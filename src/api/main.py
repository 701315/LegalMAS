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
from fastapi.middleware.cors import CORSMiddleware

from api.endpoints import (
    runner,
    documents,
    deal_review,
    runs,
    results,
    admin,
    deals,
)
from api.middleware.audit import AuditMiddleware


app = FastAPI(
    title="LegalMAS API",
    version="0.1.0",
)

# Разрешённые origin для фронтенда (Vite dev‑сервер)
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# CORS — до/вместе с остальными middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,      # конкретные origin вместо "*"
    allow_credentials=True,
    allow_methods=["*"],        # разрешаем все методы (GET, POST, OPTIONS и т.д.)
    allow_headers=["*"],
)

# Middleware аудита
app.add_middleware(AuditMiddleware)

# Роутеры
app.include_router(runner.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(deal_review.router, prefix="/api/v1")
app.include_router(runs.router, prefix="/api/v1")
app.include_router(results.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(deals.router, prefix="/api/v1")

