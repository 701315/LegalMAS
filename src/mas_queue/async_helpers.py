# src/mas_queue/async_helpers.py

"""
Вспомогательные функции для запуска async‑кода из синхронных Celery‑тасок.

Исторически воркеры были синхронными, а репозитории — на async SQLAlchemy.
Этот модуль даёт "мост" между синхронным кодом Celery и асинхронными
репозиториями/сервисами.

Текущее состояние и правила использования:

  - Новый код:
      * НЕ должен использовать get_legacy_worker_session().
      * Для работы с БД использовать db_uow() / get_session() из src.db.session.
      * Для перехода sync → async в тасках и базовых классах
        использовать только run_async() из этого модуля.

  - Legacy-код:
      * get_legacy_worker_session() допустим только в полностью старых
        тасках, которые ещё не переведены на db_uow().
      * По мере рефакторинга такие таски нужно переписывать и
        вычищать использование этого модуля.

Важно:
- Внутри Celery‑воркеров мы используем ОДИН event loop на процесс.
- Мы НЕ вызываем asyncio.run(), потому что он создаёт временный loop
  и закрывает его, что ломает пул подключений SQLAlchemy/asyncpg.
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

    Что это значит простым языком:
    - в каждом процессе воркера Celery есть один "мозг" (event loop),
      который управляет всеми асинхронными операциями;
    - мы создаём этот "мозг" один раз при первом обращении;
    - этот event loop живёт до завершения процесса и НЕ закрывается
      после каждой задачи.

    Это важно для базы данных: пул подключений SQLAlchemy/asyncpg должен
    работать всегда с одним и тем же event loop.
    """
    global _worker_loop

    if _worker_loop is None:
        _worker_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_worker_loop)

    return _worker_loop


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """
    Выполнить async‑корутину из синхронного кода Celery‑таски.

    Простыми словами:
    - Celery вызывает обычную (синхронную) функцию задачи;
    - внутри неё мы хотим запустить асинхронную функцию (работа с БД, MinIO и т.п.);
    - run_async берёт общий event loop воркера и "дожидается" выполнения корутины.

    Ограничения:
    - вызывать только из синхронного кода (Celery‑таски, базовые классы задач);
    - НЕЛЬЗЯ вызывать из кода, который уже работает в async‑контексте
      (FastAPI‑эндпоинты, pytest-asyncio и т.п.).

    Почему так:
    - мы больше НЕ используем asyncio.run(), чтобы не создавать и не
      закрывать новый event loop под каждую задачу;
    - все async‑операции (SQLAlchemy/asyncpg, MinIO) работают через один
      event loop, что соответствует рекомендациям SQLAlchemy.
    """
    # Если мы уже внутри асинхронной функции (есть запущенный event loop),
    # то использование run_async является ошибкой архитектуры.
    try:
        running_loop = asyncio.get_running_loop()
        if running_loop.is_running():
            raise RuntimeError("run_async() called from running event loop")
    except RuntimeError:
        # Здесь нормально оказаться в Celery‑воркере: event loop ещё не создан.
        pass

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

    Важно:
    - новый код должен использовать engine/AsyncSessionLocal из src.db.session;
    - этот engine нужен только для старых тасок, которые ещё не переведены
      на db_uow() / get_session().
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

    Используется только вместе с get_legacy_worker_session() в старых тасках.
    Новый код должен работать через AsyncSessionLocal / db_uow() из db/session.py.
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
    LEGACY: получить async‑сессию БД для использования в *синхронных* Celery‑воркерах
    вместе с run_async().

    Простыми словами:
    - это старый способ "самостоятельно" создать подключение к БД внутри воркера;
    - по мере рефакторинга его нужно убирать и заменять на db_uow().

    НЕ использовать в:
      - обработчиках FastAPI;
      - новых async‑воркерах;
      - тестах (там — src.db.session.get_session / get_db).
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

