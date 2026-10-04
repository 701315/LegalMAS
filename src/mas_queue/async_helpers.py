# src/mas_queue/async_helpers.py

"""
Вспомогательные функции для запуска async-кода из синхронных Celery-тасок.

Исторически воркеры проекта написаны как синхронные Celery entrypoint'ы,
а значительная часть инфраструктуры (репозитории, Unit of Work, SQLAlchemy)
работает асинхронно. Этот модуль даёт стабильный мост между sync-кодом
Celery и async-сервисами/репозиториями.

Текущее состояние и правила использования:

- Для работы с БД использовать db_uow() / get_session()
  из актуального DB-слоя проекта.
- Для перехода sync → async в Celery-тасках и базовых классах
  использовать run_async() из этого модуля.

Важно:
- Внутри Celery-воркеров используется один event loop на процесс.
- Мы НЕ используем asyncio.run() внутри текущей архитектуры воркеров,
  потому что существующий pipeline консистентно построен вокруг
  одного loop на процесс и run_async() как sync → async моста.
- Этот подход является текущим штатным решением проекта, а не временным обходным путём.

Что дополнительно умеет этот модуль:
- Проверять, был ли уже создан worker event loop.
- Аккуратно закрывать worker event loop при завершении процесса воркера.

Технический долг:
- Покрыть run_async unit-тестами:
    * нормальный loop;
    * закрытый loop;
    * вызов из уже работающего async-контекста.
- Покрыть close_worker_loop unit-тестами:
    * loop не создавался;
    * loop уже закрыт;
    * в loop есть pending tasks;
    * shutdown_asyncgens отрабатывает без ошибок.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from core.logging import get_logger

T = TypeVar("T")

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Event loop воркера (единый на процесс)
# ---------------------------------------------------------------------------

_worker_loop: asyncio.AbstractEventLoop | None = None


def get_worker_loop() -> asyncio.AbstractEventLoop:
    """
    Получить (или создать) event loop для процесса Celery-воркера.

    Event loop создаётся один раз при первом обращении и живёт
    до завершения процесса. Это важно для пула подключений
    SQLAlchemy/asyncpg: он должен работать всегда с одним loop.

    Защита:
    - если loop ещё не создан, создаём его;
    - если loop был закрыт (например, в тестах или после cleanup),
      создаём новый.
    """
    global _worker_loop

    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)

    return _worker_loop


def has_worker_loop() -> bool:
    """
    Проверить, существует ли уже worker event loop и не закрыт ли он.

    Для непрофессионального программиста:
    - Эта функция нужна shutdown-коду.
    - Она отвечает на простой вопрос:
      «Есть ли что закрывать, или loop ещё ни разу не создавался?»
    """
    return _worker_loop is not None and not _worker_loop.is_closed()


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """
    Выполнить async-корутину из синхронного кода Celery-таски.

    Вызывать только из синхронного кода (Celery-таски, базовые классы).
    Нельзя вызывать из кода, который уже работает в async-контексте
    (FastAPI-эндпоинты, pytest-asyncio и т.п.).

    Почему не asyncio.run():
      asyncio.run() создаёт и закрывает новый event loop под каждый вызов,
      а текущая архитектура Celery-воркеров в проекте использует один
      долгоживущий loop на процесс.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RuntimeError(
            "run_async() called from a running event loop. "
            "Use 'await' instead, or check the call chain for async/sync mix."
        )

    loop = get_worker_loop()
    return loop.run_until_complete(coro)


def close_worker_loop() -> None:
    """
    Аккуратно закрыть process-wide event loop Celery-воркера.

    Это infrastructure-level cleanup:
    - используется только при завершении процесса воркера;
    - НЕ должен вызываться внутри обычной бизнес-задачи.

    Что делает функция:
    1. Если loop ещё не создавался — просто выходим.
    2. Если loop уже закрыт — очищаем ссылку и выходим.
    3. Если в loop остались незавершённые async-задачи — отменяем их.
    4. Даём loop возможность корректно завершить async generators.
    5. По возможности останавливаем default executor.
    6. Закрываем loop и обнуляем глобальную ссылку.

    Для непрофессионального программиста:
    - Это «аккуратное выключение двигателя».
    - Мы не просто бросаем loop, а стараемся завершить его чисто,
      чтобы не оставлять висящие async-ресурсы и предупреждения в логах.
    """
    global _worker_loop

    loop = _worker_loop

    if loop is None:
        return

    if loop.is_closed():
        _worker_loop = None
        return

    try:
        current = None
        try:
            current = asyncio.current_task(loop=loop)
        except RuntimeError:
            current = None

        pending = {
            task for task in asyncio.all_tasks(loop) if not task.done() and task is not current
        }

        for task in pending:
            task.cancel()

        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

        loop.run_until_complete(loop.shutdown_asyncgens())

        if hasattr(loop, "shutdown_default_executor"):
            loop.run_until_complete(loop.shutdown_default_executor())
    finally:
        loop.close()
        _worker_loop = None


# ---------------------------------------------------------------------------
# Fire-and-forget task callbacks
# ---------------------------------------------------------------------------

def log_task_exception(task: asyncio.Task) -> None:
    """
    Callback для asyncio.Task.add_done_callback.

    Логирует необработанные исключения фоновых задач, созданных через
    asyncio.create_task() без последующего await (fire-and-forget).

    Зачем нужен:
    - create_task без await не пробрасывает исключение наверх;
    - без callback падение задачи остаётся незамеченным;
    - с callback — warning в structured logs, что не блокирует pipeline,
      но даёт observability.

    Поведение:
    - cancelled task → тихо выходим (это нормально при shutdown);
    - task с исключением → logger.warning с полной информацией;
    - task без исключения → ничего не логируем.
    """
    if task.cancelled():
        return

    exc = task.exception()
    if exc is None:
        return

    logger.warning(
        "Background task failed",
        error=str(exc),
        error_type=type(exc).__name__,
        task_name=task.get_name() if hasattr(task, "get_name") else None,
    )
