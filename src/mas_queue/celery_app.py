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

from celery import Celery
from celery.signals import worker_process_shutdown
from kombu import Exchange, Queue

from core.config import settings
from core.logging import get_logger
from db.session import engine
from mas_queue.async_helpers import close_worker_loop, has_worker_loop, run_async

logger = get_logger(__name__)


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
    },
    # --- Task-level overrides ---
    task_annotations={
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


# ---------------------------------------------------------------------------
# Cleanup worker child process resources
# ---------------------------------------------------------------------------


@worker_process_shutdown.connect
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
        extra={"pid": pid, "exitcode": exitcode},
    )

    if not has_worker_loop():
        logger.info(
            "Celery worker process shutdown: worker loop was never initialized, nothing to clean",
            extra={"pid": pid, "exitcode": exitcode},
        )
        return

    try:
        run_async(engine.dispose())
        logger.info(
            "Celery worker process shutdown: database engine disposed",
            extra={"pid": pid, "exitcode": exitcode},
        )
    except Exception:
        logger.exception(
            "Celery worker process shutdown: failed to dispose database engine",
            extra={"pid": pid, "exitcode": exitcode},
        )
    finally:
        try:
            close_worker_loop()
            logger.info(
                "Celery worker process shutdown: worker event loop closed",
                extra={"pid": pid, "exitcode": exitcode},
            )
        except Exception:
            logger.exception(
                "Celery worker process shutdown: failed to close worker event loop",
                extra={"pid": pid, "exitcode": exitcode},
            )
