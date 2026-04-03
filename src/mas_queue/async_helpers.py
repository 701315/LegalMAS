# src/mas_queue/async_helpers.py

"""
Вспомогательные функции для запуска async‑кода из синхронных Celery‑тасок.

Исторически воркеры проекта написаны как синхронные Celery entrypoint'ы,
а значительная часть инфраструктуры (репозитории, Unit of Work, SQLAlchemy)
работает асинхронно. Этот модуль даёт стабильный мост между sync‑кодом
Celery и async‑сервисами/репозиториями.

Текущее состояние и правила использования:

  - Новый код:
      * НЕ должен использовать get_legacy_worker_session().
      * Для работы с БД использовать db_uow() / get_session()
        из актуального DB-слоя проекта.
      * Для перехода sync → async в Celery‑тасках и базовых классах
        использовать run_async() из этого модуля.

  - Legacy-код:
      * get_legacy_worker_session() допустим только в старых тасках,
        которые ещё не переведены на db_uow().
      * По мере рефакторинга такие таски нужно переводить
        на общий Unit of Work и убирать зависимость от legacy-session factory.

Важно:
  - Внутри Celery‑воркеров используется один event loop на процесс.
  - Мы НЕ используем asyncio.run() внутри текущей архитектуры воркеров,
    потому что существующий pipeline консистентно построен вокруг
    одного loop на процесс и run_async() как sync → async моста.
  - Этот подход является текущим штатным решением проекта, а не временным обходным путём.

Технический долг:
  - Изолировать _engine / _session_factory в тестах, чтобы тестовое окружение
    не делило глобальные singleton-объекты между кейсами.
  - Покрыть run_async unit-тестами:
      * нормальный loop;
      * закрытый loop;
      * вызов из уже работающего async-контекста.
"""

import asyncio
from collections.abc import Coroutine
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Event loop воркера (единый на процесс)
# ---------------------------------------------------------------------------

_worker_loop: asyncio.AbstractEventLoop | None = None


def get_worker_loop() -> asyncio.AbstractEventLoop:
    """
    Получить (или создать) event loop для процесса Celery‑воркера.

    Event loop создаётся один раз при первом обращении и живёт
    до завершения процесса. Это важно для пула подключений
    SQLAlchemy/asyncpg: он должен работать всегда с одним loop.

    Защита: если loop был закрыт (например, в тестах или после
    ошибки), создаём новый.
    """
    global _worker_loop

    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)

    return _worker_loop


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """
    Выполнить async‑корутину из синхронного кода Celery‑таски.

    Вызывать только из синхронного кода (Celery‑таски, базовые классы).
    Нельзя вызывать из кода, который уже работает в async‑контексте
    (FastAPI‑эндпоинты, pytest-asyncio и т.п.).

    Почему не asyncio.run():
      asyncio.run() создаёт и закрывает новый event loop под каждый вызов,
      а текущая архитектура Celery‑воркеров в проекте использует один
      долгоживущий loop на процесс.
    """
    try:
        asyncio.get_running_loop()
        raise RuntimeError(
            "run_async() called from a running event loop. "
            "Use 'await' instead, or check the call chain for async/sync mix."
        )
    except RuntimeError as exc:
        if "run_async() called" in str(exc):
            raise

    loop = get_worker_loop()
    return loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# LEGACY: свой engine/session factory только для старых тасок
# ---------------------------------------------------------------------------

_engine = None
_session_factory = None


def _get_engine():
    """
    LEGACY: получить или создать async‑engine (ленивый singleton на процесс воркера).

    Новый код должен использовать engine/AsyncSessionLocal из актуального DB-слоя.
    """
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.DATABASE_URL,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
        )
    return _engine


def _get_session_factory():
    """
    LEGACY: получить или создать фабрику сессий (singleton на процесс воркера).

    Новый код должен работать через db_uow() / актуальную session factory проекта.
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


@asynccontextmanager
async def get_legacy_worker_session():
    """
    LEGACY: async‑сессия БД для синхронных Celery‑воркеров через run_async().

    НЕ использовать в новом коде. Заменять на db_uow() по мере рефакторинга.
    """
    factory = _get_session_factory()
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()