# src/api/main.py

"""
Точка входа API (FastAPI приложение).

Архитектурные договорённости по работе с БД:

- HTTP-эндпоинты используют db: AsyncSession = Depends(get_db);
  в них создаются репозитории и сервисы поверх одной request-scoped session.

- Middleware и фоновые задачи не используют get_db и DI FastAPI.
  Им нужна своя AsyncSession через get_session или db_uow.

- Unit of Work для worker'ов и фоновых write-операций реализован через db_uow
  из src/db/session.py: одна операция = один явный transactional context.

Важно для lifecycle ресурсов:
- get_session() / get_db() / db_uow() закрывают отдельные AsyncSession;
- но общий SQLAlchemy AsyncEngine живёт на уровне всего процесса API;
- поэтому его shutdown должен происходить в lifespan FastAPI.

Важно для streaming:
- long-lived response (например SSE) не должен удерживать request-scoped session
  на весь срок жизни ответа;
- такие сценарии должны открывать короткоживущие session внутри сервиса.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from classifiers.yaml_registry import YAMLRegistry
from core.logging import get_logger, setup_logging
from db.session import engine
from ops.instrument import setup_metrics

from .endpoints import (
    admin,
    audit,
    auth,
    classifier,
    deal_review,
    document_chunk_exports,
    document_pipeline_view,
    document_types,
    exports,
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
)
from .endpoints.deals.router import router as deals_router
from .endpoints.documents.router import router as documents_router
from .middleware.audit import AuditMiddleware

setup_logging()

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager для startup/shutdown process-level ресурсов.

    Startup:
    - валидирует YAML Registry fail-fast способом;
    - если конфиги типов документов некорректны, приложение не стартует.

    Shutdown:
    - корректно закрывает SQLAlchemy AsyncEngine;
    - освобождает соединения из пула PostgreSQL перед завершением процесса.
    """
    _ = app

    logger.info("Validating YAML registry on API startup...")
    registry = YAMLRegistry.get_instance(validate=True)
    logger.info(
        "YAML registry validation passed",
        types_loaded=len(registry.list_types()),
    )

    try:
        yield
    finally:
        logger.info("API shutdown — disposing database engine")
        try:
            await engine.dispose()
            logger.info("API shutdown — database engine disposed successfully")
        except Exception:
            logger.exception("API shutdown — failed to dispose database engine")
            raise


app = FastAPI(
    title="LegalMAS API",
    version="0.1.0",
    lifespan=lifespan,
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

# Документы.
app.include_router(documents_router, prefix="/api/v1")

# Pipeline view документов — отдельный router.
app.include_router(document_pipeline_view.router, prefix="/api/v1")

# Обзор сделки.
app.include_router(deal_review.router, prefix="/api/v1")

# Runs.
app.include_router(runs.router, prefix="/api/v1")

# QC actions for review mode.
app.include_router(qc.router, prefix="/api/v1")

# Результаты проверок.
app.include_router(results.router, prefix="/api/v1")

# Админские эндпоинты.
app.include_router(admin.router, prefix="/api/v1")

# Сделки и вложенные deal-specific endpoints.
app.include_router(deals_router, prefix="/api/v1")

# DD-запросы и связанные эндпоинты.
app.include_router(requests.router, prefix="/api/v1")
app.include_router(requests.requests_router, prefix="/api/v1")

# Сделки по конкретному пользователю.
app.include_router(user_projects.router)

# Пользователи / участники проектов.
app.include_router(project_members.router, prefix="/api/v1")

# Плейбуки.
app.include_router(playbooks.router, prefix="/api/v1")

# Типы документов.
app.include_router(document_types.router, prefix="/api/v1")

# История и пересборка плейбука по сделке.
app.include_router(playbook_runs.router, prefix="/api/v1")

# Конфигурации моделей.
app.include_router(model_configs.router, prefix="/api/v1")

# Debug-экспорт чанков.
app.include_router(document_chunk_exports.router, prefix="/api/v1")

# Exports.
app.include_router(exports.router, prefix="/api/v1")

# Журнал аудита.
app.include_router(audit.router, prefix="/api/v1")
