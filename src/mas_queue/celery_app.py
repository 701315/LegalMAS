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

Конфигурация очередей:

high_priority  — срочные задачи (импорт, конвертация). x-max-priority=10.
default        — основной пайплайн и лёгкая оркестрация. x-max-priority=5.
system         — инфраструктурные и служебные задачи. x-max-priority=3.
heavy_llm_enrichment — LLM-тяжёлые задачи семантического обогащения.
heavy_llm_checks     — LLM-тяжёлые atomic check-задачи (run_single_check).
low_priority   — фоновые задачи (export, relations). x-max-priority=1.

Политика надёжности:

task_acks_late=True              — ACK только после успешного выполнения.
worker_prefetch_multiplier=1     — воркер берёт ровно одну задачу за раз.
task_reject_on_worker_lost=True  — при падении воркера задача возвращается.
task_soft_time_limit             — мягкий лимит, даёт шанс записать статус.
task_time_limit                  — жёсткий лимит времени.
visibility_timeout               — должен быть больше максимального task_time_limit.
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

    Для prefork tracing инициализируется в child process через worker_process_init.
    Для solo нет child process — tracing нужно поднимать в main process через worker_init.
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

GLOBAL_TASK_SOFT_TIME_LIMIT_SEC = 1200
GLOBAL_TASK_TIME_LIMIT_SEC = 1260

RUN_SINGLE_CHECK_SOFT_TIME_LIMIT_SEC = 2700
RUN_SINGLE_CHECK_TIME_LIMIT_SEC = 3600

CLASSIFY_DOCUMENT_SEGMENTS_SOFT_TIME_LIMIT_SEC = 3600
CLASSIFY_DOCUMENT_SEGMENTS_TIME_LIMIT_SEC = 3900

RUN_PIPELINE_ORCHESTRATOR_SOFT_TIME_LIMIT_SEC = 180
RUN_PIPELINE_ORCHESTRATOR_TIME_LIMIT_SEC = 240

# build_structure использует LLM (ClauseDetector, HeadingRefiner).
# Глобального лимита (1260с) недостаточно: при недоступной Ollama задача
# висит до hard kill, не успев записать FAILED в document_stage_executions.
# Soft (45 мин) даёт Celery шанс выбросить SoftTimeLimitExceeded внутри
# задачи → base_task.py → PermanentError → on_failure → mark_failed.
# Hard (50 мин) — жёсткий потолок; остаётся << visibility_timeout (16800с).
BUILD_STRUCTURE_SOFT_TIME_LIMIT_SEC = 2700
BUILD_STRUCTURE_TIME_LIMIT_SEC = 3000

# Visibility timeout ОБЯЗАН быть больше самой долгой задачи.
# Используем settings.CELERY_BROKER_VISIBILITY_TIMEOUT — property,
# которая берёт SEMANTIC_ENRICHMENT_WORKER_TIME_LIMIT_SECONDS + 300.
#
# Если значение меньше task_time_limit — Redis считает воркер мёртвым
# и публикует задачу повторно, пока первый экземпляр ещё работает.
BROKER_VISIBILITY_TIMEOUT_SEC = settings.CELERY_BROKER_VISIBILITY_TIMEOUT


# ---------------------------------------------------------------------------
# Периодические служебные задачи
# ---------------------------------------------------------------------------

OUTBOX_DISPATCHER_INTERVAL_SEC = 5
OUTBOX_DISPATCHER_BATCH_SIZE = 100
OUTBOX_DISPATCHER_REQUEUE_STUCK = True


# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

celery_app.conf.update(
    broker_url=settings.REDIS_URL,
    result_backend=_result_backend,
    include=[
        "workers.build_primary_language_source",
        "workers.check_runner_worker",
        "workers.result_presentation_worker",
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
        "workers.stale_execution_reaper",
        "workers.stale_run_reaper",
        "workers.pii_sanitizer",
        "workers.relations_worker",
        "workers.run_orchestrator",
        "workers.segment_classifier",
        "workers.structure_builder",
        "workers.debug_dlq_task",
        "workers.build_legal_units_enrichment",
        "workers.summary_worker",
    ],
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    worker_hijack_root_logger=False,
    worker_redirect_stdouts=False,
    result_expires=3600,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_soft_time_limit=GLOBAL_TASK_SOFT_TIME_LIMIT_SEC,
    task_time_limit=GLOBAL_TASK_TIME_LIMIT_SEC,
    broker_transport_options={
        "visibility_timeout": BROKER_VISIBILITY_TIMEOUT_SEC,
        "socket_timeout": 30,
        "socket_connect_timeout": 10,
    },
    result_backend_transport_options={
        "visibility_timeout": BROKER_VISIBILITY_TIMEOUT_SEC,
    },
    visibility_timeout=BROKER_VISIBILITY_TIMEOUT_SEC,
    worker_max_tasks_per_child=200,
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
    task_default_queue=QUEUE_DEFAULT,
    task_default_exchange=QUEUE_DEFAULT,
    task_default_routing_key=QUEUE_DEFAULT,
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
        "workers.reap_stale_runs": {
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
        "workers.process_pending_result_presentations": {
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
        "workers.generate_run_summary": {
            "queue": QUEUE_HEAVY_LLM_CHECKS,
            "routing_key": QUEUE_HEAVY_LLM_CHECKS,
        },
        "workers.classify_document_segments": {
            "queue": QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION,
            "routing_key": QUEUE_HEAVY_LLM_SEGMENT_CLASSIFICATION,
        },
    },
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
        "reap-stale-runs-every-30-minutes": {
            "task": "workers.reap_stale_runs",
            "schedule": 1800.0,
            "options": {
                "queue": QUEUE_SYSTEM,
                "routing_key": QUEUE_SYSTEM,
            },
        },
    },
    task_annotations={
        "workers.start_run_pipeline": {
            "soft_time_limit": RUN_PIPELINE_ORCHESTRATOR_SOFT_TIME_LIMIT_SEC,
            "time_limit": RUN_PIPELINE_ORCHESTRATOR_TIME_LIMIT_SEC,
        },
        "workers.run_single_check": {
            "soft_time_limit": RUN_SINGLE_CHECK_SOFT_TIME_LIMIT_SEC,
            "time_limit": RUN_SINGLE_CHECK_TIME_LIMIT_SEC,
        },
        "workers.process_pending_result_presentations": {
            "soft_time_limit": 3300,
            "time_limit": 3600,
        },
        "workers.build_legal_units_enrichment": {
            "soft_time_limit": settings.SEMANTIC_ENRICHMENT_WORKER_SOFT_TIME_LIMIT_SECONDS,
            "time_limit": settings.SEMANTIC_ENRICHMENT_WORKER_TIME_LIMIT_SECONDS,
        },
        "workers.classify_document_segments": {
            "soft_time_limit": CLASSIFY_DOCUMENT_SEGMENTS_SOFT_TIME_LIMIT_SEC,
            "time_limit": CLASSIFY_DOCUMENT_SEGMENTS_TIME_LIMIT_SEC,
        },
        "workers.generate_run_summary": {
            "soft_time_limit": 600,
            "time_limit": 660,
        },
        "workers.build_structure": {
            "soft_time_limit": BUILD_STRUCTURE_SOFT_TIME_LIMIT_SEC,
            "time_limit": BUILD_STRUCTURE_TIME_LIMIT_SEC,
        },
    },
)

logger.info(
    "Celery configured",
    broker_visibility_timeout_sec=BROKER_VISIBILITY_TIMEOUT_SEC,
    semantic_enrichment_time_limit_sec=settings.SEMANTIC_ENRICHMENT_WORKER_TIME_LIMIT_SECONDS,
    run_single_check_time_limit_sec=RUN_SINGLE_CHECK_TIME_LIMIT_SEC,
    build_structure_time_limit_sec=BUILD_STRUCTURE_TIME_LIMIT_SEC,
    global_task_time_limit_sec=GLOBAL_TASK_TIME_LIMIT_SEC,
)

@worker_init.connect
def _configure_solo_worker_observability(sender: Any = None, **kwargs: Any) -> None:
    """
    Инициализировать logging + tracing для solo workers.

    В solo pool нет child process — worker_process_init не срабатывает.
    Поэтому tracing поднимаем в main process через worker_init.
    Для prefork workers здесь НЕ инициализируем — parent process до fork.
    """
    _ = kwargs

    if not _is_solo_worker(sender):
        return

    setup_logging()

    try:
        from core.tracing import setup_worker_tracing  # noqa: PLC0415
        setup_worker_tracing()
    except Exception:
        logger.exception("Failed to initialize tracing in solo worker main process")


@worker_process_init.connect
def _configure_worker_process_logging(**kwargs: Any) -> None:
    """
    Инициализировать logging + tracing в prefork worker child process.

    Каждый prefork child process — отдельный Python-процесс.
    Нужны свой logging setup и свой TracerProvider.
    """
    _ = kwargs
    setup_logging()

    try:
        from core.tracing import setup_worker_tracing  # noqa: PLC0415
        setup_worker_tracing()
    except Exception:
        logger.exception("Failed to initialize tracing in worker child process")


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
    Bind logging context и создать tracing span для каждой Celery task.

    Для noisy tasks (outbox_dispatcher, reap_stale_stage_executions):
    - execution context помечается как noisy через contextvars
    - _NoisyTaskTaggingSpanProcessor автоматически добавляет атрибут
      app.noisy_task_name ко всем spans внутри этой задачи
    - _FilteringSpanExporter выбрасывает все spans с этим атрибутом
    - logging context работает нормально

    Для бизнес tasks:
    - создаётся полноценный consumer span celery.execute/<task_name>
    - все SQL/httpx spans становятся его дочерними
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

    # ------------------------------------------------------------------
    # Пометить execution context как noisy task (если задача в списке).
    #
    # Простым языком:
    # Мы записываем в contextvars: "сейчас выполняется noisy task X".
    # _NoisyTaskTaggingSpanProcessor читает это при каждом on_start()
    # и добавляет атрибут app.noisy_task_name ко всем spans:
    # - consumer span самой задачи
    # - SQLAlchemy spans
    # - httpx spans
    # Потом _FilteringSpanExporter их все выбрасывает.
    # ------------------------------------------------------------------
    try:
        from core.tracing import bind_noisy_task_context  # noqa: PLC0415

        noisy_token = bind_noisy_task_context(getattr(task_obj, "name", None))

        if request is not None:
            setattr(request, "_otel_noisy_task_token", noisy_token)

    except Exception:
        logger.exception(
            "Failed to bind noisy task tracing context",
            task_name=getattr(task_obj, "name", None),
            task_id=task_id or getattr(request, "id", None),
        )

    # ------------------------------------------------------------------
    # Создать worker-side consumer span.
    # ------------------------------------------------------------------
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
        logger.exception(
            "Failed to create tracing span for Celery task",
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
    Завершить tracing span и очистить logging context после выполнения task.

    Без этого:
    - span не уйдёт в Tempo вовремя
    - следующая задача унаследует чужой trace/log context
    """
    _ = task_id, retval, kwargs

    try:
        task_obj = task or sender
        request = getattr(task_obj, "request", None) if task_obj is not None else None

        if request is not None:
            span = getattr(request, "_otel_consumer_span", None)
            token = getattr(request, "_otel_consumer_token", None)
            noisy_token = getattr(request, "_otel_noisy_task_token", None)

            from core.tracing import (  # noqa: PLC0415
                finish_celery_consumer_span,
                reset_noisy_task_context,
            )

            finish_celery_consumer_span(
                span,
                token,
                state=state,
                error_message="Celery task failed" if state == "FAILURE" else None,
            )

            # Сбросить noisy task marker из contextvars.
            reset_noisy_task_context(noisy_token)

            if hasattr(request, "_otel_consumer_span"):
                delattr(request, "_otel_consumer_span")
            if hasattr(request, "_otel_consumer_token"):
                delattr(request, "_otel_consumer_token")
            if hasattr(request, "_otel_noisy_task_token"):
                delattr(request, "_otel_noisy_task_token")

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
    **kwargs: Any,
) -> None:
    """
    Аккуратно закрыть process-level async ресурсы при завершении worker.

    Порядок важен:
    1. Shutdown tracing (flush pending spans)
    2. Dispose SQLAlchemy engine (через event loop пока он жив)
    3. Close worker event loop
    """
    logger.info(
        "Celery worker process shutdown started",
        pid=pid,
        exitcode=exitcode,
    )

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


