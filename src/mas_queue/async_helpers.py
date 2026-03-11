# src/mas_queue/async_helpers.py


"""
Вспомогательные функции для запуска async‑кода из синхронных Celery‑тасок (LEGACY).

Исторически воркеры были синхронными, а репозитории — на async SQLAlchemy.
Этот модуль даёт "мост" между синхронным кодом Celery и асинхронными
репозиториями/сервисами.

Текущее состояние и правила использования:

  - Новый код:
      * НЕ должен использовать run_async и get_legacy_worker_session().
      * Для воркеров — писать таски в стиле:
            @celery_app.task(...)
            def task(...):
                asyncio.run(_async_impl(...))

            async def _async_impl(...):
                ...
      * Для API/тестов — использовать src.db.session.get_session / get_db.

  - Legacy-код:
      * run_async + get_legacy_worker_session() допустимы только
        в старых чисто синхронных Celery‑тасках, которые ещё не
        переведены на новый паттерн.
      * По мере рефакторинга такие таски нужно переписывать и
        вычищать использование этого модуля.

Итого: этот модуль — временный адаптер. В новом коде его импортить не нужно.
"""


import asyncio
from collections.abc import Coroutine
from contextlib import asynccontextmanager
from typing import Any, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from core.config import settings


T = TypeVar("T")

# Лениво инициализируемый engine для процессов воркеров (singleton на процесс)
_engine = None
_session_factory = None


def _get_engine():
    """Получить или создать async‑engine (ленивый singleton на процесс воркера)."""
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
    """Получить или создать фабрику сессий (ленивый singleton на процесс воркера)."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """
    Выполнить async‑корутину из синхронного кода (legacy‑паттерн для Celery‑тасок).

    ВАЖНО:
      - Использовать только в *чисто синхронных* воркерах Celery.
      - НЕЛЬЗЯ вызывать из уже работающих event loop (pytest-asyncio, uvicorn и т.п.).

    Реализация:
      - на каждый вызов создаётся отдельный event loop;
      - не завязана на глобальный loop текущего потока.
    """
    # Всегда создаём свой loop для конкретного вызова,
    # не зависим от глобального event loop текущего потока.
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()
        asyncio.set_event_loop(None)


@asynccontextmanager
async def get_legacy_worker_session():
    """
    LEGACY: получить async‑сессию БД для использования в *синхронных* Celery‑воркерах
    вместе с run_async().

    НЕ использовать в:
      - обработчиках FastAPI;
      - новых async‑воркерах (там — asyncio.run + get_session / get_db);
      - тестах (там — src.db.session.get_session / get_db).

    В новых задачах:
      - создаём сессию через современный слой (db_uow / get_session);
      - не импортируем этот модуль.
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
