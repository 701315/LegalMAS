# src/mas_queue/celery_app.py


"""
Конфигурация Celery-приложения.

Назначение:
  - создать единый экземпляр Celery (celery_app) для всего проекта;
  - настроить брокер, backend результатов, сериализацию, очереди и надёжность;
  - подключить регистрацию всех задач через модуль workers.tasks.

Все воркеры импортируют celery_app из этого файла и регистрируют задачи через
@celery_app.task(...), используя общий экземпляр приложения.

Backlog (технический долг, связанный с очередями и асинхронностью):

  Задача 1 — Рефакторинг Celery-задач (высокий приоритет)
    Цель: убрать кастомный run_async из тела Celery-задач и перейти
          на простой паттерн asyncio.run(_async_fn()) в синхронной оболочке.
    Почему:
      - текущий паттерн хрупок при разных Celery pool (gevent, eventlet, solo);
      - создаёт неявные зависимости от состояния event loop.
    Целевой шаблон:
        @celery_app.task
        def import_bundle(deal_id, tenant_id, source_path, run_id):
            asyncio.run(_import_bundle_async(deal_id, tenant_id, source_path, run_id))

        async def _import_bundle_async(deal_id, tenant_id, source_path, run_id):
            # вся логика здесь, чисто async
            ...
    Затронутые файлы:
      - все воркеры в src/workers/;
      - src/workers/orchestrator.py;
      - src/queue/async_helpers.py.

  Задача 2 — Изолировать engine/session factory в тестах (средний приоритет)
    Цель: тесты должны использовать отдельный engine, а не тот же singleton,
          что и продакшн-код.
    Сейчас:
      - _engine и _session_factory в async_helpers.py — глобальные синглтоны;
      - в тестах они создаются один раз и живут через все тесты,
        что приводит к утечкам состояния между тестами.
    Что нужно:
      - механизм подмены engine в тестовом окружении
        (через DI, фикстуры или переменную окружения).

  Задача 3 — Покрыть run_async unit-тестами (низкий приоритет)
    Цель: добавить тесты для run_async на все ветки:
          - нормальный loop;
          - закрытый loop;
          - уже работающий loop.
    Причина:
      - после нескольких фиксов run_async стал нетривиальным;
      - нужны изолированные unit-тесты, чтобы ловить регрессии сразу.

"""


from celery import Celery
from kombu import Exchange, Queue

from core.config import settings


# Создаём экземпляр Celery.
# Используем Redis DB 0 как брокер и Redis DB 1 как backend результатов.
celery_app = Celery("mas_dd")

# Backend результатов: меняем номер БД в REDIS_URL на 1.
# Пример: redis://localhost:6379/0 -> redis://localhost:6379/1
_result_backend = settings.REDIS_URL.rsplit("/", 1)[0] + "/1"


celery_app.conf.update(
    # Брокер (очередь сообщений)
    broker_url=settings.REDIS_URL,
    # Backend результатов (хранение результатов задач)
    result_backend=_result_backend,
    # Сериализация: только JSON для безопасности и дебага
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Часовой пояс
    timezone="UTC",
    enable_utc=True,
    # Настройки надёжности
    task_acks_late=True,              # ACK после выполнения задачи, а не до
    worker_prefetch_multiplier=1,     # Воркер берёт по одной задаче
    task_reject_on_worker_lost=True,  # При падении воркера задачи переочередяются
    # Настройки результатов задач
    result_expires=3600,              # Результаты живут 1 час
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    # Определение очередей
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
    ),
    # Очередь по умолчанию
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",
)

# ЯВНАЯ регистрация задач через реестр workers.tasks.
# При старте воркера этот импорт гарантирует, что все таски зарегистрированы.
try:
    import workers.tasks  # noqa: F401
    import workers.run_orchestrator  # noqa: F401  <-- добавить эту строку

except ImportError as e:
    # При старте API (без воркера) модуль workers.tasks может отсутствовать.
    # В этом случае просто логируем предупреждение и не падаем.
    from core.logging import get_logger

    logger = get_logger(__name__)
    logger.warning(
        "Failed to import workers.tasks during celery_app init: %s",
        e,
    )
