# src/api/main.py

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

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ops.instrument import setup_metrics
from core.logging import get_logger
from classifiers.yaml_registry import YAMLRegistry

from .endpoints import (
    admin,
    auth,
    audit,
    classifier,
    deal_review,
    document_chunk_exports,
    document_pipeline_view,
    document_types,
    model_configs,
    playbook_runs,
    playbooks,
    project_members,
    qc,
    requests,
    results,
    runner,
    runs,
    user_projects,
    exports,
)
from .endpoints.documents.router import router as documents_router
from .middleware.audit import AuditMiddleware
from .endpoints.deals.router import router as deals_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager для FastAPI — управляет startup и shutdown событиями.

    Для непрофессионального программиста:
    - Этот код запускается один раз при старте приложения (до yield).
    - После yield — код выполняется при завершении приложения (shutdown).
    - Используем современный подход через context manager вместо deprecated @app.on_event().
    
    Что происходит при startup:
    - Валидируем YAML Registry (все regex-паттерны в конфигах типов документов).
    - Если есть кривой паттерн — приложение не стартует (fail-fast).
    - Это критично для production: лучше упасть сразу, чем работать с неполными правилами.
    """
    # === STARTUP: валидация YAML Registry ===
    logger.info("Validating YAML registry on API startup...")
    registry = YAMLRegistry.get_instance(validate=True)
    logger.info(
        "YAML registry validation passed",
        types_loaded=len(registry.list_types()),
    )
    
    yield  # Здесь FastAPI запускается и обрабатывает запросы
    
    # === SHUTDOWN: cleanup (если потребуется в будущем) ===
    logger.info("API shutdown — cleanup complete")


app = FastAPI(
    title="LegalMAS API",
    version="0.1.0",
    lifespan=lifespan,  # Подключаем lifespan context manager
)

setup_metrics(app)

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(AuditMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Авторизация / логин.
app.include_router(auth.router)

# Runner / запуск проверок.
app.include_router(runner.router, prefix="/api/v1")

# Классификация документов.
app.include_router(classifier.router, prefix="/api/v1")

# Документы (новый агрегирующий router из src/api/endpoints/documents/router.py).
app.include_router(documents_router, prefix="/api/v1")

# Документы (pipeline view по стадиям обработки) — пока остаётся отдельным,
# так как модуль находится вне пакета src/api/endpoints/documents/.
app.include_router(document_pipeline_view.router, prefix="/api/v1")

# Обзор сделки.
app.include_router(deal_review.router, prefix="/api/v1")

# Запуски (runs).
app.include_router(runs.router, prefix="/api/v1")

# QC actions for review mode.
app.include_router(qc.router, prefix="/api/v1")

# Результаты проверок.
app.include_router(results.router, prefix="/api/v1")

# Админские эндпоинты.
app.include_router(admin.router, prefix="/api/v1")

# Сделки (deals).
app.include_router(deals_router, prefix="/api/v1")

# DD-запросы и связанные эндпоинты.
app.include_router(requests.router, prefix="/api/v1")
app.include_router(requests.requests_router, prefix="/api/v1")

# Сделки (deals) по конкретному пользователю.
app.include_router(user_projects.router)

# Пользователи / участники проектов.
app.include_router(project_members.router, prefix="/api/v1")

# Плейбуки (playbooks / global_checks / bundles).
app.include_router(playbooks.router, prefix="/api/v1")

# Типы документов (document types) из YAMLRegistry.
app.include_router(document_types.router, prefix="/api/v1")

# История и пересборка плейбука по сделке.
app.include_router(playbook_runs.router, prefix="/api/v1")

# Конфигурации моделей (ModelConfig) для выбора модели на UI.
app.include_router(model_configs.router, prefix="/api/v1")

# Документы (debug-экспорт чанков).
app.include_router(document_chunk_exports.router, prefix="/api/v1")

app.include_router(exports.router, prefix="/api/v1")

# Журнал аудита (GET /deals/{deal_id}/audit, POST /audit-log)
app.include_router(audit.router, prefix="/api/v1")




