# src/mas_queue/celery_app.py

"""
Конфигурация Celery-приложения.

Назначение:
  - создать единый экземпляр Celery (celery_app) для всего проекта;
  - настроить брокер, backend результатов, сериализацию, очереди и надёжность;
  - подключить регистрацию всех задач через модуль workers.tasks.

Все воркеры импортируют celery_app из этого файла и регистрируют задачи через
@celery_app.task(...), используя общий экземпляр приложения.

Конфигурация очередей:

  high_priority  — срочные задачи (импорт, конвертация). x-max-priority=10.
  default        — основной пайплайн (extract, pii, structure, classify).
                    x-max-priority=5.
  llm_checks     — LLM-тяжёлые задачи (run_deal_checks). Без приоритетов,
                    собственный time_limit/visibility_timeout.
  low_priority   — фоновые задачи (export, relations). x-max-priority=1.

Политика надёжности (ключевые настройки):

  task_acks_late=True              — ACK только после успешного выполнения.
  worker_prefetch_multiplier=1     — воркер берёт ровно одну задачу за раз.
  task_reject_on_worker_lost=True  — при падении воркера задача возвращается.
  task_soft_time_limit             — SIGTERM за 60 сек до hard limit.
  task_time_limit                  — SIGKILL через заданное время.
  visibility_timeout               — должен быть >= task_time_limit * 2,
                                     иначе Redis может переотправить задачу
                                     до завершения работы воркера.

Важно: SoftTimeLimitExceeded нужно перехватывать в MASBaseTask (base_task.py),
иначе задача может остаться в RUNNING без записи в DLQ.

Технический долг (актуальное):

  - Изолировать engine/session factory в тестах:
      * тесты должны использовать отдельный engine, а не тот же singleton,
        что и продакшн-код (см. async_helpers.py).
  - Покрыть run_async unit-тестами:
      * протестировать ветки: нормальный loop, закрытый loop,
        уже работающий loop.
"""

from urllib.parse import urlparse, urlunparse

from celery import Celery
from kombu import Exchange, Queue

from core.config import settings

# ---------------------------------------------------------------------------
# Экземпляр приложения
# ---------------------------------------------------------------------------

celery_app = Celery("mas_dd")

# ---------------------------------------------------------------------------
# Backend результатов
# ---------------------------------------------------------------------------


def _make_result_backend(broker_url: str, db: int = 1) -> str:
    """
    Строит URL для result backend, подставляя нужный номер Redis DB.

    Используем urlparse/urlunparse, корректно обрабатывает URL без
    trailing /{db} (например redis://localhost:6379 без номера базы).
    """
    parsed = urlparse(broker_url)
    return urlunparse(parsed._replace(path=f"/{db}"))


_result_backend = _make_result_backend(settings.REDIS_URL)

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

celery_app.conf.update(
    # --- Брокер и backend ---
    broker_url=settings.REDIS_URL,
    result_backend=_result_backend,

    # --- Сериализация: только JSON для безопасности и читаемости ---
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # --- Часовой пояс ---
    timezone="UTC",
    enable_utc=True,

    # --- Надёжность доставки ---
    task_acks_late=True,              # ACK после выполнения задачи, а не до
    worker_prefetch_multiplier=1,     # Воркер берёт ровно одну задачу за раз
    task_reject_on_worker_lost=True,  # При падении воркера задача переочерёдивается

    # --- Результаты ---
    result_expires=3600,              # Результаты живут 1 час
    task_track_started=True,          # Видно STARTED через AsyncResult

    # --- Переподключение к брокеру при старте ---
    broker_connection_retry_on_startup=True,

    # --- Лимиты выполнения задач ---
    #
    # Глобальные лимиты — для большинства задач пайплайна (import, extract, pii, etc.):
    #   - soft: 10 мин — SIGTERM, даёт время завершить текущую операцию.
    #   - hard: 11 мин — SIGKILL, если soft не помог.
    # Для llm_checks лимиты можно переопределить через task_annotations.
    task_soft_time_limit=600,  # SIGTERM через 10 мин
    task_time_limit=660,       # SIGKILL через 11 мин

    # --- Защита брокерного соединения ---
    broker_transport_options={
        # Для Redis: время, после которого невзятое сообщение считается
        # «пропавшим» и возвращается в очередь. Должно быть >= максимального
        # task_time_limit для всех очередей.
        # Здесь 7200 с = 2 ч, перекрывает и глобальный лимит (660 с),
        # и потенциальный LLM-лимит (до 3600 с) с запасом.
        "visibility_timeout": 7200,
        "socket_timeout": 30,
        "socket_connect_timeout": 10,
    },

    # --- Управление памятью воркеров ---
    # Перезапускать форк-процесс воркера после N задач.
    worker_max_tasks_per_child=200,

    # --- Определение очередей ---
    task_queues=(
        Queue(
            "high_priority",
            Exchange("high_priority"),
            routing_key="high_priority",
            queue_arguments={"x-max-priority": 10},
        ),
        Queue(
            "default",
            Exchange("default"),
            routing_key="default",
            queue_arguments={"x-max-priority": 5},
        ),
        Queue(
            "low_priority",
            Exchange("low_priority"),
            routing_key="low_priority",
            queue_arguments={"x-max-priority": 1},
        ),
        # LLM-очередь без приоритетов — задачи обрабатываются строго по FIFO.
        Queue(
            "llm_checks",
            Exchange("llm_checks"),
            routing_key="llm_checks",
        ),
    ),

    # --- Очередь по умолчанию ---
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",

    # --- Маршрутизация задач ---
    task_routes={
        "workers.run_deal_checks": {
            "queue": "llm_checks",
            "routing_key": "llm_checks",
        },
    },
)

# ---------------------------------------------------------------------------
# LLM-задачи: переопределение time limits (пример)
# ---------------------------------------------------------------------------
#
# Пример для run_deal_checks (включить, когда будут понятны реальные SLA):
#
# celery_app.conf.update({
#     "task_annotations": {
#         "workers.run_deal_checks": {
#             "soft_time_limit": 3540,  # SIGTERM за 60 сек до hard limit
#             "time_limit": 3600,       # SIGKILL через 1 час
#         }
#     }
# })

# ---------------------------------------------------------------------------
# Регистрация задач
# ---------------------------------------------------------------------------

try:
    import workers.tasks  # noqa: F401
except ImportError as e:
    from core.logging import get_logger

    logger = get_logger(__name__)
    logger.warning(
        "Failed to import workers.tasks during celery_app init",
        error=str(e),
    )

    