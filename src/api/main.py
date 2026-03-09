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

from src.ops.instrument import setup_metrics

# Здесь собираем все группы эндпоинтов (роутеры) в одном месте.
# auth — это логин/авторизация (включая временный логин admin/admin).
from .endpoints import (
    auth,        # <--- добавили auth
    runner,
    documents,
    deal_review,
    runs,
    results,
    admin,
    deals,
    requests,
    user_projects,
    project_members,
)
from .middleware.audit import AuditMiddleware


# Создаём экземпляр приложения FastAPI.
app = FastAPI(
    title="LegalMAS API",
    version="0.1.0",
)

# Prometheus metrics (экспорт /metrics, http-метрики и build_info).
# Важно: вызываем один раз при старте приложения.
setup_metrics(app)

# Разрешённые origin для фронтенда (Vite dev‑сервер).
# Если фронтенд будет доступен с других доменов — дописываем их сюда.
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# CORS — до/вместе с остальными middleware.
# Это нужно, чтобы браузер разрешал фронтенду обращаться к API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,      # конкретные origin вместо "*"
    allow_credentials=True,
    allow_methods=["*"],        # разрешаем все методы (GET, POST, OPTIONS и т.д.)
    allow_headers=["*"],
)

# Middleware аудита (логирование действий).
app.add_middleware(AuditMiddleware)

# Роутеры (группы эндпоинтов).
# prefix="/api/v1" означает, что все маршруты внутри будут начинаться с /api/v1.

# Авторизация / логин (временно: admin/admin, см. src/api/endpoints/auth.py).
app.include_router(auth.router)

# Runner / запуск проверок.
app.include_router(runner.router, prefix="/api/v1")

# Документы (загрузка, статус и т.д.).
app.include_router(documents.router, prefix="/api/v1")

# Обзор сделки.
app.include_router(deal_review.router, prefix="/api/v1")

# Запуски (runs).
app.include_router(runs.router, prefix="/api/v1")

# Результаты проверок.
app.include_router(results.router, prefix="/api/v1")

# Админские эндпоинты.
app.include_router(admin.router, prefix="/api/v1")

# Сделки (deals).
app.include_router(deals.router, prefix="/api/v1")

# DD-запросы и связанные эндпоинты.
app.include_router(requests.router, prefix="/api/v1")
app.include_router(requests.requests_router, prefix="/api/v1")

# Сделки (deals) по конкретному пользователю.
app.include_router(user_projects.router)

# Пользователи
app.include_router(project_members.router, prefix="/api/v1")