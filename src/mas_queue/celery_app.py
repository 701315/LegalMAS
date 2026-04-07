# src/mas_queue/celery_app.py

"""
Конфигурация Celery-приложения.

Назначение:
  - создать единый экземпляр Celery (celery_app) для всего проекта;
  - настроить broker, backend результатов, сериализацию, очереди и надёжность;
  - подключить регистрацию всех задач через модуль workers.tasks.

Все воркеры импортируют celery_app из этого файла и регистрируют задачи через
@celery_app.task(...), используя общий экземпляр приложения.

Конфигурация очередей:

  high_priority  — срочные задачи (импорт, конвертация). x-max-priority=10.
  default        — основной пайплайн и лёгкая оркестрация
                   (extract, pii, structure, classify, scheduler/finalizer).
                   x-max-priority=5.
  heavy_llm      — LLM-тяжёлые атомарные задачи (run_single_check).
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
  - Для heavy_llm рекомендуется отдельный Celery worker-процесс.

Технический долг (актуальное):
  - Изолировать engine/session factory в тестах.
  - Покрыть run_async unit-тестами.
"""

from urllib.parse import urlparse, urlunparse

from celery import Celery
from kombu import Exchange, Queue

from core.config import settings
from core.logging import get_logger


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
QUEUE_HEAVY_LLM = "heavy_llm"
QUEUE_LOW_PRIORITY = "low_priority"

# ---------------------------------------------------------------------------
# Лимиты задач
# ---------------------------------------------------------------------------

# Глобальные лимиты — для большинства задач пайплайна.
GLOBAL_TASK_SOFT_TIME_LIMIT_SEC = 1200
GLOBAL_TASK_TIME_LIMIT_SEC = 1200

# Heavy LLM — атомарная single-check задача.
RUN_SINGLE_CHECK_SOFT_TIME_LIMIT_SEC = 2700
RUN_SINGLE_CHECK_TIME_LIMIT_SEC = 3600

# visibility_timeout должен быть больше максимального hard limit с запасом.
BROKER_VISIBILITY_TIMEOUT_SEC = 7200

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
        "workers.export_pending",
        "workers.exporter",
        "workers.extract_worker",
        "workers.import_worker",
        "workers.pii_sanitizer",
        "workers.relations_worker",
        "workers.run_orchestrator",
        "workers.structure_builder",
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
            QUEUE_LOW_PRIORITY,
            Exchange(QUEUE_LOW_PRIORITY),
            routing_key=QUEUE_LOW_PRIORITY,
            queue_arguments={"x-max-priority": 1},
        ),
        Queue(
            QUEUE_HEAVY_LLM,
            Exchange(QUEUE_HEAVY_LLM),
            routing_key=QUEUE_HEAVY_LLM,
        ),
    ),

    # --- Очередь по умолчанию ---
    task_default_queue=QUEUE_DEFAULT,
    task_default_exchange=QUEUE_DEFAULT,
    task_default_routing_key=QUEUE_DEFAULT,

    # --- Маршрутизация задач ---
    task_routes={
        "workers.run_deal_checks": {
            "queue": QUEUE_DEFAULT,
            "routing_key": QUEUE_DEFAULT,
        },
        "workers.run_single_check": {
            "queue": QUEUE_HEAVY_LLM,
            "routing_key": QUEUE_HEAVY_LLM,
        },
        "workers.finalize_run_if_ready": {
            "queue": QUEUE_DEFAULT,
            "routing_key": QUEUE_DEFAULT,
        },
    },

    # --- Task-level overrides ---
    task_annotations={
        "workers.run_single_check": {
            "soft_time_limit": RUN_SINGLE_CHECK_SOFT_TIME_LIMIT_SEC,
            "time_limit": RUN_SINGLE_CHECK_TIME_LIMIT_SEC,
        },
    },
)

