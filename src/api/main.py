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

Важно для OpenTelemetry:
- TracerProvider, SQLAlchemy и httpx instrumentation инициализируются
  на уровне модуля (до создания app) — через setup_tracing_provider().
- FastAPI instrumentation подключается ПОСЛЕ регистрации middleware и routers,
  но ДО старта приложения, через instrument_fastapi_app(app).
- Такой порядок нужен чтобы OpenTelemetry middleware оказался самым внешним.
  Тогда request-логи из AuditMiddleware будут выполняться уже внутри активного
  trace/span и автоматически получат trace_id / span_id.
- shutdown_tracing() вызывается в lifespan при завершении.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from classifiers.yaml_registry import YAMLRegistry
from core.config import settings
from core.logging import get_logger, setup_logging
from core.tracing import instrument_fastapi_app, setup_tracing_provider, shutdown_tracing
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
    instruction_overrides,
    instruction_preview,
    instruction_versions,
    instructions_global,
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
from .endpoints.provenance import router as provenance_router
from .endpoints.tenant_admin import router as tenant_admin_router
from .middleware.audit import AuditMiddleware
from api.endpoints.global_instruction_versions import router as global_instruction_router
from api.endpoints.instruction_sync import router as instruction_sync_router


setup_logging()

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Шаг 1: Инициализация TracerProvider на уровне модуля.
#
# Простым языком:
# Здесь мы "включаем" систему трейсинга — создаём TracerProvider,
# настраиваем exporter (отправку в Tempo), sampler (фильтр),
# и инструментируем SQLAlchemy и httpx.
#
# Это делается ДО создания FastAPI app, потому что:
# - SQLAlchemy engine уже существует на этот момент (создан в db/session.py)
# - httpx инструментируется глобально, не привязан к app
# - FastAPI instrumentation требует отдельного вызова после создания app
#
# Если OTEL_ENABLED=False — вызов мгновенно возвращается без эффекта.
# ---------------------------------------------------------------------------
setup_tracing_provider()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager для startup/shutdown process-level ресурсов.

    Startup:
    - валидирует YAML Registry fail-fast способом;
    - если конфиги типов документов некорректны, приложение не стартует.

    Shutdown:
    - сначала корректно завершает трейсинг (отправляет все pending spans);
    - потом закрывает SQLAlchemy AsyncEngine.
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
        # Сначала корректно завершаем трейсинг — отправляем все pending трейсы.
        # Важно делать это ДО закрытия engine, потому что последние трейсы
        # могут содержать SQL spans которые ещё не отправлены в Tempo.
        shutdown_tracing()

        logger.info("API shutdown — disposing database engine")
        try:
            await engine.dispose()
            logger.info("API shutdown — database engine disposed successfully")
        except Exception:
            logger.exception("API shutdown — failed to dispose database engine")
            raise


# ---------------------------------------------------------------------------
# Создание FastAPI app.
# ---------------------------------------------------------------------------
app = FastAPI(
    title="LegalMAS API",
    version="0.1.0",
    lifespan=lifespan,
    redirect_slashes=False,
)

setup_metrics(app)

# ---------------------------------------------------------------------------
# CORS — подготовка списка заголовков.
#
# Читаем конфиг из settings (который берёт значения из .env).
# Дополнительно гарантируем наличие заголовков, необходимых для корректной
# работы ETag concurrency (If-Match / If-None-Match) и базового API.
#
# Почему это нужно:
# - .env может содержать сокращённый список CORS_ALLOW_HEADERS;
# - без If-Match браузер блокирует PATCH-запросы с этим заголовком
#   на этапе preflight (400 "Disallowed CORS headers");
# - фикс в коде надёжнее чем полагаться на правильность .env в каждом окружении.
#
# Если в .env задан wildcard "*" — не трогаем, он покрывает всё.
# ---------------------------------------------------------------------------
_REQUIRED_CORS_HEADERS = [
    "If-Match",
    "If-None-Match",
    "X-Request-ID",
    "Authorization",
    "Content-Type",
    "Accept",
    "Content-Language",
    "Accept-Language",
]

cors_allow_origins = settings.cors_allow_origins_list
cors_allow_methods = settings.cors_allow_methods_list
cors_allow_headers = settings.cors_allow_headers_list

if cors_allow_headers != ["*"]:
    _existing_lower = {h.lower() for h in cors_allow_headers}
    cors_allow_headers = cors_allow_headers + [
        h for h in _REQUIRED_CORS_HEADERS
        if h.lower() not in _existing_lower
    ]

logger.info(
    "Configuring CORS middleware",
    allow_origins=cors_allow_origins,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=cors_allow_methods,
    allow_headers=cors_allow_headers,
)

# ---------------------------------------------------------------------------
# Регистрируем middleware приложения.
#
# Порядок важен — Starlette добавляет middleware в обратном порядке
# относительно вызовов add_middleware. Реальный стек выполнения:
#
#   [OTel — добавится позже] → CORSMiddleware → AuditMiddleware → endpoint
#
# CORSMiddleware должен стоять снаружи AuditMiddleware, чтобы:
# - preflight OPTIONS запросы обрабатывались до входа в AuditMiddleware;
# - CORS-заголовки проставлялись на все ответы включая ошибки.
#
# AuditMiddleware явно пропускает OPTIONS запросы (return await call_next)
# как дополнительная защита на случай если порядок middleware изменится.
#
# OpenTelemetry middleware будет добавлен ПОЗЖЕ через instrument_fastapi_app(app),
# уже после регистрации всех middleware и routers — чтобы оказаться самым внешним.
# Тогда request logs в AuditMiddleware будут выполняться внутри активного span.
# ---------------------------------------------------------------------------
app.add_middleware(AuditMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=cors_allow_methods,
    allow_headers=cors_allow_headers,
    expose_headers=["ETag"],
)

# ---------------------------------------------------------------------------
# Routers.
# ---------------------------------------------------------------------------

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

# Decision Provenance endpoints — Этап 4.
app.include_router(provenance_router, prefix="/api/v1")

# Админские эндпоинты.
app.include_router(tenant_admin_router, prefix="/api/v1")
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

# Global instruction facade over playbook domain.
app.include_router(instructions_global.router, prefix="/api/v1")

# Типы документов.
app.include_router(document_types.router, prefix="/api/v1")

# Lifecycle API для instruction versions.
app.include_router(instruction_versions.router, prefix="/api/v1")

# Lifecycle API для instruction overrides (tenant/deal level).
app.include_router(instruction_overrides.router, prefix="/api/v1")

# Unified instruction preview endpoint.
app.include_router(instruction_preview.router, prefix="/api/v1")

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

# Global instruction versions lifecycle API.
app.include_router(global_instruction_router, prefix="/api/v1")

# Sync API для платформенных инструкций (superadmin only).
app.include_router(instruction_sync_router, prefix="/api/v1")

# ---------------------------------------------------------------------------
# Шаг 2: FastAPI instrumentation подключаем ПОСЛЕ всех middleware и routers,
# но ДО старта приложения.
#
# Простым языком:
# FastAPIInstrumentor внутри себя добавляет middleware OpenTelemetry.
# Нам нужно чтобы этот middleware оказался самым внешним:
#
#   OpenTelemetryMiddleware -> CORSMiddleware -> AuditMiddleware -> endpoint
#
# Тогда:
# - span создаётся до входа в CORSMiddleware и AuditMiddleware
# - request-логи из AuditMiddleware выполняются уже внутри активного span
# - add_trace_context в logging.py автоматически добавляет
#   trace_id и span_id в structured logs
#
# Если вызвать instrument_fastapi_app(app) слишком рано,
# AuditMiddleware окажется снаружи span и trace_id в логах не появится.
#
# Если вызвать слишком поздно (после старта приложения),
# FastAPI выбросит RuntimeError: cannot add middleware after startup.
# ---------------------------------------------------------------------------
instrument_fastapi_app(app)


