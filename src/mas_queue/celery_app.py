# src/mas_queue/celery_app.py

"""
Конфигурация Celery-приложения.

Назначение:
- создать единый экземпляр Celery (celery_app) для всего проекта;
- настроить broker, backend результатов, сериализацию, очереди и надёжность;
- подключить регистрацию всех задач через явный список worker-модулей;
- настроить периодический запуск служебных задач через Celery Beat;
- централизованно закрывать process-level async ресурсы worker child process
  при его завершении.

Все воркеры импортируют celery_app из этого файла и регистрируют задачи через
@celery_app.task(...), используя общий экземпляр приложения.

Конфигурация очередей:

high_priority  — срочные задачи (импорт, конвертация). x-max-priority=10.
default        — основной пайплайн и лёгкая оркестрация
                 (extract, pii, structure, classify, scheduler/finalizer,
                 language discovery).
                 x-max-priority=5.
system         — инфраструктурные и служебные задачи
                 (outbox relay / maintenance / reconcile). x-max-priority=3.
heavy_llm_enrichment — LLM-тяжёлые задачи семантического обогащения.
heavy_llm_checks     — LLM-тяжёлые atomic check-задачи (run_single_check).
                 Без приоритетов, отдельные soft/hard time limits.
low_priority   — фоновые задачи (export, relations). x-max-priority=1.

Политика надёжности (ключевые настройки):

task_acks_late=True              — ACK только после успешного выполнения.
worker_prefetch_multiplier=1     — воркер берёт ровно одну задачу за раз.
task_reject_on_worker_lost=True  — при падении воркера задача возвращается.
task_soft_time_limit             — мягкий лимит времени, даёт шанс записать
                                   TIMEOUT / error_details до hard kill.
task_time_limit                  — жёсткий лимит времени.
visibility_timeout               — должен быть существенно больше максимального
                                   task_time_limit, иначе Redis может отдать
                                   задачу повторно до завершения воркера.

Важно:
- SoftTimeLimitExceeded должен перехватываться в задачах/базовом таске,
  иначе задача может остаться в RUNNING без корректного статуса в БД.
- Для heavy_llm_enrichment и heavy_llm_checks рекомендуются отдельные
  Celery worker-процессы.
- Для Redis visibility_timeout Celery рекомендует задавать это значение
  согласованно в broker_transport_options, result_backend_transport_options
  и visibility_timeout.
- Для outbox relay нужен отдельный worker, который слушает очередь `system`,
  и отдельный процесс `celery beat`, который будет регулярно ставить
  `workers.outbox_dispatcher` в эту очередь.

Важно для lifecycle ресурсов:
- В worker child process используется process-wide async SQLAlchemy engine
  и process-wide worker event loop.
- Эти ресурсы нельзя бросать "как есть" при завершении процесса.
- Поэтому при shutdown child process мы сначала закрываем engine,
  а затем закрываем worker event loop.

Технический долг (актуальное):
- Изолировать engine/session factory в тестах.
- Покрыть run_async unit-тестами.
- Покрыть worker shutdown cleanup интеграционными тестами.
"""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse
from typing import Any

from celery import Celery
from celery.signals import (
    task_postrun,
    task_prerun,
    worker_init,
    worker_process_init,
    worker_process_shutdown,
    worker_shutdown,
)
from kombu import Exchange, Queue

from core.config import settings
from core.logging import clear_log_context, get_logger, set_task_context, setup_logging
from db.session import engine
from mas_queue.async_helpers import close_worker_loop, has_worker_loop, run_async

setup_logging()

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_solo_worker(sender: Any | None) -> bool:
    """
    Определить, что Celery worker использует pool=solo.

    Почему это нужно:
    - для prefork tracing должен инициализироваться в child process
      через worker_process_init;
    - для solo нет child process, поэтому tracing нужно инициализировать
      в main process через worker_init.
    """
    if sender is None:
        return False

    pool_cls = getattr(sender, "pool_cls", None)
    if pool_cls is None:
        return False

    pool_name = (
        f"{getattr(pool_cls, '__module__', '')}."
        f"{getattr(pool_cls, '__name__', '')}"
    ).lower()

    return "solo" in pool_name

# ---------------------------------------------------------------------------
# Экземпляр приложения
# ---------------------------------------------------------------------------

celery_app = Celery("mas_dd")


# ---------------------------------------------------------------------------
# Backend результатов
# ---------------------------------------------------------------------------


def _make_result_backend(broker_url: str, db: int = 1) -> str:
    """
    Построить URL для Celery result backend, подставив отдельную Redis DB.

    Почему так:
    - broker и backend лучше держать в разных Redis DB;
    - urlparse/urlunparse корректно работает и с URL без /{db}.
    """
    parsed = urlparse(broker_url)
    return urlunparse(parsed._replace(path=f"/{db}"))


_result_backend = _make_result_backend(settings.REDIS_URL)


# ---------------------------------------------------------------------------
# Имена очередей
# ---------------------------------------------------------------------------

QUEUE_HIGH_PRIORITY = "high_priority"
QUEUE_DEFAULT = "default"
QUEUE_SYSTEM = "system"
QUEUE_HEAVY_LLM_ENRICHMENT = "heavy_llm_enrichment"
QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION = "heavy_llm_segment_classification"
QUEUE_HEAVY_LLM_CHECKS = "heavy_llm_checks"
QUEUE_LOW_PRIORITY = "low_priority"


# ---------------------------------------------------------------------------
# Лимиты задач
# ---------------------------------------------------------------------------

# Глобальные лимиты — для большинства задач пайплайна.
GLOBAL_TASK_SOFT_TIME_LIMIT_SEC = 1200
GLOBAL_TASK_TIME_LIMIT_SEC = 1260

# Heavy LLM — атомарная single-check задача.
RUN_SINGLE_CHECK_SOFT_TIME_LIMIT_SEC = 2700
RUN_SINGLE_CHECK_TIME_LIMIT_SEC = 3600
# Heavy LLM — segment-level classification (LLM на каждый сегмент документа).
# Задача долгая на CPU-only: один L4 LLM вызов ≈ несколько минут,
# документ может содержать много сегментов.
CLASSIFY_DOCUMENT_SEGMENTS_SOFT_TIME_LIMIT_SEC = 3600
CLASSIFY_DOCUMENT_SEGMENTS_TIME_LIMIT_SEC = 3900

# Orchestration pass — должен быть коротким.
# В норме это секунды, не минуты.
RUN_PIPELINE_ORCHESTRATOR_SOFT_TIME_LIMIT_SEC = 180
RUN_PIPELINE_ORCHESTRATOR_TIME_LIMIT_SEC = 240

# visibility_timeout должен быть больше максимального hard limit с запасом.
BROKER_VISIBILITY_TIMEOUT_SEC = 7200


# ---------------------------------------------------------------------------
# Периодические служебные задачи
# ---------------------------------------------------------------------------

# Как часто Celery Beat должен запускать outbox relay.
# 5 секунд — хороший старт для локальной разработки и dev-среды:
# события из outbox публикуются быстро, но без лишней нагрузки.
OUTBOX_DISPATCHER_INTERVAL_SEC = 5

# Сколько сообщений пытаться публиковать за один запуск dispatcher.
OUTBOX_DISPATCHER_BATCH_SIZE = 100

# Нужно ли перед publish сначала возвращать зависшие processing-сообщения
# обратно в pending.
OUTBOX_DISPATCHER_REQUEUE_STUCK = True


# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

celery_app.conf.update(
    # --- Broker / backend ---
    broker_url=settings.REDIS_URL,
    result_backend=_result_backend,
    # --- Явный список модулей с Celery tasks ---
    include=[
        "workers.build_primary_language_source",
        "workers.check_runner_worker",
        "workers.chunk_builder",
        "workers.classifier",
        "workers.convert_worker",
        "workers.detect_document_languages_native",
        "workers.detect_document_languages_ocr",
        "workers.export_pending",
        "workers.exporter",
        "workers.extract_worker",
        "workers.import_worker",
        "workers.language_discovery_orchestrator",
        "workers.prepare_document_for_language_discovery",
        "workers.convert_document_for_language_discovery",
        "workers.outbox_dispatcher",
        "workers.pii_sanitizer",
        "workers.relations_worker",
        "workers.run_orchestrator",
        "workers.segment_classifier",
        "workers.structure_builder",
        "workers.debug_dlq_task",
        "workers.build_legal_units_enrichment",
    ],
    # --- Сериализация ---
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # --- Timezone ---
    timezone="UTC",
    enable_utc=True,
    # --- Надёжность доставки ---
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    worker_hijack_root_logger=False,
    worker_redirect_stdouts=False,
    # --- Результаты ---
    result_expires=3600,
    task_track_started=True,
    # --- Подключение к брокеру ---
    broker_connection_retry_on_startup=True,
    # --- Глобальные лимиты выполнения ---
    task_soft_time_limit=GLOBAL_TASK_SOFT_TIME_LIMIT_SEC,
    task_time_limit=GLOBAL_TASK_TIME_LIMIT_SEC,
    # --- Параметры транспорта Redis ---
    broker_transport_options={
        "visibility_timeout": BROKER_VISIBILITY_TIMEOUT_SEC,
        "socket_timeout": 30,
        "socket_connect_timeout": 10,
    },
    result_backend_transport_options={
        "visibility_timeout": BROKER_VISIBILITY_TIMEOUT_SEC,
    },
    visibility_timeout=BROKER_VISIBILITY_TIMEOUT_SEC,
    # --- Управление жизненным циклом worker child process ---
    worker_max_tasks_per_child=200,
    # --- Описание очередей ---
    task_queues=(
        Queue(
            QUEUE_HIGH_PRIORITY,
            Exchange(QUEUE_HIGH_PRIORITY),
            routing_key=QUEUE_HIGH_PRIORITY,
            queue_arguments={"x-max-priority": 10},
        ),
        Queue(
            QUEUE_DEFAULT,
            Exchange(QUEUE_DEFAULT),
            routing_key=QUEUE_DEFAULT,
            queue_arguments={"x-max-priority": 5},
        ),
        Queue(
            QUEUE_SYSTEM,
            Exchange(QUEUE_SYSTEM),
            routing_key=QUEUE_SYSTEM,
            queue_arguments={"x-max-priority": 3},
        ),
        Queue(
            QUEUE_LOW_PRIORITY,
            Exchange(QUEUE_LOW_PRIORITY),
            routing_key=QUEUE_LOW_PRIORITY,
            queue_arguments={"x-max-priority": 1},
        ),
        Queue(
            QUEUE_HEAVY_LLM_ENRICHMENT,
            Exchange(QUEUE_HEAVY_LLM_ENRICHMENT),
            routing_key=QUEUE_HEAVY_LLM_ENRICHMENT,
        ),
        Queue(
            QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION,
            Exchange(QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION),
            routing_key=QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION,
        ),
        Queue(
            QUEUE_HEAVY_LLM_CHECKS,
            Exchange(QUEUE_HEAVY_LLM_CHECKS),
            routing_key=QUEUE_HEAVY_LLM_CHECKS,
        ),
    ),
    # --- Очередь по умолчанию ---
    task_default_queue=QUEUE_DEFAULT,
    task_default_exchange=QUEUE_DEFAULT,
    task_default_routing_key=QUEUE_DEFAULT,
    # --- Маршрутизация задач ---
    task_routes={
        "workers.start_language_discovery": {
            "queue": QUEUE_DEFAULT,
            "routing_key": QUEUE_DEFAULT,
        },
        "workers.prepare_document_for_language_discovery": {
            "queue": QUEUE_DEFAULT,
            "routing_key": QUEUE_DEFAULT,
        },
        "workers.convert_document_for_language_discovery": {
            "queue": QUEUE_DEFAULT,
            "routing_key": QUEUE_DEFAULT,
        },
        "workers.detect_document_languages_native": {
            "queue": QUEUE_DEFAULT,
            "routing_key": QUEUE_DEFAULT,
        },
        "workers.detect_document_languages_ocr": {
            "queue": QUEUE_DEFAULT,
            "routing_key": QUEUE_DEFAULT,
        },
        "workers.outbox_dispatcher": {
            "queue": QUEUE_SYSTEM,
            "routing_key": QUEUE_SYSTEM,
        },
        "workers.reap_stale_stage_executions": {
            "queue": QUEUE_SYSTEM,
            "routing_key": QUEUE_SYSTEM,
        },
        "workers.run_deal_checks": {
            "queue": QUEUE_DEFAULT,
            "routing_key": QUEUE_DEFAULT,
        },
        "workers.run_single_check": {
            "queue": QUEUE_HEAVY_LLM_CHECKS,
            "routing_key": QUEUE_HEAVY_LLM_CHECKS,
        },
        "workers.finalize_run_if_ready": {
            "queue": QUEUE_DEFAULT,
            "routing_key": QUEUE_DEFAULT,
        },
        "workers.build_legal_units_enrichment": {
            "queue": QUEUE_HEAVY_LLM_ENRICHMENT,
            "routing_key": QUEUE_HEAVY_LLM_ENRICHMENT,
        },
        "workers.classify_document_segments": {
            "queue": QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION,
            "routing_key": QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION,
        },
    },
    # --- Периодические задачи Celery Beat ---
    #
    # Celery Beat будет каждые 5 секунд ставить workers.outbox_dispatcher
    # в очередь system. Дальше system-worker заберёт эту задачу и:
    # 1) вернёт stuck processing messages обратно в pending;
    # 2) заберёт batch pending messages;
    # 3) опубликует их в Celery.
    beat_schedule={
        "outbox-dispatcher-every-5-seconds": {
            "task": "workers.outbox_dispatcher",
            "schedule": OUTBOX_DISPATCHER_INTERVAL_SEC,
            "kwargs": {
                "batch_size": OUTBOX_DISPATCHER_BATCH_SIZE,
                "requeue_stuck": OUTBOX_DISPATCHER_REQUEUE_STUCK,
            },
            "options": {
                "queue": QUEUE_SYSTEM,
                "routing_key": QUEUE_SYSTEM,
            },
        },
        "reap-stale-stage-executions-every-10-minutes": {
            "task": "workers.reap_stale_stage_executions",
            "schedule": 600.0,
            "options": {
                "queue": QUEUE_SYSTEM,
                "routing_key": QUEUE_SYSTEM,
            },
        },
    },
    # --- Task-level overrides ---
    task_annotations={
        "workers.start_run_pipeline": {
            "soft_time_limit": RUN_PIPELINE_ORCHESTRATOR_SOFT_TIME_LIMIT_SEC,
            "time_limit": RUN_PIPELINE_ORCHESTRATOR_TIME_LIMIT_SEC,
        },
        "workers.run_single_check": {
            "soft_time_limit": RUN_SINGLE_CHECK_SOFT_TIME_LIMIT_SEC,
            "time_limit": RUN_SINGLE_CHECK_TIME_LIMIT_SEC,
        },
        "workers.build_legal_units_enrichment": {
            "soft_time_limit": settings.SEMANTIC_ENRICHMENT_WORKER_SOFT_TIME_LIMIT_SECONDS,
            "time_limit": settings.SEMANTIC_ENRICHMENT_WORKER_TIME_LIMIT_SECONDS,
        },
        "workers.classify_document_segments": {
            "soft_time_limit": CLASSIFY_DOCUMENT_SEGMENTS_SOFT_TIME_LIMIT_SEC,
            "time_limit": CLASSIFY_DOCUMENT_SEGMENTS_TIME_LIMIT_SEC,
        },
    },
)

@worker_init.connect
def _configure_solo_worker_observability(sender: Any = None, **kwargs: Any) -> None:
    """
    Initialize logging + tracing for solo workers.

    Простым языком:
    В solo pool нет child process, значит worker_process_init не срабатывает
    так как в prefork. Поэтому для solo workers tracing надо поднимать
    в main process через worker_init.

    Для prefork workers здесь tracing НЕ инициализируем, иначе parent process
    инициализирует provider до fork, что плохо.
    """
    _ = kwargs

    if not _is_solo_worker(sender):
        return

    setup_logging()

    try:
        from core.tracing import setup_worker_tracing  # noqa: PLC0415
        setup_worker_tracing()
    except Exception:
        logger.exception(
            "Failed to initialize tracing in solo worker main process"
        )



@worker_process_init.connect
def _configure_worker_process_logging(**kwargs: Any) -> None:
    """
    Reconfigure logging and initialize tracing inside a prefork worker child process.

    Простым языком:
    Каждый prefork child process — это отдельный Python-процесс.
    Ему нужны:
    1) свой logging setup;
    2) свой TracerProvider + SQLAlchemy/httpx instrumentation.

    Это безопасно для prefork child processes.
    Для solo workers tracing поднимается в worker_init.
    """
    _ = kwargs
    setup_logging()

    try:
        from core.tracing import setup_worker_tracing  # noqa: PLC0415
        setup_worker_tracing()
    except Exception:
        logger.exception(
            "Failed to initialize tracing in worker child process"
        )


@task_prerun.connect
def _bind_task_logging_context(
    sender: Any = None,
    task_id: str | None = None,
    task: Any = None,
    args: tuple[Any, ...] | None = None,
    kwargs: dict[str, Any] | None = None,
    **signal_kwargs: Any,
) -> None:
    """
    Bind generic task logging context and restore trace context
    for every Celery task.

    Делаем две вещи:
    1) ставим logging context (request_id/run_id/deal_id/...)
    2) создаём worker-side consumer span, продолжая trace из Celery headers
    """
    _ = args, signal_kwargs

    task_obj = task or sender
    task_kwargs = kwargs if isinstance(kwargs, dict) else {}

    request = getattr(task_obj, "request", None)
    delivery_info = getattr(request, "delivery_info", None) or {}

    queue: str | None = None
    if isinstance(delivery_info, dict):
        queue = (
            delivery_info.get("routing_key")
            or delivery_info.get("queue")
            or delivery_info.get("exchange")
        )

    set_task_context(
        request_id=task_kwargs.get("request_id"),
        task_id=task_id or getattr(request, "id", None),
        tenant_id=task_kwargs.get("tenant_id"),
        deal_id=task_kwargs.get("deal_id"),
        run_id=task_kwargs.get("run_id"),
        document_id=task_kwargs.get("document_id") or task_kwargs.get("doc_id"),
        stage=getattr(task_obj, "name", None),
        actor_role=task_kwargs.get("actor_role"),
        worker_hostname=getattr(request, "hostname", None),
        queue=queue,
    )

    # ---------------------------------------------------------------------
    # Новое в B.1: создать worker-side execute span.
    #
    # Простым языком:
    # - publish side положил trace context в Celery headers
    # - worker извлекает его здесь
    # - создаёт child span: celery.execute/<task_name>
    # - все SQL/httpx/logs внутри задачи попадают в этот span
    # ---------------------------------------------------------------------
    try:
        raw_headers = getattr(request, "headers", None) or {}

        from core.tracing import start_celery_consumer_span  # noqa: PLC0415

        span, token = start_celery_consumer_span(
            task_name=getattr(task_obj, "name", "unknown"),
            task_id=task_id or getattr(request, "id", None),
            queue=queue,
            headers=raw_headers,
            request_id=task_kwargs.get("request_id"),
            tenant_id=task_kwargs.get("tenant_id"),
            deal_id=task_kwargs.get("deal_id"),
            run_id=task_kwargs.get("run_id"),
            document_id=task_kwargs.get("document_id") or task_kwargs.get("doc_id"),
        )

        if request is not None:
            setattr(request, "_otel_consumer_span", span)
            setattr(request, "_otel_consumer_token", token)

    except Exception:
        # Tracing никогда не должен ломать task execution.
        logger.exception(
            "Failed to restore tracing context for Celery task",
            task_name=getattr(task_obj, "name", None),
            task_id=task_id or getattr(request, "id", None),
        )


@task_postrun.connect
def _clear_task_logging_context(
    sender: Any = None,
    task_id: str | None = None,
    task: Any = None,
    retval: Any = None,
    state: str | None = None,
    **kwargs: Any,
) -> None:
    """
    Close worker-side tracing span and clear task logging context.

    Простым языком:
    После выполнения задачи нужно:
    1) закрыть Celery execute span;
    2) отвязать context token;
    3) очистить logging context.

    Без этого:
    - span не уйдёт в Tempo вовремя;
    - следующая задача может унаследовать чужой trace context/log context.
    """
    _ = task_id, retval, kwargs

    try:
        task_obj = task or sender
        request = getattr(task_obj, "request", None) if task_obj is not None else None

        if request is not None:
            span = getattr(request, "_otel_consumer_span", None)
            token = getattr(request, "_otel_consumer_token", None)

            from core.tracing import finish_celery_consumer_span  # noqa: PLC0415

            finish_celery_consumer_span(
                span,
                token,
                state=state,
                error_message="Celery task failed" if state == "FAILURE" else None,
            )

            if hasattr(request, "_otel_consumer_span"):
                delattr(request, "_otel_consumer_span")
            if hasattr(request, "_otel_consumer_token"):
                delattr(request, "_otel_consumer_token")

    except Exception:
        logger.exception("Failed to finalize tracing for Celery task")

    clear_log_context()

# ---------------------------------------------------------------------------
# Cleanup worker child process resources
# ---------------------------------------------------------------------------


@worker_process_shutdown.connect
@worker_shutdown.connect
def _cleanup_worker_process_async_resources(
    pid: int | None = None,
    exitcode: int | None = None,
    **kwargs,
) -> None:
    """
    Аккуратно закрыть process-level async ресурсы child process Celery.

    Порядок действий очень важен:
    1. Сначала закрываем SQLAlchemy AsyncEngine через run_async(...),
       пока worker event loop ещё жив.
    2. Потом закрываем сам worker event loop.

    Для непрофессионального программиста:
    - engine = это пул соединений к базе данных;
    - worker loop = это async-движок внутри процесса воркера;
    - если сначала "выключить loop", то engine уже может не успеть
      корректно закрыть свои async-соединения.
    """
    logger.info(
        "Celery worker process shutdown started",
        pid=pid,
        exitcode=exitcode,
    )

    # Новое в B.1: shutdown tracing provider перед закрытием engine и loop.
    # Важно делать это ПЕРВЫМ: pending spans могут содержать SQL traces,
    # которые ещё не отправлены. Если сначала закрыть engine, эти spans
    # не смогут быть корректно завершены.
    try:
        from core.tracing import shutdown_worker_tracing  # noqa: PLC0415
        shutdown_worker_tracing()
    except Exception:
        logger.exception(
            "Celery worker process shutdown: failed to shutdown tracing",
            pid=pid,
            exitcode=exitcode,
        )

    if not has_worker_loop():
        logger.info(
            "Celery worker process shutdown: worker loop was never initialized, nothing to clean",
            pid=pid,
            exitcode=exitcode,
        )
        return

    try:
        run_async(engine.dispose())
        logger.info(
            "Celery worker process shutdown: database engine disposed",
            pid=pid,
            exitcode=exitcode,
        )
    except Exception:
        logger.exception(
            "Celery worker process shutdown: failed to dispose database engine",
            pid=pid,
            exitcode=exitcode,
        )
    finally:
        try:
            close_worker_loop()
            logger.info(
                "Celery worker process shutdown: worker event loop closed",
                pid=pid,
                exitcode=exitcode,
            )
        except Exception:
            logger.exception(
                "Celery worker process shutdown: failed to close worker event loop",
                pid=pid,
                exitcode=exitcode,
            )

            
